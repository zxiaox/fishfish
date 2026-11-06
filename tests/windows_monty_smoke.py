"""Exercise the real Tk controls and single-file session on Windows."""
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import queue
import tkinter as tk

with tempfile.TemporaryDirectory() as directory:
    os.environ['APPDATA'] = directory
    app_dir = Path('apps/monty-hall').resolve()
    sys.path.insert(0, str(app_dir))
    spec = importlib.util.spec_from_file_location('monty_app', app_dir / 'main.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    record = Path(directory) / 'rounds.txt'
    module.filedialog.asksaveasfilename = lambda **kwargs: str(record)
    info_messages = []
    module.messagebox.showinfo = lambda *args, **kwargs: info_messages.append((args, kwargs))
    root = tk.Tk(); app = module.App(root); root.update_idletasks()
    class FakeSounds:
        def __init__(self): self.calls = []; self.events = queue.Queue()
        def play(self, name, fallback_text=None): self.calls.append(name)
        def stop(self): self.calls.append('stop')
    app.sound_player = FakeSounds()
    warnings = []; module.messagebox.showwarning = lambda *args, **kwargs: warnings.append((args, kwargs))
    app.sound_player.events.put(('speech_unavailable', 'en')); app.poll_sound()
    assert len(warnings) == 1
    app.sound_player.events.put(('speech_unavailable', 'en')); app.poll_sound()
    assert len(warnings) == 1
    assert app.phase == 'idle' and all('disabled' not in b.state() for b in app.door_buttons)
    app.door_buttons[0].invoke(); assert app.phase == 'idle'
    assert app.host == 'host2'
    for lang in ('en','zh','ko','ja','th','de','es'):
        app.tr = module.Translator(lang)
        for host, voice in (('host1','female1'),('host2','female2'),('host3','male')):
            app.host = host
            for cue in ('choose','door1','door2','door3'):
                app.play_sound(cue)
                assert app.sound_player.calls[-1] == ('' if lang == 'en' else lang + '_') + voice + '_' + cue
    app.host = 'host2'; app.tr = module.Translator('en')
    assert app.game_images['host_welcome'].width() == 200
    assert app.game_images['host2_welcome'].width() == 200
    app.host_choice.current(0); app.change_host()
    assert module.load_settings(module.APP)['host'] == 'host1'
    def shown(widget): return str(root.tk.splitlist(widget.cget('image'))[0])
    app.round_count.set('2'); app.start_button.invoke()
    assert app.phase == 'pick' and all('disabled' not in b.state() for b in app.door_buttons)
    assert app.sound_player.calls[-1] == 'female1_choose'
    assert not info_messages, 'Starting a saved session should not show a confirmation popup'
    assert shown(app.host_image) == str(app.game_images['host_welcome'])
    assert all(shown(b) == str(app.game_images['doors_closed']) for b in app.door_buttons)
    assert len(list(Path(directory).glob('*.txt'))) == 1
    before = record.read_text(encoding='utf-8')
    assert before.count(app.tr('round_label', number=1)) == 1
    first_choice = app.rounds[0]['prize']
    app.door_buttons[first_choice-1].invoke()
    assert app.phase == 'choose'
    assert shown(app.host_image) == str(app.game_images['host_thinking'])
    revealed = app.rounds[0]['revealed']
    assert app.sound_player.calls[-1] == 'female1_door' + str(revealed)
    assert shown(app.door_buttons[revealed-1]) == str(app.game_images['doors_empty'])
    def assert_revealed_label():
        label = str(app.door_buttons[revealed-1].cget('text'))
        assert app.tr('door_number', number=revealed) in label
        assert app.tr('empty') in label and app.tr('eliminated_by_host') in label
    for lang in ('en', 'zh', 'ko', 'ja', 'th', 'de', 'es'):
        app.set_language(lang); assert_revealed_label()
    app.set_language('en')
    assert_revealed_label()
    assert all(shown(b) == str(app.game_images['doors_closed']) for i,b in enumerate(app.door_buttons, 1) if i != revealed)
    app.host_choice.current(1); app.change_host()
    assert app.host == 'host2' and module.load_settings(module.APP)['host'] == 'host2'
    assert shown(app.host_image) == str(app.game_images['host2_thinking'])
    app.host_choice.current(2); app.change_host()
    assert app.host == 'host3' and module.load_settings(module.APP)['host'] == 'host3'
    assert shown(app.host_image) == str(app.game_images['host3_thinking'])
    app.play_sound('choose'); assert app.sound_player.calls[-1] == 'male_choose'
    app.sound_enabled.set(False); app.change_sound(); before_calls = list(app.sound_player.calls)
    app.play_sound('choose'); assert app.sound_player.calls == before_calls
    app.sound_enabled.set(True); app.change_sound()
    app.host_choice.current(0); app.change_host()
    assert app.rounds[0]['choice'] == first_choice
    assert app.rounds[0]['revealed'] not in (first_choice, app.rounds[0]['prize'])
    assert all('disabled' not in button.state() for button in app.door_buttons)
    app.door_buttons[revealed-1].invoke()
    assert app.phase == 'choose' and app.rounds[0]['choice'] == first_choice
    app.switch_button.invoke()
    assert app.phase == 'result' and len(app.results) == 1
    assert all('disabled' not in b.state() for b in app.door_buttons)
    app.door_buttons[0].invoke(); assert app.phase == 'result' and len(app.results) == 1
    result = app.results[-1]
    assert app.sound_player.calls[-1] == ('success' if result['won'] else 'failure')
    assert shown(app.host_image) == str(app.game_images['host_win' if result['won'] else 'host_loss'])
    assert shown(app.door_buttons[result['final']-1]) == str(app.game_images['doors_treasure' if result['won'] else 'doors_empty'])
    assert shown(app.door_buttons[result['revealed']-1]) == str(app.game_images['doors_empty'])
    assert_revealed_label()
    assert not result['won']
    assert shown(app.door_buttons[result['prize']-1]) == str(app.game_images['doors_treasure'])
    assert record.read_text(encoding='utf-8').startswith(before)
    assert len(module.load_history(app.history_path)['live_sessions'][0]['rounds']) == 1
    app.next_button.invoke(); assert app.phase == 'pick'
    app.set_theme('dark'); app.set_theme('light')
    winning_choice = app.rounds[1]['prize']
    app.door_buttons[winning_choice-1].invoke(); app.stay_button.invoke()
    assert app.results[-1]['won']
    assert shown(app.door_buttons[winning_choice-1]) == str(app.game_images['doors_treasure'])
    assert len(app.live_table.get_children()) == 2
    assert len(list(Path(directory).glob('*.txt'))) == 1
    app.close()
print('Three Doors Windows interaction passed.')
