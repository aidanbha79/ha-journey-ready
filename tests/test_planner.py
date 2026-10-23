from datetime import UTC, datetime, timedelta
from decimal import Decimal

from custom_components.journey_ready.models import (
    Candidate,
    DecisionContext,
    Evidence,
    Obligation,
    Place,
    RoadRoute,
    TransitService,
)
from custom_components.journey_ready.planner import park_ride_candidate, rail_candidate, recommend

ARRIVE = datetime(2026, 10, 23, 9, tzinfo=UTC)
TRIP = Obligation("a", "r", "work", "Office", ARRIVE, ARRIVE + timedelta(hours=8))
EVIDENCE = Evidence("test", ARRIVE, "live", ARRIVE + timedelta(hours=1))


def candidate(mode, minutes=60, delay=0, **kwargs):
    return Candidate(
        mode,
        ARRIVE - timedelta(minutes=minutes),
        ARRIVE,
        cost=Decimal("8"),
        traffic_delay=delay,
        **kwargs,
    )


def test_clear_roads_favour_car():
    result = recommend(TRIP, [candidate("park_ride"), candidate("train", 30)], DecisionContext())
    assert result.selected.mode == "park_ride"


def test_rain_overrides_cost_and_road_delay():
    result = recommend(
        TRIP,
        [candidate("park_ride", 90, 1200), candidate("train", 30)],
        DecisionContext(persistent_rain=True),
    )
    assert result.selected.mode == "park_ride"


def test_road_delay_enables_train_comparison():
    result = recommend(
        TRIP, [candidate("park_ride", 90, 1200), candidate("train", 30)], DecisionContext()
    )
    assert result.selected.mode == "train"


def test_car_required_excludes_train():
    result = recommend(TRIP, [candidate("train")], DecisionContext(car_required=True))
    assert result.selected is None


def test_appointments_never_use_train():
    trip = Obligation("b", "r", "appointment", "Dentist", ARRIVE, ARRIVE)
    assert (
        recommend(trip, [candidate("train")], DecisionContext(kind="appointment")).selected is None
    )


def test_work_never_uses_direct_car():
    assert recommend(TRIP, [candidate("car")], DecisionContext()).selected is None


def test_return_bus_closure_excludes_site():
    assert (
        recommend(
            TRIP, [candidate("park_ride", return_available=False)], DecisionContext()
        ).selected
        is None
    )


def test_car_unavailable_excludes_driving():
    assert (
        recommend(TRIP, [candidate("park_ride")], DecisionContext(car_available=False)).selected
        is None
    )


def test_park_ride_buffers_are_counted_once():
    road = RoadRoute(1800, 20000, 0, EVIDENCE)
    bus = TransitService(
        "b", ARRIVE - timedelta(minutes=40), ARRIVE - timedelta(minutes=15), EVIDENCE
    )
    result = park_ride_candidate(
        TRIP, Place("Site", 54, -1), road, bus, office_walk=5, parking=5, safety=10
    )
    assert result.leave_at == ARRIVE - timedelta(minutes=75)
    assert result.arrive_at == ARRIVE - timedelta(minutes=10)


def test_train_departure_means_start_walking():
    service = TransitService(
        "t", ARRIVE - timedelta(minutes=40), ARRIVE - timedelta(minutes=15), EVIDENCE
    )
    result = rail_candidate(TRIP, service, station_walk=12, office_walk=5, boarding=5, safety=10)
    assert result.leave_at == ARRIVE - timedelta(minutes=57)


def test_unknown_road_traffic_does_not_mean_clear():
    result = recommend(
        TRIP, [candidate("park_ride", 90, None), candidate("train", 30)], DecisionContext()
    )
    assert result.selected.mode == "train"
