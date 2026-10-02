from datetime import datetime, timezone

import pytest

from src.utils.helpers import parse_local_datetime, format_paris


def test_summer_input_is_utc_plus_two():
    # 2026-09-05 is CEST (UTC+2): 22:00 Paris == 20:00 UTC
    assert parse_local_datetime("2026-09-05 22:00") == datetime(
        2026, 9, 5, 20, 0, tzinfo=timezone.utc
    )


def test_winter_input_is_utc_plus_one():
    # 2026-01-15 is CET (UTC+1): 22:00 Paris == 21:00 UTC
    assert parse_local_datetime("2026-01-15 22:00") == datetime(
        2026, 1, 15, 21, 0, tzinfo=timezone.utc
    )


def test_result_is_timezone_aware():
    assert parse_local_datetime("2026-09-05 22:00").tzinfo is not None


def test_malformed_input_raises_value_error():
    with pytest.raises(ValueError):
        parse_local_datetime("pas une date")


def test_format_paris_renders_local_wall_clock():
    utc = datetime(2026, 9, 5, 20, 0, tzinfo=timezone.utc)
    assert format_paris(utc, "%H:%M") == "22:00"
