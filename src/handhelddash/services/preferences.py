"""User preferences and application configuration."""
import json
import os
from pathlib import Path

CONFIG=Path(os.environ.get('XDG_CONFIG_HOME',str(Path.home()/'.config')))/'aynthor'
DATA=Path(os.environ.get('XDG_DATA_HOME',str(Path.home()/'.local/share')))/'aynthor'
PREFS=CONFIG/'settings.json'


def preferences(catalog=None):
    defaults={'back':'escape','home':'desktop','back_command':'','home_command':'','fps_limit':60,'hud':True,'autolock':False,'language':'system','launch_screen':'','app_screens':{},'screenshot_mode':'top','panel_cpu_affinity':'little','mangohud_mode':'release','back-home':'reset-touchscreen','back-home_command':''}
    if PREFS.exists():
        try: defaults.update(json.loads(PREFS.read_text()))
        except (ValueError,OSError): pass
    if catalog and 'resident_tabs' in defaults:
        legacy={value:key for key,values in catalog.items() for value in values.values()}
        defaults['resident_tabs']=[legacy.get(title,title) for title in defaults['resident_tabs']]
    defaults.pop('mangohud_auto',None)
    return defaults


def save(data):
    CONFIG.mkdir(parents=True,exist_ok=True)
    stage=PREFS.with_suffix('.new'); stage.write_text(json.dumps(data,indent=2)); stage.replace(PREFS)


def mango_config(prefs):
    CONFIG.mkdir(parents=True,exist_ok=True)
    logs=Path('/var/cache/handhelddash/fps')
    if not logs.is_dir(): logs=DATA/'fps'
    logs.mkdir(parents=True,exist_ok=True)
    file=CONFIG/'MangoHud.conf'
    file.write_text(f"fps\nframetime\ncpu_stats\ngpu_stats\nfps_limit={prefs['fps_limit']}\nno_display={int(not prefs['hud'])}\noutput_folder={logs}\nautostart_log=1\nlog_interval=500\nlog_duration=0\ncontrol=aynthor-mango-%p\n")
    return file
