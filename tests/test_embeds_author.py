from src.utils.embeds import DowntimeEmbed, ServiceType, MaintenanceType


class FakeAuthor:
    display_name = "Spifuth"


def test_footer_uses_author_display_name():
    embed = DowntimeEmbed.maintenance(
        "traefik", "patch", "30 minutes", FakeAuthor(),
        ServiceType.CONTAINER, MaintenanceType.SECURITY,
    )
    assert "Spifuth" in embed.footer.text


def test_footer_falls_back_when_author_is_none():
    embed = DowntimeEmbed.maintenance(
        "traefik", "patch", "30 minutes", None,
        ServiceType.CONTAINER, MaintenanceType.SECURITY,
    )
    assert embed.footer.text == "Fenrir · Maintenance · inconnu"
