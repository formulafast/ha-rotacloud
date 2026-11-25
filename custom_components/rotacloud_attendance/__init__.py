"""RotaCloud Attendance with opt-in administrator terminal."""
from .const import DOMAIN

async def async_setup_entry(hass, entry):
    from homeassistant.const import Platform
    from homeassistant.helpers.aiohttp_client import async_get_clientsession
    from .api import Client
    from .const import CONF_TERMINAL, CONF_ACTIVATE_TERMINAL
    from .coordinator import AttendanceCoordinator
    from .websocket import async_register
    from homeassistant.components.http import StaticPathConfig
    from pathlib import Path

    client = Client(async_get_clientsession(hass), entry.data["api_key"], entry.options.get(CONF_TERMINAL, entry.data[CONF_TERMINAL]),
                    activate_terminal=entry.options.get(CONF_ACTIVATE_TERMINAL, False), device_id="home-assistant-" + entry.entry_id)
    coordinator = AttendanceCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    async_register(hass)
    static_key = DOMAIN + "_static_registered"
    if not hass.data.get(static_key):
        await hass.http.async_register_static_paths([StaticPathConfig(
            "/rotacloud_attendance/static", str(Path(__file__).parent / "frontend"), True)])
        hass.data[static_key] = True
    entry.async_on_unload(entry.add_update_listener(_reload))
    entry.async_on_unload(coordinator.listen_for_refresh())
    entry.async_on_unload(coordinator.listen_for_time())
    await hass.config_entries.async_forward_entry_setups(entry, [Platform.SENSOR])
    return True

async def _reload(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass, entry):
    from homeassistant.const import Platform
    unloaded = await hass.config_entries.async_unload_platforms(entry, [Platform.SENSOR])
    if unloaded:
        entry.runtime_data.terminal.sessions.clear()
    return unloaded
