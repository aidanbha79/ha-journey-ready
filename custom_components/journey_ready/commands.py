"""User-invoked controls scoped to an entry and obligation."""

import voluptuous as vol
from homeassistant.exceptions import ServiceValidationError

from .const import DOMAIN
from .questions import create_question
from .vehicle import remember_departure


async def register(hass):
    async def handle(call):
        entries = hass.data.get(DOMAIN, {})
        entry_id = call.data.get("entry_id")
        if entry_id:
            coordinator = entries.get(entry_id)
        else:
            coordinator = next(iter(entries.values())) if len(entries) == 1 else None
        if not coordinator:
            raise ServiceValidationError("Choose a Journey Ready config entry")
        if call.service == "refresh":
            await coordinator.refresh()
            return
        if call.service == "test_notification":
            await coordinator.notifier.send(
                "Journey Ready test notification. No real departure is due.", tag="test"
            )
            await coordinator._speak("Journey Ready test announcement. No real departure is due.")
            return
        if call.service == "set_car_required":
            day = call.data["work_date"]
            from datetime import date

            date.fromisoformat(day)
            question = coordinator.state.questions.get(day) or create_question(
                coordinator.entry.entry_id, coordinator._expected_user(), day, coordinator.now()
            )
            question["answer"] = call.data["required"]
            question["manual"] = True
            coordinator.state.questions[day] = question
        else:
            plan = next(
                (p for p in coordinator.plans if p.obligation.id == call.data.get("obligation_id")),
                coordinator.next_plan if not call.data.get("obligation_id") else None,
            )
            if not plan:
                raise ServiceValidationError("No matching upcoming journey")
            if call.service == "skip_journey":
                coordinator.state.skipped.append(plan.obligation.id)
            elif call.service == "mark_started":
                coordinator.state.started.append(plan.obligation.id)
                remember_departure(coordinator.state, plan)
            elif call.service == "override_mode":
                coordinator.state.overrides[plan.obligation.id] = call.data["mode"]
        await coordinator.save()
        await coordinator.refresh()

    common = {vol.Optional("entry_id"): str}
    for name in ("refresh", "test_notification", "skip_journey", "mark_started"):
        schema = vol.Schema({**common, vol.Optional("obligation_id"): str})
        hass.services.async_register(DOMAIN, name, handle, schema=schema)
    hass.services.async_register(
        DOMAIN,
        "override_mode",
        handle,
        schema=vol.Schema(
            {
                **common,
                vol.Optional("obligation_id"): str,
                vol.Required("mode"): vol.In(["auto", "car", "park_ride", "train"]),
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        "set_car_required",
        handle,
        schema=vol.Schema(
            {**common, vol.Required("work_date"): str, vol.Required("required"): bool}
        ),
    )


def unregister(hass):
    for name in (
        "refresh",
        "test_notification",
        "skip_journey",
        "mark_started",
        "override_mode",
        "set_car_required",
    ):
        hass.services.async_remove(DOMAIN, name)
