import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

pytest.importorskip("homeassistant")
from custom_components.journey_ready.coordinator import JourneyCoordinator
from custom_components.journey_ready.models import (
    Candidate,
    Obligation,
    Recommendation,
    RuntimeState,
)
from custom_components.journey_ready.questions import create_question


@pytest.mark.asyncio
async def test_removed_second_plan_is_not_delivered_after_first_await():
    now = datetime(2026, 10, 23, 8, tzinfo=UTC)
    plans = [
        Recommendation(
            Obligation(
                key, "r", "appointment", key, now + timedelta(hours=2), now + timedelta(hours=3)
            ),
            Candidate("car", now + timedelta(hours=1), now + timedelta(hours=2)),
        )
        for key in ("a", "b")
    ]
    sent = []

    async def deliver(plan, stage):
        sent.append(plan.obligation.id)
        coordinator.plans = [plans[0]]

    coordinator = SimpleNamespace(
        now=lambda: now,
        next_plan=None,
        delivery_lock=asyncio.Lock(),
        calendar_ok=True,
        plans=plans,
        settings={"change_minutes": 5},
        state=RuntimeState(),
        status=[],
        _summary=AsyncMock(),
        notifier=SimpleNamespace(plan=deliver),
        save=AsyncMock(),
        _speak=AsyncMock(),
        _questions=AsyncMock(),
        async_set_updated_data=lambda _: None,
    )
    await JourneyCoordinator._tick(coordinator, now)
    assert sent == ["a"]


@pytest.mark.asyncio
async def test_calendar_invalidation_during_first_send_stops_second():
    now = datetime(2026, 10, 23, 8, tzinfo=UTC)
    plans = [
        Recommendation(
            Obligation(
                key, "r", "appointment", key, now + timedelta(hours=2), now + timedelta(hours=3)
            ),
            Candidate("car", now + timedelta(hours=1), now + timedelta(hours=2)),
        )
        for key in ("a", "b")
    ]
    sent = []

    async def deliver(plan, stage):
        sent.append(plan.obligation.id)
        coordinator.calendar_ok = False

    coordinator = SimpleNamespace(
        now=lambda: now,
        next_plan=None,
        delivery_lock=asyncio.Lock(),
        calendar_ok=True,
        plans=plans,
        settings={"change_minutes": 5},
        state=RuntimeState(),
        status=[],
        _summary=AsyncMock(),
        notifier=SimpleNamespace(plan=deliver),
        save=AsyncMock(),
        _speak=AsyncMock(),
        _questions=AsyncMock(),
        async_set_updated_data=lambda _: None,
    )
    await JourneyCoordinator._tick(coordinator, now)
    assert sent == ["a"]
    coordinator._questions.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "responder,configured,accepted",
    [
        ("unrelated", "backend", False),
        (None, "backend", False),
        ("backend", "", False),
        ("backend", "backend", True),
    ],
)
async def test_voice_response_requires_commissioned_backend(responder, configured, accepted):
    now = datetime(2026, 10, 23, 8, tzinfo=UTC)
    q = create_question("entry", "owner", "2026-10-24", now)
    q["alexa_sent"] = True
    tasks = []
    coordinator = SimpleNamespace(
        state=RuntimeState(questions={"2026-10-24": q}),
        settings={"alexa_response_user": configured},
        alexa=SimpleNamespace(allowed=lambda: True),
        hass=SimpleNamespace(
            async_create_task=lambda coro: tasks.append(asyncio.create_task(coro))
        ),
        _accept=AsyncMock(),
    )
    event = SimpleNamespace(
        data={"event_id": "JR_" + q["token"], "event_response_type": "ResponseNo"},
        context=SimpleNamespace(user_id=responder),
    )
    JourneyCoordinator._voice_response(coordinator, event)
    if tasks:
        await asyncio.gather(*tasks)
    assert bool(coordinator._accept.await_count) is accepted
    if accepted:
        assert coordinator._accept.call_args.args[2] == "backend"
