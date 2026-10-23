"""Small options screens, with native selectors rather than JSON blobs."""

import re
from copy import deepcopy
from datetime import time

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector

from .const import DEFAULTS
from .models import Place

TEXT = selector.TextSelector()
TIME = selector.TimeSelector()
BOOL = selector.BooleanSelector()
LOCATION = selector.LocationSelector()
PASSWORD = selector.TextSelector({"type": "password"})


def number(minimum=0, maximum=1000, step=1):
    return selector.NumberSelector({"min": minimum, "max": maximum, "step": step, "mode": "box"})


def entity(domain):
    return selector.EntitySelector({"filter": {"domain": domain}})


class JourneyOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        self.values = {
            **DEFAULTS,
            **self.config_entry.data,
            **deepcopy(dict(self.config_entry.options)),
        }
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "general",
                "sources",
                "add_site",
                "remove_site",
                "stations",
                "fuel_weather",
                "alexa",
                "destination",
                "remove_destination",
                "connections",
            ],
        )

    def finish(self, updates):
        options = dict(self.config_entry.options)
        options.update(updates)
        return self.async_create_entry(title="", data=options)

    async def form(self, step, user_input, fields, required=()):
        errors = {}
        if user_input is not None:
            try:
                for key, field in fields.items():
                    if field is LOCATION and key in user_input:
                        point = user_input[key]
                        Place("Location", float(point["latitude"]), float(point["longitude"]))
                for key in ("departures", "rail_departures"):
                    if key in user_input:
                        for value in user_input[key].split(","):
                            if value.strip():
                                time.fromisoformat(value.strip())
                if "origin_crs" in user_input:
                    for key in ("origin_crs", "destination_crs"):
                        if not re.fullmatch("[A-Za-z]{3}", user_input[key]):
                            raise ValueError
                        user_input[key] = user_input[key].upper()
                return self.finish(user_input)
            except (ValueError, TypeError):
                errors["base"] = "invalid_input"
        schema = {}
        for key, field in fields.items():
            marker = vol.Required if key in required or key in DEFAULTS else vol.Optional
            default = self.values.get(key, vol.UNDEFINED)
            if field is LOCATION and isinstance(default, dict):
                default = {
                    k: v for k, v in default.items() if k in ("latitude", "longitude", "radius")
                }
            schema[marker(key, default=default)] = field
        return self.async_show_form(step_id=step, data_schema=vol.Schema(schema), errors=errors)

    async def async_step_general(self, user_input=None):
        return await self.form(
            "general",
            user_input,
            {
                "arrival_time": TIME,
                "work_end": TIME,
                "morning_time": TIME,
                "evening_time": TIME,
                "office_match": TEXT,
                "exclude_keywords": TEXT,
                "safety_minutes": number(0, 120),
                "parking_minutes": number(0, 60),
                "boarding_minutes": number(0, 60),
                "road_delay_minutes": number(0, 120),
                "change_minutes": number(1, 60),
                "fallback_minutes": number(1, 120),
                "car_available": BOOL,
                "car_required_default": BOOL,
                "quiet_start": TIME,
                "quiet_end": TIME,
                "appointment_parking": number(0, 120),
                "appointment_walk": number(0, 120),
            },
        )

    async def async_step_sources(self, user_input=None):
        if user_input is not None:
            data = dict(self.config_entry.data)
            for key, value in user_input.items():
                if key in ("road_daily_budget", "transport_daily_budget", "fuel_daily_budget"):
                    continue
                if value:
                    data[key] = value
            self.hass.config_entries.async_update_entry(self.config_entry, data=data)
            return self.finish(
                {
                    key: int(value)
                    for key, value in user_input.items()
                    if key in ("road_daily_budget", "transport_daily_budget", "fuel_daily_budget")
                }
            )
        # Credentials are never prefilled into the returned form.
        return self.async_show_form(
            step_id="sources",
            data_schema=vol.Schema(
                {
                    vol.Optional("tomtom_key"): PASSWORD,
                    vol.Optional("rail_username"): TEXT,
                    vol.Optional("rail_password"): PASSWORD,
                    vol.Optional("transport_app_id"): TEXT,
                    vol.Optional("transport_app_key"): PASSWORD,
                    vol.Optional("fuel_client_id"): TEXT,
                    vol.Optional("fuel_client_secret"): PASSWORD,
                    vol.Required(
                        "fuel_auth_format", default=self.values["fuel_auth_format"]
                    ): selector.SelectSelector({"options": ["form", "json"]}),
                    vol.Required(
                        "fuel_daily_budget", default=self.values["fuel_daily_budget"]
                    ): number(1, 100000),
                    vol.Required(
                        "road_daily_budget", default=self.values["road_daily_budget"]
                    ): number(1, 100000),
                    vol.Required(
                        "transport_daily_budget", default=self.values["transport_daily_budget"]
                    ): number(1, 100000),
                }
            ),
        )

    async def async_step_add_site(self, user_input=None):
        errors = {}
        if user_input:
            try:
                if not user_input.get("stop_id") and not (
                    user_input.get("timetable_confirmed")
                    and user_input.get("departures", "").strip()
                ):
                    raise ValueError
                for value in user_input.get("departures", "").split(","):
                    if value.strip():
                        time.fromisoformat(value.strip())
                site = {**user_input.pop("site_location"), **user_input}
                site["days"] = [int(value) for value in site["days"]]
                sites = list(self.values.get("park_ride_sites", []))
                sites = [existing for existing in sites if existing["name"] != site["name"]]
                sites.append(site)
                return self.finish({"park_ride_sites": sites})
            except (ValueError, KeyError):
                errors["base"] = "invalid_input"
        return self.async_show_form(
            step_id="add_site",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Required("name"): TEXT,
                    vol.Required("site_location"): LOCATION,
                    vol.Required("line"): TEXT,
                    vol.Optional("stop_id"): TEXT,
                    vol.Optional("departures", default=""): TEXT,
                    vol.Required("bus_minutes"): number(1, 180),
                    vol.Required("office_walk"): number(0, 120),
                    vol.Required("return_walk"): number(0, 120),
                    vol.Required("last_return"): TIME,
                    vol.Required("closes"): TIME,
                    vol.Required(
                        "days", default=["0", "1", "2", "3", "4"]
                    ): selector.SelectSelector(
                        {
                            "options": [
                                {"value": str(i), "label": label}
                                for i, label in enumerate(
                                    [
                                        "Monday",
                                        "Tuesday",
                                        "Wednesday",
                                        "Thursday",
                                        "Friday",
                                        "Saturday",
                                        "Sunday",
                                    ]
                                )
                            ],
                            "multiple": True,
                        }
                    ),
                    vol.Required("timetable_confirmed", default=False): BOOL,
                }
            ),
        )

    async def async_step_remove_site(self, user_input=None):
        if user_input:
            return self.finish(
                {
                    "park_ride_sites": [
                        s
                        for s in self.values.get("park_ride_sites", [])
                        if s["name"] != user_input["name"]
                    ]
                }
            )
        return self.async_show_form(
            step_id="remove_site",
            data_schema=vol.Schema(
                {
                    vol.Required("name"): selector.SelectSelector(
                        {"options": [s["name"] for s in self.values.get("park_ride_sites", [])]}
                    )
                }
            ),
        )

    async def async_step_stations(self, user_input=None):
        if user_input:
            for key in ("origin_station", "destination_station"):
                if key in user_input:
                    user_input[key]["name"] = user_input.get(
                        "origin_crs" if key == "origin_station" else "destination_crs", "Station"
                    )
        return await self.form(
            "stations",
            user_input,
            {
                "rail_enabled": BOOL,
                "origin_crs": TEXT,
                "destination_crs": TEXT,
                "origin_station": LOCATION,
                "destination_station": LOCATION,
                "rail_timetable_confirmed": BOOL,
                "rail_departures": TEXT,
                "rail_minutes": number(1, 360),
                "rail_last_return": TIME,
                "max_station_walk": number(1, 120),
            },
            required=(
                "origin_crs",
                "destination_crs",
                "origin_station",
                "destination_station",
                "rail_last_return",
            ),
        )

    async def async_step_fuel_weather(self, user_input=None):
        return await self.form(
            "fuel_weather",
            user_input,
            {
                "mpg": number(1, 200, 0.1),
                "gallon": selector.SelectSelector({"options": ["UK", "US"]}),
                "diesel_price": number(0, 10, 0.001),
                "fuel_sensor": entity("sensor"),
                "fuel_enabled": BOOL,
                "fuel_radius_km": number(1, 100, 0.5),
                "fuel_station_id": TEXT,
                "fuel_price_unit": selector.SelectSelector(
                    {"options": ["auto", "pence", "pounds"]}
                ),
                "park_ride_fare": number(0, 100, 0.01),
                "park_ride_pass": BOOL,
                "rail_fare": number(0, 1000, 0.01),
                "rail_pass": BOOL,
                "rain_probability": number(0, 100),
                "rain_fraction": number(1, 100),
                "rain_coverage": number(1, 100),
            },
        )

    async def async_step_alexa(self, user_input=None):
        return await self.form(
            "alexa",
            user_input,
            {
                "alexa_enabled": BOOL,
                "alexa_notify": entity("notify"),
                "alexa_speaker": entity("media_player"),
                "alexa_question_script": entity("script"),
            },
        )

    async def async_step_destination(self, user_input=None):
        if user_input:
            destinations = dict(self.values.get("destinations", {}))
            destinations[user_input["calendar_location"]] = {
                **user_input["location"],
                "name": user_input["calendar_location"],
            }
            return self.finish({"destinations": destinations})
        return self.async_show_form(
            step_id="destination",
            data_schema=vol.Schema(
                {vol.Required("calendar_location"): TEXT, vol.Required("location"): LOCATION}
            ),
        )

    async def async_step_remove_destination(self, user_input=None):
        if user_input:
            destinations = dict(self.values.get("destinations", {}))
            destinations.pop(user_input["calendar_location"], None)
            return self.finish({"destinations": destinations})
        return self.async_show_form(
            step_id="remove_destination",
            data_schema=vol.Schema(
                {
                    vol.Required("calendar_location"): selector.SelectSelector(
                        {"options": list(self.values.get("destinations", {}))}
                    )
                }
            ),
        )

    async def async_step_connections(self, user_input=None):
        return await self.form(
            "connections",
            user_input,
            {
                "person": entity("person"),
                "notify_service": TEXT,
                "phone_device": selector.DeviceSelector({"filter": {"integration": "mobile_app"}}),
                "calendars": selector.EntitySelector(
                    {"filter": {"domain": "calendar"}, "multiple": True}
                ),
                "home_location": LOCATION,
                "office_location": LOCATION,
                "location_max_age": number(1, 120),
                "location_max_accuracy": number(1, 1000),
            },
            required=("person", "notify_service", "calendars", "home_location", "office_location"),
        )
