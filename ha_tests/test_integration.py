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
    assert hass.states.get(staff[0].entity_id) is None

async def test_config_flow_validation(hass, fake_api):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] == FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {**DATA, **OPTIONS})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert result["result"].state == ConfigEntryState.LOADED

async def test_config_flow_rejects_invalid_key(hass):
    with patch("custom_components.rotacloud_attendance.api.Client._request", new_callable=AsyncMock, side_effect=ApiError(401)) as mock:
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {**DATA, **OPTIONS})
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
