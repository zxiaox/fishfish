"""Non-blocking playback of bundled cues and installed Windows voices."""
import base64
import json
import queue
import subprocess
import sys
import threading
from pathlib import Path

# Receives fixed, application-owned text as UTF-8 JSON, never as shell code.
_WINDOWS_SPEECH = r'''
$ErrorActionPreference = 'Stop'
try {
  $reader = [System.IO.StreamReader]::new([Console]::OpenStandardInput(), [System.Text.Encoding]::UTF8)
  $request = $reader.ReadToEnd() | ConvertFrom-Json
  Add-Type -AssemblyName System.Speech
  $synth = [System.Speech.Synthesis.SpeechSynthesizer]::new()
  $voices = @($synth.GetInstalledVoices() | Where-Object { $_.Enabled -and $_.VoiceInfo.Culture.TwoLetterISOLanguageName -eq $request.language })
  if ($voices.Count -eq 0) { exit 2 }
  $preferred = @($voices | Where-Object { $_.VoiceInfo.Gender.ToString() -eq $request.gender })
  if ($preferred.Count -gt 0) { $synth.SelectVoice($preferred[0].VoiceInfo.Name) }
  else { $synth.SelectVoice($voices[0].VoiceInfo.Name) }
  $synth.Speak([string]$request.text)
  $synth.Dispose()
} catch { exit 3 }
'''

class SoundPlayer:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.events = queue.Queue()
        self._process = None
        self._lock = threading.Lock()
        self._generation = 0

    def play(self, name, fallback_text=None):
        if sys.platform != 'win32': return
        voices = ('female1', 'female2', 'male')
        cues = ('choose', 'door1', 'door2', 'door3')
        languages = ('zh', 'ko', 'ja', 'th', 'de', 'es')
        valid = {'success', 'failure'} | {f'{voice}_{cue}' for voice in voices for cue in cues}
        valid |= {f'{lang}_{voice}_{cue}' for lang in languages for voice in voices for cue in cues}
        if name not in valid: raise ValueError('Invalid sound')
        self.stop()
        path = self.directory / (name + '.wav')
        if path.is_file():
            import winsound
            try: winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
            except (OSError, RuntimeError): pass
            return
        parts = name.split('_')
        if len(parts) != 3 or not fallback_text: return
        language, voice, _ = parts
        payload = json.dumps({'language':language, 'gender':'Male' if voice == 'male' else 'Female', 'text':fallback_text}, ensure_ascii=False).encode('utf-8')
        encoded = base64.b64encode(_WINDOWS_SPEECH.encode('utf-16-le')).decode('ascii')
        try:
            process = subprocess.Popen(['powershell.exe', '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded], stdin=subprocess.PIPE,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except OSError:
            self.events.put(('speech_unavailable', language)); return
        with self._lock:
            self._process = process
            generation = self._generation
        def wait_for_speech():
            try: process.communicate(input=payload)
            except (OSError, ValueError): pass
            with self._lock:
                current = self._generation == generation and self._process is process
                if current: self._process = None
            if current and process.returncode:
                self.events.put(('speech_unavailable', language))
        threading.Thread(target=wait_for_speech, daemon=True).start()

    def stop(self):
        with self._lock:
            self._generation += 1
            process, self._process = self._process, None
        if process:
            try: process.terminate()
            except OSError: pass
        if sys.platform == 'win32':
            import winsound
            try: winsound.PlaySound(None, 0)
            except (OSError, RuntimeError): pass
