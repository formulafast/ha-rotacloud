"""Low-traffic read-only coordinator. Clocking gateway not enabled yet."""
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

_LOGGER = logging.getLogger(__name__)
ROSTER_TTL = 6 * 3600
USERS_TTL = 24 * 3600
HISTORY_TTL = 6 * 3600

class AttendanceCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry, client):
        interval = entry.options.get(CONF_POLL, DEFAULT_POLL)
        super().__init__(hass, _LOGGER, config_entry=entry, name="RotaCloud Attendance",
                         update_interval=timedelta(seconds=max(1800, interval)) if interval else None,
                         always_update=False)
        self.client, self.entry = client, entry
        self.roster = RosterClient(client)
        self.employees, self.shifts, self.active, self.completed = {}, (), [], ()
        self.users_until = self.shifts_until = self.history_until = 0.0
        self.day = None
        self.dirty_history = True
        self.dirty_rota = True
        self.dirty_users = True
        self.inflight = False

    def _bounds(self, now):
        return day_bounds(now, ZoneInfo(self.hass.config.time_zone))

    def _project(self, now, today, tomorrow):
        return snapshot(self.employees,self.shifts,self.active,self.completed,int(now.timestamp()),today,tomorrow,
                        self.entry.options.get(CONF_LATE,DEFAULT_LATE),self.entry.options.get(CONF_LEAVING,DEFAULT_LEAVING))

    def listen_for_refresh(self):
        async def refresh(event):
            # Existing trusted HA automation can relay events. Payload is not attendance truth.
            kind = event.data.get("kind")
            if kind in ("shift", "rota") or event.data.get("refresh_rota") is True:
                self.dirty_rota = True
            elif kind == "user":
                self.dirty_users = True
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
        self.inflight = True
        mono = time.monotonic()
        now = datetime.now(timezone.utc)
        start, today, tomorrow = self._bounds(now)
        new_day = self.day != today
        try:
            # Consume flags before awaiting, so concurrent webhook invalidations aren't lost.
            users_due = self.dirty_users or mono >= self.users_until
            rota_due = self.dirty_rota or mono >= self.shifts_until or new_day
            history_due = self.dirty_history or mono >= self.history_until or new_day
            self.dirty_users = self.dirty_rota = self.dirty_history = False
            if users_due:
                self.employees = await self.roster.employees()
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
            self.day = today
            return self._project(now,today,tomorrow)
        except ApiError as exc:
            self.dirty_users |= users_due and mono >= self.users_until
            self.dirty_rota |= rota_due
            self.dirty_history |= history_due
            if exc.status in (401,403):
                raise ConfigEntryAuthFailed("RotaCloud authentication failed") from None
            raise UpdateFailed("RotaCloud rate limited; requests paused" if exc.status==429 else "RotaCloud attendance refresh failed") from None
        except (ValueError,TypeError,KeyError,AttributeError):
            self.dirty_history = self.dirty_rota = True
            raise UpdateFailed("Unexpected RotaCloud response format") from None
        finally:
            self.inflight = False
