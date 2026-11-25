"""Adversarial offline tests; all identities and keys are fictional."""
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from custom_components.rotacloud_attendance.api import Client, Employee, ApiError
from custom_components.rotacloud_attendance.model import Attendance, Break
from custom_components.rotacloud_attendance.terminal import Terminal, TerminalError
from custom_components.rotacloud_attendance.roster import Shift

class TerminalSafetyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = AsyncMock()
        self.client.identify.return_value = Employee(1, "Test", "Employee")
        self.client.clocked_in.return_value = []
        self.client.clock_in.return_value = Attendance(1, 300, None, ())
        self.change = AsyncMock()
        self.now = 10
        self.t = Terminal(self.client, lambda device, uid: device == "test" and uid == 1,
                          lambda *_: (), self.change, monotonic=lambda: self.now, wall=lambda: 300)
    async def session(self):
        return (await self.t.identify("test", "0000"))["session"]
    async def test_expired_session(self):
        token = await self.session()
        self.now += 21
        with self.assertRaises(TerminalError):
            await self.t.act("test", token, "clock_in")
        self.client.clock_in.assert_not_awaited()
    async def test_new_pin_invalidates_previous_session(self):
        old = await self.session()
        await self.session()
        with self.assertRaises(TerminalError):
            await self.t.act("test", old, "clock_in")
        self.client.clock_in.assert_not_awaited()
    async def test_eligibility_revocation(self):
        token = await self.session()
        self.t.eligible = lambda *_: False
        with self.assertRaises(TerminalError):
            await self.t.act("test", token, "clock_in")
        self.client.clock_in.assert_not_awaited()
    async def test_concurrent_duplicate(self):
        token = await self.session()
        results = await asyncio.gather(self.t.act("test", token, "clock_in"),
                                       self.t.act("test", token, "clock_in"), return_exceptions=True)
        self.assertEqual(sum(isinstance(x, TerminalError) for x in results), 1)
        self.client.clock_in.assert_awaited_once()
    async def test_prewrite_api_failure(self):
        token = await self.session()
        self.client.clocked_in.side_effect = ApiError(429)
        with self.assertRaisesRegex(TerminalError, "Clocking unavailable"):
            await self.t.act("test", token, "clock_in")
        self.client.clock_in.assert_not_awaited()
    async def test_wrong_user_response_is_uncertain(self):
        token = await self.session()
        self.client.clock_in.return_value = Attendance(2, 300, None, ())
        with self.assertRaisesRegex(TerminalError, "Outcome unknown"):
            await self.t.act("test", token, "clock_in")
        self.change.assert_awaited_once_with(1, None)
    async def test_reconciliation_failure_does_not_invite_retry(self):
        token = await self.session()
        self.client.clock_in.side_effect = ApiError(None, uncertain=True)
        self.change.side_effect = RuntimeError("simulated callback failure")
        with self.assertRaisesRegex(TerminalError, "Outcome unknown"):
            await self.t.act("test", token, "clock_in")
        self.client.clock_in.assert_awaited_once()
    async def test_confirmed_write_survives_callback_failure(self):
        token = await self.session()
        self.change.side_effect = RuntimeError("simulated callback failure")
        self.assertEqual((await self.t.act("test", token, "clock_in"))["state"], "here")
        self.client.clock_in.assert_awaited_once()
    async def test_mismatched_break_response(self):
        self.client.clocked_in.return_value = [Attendance(1, 100, None, (Break(200, None),))]
        token = await self.session()
        self.client.set_break.return_value = Break(201, 300)
        with self.assertRaisesRegex(TerminalError, "Outcome unknown"):
            await self.t.act("test", token, "end_break")
        self.change.assert_awaited_once_with(1, None)
    async def test_duplicate_active_records_rejected(self):
        self.client.clocked_in.return_value = [Attendance(1, 100, None, ()), Attendance(1, 101, None, ())]
        with self.assertRaisesRegex(TerminalError, "reconciliation"):
            await self.session()
    async def test_scheduled_end_in_confirmation(self):
        self.t.shifts_for = lambda *_: (Shift(5, 1, 200, 900),)
        token = await self.session()
        result = await self.t.act("test", token, "clock_in", 5)
        self.assertEqual(result["scheduled_end"], 900)

class TransportSafetyTests(unittest.IsolatedAsyncioTestCase):
    async def test_429_blocks_followup_and_mutation(self):
        session = MagicMock()
        response = MagicMock(status=429, headers={"Retry-After":"1800"})
        session.request.return_value.__aenter__ = AsyncMock(return_value=response)
        session.request.return_value.__aexit__ = AsyncMock(return_value=False)
        client = Client(session, "fictional-key", 1)
        with patch("custom_components.rotacloud_attendance.api.time.monotonic", return_value=100):
            with self.assertRaises(ApiError):
                await client.clocked_in()
            with self.assertRaises(ApiError):
                await client.clock_in(1)
            self.assertEqual(client._blocked_until, 1900)
        session.request.assert_called_once()
        self.assertFalse(session.request.call_args.kwargs["allow_redirects"])
    async def test_transport_failure_hides_credentials_and_pin(self):
        session = MagicMock()
        session.request.side_effect = asyncio.TimeoutError("sensitive example URL /pins/0000")
        client = Client(session, "fictional-key", 1)
        with self.assertRaises(ApiError) as ctx:
            await client.identify("0000")
        self.assertNotIn("0000", str(ctx.exception))
        self.assertNotIn("fictional-key", str(ctx.exception))
        self.assertFalse(ctx.exception.uncertain)
