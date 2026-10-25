"""Only the KWin rules owned by window-focus protection are managed here."""
import configparser
import hashlib
from PyQt6.QtDBus import QDBusInterface


def update_focus_rules(config,session,targets: list[dict]) -> None:
    path=config.parent/'kwinrulesrc'
    rules=configparser.ConfigParser(interpolation=None,strict=False); rules.optionxform=str
    if path.exists(): rules.read(path,encoding='utf-8')
    prefix='handhelddash-focus-'
    desired={}
    for target in targets:
        app=str(target.get('app','')).lower(); title=str(target.get('caption',''))
        if not app or not title: continue
        identity=prefix+hashlib.sha256((app+'\0'+title).encode()).hexdigest()[:16]
        desired[identity]={'Description':'HandheldDash window focus protection',
            'wmclass':app,'wmclassmatch':'1','title':title,'titlematch':'1',
            'minimize':'false','minimizerule':'2'}
    existing={section:dict(rules[section]) for section in rules.sections() if section.startswith(prefix)}
    if existing==desired: return
    ids=[value for value in rules.get('General','rules',fallback='').split(',') if value and not value.startswith(prefix)]
    for section in existing: rules.remove_section(section)
    for section,values in desired.items(): rules[section]=values
    if not rules.has_section('General'): rules.add_section('General')
    ids=list(desired)+ids
    rules['General']['rules']=','.join(ids); rules['General']['count']=str(len(ids))
    path.parent.mkdir(parents=True,exist_ok=True); stage=path.with_suffix('.handhelddash-new')
    with stage.open('w',encoding='utf-8') as stream: rules.write(stream,space_around_delimiters=False)
    stage.replace(path)
    QDBusInterface('org.kde.KWin','/KWin','org.kde.KWin',session).asyncCall('reconfigure')
