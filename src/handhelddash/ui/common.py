# SPDX-License-Identifier: LGPL-3.0-or-later

"""Unprivileged, touch-friendly Thor control panel and settings."""


from array import array

import math

from functools import lru_cache

import json

import os

from pathlib import Path

import shlex

import sys

import time

from PyQt6.QtCore import QMetaType, QProcess, QTimer, Qt, QEvent, QSize, QRectF, QPointF, QLocale, QTranslator, QLibraryInfo, QStandardPaths, QMimeData, pyqtClassInfo, pyqtSlot, pyqtSignal

from PyQt6.QtDBus import QDBus, QDBusArgument, QDBusAbstractAdaptor, QDBusConnection, QDBusInterface, QDBusMessage

from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap, QPolygonF, QImage, QConicalGradient, QBrush, QPalette, QDrag

from PyQt6.QtWidgets import QLabel as PlainLabel

from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton, QTabWidget, QTabBar, QProgressBar, QSlider, QStackedWidget, QFormLayout, QLineEdit, QColorDialog, QMenu, QStyle, QStyleOptionSlider, QStyleOptionButton, QStylePainter, QScrollArea, QSpinBox, QDialog, QProxyStyle, QSizePolicy)

sys.path.append('/usr/lib/aynthor')

from localization import Label as QLabel, Button as LocalizedButton, set_language, tr, CATALOG

from handhelddash.devices import DEVICE

from handhelddash.desktop import detect_desktop

from handhelddash.services.hardware_client import HardwareClient
from handhelddash.services.preferences import CONFIG, DATA, PREFS, preferences, save, mango_config

from handhelddash.services.buildinfo import build_identity

from handhelddash.protocol import HARDWARE_SERVICE as NAME, HARDWARE_PATH as PATH, CONTROL_SERVICE as APP

from handhelddash.ui.theme import THEME, theme_color

from handhelddash.ui.popups import EmbeddedPopup, ControllerChoicePage

from handhelddash.ui.adjustments import AdjustmentRow

from handhelddash.ui.design import ICON_SIZE, POPUP_WIDTH, CHOICE_POPUP_WIDTH, CHOICE_POPUP_HEIGHT, POPUP_MARGIN


VERSION_FILE = Path('/usr/share/aynthor/version')

VERSION = VERSION_FILE.read_text().strip() if VERSION_FILE.is_file() else '1.0.0-dev'

BUILD = build_identity("/usr/bin/aynthor-control" if Path(__file__).is_relative_to("/usr/lib/aynthor") else __file__)


ACTIONS = {'escape': 'Esc', 'desktop': 'Show desktop', 'overview': 'Overview', 'panel': 'Control panel', 'screenshot': 'Screenshot', 'swap': 'Move to other display', 'none': 'Disabled', 'command': 'Custom command', 'reset-touchscreen':'Reset touchscreen driver'}

DASHBOARD_COMPONENTS = {
    'controls': [('performance','Performance'),('fan_link','Fan linkage'),('input','Controller plan'),('focus','Window focus'),('caffeine','Caffine'),('vibration','Vibration'),('lighting','Lighting'),('bypass','Bypass charging')],
    'metrics': [('cpu','CPU'),('gpu','GPU'),('temp','Temperature'),('fan','Fan'),('ram','RAM'),('battery','Power')],
    'actions': [('screenshot','Screenshot'),('overview','Overview'),('hud','FPS overlay')],
}

DASHBOARD_SECTIONS = {'controls':'Quick controls','metrics':'Live metrics','actions':'Quick actions'}

DASHBOARD_TILES = {
    'performance': ('Performance mode','gauge'), 'fan_link': ('Fan mode','fan'),
    'input': ('Controller plan','gamepad-2'), 'focus': ('Window focus','monitor'),
    'caffeine': ('Caffine','coffee'), 'vibration': ('Vibration','vibrate'),
    'lighting': ('Lighting','palette'), 'screenshot': ('Screenshot','camera'),
    'overview': ('Overview','panels-top-left'), 'hud': ('FPS overlay','eye'),
    'brightness': ('Brightness','sun'), 'volume': ('Volume','volume-2'),
    'move_app': ('Move current app','arrow-left-right'),
    'fps_cap': ('FPS limit','gauge'),
}

CORE_TILES = ('performance','fan_link')

METRIC_TITLES = {'cpu':'CPU','gpu':'GPU','temperature':'Temperature','fan':'Fan','memory':'RAM','battery':'Power','load':'System load','network':'Network speed','disk_io':'Disk IO'}

METRIC_ICONS = {'cpu':'cpu','gpu':'gpu','temperature':'thermometer','fan':'fan','memory':'memory-stick','battery':'plug-zap','load':'activity','network':'network','disk_io':'disk'}

DEFAULT_TILES = ['performance','fan_link','input','focus','caffeine','vibration','lighting','screenshot','overview','hud','brightness','volume','fps_cap']

TILE_MIME = 'application/x-handhelddash-tile'

def dashboard_preset(name='default'):
    tiles = {
        'gaming': ['performance','fan_link','input','focus','vibration','screenshot','hud','volume'],
        'monitoring': ['performance','fan_link','caffeine','brightness','volume','screenshot'],
    }.get(name,DEFAULT_TILES)
    return {'version':6,'tiles':list(CORE_TILES)+[key for key in tiles if key not in CORE_TILES],'primary_tiles':list(CORE_TILES),'metrics':True}

def dashboard_layout(raw):
    """Validate tile IDs and migrate the original section-based layout."""
    defaults = dashboard_preset()
    if not isinstance(raw,dict): return defaults
    if 'tiles' in raw:
        if not isinstance(raw['tiles'],list): return defaults
        tiles = []
        for key in raw['tiles']:
            if isinstance(key,str) and key in DASHBOARD_TILES and key not in tiles: tiles.append(key)
        if raw.get('version') in (None,1,2,3,4,5) and raw.get('show_cap',True) and 'fps_cap' not in tiles: tiles.append('fps_cap')
        result={'version':6,'tiles':tiles,'metrics':raw.get('metrics') if isinstance(raw.get('metrics'),bool) else True}
        primary=raw.get('primary_tiles',tiles[:2])
        result['primary_tiles']=list(dict.fromkeys(key for key in primary if isinstance(key,str) and key in tiles)) if isinstance(primary,list) else tiles[:2]
        swipes=raw.get('swipe_regions',{})
        result['swipe_regions']={key:not isinstance(swipes,dict) or swipes.get(key,True) is not False for key in ('metrics','primary','shortcuts')}
        result['metric_mode']='percent' if raw.get('metric_mode') == 'percent' else 'mhz'
        modes=raw.get('metric_modes',{})
        result['metric_modes']={key:('percent' if isinstance(modes,dict) and modes.get(key,raw.get('metric_mode')) == 'percent' else 'mhz') for key in ('cpu','gpu')}
        sources=raw.get('metric_sources',{})
        result['metric_sources']={key:(sources[key][:100] if isinstance(sources,dict) and isinstance(sources.get(key),str) else 'all') for key in ('network','disk_io')}
        order=raw.get('metric_order',['cpu','gpu','temperature','fan','memory','battery'])
        result['metric_order']=list(dict.fromkeys(key for key in order if isinstance(key,str) and key in METRIC_TITLES)) if isinstance(order,list) else ['cpu','gpu','temperature','fan','memory','battery']
        return result
    if not any(isinstance(raw.get(section),list) for section in ('controls','actions','metrics')): return defaults
    tiles = []
    for section in ('controls','actions'):
        values = raw.get(section)
        if not isinstance(values,list):
            tiles.extend(key for key in defaults['tiles'] if key in dict(DASHBOARD_COMPONENTS[section]) and key not in tiles)
            continue
        seen = set()
        for item in values:
            if not isinstance(item,dict): continue
            key = item.get('id')
            if not isinstance(key,str) or key not in dict(DASHBOARD_COMPONENTS[section]) or key in seen: continue
            seen.add(key)
            if key in DASHBOARD_TILES and item.get('visible',True) is not False: tiles.append(key)
        tiles.extend(key for key in defaults['tiles'] if key in dict(DASHBOARD_COMPONENTS[section]) and key not in seen)
    metrics = raw.get('metrics')
    visible_metrics = any(isinstance(item,dict) and item.get('visible',True) is not False for item in metrics) if isinstance(metrics,list) else True
    return {'version':3,'tiles':list(CORE_TILES)+[key for key in tiles if key not in CORE_TILES],'metrics':visible_metrics}
