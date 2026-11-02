"""Per-user installer operations. Only manifest-owned files are uninstalled."""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import uuid

APP_NAME='C-130J CDU Helper'
APP_ID='C130JCDUHelper'
VERSION='1.0.0'
MANIFEST='install-manifest.json'
REGISTRY_KEY=r'Software\Microsoft\Windows\CurrentVersion\Uninstall'+'\\'+APP_ID
LOADER="pcall(function() dofile(require('lfs').writedir() .. 'Scripts/C130J_Helper.lua') end) -- C130J_HELPER"
FILES=('C130J_Reference.exe','C130J.ico','CDU_HELPER.md','C130J_CDU_Helper_User_Guide.pdf','Uninstall.exe','dcs-location.json',
       'LICENSE.txt','THIRD_PARTY_NOTICES.txt')
KNEEBOARD_FILES=('Scripts/C130J_KneeboardBridge.lua','Scripts/C130J_KneeboardPage.lua')+tuple(
    f'Kneeboard/C-130J-30/C130J_CDU_Helper_{page:02}.lua' for page in range(1,21))


def kneeboard_payload(payload):
    data={relative:(Path(payload)/Path(relative).name).read_bytes() for relative in KNEEBOARD_FILES[:2]}
    for page,relative in enumerate(KNEEBOARD_FILES[2:],1):
        data[relative]=("-- C130J_CDU_HELPER_LIVE_KNEEBOARD\nC130J_HELPER_KB_PAGE = "+str(page)+
            "\ndofile(require('lfs').writedir() .. 'Scripts/C130J_KneeboardPage.lua')\n").encode('ascii')
    return data


def digest(data):return hashlib.sha256(data).hexdigest()


def default_target():return Path(os.environ['LOCALAPPDATA'])/'Programs'/APP_ID


def shell_folder(name,fallback):
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders') as key:
            return Path(winreg.QueryValueEx(key,name)[0])
    except FileNotFoundError:return Path(fallback)


def profiles_in(root=None):
    root=Path(root or shell_folder('{4C5C32FF-BB9D-43B0-BF18-EE15F81E0DF8}',Path.home()/'Saved Games'))
    return sorted([p for p in root.glob('DCS*') if p.is_dir()],key=lambda p:p.name.lower())


def automatic_profiles(root=None):
    root=Path(root or shell_folder('{4C5C32FF-BB9D-43B0-BF18-EE15F81E0DF8}',Path.home()/'Saved Games'))
    profiles=profiles_in(root)
    return profiles or [root/'DCS']


def read_manifest(target):
    path=Path(target)/MANIFEST
    if not path.exists():return None
    data=json.loads(path.read_text(encoding='utf-8'))
    if data.get('app_id')!=APP_ID or Path(data.get('target','')).resolve()!=Path(target).resolve():
        raise ValueError('This folder contains an unrelated installation manifest.')
    if set(data.get('files',{}))-set(FILES):raise ValueError('Invalid installer file list.')
    for profile in data.get('profiles',[]):
        for item in profile.get('kneeboard',[]):
            if item.get('relative') not in KNEEBOARD_FILES:raise ValueError('Invalid live kneeboard file list.')
    return data


def powershell(script):
    encoded=base64.b64encode(script.encode('utf-16-le')).decode('ascii')
    return subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-EncodedCommand',encoded],
                          check=True,creationflags=subprocess.CREATE_NO_WINDOW,capture_output=True)


def ps_literal(value):return "'"+str(value).replace("'","''")+"'"


def shortcut_bytes(target,link):
    link=Path(link);link.parent.mkdir(parents=True,exist_ok=True)
    # The caller records the original link before this shell creates it.
    powershell("$ErrorActionPreference='Stop';$w=New-Object -ComObject WScript.Shell;"
               "$s=$w.CreateShortcut("+ps_literal(link)+");$s.TargetPath="+ps_literal(Path(target)/FILES[0])+";"
               "$s.WorkingDirectory="+ps_literal(target)+";$s.IconLocation="+ps_literal(Path(target)/'C130J.ico')+";$s.Save()")
    return link.read_bytes()


def register_app(target):
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,REGISTRY_KEY) as key:
        values={'DisplayName':APP_NAME,'DisplayVersion':VERSION,'Publisher':APP_NAME,
                'InstallLocation':str(target),'DisplayIcon':str(target/'C130J.ico'),
                'UninstallString':'"'+str(target/'Uninstall.exe')+'" --uninstall "'+str(target)+'"'}
        for name,value in values.items():winreg.SetValueEx(key,name,0,winreg.REG_SZ,value)
        winreg.SetValueEx(key,'NoModify',0,winreg.REG_DWORD,1)
        winreg.SetValueEx(key,'NoRepair',0,winreg.REG_DWORD,1)


def unregister_app(target):
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,REGISTRY_KEY) as key:
            location=winreg.QueryValueEx(key,'InstallLocation')[0]
        if Path(location).resolve()==Path(target).resolve():winreg.DeleteKey(winreg.HKEY_CURRENT_USER,REGISTRY_KEY)
    except FileNotFoundError:pass


class Transaction:
    def __init__(self):self.original={}
    def remember(self,path):
        path=Path(path)
        if path not in self.original:self.original[path]=path.read_bytes() if path.is_file() else None
    def write(self,path,data):
        path=Path(path);self.remember(path);path.parent.mkdir(parents=True,exist_ok=True)
        temp=path.with_name(path.name+'.setup-'+uuid.uuid4().hex)
        try:temp.write_bytes(data);temp.replace(path)
        finally:temp.unlink(missing_ok=True)
    def rollback(self):
        errors=[]
        for path,data in reversed(list(self.original.items())):
            try:
                if data is None:path.unlink(missing_ok=True)
                else:path.write_bytes(data)
            except OSError as ex:errors.append(str(ex))
        return errors


def install(payload,target,profiles=(),setup_exe=None,desktop=True,register=True,make_shortcuts=True,progress=lambda n,text:None,dcs_root=None,create_profiles=False):
    payload=Path(payload).resolve();target=Path(target).resolve()
    if target==Path(target.anchor) or target==Path.home().resolve():raise ValueError('Choose a dedicated app folder.')
    previous=read_manifest(target)
    if not previous and any((target/f).exists() for f in FILES):raise ValueError('Choose an empty app folder or the existing Helper installation.')
    sources={name:payload/name for name in FILES if name not in ('Uninstall.exe','dcs-location.json')}
    sources['Uninstall.exe']=Path(setup_exe)
    blobs={name:path.read_bytes() for name,path in sources.items()}
    if dcs_root is not None:
        dcs_root=Path(dcs_root).resolve()
        if not (dcs_root/'Mods/aircraft/C130J/Cockpit/Resources/nav_data.db').is_file():raise ValueError('Select the DCS folder containing the installed C-130J.')
        blobs['dcs-location.json']=json.dumps(dict(dcs_root=str(dcs_root))).encode('utf-8')
    elif previous and 'dcs-location.json' in previous['files'] and (target/'dcs-location.json').is_file():
        blobs['dcs-location.json']=(target/'dcs-location.json').read_bytes()
    if not all(data for data in blobs.values()):raise ValueError('Incomplete installer payload.')
    manifest=dict(app_id=APP_ID,version=VERSION,target=str(target),files={name:digest(data) for name,data in blobs.items()},profiles=[],shortcuts=[])
    tx=Transaction()
    try:
        progress(15,'Installing app')
        for name,data in blobs.items():tx.write(target/name,data)
        bridge=(payload/'C130J_Helper.lua').read_bytes()
        live_pages=kneeboard_payload(payload)
        selected={Path(p).resolve() for p in profiles}
        old_profiles={p['profile']:p for p in (previous or {}).get('profiles',[])}
        # Existing profile ownership remains tracked if an update omits it.
        manifest['profiles']=[p for p in old_profiles.values() if Path(p['profile']) not in selected]
        for profile in sorted(selected):
            if not profile.exists() and create_profiles:profile.mkdir(parents=True)
            if not profile.is_dir():raise ValueError('DCS profile not found: '+str(profile))
            scripts=profile/'Scripts';bridge_path=scripts/'C130J_Helper.lua';export=scripts/'Export.lua'
            original=bridge_path.read_bytes() if bridge_path.is_file() else None
            prior=old_profiles.get(str(profile))
            owned=prior and original is not None and digest(original)==prior['installed_hash']
            record=dict(profile=str(profile),original_bridge=prior['original_bridge'] if owned else (base64.b64encode(original).decode() if original is not None else None),
                        installed_hash=digest(bridge),loader_added=prior['loader_added'] if owned else False)
            content=export.read_bytes() if export.exists() else b''
            stamp=uuid.uuid4().hex[:12]
            if original is not None:tx.write(bridge_path.with_name('C130J_Helper.lua.'+stamp+'.bak'),original)
            if b'C130J_HELPER' not in content:
                if content:tx.write(export.with_name('Export.lua.'+stamp+'.bak'),content)
                tx.write(export,content+b'\r\n'+LOADER.encode()+b'\r\n');record['loader_added']=True
            tx.write(bridge_path,bridge)
            prior_pages={p['relative']:p for p in (prior or {}).get('kneeboard',[])}
            record['kneeboard']=[]
            for relative,data in live_pages.items():
                path=(profile/relative).resolve()
                if not path.is_relative_to(profile):raise ValueError('Live kneeboard files must remain inside the DCS profile')
                original=path.read_bytes() if path.is_file() else None
                prior_page=prior_pages.get(relative)
                owned=prior_page and original is not None and digest(original)==prior_page['installed_hash']
                record['kneeboard'].append(dict(relative=relative,installed_hash=digest(data),
                    original=prior_page['original'] if owned else (base64.b64encode(original).decode() if original is not None else None)))
                tx.write(path,data)
            manifest['profiles'].append(record)
        progress(65,'Creating shortcuts')
        if make_shortcuts:
            links=[shell_folder('Programs',Path(os.environ['APPDATA'])/'Microsoft/Windows/Start Menu/Programs')/APP_NAME/(APP_NAME+'.lnk')]
            desktop_path=shell_folder('Desktop',Path.home()/'Desktop')/(APP_NAME+'.lnk')
            removed=set()
            if desktop:links.append(desktop_path)
            else:
                for link in (previous or {}).get('shortcuts',[]):
                    path=Path(link['path'])
                    if path.resolve()==desktop_path.resolve() and path.is_file() and digest(path.read_bytes())==link['hash']:
                        tx.remember(path);path.unlink();removed.add(str(path))
            for link in links:
                tx.remember(link);data=shortcut_bytes(target,link)
                manifest['shortcuts'].append(dict(path=str(link),hash=digest(data)))
            manifest['shortcuts'] += [link for link in (previous or {}).get('shortcuts',[]) if link['path'] not in {str(p) for p in links}|removed]
        else:manifest['shortcuts']=(previous or {}).get('shortcuts',[])
        tx.write(target/MANIFEST,json.dumps(manifest,indent=2).encode('utf-8'))
        if register:register_app(target)
        progress(100,'Installed')
        return manifest
    except Exception:
        tx.rollback()
        if register:
            if previous:register_app(target)
            else:unregister_app(target)
        raise


def uninstall(target,register=True):
    target=Path(target).resolve();manifest=read_manifest(target)
    if not manifest:raise ValueError('Helper installation manifest not found.')
    kept=[]
    for record in manifest['profiles']:
        profile=Path(record['profile']).resolve();scripts=profile/'Scripts'
        for item in record.get('kneeboard',[]):
            relative=item['relative']
            if relative not in KNEEBOARD_FILES:raise ValueError('Invalid live kneeboard file list')
            path=(profile/relative).resolve()
            if not path.is_relative_to(profile):raise ValueError('Invalid live kneeboard path')
            if path.is_file() and digest(path.read_bytes())==item['installed_hash']:
                if item['original'] is None:path.unlink()
                else:path.write_bytes(base64.b64decode(item['original']))
            elif path.exists():kept.append(str(path))
        bridge=scripts/'C130J_Helper.lua';export=scripts/'Export.lua'
        if bridge.is_file() and digest(bridge.read_bytes())==record['installed_hash']:
            original=record['original_bridge']
            if original is None:bridge.unlink()
            else:bridge.write_bytes(base64.b64decode(original))
            if record['loader_added'] and export.is_file():
                # Remove only our exact loader line, preserving other exporters.
                content=export.read_bytes();line=LOADER.encode()
                export.write_bytes(b''.join(part for part in content.splitlines(keepends=True) if part.strip()!=line))
        elif bridge.exists():kept.append(str(bridge))
    for link in manifest['shortcuts']:
        path=Path(link['path'])
        if path.is_file() and digest(path.read_bytes())==link['hash']:path.unlink()
    if register:unregister_app(target)
    for name,expected in manifest['files'].items():
        path=target/name
        if path.is_file() and digest(path.read_bytes())==expected:path.unlink()
        elif path.exists():kept.append(str(path))
    (target/MANIFEST).unlink()
    try:target.rmdir()
    except OSError:pass  # Keep plans, logs and any user-created files.
    return kept


def webview_installed():
    import winreg
    suffix=r'Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'
    for root,prefix in ((winreg.HKEY_CURRENT_USER,'Software\\'),(winreg.HKEY_LOCAL_MACHINE,'SOFTWARE\\WOW6432Node\\'),(winreg.HKEY_LOCAL_MACHINE,'SOFTWARE\\')):
        try:
            with winreg.OpenKey(root,prefix+suffix) as key:version=winreg.QueryValueEx(key,'pv')[0]
            if version and version!='0.0.0.0':return True
        except FileNotFoundError:pass
    return False
