# SPDX-License-Identifier: LGPL-3.0-or-later
from handhelddash.ui.common import DEVICE, ICON_SIZE, Path, QApplication, QGridLayout, QHBoxLayout, QIcon, QLabel, QMenu, QSize, QTimer, Qt, tr
from handhelddash.ui.widgets.buttons import TaskButton
from handhelddash.ui.widgets.icons import control_icon
from handhelddash.ui.widgets.affinity import AffinityPopup

class TasksPageMixin:
    def make_tasks(self):
        self.tasks_index = self.tabs.count()
        layout = self.page('Tasks')
        self.task_page = 0; self.task_records = []; self.selected_task = None
        self.task_buttons = []
        grid = QGridLayout(); layout.addLayout(grid)
        for i in range(6):
            button = TaskButton('—'); button.clicked.connect(lambda checked=False,index=i:self.select_task(index))
            button.held.connect(lambda index=i:self.task_menu(index))
            button.setMinimumHeight(62); button.setIconSize(QSize(ICON_SIZE,ICON_SIZE)); grid.addWidget(button,i//2,i%2); self.task_buttons.append(button)
        row = QHBoxLayout()
        row.addWidget(self.button('Previous',lambda:self.change_task_page(-1)))
        self.task_count = QLabel('0 / 0'); self.task_count.setAlignment(Qt.AlignmentFlag.AlignCenter); row.addWidget(self.task_count,1)
        row.addWidget(self.button('Next',lambda:self.change_task_page(1))); layout.addLayout(row)
        row = QHBoxLayout(); row.addWidget(self.button('Refresh',self.refresh_tasks));  layout.addLayout(row)
        layout.addStretch()
        self.tabs.currentChanged.connect(lambda i:self.refresh_tasks() if i==self.tasks_index else None)

    def refresh_tasks(self):
        if not self.desktop.list_windows(): self.WindowList('[]')

    def change_task_page(self,delta):
        count=max(1,(len(self.task_records)+5)//6); self.task_page=max(0,min(count-1,self.task_page+delta)); self.selected_task=None
        self.task_count.setText(f'{self.task_page+1} / {count}')
        for i,button in enumerate(self.task_buttons):
            index=self.task_page*6+i; button.setChecked(False); button.setEnabled(index<len(self.task_records))
            record=self.task_records[index] if index<len(self.task_records) else None
            text=(record['caption'][:24]+' · '+tr('Top screen' if record.get('screen')==DEVICE.screen_name('top',QApplication.screens()) else 'Bottom screen' if record.get('screen')==DEVICE.screen_name('bottom',QApplication.screens()) else 'Other screen')) if record else '—'
            button.setIcon(self.app_icon(record) if record else QIcon())
            button.setToolTip(record['caption'] if record else '')
            button.setText(text); button.setVisible(record is not None)

    def app_icon(self, record):
        import configparser
        desktop = record.get('desktop') or record['app']
        for folder in [Path.home()/'.local/share/applications', Path('/usr/local/share/applications'), Path('/usr/share/applications')]:
            file = folder / (desktop if desktop.endswith('.desktop') else desktop+'.desktop')
            if file.is_file():
                parser = configparser.ConfigParser(interpolation=None, strict=False)
                try:
                    parser.read(file,encoding='utf-8')
                    name = parser.get('Desktop Entry','Icon',fallback='application-x-executable')
                    return QIcon(name) if name.startswith('/') else QIcon.fromTheme(name,control_icon('monitor'))
                except (configparser.Error,UnicodeError,OSError):
                    pass
        return QIcon.fromTheme(desktop,control_icon('monitor'))

    def task_menu(self,index):
        offset = self.task_page*6+index
        if offset >= len(self.task_records): return
        record = dict(self.task_records[offset]); menu = QMenu(self)
        for role,title in [('top','Move to top screen'),('bottom','Move to bottom screen')]:
            name=DEVICE.screen_name(role,QApplication.screens())
            if not name: continue
            action = menu.addAction(control_icon('monitor'),tr(title))
            action.triggered.connect(lambda checked=False,n=name:self.move_task(record,n))
        menu.addSeparator()
        saved = self.prefs.get('app_screens',{}).get(record['app'].lower(),'')
        for role,title in [('top','Always open on top screen'),('bottom','Always open on bottom screen'),('','Use default screen')]:
            name=DEVICE.screen_name(role,QApplication.screens()) if role else ''
            if role and not name: continue
            action = menu.addAction(tr(title)); action.setCheckable(True); action.setChecked(name==saved)
            action.triggered.connect(lambda checked=False,n=name:self.remember_task_screen(record,n))
        menu.addSeparator()
        action = menu.addAction(control_icon('circle-x'),tr('Force close'))
        pid = int(record.get('pid') or 0)
        try: started = Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()[19]
        except (OSError,IndexError): started = ''
        affinity_action = menu.addAction(tr('CPU affinity…'))
        affinity_action.setEnabled(pid > 1 and bool(started))
        affinity_action.triggered.connect(lambda:self.edit_task_affinity(pid,started))
        action.setEnabled(pid > 1 and bool(started))
        action.triggered.connect(lambda:self.force_close_task(pid,started))
        menu.exec(self.task_buttons[index].mapToGlobal(self.task_buttons[index].rect().center()))

    def edit_task_affinity(self,pid,started):
        try: popup = AffinityPopup(self,pid,started)
        except OSError as error:
            self.notify(str(error)); return
        popup.finished.connect(popup.deleteLater)
        popup.finished.connect(lambda _:popup.scrim.deleteLater())
        popup.show()

    def force_close_task(self,pid,started):
        self.call('Set',['kill-task',[str(pid),started]],lambda _:self.refresh_tasks())

    def remember_task_screen(self,record,name):
        rules = dict(self.prefs.get('app_screens',{})); key = record['app'].lower()
        if name: rules[key] = name
        else: rules.pop(key,None)
        self.set_pref('app_screens',rules); self.install_placement()
        if name: self.move_task(record,name)

    def move_task(self,record,name):
        if not self.desktop.move_window(record['id'],name): return
        QTimer.singleShot(550,self.refresh_tasks)

    def select_task(self,index):
        record=self.task_records[self.task_page*6+index]
        self.desktop.activate_window(record['id'])
