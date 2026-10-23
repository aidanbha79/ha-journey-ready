"""Versioned state via Home Assistant's supported Store API."""

from dataclasses import asdict

from .models import RuntimeState


class JourneyStore:
    def __init__(self, hass, entry_id):
        from homeassistant.helpers.storage import Store

        self.store = Store(hass, 1, f"journey_ready.{entry_id}")

    async def load(self):
        data = await self.store.async_load()
        if not isinstance(data, dict):
            return RuntimeState()
        values = {
            key: data[key]
            for key in ("sent", "questions", "overrides", "skipped", "started")
            if key in data
        }
        # Corrupted optional state must not stop the integration loading.
        for key in ("sent", "questions", "overrides"):
            if key in values and not isinstance(values[key], dict):
                values[key] = {}
        for key in ("skipped", "started"):
            if key in values and not isinstance(values[key], list):
                values[key] = []
        return RuntimeState(**values)

    async def save(self, state):
        await self.store.async_save(asdict(state))
