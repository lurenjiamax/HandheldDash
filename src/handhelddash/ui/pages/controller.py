# SPDX-License-Identifier: LGPL-3.0-or-later
from handhelddash.ui.common import CHOICE_POPUP_HEIGHT, CHOICE_POPUP_WIDTH, ControllerChoicePage, EmbeddedPopup, POPUP_MARGIN, QTabWidget, QVBoxLayout, json, tr

class ControllerPageMixin:
    def open_input_profiles(self):
        self.input_mode.show_value(self.state.get('joystick','gamepad'))
        def received(raw):
            plans=json.loads(raw); profiles=plans['profiles']; outputs=plans['outputs']
            self.input_mode.options=[(item['id'],item['name'],'mouse' if item['id']=='mouse' else 'gamepad') for item in profiles]
            self.input_mode.show_value(self.state.get('joystick','gamepad'))
            popup=EmbeddedPopup(self); box=QVBoxLayout(popup); box.setContentsMargins(12,12,12,12); box.setSpacing(6)
            popup.setWindowTitle(tr('Controller plan'))
            tabs=QTabWidget(); tabs.setMinimumSize(0,0); tabs.setStyleSheet('QTabBar::tab { min-height:36px; padding:4px 10px; }'); box.addWidget(tabs,1)
            draft={'profile':plans['profile'],'output':plans['output']}
            pages={}
            def selected(value,key):
                if value==draft[key]: return
                previous=draft[key]; draft[key]=value; tabs.setEnabled(False)
                def finished(success,busy):
                    tabs.setEnabled(True)
                    if not success:
                        draft[key]=previous; pages[key].selected=previous; pages[key].rebuild()
                        popup.setToolTip(self.error_text or tr('Failed to apply controller plan'))
                self.set('controller-plan',[draft['profile'],draft['output']],finished)
            for key,title,items in [('profile','Input mapping',profiles),('output','Output controller',outputs)]:
                content=ControllerChoicePage(self,items,draft[key],lambda value,field=key:selected(value,field),key=='output')
                pages[key]=content
                tabs.addTab(content,tr(title))
            popup.setFixedSize(min(CHOICE_POPUP_WIDTH,self.width()-2*POPUP_MARGIN),min(CHOICE_POPUP_HEIGHT,self.height()-2*POPUP_MARGIN)); popup.show()
        self.call('ControllerPlans',[],received)

