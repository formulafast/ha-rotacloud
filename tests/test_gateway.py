"""HTTP boundary checks, no real users, network or credentials."""
import json
import unittest
from unittest.mock import AsyncMock, MagicMock
from custom_components.rotacloud_attendance.gateway import Gateway, COOKIE, digest
from custom_components.rotacloud_attendance.terminal import TerminalError

KEY = "a" * 43
SESSION = "b" * 43
class GatewayTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.terminal = MagicMock()
        self.terminal.sessions = {}
        self.terminal.identify = AsyncMock(return_value={"session": SESSION, "name": "Example"})
        self.terminal.act = AsyncMock(return_value={"action": "clock_in"})
        self.g = Gateway(self.terminal, origin="https://kiosk.example.invalid",
                         networks=["192.0.2.0/24"], device_digests={"test": digest(KEY)})
    def request(self, body=None, *, secure=True, origin="https://kiosk.example.invalid",
                remote="192.0.2.1", cookie=KEY, method="POST"):
        req = MagicMock()
        raw = json.dumps(body or {}).encode()
        req.remote, req.secure, req.method = remote, secure, method
        req.headers = {"Origin": origin}
        req.cookies = {COOKIE: cookie} if cookie else {}
        req.content_type, req.content_length = "application/json", len(raw)
        req.read = AsyncMock(return_value=raw)
        return req
    async def test_requires_https_and_network_and_origin(self):
        for kwargs in ({"secure": False}, {"remote": "198.51.100.1"}, {"origin": "https://other.invalid"}, {"method": "GET"}):
            result = await self.g.handle(self.request({"pin":"0000"}, **kwargs), "identify")
            self.assertEqual(result.status, 403)
        self.terminal.identify.assert_not_awaited()
    async def test_unauthenticated_cannot_read_or_write(self):
        for op in ("identify", "act", "status"):
            self.assertEqual((await self.g.handle(self.request(cookie=None), op)).status, 401)
        self.terminal.identify.assert_not_awaited()
        self.terminal.act.assert_not_awaited()
    async def test_pair_cookie_is_restricted(self):
        r = await self.g.handle(self.request({"key":KEY}, cookie=None), "pair")
        self.assertEqual(r.status, 200)
        self.assertTrue(r.cookies[COOKIE]["secure"])
        self.assertTrue(r.cookies[COOKIE]["httponly"])
        self.assertEqual(r.cookies[COOKIE]["samesite"], "Strict")
        self.assertEqual(r.cookies[COOKIE]["path"], "/api/rotacloud_kiosk/")
        self.assertNotIn(KEY, r.text)
        self.assertIn("no-store", r.headers["Cache-Control"])
    async def test_pair_rate_limit(self):
        for _ in range(5):
            self.assertEqual((await self.g.handle(self.request({"key":"bad"}), "pair")).status, 403)
        self.assertEqual((await self.g.handle(self.request({"key":KEY}), "pair")).status, 429)
    async def test_device_identity_supplied_by_server(self):
        r = await self.g.handle(self.request({"pin":"0000"}), "identify")
        self.assertEqual(r.status, 200)
        self.terminal.identify.assert_awaited_once_with("test", "0000")
        r = await self.g.handle(self.request({"session":SESSION,"action":"clock_in","shift_id":5}), "act")
        self.assertEqual(r.status, 200)
        self.terminal.act.assert_awaited_once_with("test", SESSION, "clock_in", 5)
    async def test_rejects_arbitrary_employee_id_and_invalid_actions(self):
        for body in ({"session":SESSION,"action":"clock_in","user_id":2},
                     {"session":SESSION,"action":"delete"},
                     {"session":SESSION,"action":"clock_in","shift_id":True}):
            self.assertEqual((await self.g.handle(self.request(body), "act")).status, 400)
        self.terminal.act.assert_not_awaited()
    async def test_revocation_and_close(self):
        self.g.devices.clear()
        self.assertEqual((await self.g.handle(self.request(), "status")).status, 401)
        self.g.close()
        self.assertEqual((await self.g.handle(self.request(), "status")).status, 403)
    async def test_error_does_not_leak_secret(self):
        self.terminal.act.side_effect = RuntimeError(KEY)
        result = await self.g.handle(self.request({"session":SESSION,"action":"clock_in"}), "act")
        self.assertEqual(result.status, 503)
        self.assertNotIn(KEY, result.text)
    async def test_oversized_body_rejected(self):
        req = self.request({"pin":"0000"})
        req.content_length = 1025
        self.assertEqual((await self.g.handle(req, "identify")).status, 400)
        req.read.assert_not_awaited()
    async def test_busy_does_not_queue_write(self):
        self.g.busy = True
        self.assertEqual((await self.g.handle(self.request({"session":SESSION,"action":"clock_in"}), "act")).status, 409)
        self.terminal.act.assert_not_awaited()
