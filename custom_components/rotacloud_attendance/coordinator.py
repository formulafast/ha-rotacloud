"""Low-traffic coordinator shared by sensors and the opt-in HA terminal."""
import asyncio
from datetime import datetime, timedelta, timezone
import logging
import time
from zoneinfo import ZoneInfo
from homeassistant.core import callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .api import ApiError
from .const import (CONF_POLL, CONF_LATE, CONF_LEAVING, DEFAULT_POLL, DEFAULT_LATE,
                    DEFAULT_LEAVING, REFRESH_EVENT)
from .roster import RosterClient
from .snapshot import day_bounds, snapshot
from .terminal import Terminal, TerminalError

_LOGGER = logging.getLogger(__name__)
ROSTER_TTL = 6 * 3600
USERS_TTL = 24 * 3600
HISTORY_TTL = 6 * 3600
PLANNING_TTL = 6 * 3600

class AttendanceCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry, client):
        interval = entry.options.get(CONF_POLL, DEFAULT_POLL)
        super().__init__(hass, _LOGGER, config_entry=entry, name="RotaCloud Attendance",
                         update_interval=timedelta(seconds=max(1800, interval)) if interval else None,
                         always_update=True)
        self.client, self.entry = client, entry
        self.roster = RosterClient(client)
        self.employees, self.shifts, self.active, self.completed = {}, (), [], ()
        self.users_until = self.shifts_until = self.history_until = 0.0
        self.day = None
        self.dirty_history = True
        self.dirty_rota = True
        self.dirty_users = True
        self.inflight = False
        self.last_api_refresh = None
        self.windows = ()
        self.planning_available = False
        self.planning_until = 0.0
        self.dirty_planning = True
        self._manual_task = None
        self._last_manual = float("-inf")
        self.io_lock = asyncio.Lock()
        self.terminal = Terminal(client, self._eligible, self._shifts_for, self._terminal_changed,
                                 scheduled_end_for=self._scheduled_end, daily_breaks_for=self._daily_breaks)
        # Polls and terminal read/check/write sequences must not race each other.
        self.terminal.lock = self.io_lock

    def _eligible(self, device, uid):
        from homeassistant.config_entries import ConfigEntryState
        from .const import CONF_CLOCKING
        return (self.entry.options.get(CONF_CLOCKING, False)
                and self.entry.state == ConfigEntryState.LOADED and not self.dirty_users
                and self.last_update_success and uid in self.employees
                and time.monotonic() < self.users_until)

    def _scheduled_end(self, active):
        return next((s.end for s in self.shifts if s.id == active.shift_id
                     and s.user == active.user_id), active.scheduled_end)

    def _daily_breaks(self, uid, active, now):
        _, today, tomorrow = self._bounds(datetime.fromtimestamp(now, timezone.utc))
        records = [a for a in self.completed if a.user_id == uid
                   and (active is None or a.clock_in != active.clock_in)]
        if active is not None:
            records.append(active)
        return sum(max(0, min(b.end if b.end is not None else now, tomorrow) - max(b.start, today))
                   for a in records for b in a.breaks)

    def _shifts_for(self, device, uid, now):
        if time.monotonic() >= self.shifts_until or self.dirty_rota:
            raise TerminalError("Schedule changed. Enter your PIN again.")
        _, today, tomorrow = self._bounds(datetime.fromtimestamp(now, timezone.utc))
        if self.day != today:
            raise TerminalError("Schedule changed. Enter your PIN again.")
        used = {a.shift_id for a in self.completed if a.user_id == uid}
        return tuple(sorted((s for s in self.shifts if s.user == uid and s.id not in used
                            and s.start < tomorrow and s.end > now), key=lambda s: (s.start, s.id)))

    async def async_prepare_terminal(self):
        # Refresh expired directory/rota only; never poll on each keypad digit.
        now = datetime.now(timezone.utc)
        _, today, _ = self._bounds(now)
        if (not self.last_update_success or self.day != today or self.dirty_users
                or self.dirty_rota or self.dirty_history
                or time.monotonic() >= min(self.users_until, self.shifts_until)):
            await self.async_refresh()
        if not self.last_update_success:
            raise TerminalError("Clocking unavailable. Use the RotaCloud terminal.")

    async def _terminal_changed(self, uid, result):
        # Called with io_lock held. Publish confirmed responses immediately;
        # reconcile history later without making the write look retryable.
        from homeassistant.config_entries import ConfigEntryState
        if self.entry.state != ConfigEntryState.LOADED:
            return
        if result is not None:
            self.active = [a for a in self.active if a.user_id != uid]
            if result.clock_out is None:
                self.active.append(result)
            else:
                self.completed = tuple(a for a in self.completed
                                       if (a.user_id, a.clock_in) != (uid, result.clock_in)) + (result,)
            now = datetime.now(timezone.utc)
            _, today, tomorrow = self._bounds(now)
            self.async_set_updated_data(self._project(now, today, tomorrow))
        self.dirty_history = True
        self.hass.async_create_task(self.async_request_refresh())

    def _bounds(self, now):
        return day_bounds(now, ZoneInfo(self.hass.config.time_zone))

    def _project(self, now, today, tomorrow):
        return snapshot(self.employees,self.shifts,self.active,self.completed,int(now.timestamp()),today,tomorrow,
                        self.entry.options.get(CONF_LATE,DEFAULT_LATE),self.entry.options.get(CONF_LEAVING,DEFAULT_LEAVING),
                        self.entry.options)

    def planning_rows(self, kind):
        grouped = {}
        if not self.planning_available:
            return []
        for window in self.windows:
            person = self.employees.get(window.user)
            if window.kind != kind or person is None:
                continue
            row = grouped.setdefault(window.user, {"name": " ".join((person.first_name, person.last_name)).strip(), "times": []})
            if window.label not in row["times"]:
                row["times"].append(window.label)
        return sorted(grouped.values(), key=lambda row: row["name"].casefold())

    async def async_manual_refresh(self):
        # One shared task across clients; repeated presses cannot create batches.
        if self._manual_task is not None and not self._manual_task.done():
            return await asyncio.shield(self._manual_task)
        wait = 30 - (time.monotonic() - self._last_manual)
        if wait > 0:
            raise TerminalError("Please wait %s seconds before refreshing again." % int(wait + 1))
        self._last_manual = time.monotonic()
        self._manual_task = self.hass.async_create_task(self._manual_refresh())
        return await asyncio.shield(self._manual_task)

    async def _manual_refresh(self):
        self.dirty_users = self.dirty_rota = self.dirty_history = self.dirty_planning = True
        await self.async_refresh()
        if not self.last_update_success:
            raise TerminalError("Unable to refresh attendance. Please try later.")
        return {"last_api_refresh": self.last_api_refresh, "planning_available": self.planning_available}

    def listen_for_refresh(self):
        async def refresh(event):
            # Existing trusted HA automation can relay events. Payload is not attendance truth.
            kind = event.data.get("kind")
            if kind in ("shift", "rota") or event.data.get("refresh_rota") is True:
                self.dirty_rota = True
            elif kind == "user":
                self.dirty_users = True
            elif kind in ("leave", "availability"):
                self.dirty_planning = True
            elif kind != "clock_in":
                self.dirty_history = True
            await self.async_request_refresh()
        return self.hass.bus.async_listen(REFRESH_EVENT, refresh)

    def listen_for_time(self):
        @callback
        def tick(now):
            if self.inflight or not self.last_update_success or self.data is None:
                return
            _, today, tomorrow = self._bounds(now)
            if self.day != today:
                # Day rollover needs fresh data, even in event-only mode.
                self.hass.async_create_task(self.async_request_refresh())
                return
            data = self._project(now,today,tomorrow)
            if data != self.data:
                self.data = data
                self.async_update_listeners()
        return async_track_time_interval(self.hass,tick,timedelta(minutes=1))

    async def _async_update_data(self):
        async with self.io_lock:
            return await self._async_update_locked()

    async def _async_update_locked(self):
        self.inflight = True
        mono = time.monotonic()
        now = datetime.now(timezone.utc)
        start, today, tomorrow = self._bounds(now)
        new_day = self.day != today
        try:
            # Consume flags before awaiting, so concurrent webhook invalidations aren't lost.
            users_due = self.dirty_users or mono >= self.users_until or new_day
            rota_due = self.dirty_rota or mono >= self.shifts_until or new_day
            history_due = self.dirty_history or mono >= self.history_until or new_day
            planning_due = self.dirty_planning or mono >= self.planning_until or new_day
            self.dirty_users = self.dirty_rota = self.dirty_history = False
            self.dirty_planning = False
            if users_due:
                self.employees = await self.roster.employees(now.astimezone(ZoneInfo(self.hass.config.time_zone)).date())
                self.users_until = mono + USERS_TTL
            if rota_due:
                self.shifts = await self.roster.shifts(start,tomorrow)
                self.shifts_until = mono + ROSTER_TTL
            active = await self.client.clocked_in()
            old = {(a.user_id,a.clock_in) for a in self.active}
            current = {(a.user_id,a.clock_in) for a in active}
            # A disappearance warrants history reconciliation even if the webhook was missed.
            if history_due or old-current:
                self.completed = await self.roster.completed(start,tomorrow)
                self.history_until = mono + HISTORY_TTL
            self.active = active
            if planning_due:
                try:
                    self.windows = await self.roster.planning(now.astimezone(ZoneInfo(self.hass.config.time_zone)).date().isoformat())
                    self.planning_available = True
                    self.planning_until = mono + PLANNING_TTL
                except (ApiError, ValueError, TypeError, KeyError, AttributeError):
                    # Missing planning permissions must not hide valid attendance.
                    self.windows = ()
                    self.planning_available = False
                    self.planning_until = mono + 900
            self.day = today
            self.last_api_refresh = int(datetime.now(timezone.utc).timestamp())
            return self._project(now,today,tomorrow)
        except ApiError as exc:
            self.dirty_users |= users_due and mono >= self.users_until
            self.dirty_rota |= rota_due
            self.dirty_history |= history_due
            self.dirty_planning |= planning_due
            if exc.status in (401,403):
                raise ConfigEntryAuthFailed("RotaCloud authentication failed") from None
            raise UpdateFailed("RotaCloud rate limited; requests paused" if exc.status==429 else "RotaCloud attendance refresh failed") from None
        except (ValueError,TypeError,KeyError,AttributeError):
            self.dirty_history = self.dirty_rota = True
            raise UpdateFailed("Unexpected RotaCloud response format") from None
        finally:
            self.inflight = False
