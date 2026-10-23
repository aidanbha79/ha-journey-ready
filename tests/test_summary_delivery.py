from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

pytest.importorskip("homeassistant")
from custom_components.journey_ready.coordinator import JourneyCoordinator
from custom_components.journey_ready.models import (
    Candidate,
    Obligation,
    Recommendation,
    RuntimeState,
)


@pytest.mark.asyncio
async def test_quiet_hours_defer_voice_without_repeating_phone_summary():
    now = datetime(2026, 10, 23, 6, tzinfo=UTC)
    trip = Obligation(
        "a", "r", "work", "Office", now + timedelta(hours=3), now + timedelta(hours=10)
    )
    plan = Recommendation(trip, Candidate("park_ride", now + timedelta(hours=2), trip.arrival_by))
    phone, voice = [], []

    async def send(text, **kwargs):
        phone.append(text)

    async def speak(text):
        voice.append(text)
        return len(voice) > 1

    coordinator = SimpleNamespace(
        settings={"morning_time": "06:00"},
        calendar_ok=True,
        state=RuntimeState(),
        plans=[plan],
        next_plan=plan,
        status=[],
        notifier=SimpleNamespace(send=send),
        _speak=speak,
    )
    await JourneyCoordinator._summary(coordinator, now)
    await JourneyCoordinator._summary(coordinator, now + timedelta(minutes=1))
    assert len(phone) == 1
    assert len(voice) == 2
    assert coordinator.state.overrides["morning_voice:2026-10-23"] is True
