"""Shared coordinator; cached read-only queries and rate-limit cooldown."""
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import logging
import time
from zoneinfo import ZoneInfo
from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .api import ApiError
from .const import (CONF_POLL, CONF_LATE, CONF_LEAVING, DEFAULT_POLL, DEFAULT_LATE,
                    DEFAULT_LEAVING, REFRESH_EVENT)
from .roster import RosterClient
from .snapshot import day_bounds, snapshot

_LOGGER = logging.getLogger(__name__)

class AttendanceCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry: ConfigEntry, client):
        super().__init__(hass, _LOGGER, config_entry=entry, name="RotaCloud Attendance",
                         update_interval=timedelta(seconds=entry.options.get(CONF_POLL, DEFAULT_POLL)),
                         always_update=False)
        self.client = client
        self.roster = RosterClient(client)
        self.entry = entry
        self.employees = {}
        self.shifts = ()
        self.users_until = self.shifts_until = self.blocked_until = 0.0
        self.last_attempt = -float("inf")
        self.day = None
        self.rate_failures = 0

    def listen_for_refresh(self):
        async def refresh(event):
            # Existing trusted HA automation can emit this event; never use payload as attendance truth.
            if time.monotonic() >= max(self.blocked_until, self.last_attempt + 30):
                self.shifts_until = 0 if event.data.get("refresh_rota") is True else self.shifts_until
                await self.async_request_refresh()
        return self.hass.bus.async_listen(REFRESH_EVENT, refresh)

    async def _async_update_data(self):
        mono = time.monotonic()
        if mono < self.blocked_until:
            raise UpdateFailed("RotaCloud rate-limit cooldown")
        self.last_attempt = mono
        now = datetime.now(timezone.utc)
        start, today, tomorrow = day_bounds(now, ZoneInfo(self.hass.config.time_zone))
        try:
            if mono >= self.users_until:
                self.employees = await self.roster.employees()
                self.users_until = mono + 3600
            if mono >= self.shifts_until or self.day != today:
                self.shifts = await self.roster.shifts(start, tomorrow)
                self.shifts_until = mono + 900
                self.day = today
            active = await self.client.clocked_in()
            completed = await self.roster.completed(start, tomorrow)
            self.rate_failures = 0
            return snapshot(self.employees,self.shifts,active,completed,int(now.timestamp()),today,tomorrow,
                            self.entry.options.get(CONF_LATE,DEFAULT_LATE),self.entry.options.get(CONF_LEAVING,DEFAULT_LEAVING))
        except ApiError as exc:
            if exc.status in (401,403):
                raise ConfigEntryAuthFailed("RotaCloud authentication failed") from None
            if exc.status == 429:
                self.rate_failures += 1
                delay = min(3600,60 * 2**min(self.rate_failures-1,6))
                if exc.retry_after:
                    try:
                        retry = float(exc.retry_after)
                    except ValueError:
                        try:
                            retry = (parsedate_to_datetime(exc.retry_after) - now).total_seconds()
                        except (ValueError,TypeError,OverflowError):
                            retry = 0
                    delay = max(delay,retry)
                self.blocked_until = time.monotonic()+delay
            raise UpdateFailed("RotaCloud attendance refresh failed") from None
        except (ValueError,TypeError,KeyError,AttributeError):
            raise UpdateFailed("Unexpected RotaCloud response format") from None
