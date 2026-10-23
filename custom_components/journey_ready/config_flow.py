"""UI setup with explicit home/office coordinate confirmation."""

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN, NAME
from .http import HTTP
from .models import Place
from .providers.base import AuthError, ProviderError
from .providers.tomtom import TomTom


def notification_selector(hass):
    options = [
        f"notify.{name}"
        for name in hass.services.async_services().get("notify", {})
        if name.startswith("mobile_app_")
    ]
    return selector.SelectSelector({"options": options, "custom_value": True, "mode": "dropdown"})


class JourneyReadyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input:
            await self.async_set_unique_id(user_input["person"])
            self._abort_if_unique_id_configured()
            try:
                if not user_input["calendars"]:
                    raise ValueError("Select a calendar")
                domain, service = user_input["notify_service"].split(".", 1)
                if domain != "notify" or not self.hass.services.has_service(domain, service):
                    raise ValueError("Select an available phone notification service")
                client = TomTom(HTTP(async_get_clientsession(self.hass)), user_input["tomtom_key"])
                home = await client.geocode(user_input["home_postcode"])
                office = await client.geocode(user_input["office_address"])
                if not home or not office:
                    errors["base"] = "address_not_found"
                else:
                    self._pending = dict(user_input)
                    self._pending["response_user"] = self.context.get("user_id", "")
                    self._home, self._office = home[0], office[0]
                    return await self.async_step_confirm()
            except AuthError:
                errors["base"] = "invalid_auth"
            except ProviderError:
                errors["base"] = "cannot_connect"
            except (ValueError, KeyError):
                errors["base"] = "invalid_input"
        return self.async_show_form(
            step_id="user",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Required("name", default=NAME): str,
                    vol.Required("home_postcode"): str,
                    vol.Required("office_address"): str,
                    vol.Required("tomtom_key"): selector.TextSelector({"type": "password"}),
                    vol.Required("person"): selector.EntitySelector(
                        {"filter": {"domain": "person"}}
                    ),
                    vol.Required("calendars"): selector.EntitySelector(
                        {"filter": {"domain": "calendar"}, "multiple": True}
                    ),
                    vol.Required("notify_service"): notification_selector(self.hass),
                }
            ),
        )

    async def async_step_confirm(self, user_input=None):
        errors = {}
        if user_input:
            try:
                for key, name in (
                    ("home_location", "Home"),
                    ("office_location", self._pending["office_address"]),
                ):
                    point = Place(
                        name,
                        float(user_input[key]["latitude"]),
                        float(user_input[key]["longitude"]),
                    )
                    self._pending[key] = {
                        "latitude": point.latitude,
                        "longitude": point.longitude,
                        "name": name,
                    }
            except (ValueError, TypeError, KeyError):
                errors["base"] = "invalid_input"
            else:
                return self.async_create_entry(title=self._pending["name"], data=self._pending)
        return self.async_show_form(
            step_id="confirm",
            errors=errors,
            description_placeholders={"home": self._home.name, "office": self._office.name},
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "home_location",
                        default={
                            "latitude": self._home.latitude,
                            "longitude": self._home.longitude,
                        },
                    ): selector.LocationSelector(),
                    vol.Required(
                        "office_location",
                        default={
                            "latitude": self._office.latitude,
                            "longitude": self._office.longitude,
                        },
                    ): selector.LocationSelector(),
                }
            ),
        )

    async def async_step_reauth(self, entry_data):
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        errors = {}
        entry = self._get_reauth_entry()
        if user_input:
            try:
                client = TomTom(HTTP(async_get_clientsession(self.hass)), user_input["tomtom_key"])
                await client.geocode(entry.data["home_postcode"])
            except AuthError:
                errors["base"] = "invalid_auth"
            except ProviderError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(entry, data_updates=user_input)
        return self.async_show_form(
            step_id="reauth_confirm",
            errors=errors,
            data_schema=vol.Schema(
                {vol.Required("tomtom_key"): selector.TextSelector({"type": "password"})}
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        from .options import JourneyOptionsFlow

        return JourneyOptionsFlow()
