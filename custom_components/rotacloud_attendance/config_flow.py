"""UI configuration; no attendance mutations during setup."""
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import selector
from .api import ApiError, Client
from .const import (DOMAIN, CONF_TERMINAL, CONF_POLL, CONF_LATE, CONF_LEAVING, CONF_CLOCKING, CONF_ACTIVATE_TERMINAL,
                    DEFAULT_POLL, DEFAULT_LATE, DEFAULT_LEAVING, TIMING_KINDS, timing_options)

POLL_CHOICES = {
    "0": "Event-only (requires working webhook relay)",
    "1800": "30 minutes",
    "3600": "1 hour",
    "7200": "2 hours",
    "14400": "4 hours",
    "21600": "6 hours",
    "43200": "12 hours",
    "86400": "24 hours (minimum API usage)"
}

def settings(values):
    current = str(values.get(CONF_POLL, DEFAULT_POLL))
    choices = dict(POLL_CHOICES)
    if current not in choices and current.isdigit() and 1800 <= int(current) <= 86400:
        choices[current] = f"Current setting ({current} seconds)"
    if current not in choices:
        current = str(DEFAULT_POLL)
    result = {
        vol.Required(CONF_POLL, default=current): selector.SelectSelector(selector.SelectSelectorConfig(
            options=[{"value": value, "label": label} for value, label in choices.items()],
            mode=selector.SelectSelectorMode.DROPDOWN)),
        vol.Required(CONF_LATE, default=values.get(CONF_LATE, DEFAULT_LATE)): number_box(60),
        vol.Required(CONF_LEAVING, default=values.get(CONF_LEAVING, DEFAULT_LEAVING)): number_box(120),
        vol.Optional(CONF_CLOCKING, default=values.get(CONF_CLOCKING, False)): bool,
        vol.Optional(CONF_ACTIVATE_TERMINAL, default=values.get(CONF_ACTIVATE_TERMINAL, False)): bool,
    }
    for kind, defaults in timing_options(values).items():
        result[vol.Optional(kind + "_minutes", default=defaults["minutes"])] = number_box(120)
        result[vol.Optional(kind + "_color", default=defaults["color"])] = selector.ColorRGBSelector()
    for band in ("under18", "adult"):
        for field, maximum in (("minimum_minutes",240),("qualifying_hours",48),("qualifying_minutes",59),("warning_hours",48),("warning_minutes",59)):
            key = "break_" + band + "_" + field
            result[vol.Optional(key, default=values.get(key,0))] = number_box(maximum)
    return result

def number_box(maximum):
    return selector.NumberSelector(selector.NumberSelectorConfig(min=0,max=maximum,step=1,mode=selector.NumberSelectorMode.BOX))

def normalise(values):
    return {key: int(value) if key in (CONF_POLL,CONF_LATE,CONF_LEAVING,CONF_TERMINAL)
            or key.endswith(("_minutes","_hours")) else value for key,value in values.items()}

class RotaCloudConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if self._async_current_entries():
            return self.async_abort(reason="already_configured")
        errors = {}
        if user_input is not None:
            user_input = normalise(user_input)
            try:
                client = Client(async_get_clientsession(self.hass), user_input["api_key"].strip(), user_input[CONF_TERMINAL])
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
                    options={CONF_POLL: int(user_input[CONF_POLL]), CONF_LATE: user_input[CONF_LATE],
                             CONF_LEAVING: user_input[CONF_LEAVING],
                             CONF_CLOCKING: user_input.get(CONF_CLOCKING, False),
                             CONF_ACTIVATE_TERMINAL: user_input.get(CONF_ACTIVATE_TERMINAL, False),
                             **{k: v for k, v in user_input.items() if k.startswith("break_") or any(k.startswith(kind + "_") for kind in TIMING_KINDS)}})
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
            return self.async_create_entry(title="", data=normalise(user_input))
        return self.async_show_form(step_id="init", data_schema=vol.Schema({
            vol.Optional(CONF_TERMINAL, default=self.config_entry.options.get(CONF_TERMINAL, self.config_entry.data[CONF_TERMINAL])):
                vol.All(vol.Coerce(int), vol.Range(min=1)),
            **settings(self.config_entry.options)}))
