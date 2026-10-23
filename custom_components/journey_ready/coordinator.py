"""Home Assistant lifecycle, calendar reads and reminder scheduling."""

import asyncio
import logging
from datetime import UTC, time, timedelta
from zoneinfo import ZoneInfo

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import (
    async_track_point_in_utc_time,
    async_track_state_change_event,
    async_track_time_change,
    async_track_time_interval,
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .alexa import Alexa
from .calendar import normalise_events
from .const import DEFAULTS, DOMAIN
from .engine import Engine, place_from
from .http import HTTP
from .location import resolve_origin
from .notifications import Notifier, daily_summary, message
from .providers.bus import Bus
from .providers.fuel import sensor_price
from .providers.rail import Rail
from .providers.tomtom import TomTom
from .providers.weather import Weather
from .questions import (
    answer_question,
    create_question,
    prune_questions,
    revision_for,
    should_ask_alexa,
)
from .scheduler import due_reminders, mark_sent, prune_state
from .storage import JourneyStore

_LOGGER = logging.getLogger(__name__)


class JourneyCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry):
        super().__init__(
            hass, _LOGGER, name=DOMAIN, config_entry=entry, update_interval=timedelta(minutes=5)
        )
        self.entry = entry
        self.settings = {**DEFAULTS, **entry.data, **entry.options}
        self.store = JourneyStore(hass, entry.entry_id)
        self.plans = []
        self.unsubscribers, self.timers = [], []
        self.last_refresh = None
        self.force = True
        self.calendar_ok = False
        self.status = []
        self.delivery_lock = asyncio.Lock()
        self.notifier = Notifier(hass, entry.entry_id, self.settings["notify_service"])
        self.alexa = Alexa(hass, self.settings)
        session = async_get_clientsession(hass)
        self.road_http = HTTP(session, int(self.settings["road_daily_budget"]))
        self.transit_http = HTTP(session, int(self.settings["transport_daily_budget"]))
        self.weather_http = HTTP(session, 100)
        self.road = TomTom(self.road_http, self.settings["tomtom_key"])
        rail = (
            Rail(self.transit_http, self.settings["rail_username"], self.settings["rail_password"])
            if self.settings.get("rail_username") and self.settings.get("rail_password")
            else None
        )
        bus = (
            Bus(
                self.transit_http,
                self.settings["transport_app_id"],
                self.settings["transport_app_key"],
            )
            if self.settings.get("transport_app_id") and self.settings.get("transport_app_key")
            else None
        )
        self.engine = Engine(
            self.settings, self.road, rail=rail, bus=bus, weather=Weather(self.weather_http)
        )

    def now(self):
        return dt_util.utcnow().astimezone(ZoneInfo(self.hass.config.time_zone))

    @property
    def next_plan(self):
        return next(
            (
                p
                for p in self.plans
                if p.obligation.arrival_by > self.now()
                and p.obligation.id not in self.state.skipped
            ),
            None,
        )

    async def _async_setup(self):
        self.state = await self.store.load()
        for name, client in (
            ("road", self.road_http),
            ("transit", self.transit_http),
            ("weather", self.weather_http),
        ):
            client.restore_usage(self.state.overrides.get("_quota", {}).get(name, {}))

    async def save(self):
        self.state.overrides["_quota"] = {
            name: client.export_usage()
            for name, client in (
                ("road", self.road_http),
                ("transit", self.transit_http),
                ("weather", self.weather_http),
            )
        }
        await self.store.save(self.state)

    async def _read_calendars(self):
        if not self.settings.get("calendars"):
            return []
        day = self.now().replace(hour=0, minute=0, second=0, microsecond=0)
        result = await self.hass.services.async_call(
            "calendar",
            "get_events",
            {
                "start_date_time": day.isoformat(),
                "end_date_time": (day + timedelta(days=2)).isoformat(),
            },
            target={"entity_id": self.settings["calendars"]},
            blocking=True,
            return_response=True,
        )
        events = []
        for calendar in (result or {}).values():
            events.extend(calendar.get("events", []))
        return normalise_events(events, self.settings, day.tzinfo)

    async def _async_update_data(self):
        now = self.now()
        upcoming = self.next_plan
        active = bool(
            upcoming
            and upcoming.selected
            and upcoming.selected.leave_at - now <= timedelta(minutes=90)
        )
        if not self.force and self.last_refresh and not active:
            if now - self.last_refresh < timedelta(minutes=15):
                return self.plans
        self.force = False
        self.status = []
        try:
            obligations = await self._read_calendars()
        except HomeAssistantError:
            self.calendar_ok = False
            self.status.append("Calendar unavailable; reminders suspended until it recovers")
            return self.plans
        self.calendar_ok = True
        self.last_refresh = now
        self.update_interval = timedelta(minutes=2 if active else 5)
        person = self.hass.states.get(self.settings["person"])
        tracker = None
        if person and person.attributes.get("source"):
            tracker = self.hass.states.get(person.attributes["source"])
        location = tracker or person
        origin = resolve_origin(
            person.state if person else "unknown",
            dict(location.attributes) if location else {},
            location.last_updated if location else None,
            place_from(self.settings["home_location"]),
            now,
            max_age=self.settings["location_max_age"],
            max_accuracy=self.settings["location_max_accuracy"],
        )
        price = None
        if fuel_entity := self.settings.get("fuel_sensor"):
            fuel = self.hass.states.get(fuel_entity)
            if fuel:
                price = sensor_price(
                    fuel.state, fuel.attributes.get("unit_of_measurement"), fuel.last_updated, now
                )
            if price is None:
                self.status.append(
                    "Fuel sensor unavailable or stale; using the configured manual price if set"
                )
        self.settings["effective_diesel"] = (
            price if price is not None else self.settings.get("diesel_price") or None
        )
        prune_questions(self.state, obligations, now)
        self.plans = await self.engine.plan(obligations, origin.place, now, self.state)
        self.state.overrides["_selected"] = {
            p.obligation.id: {"mode": p.selected.mode, "leave_at": p.selected.leave_at.isoformat()}
            for p in self.plans
            if p.selected
        }
        prune_state(self.state, self.plans)
        self._schedule_reminders()
        await self.save()
        return self.plans

    def start(self):
        for key in ("morning_time", "evening_time"):
            clock = time.fromisoformat(self.settings[key])
            self.unsubscribers.append(
                async_track_time_change(
                    self.hass, self._daily, hour=clock.hour, minute=clock.minute, second=0
                )
            )
        self.unsubscribers.append(
            async_track_time_interval(self.hass, self._tick, timedelta(minutes=1))
        )
        entities = list(self.settings["calendars"]) + [self.settings["person"]]
        self.unsubscribers.append(
            async_track_state_change_event(self.hass, entities, self._source_changed)
        )
        self.unsubscribers.append(
            self.hass.bus.async_listen("mobile_app_notification_action", self._phone_response)
        )
        self.unsubscribers.append(
            self.hass.bus.async_listen("alexa_actionable_notification", self._voice_response)
        )
        self._schedule_reminders()

    def stop(self):
        for unsubscribe in self.timers + self.unsubscribers:
            unsubscribe()
        self.timers.clear()
        self.unsubscribers.clear()

    def _schedule_reminders(self):
        for unsubscribe in self.timers:
            unsubscribe()
        self.timers.clear()
        now = self.now()
        for plan in self.plans:
            if not plan.selected or plan.obligation.id in self.state.skipped:
                continue
            for minutes in (60, 15, 0):
                when = plan.selected.leave_at - timedelta(minutes=minutes)
                if now < when < plan.obligation.arrival_by:
                    self.timers.append(
                        async_track_point_in_utc_time(self.hass, self._tick, when.astimezone(UTC))
                    )

    def _source_changed(self, event):
        old, new = event.data.get("old_state"), event.data.get("new_state")
        calendar = event.data["entity_id"] in self.settings["calendars"]
        plan = self.next_plan
        if (
            not calendar
            and old
            and new
            and old.state == "home"
            and new.state == "not_home"
            and plan
            and plan.selected
        ):
            if (
                plan.selected.leave_at - timedelta(minutes=30)
                <= self.now()
                <= plan.obligation.arrival_by
            ):
                self.state.started.append(plan.obligation.id)
        if calendar or not old or not new or old.state != new.state:
            self.hass.async_create_task(self.refresh())

    async def refresh(self):
        self.force = True
        await self.async_request_refresh()

    async def _daily(self, now):
        await self.refresh()
        await self._tick(now)

    async def _summary(self, now):
        key = f"morning:{now.date()}"
        if now.time() < time.fromisoformat(
            self.settings["morning_time"]
        ) or self.state.overrides.get(key):
            return
        if not self.plans:
            return
        try:
            await self.notifier.send(daily_summary(self.plans, now.date()), tag="summary")
        except HomeAssistantError:
            self.status.append("Morning summary could not be delivered")
            return
        self.state.overrides[key] = True
        if self.next_plan and self.next_plan.obligation.arrival_by.date() == now.date():
            await self._speak(message(self.next_plan))

    async def _tick(self, _now):
        now = self.now()
        plan = self.next_plan
        if plan and plan.selected and plan.selected.leave_at - now <= timedelta(minutes=90):
            if not self.last_refresh or now - self.last_refresh >= timedelta(minutes=2):
                await self.refresh()
        async with self.delivery_lock:
            if not self.calendar_ok:
                return
            await self._summary(now)
            for reminder in due_reminders(
                self.state, self.plans, now, self.settings["change_minutes"]
            ):
                try:
                    await self.notifier.plan(reminder.plan, reminder.stage)
                except HomeAssistantError:
                    self.status.append("Phone notification failed; will retry")
                    continue
                mark_sent(self.state, reminder)
                await self.save()
                if reminder.stage in ("leave", "late", "changed", "unavailable", "recovered"):
                    await self._speak(message(reminder.plan, reminder.stage))
            await self._questions(now)
            await self.save()
        self.async_set_updated_data(self.plans)

    async def _speak(self, text):
        try:
            return await self.alexa.announce(text)
        except HomeAssistantError:
            self.status.append("Alexa announcement unavailable; phone message retained")
            return False

    async def _questions(self, now):
        tomorrow = now.date() + timedelta(days=1)
        trips = [
            p.obligation
            for p in self.plans
            if p.obligation.kind == "work" and p.obligation.arrival_by.date() == tomorrow
        ]
        if trips and now.time() >= time.fromisoformat(self.settings["evening_time"]):
            day = tomorrow.isoformat()
            if day not in self.state.questions:
                self.state.questions[day] = create_question(
                    self.entry.entry_id,
                    self._expected_user(),
                    day,
                    now,
                    self.settings["fallback_minutes"],
                    expires_at=min(t.arrival_by for t in trips),
                )
                self.state.questions[day]["revision"] = revision_for(trips, day)
            question = self.state.questions[day]
            if not question["phone_sent"]:
                try:
                    await self.notifier.question(question)
                except HomeAssistantError:
                    self.status.append("Evening phone question could not be delivered")
                else:
                    question["phone_sent"] = True
                    await self.save()
        person = self.hass.states.get(self.settings["person"])
        for question in self.state.questions.values():
            if should_ask_alexa(question, now, person.state if person else "unknown"):
                try:
                    question["alexa_sent"] = await self.alexa.ask(question)
                except HomeAssistantError:
                    self.status.append(
                        "Alexa question unavailable; using your unanswered-question default"
                    )

    def _expected_user(self):
        person = self.hass.states.get(self.settings["person"])
        return (person.attributes.get("user_id") if person else None) or self.settings.get(
            "response_user", ""
        )

    def _phone_response(self, event):
        action = event.data.get("action", "")
        if not action.startswith("JR_"):
            return
        parts = action.split("_")
        if len(parts) != 3:
            return
        user = event.context.user_id
        expected = self._expected_user()
        if not expected or user != expected:
            return
        self.hass.async_create_task(self._accept(parts[1], parts[2], expected))

    def _voice_response(self, event):
        identity = event.data.get("event_id", "")
        if not identity.startswith("JR_"):
            return
        answer = {"ResponseYes": "yes", "ResponseNo": "no"}.get(
            event.data.get("event_response_type")
        )
        if not answer:
            return
        token = identity[3:]
        question = next(
            (
                q
                for q in self.state.questions.values()
                if q["token"] == token and q.get("alexa_sent")
            ),
            None,
        )
        if question and self.alexa.allowed():
            self.hass.async_create_task(self._accept(token, answer, question["user"]))

    async def _accept(self, token, answer, user):
        async with self.delivery_lock:
            changed = False
            for question in self.state.questions.values():
                changed = answer_question(question, token, answer, user, self.now()) or changed
            if changed:
                await self.save()
        if changed:
            await self.refresh()
