# SPDX-License-Identifier: LGPL-3.0-or-later
"""Touch-only process affinity selector, embedded in the panel surface."""
from pathlib import Path
import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QGridLayout, QHBoxLayout, QScrollArea, QVBoxLayout, QWidget
from localization import Label as QLabel, tr
from handhelddash.ui.design import POPUP_MARGIN, SPACING, TOUCH_SIZE
from handhelddash.ui.popups import EmbeddedPopup


def cpu_choices() -> list[dict]:
    """Rank hardware capacity, falling back to maximum frequency, never live MHz."""
    cores = []
    for node in Path('/sys/devices/system/cpu').glob('cpu[0-9]*'):
        def number(relative: str) -> int:
            try: return int((node/relative).read_text().strip())
            except (OSError, ValueError): return 0
        online = not (node/'online').exists() or number('online') == 1
        cores.append({'cpu':int(node.name[3:]), 'capacity':number('cpu_capacity'),
                      'maximum':number('cpufreq/cpuinfo_max_freq'), 'online':online})
    field = 'capacity' if cores and all(core['capacity'] for core in cores) else 'maximum'
    levels = sorted({core[field] for core in cores if core[field]})
    names = {1:['CPU core'], 2:['Small core','Big core'],
             3:['Small core','Middle core','Big core'],
             4:['Small core','Middle core','Big core','Prime core']}.get(len(levels))
    for core in cores:
        rank = levels.index(core[field]) if core[field] in levels else None
        core['tier'] = names[rank] if names and rank is not None else 'CPU core'
        core['group'] = core[field]
    return sorted(cores,key=lambda core:core['cpu'])


class AffinityPopup(EmbeddedPopup):
    def __init__(self, panel, pid: int, started: str):
        current = os.sched_getaffinity(pid)
        super().__init__(panel)
        self.pid = pid; self.started = started
        cores = cpu_choices(); self.core_buttons = {}
        self.setWindowTitle(tr('CPU affinity'))
        box = QVBoxLayout(self); box.setContentsMargins(12,12,12,12); box.setSpacing(SPACING)
        title = QLabel('CPU affinity'); title.setObjectName('HeaderTitle'); box.addWidget(title)
        note = QLabel('Maximum hardware frequency · current selection follows the main thread')
        note.setWordWrap(True); box.addWidget(note)
        presets = QGridLayout()
        all_button = panel.button('All cores',lambda:self.select({core['cpu'] for core in cores if core['online']}))
        all_button.setMinimumHeight(TOUCH_SIZE); presets.addWidget(all_button,0,0)
        groups = sorted({core['group'] for core in cores})
        for index,group in enumerate(groups):
            members = [core for core in cores if core['group'] == group]
            label = tr(members[0]['tier'])
            if len(groups) > 4: label += f' · {index+1}'
            button = panel.button(label,lambda checked=False,items=members:self.select({core['cpu'] for core in items if core['online']}))
            button.setMinimumHeight(TOUCH_SIZE); presets.addWidget(button,(index+1)//2,(index+1)%2)
        box.addLayout(presets)
        area = QScrollArea(); area.setWidgetResizable(True); area.setFrameShape(QScrollArea.Shape.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget(); grid = QGridLayout(content); grid.setContentsMargins(0,0,0,0); grid.setSpacing(SPACING)
        columns = 4 if panel.width() >= 560 else 2
        for index,core in enumerate(cores):
            frequency = f"{core['maximum']/1_000_000:.2f} GHz" if core['maximum'] else tr('Unknown')
            label = f"CPU {core['cpu']}\n{tr(core['tier'])}\n{frequency}" if core['online'] else f"CPU {core['cpu']}\n{tr('Offline')}"
            button = panel.button(label,lambda:None); button.setCheckable(True)
            button.setChecked(core['cpu'] in current); button.setEnabled(core['online'])
            button.setMinimumSize(0,80); button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.toggled.connect(self.update_selection)
            grid.addWidget(button,index//columns,index%columns); self.core_buttons[core['cpu']] = button
        area.setWidget(content); box.addWidget(area,1)
        self.summary = QLabel(); box.addWidget(self.summary)
        footer = QLabel('Applies to existing threads · not saved for future launches')
        footer.setWordWrap(True); box.addWidget(footer)
        row = QHBoxLayout(); self.cancel_button = panel.button('Cancel',self.reject)
        self.apply_button = panel.button('Apply',self.apply_selection)
        for button in (self.cancel_button,self.apply_button): button.setMinimumHeight(TOUCH_SIZE)
        row.addWidget(self.cancel_button); row.addWidget(self.apply_button); box.addLayout(row)
        self.setFixedSize(min(560,panel.width()-2*POPUP_MARGIN),min(490,panel.height()-2*POPUP_MARGIN))
        self.update_selection()

    def selected_cpus(self) -> list[int]:
        return [cpu for cpu,button in self.core_buttons.items() if button.isEnabled() and button.isChecked()]

    def update_selection(self) -> None:
        if not hasattr(self,'apply_button'): return
        cpus = self.selected_cpus()
        self.apply_button.setEnabled(bool(cpus))
        self.summary.setText(tr('Selected cores')+': '+(', '.join(map(str,cpus)) or '—'))

    def select(self, cpus: set[int]) -> None:
        for cpu,button in self.core_buttons.items(): button.setChecked(cpu in cpus and button.isEnabled())

    def apply_selection(self) -> None:
        cpus = self.selected_cpus()
        if not cpus: return
        self.setProperty('applying',True); self.setEnabled(False)
        def finished(success, busy):
            self.setProperty('applying',False); self.setEnabled(True); self.update_selection()
            if success:
                self.accept(); self.panel.refresh_tasks()
            else:
                self.summary.setText(self.panel.error_text or tr('Failed to apply CPU affinity'))
                self.summary.setWordWrap(True)
        self.panel.call('Set',['task-affinity',[str(self.pid),self.started,','.join(map(str,cpus))]],
                        quiet=True,finished=finished)
