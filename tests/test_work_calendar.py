from datetime import date
import importlib.util
from pathlib import Path
import unittest
from unittest import mock
from shared.common import Translator

spec = importlib.util.spec_from_file_location('work_calendar', Path('apps/work-motivator/calendar_display.py'))
calendar = importlib.util.module_from_spec(spec); spec.loader.exec_module(calendar)

class CalendarTests(unittest.TestCase):
    def test_new_year_and_leap_month(self):
        solar, lunar = calendar.calendar_lines(date(2024, 2, 10), Translator('en'))
        self.assertEqual(solar, '2024-02-10 · Saturday')
        self.assertEqual(lunar, 'Chinese lunar: 2024-01-01')
        solar, lunar = calendar.calendar_lines(date(2025, 7, 25), Translator('zh'))
        self.assertEqual(solar, '2025-07-25 · 星期五')
        self.assertEqual(lunar, '农历：2025年6月1日（闰月）')
        self.assertIn('2025-01-01', calendar.calendar_lines(date(2025, 1, 29), Translator('en'))[1])

    def test_all_languages_and_graceful_failure(self):
        for language in ('en','zh','ko','ja','th','de','es'):
            translator = Translator(language)
            solar, lunar = calendar.calendar_lines(date(2024, 2, 10), translator)
            self.assertIn(translator('weekday_5'), solar)
            self.assertNotEqual(lunar, translator('calendar_lunar_unavailable'))
            with mock.patch.object(calendar.Solar, 'fromYmd', side_effect=ValueError):
                self.assertEqual(calendar.calendar_lines(date(2024, 2, 10), translator)[1], translator('calendar_lunar_unavailable'))
