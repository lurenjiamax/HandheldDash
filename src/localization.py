# SPDX-License-Identifier: LGPL-3.0-or-later
# Copyright (c) 2026 lurenjiamax
"""Small runtime catalog for the three supported interface languages."""
from PyQt6.QtCore import QLocale
from PyQt6.QtWidgets import QLabel as QtLabel, QPushButton as QtButton

LANGUAGE = 'en'
import json
import re
from pathlib import Path

file = Path(__file__).resolve().parent.parent/'packaging/translations.json'
if not file.exists(): file = Path('/usr/share/aynthor/translations.json')
CATALOG = json.loads(file.read_text(encoding='utf-8'))
PATTERN = re.compile('|'.join(('(?<!\\w)' if key[0].isalnum() else '')+re.escape(key)+('(?!\\w)' if key[-1].isalnum() else '') for key in sorted(CATALOG,key=len,reverse=True)))


def set_language(value):
    global LANGUAGE
    system = QLocale.system().name()
    LANGUAGE = value if value != 'system' else ('zh_TW' if system in ('zh_TW','zh_HK','zh_MO') else 'zh_CN' if system.startswith('zh') else 'en')
    if LANGUAGE not in ('en','zh_CN','zh_TW'): LANGUAGE = 'en'
    QLocale.setDefault(QLocale(LANGUAGE))


def tr(text):
    # One pass prevents replacement text from being translated a second time.
    return PATTERN.sub(lambda m:CATALOG[m[0]][LANGUAGE],text)


class Label(QtLabel):
    def __init__(self,text='',*args):
        super().__init__(*args); self.setText(text)

    def setText(self,text):
        self.source_text=text; super().setText(tr(text))

    def retranslate(self): super().setText(tr(self.source_text))


class Button(QtButton):
    def __init__(self,text='',*args):
        super().__init__(*args); self.setText(text)

    def setText(self,text):
        self.source_text=text; super().setText(tr(text))

    def retranslate(self): super().setText(tr(self.source_text))
