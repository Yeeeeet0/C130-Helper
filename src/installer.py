"""Single-file Windows setup, updater and manifest-based uninstaller."""
import argparse
import base64
import ctypes
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
from setup_support import APP_NAME,FILES,default_target,automatic_profiles,install,uninstall,webview_installed,ps_literal


def payload_dir():
    base=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]/'build/installer'))
    return base/'payload'


def self_test():
    import hashlib,json
    root=payload_dir();manifest=json.loads((root/'payload.json').read_text(encoding='utf-8'))
    for name,expected in manifest.items():
        path=root/name
        if path.parent!=root or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            raise ValueError('Installer payload validation failed: '+name)
    for name in ('C130J_Reference.exe','MicrosoftEdgeWebview2Setup.exe'):
        if (root/name).read_bytes()[:2]!=b'MZ':raise ValueError('Invalid executable: '+name)
    if b'GESTURE_MODES' not in (root/'C130J_Helper.lua').read_bytes():raise ValueError('Outdated bridge')
    guide='C130J_CDU_Helper_User_Guide.pdf'
    if guide not in manifest or not (root/guide).read_bytes().startswith(b'%PDF-'):raise ValueError('Missing PDF user guide')
    for name in ('C130J_KneeboardBridge.lua','C130J_KneeboardPage.lua'):
        if name not in manifest or b'C130J_HELPER_KB_' not in (root/name).read_bytes():raise ValueError('Missing live kneeboard component: '+name)
    for name in ('LICENSE.txt','THIRD_PARTY_NOTICES.txt'):
        if name not in manifest or not (root/name).read_text(encoding='utf-8').strip():
            raise ValueError('Missing licence document: '+name)
    return 0


def wait_for_parent(pid):
    from ctypes import wintypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.restype=wintypes.HANDLE
    handle=kernel.OpenProcess(0x100000,False,pid)
    if handle:
        kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
        kernel.CloseHandle.argtypes=[wintypes.HANDLE]
        try:
            if kernel.WaitForSingleObject(handle,30000)!=0:raise RuntimeError('Close the installer and retry uninstalling.')
        finally:kernel.CloseHandle(handle)


def schedule_temp_cleanup():
    exe=Path(sys.executable).resolve();folder=exe.parent
    if not folder.name.startswith('c130j-uninstall-') or not folder.is_relative_to(Path(tempfile.gettempdir()).resolve()):return
    script='Wait-Process -Id '+str(os.getpid())+' -ErrorAction SilentlyContinue;Remove-Item -LiteralPath '+ps_literal(exe)+' -Force -ErrorAction SilentlyContinue;Remove-Item -LiteralPath '+ps_literal(folder)+' -ErrorAction SilentlyContinue'
    subprocess.Popen(['powershell.exe','-NoProfile','-NonInteractive','-EncodedCommand',base64.b64encode(script.encode('utf-16-le')).decode()],creationflags=subprocess.CREATE_NO_WINDOW,cwd=tempfile.gettempdir())


def uninstall_ui(target,remove=False,parent=None):
    root=tk.Tk();root.withdraw()
    try:
        if remove:
            if parent:wait_for_parent(parent)
            kept=uninstall(target)
            messagebox.showinfo(APP_NAME,'Uninstalled. Your plans and logs were kept.'+('\nModified files were preserved.' if kept else ''))
        elif messagebox.askyesno(APP_NAME,'Uninstall '+APP_NAME+'?\nYour plans and other DCS exporters will be kept.'):
            folder=Path(tempfile.mkdtemp(prefix='c130j-uninstall-'))
            child=folder/'Uninstall.exe';shutil.copy2(sys.executable,child)
            subprocess.Popen([str(child),'--remove',str(Path(target).resolve()),'--waitpid',str(os.getpid())],cwd=folder)
    finally:
        root.destroy()
        if remove:schedule_temp_cleanup()


def show_notice(parent,name):
    dialog=tk.Toplevel(parent);dialog.title(name);dialog.geometry('760x520')
    text=tk.Text(dialog,wrap='word',font=('Segoe UI',10),padx=16,pady=14)
    scroll=ttk.Scrollbar(dialog,orient='vertical',command=text.yview)
    text.configure(yscrollcommand=scroll.set)
    scroll.pack(side='right',fill='y');text.pack(fill='both',expand=True)
    text.insert('1.0',(payload_dir()/name).read_text(encoding='utf-8'));text.configure(state='disabled')
    return dialog,text


def setup_ui(test=False):
    self_test()
    root=tk.Tk();root.title(APP_NAME+' Setup');root.geometry('680x560');root.minsize(620,530)
    if test:root.withdraw()
    root.configure(bg='#101e2b')
    style=ttk.Style();style.theme_use('clam')
    style.configure('.',font=('Segoe UI',10),background='#101e2b',foreground='#e4edf3')
    style.configure('TButton',padding=(14,9),background='#284c48',foreground='#e4fff5')
    style.configure('TEntry',fieldbackground='#172b3b',foreground='#ffffff',padding=7)
    style.configure('TCheckbutton',background='#101e2b',foreground='#e4edf3')
    style.configure('Title.TLabel',font=('Segoe UI Semibold',22),foreground='#8ee3c6')
    style.configure('TProgressbar',background='#80e2c4',troughcolor='#223b4e')
    frame=ttk.Frame(root,padding=26);frame.pack(fill='both',expand=True);frame.columnconfigure(0,weight=1)
    ttk.Label(frame,text=APP_NAME,style='Title.TLabel').grid(row=0,column=0,columnspan=2,sticky='w')
    ttk.Label(frame,text='App · DCS bridge · Shortcuts').grid(row=1,column=0,columnspan=2,sticky='w',pady=(4,20))
    location=tk.StringVar(value=str(default_target()))
    ttk.Label(frame,text='Install folder').grid(row=2,column=0,sticky='w')
    ttk.Entry(frame,textvariable=location).grid(row=3,column=0,sticky='ew',pady=(5,12))
    def browse_target():
        path=filedialog.askdirectory(title='Install folder')
        if path:location.set(str(Path(path)/'C130JCDUHelper'))
    ttk.Button(frame,text='Browse',command=browse_target).grid(row=3,column=1,padx=(10,0),pady=(5,12))
    from navigation import discover_dcs,NAV_RELATIVE
    detected=discover_dcs()
    dcs_location=tk.StringVar(value=str(detected) if detected else '')
    if detected is None:
        ttk.Label(frame,text='DCS folder (C-130J installed)').grid(row=4,column=0,sticky='w')
        ttk.Entry(frame,textvariable=dcs_location).grid(row=5,column=0,sticky='ew',pady=(5,12))
        def browse_dcs():
            path=filedialog.askdirectory(title='Select DCS installation folder')
            if path:dcs_location.set(path)
        ttk.Button(frame,text='Browse',command=browse_dcs).grid(row=5,column=1,padx=(10,0))
    licence=ttk.Frame(frame);licence.grid(row=6,column=0,columnspan=2,sticky='ew',pady=(4,6))
    ttk.Label(licence,text='Free use. Distribution is subject to the app licence.').pack(anchor='w')
    ttk.Label(licence,text='By selecting Install, you accept the licence.').pack(anchor='w',pady=(2,5))
    links=ttk.Frame(licence);links.pack(anchor='w')
    ttk.Button(links,text='Read licence',command=lambda:show_notice(root,'LICENSE.txt')).pack(side='left')
    ttk.Button(links,text='Third-party notices',command=lambda:show_notice(root,'THIRD_PARTY_NOTICES.txt')).pack(side='left',padx=(8,0))
    desktop_link=tk.BooleanVar(value=True)
    desktop_checkbox=ttk.Checkbutton(frame,text='Create desktop shortcut',variable=desktop_link)
    desktop_checkbox.grid(row=7,column=0,columnspan=2,sticky='w',pady=(8,4))
    status=tk.StringVar(value='DCS bridge, Start menu shortcut and required runtime install automatically.')
    ttk.Label(frame,textvariable=status,wraplength=610).grid(row=8,column=0,columnspan=2,sticky='w',pady=(10,8))
    bar=ttk.Progressbar(frame,maximum=100);bar.grid(row=9,column=0,columnspan=2,sticky='ew',pady=(0,16))
    events=queue.Queue();working=[False];installed=[False]
    def progress(n,text):events.put(('progress',n,text))
    def worker(target,chosen,dcs_root,desktop_shortcut):
        try:
            if not webview_installed():
                progress(3,'Installing WebView2 (internet required)…')
                subprocess.run([str(payload_dir()/'MicrosoftEdgeWebview2Setup.exe'),'/silent','/install'],check=True,creationflags=subprocess.CREATE_NO_WINDOW,timeout=600)
                if not webview_installed():raise RuntimeError('WebView2 installation did not complete. Check internet access and retry.')
            install(payload_dir(),target,chosen,setup_exe=sys.executable,desktop=desktop_shortcut,progress=progress,dcs_root=dcs_root,create_profiles=True)
            events.put(('done',target,bool(chosen)))
        except PermissionError:events.put(('error','Close the Helper and retry. The installation folder must be writable.'))
        except Exception as ex:events.put(('error',str(ex)))
    def action():
        if installed[0]:
            subprocess.Popen([str(Path(location.get())/'C130J_Reference.exe')],cwd=location.get());root.destroy();return
        if working[0]:return
        dcs_root=Path(dcs_location.get()).expanduser()
        if not dcs_location.get().strip() or not (dcs_root/NAV_RELATIVE).is_file():
            messagebox.showerror(APP_NAME,'Select your DCS installation folder containing the C-130J.');return
        chosen=automatic_profiles()
        target=Path(location.get()).expanduser().resolve()
        working[0]=True;button.configure(state='disabled');status.set('Installing…')
        # Freeze the choices before starting the worker.
        for widget in frame.winfo_children():
            if isinstance(widget,(ttk.Entry,ttk.Button,ttk.Checkbutton)):widget.configure(state='disabled')
        threading.Thread(target=worker,args=(target,chosen,dcs_root.resolve(),desktop_link.get()),daemon=True).start()
    button=ttk.Button(frame,text='Install',command=action);button.grid(row=10,column=1,sticky='e')
    def poll():
        try:
            while True:
                event=events.get_nowait()
                if event[0]=='progress':bar['value']=event[1];status.set(event[2])
                elif event[0]=='done':
                    working[0]=False;installed[0]=True;location.set(str(event[1]));bar['value']=100
                    status.set('Installed. Restart DCS once to load the bridge.' if event[2] else 'Installed.')
                    button.configure(text='Open app',state='normal')
                else:
                    working[0]=False;status.set('Installation stopped.');messagebox.showerror(APP_NAME,event[1])
                    for widget in frame.winfo_children():
                        if isinstance(widget,(ttk.Entry,ttk.Button,ttk.Checkbutton)):widget.configure(state='normal')
        except queue.Empty:pass
        root.after(100,poll)
    def close():
        if working[0]:messagebox.showinfo(APP_NAME,'Please wait for installation to finish.')
        else:root.destroy()
    root.protocol('WM_DELETE_WINDOW',close)
    if test:
        root.update_idletasks()
        if button.cget('text')!='Install' or not desktop_link.get() or sum(isinstance(w,ttk.Checkbutton) for w in frame.winfo_children())!=1:raise ValueError('Installer controls failed')
        desktop_checkbox.invoke()
        if desktop_link.get():raise ValueError('Desktop shortcut cannot be disabled')
        for name in ('LICENSE.txt','THIRD_PARTY_NOTICES.txt'):
            dialog,text=show_notice(root,name)
            if text.cget('state')!='disabled' or not text.get('1.0','end').strip():
                raise ValueError('Licence reader failed')
            dialog.destroy()
        root.destroy()
    else:root.after(100,poll);root.mainloop()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--self-test',action='store_true')
    parser.add_argument('--ui-self-test',action='store_true')
    parser.add_argument('--uninstall');parser.add_argument('--remove');parser.add_argument('--waitpid',type=int)
    args=parser.parse_args()
    if args.self_test:return self_test()
    if args.remove:uninstall_ui(args.remove,True,args.waitpid)
    elif args.uninstall:uninstall_ui(args.uninstall)
    else:setup_ui(args.ui_self_test)
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as ex:
        if '--self-test' in sys.argv or '--ui-self-test' in sys.argv:
            print(str(ex),file=sys.stderr);raise SystemExit(1)
        root=tk.Tk();root.withdraw();messagebox.showerror(APP_NAME,str(ex));root.destroy();raise SystemExit(1)
