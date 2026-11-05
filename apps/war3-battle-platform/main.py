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
from shared.common import Translator, VERSIONS, load_settings, save_settings, settings_menu, apply_theme, set_app_icon, config_dir
from shared.dialogs import center_window
from shared.updater import check_updates, helper_mode, cleanup_mode
from mesh import LobbyClient
from server_host import HostedBroker, ensure_certificate
from connection_modes import MODES, load_profiles, normalize_address, zerotier_ips

APP = 'war3-battle-platform'


def empty_scan_stats():
    return {'queries':0, 'responses':0, 'accepted':0, 'rejected':0,
            'last_source_port':0, 'game_version':0, 'product':'',
            'publish_sent':0, 'publish_ack':0, 'publish_rejected':0,
            'server_id':'unknown', 'peers':0}

class App:
    def __init__(self, root):
        self.root=root; self.settings=load_settings(APP); self.tr=Translator(self.settings.get('language','en')); self.theme=self.settings.get('theme','light')
        self.profiles=load_profiles(self.settings)
        saved_mode=self.settings.get('connection_mode','direct')
        self.connection_mode=saved_mode if saved_mode in MODES else 'direct'
        self.apply_profile(self.connection_mode)
        self.path=tk.StringVar(value=self.settings.get('path','')); self.status=tk.StringVar(); self.status_key=('war_offline',{})
        self.discovery=tk.StringVar(); self.discovery_key=('war_local_offline',{}); self.scan_stats=empty_scan_stats(); self.remote_count=0; self.local_name=''
        self.events=queue.Queue(); self.client=None; self.server=None; self.generation=0; self.server_generation=0; self.connecting=False; self.retry_enabled=True
        set_app_icon(root,APP); self.build(); self.set_status('war_offline'); self.set_discovery('war_local_offline'); root.protocol('WM_DELETE_WINDOW',self.close)
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
        ttk.Label(frame,textvariable=self.discovery,wraplength=660).grid(row=3,column=0,columnspan=3,sticky='w',pady=3)
        buttons=ttk.Frame(frame); buttons.grid(row=4,column=0,columnspan=3,sticky='w',pady=8)
        self.connect_button=ttk.Button(buttons,text=t('war_connect'),command=self.connect); self.connect_button.pack(side='left',padx=(0,8))
        self.stop_button=ttk.Button(buttons,text=t('war_disconnect'),command=self.disconnect); self.stop_button.pack(side='left')
        ttk.Button(buttons,text=t('war_copy_diag'),command=self.copy_diagnostics).pack(side='left',padx=8)
        ttk.Separator(frame).grid(row=5,column=0,columnspan=3,sticky='ew',pady=12)
        ttk.Label(frame,text=t('war_exe')).grid(row=6,column=0,sticky='w')
        ttk.Entry(frame,textvariable=self.path).grid(row=6,column=1,sticky='ew',padx=8)
        ttk.Button(frame,text=t('war_browse'),command=self.browse).grid(row=6,column=2)
        ttk.Button(frame,text=t('war_launch'),command=self.launch).grid(row=7,column=1,sticky='w',padx=8,pady=12)
        ttk.Label(frame,text=t('war_zt_main_help' if self.connection_mode=='zerotier' else 'war_setup_note'),wraplength=660,justify='left').grid(row=8,column=0,columnspan=3,sticky='w',pady=8)
        frame.columnconfigure(1,weight=1); self.update_buttons()

    def set_status(self,key,**kwargs): self.status_key=(key,kwargs); self.status.set(self.tr(key,**kwargs))
    def set_discovery(self,key,**kwargs): self.discovery_key=(key,kwargs); self.discovery.set(self.tr(key,**kwargs))
    def set_language(self,code):
        self.tr=Translator(code)
        if self.client: self.client.language=code
        self.save(); self.build(); self.set_status(self.status_key[0],**self.status_key[1]); self.set_discovery(self.discovery_key[0],**self.discovery_key[1])
    def set_theme(self,theme): self.theme=theme; self.save(); self.build()
    def apply_profile(self, mode):
        profile=self.profiles[mode]
        self.server_host=profile['server_host']; self.server_port=profile['server_port']
        self.fingerprint=profile['fingerprint']; self.host_mode=profile['host_mode']

    def current_profile(self):
        return {'server_host':self.server_host, 'server_port':self.server_port,
                'fingerprint':self.fingerprint, 'host_mode':self.host_mode}

    def save(self):
        self.profiles[self.connection_mode]=self.current_profile()
        self.settings.update({'language':self.tr.code, 'theme':self.theme,
                              'connection_mode':self.connection_mode, 'connection_profiles':self.profiles,
                              'path':self.path.get(), **self.profiles['direct']})
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
        frame=ttk.Frame(dialog,padding=14); frame.pack(fill='both',expand=True)
        draft={mode:dict(profile) for mode,profile in self.profiles.items()}
        draft[self.connection_mode]=self.current_profile()
        selected=tk.StringVar(value=self.connection_mode); previous=[self.connection_mode]
        profile=draft[self.connection_mode]
        host=tk.StringVar(value=profile['server_host']); port=tk.StringVar(value=str(profile['server_port']))
        fingerprint=tk.StringVar(value=profile['fingerprint']); host_mode=tk.BooleanVar(value=profile['host_mode'])
        help_text=tk.StringVar(); zt_status=tk.StringVar(value=t('war_zt_unchecked'))
        ttk.Label(frame,text=t('war_mode')).grid(row=0,column=0,sticky='w')
        choices=ttk.Frame(frame); choices.grid(row=0,column=1,sticky='w')
        def change_mode():
            draft[previous[0]]={'server_host':host.get(), 'server_port':port.get(), 'fingerprint':fingerprint.get(), 'host_mode':host_mode.get()}
            previous[0]=selected.get(); profile=draft[selected.get()]
            host.set(profile['server_host']); port.set(str(profile['server_port'])); fingerprint.set(profile['fingerprint']); host_mode.set(profile['host_mode'])
            help_text.set(t('war_zt_help' if selected.get()=='zerotier' else 'war_direct_help'))
            if selected.get()=='zerotier': zt_frame.grid()
            else: zt_frame.grid_remove()
            dialog.update_idletasks()
        for key in MODES:
            ttk.Radiobutton(choices,text=t('war_mode_'+key),variable=selected,value=key,command=change_mode).pack(side='left',padx=(0,10))
        ttk.Checkbutton(frame,text=t('war_run_server'),variable=host_mode).grid(row=1,column=0,columnspan=2,sticky='w',pady=5)
        for row,(key,var) in enumerate((('war_server',host),('war_server_port',port),('war_fingerprint',fingerprint)),start=2):
            ttk.Label(frame,text=t(key)).grid(row=row,column=0,sticky='w',pady=4)
            ttk.Entry(frame,textvariable=var,width=42).grid(row=row,column=1,sticky='ew',padx=8)
        def copy_fingerprint(): self.root.clipboard_clear(); self.root.clipboard_append(fingerprint.get())
        ttk.Button(frame,text=t('war_copy'),command=copy_fingerprint).grid(row=5,column=1,sticky='e')
        zt_frame=ttk.Frame(frame); zt_frame.grid(row=6,column=0,columnspan=2,sticky='ew',pady=4)
        zt_button=ttk.Button(zt_frame,text=t('war_zt_check'))
        zt_button.pack(side='left',padx=(0,8))
        ttk.Entry(zt_frame,textvariable=zt_status,state='readonly',width=45).pack(side='left',fill='x',expand=True)
        def check_zt():
            zt_button.state(['disabled']); zt_status.set(t('war_zt_checking'))
            def work():
                try: result=(zerotier_ips(),None)
                except (OSError,ValueError,subprocess.SubprocessError) as exc: result=(None,str(exc))
                self.events.put((self.generation,'zerotier_result',(dialog,zt_button,zt_status,result)))
            threading.Thread(target=work,daemon=True).start()
        zt_button.configure(command=check_zt)
        ttk.Label(frame,textvariable=help_text,wraplength=520,justify='left').grid(row=7,columnspan=2,sticky='w',pady=8)
        def confirm():
            try:
                number=int(port.get())
                if not 1<=number<=65535: raise ValueError()
                mode=selected.get(); is_host=host_mode.get()
                if mode not in MODES: raise ValueError()
                if is_host:
                    _,_,pin=ensure_certificate(config_dir(APP)/'server'); server='127.0.0.1'
                else:
                    server=normalize_address(mode,host.get()); pin=fingerprint.get().replace(':','').strip().lower()
                    if not re.fullmatch('[0-9a-f]{64}',pin): raise ValueError()
            except (OSError,ValueError):
                messagebox.showerror(t('error'),t('war_config_error'),parent=dialog); return
            draft[mode]={'server_host':server, 'server_port':number, 'fingerprint':pin, 'host_mode':is_host}
            self.shutdown_network(); self.profiles[mode]=draft[mode]; self.connection_mode=mode; self.apply_profile(mode); self.retry_enabled=True
            self.save(); dialog.destroy(); self.build()
            if self.host_mode: self.start_server()
            else: self.connect()
        ttk.Button(frame,text=t('confirm'),command=confirm).grid(row=8,column=1,pady=6)
        help_text.set(t('war_zt_help' if selected.get()=='zerotier' else 'war_direct_help'))
        if selected.get()!='zerotier': zt_frame.grid_remove()
        center_window(dialog,self.root)

    def start_server(self):
        if self.server: return
        try:
            self.server_generation+=1; server_generation=self.server_generation
            self.server=HostedBroker(config_dir(APP)/'server',self.server_port,lambda kind,info:self.events.put((server_generation,kind,info)))
            self.fingerprint=self.server.fingerprint; self.server_host='127.0.0.1'; self.save(); self.set_status('war_server_starting'); self.server.start()
        except (OSError,ValueError) as exc:
            self.server=None; self.set_status('war_server_failed',error=str(exc))

    def connect(self):
        if self.client or self.connecting: return
        if not self.server_host or not re.fullmatch('[0-9a-f]{64}',self.fingerprint): self.open_settings(); return
        self.retry_enabled=True; self.connecting=True; self.reset_session(); self.generation+=1; generation=self.generation
        self.set_status('war_connecting'); self.update_buttons()
        def worker():
            candidate=LobbyClient(self.server_host,self.server_port,self.fingerprint,lambda kind,info:self.events.put((generation,kind,info)),language=self.tr.code)
            try: candidate.start(); self.events.put((generation,'client_ready',candidate))
            except Exception as exc: candidate.stop(); self.events.put((generation,'connect_error',str(exc)))
        threading.Thread(target=worker,daemon=True).start()

    def reset_session(self):
        self.local_name=''; self.remote_count=0; self.scan_stats=empty_scan_stats()
        self.set_discovery('war_local_offline')

    def disconnect(self):
        self.retry_enabled=False; self.generation+=1; self.connecting=False
        if self.client: self.client.stop(); self.client=None
        self.reset_session(); self.set_status('war_offline'); self.update_buttons()

    def shutdown_network(self):
        self.disconnect()
        self.server_generation+=1
        server=self.server; self.server=None
        if server: server.stop()

    def poll(self):
        try:
            while True:
                generation,kind,info=self.events.get_nowait()
                if kind=='zerotier_result':
                    dialog,button,status,result=info
                    if dialog.winfo_exists():
                        button.state(['!disabled']); addresses,error=result
                        status.set(self.tr('war_zt_error') if error else ', '.join(addresses) if addresses else self.tr('war_zt_none'))
                    continue
                if kind.startswith('server_'):
                    if not self.server or generation != self.server_generation: continue
                    if kind=='server_ready':
                        self.fingerprint=info; self.server_host='127.0.0.1'; self.save(); self.connect()
                    elif kind=='server_error': self.server=None; self.set_status('war_server_failed',error=info)
                    continue
                if generation != self.generation:
                    if kind=='client_ready': info.stop()
                    continue
                if kind=='client_ready':
                    self.connecting=False; self.client=info; self.set_status('war_online',count=self.remote_count)
                    if self.discovery_key[0]=='war_local_offline': self.set_discovery('war_local_search')
                    self.update_buttons()
                elif kind=='lobbies': self.remote_count=info; self.set_status('war_online',count=info)
                elif kind=='local_found': self.local_name=info; self.set_discovery('war_local_found',name=info)
                elif kind=='published' and self.local_name: self.set_discovery('war_local_published',name=self.local_name)
                elif kind=='publish_rejected': self.set_discovery('war_publish_rejected')
                elif kind=='local_lost': self.local_name=''; self.set_discovery('war_local_search')
                elif kind=='scan_stats': self.scan_stats=info
                elif kind=='game_connected': self.set_status('war_game_connected')
                elif kind in ('connect_error','error'):
                    self.generation+=1; self.connecting=False
                    if self.client: self.client.stop(); self.client=None
                    self.reset_session(); self.set_status('war_connection_error',error=info); self.update_buttons()
                    if self.retry_enabled: self.root.after(5000,lambda:self.connect() if self.retry_enabled and not self.client and not self.connecting else None)
                elif kind=='relay_error': self.set_status('war_connection_error',error=info)
        except queue.Empty: pass
        self.root.after(100,self.poll)

    def copy_diagnostics(self):
        stats=self.client.snapshot() if self.client else self.scan_stats
        text=(f"War3 Battle Platform {VERSIONS[APP]}\nConnection mode: {self.connection_mode}\n{self.status.get()}\n{self.discovery.get()}\n"
              f"UDP queries: {stats['queries']}; local replies: {stats['responses']}; "
              f"accepted: {stats['accepted']}; rejected: {stats['rejected']}; last local source port: {stats['last_source_port']}\n"
              f"Server ID: {stats['server_id']}; connected peers: {stats['peers']}; "
              f"product: {stats['product']}; protocol version: {stats['game_version']}\n"
              f"Publications sent: {stats['publish_sent']}; acknowledged: {stats['publish_ack']}; server rejected: {stats['publish_rejected']}")
        self.root.clipboard_clear(); self.root.clipboard_append(text)
        messagebox.showinfo(self.tr('war_copy_diag'),self.tr('war_diag_copied'),parent=self.root)

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
