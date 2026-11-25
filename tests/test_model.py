import unittest
from custom_components.rotacloud_attendance.model import Attendance

class ModelTests(unittest.TestCase):
    def test_gross_duration_ignores_breaks_and_payroll_adjustments(self):
        a = Attendance.from_record({'user': 1, 'in_time': 200, 'in_time_clocked': 100,
            'out_time': 3700, 'out_time_clocked': 3800, 'breaks_clocked': [{'start_time': 500, 'end_time': 1100}]})
        self.assertEqual(a.shift_seconds(9999), 3700)
        self.assertEqual(a.break_seconds(9999), 600)
        self.assertEqual(a.state, 'gone')

    def test_active_break_and_completed_breaks(self):
        a = Attendance.from_record({'user': 1, 'in_time': 100, 'breaks_clocked': [
            {'start_time': 200, 'end_time': 260}, {'start_time': 500}]})
        self.assertEqual(a.state, 'break')
        self.assertEqual(a.allowed_actions, ('end_break', 'clock_out'))
        self.assertEqual(a.break_seconds(620), 180)

    def test_same_minute_break_closed(self):
        a = Attendance.from_record({'user': 1, 'in_time': 100, 'out_time': 100,
                                    'breaks_clocked': [{'start_time': 100, 'end_time': 100}]})
        self.assertIsNone(a.active_break)
        self.assertEqual(a.break_seconds(999), 0)

    def test_working_and_shift_link(self):
        a = Attendance.from_record({'user': 1, 'in_time': 100, 'shift': {'id': 7, 'end_time': 1000}})
        self.assertEqual(a.allowed_actions, ('start_break', 'clock_out'))
        self.assertEqual(a.scheduled_end, 1000)

    def test_closed_record_with_missing_break_end(self):
        a = Attendance.from_record({'user': 1, 'in_time': 100, 'out_time': 200,
                                    'breaks_clocked': [{'start_time': 180}]})
        self.assertEqual(a.break_seconds(999), 20)
        self.assertIsNone(a.active_break)
