from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from custom_components.journey_ready.models import Place
from custom_components.journey_ready.providers.base import ProviderError
from custom_components.journey_ready.providers.bus import parse_departures
from custom_components.journey_ready.providers.fuel import sensor_price
from custom_components.journey_ready.providers.rail import parse_board
from custom_components.journey_ready.providers.tomtom import TomTom, parse_route
from custom_components.journey_ready.providers.weather import classify_rain

NOW = datetime(2026, 10, 23, 7, tzinfo=UTC)


def test_traffic_delay_is_not_added_twice():
    route = parse_route(
        {
            "routes": [
                {
                    "summary": {
                        "travelTimeInSeconds": 1800,
                        "lengthInMeters": 20000,
                        "trafficDelayInSeconds": 300,
                    }
                }
            ]
        },
        NOW,
        NOW,
    )
    assert route.seconds == 1800
    assert route.delay_seconds == 300


def test_missing_route_is_an_error():
    with pytest.raises(ProviderError):
        parse_route({"routes": []}, NOW, NOW)


def test_future_route_is_forecast():
    data = {
        "routes": [
            {
                "summary": {
                    "travelTimeInSeconds": 100,
                    "lengthInMeters": 1000,
                    "trafficDelayInSeconds": 0,
                }
            }
        ]
    }
    assert parse_route(data, NOW, NOW + timedelta(days=1)).evidence.kind == "forecast"


def test_cancelled_and_unknown_delay_train_are_rejected():
    records = [
        {"serviceID": "a", "std": "08:30", "etd": "On time", "isCancelled": True},
        {"serviceID": "b", "std": "08:40", "etd": "Delayed"},
    ]
    assert parse_board({"generatedAt": NOW.isoformat(), "trainServices": records}, "YRK", NOW) == []


def test_train_must_call_at_destination():
    record = {
        "serviceID": "a",
        "std": "08:30",
        "etd": "On time",
        "subsequentCallingPoints": [
            {"callingPoint": [{"crs": "YRK", "st": "09:00", "et": "09:05"}]}
        ],
    }
    services = parse_board({"generatedAt": NOW.isoformat(), "trainServices": [record]}, "YRK", NOW)
    assert services[0].arrival.isoformat() == "2026-10-23T09:05:00+01:00"
    assert (
        parse_board({"generatedAt": NOW.isoformat(), "trainServices": [record]}, "LDS", NOW) == []
    )


def test_bus_positions_are_not_arrival_predictions():
    assert parse_departures({"vehicles": [{"latitude": 54}]}, "9", NOW) == []


def test_bus_route_is_filtered_and_missing_expected_is_timetable():
    data = {
        "departures": {
            "9": [
                {
                    "line": "9",
                    "date": "2026-10-23",
                    "aimed_departure_time": "08:30",
                    "expected_departure_time": None,
                }
            ],
            "8": [{"line": "8", "date": "2026-10-23", "aimed_departure_time": "08:10"}],
        }
    }
    services = parse_departures(data, "9", NOW)
    assert len(services) == 1
    assert services[0].evidence.kind == "timetable"


def test_insufficient_weather_coverage_is_unknown():
    assert (
        classify_rain(
            [{"datetime": NOW.isoformat(), "precipitation_probability": 90}],
            NOW,
            NOW + timedelta(hours=8),
        )
        is None
    )


def test_all_day_rain_threshold():
    hours = [
        {
            "datetime": (NOW + timedelta(hours=i)).isoformat(),
            "precipitation_probability": 80 if i < 6 else 0,
        }
        for i in range(8)
    ]
    assert classify_rain(hours, NOW, NOW + timedelta(hours=8)) is True


def test_fuel_sensor_is_explicitly_priced_and_fresh():
    assert sensor_price("149.9", "p/L", NOW, NOW) == Decimal("1.499")
    assert sensor_price("unknown", "p/L", NOW, NOW) is None
    assert sensor_price("150", "p/L", NOW - timedelta(days=3), NOW) is None


@pytest.mark.asyncio
async def test_tomtom_encodes_the_route_and_does_not_log_key():
    class HTTP:
        async def get(self, url, **kwargs):
            assert url.endswith("/54.0,-1.2:53.9,-1.1/json")
            assert kwargs["params"]["key"] == "secret"
            assert kwargs["params"]["traffic"] == "true"
            return {
                "routes": [
                    {
                        "summary": {
                            "travelTimeInSeconds": 100,
                            "lengthInMeters": 1000,
                            "trafficDelayInSeconds": 0,
                        }
                    }
                ]
            }

    provider = TomTom(HTTP(), "secret")
    assert (
        await provider.route(Place("A", 54, -1.2), Place("B", 53.9, -1.1), NOW, now=NOW)
    ).seconds == 100
