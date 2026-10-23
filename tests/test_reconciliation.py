from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from test_http import Response, Session

from custom_components.journey_ready.http import HTTP
from custom_components.journey_ready.models import (
    Candidate,
    Obligation,
    Recommendation,
    RuntimeState,
)
from custom_components.journey_ready.notifications import daily_summary
from custom_components.journey_ready.providers.base import RateLimitError
from custom_components.journey_ready.questions import create_question, prune_questions, revision_for
from custom_components.journey_ready.scheduler import due_reminders, mark_sent

NOW = datetime(2026, 10, 23, 8, tzinfo=UTC)
TRIP = Obligation("a", "r", "work", "Office", NOW + timedelta(hours=2), NOW + timedelta(hours=10))
PLAN = Recommendation(TRIP, Candidate("park_ride", NOW + timedelta(hours=1), TRIP.arrival_by))


def test_route_loss_after_a_reminder_is_reported_once():
    state = RuntimeState()
    mark_sent(state, due_reminders(state, [PLAN], NOW)[0])
    unavailable = replace(PLAN, selected=None)
    updates = due_reminders(state, [unavailable], NOW + timedelta(minutes=1))
    assert [item.stage for item in updates] == ["unavailable"]
    mark_sent(state, updates[0])
    assert due_reminders(state, [unavailable], NOW + timedelta(minutes=2)) == []
    assert [item.stage for item in due_reminders(state, [PLAN], NOW + timedelta(minutes=3))] == [
        "recovered"
    ]


def test_changed_calendar_invalidates_old_pending_answer():
    state = RuntimeState()
    day = TRIP.arrival_by.date().isoformat()
    question = create_question("e", "u", day, NOW)
    question["revision"] = revision_for([TRIP], day)
    state.questions[day] = question
    prune_questions(state, [replace(TRIP, revision="changed")], NOW)
    assert not state.questions


def test_unchanged_calendar_retains_answer():
    state = RuntimeState()
    day = TRIP.arrival_by.date().isoformat()
    question = create_question("e", "u", day, NOW)
    question.update(answer=False, revision=revision_for([TRIP], day))
    state.questions[day] = question
    prune_questions(state, [TRIP], NOW)
    assert state.questions[day]["answer"] is False


@pytest.mark.parametrize("change", ["add", "delete", "revise"])
def test_after_work_calendar_changes_invalidate_car_answer(change):
    appointment = replace(
        TRIP,
        id="dentist",
        revision="one",
        kind="appointment",
        arrival_by=TRIP.end_at + timedelta(hours=1),
    )
    before = [TRIP] if change == "add" else [TRIP, appointment]
    after = [TRIP] if change == "delete" else [TRIP, replace(appointment, revision="two")]
    day = TRIP.arrival_by.date().isoformat()
    q = create_question("e", "u", day, NOW)
    q.update(answer=False, revision=revision_for(before, day))
    state = RuntimeState(questions={day: q})
    prune_questions(state, after, NOW)
    assert state.questions == {}


def test_summary_includes_today_and_provisional_tomorrow():
    second = replace(
        TRIP, id="b", destination="Dentist", kind="appointment", arrival_by=NOW + timedelta(hours=5)
    )
    tomorrow = replace(
        TRIP, id="c", destination="Tomorrow office", arrival_by=NOW + timedelta(days=1, hours=2)
    )
    text = daily_summary(
        [PLAN, Recommendation(second, None), Recommendation(tomorrow, None)], NOW.date()
    )
    assert "Office" in text and "Dentist" in text
    assert "Tomorrow (provisional)" in text


@pytest.mark.asyncio
async def test_http_budget_survives_reload():
    http = HTTP(Session(Response()), budget=1, clock=lambda: NOW)
    await http.get("https://example.test")
    restored = HTTP(Session(Response()), budget=1, clock=lambda: NOW)
    restored.restore_usage(http.export_usage())
    with pytest.raises(RateLimitError):
        await restored.get("https://other.test")
