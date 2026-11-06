"""Exercise the real Tk controls and single-file session on Windows."""
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import tkinter as tk

with tempfile.TemporaryDirectory() as directory:
    os.environ['APPDATA'] = directory
    app_dir = Path('apps/monty-hall').resolve()
    sys.path.insert(0, str(app_dir))
    spec = importlib.util.spec_from_file_location('monty_app', app_dir / 'main.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    record = Path(directory) / 'rounds.txt'
    module.filedialog.asksaveasfilename = lambda **kwargs: str(record)
    module.messagebox.showinfo = lambda *args, **kwargs: None
    root = tk.Tk(); app = module.App(root); root.update_idletasks()
    app.round_count.set('2'); app.start_button.invoke()
    assert app.phase == 'pick'
    assert str(app.host_image.cget('image')) == str(app.game_images['host_welcome'])
    assert all(str(b.cget('image')) == str(app.game_images['doors_closed']) for b in app.door_buttons)
    assert len(list(Path(directory).glob('*.txt'))) == 1
    before = record.read_text(encoding='utf-8')
    assert before.count(app.tr('round_label', number=1)) == 1
    app.door_buttons[0].invoke()
    assert app.phase == 'choose'
    assert str(app.host_image.cget('image')) == str(app.game_images['host_thinking'])
    assert all(str(b.cget('image')) == str(app.game_images['doors_closed']) for b in app.door_buttons)
    assert app.rounds[0]['choice'] == 1
    assert app.rounds[0]['revealed'] not in (1, app.rounds[0]['prize'])
    app.switch_button.invoke()
    assert app.phase == 'result' and len(app.results) == 1
    result = app.results[-1]
    assert str(app.host_image.cget('image')) == str(app.game_images['host_win' if result['won'] else 'host_loss'])
    assert str(app.door_buttons[result['final']-1].cget('image')) == str(app.game_images['doors_treasure' if result['won'] else 'doors_empty'])
    assert all(str(b.cget('image')) == str(app.game_images['doors_closed']) for i,b in enumerate(app.door_buttons, 1) if i != result['final'])
    assert record.read_text(encoding='utf-8').startswith(before)
    assert len(module.load_history(app.history_path)['live_sessions'][0]['rounds']) == 1
    app.next_button.invoke(); assert app.phase == 'pick'
    app.set_theme('dark'); app.set_theme('light')
    app.door_buttons[1].invoke(); app.stay_button.invoke()
    assert len(app.live_table.get_children()) == 2
    assert len(list(Path(directory).glob('*.txt'))) == 1
    app.close()
print('Three Doors Windows interaction passed.')
