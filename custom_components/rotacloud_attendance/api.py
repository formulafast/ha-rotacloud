"""Async server-only API transport. No retries on attendance mutations."""
import asyncio
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from dataclasses import dataclass
from typing import Any
import aiohttp
from .model import Attendance, Break

BASE_URL = 'https://api.rotacloud.com/v1'


class ApiError(Exception):
    """Safe exception: no URLs, PINs, tokens or raw response data."""
    def __init__(self, status: int | None, *, uncertain: bool = False, retry_after: str | None = None):
        self.status = status
        self.uncertain = uncertain
        self.retry_after = retry_after
        super().__init__('RotaCloud request failed' if not uncertain else 'RotaCloud write outcome unknown; reconcile before retrying')


@dataclass(frozen=True, slots=True)
class Employee:
    id: int
    first_name: str
    last_name: str


class Client:
    def __init__(self, session: aiohttp.ClientSession, api_key: str, terminal_id: int):
        if type(terminal_id) is not int or terminal_id <= 0 or not api_key:
            raise ValueError('Missing valid terminal or credentials')
        self._session = session
        self._key = api_key
        self._terminal = terminal_id
        self._blocked_until = 0.0
        self._rate_failures = 0
        self._request_lock = asyncio.Lock()

    async def _request(self, method: str, path: str, *, body: dict | None = None, params: dict | None = None) -> tuple[Any, dict]:
        async with self._request_lock:
            if time.monotonic() < self._blocked_until:
                raise ApiError(429)
            return await self._send(method, path, body=body, params=params)

    async def _send(self, method, path, *, body=None, params=None):
        try:
            async with self._session.request(method, BASE_URL + path,
                    headers={'Authorization': 'Bearer ' + self._key, 'Accept': 'application/json'},
                    json=body, params=params, timeout=aiohttp.ClientTimeout(total=15), allow_redirects=False) as response:
                if response.status == 429:
                    self._rate_failures += 1
                    delay = min(21600, 900 * 2**min(self._rate_failures-1, 5))
                    raw = response.headers.get("Retry-After")
                    if raw:
                        try:
                            delay = max(delay, float(raw))
                        except ValueError:
                            try:
                                delay = max(delay, (parsedate_to_datetime(raw) - datetime.now(timezone.utc)).total_seconds())
                            except (ValueError, TypeError, OverflowError):
                                pass
                    self._blocked_until = time.monotonic() + delay
                if not 200 <= response.status < 300:
                    raise ApiError(response.status, uncertain=method != 'GET' and response.status >= 500,
                                   retry_after=response.headers.get('Retry-After'))
                data = await response.json()
                self._rate_failures = 0
                return data, dict(response.headers)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            raise ApiError(None, uncertain=method != 'GET') from None

    async def identify(self, pin: str) -> Employee:
        # Never call with a PIN from an automation/service; only the protected terminal endpoint.
        if not isinstance(pin, str) or not 1 <= len(pin) <= 12 or not pin.isascii() or not pin.isdigit():
            raise ValueError('Invalid PIN format')
        data, _ = await self._request('GET', '/pins/' + pin)
        if not isinstance(data, dict) or data.get('deleted') or type(data.get('id')) is not int:
            raise ApiError(403)
        return Employee(data['id'], str(data.get('first_name') or ''), str(data.get('last_name') or ''))

    async def clocked_in(self) -> list[Attendance]:
        records = []
        offset = 0
        while True:
            data, headers = await self._request('GET', '/users_clocked_in', params={'limit': 100, 'offset': offset})
            if not isinstance(data, list):
                raise ApiError(None)
            records.extend(Attendance.from_record(row) for row in data)
            offset += len(data)
            total = next((v for k, v in headers.items() if k.lower() == 'x-total-count'), None)
            if total is None or offset >= int(total):
                return records
            if not data:
                raise ApiError(None)

    def _payload(self) -> dict:
        return {'method': 'terminal', 'terminal': self._terminal}

    async def clock_in(self, user_id: int, shift_id: int | None = None) -> Attendance:
        body = self._payload() | {'user': user_id}
        if shift_id is not None:
            body['shift'] = shift_id
        data, _ = await self._request('POST', '/users_clocked_in', body=body)
        try:
            return Attendance.from_record(data)
        except (ValueError, TypeError, AttributeError):
            raise ApiError(None, uncertain=True) from None

    async def set_break(self, user_id: int, action: str) -> Break:
        if action not in ('start_break', 'end_break'):
            raise ValueError('Invalid break action')
        data, _ = await self._request('POST', f'/users_clocked_in/{int(user_id)}', body=self._payload() | {'action': action})
        if not isinstance(data, dict) or type(data.get('start_time')) is not int or (action == 'end_break' and type(data.get('end_time')) is not int):
            raise ApiError(None, uncertain=True)
        return Break(data['start_time'], data.get('end_time'))

    async def clock_out(self, user_id: int) -> Attendance:
        data, _ = await self._request('DELETE', f'/users_clocked_in/{int(user_id)}', body=self._payload())
        try:
            return Attendance.from_record(data)
        except (ValueError, TypeError, AttributeError):
            raise ApiError(None, uncertain=True) from None
