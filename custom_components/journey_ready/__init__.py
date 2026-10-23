"""Journey Ready integration. Domain helpers stay importable without HA."""

from .const import DOMAIN


async def async_setup_entry(hass, entry):
    from homeassistant.const import Platform

    from .commands import register
    from .coordinator import JourneyCoordinator

    coordinator = JourneyCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}
        await register(hass)
    hass.data[DOMAIN][entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, [Platform.SENSOR, Platform.BUTTON])
    coordinator.start()
    entry.async_on_unload(entry.add_update_listener(_reload))
    return True


async def async_unload_entry(hass, entry):
    from homeassistant.const import Platform

    from .commands import unregister

    if not await hass.config_entries.async_unload_platforms(
        entry, [Platform.SENSOR, Platform.BUTTON]
    ):
        return False
    entry.runtime_data.stop()
    await entry.runtime_data.store.save(entry.runtime_data.state)
    hass.data[DOMAIN].pop(entry.entry_id, None)
    if not hass.data[DOMAIN]:
        unregister(hass)
        hass.data.pop(DOMAIN)
    return True


async def _reload(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)
