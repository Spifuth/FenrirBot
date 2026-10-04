"""Discord-facing paths of /rapport (VictoriaMetrics) and /alerts (Grafana).

The HTTP clients are replaced with fakes on the cog instance; the clients
themselves are pinned in test_grafana_client.py. Cogs are built with __new__
so their __init__ never reads the module-level config.
"""

import asyncio
from datetime import datetime, timedelta, timezone

from src.cogs.alerts import AlertsCog
from src.cogs.reports import ReportsCog
from tests.discord_fakes import FakeInteraction, field

# ── /rapport ───────────────────────────────────────────────────────────────

class FakeVM:
    def __init__(self, stats=None, instant=None):
        self.stats = stats
        self.instant = instant
        self.range_calls: list[tuple] = []
        self.instant_calls: list[str] = []

    async def query_range_stats(self, query, start, end, step):
        self.range_calls.append((query, start, end, step))
        return self.stats

    async def query_instant(self, query):
        self.instant_calls.append(query)
        return self.instant


def _reports_cog(vm):
    cog = ReportsCog.__new__(ReportsCog)
    cog.bot = None
    cog.vm = vm
    return cog


def test_rapport_without_victoriametrics_refuses_before_deferring():
    inter = FakeInteraction()

    asyncio.run(ReportsCog.rapport_slash.callback(_reports_cog(None), inter))

    assert inter.log.names() == ["response.send_message"]
    reply = inter.log.of("response.send_message")[0]
    assert "VICTORIAMETRICS_URL" in reply["content"]
    assert reply["ephemeral"] is True


def test_rapport_weekly_queries_seven_days_and_renders_cpu_ram_network():
    vm = FakeVM(stats={"avg": 42.0, "max": 97.5, "min": 1.0}, instant=3 * 1_073_741_824)
    inter = FakeInteraction()

    asyncio.run(ReportsCog.rapport_slash.callback(_reports_cog(vm), inter, periode="weekly"))

    assert inter.log.names() == ["response.defer", "followup.send"]
    assert [step for *_, step in vm.range_calls] == ["6h", "6h"]
    _, start, end, _ = vm.range_calls[0]
    assert end - start == timedelta(days=7)
    assert all("[604800s]" in q for q in vm.instant_calls)

    embed = inter.log.of("followup.send")[0]["embed"]
    assert embed.title == "Rapport · 7 derniers jours"
    assert field(embed, "CPU") == (
        "```\navg  [████······]   42.0%\npic  [██████████]   97.5%\n```"
    )
    assert field(embed, "RAM") == field(embed, "CPU")
    assert field(embed, "Réseau") == "```\n↓      3.00 GB\n↑      3.00 GB\n```"


def test_rapport_renders_na_when_victoriametrics_has_no_data():
    inter = FakeInteraction()

    asyncio.run(ReportsCog.rapport_slash.callback(_reports_cog(FakeVM()), inter))

    embed = inter.log.of("followup.send")[0]["embed"]
    assert embed.title == "Rapport · 24 dernières heures"
    assert field(embed, "CPU") == "```\nn/a\n```"
    assert field(embed, "Réseau") == "```\n↓         N/A\n↑         N/A\n```"


# ── /alerts ────────────────────────────────────────────────────────────────

class FakeGrafana:
    def __init__(self, alerts):
        self.alerts = alerts

    async def get_active_alerts(self):
        return self.alerts


def _alerts_cog(grafana):
    cog = AlertsCog.__new__(AlertsCog)
    cog.bot = None
    cog.grafana = grafana
    return cog


def _alert(name, severity="warning", minutes_ago=5, **extra_labels):
    started = (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat()
    return {
        "labels": {"alertname": name, "severity": severity, **extra_labels},
        "annotations": {"summary": f"{name} summary"},
        "startsAt": started.replace("+00:00", "Z"),
    }


def test_alerts_without_grafana_refuses_before_deferring():
    inter = FakeInteraction()

    asyncio.run(AlertsCog.alerts_slash.callback(_alerts_cog(None), inter))

    assert inter.log.names() == ["response.send_message"]
    assert inter.log.of("response.send_message")[0]["ephemeral"] is True


def test_alerts_unreachable_grafana_is_not_rendered_as_all_clear():
    inter = FakeInteraction()

    asyncio.run(AlertsCog.alerts_slash.callback(_alerts_cog(FakeGrafana(None)), inter))

    assert inter.log.names() == ["response.defer", "followup.send"]
    embed = inter.log.of("followup.send")[0]["embed"]
    assert embed.title == "Statut inconnu"
    assert "pas" in embed.description
    assert embed.footer.text == "Fenrir · Grafana injoignable"


def test_alerts_empty_list_is_the_all_clear():
    inter = FakeInteraction()

    asyncio.run(AlertsCog.alerts_slash.callback(_alerts_cog(FakeGrafana([])), inter))

    embed = inter.log.of("followup.send")[0]["embed"]
    assert embed.title == "Aucune alerte"
    assert embed.footer.text == "Fenrir · Grafana"


def test_alerts_renders_one_field_per_alert_with_severity_and_instance():
    alerts = [
        _alert("DiskFull", severity="critical", minutes_ago=90, instance="krypton:9100"),
        _alert("HighLoad", severity="warning", minutes_ago=3, job="node"),
    ]
    inter = FakeInteraction()

    asyncio.run(AlertsCog.alerts_slash.callback(_alerts_cog(FakeGrafana(alerts)), inter))

    embed = inter.log.of("followup.send")[0]["embed"]
    assert embed.title == "Alertes · 2"
    assert embed.description == "1 critique · 1 avertissement"
    assert field(embed, "DiskFull") == (
        "```\nCRITICAL · depuis 1h 30m\nkrypton:9100\nDiskFull summary\n```"
    )
    assert field(embed, "HighLoad").splitlines()[2] == "node", "falls back to the job label"
    assert embed.footer.text == "Fenrir · Grafana Alertmanager"


def test_alerts_shows_ten_and_counts_the_overflow_in_the_footer():
    alerts = [_alert(f"A{i}") for i in range(13)]
    inter = FakeInteraction()

    asyncio.run(AlertsCog.alerts_slash.callback(_alerts_cog(FakeGrafana(alerts)), inter))

    embed = inter.log.of("followup.send")[0]["embed"]
    assert len(embed.fields) == 10
    assert embed.title == "Alertes · 13"
    assert embed.footer.text == "Fenrir · Grafana Alertmanager · +3 non affichée(s)"
