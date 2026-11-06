"""Exercise Work Motivator's real settings and persisted countdown on Windows."""
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import time
import tkinter as tk
from tkinter import ttk

with tempfile.TemporaryDirectory() as directory:
    os.environ['APPDATA'] = directory
    app_dir = Path('apps/work-motivator').resolve(); sys.path.insert(0, str(app_dir))
    spec = importlib.util.spec_from_file_location('work_app', app_dir / 'main.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    root = tk.Tk(); app = module.App(root); root.update_idletasks()
    assert not app.countdown_enabled and app.countdown_duration == '05:00:00'
    app.open_settings()
    def descendants(widget):
        result = []
        for child in widget.winfo_children(): result.append(child); result.extend(descendants(child))
        return result
    def find_button(text): return next(w for w in descendants(app.dialog) if isinstance(w, ttk.Button) and w.cget('text') == app.tr(text))
    def find_check(text): return next(w for w in descendants(app.dialog) if isinstance(w, ttk.Checkbutton) and w.cget('text') == app.tr(text))
    find_check('countdown_enable').invoke()
    start = time.time(); find_button('confirm').invoke()
    assert app.countdown_enabled and 17995 <= app.countdown_deadline - start <= 18005
    first = app.countdown_deadline
    stored = module.load_settings(module.APP)
    assert stored['countdown_deadline'] == first and stored['countdown_duration'] == '05:00:00'
    app.open_settings(); find_button('confirm').invoke(); assert app.countdown_deadline == first
    app.open_settings()
    entries = [w for w in descendants(app.dialog) if isinstance(w, ttk.Entry)]
    entries[-1].delete(0, 'end'); entries[-1].insert(0, '00:10:00')
    start = time.time(); find_button('confirm').invoke()
    assert 595 <= app.countdown_deadline - start <= 605
    app.open_settings(); find_check('countdown_enable').invoke(); find_button('confirm').invoke()
    assert not app.countdown_enabled and app.countdown_deadline is None
    app.close()
print('Work Motivator countdown Windows interaction passed.')
