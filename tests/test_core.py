import json
import hashlib
import struct
import tempfile
import random
import string
import unittest
from datetime import datetime
from pathlib import Path
from shared.common import find_latest
from shared.core import trial, work_status, work_interval, observed_work_by_day, prepare_live_rounds, choose_live_door, finish_live_round
from shared.updater import asset_details, check_url, verify
from shared.history import load_history, save_history, add_experiment, limit_live_rounds
from shared.session_record import create_game_records, append_round

class Tests(unittest.TestCase):
    def test_work_bounds_and_precision(self):
        d = lambda h,m,s=0,us=0: datetime(2026, 1, 1, h,m,s,us)
        self.assertEqual(work_status(d(8,0), '09:00','17:00','18')[1], 0)
        remaining, earned, progress = work_status(d(10,30,0,500000), '09:00','17:00','18')
        self.assertAlmostEqual(remaining, 23399.5)
        self.assertAlmostEqual(float(earned), 27.0025)
        self.assertAlmostEqual(progress, 5400.5 / 28800)
        self.assertEqual(work_status(d(18,0), '09:00','17:00','18')[0], 0)
        self.assertEqual(work_status(d(18,0), '09:00','17:00','18')[1], 144)
        for end, wage in [('09:00','1'),('17:00','NaN'),('17:00','-1')]:
            with self.assertRaises(ValueError): work_status(d(10,0),'09:00',end,wage)

    def test_overnight_shift_and_month_rollover(self):
        start, end, wage = '22:00', '06:00', '18'
        remaining, earned, progress = work_status(datetime(2026, 2, 1, 1), start, end, wage)
        self.assertEqual(remaining, 5 * 3600)
        self.assertEqual(earned, 54)
        self.assertEqual(progress, 3 / 8)
        self.assertEqual(work_interval(datetime(2026, 2, 1, 1), start, end)[0], datetime(2026, 1, 31, 22))
        self.assertEqual(work_status(datetime(2026, 2, 1, 6), start, end, wage)[1], 144)
        self.assertEqual(work_status(datetime(2026, 2, 1, 21), start, end, wage)[1], 0)
        result = observed_work_by_day(datetime(2026, 1, 31, 23, 59, 59, 500000), datetime(2026, 2, 1, 0, 0, 0, 500000), start, end, 1)
        self.assertEqual(result, {'2026-01-31': .5, '2026-02-01': .5})
        result = observed_work_by_day(datetime(2026, 2, 1, 5, 59, 59, 500000), datetime(2026, 2, 1, 6, 0, 0, 500000), start, end, 1)
        self.assertEqual(result, {'2026-02-01': .5})
        self.assertEqual(observed_work_by_day(datetime(2026, 2, 1, 7), datetime(2026, 2, 1, 7, 0, 1), start, end, 1), {})

    def test_monty_rules_and_distribution(self):
        rng = random.Random(9)
        for strategy in ('stay','switch'):
            records = [trial(strategy, rng) for _ in range(12000)]
            for r in records:
                self.assertNotIn(r['revealed'], (r['choice'], r['prize']))
                self.assertEqual(r['final'] == r['choice'], strategy == 'stay')
                self.assertEqual(r['won'], r['final'] == r['prize'])
            rate = sum(r['won'] for r in records) / len(records)
            self.assertAlmostEqual(rate, 2/3 if strategy == 'switch' else 1/3, delta=.025)

    def test_live_rounds_are_precommitted_and_consistent(self):
        rounds = prepare_live_rounds(20, random.Random(17))
        self.assertEqual(len(rounds), 20)
        for game in rounds:
            for door in (1, 2, 3):
                selected = choose_live_door(game, door, random.Random(door))
                self.assertNotIn(selected['revealed'], (selected['prize'], door))
                for strategy in ('stay', 'switch'):
                    result = finish_live_round(selected, strategy)
                    self.assertEqual(result['prize'], game['prize'])
                    self.assertEqual(result['won'], result['final'] == game['prize'])
                    self.assertEqual(result['final'] == door, strategy == 'stay')
        for count in (0, 21):
            with self.assertRaises(ValueError): prepare_live_rounds(count)

    def test_history_persists_and_limits_experiments(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'history.json'
            history = load_history(path)
            for index in range(55):
                add_experiment(history, {'date': str(index), 'strategy': 'switch', 'trials': 2, 'wins': 1, 'losses': 1})
            live = {'date': '2026-11-04', 'record_path': 'layout.txt', 'rounds': [finish_live_round(choose_live_door(prepare_live_rounds(1, random.Random(3))[0], 1), 'stay')]}
            history['live_sessions'].append(live)
            save_history(path, history)
            restored = load_history(path)
            self.assertEqual(len(restored['experiments']), 50)
            self.assertEqual(restored['experiments'][0]['date'], '5')
            self.assertEqual(restored['live_sessions'], [live])
            path.write_text('{bad json', encoding='utf-8')
            with self.assertRaises(ValueError): load_history(path)
            self.assertEqual(path.read_text(encoding='utf-8'), '{bad json')

    def test_game_text_records_preserve_precommitted_layout(self):
        with tempfile.TemporaryDirectory() as directory:
            session = Path(directory) / 'three-door-time-test.txt'
            create_game_records(session, 'Round 1 — 1: Empty, 2: Prize, 3: Empty\n', 'Game session\n')
            original = session.read_text(encoding='utf-8')
            self.assertIn('2: Prize', original)
            append_round(session, 'Round 1: initial 1, opened 3, switch, final 2, prize 2, win.')
            self.assertTrue(session.read_text(encoding='utf-8').startswith(original))
            self.assertIn('final 2', session.read_text(encoding='utf-8'))
            self.assertEqual([p.name for p in Path(directory).iterdir()], [session.name])
            with self.assertRaises(FileExistsError): create_game_records(session, 'replacement', 'replacement')
            self.assertTrue(session.read_text(encoding='utf-8').startswith(original))

    def test_live_history_limits_round_entries(self):
        sessions = [{'date': str(i), 'rounds': [{'n': i * 20 + j} for j in range(20)]} for i in range(4)]
        limit_live_rounds(sessions)
        entries = [r['n'] for session in sessions for r in session['rounds']]
        self.assertEqual(entries, list(range(30, 80)))

    def test_release_selection(self):
        def release(tag, **kw):
            return {'tag_name': tag, 'html_url': 'https://github.com/zxiaox/fishfish/releases/tag/' + tag, **kw}
        releases = [release('work-motivator-v1.2.0'), release('monty-hall-v9.0.0'), release('work-motivator-v1.10.0'), release('work-motivator-v2.0.0', prerelease=True)]
        self.assertEqual(find_latest(releases, 'work-motivator', '1.0.0')[0], (1,10,0))
        self.assertIsNone(find_latest(releases, 'work-motivator', '1.10.0'))
        bad = release('work-motivator-v3.0.0'); bad['html_url'] = 'https://evil.example/'
        self.assertIsNone(find_latest([bad], 'work-motivator'))

    def test_update_asset_validation(self):
        app = 'monty-hall'; tag = app + '-v1.1.0'
        prefix = f'https://github.com/zxiaox/fishfish/releases/download/{tag}/'
        release = {'tag_name': tag, 'assets': [
            {'name': app + '.exe', 'browser_download_url': prefix + app + '.exe', 'size': 128},
            {'name': app + '.exe.sha256', 'browser_download_url': prefix + app + '.exe.sha256'}]}
        asset_details(release, app)
        release['assets'][0]['browser_download_url'] = 'https://evil.example/app.exe'
        with self.assertRaises(ValueError): asset_details(release, app)
        for url in ('http://github.com/a', 'https://github.com.evil.example/a', 'https://user@github.com/a'):
            with self.assertRaises(ValueError): check_url(url)

    def test_update_executable_verification(self):
        data = bytearray(128); data[:2] = b'MZ'; struct.pack_into('<I', data, 0x3c, 64)
        data[64:70] = b'PE\0\0\x64\x86'
        digest = hashlib.sha256(data).hexdigest()
        verify(data, len(data), digest)
        with self.assertRaises(ValueError): verify(data, len(data) - 1, digest)
        with self.assertRaises(ValueError): verify(data, len(data), '0' * 64)
        data[68] = 0
        with self.assertRaises(ValueError): verify(data, len(data), hashlib.sha256(data).hexdigest())

    def test_locale_keys_and_placeholders(self):
        paths = sorted(Path('shared/locales').glob('*.json'))
        self.assertEqual(len(paths), 7)
        english = json.loads(Path('shared/locales/en.json').read_text(encoding='utf-8'))
        formatter = string.Formatter()
        fields = lambda s: {name for _, name, _, _ in formatter.parse(s) if name}
        for path in paths:
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(set(data), set(english), path)
            for key in english: self.assertEqual(fields(data[key]), fields(english[key]), (path, key))

if __name__ == '__main__': unittest.main()
