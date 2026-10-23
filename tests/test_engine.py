from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from custom_components.journey_ready.engine import Engine
from custom_components.journey_ready.models import (
    Evidence,
    Obligation,
    Place,
    RoadRoute,
    RuntimeState,
)
from custom_components.journey_ready.providers.base import ProviderError

NOW = datetime(2026, 10, 23, 6, tzinfo=UTC)
HOME = Place("Home", 54, -1.2)
OFFICE = {"name": "Office", "latitude": 53.96, "longitude": -1.08}
SITE = {
    "name": "Site",
    "latitude": 54.01,
    "longitude": -1.1,
    "departures": "07:30,08:00",
    "bus_minutes": 20,
    "office_walk": 5,
    "last_return": "22:00",
    "closes": "22:30",
    "return_walk": 5,
    "days": [0, 1, 2, 3, 4, 5, 6],
    "timetable_confirmed": True,
}
SETTINGS = {
    "office_address": "Office",
    "office_location": OFFICE,
    "park_ride_sites": [SITE],
    "diesel_price": 1.5,
    "mpg": 45,
    "park_ride_fare": 4,
    "safety_minutes": 10,
    "parking_minutes": 5,
    "car_available": True,
}


class Road:
    async def route(self, origin, destination, departure, **kwargs):
        return RoadRoute(
            1200, 16093, 0, Evidence("road", NOW, "forecast", NOW + timedelta(hours=1))
        )

    async def geocode(self, query):
        return [Place(query, 53.9, -1)]


@pytest.mark.asyncio
async def test_engine_builds_work_park_ride_and_return_cost():
    trip = Obligation(
        "a", "r", "work", "Office", NOW + timedelta(hours=3), NOW + timedelta(hours=10)
    )
    plans = await Engine(SETTINGS, Road()).plan([trip], HOME, NOW, RuntimeState())
    assert plans[0].selected.mode == "park_ride"
    assert plans[0].selected.drive_destination.name == "Site"
    assert round(plans[0].selected.cost, 2) == Decimal("7.03")
    assert plans[0].selected.arrive_at <= trip.arrival_by - timedelta(minutes=10)


@pytest.mark.asyncio
async def test_engine_rejects_site_that_closes_before_return():
    settings = {
        **SETTINGS,
        "park_ride_sites": [{**SITE, "last_return": "12:00", "closes": "12:30"}],
    }
    trip = Obligation(
        "a", "r", "work", "Office", NOW + timedelta(hours=2), NOW + timedelta(hours=10)
    )
    assert (await Engine(settings, Road()).plan([trip], HOME, NOW, RuntimeState()))[
        0
    ].selected is None


@pytest.mark.asyncio
async def test_engine_appointment_routes_to_confirmed_destination():
    trip = Obligation(
        "a", "r", "appointment", "Dentist", NOW + timedelta(hours=4), NOW + timedelta(hours=5)
    )
    settings = {
        **SETTINGS,
        "destinations": {"Dentist": {"name": "Dentist", "latitude": 53.9, "longitude": -1.0}},
    }
    plan = (await Engine(settings, Road()).plan([trip], HOME, NOW, RuntimeState()))[0]
    assert plan.selected.mode == "car"
    assert plan.selected.drive_destination.name == "Dentist"


@pytest.mark.asyncio
async def test_unconfirmed_address_is_not_silently_selected():
    trip = Obligation(
        "a", "r", "appointment", "Dentist", NOW + timedelta(hours=4), NOW + timedelta(hours=5)
    )
    plan = (await Engine(SETTINGS, Road()).plan([trip], HOME, NOW, RuntimeState()))[0]
    assert plan.selected is None
    assert any("confirm" in warning.lower() for warning in plan.warnings)


@pytest.mark.asyncio
async def test_provider_failure_does_not_fake_clear_roads():
    class FailedRoad(Road):
        async def route(self, *args, **kwargs):
            raise ProviderError("Source unavailable")

    trip = Obligation(
        "a", "r", "work", "Office", NOW + timedelta(hours=2), NOW + timedelta(hours=10)
    )
    plan = (await Engine(SETTINGS, FailedRoad()).plan([trip], HOME, NOW, RuntimeState()))[0]
    assert plan.selected is None
    assert plan.warnings


@pytest.mark.asyncio
async def test_unique_postcode_location_can_be_resolved_automatically():
    trip = Obligation(
        "a",
        "r",
        "appointment",
        "Dentist, YO1 1AA",
        NOW + timedelta(hours=4),
        NOW + timedelta(hours=5),
    )
    plan = (await Engine(SETTINGS, Road()).plan([trip], HOME, NOW, RuntimeState()))[0]
    assert plan.selected is not None
    assert plan.selected.drive_destination.name == "Dentist, YO1 1AA"


@pytest.mark.asyncio
async def test_ambiguous_postcode_matches_require_confirmation():
    class Ambiguous(Road):
        async def geocode(self, query):
            return [Place("A", 54, -1), Place("B", 53, -1)]

    trip = Obligation(
        "a",
        "r",
        "appointment",
        "Dentist, YO1 1AA",
        NOW + timedelta(hours=4),
        NOW + timedelta(hours=5),
    )
    plan = (await Engine(SETTINGS, Ambiguous()).plan([trip], HOME, NOW, RuntimeState()))[0]
    assert plan.selected is None
