import unittest
from datetime import date
from custom_components.rotacloud_attendance.api import Employee
from custom_components.rotacloud_attendance.model import Attendance, Break
from custom_components.rotacloud_attendance.planning import age_band, break_warning, break_seconds_today, availability_windows, leave_windows
from custom_components.rotacloud_attendance.snapshot import snapshot


class PlanningTests(unittest.TestCase):
    def test_age_band_changes_on_birthday_and_unknown_is_not_assumed_adult(self):
        self.assertEqual(age_band('2008-11-26',date(2026,11,25)),'under18')
        self.assertEqual(age_band('2008-11-26',date(2026,11,26)),'adult')
        for dob in (None,'','not-a-date','2099-01-01'):
            self.assertIsNone(age_band(dob,date(2026,11,26)))

    def test_availability_is_explicit_not_inferred_from_empty_or_unavailable(self):
        rows=[{'user':1,'dates':[{'date':'2026-11-26','available':[],'unavailable':[]}]},
              {'user':2,'dates':[{'date':'2026-11-26','available':[{'start_time':'09:00','end_time':'13:00'},{'start_time':'17:00','end_time':'21:00'}]}]},
              {'user':3,'dates':[{'date':'2026-11-26','available':[],'unavailable':[{'start_time':'00:00','end_time':'00:00'}]}]}]
        windows=availability_windows(rows,'2026-11-26')
        self.assertEqual([w.user for w in windows],[2,2])
        self.assertEqual([w.label for w in windows],['09:00 – 13:00','17:00 – 21:00'])

    def test_availability_all_day_and_overnight(self):
        windows=availability_windows([{'user':1,'dates':[{'date':'2026-11-26','available':[{'start_time':'00:00','end_time':'00:00'},{'start_time':'22:00','end_time':'02:00'}]}]}],'2026-11-26')
        self.assertEqual([w.label for w in windows],['All Day','22:00 – 02:00 (+1 day)'])

    def test_leave_approved_only_and_no_invented_half_day_times(self):
        row={'user':1,'status':'approved','start_date':'2026-11-26','end_date':'2026-11-26','start_am_pm':'pm','end_am_pm':'pm','dates':[{'date':'2026-11-26','days':.5}]}
        self.assertEqual(leave_windows([row],'2026-11-26')[0].label,'PM · exact times not provided')
        self.assertFalse(leave_windows([{**row,'status':'pending'},{**row,'deleted':True}],'2026-11-26'))
        row['dates'][0].update(start_time='13:15',end_time='17:45')
        self.assertEqual(leave_windows([row],'2026-11-26')[0].label,'13:15 – 17:45')

    def test_leave_all_day(self):
        row={'user':1,'status':'approved','dates':[{'date':'2026-11-26','days':1}]}
        self.assertEqual(leave_windows([row],'2026-11-26')[0].label,'All Day')

    def test_partial_leave_without_precise_boundaries_is_not_all_day(self):
        row={'user':1,'status':'approved','start_date':'2026-11-26','end_date':'2026-11-26','start_am_pm':'am','end_am_pm':'pm','dates':[{'date':'2026-11-26','days':.5}]}
        self.assertEqual(leave_windows([row],'2026-11-26')[0].label,'Part Day · exact times not provided')

    def test_break_eligibility_uses_worked_time_excluding_breaks(self):
        options={'break_under18_minimum_minutes':30,'break_under18_qualifying_hours':4,'break_under18_qualifying_minutes':30,'break_under18_warning_hours':4}
        a=Attendance(1,0,None,(Break(60,660),))
        self.assertFalse(break_warning(a,'under18',options,4*3600+30*60))
        self.assertTrue(break_warning(a,'under18',options,4*3600+40*60))
        self.assertFalse(break_warning(a,'adult',options,8*3600))
        self.assertFalse(break_warning(a,None,options,8*3600))

    def test_warning_waits_for_elapsed_threshold_and_clears_after_break(self):
        options={'break_adult_minimum_minutes':20,'break_adult_qualifying_hours':3,'break_adult_warning_hours':4}
        a=Attendance(1,0,None,())
        self.assertFalse(break_warning(a,'adult',options,3*3600+59*60))
        self.assertTrue(break_warning(a,'adult',options,4*3600))
        a=Attendance(1,0,None,(Break(3600,4800),))
        self.assertFalse(break_warning(a,'adult',options,5*3600))

    def test_break_totals_clip_to_today_and_include_active(self):
        records=[Attendance(1,0,None,(Break(80,120),Break(160,None)))]
        self.assertEqual(break_seconds_today(records,100,200,180),40)

    def test_previous_day_flag_only_for_still_open_clockings(self):
        employee={1:Employee(1,'Alex','Example')}
        open_record=Attendance(1,90,None,())
        result=snapshot(employee,(),[open_record],(),150,100,200)
        self.assertTrue(result[1].previous_day)
        result=snapshot(employee,(),[],(Attendance(1,90,140,()),),150,100,200)
        self.assertFalse(result[1].previous_day)
