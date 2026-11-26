"""Administrator-authenticated HA transport for the attendance terminal.

No clocking HTTP endpoints, device tokens, HA services or employee IDs in write messages.
PINs travel only in the authenticated WebSocket request and are never published.
"""
import secrets

import probatio as vol
from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import callback

from .const import CONF_CLOCKING, DOMAIN
from .terminal import TerminalError


def _positive_id(value):
    if type(value) is not int or value <= 0:
        raise vol.Invalid("Expected a positive integer")
    return value


def _coordinator(hass, entry_id):
    entry = hass.config_entries.async_get_entry(entry_id)
    if (entry is None or entry.domain != DOMAIN
            or entry.state != ConfigEntryState.LOADED):
        raise TerminalError("RotaCloud integration is not loaded.")
    return entry.runtime_data


def _terminal(hass, entry_id):
    coordinator = _coordinator(hass, entry_id)
    entry = coordinator.entry
    if not entry.options.get(CONF_CLOCKING, False):
        raise TerminalError("Enable HA terminal clocking in the integration options first.")
    return entry.runtime_data


@websocket_api.websocket_command({
    vol.Required("type"): DOMAIN + "/refresh",
    vol.Required("entry_id"): str,
})
@websocket_api.require_admin
@websocket_api.async_response
async def refresh(hass, connection, msg):
    try:
        result = await _coordinator(hass, msg["entry_id"]).async_manual_refresh()
    except TerminalError as exc:
        connection.send_error(msg["id"], "refresh_error", str(exc))
    else:
        connection.send_result(msg["id"], result)


class _ConnectionSession:
    def __init__(self, connection, terminal):
        self.identity = connection.user.id + ":" + secrets.token_urlsafe(32)
        self.terminal = terminal
        self.closed = False

    def __call__(self):
        self.closed = True
        self.terminal.sessions = {k: v for k, v in self.terminal.sessions.items()
                                  if v.device != self.identity}


def _device(coordinator, connection):
    # HA invokes subscription cleanup on disconnect. Use its supported storage;
    # ActiveConnection is slotted and cannot accept arbitrary attributes.
    key = DOMAIN + "/terminal/" + coordinator.entry.entry_id
    binding = connection.subscriptions.get(key)
    if binding is None or binding.terminal is not coordinator.terminal:
        if binding is not None:
            binding()
        binding = _ConnectionSession(connection, coordinator.terminal)
        connection.subscriptions[key] = binding
    return binding


@websocket_api.websocket_command({
    vol.Required("type"): DOMAIN + "/terminal/identify",
    vol.Required("entry_id"): str,
    # HA redacts password/token keys in protocol errors and debug logs.
    vol.Required("password"): vol.All(str, vol.Match(r"^[0-9]{1,12}$")),
})
@websocket_api.require_admin
@websocket_api.async_response
async def identify(hass, connection, msg):
    pin = msg.pop("password")
    try:
        coordinator = _terminal(hass, msg["entry_id"])
        binding = _device(coordinator, connection)
        await coordinator.async_prepare_terminal()
        if binding.closed:
            return
        result = await coordinator.terminal.identify(binding.identity, pin)
        if binding.closed:
            binding()
            return
    except TerminalError as exc:
        connection.send_error(msg["id"], "terminal_error", str(exc))
    else:
        result["token"] = result.pop("session")
        connection.send_result(msg["id"], result)
    finally:
        pin = None


@websocket_api.websocket_command({
    vol.Required("type"): DOMAIN + "/terminal/act",
    vol.Required("entry_id"): str,
    vol.Required("token"): vol.All(str, vol.Length(min=40, max=100)),
    vol.Required("action"): vol.In(("clock_in", "clock_out", "start_break", "end_break")),
    vol.Optional("shift_id"): _positive_id,
})
@websocket_api.require_admin
@websocket_api.async_response
async def act(hass, connection, msg):
    try:
        coordinator = _terminal(hass, msg["entry_id"])
        result = await coordinator.terminal.act(
            _device(coordinator, connection).identity, msg["token"], msg["action"], msg.get("shift_id"))
    except TerminalError as exc:
        connection.send_error(msg["id"], "terminal_error", str(exc))
    else:
        connection.send_result(msg["id"], result)


@callback
def async_register(hass):
    key = DOMAIN + "_websocket_registered"
    if hass.data.get(key):
        return
    websocket_api.async_register_command(hass, identify)
    websocket_api.async_register_command(hass, act)
    websocket_api.async_register_command(hass, refresh)
    hass.data[key] = True
