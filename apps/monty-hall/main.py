import sys
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import tkinter as tk
from tkinter import ttk, filedialog
from PIL import Image, ImageTk
from shared import dialogs as messagebox
from shared.common import Translator, load_settings, save_settings, settings_menu, config_dir, apply_theme, set_app_icon, resource_root
from shared.updater import check_updates, helper_mode, cleanup_mode
from shared.core import trial, prepare_live_rounds, choose_live_door, finish_live_round
from shared.history import load_history, save_history, add_experiment, limit_live_rounds
from shared.session_record import create_game_records, append_round
from sound import SoundPlayer

APP = 'monty-hall'; MAX_TRIALS = 100000

class App:
    def __init__(self, root):
        self.root = root; self.settings = load_settings(APP); self.tr = Translator(self.settings.get('language','en')); self.theme = self.settings.get('theme','light'); self.host = self.settings.get('host','host2')
        if self.host not in ('host1', 'host2', 'host3'): self.host = 'host2'
        self.count = tk.StringVar(value='1000'); self.round_count = tk.StringVar(value='5'); self.strategy = tk.StringVar(value='switch')
        self.sound_enabled = tk.BooleanVar(value=self.settings.get('sound_enabled', True)); self.sound_player = SoundPlayer(resource_root() / 'assets' / 'monty-hall-game' / 'audio')
        self.save_live = tk.BooleanVar(value=self.settings.get('save_live', True)); self.session_saving = False; self.unsaved_sessions = []
        self.summary = tk.StringVar(); self.live_text = tk.StringVar(); self.rounds = []; self.results = []; self.round_index = 0; self.job = None; self.phase = 'idle'
        self.history_path = config_dir(APP) / 'history.json'
        self.history_error = None
        try: self.history = load_history(self.history_path)
        except (OSError, ValueError) as exc:
            self.history_error = str(exc); self.history = {'experiments': [], 'live_sessions': []}
        self.session = None
        self.load_game_images()
        set_app_icon(root, APP); self.build()
        if self.history_error: root.after(100, lambda: messagebox.showerror(self.tr('error'), self.tr('history_error', error=self.history_error), parent=self.root))
        root.protocol('WM_DELETE_WINDOW', self.close)

    def load_game_images(self):
        """Resize host art with high-quality filtering and keep Tk images alive."""
        self.image_sheets = {}; self.game_images = {}
        for sheet in ('host', 'host2', 'host3'):
            with Image.open(resource_root() / 'assets' / 'monty-hall-game' / (sheet + '.png')) as source:
                width, height = source.width // 2, source.height // 2
                for index, name in enumerate(('welcome', 'thinking', 'win', 'loss')):
                    x, y = (index % 2) * width, (index // 2) * height
                    cropped = source.crop((x, y, x + width, y + height))
                    resized = cropped.resize((200, 200), Image.Resampling.LANCZOS)
                    self.game_images[sheet + '_' + name] = ImageTk.PhotoImage(resized, master=self.root)
        source = tk.PhotoImage(master=self.root, file=str(resource_root() / 'assets' / 'monty-hall-game' / 'doors.png'))
        self.image_sheets['doors'] = source
        width, height = source.width() // 2, source.height() // 2
        step = max(1, (width + 159) // 160)
        for index, name in enumerate(('closed', 'closed_alt', 'empty', 'treasure')):
            x, y = (index % 2) * width, (index // 2) * height
            image = tk.PhotoImage(master=self.root)
            image.tk.call(image, 'copy', source, '-from', x, y, x + width, y + height, '-subsample', step, step)
            self.game_images['doors_' + name] = image

    def build(self):
        for child in self.root.winfo_children(): child.destroy()
        t = self.tr; self.root._fishfish_language = t.code; apply_theme(self.root, self.theme); self.root.title(t('monty_title')); self.root.geometry('980x940'); self.root.minsize(820, 780)
        menubar = settings_menu(self.root, t, self.theme, self.set_language, self.set_theme,
                      lambda: check_updates(self.root, APP, self.tr))
        menu = self.root.nametowidget(menubar.entrycget(0, 'menu'))
        menu.add_separator(); menu.add_checkbutton(label=t('game_sound_english'), variable=self.sound_enabled, command=self.change_sound)
        frame = ttk.LabelFrame(self.root, text=t('run_experiment'), padding=12); frame.pack(fill='x', padx=12, pady=5)
        ttk.Label(frame, text=t('trial_count')).grid(row=0,column=0); ttk.Entry(frame, textvariable=self.count,width=10).grid(row=0,column=1,padx=8)
        ttk.Radiobutton(frame,text=t('switch'),variable=self.strategy,value='switch').grid(row=0,column=2)
        ttk.Radiobutton(frame,text=t('stay'),variable=self.strategy,value='stay').grid(row=0,column=3)
        self.experiment = ttk.Button(frame,text=t('run_experiment'),command=self.run_experiment); self.experiment.grid(row=0,column=4,padx=8)
        ttk.Label(frame, textvariable=self.summary, wraplength=690).grid(row=1,columnspan=5,pady=8)
        live = ttk.LabelFrame(self.root, text=t('live_game'), padding=12); live.pack(fill='x', padx=12, pady=8)
        settings=ttk.Frame(live); settings.pack(pady=3)
        ttk.Label(settings,text=t('round_count')).pack(side='left',padx=4)
        ttk.Entry(settings,textvariable=self.round_count,width=6).pack(side='left',padx=4)
        ttk.Label(settings,text=t('host_label')).pack(side='left',padx=(18,4))
        self.host_choice = ttk.Combobox(settings, values=(t('host_1'),t('host_2'),t('host_3')), state='readonly', width=12)
        self.host_choice.current(('host1','host2','host3').index(self.host)); self.host_choice.pack(side='left',padx=4)
        self.host_choice.bind('<<ComboboxSelected>>', self.change_host)
        self.start_button = ttk.Button(settings,text=t('live_game'),command=self.start_game); self.start_button.pack(side='left',padx=10)
        ttk.Style(self.root).configure('Save.TCheckbutton', wraplength=740)
        self.save_checkbox = ttk.Checkbutton(live, text=t('save_live'), variable=self.save_live, command=self.save, style='Save.TCheckbutton')
        self.save_checkbox.pack(pady=3)
        ttk.Label(live,textvariable=self.live_text,wraplength=850,justify='center',font=('',11)).pack(pady=5)
        scene=ttk.Frame(live); scene.pack(pady=3)
        self.host_image = ttk.Label(scene, image=self.game_images['host_welcome']); self.host_image.pack(side='left',padx=(0,16))
        doors=ttk.Frame(scene); doors.pack(side='left')
        self.door_buttons=[]
        for number in (1,2,3):
            button=ttk.Button(doors, image=self.game_images['doors_closed'], compound='top', command=lambda door=number:self.select_door(door))
            button.pack(side='left',padx=3); self.door_buttons.append(button)
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
        if self.phase in ('pick', 'choose', 'result'): self.logs.select(1)
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
        live_rows = []
        for session in sorted(self.history['live_sessions'] + self.unsaved_sessions, key=lambda item: item['date']):
            for index, result in enumerate(session['rounds'], 1):
                live_rows.append((session['date'], index, result))
        for date, index, result in reversed(live_rows[-50:]):
            self.live_table.insert('', 'end', values=(date, index, result['choice'], result['revealed'], result['final'], result['prize'], self.tr(result['strategy']), self.tr('win' if result['won'] else 'loss')))


    def persist_history(self):
        if self.history_error: return
        try: save_history(self.history_path, self.history)
        except OSError as exc:
            self.history_error = str(exc)
            messagebox.showerror(self.tr('error'), self.tr('history_error', error=self.history_error), parent=self.root)

    def update_controls(self):
        for button in (self.switch_button,self.stay_button): button.state(['!disabled' if self.phase=='choose' else 'disabled'])
        self.next_button.state(['!disabled' if self.phase=='result' and self.round_index < len(self.rounds)-1 else 'disabled'])
        running = self.phase in ('pick', 'choose') or (self.phase == 'result' and self.round_index < len(self.rounds)-1)
        self.start_button.state(['disabled' if running else '!disabled'])
        self.save_checkbox.state(['disabled' if running else '!disabled'])
        host = 'thinking' if self.phase == 'choose' else ('win' if self.results[-1]['won'] else 'loss') if self.phase == 'result' and self.results else 'welcome'
        self.host_image.configure(image=self.game_images[('host_' if self.host == 'host1' else self.host + '_') + host])
        for door, button in enumerate(self.door_buttons, 1):
            label=self.tr('door_number',number=door)
            if self.phase in ('choose','result'):
                r=self.results[-1] if self.phase == 'result' else self.rounds[self.round_index]
                if door==r['revealed']: label += ' · ' + self.tr('empty') + '\n' + self.tr('eliminated_by_host')
                elif self.phase=='result' and door==r['prize']: label += ' · ' + self.tr('prize')
                elif self.phase=='result' and door==r['final']: label += ' · ' + self.tr('empty')
                if door==r['choice']: label += ' · ' + self.tr('door_selected')
            door_image = 'closed'
            if self.phase in ('choose', 'result') and door == self.rounds[self.round_index]['revealed']:
                door_image = 'empty'
            if self.phase == 'result' and door == self.results[-1]['final']:
                door_image = 'empty'
            if self.phase == 'result' and door == self.results[-1]['prize']:
                door_image = 'treasure'
            button.configure(text=label, image=self.game_images['doors_' + door_image])
        if self.phase in ('pick','choose'): self.show_round()
        elif self.phase == 'result' and self.results: self.show_result()

    def change_host(self, event=None):
        self.host = ('host1','host2','host3')[self.host_choice.current()]
        self.save(); self.update_controls()

    def change_sound(self):
        if not self.sound_enabled.get(): self.sound_player.stop()
        self.save()

    def play_sound(self, cue):
        if self.sound_enabled.get():
            voice = {'host1':'female1', 'host2':'female2', 'host3':'male'}[self.host]
            self.sound_player.play(voice + '_' + cue if cue in ('choose','door1','door2','door3') else cue)

    def set_language(self, code): self.tr = Translator(code); self.save(); self.build()
    def set_theme(self, theme): self.theme = theme; self.save(); self.build()
    def save(self): save_settings(APP, {'language':self.tr.code,'theme':self.theme,'save_live':self.save_live.get(),'host':self.host,'sound_enabled':self.sound_enabled.get()})
    def close(self): self.sound_player.stop(); self.save(); self.root.destroy()

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
        rounds = prepare_live_rounds(count)
        saving = self.save_live.get()
        path = None
        if saving:
            filename = 'three-door-time-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '.txt'
            path = filedialog.asksaveasfilename(parent=self.root, initialfile=filename, defaultextension='.txt', filetypes=[('Text','*.txt')])
            if not path: return
            lines = []
            for i, r in enumerate(rounds, 1):
                layout = ', '.join(f'{door}: '+self.tr('prize' if door==r['prize'] else 'empty') for door in (1,2,3))
                lines.append(f"{self.tr('round_label', number=i)} — {layout}")
            try:
                create_game_records(path, '\n'.join(lines)+'\n', self.tr('session_header')+'\n')
            except FileExistsError:
                messagebox.showerror(self.tr('error'), self.tr('file_exists'), parent=self.root); return
            except OSError as exc:
                messagebox.showerror(self.tr('error'), str(exc), parent=self.root); return
        self.rounds = rounds; self.results = []; self.round_index = 0; self.phase = 'pick'; self.record_path = path; self.session_saving = saving
        self.session = {'date': datetime.now().isoformat(timespec='seconds'), 'record_path': path, 'rounds': self.results}
        self.update_controls(); self.play_sound('choose')

    def show_round(self):
        r=self.rounds[self.round_index]
        if self.phase == 'pick':
            self.live_text.set(self.tr('door_prompt',number=self.round_index+1,total=len(self.rounds)))
        else:
            self.live_text.set(self.tr('door_revealed_prompt',number=self.round_index+1,total=len(self.rounds),choice=r['choice'],revealed=r['revealed']))

    def select_door(self, door):
        if self.phase != 'pick': return
        self.rounds[self.round_index] = choose_live_door(self.rounds[self.round_index], door)
        self.phase = 'choose'; self.update_controls(); self.play_sound('door' + str(self.rounds[self.round_index]['revealed']))

    def play(self, strategy):
        if self.phase != 'choose': return
        if not self.results:
            (self.history['live_sessions'] if self.session_saving else self.unsaved_sessions).append(self.session)
        self.results.append(finish_live_round(self.rounds[self.round_index],strategy))
        if self.session_saving:
            r = self.results[-1]
            line = self.tr('session_round', number=len(self.results), choice=r['choice'], revealed=r['revealed'], strategy=self.tr(r['strategy']), final=r['final'], prize=r['prize'], result=self.tr('win' if r['won'] else 'loss'))
            try: append_round(self.record_path, line)
            except OSError as exc: messagebox.showerror(self.tr('error'), self.tr('record_error', error=str(exc)), parent=self.root)
            self.persist_history()
        limit_live_rounds(self.unsaved_sessions)
        self.refresh_history(); self.logs.select(1)
        self.phase='result'; self.show_result(); self.update_controls(); self.play_sound('success' if self.results[-1]['won'] else 'failure')

    def show_result(self):
        r=self.results[-1]
        self.live_text.set(self.tr('round_result',number=self.round_index+1,prize=r['prize'],final=r['final'],result=self.tr('win' if r['won'] else 'loss'),wins=sum(x['won'] for x in self.results),total=len(self.results)))

    def next_round(self):
        if self.phase != 'result' or self.round_index+1 >= len(self.rounds): return
        self.round_index += 1; self.phase='pick'; self.update_controls(); self.play_sound('choose')

if __name__ == '__main__':
    if not helper_mode(APP):
        cleanup_mode(APP); root=tk.Tk(); app=App(root)
        root.after(1500,lambda:check_updates(root,APP,app.tr,automatic=True)); root.mainloop()
