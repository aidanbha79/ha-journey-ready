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


@pytest.mark.asyncio
async def test_bus_must_still_be_reachable_from_now():
    now = NOW.replace(hour=7, minute=20)
    trip = Obligation("a", "r", "work", "Office", NOW.replace(hour=9), NOW.replace(hour=17))
    plan = (await Engine(SETTINGS, Road()).plan([trip], HOME, now, RuntimeState()))[0]
    assert plan.selected.leave_at >= now
    assert plan.selected.leave_at == NOW.replace(hour=7, minute=35)


@pytest.mark.asyncio
async def test_empty_bus_board_does_not_claim_coverage_of_later_timetable():
    class EmptyBus:
        async def departures(self, *args):
            return []

    settings = {**SETTINGS, "park_ride_sites": [{**SITE, "stop_id": "stop", "line": "9"}]}
    trip = Obligation("a", "r", "work", "Office", NOW.replace(hour=9), NOW.replace(hour=17))
    plan = (await Engine(settings, Road(), bus=EmptyBus()).plan([trip], HOME, NOW, RuntimeState()))[
        0
    ]
    assert plan.selected is not None
    assert any("unconfirmed" in warning for warning in plan.warnings)


@pytest.mark.asyncio
async def test_late_car_candidate_reports_achievable_arrival():
    trip = Obligation(
        "a", "r", "appointment", "Dentist", NOW + timedelta(minutes=10), NOW + timedelta(hours=1)
    )
    settings = {**SETTINGS, "destinations": {"Dentist": OFFICE}}
    plan = (await Engine(settings, Road()).plan([trip], HOME, NOW, RuntimeState()))[0]
    assert plan.selected is None
    assert plan.alternatives[0].arrive_at >= NOW + timedelta(minutes=25)
    assert any("deadline" in warning for warning in plan.warnings)


@pytest.mark.asyncio
@pytest.mark.parametrize("appointment_time,possible", [("17:45", False), ("18:30", True)])
async def test_onward_car_requires_return_to_parked_car(appointment_time, possible):
    work = Obligation("work", "r", "work", "Office", NOW.replace(hour=9), NOW.replace(hour=17))
    hour, minute = map(int, appointment_time.split(":"))
    appointment = Obligation(
        "dentist",
        "r",
        "appointment",
        "Dentist",
        NOW.replace(hour=hour, minute=minute),
        NOW.replace(hour=19),
    )
    settings = {
        **SETTINGS,
        "park_ride_sites": [{**SITE, "return_departures": "17:10,17:40"}],
        "destinations": {"Dentist": {**OFFICE, "name": "Dentist"}},
    }
    plans = await Engine(settings, Road()).plan([work, appointment], HOME, NOW, RuntimeState())
    assert (plans[1].selected is not None) is possible
    if possible:
        assert "Collect car at Site" in plans[1].selected.detail
        assert plans[1].selected.leave_at >= work.end_at


@pytest.mark.asyncio
async def test_onward_car_without_confirmed_return_bus_is_unresolved():
    work = Obligation("work", "r", "work", "Office", NOW.replace(hour=9), NOW.replace(hour=17))
    appointment = Obligation(
        "dentist", "r", "appointment", "Dentist", NOW.replace(hour=18), NOW.replace(hour=19)
    )
    settings = {**SETTINGS, "destinations": {"Dentist": OFFICE}}
    plans = await Engine(settings, Road()).plan([work, appointment], HOME, NOW, RuntimeState())
    assert plans[1].selected is None
    assert any("return departures" in warning for warning in plans[1].warnings)


@pytest.mark.asyncio
async def test_started_park_ride_is_remembered_for_afternoon_collection():
    from custom_components.journey_ready.vehicle import remember_departure

    work = Obligation("work", "r", "work", "Office", NOW.replace(hour=9), NOW.replace(hour=17))
    appointment = Obligation(
        "dentist", "r", "appointment", "Dentist", NOW.replace(hour=19), NOW.replace(hour=20)
    )
    settings = {
        **SETTINGS,
        "home_location": {
            "name": HOME.name,
            "latitude": HOME.latitude,
            "longitude": HOME.longitude,
        },
        "park_ride_sites": [{**SITE, "return_departures": "17:40,18:00"}],
        "destinations": {"Dentist": {**OFFICE, "name": "Dentist"}},
    }
    state = RuntimeState()
    morning = await Engine(settings, Road()).plan([work], HOME, NOW, state)
    remember_departure(state, morning[0])
    # Simulate reload and an actual phone origin at the office after work.
    state = RuntimeState(overrides=state.overrides)
    plans = await Engine(settings, Road()).plan(
        [work, appointment],
        Place(
            **{"name": "Office", "latitude": OFFICE["latitude"], "longitude": OFFICE["longitude"]}
        ),
        NOW.replace(hour=17),
        state,
    )
    assert plans[0].selected is None
    assert plans[1].selected is not None
    assert "Collect car at Site" in plans[1].selected.detail


@pytest.mark.asyncio
async def test_cancelled_bus_cannot_return_from_manual_timetable():
    from custom_components.journey_ready.providers.bus import parse_departures

    class CancelledBus:
        async def departures(self, *args):
            return parse_departures(
                {
                    "departures": {
                        "9": [
                            {
                                "line": "9",
                                "date": "2026-10-23",
                                "aimed_departure_time": "08:30",  # London time, 07:30 UTC
                                "status": "cancelled",
                            }
                        ]
                    }
                },
                "9",
                NOW,
            )

    settings = {
        **SETTINGS,
        "park_ride_sites": [{**SITE, "stop_id": "stop", "line": "9", "departures": "07:30"}],
    }
    trip = Obligation("a", "r", "work", "Office", NOW.replace(hour=9), NOW.replace(hour=17))
    plan = (
        await Engine(settings, Road(), bus=CancelledBus()).plan([trip], HOME, NOW, RuntimeState())
    )[0]
    assert plan.selected is None


@pytest.mark.asyncio
async def test_late_timed_work_end_invalidates_return_site():
    from custom_components.journey_ready.calendar import normalise_events
    from custom_components.journey_ready.questions import revision_for

    early = normalise_events(
        [
            {
                "summary": "Office",
                "uid": "a",
                "start": NOW.replace(hour=9),
                "end": NOW.replace(hour=17),
            }
        ],
        {},
        UTC,
    )[0]
    late = normalise_events(
        [
            {
                "summary": "Office",
                "uid": "a",
                "start": NOW.replace(hour=9),
                "end": NOW.replace(hour=23),
            }
        ],
        {},
        UTC,
    )[0]
    assert revision_for([early], "2026-10-23") != revision_for([late], "2026-10-23")
    assert (await Engine(SETTINGS, Road()).plan([late], HOME, NOW, RuntimeState()))[
        0
    ].selected is None


@pytest.mark.asyncio
async def test_train_commute_does_not_create_a_car_at_the_office():
    work = Obligation("work", "r", "work", "Office", NOW.replace(hour=9), NOW.replace(hour=17))
    appointment = Obligation(
        "dentist", "r", "appointment", "Dentist", NOW.replace(hour=19), NOW.replace(hour=20)
    )
    settings = {
        **SETTINGS,
        "park_ride_sites": [],
        "rail_enabled": True,
        "car_required_default": False,
        "origin_station": OFFICE,
        "destination_station": OFFICE,
        "rail_timetable_confirmed": True,
        "rail_departures": "07:40",
        "rail_minutes": 30,
        "rail_last_return": "22:00",
        "destinations": {"Dentist": OFFICE},
    }
    plans = await Engine(settings, Road()).plan([work, appointment], HOME, NOW, RuntimeState())
    assert plans[0].selected.mode == "train"
    assert plans[1].selected is None
    assert any("Car is not confirmed" in warning for warning in plans[1].warnings)


@pytest.mark.asyncio
async def test_return_departure_cannot_collect_car_after_gate_closes():
    trip = Obligation("work", "r", "work", "Office", NOW.replace(hour=9), NOW.replace(hour=17))
    settings = {
        **SETTINGS,
        "park_ride_sites": [{**SITE, "return_departures": "22:00", "closes": "22:15"}],
    }
    assert (await Engine(settings, Road()).plan([trip], HOME, NOW, RuntimeState()))[
        0
    ].selected is None
