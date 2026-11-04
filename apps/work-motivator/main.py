import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import tkinter as tk
from tkinter import ttk
from datetime import datetime
from shared.common import Translator, load_settings, save_settings, language_picker
from shared.updater import check_updates, helper_mode, cleanup_mode
from shared.core import work_status

APP = 'work-motivator'

class App:
    def __init__(self, root):
        self.root = root
        self.settings = load_settings(APP)
        self.tr = Translator(self.settings.get('language', 'en'))
        self.start = tk.StringVar(value=self.settings.get('start', '09:00'))
        self.end = tk.StringVar(value=self.settings.get('end', '17:00'))
        self.wage = tk.StringVar(value=self.settings.get('wage', '20'))
        self.remaining = tk.StringVar(); self.earned = tk.StringVar(); self.status = tk.StringVar()
        self.build()
        self.tick()
        root.protocol('WM_DELETE_WINDOW', self.close)

    def build(self):
        for child in self.root.winfo_children(): child.destroy()
        t = self.tr
        self.root.title(t('work_title'))
        self.root.geometry('520x340')
        top = ttk.Frame(self.root, padding=12); top.pack(fill='x')
        ttk.Label(top, text=t('language')).pack(side='left')
        language_picker(top, t.code, self.set_language)
        form = ttk.Frame(self.root, padding=(18, 4)); form.pack(fill='x')
        for row, (label, var) in enumerate((('start_time', self.start), ('end_time', self.end), ('hourly_wage', self.wage))):
            ttk.Label(form, text=t(label)).grid(row=row, column=0, sticky='w', pady=6)
            ttk.Entry(form, textvariable=var, width=20).grid(row=row, column=1, sticky='ew', padx=12)
        form.columnconfigure(1, weight=1)
        ttk.Label(self.root, textvariable=self.remaining, font=('', 15)).pack(pady=(12, 4))
        ttk.Label(self.root, textvariable=self.earned, font=('', 15)).pack(pady=4)
        self.progress = ttk.Progressbar(self.root, maximum=100); self.progress.pack(fill='x', padx=20, pady=8)
        ttk.Label(self.root, textvariable=self.status, foreground='#a23535', wraplength=480).pack()
        ttk.Button(self.root, text=t('check_updates'), command=lambda: check_updates(self.root, APP, self.tr)).pack(pady=8)

    def set_language(self, code):
        self.tr = Translator(code); self.build()

    def tick(self):
        try:
            remaining, earned, progress = work_status(datetime.now(), self.start.get(), self.end.get(), self.wage.get())
            ms = int(remaining * 1000); hours, ms = divmod(ms, 3600000); minutes, ms = divmod(ms, 60000); seconds, ms = divmod(ms, 1000)
            self.remaining.set(self.tr('remaining', time=f'{hours:02}:{minutes:02}:{seconds:02}.{ms:03}'))
            self.earned.set(self.tr('earned', amount=f'{earned:.4f}'))
            self.progress['value'] = progress * 100
            self.status.set('')
        except ValueError:
            self.remaining.set(''); self.earned.set(''); self.progress['value'] = 0
            self.status.set(self.tr('work_error'))
        self.root.after(25, self.tick)

    def close(self):
        save_settings(APP, {'language': self.tr.code, 'start': self.start.get(), 'end': self.end.get(), 'wage': self.wage.get()})
        self.root.destroy()

if __name__ == '__main__':
    if not helper_mode(APP):
        cleanup_mode(APP)
        root = tk.Tk(); App(root)
        root.after(1500, lambda: check_updates(root, APP, Translator(load_settings(APP).get('language', 'en')), automatic=True))
        root.mainloop()
