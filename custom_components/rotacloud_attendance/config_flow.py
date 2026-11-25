"""UI configuration; no attendance mutations during setup."""
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import selector
from .api import ApiError, Client
from .const import (DOMAIN, CONF_TERMINAL, CONF_POLL, CONF_LATE, CONF_LEAVING,
                    DEFAULT_POLL, DEFAULT_LATE, DEFAULT_LEAVING)
from .roster import RosterClient

def settings(values):
    return {
        vol.Required(CONF_POLL, default=values.get(CONF_POLL, DEFAULT_POLL)): vol.All(vol.Coerce(int), vol.Range(min=120, max=3600)),
        vol.Required(CONF_LATE, default=values.get(CONF_LATE, DEFAULT_LATE)): vol.All(vol.Coerce(int), vol.Range(min=0, max=60)),
        vol.Required(CONF_LEAVING, default=values.get(CONF_LEAVING, DEFAULT_LEAVING)): vol.All(vol.Coerce(int), vol.Range(min=0, max=120)),
    }

class RotaCloudConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if self._async_current_entries():
            return self.async_abort(reason="already_configured")
        errors = {}
        if user_input is not None:
            client = Client(async_get_clientsession(self.hass), user_input["api_key"].strip(), user_input[CONF_TERMINAL])
            try:
                await RosterClient(client).employees()
                await client.clocked_in()
            except ApiError as exc:
                errors["base"] = "invalid_auth" if exc.status in (401, 403) else "cannot_connect"
            except (ValueError, TypeError):
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(DOMAIN)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title="RotaCloud Attendance", data={
                    "api_key": user_input["api_key"].strip(), CONF_TERMINAL: user_input[CONF_TERMINAL]},
                    options={k: user_input[k] for k in (CONF_POLL, CONF_LATE, CONF_LEAVING)})
        return self.async_show_form(step_id="user", errors=errors, data_schema=vol.Schema({
            vol.Required("api_key"): selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)),
            vol.Required(CONF_TERMINAL): vol.All(vol.Coerce(int), vol.Range(min=1)),
            **settings({})}))

    @staticmethod
    def async_get_options_flow(config_entry):
        return AttendanceOptionsFlow()

class AttendanceOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(step_id="init", data_schema=vol.Schema(settings(self.config_entry.options)))
