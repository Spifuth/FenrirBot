"""Webhook server for receiving external alerts (Prometheus, Grafana, Generic)"""

import asyncio
import json
from aiohttp import web
from datetime import datetime, timezone
from typing import Optional, Callable, Awaitable
import discord


def _bar(value: float, width: int = 10) -> str:
    """Render a fixed-width ASCII progress bar using █ and ·."""
    filled = round(max(0.0, min(value, 100.0)) / 100 * width)
    return "[" + "█" * filled + "·" * (width - filled) + "]"


class WebhookServer:
    """HTTP server for receiving webhook alerts"""
    
    def __init__(
        self,
        bot: discord.Client,
        host: str = "0.0.0.0",
        port: int = 8080,
        secret_token: Optional[str] = None
    ):
        self.bot = bot
        self.host = host
        self.port = port
        self.secret_token = secret_token
        self.app = web.Application()
        self.runner: Optional[web.AppRunner] = None
        self.channel_id: Optional[int] = None
        self.notification_mention: str = "@here"
        self.start_time: datetime = datetime.now()

        # Setup routes
        self.app.router.add_post("/webhook/generic", self.handle_generic)
        self.app.router.add_post("/webhook/prometheus", self.handle_prometheus)
        self.app.router.add_post("/webhook/grafana", self.handle_grafana)
        self.app.router.add_get("/health", self.health_check)
        self.app.router.add_get("/metrics", self.metrics)
    
    def set_channel(self, channel_id: int):
        """Set the channel to send alerts to"""
        self.channel_id = channel_id
    
    def set_mention(self, mention: str):
        """Set the mention string for alerts"""
        self.notification_mention = mention
    
    async def start(self):
        """Start the webhook server"""
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, self.host, self.port)
        await site.start()
        print(f"🌐 Webhook server started on http://{self.host}:{self.port}")
    
    async def stop(self):
        """Stop the webhook server"""
        if self.runner:
            await self.runner.cleanup()
            print("🌐 Webhook server stopped")
    
    def _verify_token(self, request: web.Request) -> bool:
        """Verify the authorization token if configured"""
        if not self.secret_token:
            return True
        
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return auth_header[7:] == self.secret_token
        
        # Also check query param
        return request.query.get("token") == self.secret_token
    
    async def _send_alert(
        self,
        title: str,
        description: str,
        fields: list | None = None,
        source: str = "External Alert",
    ):
        """Send an alert embed to the configured channel"""
        if not self.channel_id:
            print("⚠️ Webhook received but no channel configured")
            return

        channel = self.bot.get_channel(self.channel_id)
        if not channel or not isinstance(channel, discord.abc.Messageable):
            print(f"⚠️ Channel {self.channel_id} not found")
            return

        embed = discord.Embed(
            title=title,
            description=description,
            color=0x2C2F33,
            timestamp=datetime.now(timezone.utc),
        )

        if fields:
            for field in fields:
                embed.add_field(
                    name=field.get("name", "Info"),
                    value=field.get("value", "-"),
                    inline=field.get("inline", False),
                )

        embed.set_footer(text=f"Fenrir · {source}")

        await channel.send(content=self.notification_mention, embed=embed)
    
    # ═══════════════════════════════════════════════════════════════
    # Route Handlers
    # ═══════════════════════════════════════════════════════════════
    
    async def health_check(self, request: web.Request) -> web.Response:
        """Health check endpoint"""
        return web.json_response({
            "status": "ok",
            "bot_ready": self.bot.is_ready(),
            "timestamp": datetime.now().isoformat()
        })

    async def metrics(self, request: web.Request) -> web.Response:
        """Bot metrics endpoint for Glance dashboard"""
        uptime = (datetime.now() - self.start_time).total_seconds()
        return web.json_response({
            "bot_ready": self.bot.is_ready(),
            "guilds": len(self.bot.guilds) if self.bot.is_ready() else 0,
            "latency_ms": round(self.bot.latency * 1000, 1),
            "uptime_seconds": round(uptime),
            "cogs_loaded": len(self.bot.cogs),
        })

    async def handle_generic(self, request: web.Request) -> web.Response:
        """Handle generic webhook alerts

        Expected JSON body:
        {
            "title": "Alert Title",
            "message": "Alert description",
            "severity": "critical|warning|info",
            "service": "optional service name",
            "fields": [{"name": "...", "value": "..."}]
        }
        """
        if not self._verify_token(request):
            return web.Response(status=401, text="Unauthorized")

        try:
            data = await request.json()
        except json.JSONDecodeError:
            return web.Response(status=400, text="Invalid JSON")

        title = data.get("title", "Alerte")
        message = data.get("message", "Aucun détail")
        severity = data.get("severity", "warning").lower()
        service = data.get("service")
        fields = data.get("fields", [])

        if service:
            fields.insert(0, {"name": "Service", "value": f"```\n{service}\n```", "inline": True})

        description = f"```\nSévérité : {severity.upper()}\n```\n{message}"

        await self._send_alert(
            title=title,
            description=description,
            fields=fields,
            source="Generic Webhook",
        )

        return web.json_response({"status": "ok", "message": "Alert sent"})
    
    async def handle_prometheus(self, request: web.Request) -> web.Response:
        """Handle Prometheus Alertmanager webhooks

        Prometheus Alertmanager sends alerts in this format:
        {
            "status": "firing|resolved",
            "alerts": [{
                "status": "firing",
                "labels": {"alertname": "...", "severity": "..."},
                "annotations": {"summary": "...", "description": "..."}
            }]
        }
        """
        if not self._verify_token(request):
            return web.Response(status=401, text="Unauthorized")

        try:
            data = await request.json()
        except json.JSONDecodeError:
            return web.Response(status=400, text="Invalid JSON")

        alerts = data.get("alerts", [])

        for alert in alerts:
            status = alert.get("status", "unknown")
            labels = alert.get("labels", {})
            annotations = alert.get("annotations", {})

            alert_name = labels.get("alertname", "Unknown Alert")
            severity = labels.get("severity", "warning")
            summary = annotations.get("summary", "")
            description = annotations.get("description", "No description")

            state_label = "RESOLVED" if status == "resolved" else "FIRING"
            title = f"[{state_label}] {alert_name}"

            fields = []
            if summary:
                fields.append({"name": "Résumé", "value": summary, "inline": False})
            for key in ["instance", "job", "service"]:
                if key in labels:
                    fields.append({"name": key.title(), "value": f"```\n{labels[key]}\n```", "inline": True})

            await self._send_alert(
                title=title,
                description=f"```\nSévérité : {severity.upper()}\n```\n{description}",
                fields=fields,
                source="Prometheus",
            )

        return web.json_response({"status": "ok", "alerts_processed": len(alerts)})
    
    async def handle_grafana(self, request: web.Request) -> web.Response:
        """Handle Grafana webhook notifications
        
        Supports both legacy and unified alerting formats.
        """
        if not self._verify_token(request):
            return web.Response(status=401, text="Unauthorized")
        
        try:
            data = await request.json()
        except json.JSONDecodeError:
            return web.Response(status=400, text="Invalid JSON")
        
        # Check if it's unified alerting (Grafana 8+) or legacy format
        if "alerts" in data:
            return await self._handle_grafana_unified(data)
        else:
            return await self._handle_grafana_legacy(data)
    
    async def _handle_grafana_unified(self, data: dict) -> web.Response:
        """Handle Grafana Unified Alerting (Grafana 8+)

        Format:
        {
            "alerts": [{
                "status": "firing|resolved",
                "labels": {"alertname": "...", "severity": "..."},
                "annotations": {"summary": "...", "description": "..."},
                "values": {"A": 92.5}
            }],
            "commonLabels": {...},
            "externalURL": "..."
        }
        """
        alerts = data.get("alerts", [])
        external_url = data.get("externalURL", "")

        for alert in alerts:
            status = alert.get("status", "firing")
            labels = alert.get("labels", {})
            annotations = alert.get("annotations", {})
            values = alert.get("values", {})

            alert_name = labels.get("alertname", "Grafana Alert")
            severity = labels.get("severity", "warning")
            instance = labels.get("instance", "")
            summary = annotations.get("summary", "")
            description = annotations.get("description", "")

            state_label = "RESOLVED" if status == "resolved" else severity.upper()
            title = f"[{state_label}] {alert_name}"

            bar_lines = []
            for key, value in values.items():
                if isinstance(value, (int, float)) and 0 <= value <= 100:
                    bar_lines.append(f"{key:<12} {_bar(value)}  {value:.1f}%")
                else:
                    bar_lines.append(f"{key}: {value}")

            text_parts = []
            if summary:
                text_parts.append(summary)
            if description and description != summary:
                text_parts.append(description)

            parts = []
            if bar_lines:
                parts.append("```\n" + "\n".join(bar_lines) + "\n```")
            if text_parts:
                parts.append("\n".join(text_parts))
            full_description = "\n".join(parts) if parts else "Aucun détail"

            fields = []
            if instance:
                fields.append({"name": "Instance", "value": f"```\n{instance}\n```", "inline": True})
            if external_url:
                fields.append({"name": "Dashboard", "value": f"[Grafana]({external_url})", "inline": True})

            await self._send_alert(
                title=title,
                description=full_description,
                fields=fields,
                source="Grafana",
            )

        return web.json_response({"status": "ok", "alerts_processed": len(alerts)})
    
    async def _handle_grafana_legacy(self, data: dict) -> web.Response:
        """Handle legacy Grafana alerting format"""
        title = data.get("title", data.get("ruleName", "Grafana Alert"))
        message = data.get("message", "No message")
        state = data.get("state", "alerting")
        eval_matches = data.get("evalMatches", [])
        rule_url = data.get("ruleUrl", "")

        state_label = {
            "ok": "RESOLVED",
            "alerting": "FIRING",
            "no_data": "NO DATA",
        }.get(state, "PENDING")
        title_str = f"[{state_label}] {title}"

        bar_lines = []
        for match in eval_matches[:5]:
            metric = match.get("metric", "Value")
            value = match.get("value", 0)
            if isinstance(value, (int, float)) and 0 <= value <= 100:
                bar_lines.append(f"{metric:<12} {_bar(value)}  {value:.1f}%")
            else:
                bar_lines.append(f"{metric}: {value}")

        parts = []
        if bar_lines:
            parts.append("```\n" + "\n".join(bar_lines) + "\n```")
        if message and message != title:
            parts.append(message)
        full_description = "\n".join(parts) if parts else "Aucun détail"

        fields = []
        if rule_url:
            fields.append({"name": "Dashboard", "value": f"[Grafana]({rule_url})", "inline": True})

        await self._send_alert(
            title=title_str,
            description=full_description,
            fields=fields,
            source="Grafana",
        )

        return web.json_response({"status": "ok"})
    
