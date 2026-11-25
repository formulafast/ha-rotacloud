import unittest
from unittest.mock import AsyncMock
from custom_components.rotacloud_attendance.api import Employee,ApiError
from custom_components.rotacloud_attendance.model import Attendance,Break
from custom_components.rotacloud_attendance.terminal import Terminal,TerminalError
from custom_components.rotacloud_attendance.roster import Shift

class TerminalTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client=AsyncMock()
        self.client.identify.return_value=Employee(1,"Alex","Example")
        self.client.clocked_in.return_value=[]
        self.change=AsyncMock()
        self.t=Terminal(self.client,lambda device,uid:device=="kiosk" and uid==1,lambda *_:(),self.change,monotonic=lambda:10,wall=lambda:300)
    async def test_clock_in_one_use(self):
        s=await self.t.identify("kiosk","1234")
        self.client.clock_in.return_value=Attendance(1,300,None,())
        r=await self.t.act("kiosk",s["session"],"clock_in")
        self.assertEqual(r["clock_in"],300)
        with self.assertRaises(TerminalError):
            await self.t.act("kiosk",s["session"],"clock_in")
        self.client.clock_in.assert_awaited_once()
    async def test_device_binding(self):
        s=await self.t.identify("kiosk","1234")
        with self.assertRaises(TerminalError):
            await self.t.act("other",s["session"],"clock_in")
        self.client.clock_in.assert_not_awaited()
    async def test_state_changed(self):
        s=await self.t.identify("kiosk","1234")
        self.client.clocked_in.return_value=[Attendance(1,200,None,())]
        with self.assertRaises(TerminalError):
            await self.t.act("kiosk",s["session"],"clock_in")
    async def test_end_break(self):
        self.client.clocked_in.return_value=[Attendance(1,100,None,(Break(120,150),Break(200,None)))]
        s=await self.t.identify("kiosk","1234")
        self.client.set_break.return_value=Break(200,300)
        r=await self.t.act("kiosk",s["session"],"end_break")
        self.assertEqual((r["last_break_seconds"],r["break_seconds"]),(100,130))
    async def test_clock_out_on_break(self):
        self.client.clocked_in.return_value=[Attendance(1,100,None,(Break(200,None),))]
        s=await self.t.identify("kiosk","1234")
        self.client.clock_out.return_value=Attendance(1,100,300,())
        r=await self.t.act("kiosk",s["session"],"clock_out")
        self.assertEqual((r["shift_seconds"],r["break_seconds"]),(200,100))
        self.assertTrue(r["provisional_break_total"])
    async def test_shift_required(self):
        self.t.shifts_for=lambda *_:(Shift(2,1,100,500),)
        s=await self.t.identify("kiosk","1234")
        with self.assertRaises(TerminalError):
            await self.t.act("kiosk",s["session"],"clock_in",99)
        self.client.clock_in.assert_not_awaited()
    async def test_uncertain_not_retried(self):
        s=await self.t.identify("kiosk","1234")
        self.client.clock_in.side_effect=ApiError(None,uncertain=True)
        with self.assertRaisesRegex(TerminalError,"Outcome unknown"):
            await self.t.act("kiosk",s["session"],"clock_in")
        self.client.clock_in.assert_awaited_once()
    async def test_rate_limit(self):
        for _ in range(8):
            await self.t.identify("kiosk","1234")
        with self.assertRaisesRegex(TerminalError,"Too many"):
            await self.t.identify("kiosk","1234")
        self.assertEqual(self.client.identify.await_count,8)
