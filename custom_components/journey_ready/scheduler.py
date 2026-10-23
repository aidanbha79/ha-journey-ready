"""Pure reminder reconciliation, with delivery acknowledgement."""

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class Reminder:
    key: str
    stage: str
    plan: object


def due_reminders(state, recommendations, now, change_minutes=5):
    reminders = []
    for plan in recommendations:
        trip, candidate = plan.obligation, plan.selected
        if trip.id in state.skipped or trip.id in state.started or now >= trip.arrival_by:
            continue
        prefix = f"{trip.id}:{trip.revision}:"
        if not candidate:
            if prefix + "unavailable" not in state.sent and (
                prefix + "last" in state.sent or trip.arrival_by - now <= timedelta(hours=2)
            ):
                reminders.append(Reminder(prefix + "unavailable", "unavailable", plan))
            continue
        if prefix + "unavailable" in state.sent:
            reminders.append(Reminder(prefix + "recovered", "recovered", plan))
            continue
        if now >= candidate.leave_at:
            stage = "late"
        elif now >= candidate.leave_at - timedelta(minutes=15):
            stage = "leave"
        elif now >= candidate.leave_at - timedelta(hours=1):
            stage = "hour"
        else:
            stage = None
        key = prefix + stage if stage else None
        # A new late or quarter-hour message supersedes the one-hour reminder.
        if key and key not in state.sent:
            reminders.append(Reminder(key, stage, plan))
            continue
        previous = state.sent.get(prefix + "last", state.sent.get(prefix + "hour"))
        if previous:
            try:
                difference = abs(
                    (datetime.fromisoformat(previous) - candidate.leave_at).total_seconds()
                )
            except ValueError:
                difference = 0
            if difference >= change_minutes * 60:
                reminders.append(Reminder(prefix + "changed", "changed", plan))
    return reminders


def mark_sent(state, reminder):
    prefix = f"{reminder.plan.obligation.id}:{reminder.plan.obligation.revision}:"
    if reminder.stage == "unavailable":
        state.sent[reminder.key] = "1"
        return
    if reminder.stage == "recovered":
        state.sent.pop(prefix + "unavailable", None)
    value = reminder.plan.selected.leave_at.isoformat()
    state.sent[reminder.key] = value
    state.sent[prefix + "last"] = value
    if reminder.stage in ("leave", "late"):
        state.sent.setdefault(prefix + "hour", value)
    if reminder.stage == "late":
        state.sent.setdefault(prefix + "leave", value)


def prune_state(state, recommendations):
    active = {f"{plan.obligation.id}:{plan.obligation.revision}:" for plan in recommendations}
    state.sent = {
        key: value for key, value in state.sent.items() if any(key.startswith(p) for p in active)
    }
    ids = {plan.obligation.id for plan in recommendations}
    state.skipped = [item for item in state.skipped if item in ids]
    state.started = [item for item in state.started if item in ids]
