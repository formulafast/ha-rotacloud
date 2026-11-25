"""RotaCloud Attendance: read-only development integration."""
from .const import DOMAIN

async def async_setup_entry(hass, entry):
    from homeassistant.const import Platform
    from homeassistant.helpers.aiohttp_client import async_get_clientsession
    from .api import Client
    from .const import CONF_TERMINAL
    from .coordinator import AttendanceCoordinator

    client = Client(async_get_clientsession(hass), entry.data["api_key"], entry.data[CONF_TERMINAL])
    coordinator = AttendanceCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_reload))
    entry.async_on_unload(coordinator.listen_for_refresh())
    await hass.config_entries.async_forward_entry_setups(entry, [Platform.SENSOR])
    return True

async def _reload(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass, entry):
    from homeassistant.const import Platform
    return await hass.config_entries.async_unload_platforms(entry, [Platform.SENSOR])
