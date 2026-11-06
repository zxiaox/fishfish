"""Non-blocking Windows playback of bundled, opt-in game sounds."""
import sys
from pathlib import Path

class SoundPlayer:
    def __init__(self, directory):
        self.directory = Path(directory)

    def play(self, name):
        if sys.platform != 'win32': return
        if name not in {'success','failure', *(f'{voice}_{cue}' for voice in ('female1','female2','male') for cue in ('choose','door1','door2','door3'))}:
            raise ValueError('Invalid sound')
        import winsound
        try: winsound.PlaySound(str(self.directory / (name + '.wav')), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
        except (OSError, RuntimeError): pass

    def stop(self):
        if sys.platform == 'win32':
            import winsound
            try: winsound.PlaySound(None, 0)
            except (OSError, RuntimeError): pass
