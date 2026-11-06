import sys
import time
from datetime import datetime
from decimal import Decimal
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import tkinter as tk
from tkinter import ttk
from shared import dialogs as messagebox
from shared.common import Translator, load_settings, save_settings, settings_menu, apply_theme, set_app_icon
from shared.dialogs import center_window
from shared.updater import check_updates, helper_mode, cleanup_mode
from shared.core import work_status, work_interval, observed_work_by_day
from countdown import DEFAULT_DURATION, parse_duration, new_deadline, remaining_text
from calendar_display import calendar_lines

APP = 'work-motivator'

class App:
    def __init__(self, root):
        self.root = root; self.settings = load_settings(APP)
        self.tr = Translator(self.settings.get('language', 'en')); self.theme = self.settings.get('theme', 'light')
        self.start = self.settings.get('start', '09:00'); self.end = self.settings.get('end', '17:00'); self.wage = self.settings.get('wage', '20')
        self.countdown_enabled = self.settings.get('countdown_enabled', False) is True
        self.countdown_duration = self.settings.get('countdown_duration', DEFAULT_DURATION)
        try: parse_duration(self.countdown_duration)
        except ValueError: self.countdown_duration = DEFAULT_DURATION
        self.countdown_deadline = new_deadline(self.countdown_enabled, self.countdown_duration, self.countdown_enabled, self.countdown_duration, self.settings.get('countdown_deadline'), time.time())
        self.days = self.settings.get('worked_seconds', {}); self.last_wall = datetime.now(); self.last_mono = time.monotonic(); self.last_save = self.last_mono
        self.remaining = tk.StringVar(); self.earned = tk.StringVar(); self.status = tk.StringVar(); self.rate = tk.StringVar(); self.month = tk.StringVar(); self.countdown = tk.StringVar(); self.calendar_date = tk.StringVar(); self.calendar_lunar = tk.StringVar(); self.calendar_cache = None
        set_app_icon(root, APP); self.build(); self.tick(); root.protocol('WM_DELETE_WINDOW', self.close)
        if not self.settings.get('configured'): root.after(100, self.open_settings)

    def build(self):
        for child in self.root.winfo_children(): child.destroy()
        apply_theme(self.root, self.theme); t = self.tr; self.root._fishfish_language = t.code
        self.root.title(t('work_title')); self.root.geometry('560x490' if self.countdown_enabled else '560x430')
        top = ttk.Frame(self.root, padding=12); top.pack(fill='x')
        ttk.Label(top, text=t('work_title'), font=('', 16, 'bold')).pack(side='left')
        settings_menu(self.root, t, self.theme, self.set_language, self.set_theme,
                      lambda: check_updates(self.root, APP, self.tr), self.open_settings, t('work_countdown_settings'))
        ttk.Label(self.root, textvariable=self.calendar_date, font=('', 11, 'bold')).pack(pady=(0, 2))
        ttk.Label(self.root, textvariable=self.calendar_lunar, font=('', 10)).pack(pady=(0, 2))
        ttk.Label(self.root, textvariable=self.status, font=('', 13, 'bold')).pack(pady=(8, 5))
        ttk.Label(self.root, textvariable=self.remaining, font=('', 15)).pack(pady=5)
        ttk.Label(self.root, textvariable=self.earned, style='Earnings.TLabel').pack(pady=8)
        ttk.Label(self.root, textvariable=self.rate, font=('', 12)).pack(pady=5)
        self.progress = ttk.Progressbar(self.root, maximum=100, style='Work.Horizontal.TProgressbar'); self.progress.pack(fill='x', padx=28, pady=12)
        ttk.Label(self.root, textvariable=self.month, font=('', 12)).pack(pady=4)
        ttk.Label(self.root, text=t('monthly_note'), wraplength=500).pack(pady=4)
        if self.countdown_enabled:
            ttk.Label(self.root, textvariable=self.countdown, font=('', 14, 'bold')).pack(pady=(12, 4))

    def open_settings(self):
        if hasattr(self, 'dialog') and self.dialog.winfo_exists(): self.dialog.lift(); return
        t = self.tr; dialog = self.dialog = tk.Toplevel(self.root); dialog.title(t('settings')); dialog.transient(self.root); dialog.resizable(False, False)
        form = ttk.Frame(dialog, padding=16); form.pack(fill='both', expand=True)
        start = tk.StringVar(value=self.start); end = tk.StringVar(value=self.end); wage = tk.StringVar(value=self.wage)
        countdown_enabled = tk.BooleanVar(value=self.countdown_enabled); countdown_duration = tk.StringVar(value=self.countdown_duration); restart = tk.BooleanVar(value=False)
        for row, (label, var) in enumerate((('start_time', start), ('end_time', end), ('hourly_wage', wage))):
            ttk.Label(form, text=t(label)).grid(row=row, column=0, sticky='w', pady=6)
            ttk.Entry(form, textvariable=var, width=20).grid(row=row, column=1, sticky='ew', padx=12)
        ttk.Separator(form).grid(row=3, column=0, columnspan=2, sticky='ew', pady=8)
        ttk.Checkbutton(form, text=t('countdown_enable'), variable=countdown_enabled).grid(row=4, column=0, columnspan=2, sticky='w', pady=4)
        ttk.Label(form, text=t('countdown_duration')).grid(row=5, column=0, sticky='w', pady=6)
        ttk.Entry(form, textvariable=countdown_duration, width=20).grid(row=5, column=1, sticky='ew', padx=12)
        ttk.Checkbutton(form, text=t('countdown_restart'), variable=restart).grid(row=6, column=0, columnspan=2, sticky='w', pady=4)
        def confirm():
            try: work_status(datetime.now(), start.get(), end.get(), wage.get())
            except (ValueError, ArithmeticError): messagebox.showerror(t('error'), t('work_error'), parent=dialog); return
            duration = countdown_duration.get().strip()
            try:
                deadline = new_deadline(countdown_enabled.get(), duration, self.countdown_enabled, self.countdown_duration, self.countdown_deadline, time.time(), restart.get())
            except (ValueError, ArithmeticError): messagebox.showerror(t('error'), t('countdown_error'), parent=dialog); return
            self.countdown_enabled, self.countdown_duration, self.countdown_deadline = countdown_enabled.get(), duration, deadline
            self.start, self.end, self.wage = start.get(), end.get(), wage.get()
            self.settings['configured'] = True
            self.last_wall = datetime.now(); self.last_mono = time.monotonic(); self.save(); dialog.destroy(); self.build()
        ttk.Button(form, text=t('confirm'), command=confirm).grid(row=7,column=1,pady=10)
        center_window(dialog, self.root)

    def set_language(self, code):
        self.tr = Translator(code); self.refresh_calendar(datetime.now().date()); self.save(); self.build()

    def set_theme(self, theme):
        self.theme = theme; self.save(); self.build()

    def refresh_calendar(self, day):
        key = (day, self.tr.code)
        if key != self.calendar_cache:
            date_text, lunar_text = calendar_lines(day, self.tr)
            self.calendar_date.set(date_text); self.calendar_lunar.set(lunar_text); self.calendar_cache = key

    def tick(self):
        now = datetime.now(); mono = time.monotonic(); self.refresh_calendar(now.date())
        try:
            remaining, earned, progress = work_status(now, self.start, self.end, self.wage)
            # Track observed time by calendar date, including across midnight.
            if self.settings.get('configured'):
                for key, seconds in observed_work_by_day(self.last_wall, now, self.start, self.end, mono - self.last_mono).items():
                    self.days[key] = self.days.get(key, 0) + seconds
            begin, finish = work_interval(now, self.start, self.end)
            on = begin <= now < finish
            ms = int(remaining*1000); h, ms = divmod(ms,3600000); m, ms = divmod(ms,60000); sec, ms = divmod(ms,1000)
            self.remaining.set(self.tr('remaining', time=f'{h:02}:{m:02}:{sec:02}.{ms:03}'))
            self.earned.set(self.tr('earned', amount=f'{earned:.4f}'))
            self.status.set(self.tr('on_clock' if on else 'off_clock'))
            self.rate.set(self.tr('earning_rate', rate=f'{Decimal(self.wage)/Decimal(3600) if on else Decimal(0):.5f}'))
            self.month.set(self.tr('month_hours', hours=f'{sum(float(v) for k,v in self.days.items() if k.startswith(now.strftime("%Y-%m-")))/3600:.2f}'))
            self.progress['value'] = progress*100
        except (ValueError, ArithmeticError, TypeError): self.status.set(self.tr('work_error'))
        if self.countdown_enabled and self.countdown_deadline is not None:
            self.countdown.set(self.tr('countdown_display', time=remaining_text(self.countdown_deadline, time.time())))
        self.last_wall = now; self.last_mono = mono
        if mono - self.last_save > 10:
            self.save(); self.last_save = mono
        self.root.after(25, self.tick)

    def save(self):
        self.settings.update({'language': self.tr.code, 'theme': self.theme, 'start': self.start, 'end': self.end, 'wage': self.wage, 'worked_seconds': self.days, 'countdown_enabled': self.countdown_enabled, 'countdown_duration': self.countdown_duration, 'countdown_deadline': self.countdown_deadline}); save_settings(APP, self.settings)

    def close(self): self.save(); self.root.destroy()

if __name__ == '__main__':
    if not helper_mode(APP):
        cleanup_mode(APP); root = tk.Tk(); app = App(root)
        root.after(1500, lambda: check_updates(root, APP, app.tr, automatic=True)); root.mainloop()
