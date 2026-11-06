import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('work_countdown', Path('apps/work-motivator/countdown.py'))
countdown = importlib.util.module_from_spec(spec); spec.loader.exec_module(countdown)

class CountdownTests(unittest.TestCase):
    def test_duration_validation(self):
        self.assertEqual(countdown.parse_duration('05:00:00'), 18000)
        self.assertEqual(countdown.parse_duration('2:03:04'), 7384)
        for value in ('00:00:00', '5', '-1:00:00', '01:60:00', '1:1:1', '1000:00:00', None):
            with self.subTest(value=value), self.assertRaises(ValueError): countdown.parse_duration(value)

    def test_activation_preservation_reset_and_expiry(self):
        start = countdown.new_deadline(True, '05:00:00', False, '05:00:00', None, 100)
        self.assertEqual(start, 18100)
        self.assertEqual(countdown.new_deadline(True, '05:00:00', True, '05:00:00', start, 200), start)
        self.assertEqual(countdown.remaining_text(start, 280), '04:57:00')
        self.assertEqual(countdown.remaining_text(start, 19000), '00:00:00')
        self.assertEqual(countdown.new_deadline(True, '01:30:00', True, '05:00:00', start, 200), 5600)
        self.assertEqual(countdown.new_deadline(True, '05:00:00', True, '05:00:00', start, 200, reset=True), 18200)
        self.assertIsNone(countdown.new_deadline(False, '05:00:00', True, '05:00:00', start, 200))
        self.assertEqual(countdown.new_deadline(True, '05:00:00', False, '05:00:00', None, 300), 18300)
