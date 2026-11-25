"""Isolated kiosk HTTP boundary. Not registered with HA in this development stage."""
from collections import deque
import hashlib
import hmac
import ipaddress
import json
import re
import time
from urllib.parse import urlsplit
from aiohttp import web
from .terminal import TerminalError

COOKIE = "__Secure-rotacloud_kiosk"
PATH = "/api/rotacloud_kiosk/"
TOKEN = re.compile(r"[A-Za-z0-9_-]{43}")
ACTIONS = frozenset({"clock_in", "clock_out", "start_break", "end_break"})
HEADERS = {
    "Cache-Control": "no-store, private",
    "Pragma": "no-cache",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
}

def digest(key):
    return hashlib.sha256(key.encode("ascii")).hexdigest()

def reply(data, status=200):
    return web.json_response(data, status=status, headers=HEADERS)

class Gateway:
    """Use server-verified peer IP and TLS; never trust arbitrary forwarded headers."""
    def __init__(self, terminal, *, origin, networks, device_digests, clock=time.monotonic):
        url = urlsplit(origin)
        if url.scheme != "https" or not url.hostname or url.username or url.password or url.path or url.query or url.fragment:
            raise ValueError("An exact HTTPS origin is required")
        self.origin = origin
        self.networks = tuple(ipaddress.ip_network(n, strict=True) for n in networks)
        if not self.networks or any(n.prefixlen == 0 for n in self.networks):
            raise ValueError("Explicit restricted kiosk networks required")
        if not device_digests or any(not re.fullmatch(r"[0-9a-f]{64}", v) for v in device_digests.values()):
            raise ValueError("Provision device digests first")
        if len(set(device_digests.values())) != len(device_digests):
            raise ValueError("Device credentials must be unique")
        self.devices = dict(device_digests)
        self.terminal = terminal
        self.clock = clock
        self.pair_attempts = deque()
        self.calls = deque()
        self.closed = False
        self.busy = False

    def close(self):
        self.closed = True
        self.devices.clear()
        self.terminal.sessions.clear()

    def _device(self, token):
        if not isinstance(token, str) or TOKEN.fullmatch(token) is None:
            return None
        candidate = digest(token)
        return next((name for name, expected in self.devices.items()
                     if hmac.compare_digest(candidate, expected)), None)

    def _allowed(self, request):
        try:
            peer = ipaddress.ip_address(request.remote)
        except (ValueError, TypeError):
            return False
        return (not self.closed and request.secure and request.method == "POST"
                and request.headers.get("Origin") == self.origin
                and request.headers.get("Sec-Fetch-Site", "same-origin") == "same-origin"
                and any(peer in n for n in self.networks))

    def _limit(self, queue, limit, seconds):
        now = self.clock()
        while queue and queue[0] <= now - seconds:
            queue.popleft()
        if len(queue) >= limit:
            return False
        queue.append(now)
        return True

    async def _body(self, request):
        if request.content_type != "application/json":
            raise ValueError("JSON required")
        if request.content_length is None or not 0 < request.content_length <= 1024:
            raise ValueError("Invalid body length")
        raw = await request.read()
        if len(raw) > 1024:
            raise ValueError("Body too large")
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("Object required")
        return data

    async def handle(self, request, operation):
        if not self._allowed(request):
            return reply({"error": "Terminal unavailable"}, 403)
        if operation not in ("pair", "identify", "act", "status"):
            return reply({"error": "Unknown operation"}, 404)
        if operation == "pair":
            if not self._limit(self.pair_attempts, 5, 60):
                return reply({"error": "Try again later"}, 429)
            try:
                body = await self._body(request)
                if set(body) != {"key"} or self._device(body["key"]) is None:
                    return reply({"error": "Pairing refused"}, 403)
                response = reply({"paired": True})
                response.set_cookie(COOKIE, body["key"], secure=True, httponly=True,
                                    samesite="Strict", path=PATH, max_age=86400 * 30)
                return response
            except (ValueError, TypeError, UnicodeError):
                return reply({"error": "Invalid request"}, 400)
        device = self._device(request.cookies.get(COOKIE))
        if device is None:
            return reply({"error": "Pair this terminal first"}, 401)
        if not self._limit(self.calls, 40, 60):
            return reply({"error": "Try again later"}, 429)
        if operation == "status":
            return reply({"paired": True})
        # Reject overlapping operations rather than queuing unbounded work or stale PINs.
        if self.busy:
            return reply({"error": "Terminal busy; wait for the current result"}, 409)
        self.busy = True
        try:
            body = await self._body(request)
            if operation == "identify":
                if set(body) != {"pin"} or not isinstance(body["pin"], str) or re.fullmatch(r"[0-9]{1,12}", body["pin"]) is None:
                    return reply({"error": "Invalid PIN format"}, 400)
                return reply(await self.terminal.identify(device, body["pin"]))
            if not {"session", "action"} <= set(body) <= {"session", "action", "shift_id"}:
                return reply({"error": "Invalid action request"}, 400)
            token, action, shift = body["session"], body["action"], body.get("shift_id")
            if not isinstance(token, str) or TOKEN.fullmatch(token) is None or not isinstance(action, str) or action not in ACTIONS or (shift is not None and (type(shift) is not int or shift <= 0)):
                return reply({"error": "Invalid action request"}, 400)
            return reply(await self.terminal.act(device, token, action, shift))
        except TerminalError as exc:
            return reply({"error": str(exc)}, 409)
        except (ValueError, TypeError, UnicodeError):
            return reply({"error": "Invalid request"}, 400)
        except Exception:
            # Do not expose exception text (could include credentials or PINs).
            return reply({"error": "Outcome unavailable. Check RotaCloud before retrying."}, 503)
        finally:
            self.busy = False
