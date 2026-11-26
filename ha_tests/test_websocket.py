"""Exercise the real HA WebSocket boundary with fictional attendance only."""
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant.common import MockConfigEntry

from custom_components.rotacloud_attendance.api import ApiError
from custom_components.rotacloud_attendance.const import CONF_CLOCKING, DOMAIN


@pytest.fixture
def api():
    now = int(datetime.now(timezone.utc).timestamp())
    state = {"now": now, "active": [], "completed": [], "calls": []}

    async def request(method, path, *, body=None, params=None):
        state["calls"].append((method, path, body))
        if path in ("/leave", "/availability"):
            return state.get(path[1:], []), {}
        if path == "/terminals/1":
            return {"id": 1, "active": state.get("terminal_active", True)}, {}
        if path == "/terminals_active":
            assert body["terminal"] == 1
            assert body["device"].startswith("home-assistant-")
            state["terminal_active"] = True
            return {"id": 1, "active": True}, {}
        if path == "/users":
            return state.get("users", [{"id": 1, "first_name": "Alex", "last_name": "Example"}]), {}
        if path == "/shifts":
            return [{"id": 7, "user": 1, "start_time": now-600, "end_time": now+3600}], {}
        if path == "/attendance":
            return state["completed"], {}
        if path == "/pins/1234":
            return {"id": 1, "first_name": "Alex", "email": "never-return@example.invalid"}, {}
        if path.startswith("/pins/"):
            raise ApiError(404)
        if method == "GET" and path == "/users_clocked_in":
            return state["active"], {}
        if method == "POST" and path == "/users_clocked_in":
            assert body == {"method": "terminal", "terminal": 1, "user": 1, "shift": 7}
            state["active"] = [{"user": 1, "in_time": now, "shift": 7}]
            return state["active"][0], {}
        if method == "POST" and path == "/users_clocked_in/1":
            start = now+10
            result = {"start_time": start}
            if body["action"] == "end_break":
                result["end_time"] = now+70
            state["active"][0]["breaks_clocked"] = [result]
            return result, {}
        if method == "DELETE" and path == "/users_clocked_in/1":
            record = {**state["active"][0], "out_time": now+3600}
            state["completed"].append(record)
            state["active"] = []
            return record, {}
        raise AssertionError((method, path))

    with patch("custom_components.rotacloud_attendance.api.Client._request", new=AsyncMock(side_effect=request)) as mock:
        state["mock"] = mock
        yield state


async def setup(hass, enabled=True, **options):
    entry = MockConfigEntry(domain=DOMAIN, data={"api_key": "fictional", "terminal_id": 1},
                            options={"poll_seconds": 86400, CONF_CLOCKING: enabled, **options}, unique_id=DOMAIN)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def send(client, entry, command, **data):
    await client.send_json_auto_id({"type": DOMAIN+"/terminal/"+command,
                                    "entry_id": entry.entry_id, **data})
    return await client.receive_json()


async def test_full_clocking_flow_and_duplicate_prevention(hass, hass_ws_client, api):
    entry = await setup(hass)
    client = await hass_ws_client(hass)
    for action in ("clock_in", "start_break", "end_break", "clock_out"):
        identified = await send(client, entry, "identify", password="1234")
        assert identified["success"], identified
        person = identified["result"]
        assert "never-return" not in str(person)
        assert "1234" not in str(person)
        assert action in person["actions"]
        data = {"token": person["token"], "action": action}
        if action == "clock_in":
            data["shift_id"] = 7
        result = await send(client, entry, "act", **data)
        assert result["success"], result
        assert result["result"]["action"] == action
        await hass.async_block_till_done()
        repeated = await send(client, entry, "act", **data)
        assert not repeated["success"]
        if action != "clock_out":
            assert result["result"]["scheduled_end"] == api["now"]+3600
    assert len([c for c in api["calls"] if c[0] != "GET"]) == 4
    assert entry.runtime_data.data[1].status == "gone"
    assert result["result"]["shift_seconds"] == 3600
    assert result["result"]["break_seconds"] == 60


async def test_disabled_and_nonadmin_rejected_before_api(hass, hass_ws_client, hass_read_only_access_token, api):
    entry = await setup(hass, enabled=False)
    admin = await hass_ws_client(hass)
    api["calls"].clear()
    result = await send(admin, entry, "identify", password="1234")
    assert not result["success"]
    assert "Enable" in result["error"]["message"]
    reader = await hass_ws_client(hass, access_token=hass_read_only_access_token)
    for command, data in (("identify", {"password": "1234"}),
                           ("act", {"token": "a"*43, "action": "clock_out"})):
        result = await send(reader, entry, command, **data)
        assert result["error"]["code"] == "unauthorized"
    assert not api["calls"]


async def test_connection_bound_tokens_and_disconnect_cleanup(hass, hass_ws_client, api):
    entry = await setup(hass)
    first, other = await hass_ws_client(hass), await hass_ws_client(hass)
    result = await send(first, entry, "identify", password="1234")
    token = result["result"]["token"]
    wrong = await send(other, entry, "act", token=token, action="clock_in", shift_id=7)
    assert not wrong["success"]
    assert token in entry.runtime_data.terminal.sessions
    await first.close()
    await hass.async_block_till_done()
    assert token not in entry.runtime_data.terminal.sessions
    assert not [c for c in api["calls"] if c[0] != "GET"]


async def test_invalid_fields_and_pin_logs_are_redacted(hass, hass_ws_client, api, caplog):
    entry = await setup(hass)
    client = await hass_ws_client(hass)
    api["calls"].clear()
    for command, data in (("identify", {"password": "fictional-sensitive-value"}),
                           ("identify", {"password": "1234", "user_id": 99}),
                           ("act", {"token": "a"*43, "action": "clock_in", "shift_id": True})):
        result = await send(client, entry, command, **data)
        assert result["error"]["code"] == "invalid_format"
    assert not api["calls"]
    assert "fictional-sensitive-value" not in caplog.text
    assert "1234" not in caplog.text


async def test_unload_rejects_old_sessions(hass, hass_ws_client, api):
    entry = await setup(hass)
    client = await hass_ws_client(hass)
    result = await send(client, entry, "identify", password="1234")
    terminal = entry.runtime_data.terminal
    assert await hass.config_entries.async_unload(entry.entry_id)
    result = await send(client, entry, "act", token=result["result"]["token"], action="clock_in", shift_id=7)
    assert not result["success"]
    assert not terminal.sessions
    assert not [c for c in api["calls"] if c[0] != "GET"]


async def test_uncertain_write_never_retried(hass, hass_ws_client, api):
    entry = await setup(hass)
    client = await hass_ws_client(hass)
    person = (await send(client, entry, "identify", password="1234"))["result"]
    with patch.object(entry.runtime_data.client, "clock_in", new=AsyncMock(side_effect=ApiError(None, uncertain=True))) as mutation:
        data = {"token": person["token"], "action": "clock_in", "shift_id": 7}
        result = await send(client, entry, "act", **data)
        assert "Outcome unknown" in result["error"]["message"]
        await hass.async_block_till_done()
        await send(client, entry, "act", **data)
        mutation.assert_awaited_once()


async def test_poll_waits_for_terminal_transaction(hass, hass_ws_client, api):
    entry = await setup(hass)
    client = await hass_ws_client(hass)
    person = (await send(client, entry, "identify", password="1234"))["result"]
    started, release = asyncio.Event(), asyncio.Event()
    original = entry.runtime_data.client.clock_in

    async def delayed(*args):
        started.set()
        await release.wait()
        return await original(*args)

    with patch.object(entry.runtime_data.client, "clock_in", side_effect=delayed):
        await client.send_json_auto_id({"type": DOMAIN+"/terminal/act", "entry_id": entry.entry_id,
                                        "token": person["token"], "action": "clock_in", "shift_id": 7})
        await started.wait()
        count = len(api["calls"])
        poll = hass.async_create_task(entry.runtime_data.async_refresh())
        await asyncio.sleep(0)
        assert len(api["calls"]) == count
        release.set()
        result = await client.receive_json()
        assert result["success"]
        await poll
        await hass.async_block_till_done()
    assert entry.runtime_data.data[1].status in ("here", "leaving")


async def test_eligibility_revoked_during_prewrite_read(hass, hass_ws_client, api):
    entry = await setup(hass)
    client = await hass_ws_client(hass)
    person = (await send(client, entry, "identify", password="1234"))["result"]
    coordinator = entry.runtime_data

    async def revoke():
        coordinator.employees.clear()
        return []

    with patch.object(coordinator.client, "clocked_in", side_effect=revoke):
        result = await send(client, entry, "act", token=person["token"], action="clock_in", shift_id=7)
    assert not result["success"]
    assert not [c for c in api["calls"] if c[0] != "GET"]


async def test_packaged_card_served_and_reload_is_idempotent(hass, hass_ws_client, api):
    entry = await setup(hass)
    client = await hass_ws_client(hass)
    response = await client.client.get("/rotacloud_attendance/static/staff-terminal.js?v=0.4.0")
    assert response.status == 200
    source = await response.text()
    assert "class FFStaffTerminal" in source
    assert "fictional" not in source
    assert await hass.config_entries.async_reload(entry.entry_id)
    result = await send(client, entry, "identify", password="1234")
    assert result["success"]


async def test_inactive_terminal_launch_is_opt_in_and_precedes_clocking(hass, hass_ws_client, api):
    api["terminal_active"] = False
    entry = await setup(hass, activate_terminal=True)
    client = await hass_ws_client(hass)
    person = (await send(client, entry, "identify", password="1234"))["result"]
    result = await send(client, entry, "act", token=person["token"], action="clock_in", shift_id=7)
    assert result["success"], result
    writes = [c for c in api["calls"] if c[0] != "GET"]
    assert [c[1] for c in writes] == ["/terminals_active", "/users_clocked_in"]


async def test_inactive_terminal_never_launches_without_option(hass, hass_ws_client, api):
    api["terminal_active"] = False
    entry = await setup(hass)
    client = await hass_ws_client(hass)
    person = (await send(client, entry, "identify", password="1234"))["result"]
    result = await send(client, entry, "act", token=person["token"], action="clock_in", shift_id=7)
    assert "inactive" in result["error"]["message"]
    assert not [c for c in api["calls"] if c[0] != "GET"]


async def test_terminal_breaks_include_prior_clockings_today_without_double_count(hass, hass_ws_client, api):
    entry = await setup(hass)
    from custom_components.rotacloud_attendance.model import Attendance, Break
    now = api["now"]
    entry.runtime_data.completed = (
        Attendance(1, now-500, now-300, (Break(now-490, now-430),)),
        Attendance(1, now-250, now-50, (Break(now-240, now-120),)),
    )
    client = await hass_ws_client(hass)
    person = (await send(client, entry, "identify", password="1234"))["result"]
    assert person["break_seconds_today"] == 180
    result = await send(client, entry, "act", token=person["token"], action="clock_in", shift_id=7)
    assert result["success"]
    assert result["result"]["break_seconds_today"] == 180


async def test_options_store_terminal_and_timing_colours(hass, api):
    entry = await setup(hass)
    form = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(form["flow_id"], {
        "terminal_id": 99, "poll_seconds": "86400", "late_minutes": 0, "leaving_minutes": 15,
        "enable_clocking": True, "activate_terminal": True,
        "clock_in_late_minutes": 5, "clock_in_late_color": [200, 30, 50],
        "clock_out_early_minutes": 3, "clock_out_early_color": [250, 210, 20],
    })
    await hass.async_block_till_done()
    assert entry.options["terminal_id"] == 99
    assert entry.runtime_data.client._terminal == 99
    from custom_components.rotacloud_attendance.const import timing_options
    assert timing_options(entry.options)["clock_in_late"] == {"minutes": 5, "color": [200, 30, 50]}
    present = next(s for s in hass.states.async_all("sensor") if s.attributes.get("rotacloud_status") == "present")
    assert present.attributes["display_options"]["clock_out_early"]["minutes"] == 3


async def test_uncertain_activation_never_sends_attendance(hass, hass_ws_client, api):
    entry = await setup(hass, activate_terminal=True)
    client = await hass_ws_client(hass)
    person = (await send(client, entry, "identify", password="1234"))["result"]
    with patch.object(entry.runtime_data.client, "prepare_terminal", side_effect=ApiError(None, uncertain=True)):
        result = await send(client, entry, "act", token=person["token"], action="clock_in", shift_id=7)
    assert "No attendance action was sent" in result["error"]["message"]
    assert not [c for c in api["calls"] if c[0] != "GET"]


async def test_planning_is_cached_and_dob_is_not_published(hass, api):
    from zoneinfo import ZoneInfo
    day = datetime.now(ZoneInfo(hass.config.time_zone)).date().isoformat()
    api["users"] = [{"id":1,"first_name":"Alex","last_name":"Example","dob":"2000-02-03"}]
    api["leave"] = [{"user":1,"status":"approved","dates":[{"date":day,"days":1}]}]
    api["availability"] = [{"user":1,"dates":[{"date":day,"available":[{"start_time":"09:00","end_time":"13:00"},{"start_time":"17:00","end_time":"19:00"}]}]}]
    entry = await setup(hass)
    assert len(api["calls"]) == 6
    assert entry.runtime_data.windows, (day, hass.config.time_zone, api["leave"], entry.runtime_data.windows)
    assert entry.runtime_data.employees[1].age_band == "adult"
    counts = {s.attributes.get("rotacloud_status"):s for s in hass.states.async_all("sensor") if s.attributes.get("rotacloud_kind")=="count"}
    assert counts["on_leave"].state == "1"
    assert counts["available"].state == "1"
    assert counts["available"].attributes["rows"][0]["times"] == ["09:00 – 13:00","17:00 – 19:00"]
    assert "2000-02-03" not in str(hass.states.async_all("sensor"))
    api["calls"].clear()
    await entry.runtime_data.async_refresh()
    assert [c[1] for c in api["calls"]] == ["/users_clocked_in"]


async def test_manual_refresh_coalesces_and_is_throttled(hass, api):
    entry = await setup(hass)
    coordinator = entry.runtime_data
    original = coordinator.roster.planning
    started, release = asyncio.Event(), asyncio.Event()
    async def gated(day):
        started.set()
        await release.wait()
        return await original(day)
    api["calls"].clear()
    with patch.object(coordinator.roster,"planning",side_effect=gated):
        one=hass.async_create_task(coordinator.async_manual_refresh())
        await started.wait()
        two=hass.async_create_task(coordinator.async_manual_refresh())
        await asyncio.sleep(0)
        release.set()
        results=await asyncio.gather(one,two)
    assert results[0] == results[1]
    assert len(api["calls"]) == 6
    from custom_components.rotacloud_attendance.terminal import TerminalError
    with pytest.raises(TerminalError,match="Please wait"):
        await coordinator.async_manual_refresh()
    assert len(api["calls"]) == 6


async def test_refresh_websocket_admin_only_even_when_clocking_disabled(hass, hass_ws_client, hass_read_only_access_token, api):
    entry=await setup(hass,enabled=False)
    reader=await hass_ws_client(hass,access_token=hass_read_only_access_token)
    api["calls"].clear()
    await reader.send_json_auto_id({"type":DOMAIN+"/refresh","entry_id":entry.entry_id})
    result=await reader.receive_json()
    assert result["error"]["code"]=="unauthorized"
    assert not api["calls"]
    admin=await hass_ws_client(hass)
    await admin.send_json_auto_id({"type":DOMAIN+"/refresh","entry_id":entry.entry_id})
    result=await admin.receive_json()
    assert result["success"]
    assert len(api["calls"])==6


async def test_local_tick_does_not_poll_and_previous_day_is_not_in_main_counts(hass, api, freezer):
    from datetime import timedelta
    from pytest_homeassistant.common import async_fire_time_changed
    freezer.move_to("2026-11-26T12:00:00+00:00")
    api["active"]=[{"user":1,"in_time":int(datetime.now(timezone.utc).timestamp())-86400}]
    entry=await setup(hass)
    state=next(s for s in hass.states.async_all("sensor") if s.attributes.get("rotacloud_status")=="present")
    assert state.state=="0"
    staff=next(s for s in hass.states.async_all("sensor") if s.attributes.get("rotacloud_kind")=="staff")
    assert staff.attributes["previous_day"] is True
    api["calls"].clear()
    async_fire_time_changed(hass,datetime.now(timezone.utc)+timedelta(minutes=1))
    await hass.async_block_till_done()
    assert not api["calls"]


async def test_planning_permission_failure_does_not_hide_attendance(hass, api):
    api["active"]=[{"user":1,"in_time":api["now"]-60}]
    original=api["mock"].side_effect
    async def request(method,path,**kwargs):
        if path=="/leave":
            raise ApiError(403)
        return await original(method,path,**kwargs)
    api["mock"].side_effect=request
    entry=await setup(hass)
    assert entry.runtime_data.last_update_success
    assert not entry.runtime_data.planning_available
    assert entry.runtime_data.data[1].status in ("here","leaving")
