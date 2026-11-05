"""Windows UI startup smoke test; does not require a Warcraft installation."""
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import tkinter as tk

with tempfile.TemporaryDirectory() as directory:
    os.environ['APPDATA'] = directory
    app_dir = Path('apps/war3-battle-platform').resolve()
    sys.path.insert(0, str(app_dir))
    spec = importlib.util.spec_from_file_location('war3_app', app_dir / 'main.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    root = tk.Tk()
    app = module.App(root)
    root.update_idletasks()
    assert root.title() == app.tr('war_title')
    assert root['menu'], 'Settings menu missing'
    assert app.connect_button.winfo_exists()
    class FakeClient:
        def stop(self): pass
    # A lobby update may arrive before the worker's client-ready event.
    app.events.put((app.generation, 'lobbies', '1'))
    app.events.put((app.generation, 'local_found', 'Test Lobby'))
    app.events.put((app.generation, 'client_ready', FakeClient()))
    app.poll()
    assert '1' in app.status.get(), app.status.get()
    assert 'Test Lobby' in app.discovery.get(), app.discovery.get()
    app.close()
print('War3 Battle Platform Windows UI startup passed.')
