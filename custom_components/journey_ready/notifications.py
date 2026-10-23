"""Message formatting and Home Assistant notification delivery."""

from datetime import time
from urllib.parse import urlencode


def waze_url(place):
    return "https://waze.com/ul?" + urlencode(
        {
            "ll": f"{place.latitude},{place.longitude}",
            "navigate": "yes",
            "utm_source": "journey_ready",
        }
    )


def can_speak(presence, clock, quiet_start="22:00", quiet_end="07:00"):
    if presence != "home":
        return False
    value, start, end = (
        time.fromisoformat(clock),
        time.fromisoformat(quiet_start),
        time.fromisoformat(quiet_end),
    )
    if start == end:
        return True
    quiet = start <= value < end if start < end else value >= start or value < end
    return not quiet


def message(plan, stage="morning"):
    candidate = plan.selected
    if not candidate:
        return (
            f"No confirmed journey to {plan.obligation.destination or plan.obligation.title}. "
            + "; ".join(plan.reasons + plan.warnings)
        )
    mode = {
        "park_ride": "Drive to Park & Ride",
        "train": "Walk to the station for your train",
        "car": "Drive",
    }.get(candidate.mode, candidate.mode)
    lead = {
        "hour": "One hour until departure. ",
        "leave": "Prepare to leave in 15 minutes. ",
        "late": "Your calculated departure time has passed. ",
        "changed": "Your departure time has moved earlier. ",
    }.get(stage, "")
    text = f"{lead}{mode}. Leave by {candidate.leave_at:%H:%M}; expected arrival {candidate.arrive_at:%H:%M}. {candidate.detail}."
    if candidate.cost is not None:
        text += f" Estimated return fuel/tickets: £{candidate.cost:.2f}."
    text += " " + "; ".join(plan.reasons)
    kinds = sorted({item.kind for item in candidate.evidence if item.kind not in ("live",)})
    if kinds:
        text += ". Includes " + ", ".join(kinds) + " estimates."
    if plan.warnings:
        text += " " + "; ".join(plan.warnings)
    return text


class Notifier:
    def __init__(self, hass, entry_id, service):
        self.hass, self.entry_id, self.service = hass, entry_id, service

    async def send(self, text, *, actions=None, tag="plan"):
        domain, service = self.service.split(".", 1)
        await self.hass.services.async_call(
            domain,
            service,
            {
                "title": "Journey Ready",
                "message": text,
                "data": {"tag": f"journey_ready_{self.entry_id}_{tag}", "actions": actions or []},
            },
            blocking=True,
        )

    async def plan(self, plan, stage):
        actions = []
        if plan.selected and plan.selected.drive_destination:
            actions.append(
                {
                    "action": "URI",
                    "title": "Open Waze",
                    "uri": waze_url(plan.selected.drive_destination),
                }
            )
        await self.send(message(plan, stage), actions=actions, tag=plan.obligation.id)
        from homeassistant.components import persistent_notification

        persistent_notification.async_create(
            self.hass,
            message(plan, stage),
            title="Journey Ready",
            notification_id=f"journey_ready_{self.entry_id}",
        )

    async def question(self, question):
        token = question["token"]
        await self.send(
            f"Do you need your car after work on {question['date']}?",
            actions=[
                {"action": f"JR_{token}_yes", "title": "Yes"},
                {"action": f"JR_{token}_no", "title": "No"},
            ],
            tag="car_question",
        )
