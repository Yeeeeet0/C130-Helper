"""Collect supplied runtime/build notices without changing their licence texts."""
from importlib.metadata import distribution
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
RUNTIME=('bottle','cffi','clr_loader','packaging','pillow','proxy_tools',
         'pycparser','pythonnet','pywebview','setuptools','typing_extensions')
BUILD=('altgraph','pefile','pyinstaller','pyinstaller-hooks-contrib','pywin32-ctypes')


def collect():
    sections=[('Scope',
        'Third-party components retain their own licences and copyright holders.\n'
        'The Helper proprietary licence does not restrict rights granted by\n'
        'these separate licences. Notices below include runtime components and\n'
        'build tools; listing a build tool does not mean its full source is bundled.\n\n'
        'DCS, ASC, terrain charts, airfield reference content and associated names\n'
        'and trademarks remain subject to their respective owners\' rights.\n'
        'No ownership, endorsement or redistribution permission is claimed here.\n'
        'A local installation or a bundled data cache is not evidence of permission\n'
        'to redistribute its source content.\n\n'
        'Microsoft Edge WebView2 Runtime is installed separately when required,\n'
        'under Microsoft\'s runtime terms. The included WebView2 SDK/loader notice\n'
        'is reproduced below; this does not replace the runtime terms.\n'
        'https://developer.microsoft.com/microsoft-edge/webview2/\n')]
    for kind,names in [('Runtime',RUNTIME),('Build tool',BUILD)]:
        for name in names:
            dist=distribution(name)
            paths=sorted(f for f in dist.files or [] if
                         Path(str(f)).name.lower().startswith(('license','copying','notice'))
                         and not str(f).endswith(('.py','.pyc')))
            for path in paths:
                text=Path(dist.locate_file(path)).read_text(encoding='utf-8',errors='replace')
                sections.append((f'{kind}: {dist.metadata["Name"]} {dist.version} / {path}',text))
            if not paths and name!='proxy_tools':
                raise ValueError('Missing supplied licence for '+name)
    base=Path(sys.base_prefix)
    for title,path in [('Python '+sys.version.split()[0],base/'LICENSE.txt'),
                       ('Tk runtime',base/'tcl/tk8.6/license.terms')]:
        sections.append((title,path.read_text(encoding='utf-8',errors='replace')))
    for path in sorted((ROOT/'legal/third-party').glob('*.txt')):
        sections.append((path.name,path.read_text(encoding='utf-8-sig')))
    # The bundled JS header identifies this work and its MIT licence.
    mit=Path(distribution('bottle').locate_file('bottle-'
        +distribution('bottle').version+'.dist-info/licenses/LICENSE')).read_text(encoding='utf-8')
    permission=mit[mit.index('Permission is hereby granted'):]
    sections.append(('domJSON.js 0.1.2 (embedded in pywebview)',
        'Copyright (c) 2013 Alex Zaslavsky\nThe MIT License\n\n'+permission))
    result='THIRD-PARTY NOTICES — C-130J CDU Helper\n\n'
    result+='\n\n'.join(title+'\n'+'='*min(len(title),80)+'\n'+body.strip()
                        for title,body in sections)+'\n'
    (ROOT/'THIRD_PARTY_NOTICES.txt').write_text(result,encoding='utf-8')
    print(f'Collected {len(sections)} notice sections.')


if __name__=='__main__':collect()
