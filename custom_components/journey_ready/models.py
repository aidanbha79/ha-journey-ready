"""Portable domain models with no Home Assistant dependency."""

import math
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class Place:
    name: str
    latitude: float
    longitude: float

    def __post_init__(self):
        if not math.isfinite(self.latitude) or not -90 <= self.latitude <= 90:
            raise ValueError("Invalid latitude")
        if not math.isfinite(self.longitude) or not -180 <= self.longitude <= 180:
            raise ValueError("Invalid longitude")


@dataclass(frozen=True)
class Evidence:
    source: str
    observed_at: datetime
    kind: str = "unknown"
    valid_until: datetime | None = None

    def fresh(self, now: datetime) -> bool:
        return self.kind not in ("unknown", "stale") and (
            self.valid_until is None or now <= self.valid_until
        )


@dataclass(frozen=True)
class Obligation:
    id: str
    revision: str
    kind: str
    destination: str
    arrival_by: datetime
    end_at: datetime
    title: str = ""


@dataclass(frozen=True)
class OriginResult:
    place: Place | None
    provisional: bool = False
    reason: str = ""


@dataclass(frozen=True)
class RoadRoute:
    seconds: int
    metres: int
    delay_seconds: int
    evidence: Evidence


@dataclass(frozen=True)
class TransitService:
    id: str
    departure: datetime
    arrival: datetime
    evidence: Evidence
    cancelled: bool = False
    line: str = ""


@dataclass(frozen=True)
class Candidate:
    mode: str
    leave_at: datetime
    arrive_at: datetime
    cost: Decimal | None = None
    traffic_delay: int | None = None
    feasible: bool = True
    return_available: bool = True
    drive_destination: Place | None = None
    detail: str = ""
    evidence: tuple[Evidence, ...] = ()
    walking_minutes: int = 0

    @property
    def duration(self) -> float:
        return (self.arrive_at - self.leave_at).total_seconds()


@dataclass(frozen=True)
class DecisionContext:
    kind: str = "work"
    car_required: bool = False
    persistent_rain: bool | None = None
    road_delay_minutes: int = 10
    car_available: bool = True
    previous_mode: str | None = None
    lock_mode: bool = False


@dataclass(frozen=True)
class Recommendation:
    obligation: Obligation
    selected: Candidate | None
    alternatives: tuple[Candidate, ...] = ()
    reasons: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass
class RuntimeState:
    sent: dict[str, str] = field(default_factory=dict)
    questions: dict = field(default_factory=dict)
    overrides: dict = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)
    started: list[str] = field(default_factory=list)
