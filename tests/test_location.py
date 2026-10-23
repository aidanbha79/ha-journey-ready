from datetime import UTC, datetime, timedelta

from custom_components.journey_ready.location import resolve_origin
from custom_components.journey_ready.models import Place

NOW = datetime(2026, 10, 23, 8, tzinfo=UTC)
HOME = Place("Home", 54.0, -1.2)


def test_uses_home_when_home():
    assert resolve_origin("home", {}, NOW, HOME, NOW).place == HOME


def test_fresh_away_location():
    result = resolve_origin(
        "not_home", {"latitude": 53.9, "longitude": -1.1, "gps_accuracy": 20}, NOW, HOME, NOW
    )
    assert result.place.latitude == 53.9
    assert not result.provisional


def test_location_requires_coordinates():
    assert resolve_origin("not_home", {}, NOW, HOME, NOW).place is None


def test_location_age_11_minutes_is_stale():
    attrs = {"latitude": 53.9, "longitude": -1.1, "gps_accuracy": 20}
    assert resolve_origin("not_home", attrs, NOW - timedelta(minutes=11), HOME, NOW).place is None


def test_accuracy_201_metres_rejected():
    attrs = {"latitude": 53.9, "longitude": -1.1, "gps_accuracy": 201}
    assert resolve_origin("not_home", attrs, NOW, HOME, NOW).place is None


def test_tomorrow_away_origin_is_provisional_home():
    result = resolve_origin("not_home", {}, NOW, HOME, NOW, future=True)
    assert result.place == HOME
    assert result.provisional


def test_unknown_presence_does_not_imply_home():
    assert resolve_origin("unknown", {}, NOW, HOME, NOW).place is None
