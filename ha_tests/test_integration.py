"""Isolated HA tests. All external requests are mocked."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant.common import MockConfigEntry
from custom_components.rotacloud_attendance.api import ApiError
from custom_components.rotacloud_attendance.const import DOMAIN

DATA = {"api_key": "fictional-test-key", "terminal_id": 1}
OPTIONS = {"poll_seconds": 86400, "late_minutes": 0, "leaving_minutes": 15}

@pytest.fixture
def fake_api():
    now = int(datetime.now(timezone.utc).timestamp())
    responses = {
        "/users": [{"id": 1, "first_name": "Example", "last_name": "Employee"}],
        "/shifts": [{"id": 1, "user": 1, "start_time": now - 600, "end_time": now + 3600, "published": True}],
        "/users_clocked_in": [{"user": 1, "in_time": now - 600, "shift": 1}],
        "/attendance": [],
    }
    async def request(method, path, **kwargs):
        assert method == "GET", "Read-only pilot must never write attendance"
        return responses[path], {}
    with patch("custom_components.rotacloud_attendance.api.Client._request", new_callable=AsyncMock) as mock:
        mock.side_effect = request
        yield mock

async def test_setup_entities_refresh_and_unload(hass, fake_api):
    entry = MockConfigEntry(domain=DOMAIN, title="RotaCloud Attendance", data=DATA, options=OPTIONS, unique_id=DOMAIN)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state == ConfigEntryState.LOADED
    states = hass.states.async_all("sensor")
    counts = {s.attributes.get("rotacloud_status"): s for s in states if s.attributes.get("rotacloud_kind") == "count"}
    assert counts["present"].state == "1"
    assert counts["here"].state == "1"
    assert isinstance(counts["present"].attributes["last_api_refresh"], int)
    staff = [s for s in states if s.attributes.get("rotacloud_kind") == "staff"]
    assert len(staff) == 1
    assert staff[0].attributes["staff_name"] == "Example Employee"
    assert staff[0].state == "here"
    assert fake_api.await_count == 4
    fake_api.reset_mock()
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert fake_api.await_count == 1
    assert fake_api.call_args.args == ("GET", "/users_clocked_in")
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state == ConfigEntryState.NOT_LOADED
    # HA preserves registry-backed entities as unavailable placeholders on unload.
    for state in [*counts.values(), *staff]:
        restored = hass.states.get(state.entity_id)
        assert restored is None or (restored.state == "unavailable" and restored.attributes.get("restored") is True)
        if restored is not None:
            assert "rotacloud_kind" not in restored.attributes
            assert "clock_in" not in restored.attributes
    # An unloaded integration must not respond to attendance refresh events.
    fake_api.reset_mock()
    hass.bus.async_fire("rotacloud_attendance_refresh", {"kind": "clock_in"})
    await hass.async_block_till_done()
    fake_api.assert_not_awaited()

async def test_config_flow_validation(hass, fake_api):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] == FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {**DATA, **OPTIONS, "poll_seconds": "86400"})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert result["result"].state == ConfigEntryState.LOADED
    assert result["result"].options["poll_seconds"] == 86400
    assert result["result"].runtime_data.update_interval.total_seconds() == 86400

async def test_config_flow_rejects_invalid_key(hass):
    with patch("custom_components.rotacloud_attendance.api.Client._request", new_callable=AsyncMock, side_effect=ApiError(401)) as mock:
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {**DATA, **OPTIONS, "poll_seconds": "86400"})
        assert result["type"] == FlowResultType.FORM
        assert result["errors"]["base"] == "invalid_auth"
        mock.assert_awaited_once()

async def test_failed_poll_marks_entities_unavailable(hass, fake_api):
    entry = MockConfigEntry(domain=DOMAIN, data=DATA, options=OPTIONS, unique_id=DOMAIN)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    present = next(s for s in hass.states.async_all("sensor") if s.attributes.get("rotacloud_status") == "present")
    fake_api.side_effect = ApiError(429)
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(present.entity_id).state == "unavailable"

async def test_poll_selector_serializes_for_frontend(hass):
    from homeassistant.helpers import selector
    from homeassistant.helpers import config_validation as cv
    from probatio import to_field_list
    from custom_components.rotacloud_attendance.config_flow import settings
    import voluptuous as vol
    schema = vol.Schema(settings({}))
    serialized = to_field_list(schema, custom_serializer=cv.custom_serializer)
    assert isinstance(serialized, list)
    poll = next(field for field in serialized if field["name"] == "poll_seconds")
    assert poll["default"] == "86400"
    assert poll["selector"]["select"]["mode"] == "dropdown"
    choices = {item["value"] for item in poll["selector"]["select"]["options"]}
    assert {"86400", "1800", "0"} <= choices
    assert schema({"poll_seconds": "0", "late_minutes": 0, "leaving_minutes": 15})["poll_seconds"] == "0"
    with pytest.raises(vol.Invalid):
        schema({"poll_seconds": "60", "late_minutes": 0, "leaving_minutes": 15})

async def test_options_flow_stores_integer_poll(hass, fake_api):
    entry = MockConfigEntry(domain=DOMAIN, data=DATA, options=OPTIONS, unique_id=DOMAIN)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(result["flow_id"], {**OPTIONS, "poll_seconds": "21600"})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options["poll_seconds"] == 21600
