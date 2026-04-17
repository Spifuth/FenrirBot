"""Webhook server for receiving external alerts (Prometheus, Grafana, Generic)"""

import asyncio
import json
from aiohttp import web
from datetime import datetime
from typing import Optional, Callable, Awaitable
import discord


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
        color: int = 0xFF4444,
        fields: Optional[list] = None,
        source: str = "External Alert"
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
            color=color,
            timestamp=datetime.now()
        )
        
        if fields:
            for field in fields:
                embed.add_field(
                    name=field.get("name", "Info"),
                    value=field.get("value", "-"),
                    inline=field.get("inline", True)
                )
        
        embed.set_footer(text=f"🔔 {source} • Fenrir Webhook")
        
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
            "fields": [{"name": "...", "value": "..."}]  # optional
        }
        """
        if not self._verify_token(request):
            return web.Response(status=401, text="Unauthorized")
        
        try:
            data = await request.json()
        except json.JSONDecodeError:
            return web.Response(status=400, text="Invalid JSON")
        
        title = data.get("title", "🔔 Alert")
        message = data.get("message", "No details provided")
        severity = data.get("severity", "warning").lower()
        service = data.get("service")
        fields = data.get("fields", [])
        
        # Color based on severity
        colors = {
            "critical": 0xFF0000,  # Red
            "warning": 0xFFAA00,   # Orange
            "info": 0x5865F2,      # Blue
            "success": 0x44FF44,   # Green
        }
        color = colors.get(severity, 0xFFAA00)
        
        # Add severity emoji to title
        severity_emoji = {
            "critical": "🚨",
            "warning": "⚠️",
            "info": "ℹ️",
            "success": "✅"
        }
        emoji = severity_emoji.get(severity, "🔔")
        
        if service:
            fields.insert(0, {"name": "Service", "value": f"`{service}`", "inline": True})
        
        await self._send_alert(
            title=f"{emoji} {title}",
            description=message,
            color=color,
            fields=fields,
            source="Generic Webhook"
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
            
            if status == "resolved":
                color = 0x44FF44
                emoji = "✅"
                title = f"{emoji} [RESOLVED] {alert_name}"
            else:
                colors = {"critical": 0xFF0000, "warning": 0xFFAA00}
                color = colors.get(severity, 0xFFAA00)
                emoji = "🚨" if severity == "critical" else "⚠️"
                title = f"{emoji} [FIRING] {alert_name}"
            
            fields = []
            if summary:
                fields.append({"name": "Summary", "value": summary, "inline": False})
            
            # Add relevant labels as fields
            for key in ["instance", "job", "service"]:
                if key in labels:
                    fields.append({"name": key.title(), "value": f"`{labels[key]}`", "inline": True})
            
            await self._send_alert(
                title=title,
                description=description,
                color=color,
                fields=fields,
                source="Prometheus"
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
    
    def _create_metric_bar(self, value: float, metric_type: str = "generic") -> str:
        """Create a visual progress bar for metrics"""
        # Determine thresholds based on metric type
        thresholds = {
            "cpu": {"warning": 80, "critical": 95},
            "memory": {"warning": 85, "critical": 95},
            "ram": {"warning": 85, "critical": 95},
            "disk": {"warning": 80, "critical": 90},
            "network": {"warning": 80, "critical": 95},
            "generic": {"warning": 75, "critical": 90},
        }
        
        # Find matching threshold
        thresh = thresholds.get("generic")
        for key in thresholds:
            if key in metric_type.lower():
                thresh = thresholds[key]
                break
        
        # Determine color/emoji based on value
        if value >= thresh["critical"]:
            bar_char = "🟥"
            status = "CRITICAL"
            status_emoji = "🚨"
        elif value >= thresh["warning"]:
            bar_char = "🟨"
            status = "WARNING"
            status_emoji = "⚠️"
        else:
            bar_char = "🟩"
            status = "OK"
            status_emoji = "✅"
        
        # Create the bar (10 segments)
        filled = min(int(value / 10), 10)
        empty = 10 - filled
        bar = bar_char * filled + "⬜" * empty
        
        return f"{bar} **{value:.1f}%** [{status}] {status_emoji}"
    
    def _get_metric_emoji(self, metric_name: str) -> str:
        """Get an appropriate emoji for a metric type"""
        metric_lower = metric_name.lower()
        
        if "cpu" in metric_lower:
            return "🖥️"
        elif "memory" in metric_lower or "ram" in metric_lower:
            return "🧠"
        elif "disk" in metric_lower or "storage" in metric_lower:
            return "💾"
        elif "network" in metric_lower or "bandwidth" in metric_lower or "traffic" in metric_lower:
            return "🌐"
        elif "temp" in metric_lower:
            return "🌡️"
        elif "load" in metric_lower:
            return "📊"
        elif "io" in metric_lower:
            return "💿"
        else:
            return "📈"
    
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
            
            # Build description with metric bars
            desc_parts = []
            
            if status == "resolved":
                color = 0x44FF44
                title = f"✅ [RESOLVED] {alert_name}"
                desc_parts.append("*The alert has been resolved.*")
            else:
                colors = {"critical": 0xFF0000, "warning": 0xFFAA00, "info": 0x5865F2}
                color = colors.get(severity, 0xFFAA00)
                emoji = "🚨" if severity == "critical" else "⚠️"
                title = f"{emoji} [{severity.upper()}] {alert_name}"
            
            # Add visual metric bars for percentage values
            metric_bars = []
            for key, value in values.items():
                if isinstance(value, (int, float)) and 0 <= value <= 100:
                    metric_emoji = self._get_metric_emoji(alert_name)
                    bar = self._create_metric_bar(value, alert_name)
                    metric_bars.append(f"{metric_emoji} **{key}**\n{bar}")
            
            if metric_bars:
                desc_parts.append("\n".join(metric_bars))
            
            if summary:
                desc_parts.append(f"\n📋 {summary}")
            
            if description and description != summary:
                desc_parts.append(f"\n> {description}")
            
            fields = []
            if instance:
                fields.append({"name": "🖥️ Instance", "value": f"`{instance}`", "inline": True})
            if external_url:
                fields.append({"name": "🔗 Dashboard", "value": f"[Open Grafana]({external_url})", "inline": True})
            
            await self._send_alert(
                title=title,
                description="\n".join(desc_parts) if desc_parts else "No details",
                color=color,
                fields=fields,
                source="Grafana"
            )
        
        return web.json_response({"status": "ok", "alerts_processed": len(alerts)})
    
    async def _handle_grafana_legacy(self, data: dict) -> web.Response:
        """Handle legacy Grafana alerting format"""
        title = data.get("title", data.get("ruleName", "Grafana Alert"))
        message = data.get("message", "No message")
        state = data.get("state", "alerting")
        eval_matches = data.get("evalMatches", [])
        rule_url = data.get("ruleUrl", "")
        
        # Color and emoji based on state
        if state == "ok":
            color = 0x44FF44
            emoji = "✅"
            state_text = "RESOLVED"
        elif state == "alerting":
            color = 0xFF4444
            emoji = "🚨"
            state_text = "ALERTING"
        elif state == "no_data":
            color = 0x808080
            emoji = "❓"
            state_text = "NO DATA"
        else:
            color = 0xFFAA00
            emoji = "⚠️"
            state_text = "PENDING"
        
        # Build description with metric bars
        desc_parts = [f"**Status:** {state_text}", ""]
        
        for match in eval_matches[:5]:
            metric = match.get("metric", "Value")
            value = match.get("value", 0)
            
            metric_emoji = self._get_metric_emoji(metric)
            
            # If it looks like a percentage, show a bar
            if isinstance(value, (int, float)) and 0 <= value <= 100:
                bar = self._create_metric_bar(value, metric)
                desc_parts.append(f"{metric_emoji} **{metric}**\n{bar}")
            else:
                desc_parts.append(f"{metric_emoji} **{metric}:** `{value}`")
        
        if message and message != title:
            desc_parts.append(f"\n📋 {message}")
        
        fields = []
        if rule_url:
            fields.append({"name": "🔗 Dashboard", "value": f"[Open Alert]({rule_url})", "inline": True})
        
        await self._send_alert(
            title=f"{emoji} {title}",
            description="\n".join(desc_parts),
            color=color,
            fields=fields,
            source="Grafana"
        )
        
        return web.json_response({"status": "ok"})
    
