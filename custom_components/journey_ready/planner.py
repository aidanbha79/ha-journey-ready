"""Deterministic complete-journey construction and selection."""

from datetime import timedelta
from decimal import Decimal

from .models import Candidate, Recommendation


def park_ride_candidate(
    obligation,
    site,
    road,
    bus,
    *,
    office_walk=0,
    parking=5,
    safety=10,
    cost=None,
    return_available=True,
):
    leave = bus.departure - timedelta(seconds=road.seconds, minutes=parking)
    arrive = bus.arrival + timedelta(minutes=office_walk)
    feasible = not bus.cancelled and arrive <= obligation.arrival_by - timedelta(minutes=safety)
    return Candidate(
        "park_ride",
        leave,
        arrive,
        cost,
        road.delay_seconds,
        feasible,
        return_available,
        site,
        f"{site.name}, bus {bus.line}",
        (road.evidence, bus.evidence),
        office_walk,
    )


def rail_candidate(
    obligation,
    service,
    *,
    station_walk=0,
    office_walk=0,
    boarding=5,
    safety=10,
    cost=None,
    return_available=True,
):
    leave = service.departure - timedelta(minutes=station_walk + boarding)
    arrive = service.arrival + timedelta(minutes=office_walk)
    feasible = not service.cancelled and arrive <= obligation.arrival_by - timedelta(minutes=safety)
    return Candidate(
        "train",
        leave,
        arrive,
        cost,
        None,
        feasible,
        return_available,
        None,
        f"Train {service.departure:%H:%M}, arrive {service.arrival:%H:%M}",
        (service.evidence,),
        station_walk + office_walk,
    )


def recommend(obligation, candidates, context):
    allowed = {"park_ride", "train"} if obligation.kind == "work" else {"car"}
    viable = [
        c
        for c in candidates
        if c.mode in allowed
        and c.feasible
        and c.return_available
        and c.arrive_at <= obligation.arrival_by
    ]
    if not context.car_available:
        viable = [c for c in viable if c.mode == "train"]
    car_required = context.car_required or context.persistent_rain is True
    if car_required:
        viable = [c for c in viable if c.mode != "train"]
    reason = "Shortest feasible journey; cost breaks ties"
    if context.car_required:
        reason = "Car needed after work"
    elif context.persistent_rain:
        reason = "Persistent rain forecast"
    if context.lock_mode and context.previous_mode:
        previous = [c for c in viable if c.mode == context.previous_mode]
        if previous:
            viable = previous
            reason = "Keep the current travel mode close to departure"
    if not car_required:
        clear = [
            c
            for c in viable
            if c.mode != "train"
            and c.traffic_delay is not None
            and c.traffic_delay <= context.road_delay_minutes * 60
        ]
        if clear:
            viable = clear
            reason = "Roads are within your delay threshold"

    def key(c):
        return (c.duration, c.cost if c.cost is not None else Decimal("Infinity"))

    selected = min(viable, key=key) if viable else None
    return Recommendation(
        obligation,
        selected,
        tuple(candidates),
        (reason,) if selected else ("No feasible journey for your requirements",),
    )
