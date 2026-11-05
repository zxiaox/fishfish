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
    app.close()
print('War3 Battle Platform Windows UI startup passed.')
