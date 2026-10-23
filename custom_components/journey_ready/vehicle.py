"""Remember the work mode actually started, rather than moving the car with the person."""

from dataclasses import asdict
from datetime import datetime

from .models import Candidate, Place


def remember_departure(state, plan):
    if plan.obligation.kind != "work" or not plan.selected:
        return
    selected = plan.selected
    state.overrides.setdefault("_commutes", {})[plan.obligation.id] = {
        "revision": plan.obligation.revision,
        "mode": selected.mode,
        "leave_at": selected.leave_at.isoformat(),
        "site": asdict(selected.drive_destination) if selected.drive_destination else None,
    }


def started_commute(state, trip):
    saved = state.overrides.get("_commutes", {}).get(trip.id, {})
    if saved.get("revision") != trip.revision:
        return None
    try:
        return Candidate(
            saved["mode"],
            datetime.fromisoformat(saved["leave_at"]),
            trip.arrival_by,
            drive_destination=Place(**saved["site"]) if saved.get("site") else None,
        )
    except (KeyError, TypeError, ValueError):
        return None
