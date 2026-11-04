import csv
import io
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from urllib.parse import urlencode
import webbrowser
from shared.common import Translator, load_settings, save_settings, language_picker
from shared.updater import check_updates, helper_mode, cleanup_mode
from shared.core import trial

APP = 'monty-hall'
MAX_TRIALS = 100000

class App:
    def __init__(self, root):
        self.root = root; self.settings = load_settings(APP); self.tr = Translator(self.settings.get('language', 'en'))
        self.count = tk.StringVar(value='1000'); self.email = tk.StringVar(); self.strategy = tk.StringVar(value='switch')
        self.summary = tk.StringVar(); self.records = []; self.job = None
        self.build(); root.protocol('WM_DELETE_WINDOW', self.close)

    def build(self):
        for child in self.root.winfo_children(): child.destroy()
        t = self.tr; self.root.title(t('monty_title')); self.root.geometry('760x600')
        top = ttk.Frame(self.root, padding=10); top.pack(fill='x')
        ttk.Label(top, text=t('language')).pack(side='left'); language_picker(top, t.code, self.set_language)
        controls = ttk.Frame(self.root, padding=10); controls.pack(fill='x')
        ttk.Label(controls, text=t('strategy')).grid(row=0, column=0, sticky='w')
        ttk.Radiobutton(controls, text=t('switch'), variable=self.strategy, value='switch').grid(row=0, column=1)
        ttk.Radiobutton(controls, text=t('stay'), variable=self.strategy, value='stay').grid(row=0, column=2)
        ttk.Label(controls, text=t('trial_count')).grid(row=1, column=0, sticky='w', pady=8)
        ttk.Entry(controls, textvariable=self.count, width=12).grid(row=1, column=1)
        self.single = ttk.Button(controls, text=t('single_trial'), command=lambda: self.run(1)); self.single.grid(row=2, column=0, pady=8)
        self.multi = ttk.Button(controls, text=t('multi_trial'), command=self.run_many); self.multi.grid(row=2, column=1, padx=8)
        ttk.Label(self.root, textvariable=self.summary, wraplength=700).pack(padx=10, pady=5)
        tableframe = ttk.Frame(self.root, padding=10); tableframe.pack(fill='both', expand=True)
        columns = ('number', 'choice', 'revealed', 'final', 'prize', 'result')
        self.table = ttk.Treeview(tableframe, columns=columns, show='headings', height=10)
        for col in columns:
            self.table.heading(col, text=t(col)); self.table.column(col, width=90, anchor='center')
        scroll = ttk.Scrollbar(tableframe, orient='vertical', command=self.table.yview); self.table.configure(yscrollcommand=scroll.set)
        self.table.pack(side='left', fill='both', expand=True); scroll.pack(side='right', fill='y')
        bottom = ttk.Frame(self.root, padding=10); bottom.pack(fill='x')
        ttk.Label(bottom, text=t('email_address')).grid(row=0, column=0, sticky='w')
        ttk.Entry(bottom, textvariable=self.email, width=35).grid(row=0, column=1, sticky='ew', padx=5)
        ttk.Button(bottom, text=t('email_results'), command=self.email_results).grid(row=0, column=2)
        ttk.Button(bottom, text=t('export_csv'), command=self.export).grid(row=1, column=1, pady=8)
        ttk.Button(bottom, text=t('check_updates'), command=lambda: check_updates(self.root, APP, self.tr)).grid(row=1, column=2)
        bottom.columnconfigure(1, weight=1)
        if self.records: self.refresh()
        if self.job: self.single.state(['disabled']); self.multi.state(['disabled'])

    def set_language(self, code):
        self.tr = Translator(code); self.build()

    def run_many(self):
        try:
            count = int(self.count.get())
            if not 1 <= count <= MAX_TRIALS: raise ValueError()
        except ValueError:
            messagebox.showerror(self.tr('error'), self.tr('count_error'), parent=self.root); return
        self.run(count)

    def run(self, count):
        if self.job: return
        self.records = []; self.job = {'remaining': count, 'strategy': self.strategy.get()}
        self.single.state(['disabled']); self.multi.state(['disabled']); self.process()

    def process(self):
        count = min(1000, self.job['remaining'])
        self.records.extend(trial(self.job['strategy']) for _ in range(count)); self.job['remaining'] -= count
        if self.job['remaining']:
            self.summary.set(self.tr('running', count=len(self.records)))
            self.root.after(1, self.process)
        else:
            self.job = None; self.single.state(['!disabled']); self.multi.state(['!disabled']); self.refresh()

    def refresh(self):
        t = self.tr; self.table.delete(*self.table.get_children())
        wins = sum(r['won'] for r in self.records); count = len(self.records)
        self.summary.set(t('summary', count=count, wins=wins, losses=count-wins, percent=100*wins/count, strategy=t(self.records[0]['strategy'])))
        for i, r in enumerate(self.records[:500], 1):
            self.table.insert('', 'end', values=(i, r['choice'], r['revealed'], r['final'], r['prize'], t('win' if r['won'] else 'loss')))
        if count > 500: self.summary.set(self.summary.get() + ' ' + t('preview_limit'))

    def csv_text(self):
        output = io.StringIO(newline=''); writer = csv.writer(output)
        writer.writerow(['trial', 'initial_choice', 'host_revealed', 'final_choice', 'prize_door', 'strategy', 'won'])
        for i, r in enumerate(self.records, 1): writer.writerow([i, r['choice'], r['revealed'], r['final'], r['prize'], r['strategy'], r['won']])
        return output.getvalue()

    def export(self):
        if not self.records or self.job:
            messagebox.showinfo(self.tr('error'), self.tr('no_records'), parent=self.root); return
        path = filedialog.asksaveasfilename(defaultextension='.csv', filetypes=[('CSV', '*.csv')], parent=self.root)
        if path:
            try: Path(path).write_text(self.csv_text(), encoding='utf-8-sig', newline='')
            except OSError as exc: messagebox.showerror(self.tr('error'), str(exc), parent=self.root)

    def email_results(self):
        if not self.records or self.job:
            messagebox.showinfo(self.tr('error'), self.tr('no_records'), parent=self.root); return
        address = self.email.get().strip()
        if '@' not in address or any(c in address for c in '\r\n?&# ,;'):
            messagebox.showerror(self.tr('error'), self.tr('email_error'), parent=self.root); return
        wins = sum(r['won'] for r in self.records); count = len(self.records)
        body = self.tr('summary', count=count, wins=wins, losses=count-wins, percent=100*wins/count, strategy=self.tr(self.records[0]['strategy']))
        # Mailto URLs are length-limited: larger batches require CSV export and manual attachment.
        if count <= 10:
            body += '\n\n' + self.csv_text()
        else:
            body += '\n\n' + self.tr('attach_csv')
            messagebox.showinfo(self.tr('email_results'), self.tr('email_notice'), parent=self.root)
        url = 'mailto:' + address + '?' + urlencode({'subject': self.tr('monty_title'), 'body': body}, encoding='utf-8').replace('+', '%20')
        if not webbrowser.open(url): messagebox.showerror(self.tr('error'), self.tr('mail_error'), parent=self.root)

    def close(self):
        save_settings(APP, {'language': self.tr.code}); self.root.destroy()

if __name__ == '__main__':
    if not helper_mode(APP):
        cleanup_mode(APP)
        root = tk.Tk(); App(root)
        root.after(1500, lambda: check_updates(root, APP, Translator(load_settings(APP).get('language', 'en')), automatic=True))
        root.mainloop()
