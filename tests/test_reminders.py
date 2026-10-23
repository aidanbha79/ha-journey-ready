from datetime import UTC, datetime, timedelta

from custom_components.journey_ready.models import (
    Candidate,
    Obligation,
    Recommendation,
    RuntimeState,
)
from custom_components.journey_ready.scheduler import due_reminders, mark_sent, prune_state

LEAVE = datetime(2026, 10, 23, 10, tzinfo=UTC)
TRIP = Obligation(
    "a", "r", "appointment", "Dentist", LEAVE + timedelta(hours=1), LEAVE + timedelta(hours=2)
)


def plan(leave=LEAVE, trip=TRIP):
    return Recommendation(trip, Candidate("car", leave, LEAVE + timedelta(hours=1)))


def test_hour_and_quarter_hour_reminders():
    state = RuntimeState()
    assert [r.stage for r in due_reminders(state, [plan()], LEAVE - timedelta(hours=1))] == ["hour"]
    reminder = due_reminders(state, [plan()], LEAVE - timedelta(hours=1))[0]
    mark_sent(state, reminder)
    assert due_reminders(state, [plan()], LEAVE - timedelta(minutes=30)) == []
    assert [r.stage for r in due_reminders(state, [plan()], LEAVE - timedelta(minutes=15))] == [
        "leave"
    ]


def test_restart_preserves_sent_reminders():
    state = RuntimeState()
    reminder = due_reminders(state, [plan()], LEAVE - timedelta(hours=1))[0]
    mark_sent(state, reminder)
    restored = RuntimeState(sent=dict(state.sent))
    assert due_reminders(restored, [plan()], LEAVE - timedelta(hours=1)) == []


def test_new_appointment_inside_window_does_not_send_two_messages():
    assert [
        r.stage for r in due_reminders(RuntimeState(), [plan()], LEAVE - timedelta(minutes=5))
    ] == ["leave"]


def test_departure_moved_earlier_sends_change_once():
    state = RuntimeState()
    mark_sent(state, due_reminders(state, [plan()], LEAVE - timedelta(hours=1))[0])
    reminders = due_reminders(
        state, [plan(LEAVE - timedelta(minutes=10))], LEAVE - timedelta(minutes=30)
    )
    assert [r.stage for r in reminders] == ["changed"]
    mark_sent(state, reminders[0])
    assert (
        due_reminders(state, [plan(LEAVE - timedelta(minutes=10))], LEAVE - timedelta(minutes=30))
        == []
    )


def test_removed_or_changed_event_prunes_sent_keys():
    state = RuntimeState()
    mark_sent(state, due_reminders(state, [plan()], LEAVE - timedelta(hours=1))[0])
    prune_state(state, [])
    assert not state.sent


def test_started_journey_does_not_repeat_departure():
    state = RuntimeState(started=["a"])
    assert due_reminders(state, [plan()], LEAVE - timedelta(minutes=5)) == []


def test_late_plan_warns_immediately():
    assert [
        r.stage for r in due_reminders(RuntimeState(), [plan()], LEAVE + timedelta(minutes=1))
    ] == ["late"]
