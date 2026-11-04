"""Windows portable updater. Updates require explicit consent and a frozen executable."""
import ctypes
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import urllib.parse
import urllib.request
from pathlib import Path
from shared.common import REPO, VERSIONS, find_latest

MAX_EXE = 150 * 1024 * 1024
HOSTS = {'api.github.com', 'github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com'}

class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)

def check_url(url):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or parsed.hostname not in HOSTS or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError('Untrusted URL')

def read_url(url, limit):
    check_url(url)
    request = urllib.request.Request(url, headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'FishFish-updater'})
    with urllib.request.build_opener(SafeRedirect()).open(request, timeout=20) as response:
        data = response.read(limit + 1)
    if len(data) > limit: raise ValueError('Download too large')
    return data

def asset_details(release, app):
    tag = release['tag_name']
    prefix = f'https://github.com/{REPO}/releases/download/{tag}/'
    assets = release.get('assets', [])
    exe = [a for a in assets if a.get('name') == app + '.exe']
    checksum = [a for a in assets if a.get('name') == app + '.exe.sha256']
    if len(exe) != 1 or len(checksum) != 1: raise ValueError('Missing or duplicate assets')
    for asset in exe + checksum:
        if asset.get('browser_download_url') != prefix + asset['name']: raise ValueError('Untrusted asset')
    size = exe[0].get('size')
    if type(size) is not int or not 0 < size <= MAX_EXE: raise ValueError('Invalid size')
    digest = exe[0].get('digest')
    if digest is not None and not re.fullmatch(r'sha256:[a-fA-F0-9]{64}', digest): raise ValueError('Invalid digest')
    return exe[0], checksum[0], digest[7:].lower() if digest else None

def verify(data, size, digest):
    if len(data) != size or hashlib.sha256(data).hexdigest() != digest: raise ValueError('Checksum mismatch')
    if len(data) < 64 or data[:2] != b'MZ': raise ValueError('Invalid executable')
    offset = struct.unpack_from('<I', data, 0x3c)[0]
    if offset + 6 > len(data) or data[offset:offset+4] != b'PE\0\0' or data[offset+4:offset+6] != b'\x64\x86':
        raise ValueError('Not a Windows x64 executable')

def latest_release(app):
    releases = []
    for page in range(1, 6):
        batch = json.loads(read_url(f'https://api.github.com/repos/{REPO}/releases?per_page=100&page={page}', 4 * 1024 * 1024))
        if not isinstance(batch, list): raise ValueError('Invalid metadata')
        releases.extend(batch)
        if len(batch) < 100: break
    latest = find_latest(releases, app)
    if not latest: return None
    tag = app + '-v' + '.'.join(map(str, latest[0]))
    release = next(r for r in releases if r.get('tag_name') == tag and not r.get('draft') and not r.get('prerelease'))
    asset_details(release, app)
    return release

def download(release, app):
    exe, checksum, api_digest = asset_details(release, app)
    text = read_url(checksum['browser_download_url'], 4096).decode('ascii').strip()
    match = re.fullmatch(r'([a-fA-F0-9]{64})\s+\*?' + re.escape(app + '.exe'), text)
    if not match: raise ValueError('Invalid checksum')
    digest = match.group(1).lower()
    if api_digest and digest != api_digest: raise ValueError('Conflicting checksums')
    data = read_url(exe['browser_download_url'], exe['size'])
    verify(data, exe['size'], digest)
    return data, digest

def start_install(root, app, data, digest):
    if sys.platform != 'win32' or not getattr(sys, 'frozen', False): raise ValueError('Windows packaged build required')
    target = Path(sys.executable).resolve()
    stage = Path(tempfile.mkdtemp(prefix='.' + app + '-update-', dir=target.parent))
    try:
        (stage / 'new.exe').write_bytes(data)
        helper = stage / 'helper.exe'; shutil.copy2(target, helper)
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.SetHandleInformation.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32]
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.OpenProcess(0x00100000 | 0x1000, True, os.getpid())
        if not handle: raise OSError('Cannot obtain process handle')
        try:
            if not kernel.SetHandleInformation(handle, 1, 1): raise OSError('Cannot inherit process handle')
            startup = subprocess.STARTUPINFO(); startup.lpAttributeList = {'handle_list': [handle]}
            subprocess.Popen([str(helper), '--fishfish-apply', app, str(target), str(handle), digest, str(len(data))], startupinfo=startup, close_fds=True)
        finally: kernel.CloseHandle(handle)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True); raise
    close_callback = root.protocol('WM_DELETE_WINDOW')
    if close_callback: root.tk.call(close_callback)
    else: root.destroy()

def helper_mode(app):
    if len(sys.argv) < 2 or sys.argv[1] != '--fishfish-apply': return False
    target = None; exited = False
    try:
        if sys.platform != 'win32' or len(sys.argv) != 7 or sys.argv[2] != app: raise ValueError('Bad helper arguments')
        target = Path(sys.argv[3]); handle = int(sys.argv[4]); digest = sys.argv[5]; size = int(sys.argv[6])
        stage = Path(sys.executable).resolve().parent
        if (not target.is_absolute() or target.suffix.lower() != '.exe' or target.parent.resolve() != stage.parent or
            not stage.name.startswith('.' + app + '-update-') or Path(sys.executable).name.lower() != 'helper.exe' or
            not re.fullmatch('[a-f0-9]{64}', digest) or not 0 < size <= MAX_EXE): raise ValueError('Invalid staging path')
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        kernel.WaitForSingleObject.restype = ctypes.c_uint32
        if kernel.WaitForSingleObject(handle, 30000) != 0: raise OSError('Parent did not exit')
        exited = True
        staged = stage / 'new.exe'; verify(staged.read_bytes(), size, digest)
        backup = Path(str(target) + '.backup'); shutil.copy2(target, backup)
        os.replace(staged, target)
        try: subprocess.Popen([str(target), '--fishfish-cleanup', str(stage)])
        except Exception:
            shutil.copy2(backup, target); raise
    except Exception:
        ctypes.windll.user32.MessageBoxW(None, 'The update could not be installed. Your settings are unchanged; the previous executable or its .backup file may be used to recover.', 'FishFish update', 0x30)
        if exited and target and target.exists():
            try: subprocess.Popen([str(target)])
            except OSError: pass
    return True

def cleanup_mode(app):
    if len(sys.argv) != 3 or sys.argv[1] != '--fishfish-cleanup' or not getattr(sys, 'frozen', False): return
    stage = Path(sys.argv[2]); target = Path(sys.executable).resolve()
    if stage.is_absolute() and stage.parent.resolve() == target.parent and stage.name.startswith('.' + app + '-update-'):
        import time
        def cleanup():
            for _ in range(20):
                try: shutil.rmtree(stage); return
                except OSError: time.sleep(.5)
        threading.Thread(target=cleanup, daemon=True).start()

def check_updates(root, app, tr, automatic=False):
    from shared import dialogs as messagebox
    def error():
        if not automatic: messagebox.showerror(tr('updates'), tr('update_error'), parent=root)
    def worker():
        try:
            release = latest_release(app)
            def found():
                if not release:
                    if not automatic: messagebox.showinfo(tr('updates'), tr('up_to_date'), parent=root)
                    return
                version = release['tag_name'][len(app)+2:]
                if not messagebox.askyesno(tr('updates'), tr('update_install', version=version), parent=root): return
                def get():
                    try:
                        data, digest = download(release, app)
                        def apply():
                            try: start_install(root, app, data, digest)
                            except Exception: messagebox.showerror(tr('updates'), tr('update_error'), parent=root)
                        root.after(0, apply)
                    except Exception: root.after(0, lambda: messagebox.showerror(tr('updates'), tr('update_error'), parent=root))
                threading.Thread(target=get, daemon=True).start()
            root.after(0, found)
        except Exception: root.after(0, error)
    if sys.platform != 'win32' or not getattr(sys, 'frozen', False):
        if not automatic: messagebox.showinfo(tr('updates'), tr('update_packaged'), parent=root)
        return
    threading.Thread(target=worker, daemon=True).start()
