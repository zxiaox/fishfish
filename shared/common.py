"""Cross-platform application services; UI and platform integrations stay at the edge."""
import json
import os
import sys
import threading
import urllib.request
import webbrowser
from pathlib import Path

VERSIONS = {'work-motivator': '1.0.4', 'monty-hall': '1.0.14', 'war3-battle-platform': '1.0.9'}
LANGUAGES = {'English': 'en', '简体中文': 'zh', '한국어': 'ko', '日本語': 'ja', 'ไทย': 'th', 'Deutsch': 'de', 'Español': 'es'}
REPO = 'zxiaox/fishfish'


def resource_root():
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent))


def config_dir(app_id):
    root = Path(os.environ.get('APPDATA', Path.home() / '.config')) if sys.platform == 'win32' else Path.home() / '.config'
    directory = root / 'fishfish' / app_id
    directory.mkdir(parents=True, exist_ok=True)
    return directory


class Translator:
    def __init__(self, code='en'):
        self.code = code if code in LANGUAGES.values() else 'en'
        directory = resource_root() / 'shared' / 'locales'
        self.fallback = json.loads((directory / 'en.json').read_text(encoding='utf-8'))
        self.messages = json.loads((directory / (self.code + '.json')).read_text(encoding='utf-8'))

    def __call__(self, key, **kwargs):
        return self.messages.get(key, self.fallback.get(key, key)).format(**kwargs)


def load_settings(app_id):
    try:
        return json.loads((config_dir(app_id) / 'settings.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def save_settings(app_id, settings):
    path = config_dir(app_id) / 'settings.json'
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)


def language_picker(parent, current, callback):
    from tkinter import ttk
    name = next((k for k, v in LANGUAGES.items() if v == current), 'English')
    box = ttk.Combobox(parent, values=list(LANGUAGES), state='readonly', width=16)
    box.set(name)
    box.bind('<<ComboboxSelected>>', lambda event: callback(LANGUAGES[box.get()]))
    box.pack(side='right', padx=5)


def find_latest(releases, app_id, current=None):
    current = current or VERSIONS[app_id]
    prefix = app_id + '-v'
    def parse(s):
        parts = s.split('.')
        if len(parts) != 3 or any(not p.isascii() or not p.isdigit() for p in parts):
            return None
        return tuple(map(int, parts))
    current_version = parse(current)
    candidates = []
    for release in releases:
        tag = release.get('tag_name', '')
        if release.get('draft') or release.get('prerelease') or not tag.startswith(prefix):
            continue
        version = parse(tag[len(prefix):])
        url = release.get('html_url', '')
        expected = 'https://github.com/' + REPO + '/releases/tag/' + tag
        if version and version > current_version and url == expected:
            candidates.append((version, url))
    return max(candidates, default=None)




def apply_theme(root, theme):
    from tkinter import ttk
    dark = theme == 'dark'
    bg, fg, field = ('#20252d', '#f5f5f5', '#343b46') if dark else ('#f3f5f6', '#17212b', '#ffffff')
    style = ttk.Style(root)
    style.theme_use('clam')
    root.configure(background=bg)
    style.configure('.', background=bg, foreground=fg, fieldbackground=field)
    # The clam theme uses a cross for checked boxes on some platforms. Draw a
    # consistent checkmark and retain the images on the root for Tk's lifetime.
    import tkinter as tk
    if not hasattr(root, '_fishfish_check_images'):
        unchecked, checked = tk.PhotoImage(master=root, width=16, height=16), tk.PhotoImage(master=root, width=16, height=16)
        root._fishfish_check_images = (unchecked, checked)
        style.element_create('Fishfish.indicator', 'image', unchecked,
                             ('selected', checked), width=20, sticky='w')
    unchecked, checked = root._fishfish_check_images
    for image in (unchecked, checked):
        image.put(bg, to=(0, 0, 16, 16))
        image.put('#98a8a0' if dark else '#84928a', to=(1, 1, 15, 15))
        image.put(field, to=(2, 2, 14, 14))
    checked.put('#328b57' if dark else '#217a45', to=(2, 2, 14, 14))
    for x, y in ((4, 8), (5, 9), (6, 10), (7, 9), (8, 8), (9, 7), (10, 6), (11, 5)):
        checked.put('#ffffff', to=(x, y, x + 2, y + 2))
    style.layout('TCheckbutton', [('Checkbutton.padding', {'sticky': 'nswe', 'children': [
        ('Fishfish.indicator', {'side': 'left', 'sticky': 'w'}),
        ('Checkbutton.focus', {'side': 'left', 'sticky': 'w', 'children': [
            ('Checkbutton.label', {'sticky': 'nswe'})]})]})])
    style.configure('TCheckbutton', background=bg, foreground=fg)
    style.map('TCheckbutton', background=[('active', bg)], foreground=[('disabled', '#909d95')])
    style.configure('TFrame', background=bg)
    style.configure('TLabel', background=bg, foreground=fg)
    style.configure('TButton', background=field, foreground=fg)
    style.map('TButton', background=[('active', '#637e89')])
    style.configure('Treeview', background=field, fieldbackground=field, foreground=fg)
    style.configure('Treeview.Heading', background=field, foreground=fg)
    style.configure('Work.Horizontal.TProgressbar', background='#28a745', troughcolor=field, borderwidth=0, thickness=16)
    style.configure('Earnings.TLabel', background=bg, foreground='#42b86e' if dark else '#08782e', font=('', 22, 'bold'))


def set_app_icon(root, app_id):
    if sys.platform == 'win32':
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('zxiaox.fishfish.' + app_id)
    root.iconphoto(True, __import__('tkinter').PhotoImage(file=str(resource_root() / 'assets' / (app_id + '.png'))))


def settings_menu(root, tr, current_theme, set_language, set_theme, check_update, app_settings=None, app_settings_label=None):
    """Install a native top-left Settings menu shared by every app."""
    import tkinter as tk
    menubar = tk.Menu(root)
    menu = tk.Menu(menubar, tearoff=False)
    if app_settings:
        menu.add_command(label=app_settings_label or tr('work_config'), command=app_settings)
        menu.add_separator()
    languages = tk.Menu(menu, tearoff=False)
    for name, code in LANGUAGES.items():
        languages.add_command(label=('✓ ' if code == tr.code else '') + name,
                              command=lambda code=code: set_language(code))
    menu.add_cascade(label=tr('language'), menu=languages)
    themes = tk.Menu(menu, tearoff=False)
    for key in ('light', 'dark'):
        themes.add_command(label=('✓ ' if key == current_theme else '') + tr(key),
                           command=lambda key=key: set_theme(key))
    menu.add_cascade(label=tr('theme'), menu=themes)
    menu.add_separator()
    menu.add_command(label=tr('check_updates'), command=check_update)
    menubar.add_cascade(label=tr('settings'), menu=menu)
    root.config(menu=menubar)
    return menubar
