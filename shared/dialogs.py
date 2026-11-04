"""Small owner-centered dialogs shared by the desktop applications."""
import tkinter as tk
from tkinter import ttk

BUTTONS = {
    'en': ('OK', 'Yes', 'No'), 'zh': ('确定', '是', '否'),
    'ko': ('확인', '예', '아니요'), 'ja': ('OK', 'はい', 'いいえ'),
    'th': ('ตกลง', 'ใช่', 'ไม่'), 'de': ('OK', 'Ja', 'Nein'),
    'es': ('Aceptar', 'Sí', 'No'),
}


def center_window(window, owner):
    """Place a realized window at its owner's center, clamped to the display."""
    window.withdraw()
    window.update_idletasks(); owner.update_idletasks()
    width, height = window.winfo_reqwidth(), window.winfo_reqheight()
    x = owner.winfo_rootx() + (owner.winfo_width() - width) // 2
    y = owner.winfo_rooty() + (owner.winfo_height() - height) // 2
    x = max(0, min(x, window.winfo_screenwidth() - width))
    y = max(0, min(y, window.winfo_screenheight() - height))
    window.geometry(f'+{x}+{y}'); window.deiconify()


def _show(title, message, parent, question=False):
    owner = parent.winfo_toplevel()
    root = owner._root()
    dialog = tk.Toplevel(owner); dialog.withdraw(); dialog.title(title); dialog.transient(owner); dialog.resizable(False, False)
    frame = ttk.Frame(dialog, padding=20); frame.pack(fill='both', expand=True)
    ttk.Label(frame, text=message, wraplength=420, justify='left').pack(pady=(0, 16))
    buttons = ttk.Frame(frame); buttons.pack()
    ok, yes, no = BUTTONS.get(getattr(root, '_fishfish_language', 'en'), BUTTONS['en'])
    result = [False]
    def close(value=False):
        result[0] = value
        dialog.destroy()
    if question:
        ttk.Button(buttons, text=yes, command=lambda: close(True)).pack(side='left', padx=4)
        ttk.Button(buttons, text=no, command=close).pack(side='left', padx=4)
    else:
        ttk.Button(buttons, text=ok, command=lambda: close(True)).pack()
    dialog.protocol('WM_DELETE_WINDOW', close)
    dialog.bind('<Escape>', lambda event: close())
    dialog.bind('<Return>', lambda event: close(True))
    previous_grab = root.grab_current()
    center_window(dialog, root)
    dialog.grab_set(); dialog.focus_set(); owner.wait_window(dialog)
    if previous_grab and previous_grab.winfo_exists(): previous_grab.grab_set()
    return result[0]


def showinfo(title, message, *, parent):
    return _show(title, message, parent)


def showerror(title, message, *, parent):
    return _show(title, message, parent)


def askyesno(title, message, *, parent):
    return _show(title, message, parent, question=True)
