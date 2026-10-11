#!/usr/bin/python
# SPDX-License-Identifier: LGPL-3.0-or-later
"""KDE application-menu screen actions, without modifying system desktop files."""
import configparser
import json
import os
from pathlib import Path
import subprocess
import sys
sys.path.append('/usr/lib/aynthor')

DATA = Path(os.environ.get('XDG_DATA_HOME',str(Path.home()/'.local/share')))
CONFIG = Path(os.environ.get('XDG_CONFIG_HOME',str(Path.home()/'.config')))/'aynthor'
IDS = ('HandheldDashTop','HandheldDashBottom')


def desktop_file(path):
    parser = configparser.ConfigParser(interpolation=None,strict=False)
    parser.optionxform = str
    parser.read(path,encoding='utf-8')
    return parser


def sync():
    applications = DATA/'applications'; applications.mkdir(parents=True,exist_ok=True)
    backups = CONFIG/'desktop-backups'; backups.mkdir(parents=True,exist_ok=True)
    from localization import CATALOG
    sources = {}
    for base in [DATA,*map(Path,os.environ.get('XDG_DATA_DIRS','/usr/local/share:/usr/share').split(':'))]:
        for path in (base/'applications').rglob('*.desktop'):
            ident = str(path.relative_to(base/'applications')).replace('/','-')
            if ident in sources: continue
            # Generated overrides track their original file across package updates.
            parser = desktop_file(path)
            original = parser.get('Desktop Entry','X-HandheldDash-Source',fallback='')
            if original and Path(original).is_file(): path = Path(original)
            sources[ident] = path
    changed = False
    for ident,path in sources.items():
        try:
            parser = desktop_file(path)
            entry = parser['Desktop Entry']
            if entry.get('Type') != 'Application' or entry.get('Hidden','false') == 'true' or entry.get('NoDisplay','false') == 'true': continue
            if not entry.get('Exec') and entry.get('DBusActivatable') != 'true': continue
            target = applications/ident
            backup = backups/ident
            if path == target and not backup.exists(): backup.write_bytes(path.read_bytes())
            entry['X-HandheldDash-Source'] = str(path if path != target else backup)
            actions = [a for a in entry.get('Actions','').split(';') if a and a not in IDS]
            entry['Actions'] = ';'.join(actions+list(IDS))+';'
            for action,screen,en in [('HandheldDashTop','top','Open on top screen'),('HandheldDashBottom','bottom','Open on bottom screen')]:
                # Exec field codes in filenames must be escaped independently of shell quoting.
                quoted = '"'+str(target).replace('\\','\\\\').replace('"','\\"').replace('`','\\`').replace('$','\\$').replace('%','%%')+'"'
                parser['Desktop Action '+action] = {'Name':en,'Name[zh_CN]':CATALOG[en]['zh_CN'],'Name[zh_TW]':CATALOG[en]['zh_TW'],'Icon':'video-display','Exec':'/usr/bin/python /usr/lib/aynthor/desktop_launch.py '+screen+' '+quoted}
            from io import StringIO
            output = StringIO(); parser.write(output,space_around_delimiters=False)
            text = output.getvalue()
            if target.exists() and target.read_text() == text: continue
            stage = target.with_suffix('.handhelddash-new'); stage.write_text(text); stage.replace(target); changed = True
        except (OSError,configparser.Error,KeyError) as error:
            print(f'{path}: {error}',file=sys.stderr)
    if changed: subprocess.run(['kbuildsycoca6','--noincremental'],check=True)


def launch(screen,path):
    from gi.repository import Gio, GioUnix, GLib
    file = Path(path).resolve()
    parser = desktop_file(file)
    entry = parser['Desktop Entry']
    app = GioUnix.DesktopAppInfo.new_from_filename(str(file))
    if app is None: raise ValueError('Invalid desktop application')
    CONFIG.mkdir(parents=True,exist_ok=True)
    key = file.stem
    name = 'handhelddash-launch-'+key+'-'+str(os.getpid())
    script = CONFIG/(name+'.js')
    aliases = [value for value in (key.lower(),entry.get('StartupWMClass','').lower()) if value]
    script.write_text('const aliases='+json.dumps(aliases)+'; const output='+json.dumps('DSI-2' if screen == 'top' else 'DSI-1')+r''';
const deadline = Date.now()+30000;
function move(w) {
    if (Date.now()>deadline || !w.normalWindow) return;
    if (!aliases.includes(String(w.desktopFileName).replace(/\.desktop$/,'').toLowerCase()) && !aliases.includes(String(w.resourceClass).toLowerCase())) return;
    const target=workspace.screens.find(s=>s.name===output);
    if (target) workspace.sendClientToScreen(w,target);
}
workspace.windowAdded.connect(w => { move(w); w.desktopFileNameChanged.connect(() => move(w)); });
workspace.windowList().forEach(move);
''')
    def kwin(method,*args):
        return subprocess.run(['qdbus6','org.kde.KWin','/Scripting','org.kde.kwin.Scripting.'+method,*args],capture_output=True,text=True,check=True).stdout.strip()
    kwin('unloadScript',name)
    script_id = kwin('loadScript',str(script),name)
    subprocess.run(['qdbus6','org.kde.KWin','/Scripting/Script'+script_id,'org.kde.kwin.Script.run'],check=True)
    try:
        context = Gio.AppLaunchContext()
        for variable in ('XDG_ACTIVATION_TOKEN','DESKTOP_STARTUP_ID'):
            if variable in os.environ: context.setenv(variable,os.environ[variable])
        app.launch([],context)
        loop = GLib.MainLoop()
        GLib.timeout_add_seconds(30,lambda: (loop.quit(),False)[1])
        loop.run()
    finally:
        kwin('unloadScript',name)


if __name__ == '__main__':
    if sys.argv[1:] == ['--sync']: sync()
    elif len(sys.argv) == 3 and sys.argv[1] in ('top','bottom'): launch(*sys.argv[1:])
    else: raise SystemExit('Usage: desktop_launch.py --sync | top|bottom APP.desktop')
