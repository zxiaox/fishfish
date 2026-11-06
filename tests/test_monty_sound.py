import importlib.util
import json
import queue
from pathlib import Path
import unittest
from unittest import mock
import wave

spec = importlib.util.spec_from_file_location('monty_sound', Path('apps/monty-hall/sound.py'))
sound = importlib.util.module_from_spec(spec); spec.loader.exec_module(sound)

class SoundTests(unittest.TestCase):
    def test_audio_pack_is_complete_and_valid(self):
        root = Path('assets/monty-hall-game/audio')
        names = {'success', 'failure'} | {f'{voice}_{cue}' for voice in ('female1','female2','male') for cue in ('choose','door1','door2','door3')}
        names |= {f'{lang}_{voice}_{cue}' for lang in ('zh','ko') for voice in ('female1','female2','male') for cue in ('choose','door1','door2','door3')}
        for name in names:
            with self.subTest(name=name), wave.open(str(root / (name + '.wav')), 'rb') as audio:
                self.assertEqual((audio.getnchannels(), audio.getsampwidth(), audio.getframerate()), (1, 2, 22050))
                self.assertGreater(audio.getnframes(), 1000)
    def test_installed_voice_fallback_uses_language_and_reports_missing_voice(self):
        player = sound.SoundPlayer('assets/monty-hall-game/audio')
        winsound = mock.Mock(SND_FILENAME=1, SND_ASYNC=2, SND_NODEFAULT=4)
        proc = mock.Mock(returncode=2)
        with mock.patch.object(sound.sys, 'platform', 'win32'), mock.patch.dict('sys.modules', {'winsound':winsound}), mock.patch.object(sound.subprocess, 'Popen', return_value=proc):
            player.play('ja_male_door2', fallback_text='二番のドアを除外しました。')
            self.assertEqual(player.events.get(timeout=3), ('speech_unavailable', 'ja'))
            payload = json.loads(proc.communicate.call_args.kwargs['input'].decode('utf-8'))
            self.assertEqual(payload['language'], 'ja')
            self.assertEqual(payload['gender'], 'Male')
            self.assertIn('二番', payload['text'])

    def test_windows_playback_and_stop(self):
        player = sound.SoundPlayer('assets/monty-hall-game/audio')
        winsound = mock.Mock(SND_FILENAME=1, SND_ASYNC=2, SND_NODEFAULT=4)
        with mock.patch.object(sound.sys, 'platform', 'win32'), mock.patch.dict('sys.modules', {'winsound':winsound}):
            player.play('male_door2'); winsound.PlaySound.assert_called_with(str(player.directory/'male_door2.wav'), 7)
            player.play('zh_female2_door3'); winsound.PlaySound.assert_called_with(str(player.directory/'zh_female2_door3.wav'), 7)
            player.stop(); winsound.PlaySound.assert_called_with(None, 0)
            with self.assertRaises(ValueError): player.play('../outside')
