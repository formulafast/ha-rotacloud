import unittest
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
from custom_components.rotacloud_attendance.snapshot import day_bounds,snapshot
from custom_components.rotacloud_attendance.roster import Shift
from custom_components.rotacloud_attendance.model import Attendance,Break
from custom_components.rotacloud_attendance.api import Employee

class SnapshotTests(unittest.TestCase):
    def test_dst_day(self):
        _,a,b=day_bounds(datetime(2026,3,29,12,tzinfo=timezone.utc),ZoneInfo("Europe/London"))
        self.assertEqual(b-a,23*3600)
    def test_fall_dst(self):
        _,a,b=day_bounds(datetime(2026,10,25,12,tzinfo=timezone.utc),ZoneInfo("Europe/London"))
        self.assertEqual(b-a,25*3600)
    def test_statuses(self):
        shifts=[Shift(1,1,100,1000),Shift(2,2,900,1000),Shift(3,3,100,1000),Shift(4,4,100,200),Shift(5,5,100,1000)]
        active=[Attendance(3,110,None,(Break(200,None),),3),Attendance(5,90,None,(),5)]
        past=[Attendance(4,100,210,(),4)]
        r=snapshot({},shifts,active,past,500,0,2000,0,0)
        self.assertEqual([r[i].status for i in range(1,6)],["late","due","break","gone","here"])
        self.assertEqual(r[3].active_break_start,200)
        self.assertEqual(r[5].clock_in_delta_seconds,-10)
    def test_unscheduled_and_overnight(self):
        r=snapshot({},[Shift(1,1,-500,300)], [Attendance(2,-500,None,())],[],100,0,2000)
        self.assertEqual(r[1].status,"late")
        self.assertEqual(r[2].status,"here")
        self.assertIsNone(r[2].clock_in_delta_seconds)
    def test_split_shift(self):
        shifts=[Shift(1,1,100,200),Shift(2,1,900,1000)]
        r=snapshot({},shifts,[],[Attendance(1,100,200,(),1)],500,0,2000)
        self.assertEqual(r[1].status,"due")
        self.assertIsNone(r[1].clock_in_delta_seconds)
    def test_breaks_and_gross(self):
        a=Attendance(1,100,300,(Break(150,180),),1)
        r=snapshot({},[Shift(1,1,110,290)],[],[a],400,0,2000)[1]
        self.assertEqual(r.completed_break_seconds,30)
        self.assertEqual(r.attendance.shift_seconds(400),200)
        self.assertEqual(r.clock_out_delta_seconds,10)
    def test_leaving(self):
        r=snapshot({},[Shift(1,1,100,1000)],[Attendance(1,100,None,(),1)],[],990,0,2000,0,1)
        self.assertEqual(r[1].status,"leaving")
    def test_missed_shift(self):
        r=snapshot({},[Shift(1,1,100,200)],[],[],500,0,2000)
        self.assertEqual(r[1].status,"late")
    def test_names(self):
        r=snapshot({1:Employee(1,"Example","Staff")},[],[Attendance(1,100,None,())],[],500,0,2000)
        self.assertEqual(r[1].name,"Example Staff")
