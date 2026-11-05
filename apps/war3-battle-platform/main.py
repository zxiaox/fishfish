import queue
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import tkinter as tk
from tkinter import ttk, filedialog
from shared import dialogs as messagebox
from shared.common import Translator, load_settings, save_settings, settings_menu, apply_theme, set_app_icon
from shared.updater import check_updates, helper_mode, cleanup_mode
from network import Bridge

APP = 'war3-battle-platform'


class App:
    def __init__(self, root):
        self.root = root; self.settings = load_settings(APP)
        self.tr = Translator(self.settings.get('language', 'en')); self.theme = self.settings.get('theme', 'light')
        self.host = tk.StringVar(value=self.settings.get('host', ''))
        self.game = tk.StringVar(value=self.settings.get('game', 'TFT'))
        self.version = tk.StringVar(value=self.settings.get('version', '1.26'))
        self.path = tk.StringVar(value=self.settings.get('path', ''))
        self.status = tk.StringVar(); self.events = queue.Queue(); self.bridge = None; self.generation = 0
        set_app_icon(root, APP); self.build(); self.set_status('war_idle'); root.protocol('WM_DELETE_WINDOW', self.close)
        root.after(100, self.poll)

    def build(self):
        for widget in self.root.winfo_children(): widget.destroy()
        self.root._fishfish_language = self.tr.code; apply_theme(self.root, self.theme)
        self.root.title(self.tr('war_title')); self.root.geometry('720x550'); self.root.minsize(640, 480)
        settings_menu(self.root, self.tr, self.theme, self.set_language, self.set_theme, lambda: check_updates(self.root, APP, self.tr))
        frame = ttk.Frame(self.root, padding=18); frame.pack(fill='both', expand=True)
        t = self.tr
        ttk.Label(frame, text=t('war_title'), font=('', 18, 'bold')).grid(row=0,column=0,columnspan=3,sticky='w',pady=(0,10))
        ttk.Label(frame, text=t('war_instructions'), wraplength=660, justify='left').grid(row=1,column=0,columnspan=3,sticky='w',pady=(0,12))
        ttk.Label(frame, text=t('war_host')).grid(row=2,column=0,sticky='w',pady=6)
        self.host_input = ttk.Entry(frame, textvariable=self.host); self.host_input.grid(row=2,column=1,columnspan=2,sticky='ew',padx=8)
        ttk.Label(frame, text=t('war_edition')).grid(row=3,column=0,sticky='w',pady=6)
        self.game_box = ttk.Combobox(frame, textvariable=self.game, values=('TFT','ROC'), state='readonly', width=12); self.game_box.grid(row=3,column=1,sticky='w',padx=8)
        ttk.Label(frame, text=t('war_version')).grid(row=4,column=0,sticky='w',pady=6)
        self.version_box = ttk.Combobox(frame,textvariable=self.version,values=tuple(f'1.{x}' for x in range(21,30)),state='readonly',width=12); self.version_box.grid(row=4,column=1,sticky='w',padx=8)
        buttons = ttk.Frame(frame); buttons.grid(row=5,column=0,columnspan=3,sticky='w',pady=10)
        self.connect_button = ttk.Button(buttons,text=t('war_connect'),command=self.connect); self.connect_button.pack(side='left',padx=(0,8))
        self.stop_button = ttk.Button(buttons,text=t('war_disconnect'),command=self.disconnect); self.stop_button.pack(side='left')
        ttk.Label(frame, textvariable=self.status, wraplength=660).grid(row=6,column=0,columnspan=3,sticky='w',pady=8)
        ttk.Separator(frame).grid(row=7,column=0,columnspan=3,sticky='ew',pady=10)
        ttk.Label(frame,text=t('war_exe')).grid(row=8,column=0,sticky='w')
        ttk.Entry(frame,textvariable=self.path).grid(row=8,column=1,sticky='ew',padx=8)
        ttk.Button(frame,text=t('war_browse'),command=self.browse).grid(row=8,column=2)
        ttk.Button(frame,text=t('war_launch'),command=self.launch).grid(row=9,column=1,sticky='w',padx=8,pady=12)
        ttk.Label(frame,text=t('war_network_note'),wraplength=660,justify='left').grid(row=10,column=0,columnspan=3,sticky='w',pady=8)
        frame.columnconfigure(1,weight=1); self.update_buttons()

    def set_status(self, key, **kwargs): self.status.set(self.tr(key, **kwargs)); self.status_key = (key, kwargs)
    def set_language(self, code):
        self.tr = Translator(code); self.save(); self.build()
        self.set_status(*self.status_key[:1], **self.status_key[1])
    def set_theme(self, theme): self.theme = theme; self.save(); self.build()
    def save(self): save_settings(APP, {'language':self.tr.code, 'theme':self.theme, 'host':self.host.get(), 'game':self.game.get(), 'version':self.version.get(), 'path':self.path.get()})
    def update_buttons(self):
        self.connect_button.state(['disabled' if self.bridge else '!disabled'])
        self.stop_button.state(['!disabled' if self.bridge else 'disabled'])
        self.host_input.state(['disabled' if self.bridge else '!disabled'])
        self.game_box.state(['disabled' if self.bridge else '!disabled'])
        self.version_box.state(['disabled' if self.bridge else '!disabled'])

    def connect(self):
        try:
            version_text = self.version.get()
            if version_text not in tuple(f'1.{x}' for x in range(21,30)): raise ValueError('version')
            self.generation += 1; generation = self.generation
            bridge = Bridge(self.host.get().strip(), self.game.get(), int(version_text.split('.')[1]), lambda kind, info: self.events.put((generation, kind, info)))
            bridge.start(); self.bridge = bridge; self.save(); self.set_status('war_searching'); self.update_buttons()
        except (OSError, ValueError) as exc:
            messagebox.showerror(self.tr('error'), self.tr('war_connect_error', error=str(exc)), parent=self.root)

    def disconnect(self):
        self.generation += 1
        bridge = self.bridge; self.bridge = None
        if bridge: bridge.stop()
        self.set_status('war_idle'); self.update_buttons()

    def poll(self):
        try:
            while True:
                generation, kind, info = self.events.get_nowait()
                if generation != self.generation: continue
                if kind == 'found': self.set_status('war_found', name=info)
                elif kind == 'lost': self.set_status('war_searching')
                elif kind == 'connected': self.set_status('war_connected')
                elif kind == 'error':
                    self.disconnect(); messagebox.showerror(self.tr('error'), self.tr('war_connect_error', error=info), parent=self.root)
                elif kind == 'relay_error': self.set_status('war_relay_error', error=info)
        except queue.Empty: pass
        self.root.after(100, self.poll)

    def browse(self):
        path = filedialog.askopenfilename(parent=self.root, filetypes=[('Windows executable', '*.exe')])
        if path: self.path.set(path); self.save()

    def launch(self):
        try:
            exe = Path(self.path.get()).expanduser()
            if not exe.is_file() or exe.suffix.lower() != '.exe': raise ValueError(self.tr('war_exe_error'))
            subprocess.Popen([str(exe)], cwd=str(exe.parent)); self.save()
        except (OSError, ValueError) as exc: messagebox.showerror(self.tr('error'), str(exc), parent=self.root)

    def close(self):
        if self.bridge: self.bridge.stop()
        self.save(); self.root.destroy()

if __name__ == '__main__':
    if not helper_mode(APP):
        cleanup_mode(APP); root = tk.Tk(); app = App(root)
        root.after(1500, lambda: check_updates(root, APP, app.tr, automatic=True)); root.mainloop()
