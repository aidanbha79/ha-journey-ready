"""Explicit refresh and test controls."""

from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.entity import DeviceInfo, EntityCategory

from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(
        JourneyButton(entry.runtime_data, key) for key in ("refresh", "test_notification")
    )


class JourneyButton(ButtonEntity):
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, key):
        self.coordinator, self.key = coordinator, key
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{key}"
        self._attr_name = key.replace("_", " ").capitalize()
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, coordinator.entry.entry_id)})

    async def async_press(self):
        await self.hass.services.async_call(
            DOMAIN, self.key, {"entry_id": self.coordinator.entry.entry_id}, blocking=True
        )
