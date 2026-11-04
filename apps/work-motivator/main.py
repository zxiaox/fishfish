import sys
import time
from datetime import datetime
from decimal import Decimal
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import tkinter as tk
from tkinter import ttk, messagebox
from shared.common import Translator, load_settings, save_settings, LANGUAGES, apply_theme, set_app_icon
from shared.updater import check_updates, helper_mode, cleanup_mode
from shared.core import work_status

APP = 'work-motivator'

class App:
    def __init__(self, root):
        self.root = root; self.settings = load_settings(APP)
        self.tr = Translator(self.settings.get('language', 'en')); self.theme = self.settings.get('theme', 'light')
        self.start = self.settings.get('start', '09:00'); self.end = self.settings.get('end', '17:00'); self.wage = self.settings.get('wage', '20')
        self.days = self.settings.get('worked_seconds', {}); self.last_wall = datetime.now(); self.last_mono = time.monotonic(); self.last_save = self.last_mono
        self.remaining = tk.StringVar(); self.earned = tk.StringVar(); self.status = tk.StringVar(); self.rate = tk.StringVar(); self.month = tk.StringVar()
        set_app_icon(root, APP); self.build(); self.tick(); root.protocol('WM_DELETE_WINDOW', self.close)
        if not self.settings.get('configured'): root.after(100, self.open_settings)

    def build(self):
        for child in self.root.winfo_children(): child.destroy()
        apply_theme(self.root, self.theme); t = self.tr
        self.root.title(t('work_title')); self.root.geometry('560x380')
        top = ttk.Frame(self.root, padding=12); top.pack(fill='x')
        ttk.Label(top, text=t('work_title'), font=('', 16, 'bold')).pack(side='left')
        ttk.Button(top, text=t('settings'), command=self.open_settings).pack(side='right')
        ttk.Label(self.root, textvariable=self.status, font=('', 13, 'bold')).pack(pady=(12, 5))
        ttk.Label(self.root, textvariable=self.remaining, font=('', 15)).pack(pady=5)
        ttk.Label(self.root, textvariable=self.earned, style='Earnings.TLabel').pack(pady=8)
        ttk.Label(self.root, textvariable=self.rate, font=('', 12)).pack(pady=5)
        self.progress = ttk.Progressbar(self.root, maximum=100); self.progress.pack(fill='x', padx=28, pady=12)
        ttk.Label(self.root, textvariable=self.month, font=('', 12)).pack(pady=4)
        ttk.Label(self.root, text=t('monthly_note'), wraplength=500).pack(pady=4)

    def open_settings(self):
        if hasattr(self, 'dialog') and self.dialog.winfo_exists(): self.dialog.lift(); return
        t = self.tr; dialog = self.dialog = tk.Toplevel(self.root); dialog.title(t('settings')); dialog.transient(self.root); dialog.resizable(False, False)
        form = ttk.Frame(dialog, padding=16); form.pack(fill='both', expand=True)
        start = tk.StringVar(value=self.start); end = tk.StringVar(value=self.end); wage = tk.StringVar(value=self.wage)
        for row, (label, var) in enumerate((('start_time', start), ('end_time', end), ('hourly_wage', wage))):
            ttk.Label(form, text=t(label)).grid(row=row, column=0, sticky='w', pady=6)
            ttk.Entry(form, textvariable=var, width=20).grid(row=row, column=1, sticky='ew', padx=12)
        ttk.Label(form, text=t('language')).grid(row=3, column=0, sticky='w')
        language = ttk.Combobox(form, values=list(LANGUAGES), state='readonly', width=18)
        langs = LANGUAGES
        language.set(next(k for k,v in langs.items() if v == self.tr.code)); language.grid(row=3,column=1,pady=6)
        ttk.Label(form, text=t('theme')).grid(row=4,column=0,sticky='w')
        theme = ttk.Combobox(form, values=[t('light'), t('dark')], state='readonly', width=18); theme.current(1 if self.theme=='dark' else 0); theme.grid(row=4,column=1,pady=6)
        def confirm():
            try: work_status(datetime.now(), start.get(), end.get(), wage.get())
            except (ValueError, ArithmeticError): messagebox.showerror(t('error'), t('work_error'), parent=dialog); return
            self.start, self.end, self.wage = start.get(), end.get(), wage.get()
            self.tr = Translator(langs[language.get()]); self.theme = 'dark' if theme.current()==1 else 'light'; self.settings['configured'] = True
            self.last_wall = datetime.now(); self.last_mono = time.monotonic(); self.save(); dialog.destroy(); self.build()
        ttk.Button(form, text=t('confirm'), command=confirm).grid(row=5,column=1,pady=10)
        ttk.Button(form, text=t('check_updates'), command=lambda: check_updates(self.root, APP, self.tr)).grid(row=6,columnspan=2,pady=4)

    def tick(self):
        now = datetime.now(); mono = time.monotonic()
        try:
            remaining, earned, progress = work_status(now, self.start, self.end, self.wage)
            # Track only observed running time; don't infer work while closed or asleep.
            elapsed = min(max(mono-self.last_mono, 0), 2.0)
            if self.settings.get('configured') and now.date() == self.last_wall.date() and (now-self.last_wall).total_seconds() >= 0:
                start = datetime.combine(now.date(), datetime.strptime(self.start, '%H:%M:%S' if len(self.start.split(':')) == 3 else '%H:%M').time())
                end = datetime.combine(now.date(), datetime.strptime(self.end, '%H:%M:%S' if len(self.end.split(':')) == 3 else '%H:%M').time())
                overlap = max(0.0, (min(now,end)-max(self.last_wall,start)).total_seconds())
                key = now.date().isoformat(); self.days[key] = self.days.get(key, 0) + min(elapsed, overlap)
            on = 0 < progress < 1 or (progress == 0 and remaining > 0 and now.time() >= datetime.strptime(self.start, '%H:%M:%S' if len(self.start.split(':')) == 3 else '%H:%M').time())
            ms = int(remaining*1000); h, ms = divmod(ms,3600000); m, ms = divmod(ms,60000); sec, ms = divmod(ms,1000)
            self.remaining.set(self.tr('remaining', time=f'{h:02}:{m:02}:{sec:02}.{ms:03}'))
            self.earned.set(self.tr('earned', amount=f'{earned:.4f}'))
            self.status.set(self.tr('on_clock' if on else 'off_clock'))
            self.rate.set(self.tr('earning_rate', rate=f'{Decimal(self.wage)/Decimal(3600) if on else Decimal(0):.5f}'))
            self.month.set(self.tr('month_hours', hours=f'{sum(float(v) for k,v in self.days.items() if k.startswith(now.strftime("%Y-%m-")))/3600:.2f}'))
            self.progress['value'] = progress*100
        except (ValueError, ArithmeticError, TypeError): self.status.set(self.tr('work_error'))
        self.last_wall = now; self.last_mono = mono
        if mono - self.last_save > 10:
            self.save(); self.last_save = mono
        self.root.after(25, self.tick)

    def save(self):
        self.settings.update({'language': self.tr.code, 'theme': self.theme, 'start': self.start, 'end': self.end, 'wage': self.wage, 'worked_seconds': self.days}); save_settings(APP, self.settings)

    def close(self): self.save(); self.root.destroy()

if __name__ == '__main__':
    if not helper_mode(APP):
        cleanup_mode(APP); root = tk.Tk(); app = App(root)
        root.after(1500, lambda: check_updates(root, APP, app.tr, automatic=True)); root.mainloop()
