"""Remove obsolete HandheldDash minimization rules without touching user rules."""
import configparser
from PyQt6.QtDBus import QDBusInterface


def remove_focus_rules(config,session) -> None:
    path=config.parent/'kwinrulesrc'
    rules=configparser.ConfigParser(interpolation=None,strict=False); rules.optionxform=str
    if path.exists(): rules.read(path,encoding='utf-8')
    prefix='handhelddash-focus-'
    existing={section:dict(rules[section]) for section in rules.sections() if section.startswith(prefix)}
    if not existing: return
    order='Order' if rules.has_option('General','Order') else 'rules'
    ids=[value for value in rules.get('General',order,fallback='').split(',') if value and not value.startswith(prefix)]
    for section in existing: rules.remove_section(section)
    if not rules.has_section('General'): rules.add_section('General')
    rules['General'][order]=','.join(ids)
    if order=='rules': rules['General']['count']=str(len(ids))
    path.parent.mkdir(parents=True,exist_ok=True); stage=path.with_suffix('.handhelddash-new')
    with stage.open('w',encoding='utf-8') as stream: rules.write(stream,space_around_delimiters=False)
    stage.replace(path)
    QDBusInterface('org.kde.KWin','/KWin','org.kde.KWin',session).asyncCall('reconfigure')
