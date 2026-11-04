import sys
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import tkinter as tk
from tkinter import ttk, filedialog
from shared import dialogs as messagebox
from shared.common import Translator, load_settings, save_settings, settings_menu, config_dir, apply_theme, set_app_icon
from shared.updater import check_updates, helper_mode, cleanup_mode
from shared.core import trial, prepare_live_rounds, finish_live_round
from shared.history import load_history, save_history, add_experiment

APP = 'monty-hall'; MAX_TRIALS = 100000

class App:
    def __init__(self, root):
        self.root = root; self.settings = load_settings(APP); self.tr = Translator(self.settings.get('language','en')); self.theme = self.settings.get('theme','light')
        self.count = tk.StringVar(value='1000'); self.round_count = tk.StringVar(value='5'); self.strategy = tk.StringVar(value='switch')
        self.summary = tk.StringVar(); self.live_text = tk.StringVar(); self.rounds = []; self.results = []; self.round_index = 0; self.job = None; self.phase = 'idle'
        self.history_path = config_dir(APP) / 'history.json'
        self.history_error = None
        try: self.history = load_history(self.history_path)
        except (OSError, ValueError) as exc:
            self.history_error = str(exc); self.history = {'experiments': [], 'live_sessions': []}
        self.session = None
        set_app_icon(root, APP); self.build()
        if self.history_error: root.after(100, lambda: messagebox.showerror(self.tr('error'), self.tr('history_error', error=self.history_error), parent=self.root))
        root.protocol('WM_DELETE_WINDOW', self.close)

    def build(self):
        for child in self.root.winfo_children(): child.destroy()
        t = self.tr; self.root._fishfish_language = t.code; apply_theme(self.root, self.theme); self.root.title(t('monty_title')); self.root.geometry('920x820'); self.root.minsize(760, 650)
        settings_menu(self.root, t, self.theme, self.set_language, self.set_theme,
                      lambda: check_updates(self.root, APP, self.tr))
        frame = ttk.LabelFrame(self.root, text=t('run_experiment'), padding=12); frame.pack(fill='x', padx=12, pady=5)
        ttk.Label(frame, text=t('trial_count')).grid(row=0,column=0); ttk.Entry(frame, textvariable=self.count,width=10).grid(row=0,column=1,padx=8)
        ttk.Radiobutton(frame,text=t('switch'),variable=self.strategy,value='switch').grid(row=0,column=2)
        ttk.Radiobutton(frame,text=t('stay'),variable=self.strategy,value='stay').grid(row=0,column=3)
        self.experiment = ttk.Button(frame,text=t('run_experiment'),command=self.run_experiment); self.experiment.grid(row=0,column=4,padx=8)
        ttk.Label(frame, textvariable=self.summary, wraplength=690).grid(row=1,columnspan=5,pady=8)
        live = ttk.LabelFrame(self.root, text=t('live_game'), padding=12); live.pack(fill='x', padx=12, pady=8)
        ttk.Label(live,text=t('round_count')).pack(); ttk.Entry(live,textvariable=self.round_count,width=8).pack(pady=4)
        self.start_button = ttk.Button(live,text=t('live_game'),command=self.start_game); self.start_button.pack(pady=4)
        ttk.Label(live,textvariable=self.live_text,wraplength=680,justify='center',font=('',12)).pack(pady=15)
        buttons = ttk.Frame(live); buttons.pack(pady=4)
        self.switch_button = ttk.Button(buttons,text=t('switch'),command=lambda:self.play('switch')); self.switch_button.pack(side='left',padx=5)
        self.stay_button = ttk.Button(buttons,text=t('stay'),command=lambda:self.play('stay')); self.stay_button.pack(side='left',padx=5)
        self.next_button = ttk.Button(buttons,text=t('next_round'),command=self.next_round); self.next_button.pack(side='left',padx=5)
        logs = self.logs = ttk.Notebook(self.root); logs.pack(fill='both', expand=True, padx=12, pady=8)
        experiments = ttk.Frame(logs); sessions = ttk.Frame(logs)
        logs.add(experiments, text=t('experiment_history')); logs.add(sessions, text=t('live_history'))
        self.experiment_table = self.make_table(experiments, ('date', 'strategy', 'trial_count', 'wins', 'losses', 'win_rate'))
        self.live_table = self.make_table(sessions, ('date', 'number', 'choice', 'revealed', 'final', 'prize', 'strategy', 'result'))
        self.refresh_history()
        if self.phase in ('choose', 'result'): self.logs.select(1)
        self.update_controls()
        if self.job: self.experiment.state(['disabled'])

    def make_table(self, parent, columns):
        table = ttk.Treeview(parent, columns=columns, show='headings', height=6)
        for col in columns:
            table.heading(col, text=self.tr(col)); table.column(col, width=105, minwidth=60, anchor='center')
        scroll = ttk.Scrollbar(parent, orient='vertical', command=table.yview)
        table.configure(yscrollcommand=scroll.set); table.pack(side='left', fill='both', expand=True); scroll.pack(side='right', fill='y')
        return table

    def refresh_history(self):
        for table in (self.experiment_table, self.live_table): table.delete(*table.get_children())
        for entry in reversed(self.history['experiments']):
            self.experiment_table.insert('', 'end', values=(entry['date'], self.tr(entry['strategy']), entry['trials'], entry['wins'], entry['losses'], f"{entry['wins'] / entry['trials'] * 100:.2f}%"))
        for session in reversed(self.history['live_sessions']):
            for index, result in enumerate(session['rounds'], 1):
                self.live_table.insert('', 'end', values=(session['date'], index, result['choice'], result['revealed'], result['final'], result['prize'], self.tr(result['strategy']), self.tr('win' if result['won'] else 'loss')))

    def persist_history(self):
        if self.history_error: return
        try: save_history(self.history_path, self.history)
        except OSError as exc:
            self.history_error = str(exc)
            messagebox.showerror(self.tr('error'), self.tr('history_error', error=self.history_error), parent=self.root)

    def update_controls(self):
        for button in (self.switch_button,self.stay_button): button.state(['!disabled' if self.phase=='choose' else 'disabled'])
        self.next_button.state(['!disabled' if self.phase=='result' and self.round_index < len(self.rounds)-1 else 'disabled'])
        self.start_button.state(['disabled' if self.phase == 'choose' or (self.phase == 'result' and self.round_index < len(self.rounds)-1) else '!disabled'])
        if self.phase == 'choose': self.show_round()
        elif self.phase == 'result' and self.results: self.show_result()

    def set_language(self, code): self.tr = Translator(code); self.save(); self.build()
    def set_theme(self, theme): self.theme = theme; self.save(); self.build()
    def save(self): save_settings(APP, {'language':self.tr.code,'theme':self.theme})
    def close(self): self.save(); self.root.destroy()

    def run_experiment(self):
        if self.job: return
        try:
            count = int(self.count.get())
            if not 1 <= count <= MAX_TRIALS: raise ValueError()
        except ValueError: messagebox.showerror(self.tr('error'), self.tr('count_error'),parent=self.root); return
        self.job = {'remaining': count, 'total': count, 'wins': 0, 'strategy': self.strategy.get()}; self.experiment.state(['disabled']); self.process()

    def process(self):
        n = min(1000,self.job['remaining']); self.job['wins'] += sum(trial(self.job['strategy'])['won'] for _ in range(n)); self.job['remaining'] -= n
        if self.job['remaining']: self.summary.set(self.tr('running',count=self.job['total']-self.job['remaining'])); self.root.after(1,self.process)
        else:
            j = self.job; self.summary.set(self.tr('summary',count=j['total'],wins=j['wins'],losses=j['total']-j['wins'],percent=100*j['wins']/j['total'],strategy=self.tr(j['strategy'])))
            add_experiment(self.history, {'date': datetime.now().isoformat(timespec='seconds'), 'strategy': j['strategy'], 'trials': j['total'], 'wins': j['wins'], 'losses': j['total']-j['wins']})
            self.persist_history(); self.refresh_history(); self.logs.select(0)
            self.job = None; self.experiment.state(['!disabled'])

    def start_game(self):
        try:
            count = int(self.round_count.get())
            if not 1 <= count <= 20: raise ValueError()
        except ValueError: messagebox.showerror(self.tr('error'),self.tr('round_error'),parent=self.root); return
        filename = 'three-doors-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '.txt'
        path = filedialog.asksaveasfilename(parent=self.root, initialfile=filename, defaultextension='.txt', filetypes=[('Text','*.txt')])
        if not path: return
        rounds = prepare_live_rounds(count)
        lines = []
        for i, r in enumerate(rounds, 1):
            layout = ', '.join(f'{door}: '+self.tr('prize' if door==r['prize'] else 'empty') for door in (1,2,3))
            lines.append(f"{self.tr('round_label', number=i)} — {layout}")
        try:
            with open(path, 'x', encoding='utf-8') as f: f.write('\n'.join(lines)+'\n')
        except FileExistsError:
            messagebox.showerror(self.tr('error'),self.tr('file_exists'),parent=self.root); return
        except OSError as exc: messagebox.showerror(self.tr('error'),str(exc),parent=self.root); return
        self.rounds = rounds; self.results = []; self.round_index = 0; self.phase = 'choose'; self.record_path = path
        self.session = {'date': datetime.now().isoformat(timespec='seconds'), 'record_path': path, 'rounds': self.results}
        messagebox.showinfo(self.tr('live_game'),self.tr('record_saved',path=path),parent=self.root); self.update_controls()

    def show_round(self):
        r=self.rounds[self.round_index]
        self.live_text.set(self.tr('round_prompt',number=self.round_index+1,total=len(self.rounds),choice=r['choice'],revealed=r['revealed']))

    def play(self, strategy):
        if self.phase != 'choose': return
        if not self.results: self.history['live_sessions'].append(self.session)
        self.results.append(finish_live_round(self.rounds[self.round_index],strategy))
        self.persist_history(); self.refresh_history(); self.logs.select(1)
        self.phase='result'; self.show_result(); self.update_controls()

    def show_result(self):
        r=self.results[-1]
        self.live_text.set(self.tr('round_result',number=self.round_index+1,prize=r['prize'],final=r['final'],result=self.tr('win' if r['won'] else 'loss'),wins=sum(x['won'] for x in self.results),total=len(self.results)))

    def next_round(self):
        if self.phase != 'result' or self.round_index+1 >= len(self.rounds): return
        self.round_index += 1; self.phase='choose'; self.update_controls()

if __name__ == '__main__':
    if not helper_mode(APP):
        cleanup_mode(APP); root=tk.Tk(); app=App(root)
        root.after(1500,lambda:check_updates(root,APP,app.tr,automatic=True)); root.mainloop()
