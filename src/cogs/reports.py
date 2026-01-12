"""Server statistics reports - Daily, Weekly, Monthly summaries from Netdata"""

import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta, time, timezone
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, field
from enum import Enum
import aiohttp
import asyncio
import json
import os

from ..config import config
from ..utils.helpers import (
    create_progress_bar,
    format_duration,
    THRESHOLDS,
    PARIS_TZ
)


class ReportPeriod(Enum):
    """Report period types"""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    
    @property
    def seconds(self) -> int:
        """Get period in seconds for Netdata API"""
        return {
            ReportPeriod.DAILY: 86400,      # 24 hours
            ReportPeriod.WEEKLY: 604800,    # 7 days
            ReportPeriod.MONTHLY: 2592000,  # 30 days
        }[self]
    
    @property
    def emoji(self) -> str:
        return {
            ReportPeriod.DAILY: "📅",
            ReportPeriod.WEEKLY: "📊",
            ReportPeriod.MONTHLY: "📈",
        }[self]
    
    @property
    def title(self) -> str:
        return {
            ReportPeriod.DAILY: "Rapport Journalier",
            ReportPeriod.WEEKLY: "Rapport Hebdomadaire",
            ReportPeriod.MONTHLY: "Rapport Mensuel",
        }[self]


@dataclass
class MetricStats:
    """Statistics for a single metric"""
    name: str
    emoji: str
    unit: str
    current: float = 0.0
    average: float = 0.0
    minimum: float = 0.0
    maximum: float = 0.0
    peak_time: Optional[datetime] = None
    low_time: Optional[datetime] = None
    
    def format_value(self, value: float) -> str:
        """Format value with unit"""
        if self.unit == "%":
            return f"{value:.1f}%"
        elif self.unit == "°C":
            return f"{value:.1f}°C"
        elif self.unit == "GB":
            return f"{value:.2f} GB"
        elif self.unit == "MB/s":
            return f"{value:.2f} MB/s"
        elif self.unit == "Mbps":
            return f"{value:.2f} Mbps"
        else:
            return f"{value:.2f} {self.unit}"
    
    def create_bar(self, value: float, max_val: float = 100) -> str:
        """Create a visual progress bar"""
        percentage = min((value / max_val) * 100, 100) if max_val > 0 else 0
        
        if percentage >= 90:
            bar_char = "🟥"
        elif percentage >= 75:
            bar_char = "🟨"
        else:
            bar_char = "🟩"
        
        filled = min(int(percentage / 10), 10)
        empty = 10 - filled
        return bar_char * filled + "⬜" * empty


@dataclass 
class ServerReport:
    """Complete server statistics report"""
    hostname: str
    period: ReportPeriod
    generated_at: datetime
    metrics: Dict[str, MetricStats] = field(default_factory=dict)
    uptime_seconds: int = 0
    alerts_count: int = 0
    docker_containers: int = 0
    docker_healthy: int = 0


class ReportsCog(commands.Cog):
    """Periodic server statistics reports"""
    
    # Data file for storing historical stats
    DATA_FILE = "data/server_stats.json"
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.netdata_url = getattr(config, 'netdata_url', '') if config else ''
        self.reports_channel_id = getattr(config, 'reports_channel_id', 0) if config else 0
        
        # Report schedule times (24h format)
        self.daily_time = time(hour=8, minute=0)    # 8:00 AM
        self.weekly_day = 0  # Monday
        self.weekly_time = time(hour=9, minute=0)   # 9:00 AM Monday
        self.monthly_day = 1  # 1st of month
        self.monthly_time = time(hour=10, minute=0) # 10:00 AM on 1st
        
        # Historical data storage
        self.stats_history: List[Dict] = []
        self._load_history()
        
        # Start background tasks
        self.collect_stats.start()
        self.daily_report.start()
        self.weekly_report.start()
        self.monthly_report.start()
    
    def cog_unload(self):
        """Cleanup when cog is unloaded"""
        self.collect_stats.cancel()
        self.daily_report.cancel()
        self.weekly_report.cancel()
        self.monthly_report.cancel()
        self._save_history()
    
    def _load_history(self):
        """Load historical stats from file"""
        try:
            if os.path.exists(self.DATA_FILE):
                with open(self.DATA_FILE, 'r') as f:
                    self.stats_history = json.load(f)
                # Keep only last 35 days of data
                cutoff = (datetime.now() - timedelta(days=35)).timestamp()
                self.stats_history = [s for s in self.stats_history if s.get('timestamp', 0) > cutoff]
        except Exception as e:
            print(f"  ⚠️ Could not load stats history: {e}")
            self.stats_history = []
    
    def _save_history(self):
        """Save historical stats to file"""
        try:
            os.makedirs(os.path.dirname(self.DATA_FILE), exist_ok=True)
            with open(self.DATA_FILE, 'w') as f:
                json.dump(self.stats_history, f)
        except Exception as e:
            print(f"  ⚠️ Could not save stats history: {e}")
    
    async def _fetch_netdata(self, endpoint: str) -> Optional[dict]:
        """Fetch data from Netdata API"""
        if not self.netdata_url:
            return None
        
        url = f"{self.netdata_url.rstrip('/')}/api/v1/{endpoint}"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as response:
                    if response.status == 200:
                        return await response.json()
        except Exception as e:
            print(f"  ⚠️ Netdata API error: {e}")
        return None
    
    async def _get_metric_data(self, chart: str, after: int = -3600, points: int = 60) -> Optional[dict]:
        """Get metric data with multiple points for analysis"""
        endpoint = f"data?chart={chart}&after={after}&points={points}&format=json&options=absolute"
        return await self._fetch_netdata(endpoint)
    
    async def _collect_current_stats(self) -> Dict[str, float]:
        """Collect current statistics from Netdata"""
        stats = {
            'timestamp': datetime.now().timestamp(),
            'cpu': 0.0,
            'ram': 0.0,
            'disk': 0.0,
            'net_in': 0.0,
            'net_out': 0.0,
            'temp': 0.0,
            'load': 0.0,
        }
        
        # CPU
        cpu_data = await self._get_metric_data("system.cpu", after=-60, points=1)
        if cpu_data and "data" in cpu_data:
            try:
                values = cpu_data["data"][0][1:]
                labels = cpu_data.get("labels", [])
                idle_idx = labels.index("idle") - 1 if "idle" in labels else -1
                if idle_idx >= 0:
                    stats['cpu'] = 100 - values[idle_idx]
                else:
                    stats['cpu'] = sum(v for v in values if v and v > 0)
            except:
                pass
        
        # RAM
        ram_data = await self._get_metric_data("system.ram", after=-60, points=1)
        if ram_data and "data" in ram_data:
            try:
                values = ram_data["data"][0][1:]
                labels = ram_data.get("labels", [])
                used_idx = labels.index("used") - 1 if "used" in labels else -1
                free_idx = labels.index("free") - 1 if "free" in labels else -1
                cached_idx = labels.index("cached") - 1 if "cached" in labels else -1
                buffers_idx = labels.index("buffers") - 1 if "buffers" in labels else -1
                
                if used_idx >= 0:
                    used = abs(values[used_idx])
                    free = abs(values[free_idx]) if free_idx >= 0 else 0
                    cached = abs(values[cached_idx]) if cached_idx >= 0 else 0
                    buffers = abs(values[buffers_idx]) if buffers_idx >= 0 else 0
                    total = used + free + cached + buffers
                    if total > 0:
                        stats['ram'] = (used / total) * 100
            except:
                pass
        
        # Disk
        disk_data = await self._get_metric_data("disk_space._", after=-60, points=1)
        if disk_data and "data" in disk_data:
            try:
                values = disk_data["data"][0][1:]
                labels = disk_data.get("labels", [])
                avail_idx = labels.index("avail") - 1 if "avail" in labels else -1
                used_idx = labels.index("used") - 1 if "used" in labels else -1
                
                if avail_idx >= 0 and used_idx >= 0:
                    avail = abs(values[avail_idx])
                    used = abs(values[used_idx])
                    total = avail + used
                    if total > 0:
                        stats['disk'] = (used / total) * 100
            except:
                pass
        
        # Network
        net_data = await self._get_metric_data("system.net", after=-60, points=1)
        if net_data and "data" in net_data:
            try:
                values = net_data["data"][0][1:]
                labels = net_data.get("labels", [])
                recv_idx = labels.index("received") - 1 if "received" in labels else -1
                sent_idx = labels.index("sent") - 1 if "sent" in labels else -1
                
                if recv_idx >= 0:
                    stats['net_in'] = abs(values[recv_idx]) / 1000  # Convert to Mbps
                if sent_idx >= 0:
                    stats['net_out'] = abs(values[sent_idx]) / 1000
            except:
                pass
        
        # Load
        load_data = await self._get_metric_data("system.load", after=-60, points=1)
        if load_data and "data" in load_data:
            try:
                values = load_data["data"][0][1:]
                stats['load'] = values[0] if values else 0
            except:
                pass
        
        return stats
    
    def _analyze_period(self, period: ReportPeriod) -> Dict[str, MetricStats]:
        """Analyze statistics for a given period"""
        now = datetime.now()
        cutoff = (now - timedelta(seconds=period.seconds)).timestamp()
        
        # Filter data for period
        period_data = [s for s in self.stats_history if s.get('timestamp', 0) > cutoff]
        
        if not period_data:
            return {}
        
        metrics = {}
        
        # Define metrics to analyze
        metric_defs = [
            ('cpu', '🖥️ CPU', '%'),
            ('ram', '🧠 RAM', '%'),
            ('disk', '💾 Disque', '%'),
            ('net_in', '📥 Network In', 'Mbps'),
            ('net_out', '📤 Network Out', 'Mbps'),
            ('load', '📊 Load', ''),
        ]
        
        for key, name, unit in metric_defs:
            values_with_time = [(s.get(key, 0), s.get('timestamp', 0)) for s in period_data if key in s]
            
            if not values_with_time:
                continue
            
            values = [v[0] for v in values_with_time]
            
            # Find peak and low times
            max_val = max(values)
            min_val = min(values)
            peak_entry = next((v for v in values_with_time if v[0] == max_val), None)
            low_entry = next((v for v in values_with_time if v[0] == min_val), None)
            
            metrics[key] = MetricStats(
                name=name,
                emoji=name.split()[0],
                unit=unit,
                current=values[-1] if values else 0,
                average=sum(values) / len(values),
                minimum=min_val,
                maximum=max_val,
                peak_time=datetime.fromtimestamp(peak_entry[1]) if peak_entry else None,
                low_time=datetime.fromtimestamp(low_entry[1]) if low_entry else None,
            )
        
        return metrics
    
    async def _generate_report(self, period: ReportPeriod) -> Optional[ServerReport]:
        """Generate a complete server report"""
        # Get system info
        info = await self._fetch_netdata("info")
        if not info:
            return None
        
        hostname = info.get("hostname", "Unknown")
        uptime = info.get("uptime", 0)
        
        # Analyze metrics
        metrics = self._analyze_period(period)
        
        # Get current values for metrics that weren't in history
        current = await self._collect_current_stats()
        for key, stat in metrics.items():
            if stat.current == 0 and key in current:
                stat.current = current[key]
        
        # Get alerts count
        alarms_data = await self._fetch_netdata("alarms?all")
        alerts_count = 0
        if alarms_data:
            for alarm in alarms_data.get("alarms", {}).values():
                if alarm.get("status") in ["WARNING", "CRITICAL"]:
                    alerts_count += 1
        
        return ServerReport(
            hostname=hostname,
            period=period,
            generated_at=datetime.now(),
            metrics=metrics,
            uptime_seconds=int(uptime),
            alerts_count=alerts_count,
        )
    
    def _create_report_embed(self, report: ServerReport) -> discord.Embed:
        """Create a Discord embed from a server report"""
        
        # Determine color based on metrics
        color = 0x44FF44  # Green
        for metric in report.metrics.values():
            if metric.average > 90:
                color = 0xFF0000  # Red
                break
            elif metric.average > 75:
                color = 0xFFAA00  # Orange
        
        embed = discord.Embed(
            title=f"{report.period.emoji} {report.period.title} - {report.hostname}",
            description=f"Période : **{report.period.value}** | Généré le {report.generated_at.strftime('%d/%m/%Y à %H:%M')}",
            color=color,
            timestamp=report.generated_at
        )
        
        # Uptime
        days, remainder = divmod(report.uptime_seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, _ = divmod(remainder, 60)
        uptime_str = f"{days}j {hours}h {minutes}m"
        
        embed.add_field(
            name="⏱️ Uptime",
            value=f"`{uptime_str}`",
            inline=True
        )
        
        # Alerts
        alert_emoji = "✅" if report.alerts_count == 0 else "⚠️"
        embed.add_field(
            name=f"{alert_emoji} Alertes Actives",
            value=f"`{report.alerts_count}`",
            inline=True
        )
        
        embed.add_field(name="\u200b", value="\u200b", inline=True)  # Spacer
        
        # Metrics
        for key in ['cpu', 'ram', 'disk', 'net_in', 'net_out', 'load']:
            metric = report.metrics.get(key)
            if not metric:
                continue
            
            # Create visual bar for percentage metrics
            if metric.unit == '%':
                bar = metric.create_bar(metric.average)
                current_bar = metric.create_bar(metric.current)
                
                value_text = (
                    f"**Actuel:** {current_bar} {metric.format_value(metric.current)}\n"
                    f"**Moyenne:** {bar} {metric.format_value(metric.average)}\n"
                    f"📈 **Max:** {metric.format_value(metric.maximum)}"
                )
                if metric.peak_time:
                    value_text += f" ({metric.peak_time.strftime('%d/%m %H:%M')})"
                value_text += f"\n📉 **Min:** {metric.format_value(metric.minimum)}"
                if metric.low_time:
                    value_text += f" ({metric.low_time.strftime('%d/%m %H:%M')})"
            else:
                value_text = (
                    f"**Actuel:** {metric.format_value(metric.current)}\n"
                    f"**Moyenne:** {metric.format_value(metric.average)}\n"
                    f"📈 **Max:** {metric.format_value(metric.maximum)}\n"
                    f"📉 **Min:** {metric.format_value(metric.minimum)}"
                )
            
            embed.add_field(
                name=f"{metric.name}",
                value=value_text,
                inline=True
            )
        
        embed.set_footer(text="🐺 Fenrir Server Reports")
        
        return embed
    
    async def _send_report(self, period: ReportPeriod):
        """Generate and send a report to the configured channel"""
        if not self.reports_channel_id:
            return
        
        channel = self.bot.get_channel(self.reports_channel_id)
        if not channel:
            print(f"  ⚠️ Reports channel {self.reports_channel_id} not found")
            return
        
        report = await self._generate_report(period)
        if not report:
            return
        
        embed = self._create_report_embed(report)
        await channel.send(embed=embed)
    
    # ═══════════════════════════════════════════════════════════════
    # Background Tasks
    # ═══════════════════════════════════════════════════════════════
    
    @tasks.loop(minutes=5)
    async def collect_stats(self):
        """Collect statistics every 5 minutes"""
        if not self.netdata_url:
            return
        
        stats = await self._collect_current_stats()
        self.stats_history.append(stats)
        
        # Keep only last 35 days
        cutoff = (datetime.now() - timedelta(days=35)).timestamp()
        self.stats_history = [s for s in self.stats_history if s.get('timestamp', 0) > cutoff]
        
        # Save periodically (every hour)
        if len(self.stats_history) % 12 == 0:
            self._save_history()
    
    @collect_stats.before_loop
    async def before_collect_stats(self):
        await self.bot.wait_until_ready()
    
    @tasks.loop(time=time(hour=8, minute=0, tzinfo=PARIS_TZ))
    async def daily_report(self):
        """Send daily report at 8:00 AM Paris time"""
        await self._send_report(ReportPeriod.DAILY)
    
    @daily_report.before_loop
    async def before_daily_report(self):
        await self.bot.wait_until_ready()
    
    @tasks.loop(time=time(hour=9, minute=0, tzinfo=PARIS_TZ))
    async def weekly_report(self):
        """Send weekly report on Monday at 9:00 AM Paris time"""
        if datetime.now().weekday() == 0:  # Monday
            await self._send_report(ReportPeriod.WEEKLY)
    
    @weekly_report.before_loop
    async def before_weekly_report(self):
        await self.bot.wait_until_ready()
    
    @tasks.loop(time=time(hour=10, minute=0, tzinfo=PARIS_TZ))
    async def monthly_report(self):
        """Send monthly report on 1st of month at 10:00 AM Paris time"""
        if datetime.now().day == 1:
            await self._send_report(ReportPeriod.MONTHLY)
    
    @monthly_report.before_loop
    async def before_monthly_report(self):
        await self.bot.wait_until_ready()
    
    # ═══════════════════════════════════════════════════════════════
    # Slash Commands
    # ═══════════════════════════════════════════════════════════════
    
    reports_group = app_commands.Group(
        name="reports",
        description="📊 Commandes de rapports serveur"
    )
    
    @reports_group.command(name="daily", description="📅 Générer un rapport journalier")
    async def report_daily(self, interaction: discord.Interaction):
        """Generate a daily report on demand"""
        await interaction.response.defer(thinking=True)
        
        if not self.netdata_url:
            await interaction.followup.send("❌ Netdata n'est pas configuré.", ephemeral=True)
            return
        
        report = await self._generate_report(ReportPeriod.DAILY)
        if not report:
            await interaction.followup.send("❌ Impossible de générer le rapport.", ephemeral=True)
            return
        
        embed = self._create_report_embed(report)
        await interaction.followup.send(embed=embed)
    
    @reports_group.command(name="weekly", description="📊 Générer un rapport hebdomadaire")
    async def report_weekly(self, interaction: discord.Interaction):
        """Generate a weekly report on demand"""
        await interaction.response.defer(thinking=True)
        
        if not self.netdata_url:
            await interaction.followup.send("❌ Netdata n'est pas configuré.", ephemeral=True)
            return
        
        report = await self._generate_report(ReportPeriod.WEEKLY)
        if not report:
            await interaction.followup.send("❌ Impossible de générer le rapport.", ephemeral=True)
            return
        
        embed = self._create_report_embed(report)
        await interaction.followup.send(embed=embed)
    
    @reports_group.command(name="monthly", description="📈 Générer un rapport mensuel")
    async def report_monthly(self, interaction: discord.Interaction):
        """Generate a monthly report on demand"""
        await interaction.response.defer(thinking=True)
        
        if not self.netdata_url:
            await interaction.followup.send("❌ Netdata n'est pas configuré.", ephemeral=True)
            return
        
        report = await self._generate_report(ReportPeriod.MONTHLY)
        if not report:
            await interaction.followup.send("❌ Impossible de générer le rapport.", ephemeral=True)
            return
        
        embed = self._create_report_embed(report)
        await interaction.followup.send(embed=embed)
    
    @reports_group.command(name="now", description="⚡ Rapport instantané de l'état actuel")
    async def report_now(self, interaction: discord.Interaction):
        """Generate an instant status report"""
        await interaction.response.defer(thinking=True)
        
        if not self.netdata_url:
            await interaction.followup.send("❌ Netdata n'est pas configuré.", ephemeral=True)
            return
        
        # Get current stats
        stats = await self._collect_current_stats()
        info = await self._fetch_netdata("info")
        
        if not info:
            await interaction.followup.send("❌ Impossible de contacter Netdata.", ephemeral=True)
            return
        
        hostname = info.get("hostname", "Unknown")
        uptime = info.get("uptime", 0)
        
        # Create embed
        embed = discord.Embed(
            title=f"⚡ État Instantané - {hostname}",
            color=0x5865F2,
            timestamp=datetime.now()
        )
        
        # Uptime
        days, remainder = divmod(int(uptime), 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, _ = divmod(remainder, 60)
        
        embed.add_field(name="⏱️ Uptime", value=f"`{days}j {hours}h {minutes}m`", inline=True)
        
        cpu = stats.get('cpu', 0)
        ram = stats.get('ram', 0)
        disk = stats.get('disk', 0)
        
        embed.add_field(
            name="🖥️ CPU",
            value=create_progress_bar(cpu, "cpu"),
            inline=False
        )
        embed.add_field(
            name="🧠 RAM",
            value=create_progress_bar(ram, "ram"),
            inline=False
        )
        embed.add_field(
            name="💾 Disque",
            value=create_progress_bar(disk, "disk"),
            inline=False
        )
        
        net_in = stats.get('net_in', 0)
        net_out = stats.get('net_out', 0)
        embed.add_field(
            name="🌐 Réseau",
            value=f"📥 `{net_in:.2f} Mbps` | 📤 `{net_out:.2f} Mbps`",
            inline=False
        )
        
        load = stats.get('load', 0)
        embed.add_field(name="📊 Load", value=f"`{load:.2f}`", inline=True)
        
        embed.set_footer(text="🐺 Fenrir Server Reports")
        
        await interaction.followup.send(embed=embed)
    
    @reports_group.command(name="config", description="⚙️ Configurer le canal des rapports")
    @app_commands.describe(channel="Le canal où envoyer les rapports automatiques")
    @app_commands.checks.has_permissions(administrator=True)
    async def report_config(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Configure the reports channel"""
        self.reports_channel_id = channel.id
        
        # Note: In production, this should be saved to config/env
        embed = discord.Embed(
            title="✅ Canal Configuré",
            description=f"Les rapports automatiques seront envoyés dans {channel.mention}\n\n"
                        f"**Horaires:**\n"
                        f"📅 **Journalier:** 8h00\n"
                        f"📊 **Hebdo:** Lundi 9h00\n"
                        f"📈 **Mensuel:** 1er du mois 10h00\n\n"
                        f"⚠️ Ajoute `REPORTS_CHANNEL_ID={channel.id}` à ton `.env` pour persister ce paramètre.",
            color=0x44FF44
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @report_config.error
    async def report_config_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "❌ Tu as besoin des permissions d'administrateur.",
                ephemeral=True
            )


async def setup(bot: commands.Bot):
    """Setup function for loading the cog"""
    await bot.add_cog(ReportsCog(bot))
    print("  ✅ Loaded: Server reports cog")
