import queue
import re
import subprocess
import sys
import threading
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import tkinter as tk
from tkinter import ttk, filedialog
from shared import dialogs as messagebox
from shared.common import Translator, load_settings, save_settings, settings_menu, apply_theme, set_app_icon, config_dir
from shared.dialogs import center_window
from shared.updater import check_updates, helper_mode, cleanup_mode
from mesh import LobbyClient
from server_host import HostedBroker, ensure_certificate

APP = 'war3-battle-platform'

class App:
    def __init__(self, root):
        self.root=root; self.settings=load_settings(APP); self.tr=Translator(self.settings.get('language','en')); self.theme=self.settings.get('theme','light')
        self.server_host=self.settings.get('server_host',''); self.server_port=self.settings.get('server_port',47653)
        self.fingerprint=self.settings.get('fingerprint',''); self.host_mode=self.settings.get('host_mode',False)
        self.path=tk.StringVar(value=self.settings.get('path','')); self.status=tk.StringVar(); self.status_key=('war_offline',{})
        self.events=queue.Queue(); self.client=None; self.server=None; self.generation=0; self.connecting=False; self.retry_enabled=True
        set_app_icon(root,APP); self.build(); self.set_status('war_offline'); root.protocol('WM_DELETE_WINDOW',self.close)
        root.after(100,self.poll); root.after(300,self.startup)

    def build(self):
        for widget in self.root.winfo_children(): widget.destroy()
        t=self.tr; self.root._fishfish_language=t.code; apply_theme(self.root,self.theme)
        self.root.title(t('war_title')); self.root.geometry('720x500'); self.root.minsize(640,440)
        settings_menu(self.root,t,self.theme,self.set_language,self.set_theme,lambda:check_updates(self.root,APP,self.tr),self.open_settings,t('war_config'))
        frame=ttk.Frame(self.root,padding=18); frame.pack(fill='both',expand=True)
        ttk.Label(frame,text=t('war_title'),font=('',18,'bold')).grid(row=0,column=0,columnspan=3,sticky='w',pady=(0,10))
        ttk.Label(frame,text=t('war_auto_help'),wraplength=660,justify='left').grid(row=1,column=0,columnspan=3,sticky='w',pady=(0,15))
        ttk.Label(frame,textvariable=self.status,wraplength=660,font=('',12)).grid(row=2,column=0,columnspan=3,sticky='w',pady=10)
        buttons=ttk.Frame(frame); buttons.grid(row=3,column=0,columnspan=3,sticky='w',pady=8)
        self.connect_button=ttk.Button(buttons,text=t('war_connect'),command=self.connect); self.connect_button.pack(side='left',padx=(0,8))
        self.stop_button=ttk.Button(buttons,text=t('war_disconnect'),command=self.disconnect); self.stop_button.pack(side='left')
        ttk.Separator(frame).grid(row=4,column=0,columnspan=3,sticky='ew',pady=12)
        ttk.Label(frame,text=t('war_exe')).grid(row=5,column=0,sticky='w')
        ttk.Entry(frame,textvariable=self.path).grid(row=5,column=1,sticky='ew',padx=8)
        ttk.Button(frame,text=t('war_browse'),command=self.browse).grid(row=5,column=2)
        ttk.Button(frame,text=t('war_launch'),command=self.launch).grid(row=6,column=1,sticky='w',padx=8,pady=12)
        ttk.Label(frame,text=t('war_setup_note'),wraplength=660,justify='left').grid(row=7,column=0,columnspan=3,sticky='w',pady=8)
        frame.columnconfigure(1,weight=1); self.update_buttons()

    def set_status(self,key,**kwargs): self.status_key=(key,kwargs); self.status.set(self.tr(key,**kwargs))
    def set_language(self,code): self.tr=Translator(code); self.save(); self.build(); self.set_status(self.status_key[0],**self.status_key[1])
    def set_theme(self,theme): self.theme=theme; self.save(); self.build()
    def save(self):
        self.settings.update({'language':self.tr.code,'theme':self.theme,'server_host':self.server_host,'server_port':self.server_port,'fingerprint':self.fingerprint,'host_mode':self.host_mode,'path':self.path.get()})
        save_settings(APP,self.settings)
    def update_buttons(self):
        self.connect_button.state(['disabled' if self.client or self.connecting else '!disabled'])
        self.stop_button.state(['!disabled' if self.client or self.connecting else 'disabled'])

    def startup(self):
        if self.host_mode: self.start_server()
        elif self.server_host and self.fingerprint: self.connect()
        else: self.open_settings()

    def open_settings(self):
        if hasattr(self,'dialog') and self.dialog.winfo_exists(): self.dialog.lift(); return
        t=self.tr; dialog=self.dialog=tk.Toplevel(self.root); dialog.title(t('war_config')); dialog.transient(self.root); dialog.resizable(False,False)
        frame=ttk.Frame(dialog,padding=16); frame.pack(fill='both',expand=True)
        host=tk.StringVar(value=self.server_host); port=tk.StringVar(value=str(self.server_port)); fingerprint=tk.StringVar(value=self.fingerprint); host_mode=tk.BooleanVar(value=self.host_mode)
        ttk.Label(frame,text=t('war_host_mode'),wraplength=470).grid(row=0,column=0,columnspan=2,sticky='w')
        ttk.Checkbutton(frame,text=t('war_run_server'),variable=host_mode).grid(row=1,column=0,columnspan=2,sticky='w',pady=6)
        for row,(key,var) in enumerate((('war_server',host),('war_server_port',port),('war_fingerprint',fingerprint)),start=2):
            ttk.Label(frame,text=t(key)).grid(row=row,column=0,sticky='w',pady=6)
            ttk.Entry(frame,textvariable=var,width=48).grid(row=row,column=1,sticky='ew',padx=8)
        def copy():
            self.root.clipboard_clear(); self.root.clipboard_append(fingerprint.get())
        ttk.Button(frame,text=t('war_copy'),command=copy).grid(row=5,column=1,sticky='e')
        ttk.Label(frame,text=t('war_setup_note'),wraplength=500).grid(row=6,columnspan=2,sticky='w',pady=10)
        def confirm():
            try:
                number=int(port.get())
                if not 1<=number<=65535: raise ValueError()
                is_host=host_mode.get()
                if is_host:
                    _,_,pin=ensure_certificate(config_dir(APP)/'server'); server='127.0.0.1'
                else:
                    server=host.get().strip(); pin=fingerprint.get().replace(':','').strip().lower()
                    if not server or not re.fullmatch('[0-9a-f]{64}',pin): raise ValueError()
            except (OSError,ValueError) as exc:
                messagebox.showerror(t('error'),t('war_config_error'),parent=dialog); return
            self.shutdown_network(); self.server_host=server; self.server_port=number; self.fingerprint=pin; self.host_mode=is_host; self.retry_enabled=True
            self.save(); dialog.destroy()
            if self.host_mode: self.start_server()
            else: self.connect()
        ttk.Button(frame,text=t('confirm'),command=confirm).grid(row=7,column=1,pady=8)
        center_window(dialog,self.root)

    def start_server(self):
        if self.server: return
        try:
            self.server=HostedBroker(config_dir(APP)/'server',self.server_port,lambda kind,info:self.events.put((self.generation,kind,info)))
            self.fingerprint=self.server.fingerprint; self.server_host='127.0.0.1'; self.save(); self.set_status('war_server_starting'); self.server.start()
        except (OSError,ValueError) as exc:
            self.server=None; self.set_status('war_server_failed',error=str(exc))

    def connect(self):
        if self.client or self.connecting: return
        if not self.server_host or not re.fullmatch('[0-9a-f]{64}',self.fingerprint): self.open_settings(); return
        self.retry_enabled=True; self.connecting=True; self.generation+=1; generation=self.generation
        self.set_status('war_connecting'); self.update_buttons()
        def worker():
            candidate=LobbyClient(self.server_host,self.server_port,self.fingerprint,lambda kind,info:self.events.put((generation,kind,info)))
            try: candidate.start(); self.events.put((generation,'client_ready',candidate))
            except Exception as exc: candidate.stop(); self.events.put((generation,'connect_error',str(exc)))
        threading.Thread(target=worker,daemon=True).start()

    def disconnect(self):
        self.retry_enabled=False; self.generation+=1; self.connecting=False
        if self.client: self.client.stop(); self.client=None
        self.set_status('war_offline'); self.update_buttons()

    def shutdown_network(self):
        self.disconnect()
        if self.server: self.server.stop(); self.server=None

    def poll(self):
        try:
            while True:
                generation,kind,info=self.events.get_nowait()
                if kind.startswith('server_'):
                    if not self.server: continue
                    if kind=='server_ready':
                        self.fingerprint=info; self.server_host='127.0.0.1'; self.save(); self.connect()
                    elif kind=='server_error': self.server=None; self.set_status('war_server_failed',error=info)
                    continue
                if generation != self.generation:
                    if kind=='client_ready': info.stop()
                    continue
                if kind=='client_ready': self.connecting=False; self.client=info; self.set_status('war_online',count=0); self.update_buttons()
                elif kind=='lobbies': self.set_status('war_online',count=info)
                elif kind=='game_connected': self.set_status('war_game_connected')
                elif kind in ('connect_error','error'):
                    self.connecting=False
                    if self.client: self.client.stop(); self.client=None
                    self.set_status('war_connection_error',error=info); self.update_buttons()
                    if self.retry_enabled: self.root.after(5000,lambda:self.connect() if self.retry_enabled and not self.client and not self.connecting else None)
                elif kind=='relay_error': self.set_status('war_connection_error',error=info)
        except queue.Empty: pass
        self.root.after(100,self.poll)

    def browse(self):
        path=filedialog.askopenfilename(parent=self.root,filetypes=[('Windows executable','*.exe')])
        if path: self.path.set(path); self.save()
    def launch(self):
        try:
            exe=Path(self.path.get()).expanduser()
            if not exe.is_file() or exe.suffix.lower()!='.exe': raise ValueError(self.tr('war_exe_error'))
            subprocess.Popen([str(exe)],cwd=str(exe.parent)); self.save()
        except (OSError,ValueError) as exc: messagebox.showerror(self.tr('error'),str(exc),parent=self.root)
    def close(self): self.shutdown_network(); self.save(); self.root.destroy()

if __name__=='__main__':
    if not helper_mode(APP):
        cleanup_mode(APP); root=tk.Tk(); app=App(root)
        root.after(1500,lambda:check_updates(root,APP,app.tr,automatic=True)); root.mainloop()
