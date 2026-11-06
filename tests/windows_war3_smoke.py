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
    # The shared selected indicator is a checkmark and remains available after theme changes.
    unchecked, checked = root._fishfish_check_images
    assert checked.get(5, 9) == (255, 255, 255)
    assert checked.get(2, 2) != unchecked.get(2, 2)
    app.set_theme('dark'); app.set_theme('light')
    assert checked.get(5, 9) == (255, 255, 255)
    assert app.connection_mode == 'direct'
    app.server_host='example.test'; app.server_port=47653; app.fingerprint='a'*64; app.save()
    app.open_settings()
    def descendants(widget):
        result=[]
        for child in widget.winfo_children(): result.append(child); result.extend(descendants(child))
        return result
    radio=next(w for w in descendants(app.dialog) if isinstance(w, __import__('tkinter').ttk.Radiobutton) and w.cget('value') == 'zerotier')
    radio.invoke()
    assert app.dialog.winfo_exists()
    entries=[w for w in descendants(app.dialog) if isinstance(w, __import__('tkinter').ttk.Entry)]
    entries[0].delete(0,'end'); entries[0].insert(0,'10.147.17.2')
    entries[2].delete(0,'end'); entries[2].insert(0,'b'*64)
    app.connect=lambda: None
    confirm=next(w for w in descendants(app.dialog) if isinstance(w, __import__('tkinter').ttk.Button) and w.cget('text') == app.tr('confirm'))
    confirm.invoke()
    assert app.connection_mode == 'zerotier', app.connection_mode
    assert app.server_host == '10.147.17.2', app.server_host
    assert app.profiles['direct']['server_host'] == 'example.test', app.profiles
    stored=module.load_settings(module.APP)
    assert stored['connection_mode'] == 'zerotier'
    assert stored['connection_profiles']['direct']['server_host'] == 'example.test'
    assert stored['connection_profiles']['zerotier']['server_host'] == '10.147.17.2'
    class FakeClient:
        def stop(self): pass
    # A lobby update may arrive before the worker's client-ready event.
    app.events.put((app.generation, 'lobbies', '1'))
    app.events.put((app.generation, 'local_found', 'Test Lobby'))
    app.events.put((app.generation, 'client_ready', FakeClient()))
    app.poll()
    assert '1' in app.status.get(), app.status.get()
    assert 'Test Lobby' in app.discovery.get(), app.discovery.get()
    app.retry_enabled = False
    app.scan_stats.update({'server_id':'old-server', 'peers':2, 'queries':42})
    old_generation = app.generation
    app.events.put((old_generation, 'error', 'timed out'))
    app.events.put((old_generation, 'scan_stats', {'server_id':'old-server', 'peers':2}))
    app.poll()
    assert app.scan_stats['server_id'] == 'unknown', app.scan_stats
    assert app.scan_stats['peers'] == 0, app.scan_stats
    assert app.discovery.get() == app.tr('war_local_offline'), app.discovery.get()
    app.close()
print('War3 Battle Platform Windows UI startup passed.')
