# SPDX-License-Identifier: LGPL-3.0-or-later
from handhelddash.ui.common import QDialog, QGridLayout, QHBoxLayout, QLabel, QScrollArea, QSpinBox, QTimer, QVBoxLayout, QWidget, Qt, tr
from handhelddash.ui.widgets.buttons import StateButton
from handhelddash.ui.widgets.fan import FanCurve
from handhelddash.ui.widgets.sliders import TouchSlider

class FanPageMixin:
    @staticmethod
    def fan_link_choices():
        return [(True,'Default','fan'),(False,'Manual','fan')]

    def set_fan_follow(self,value):
        self.fan_edit_timer.stop(); self.write_queue.pop('fan-curve',None); self.fan_dirty=False
        self.fan_graph.dragging=False
        if value:
            if self.fan_graph.curve: self.load_fan_curve(self.fan_graph.curve,False)
        else:
            curve=self.state.get('fan_control',{}).get('curves',{}).get('custom')
            if curve: self.load_fan_curve(curve,True)
        self.set('fan-follow-performance',['on' if value else 'off'])

    def make_fan(self):
        layout=self.page('Fan'); self.fan_dirty=False; self.fan_loading=False
        self.fan_performance=QLabel('—'); layout.addWidget(self.fan_performance)
        row=QHBoxLayout()
        self.fan_profile=QLabel('—')
        self.fan_sensor=StateButton('Fan sensor',[('max','Hottest sensor','thermometer'),('average','Average sensors','activity')],lambda v:self.set('fan-sensor-mode',[v]))
        self.fan_follow=StateButton('Fan linkage',self.fan_link_choices(),self.set_fan_follow)
        row.addWidget(self.fan_follow,1)
        row.addWidget(self.fan_profile,1); row.addWidget(self.fan_sensor,1); layout.addLayout(row)
        self.fan_graph=FanCurve(); self.fan_graph.pointChanged.connect(self.edit_fan_point); layout.addWidget(self.fan_graph,1)
        self.fan_reading=QLabel('—'); layout.addWidget(self.fan_reading)
        self.fan_edit_timer=QTimer(self); self.fan_edit_timer.setSingleShot(True); self.fan_edit_timer.setInterval(120); self.fan_edit_timer.timeout.connect(self.apply_fan_curve)
        self.fan_dialog=QDialog(self); self.fan_dialog.setWindowTitle(tr('Advanced values')); dialog_layout=QVBoxLayout(self.fan_dialog)
        advanced=self.button('Advanced values',self.fan_dialog.show); layout.addWidget(advanced)
        scroll=QScrollArea(); scroll.setWidgetResizable(True); scroll.setMinimumHeight(250)
        editor=QWidget(); grid=QGridLayout(editor); grid.setContentsMargins(8,4,8,4)
        self.fan_points=[]
        for i in range(7):
            temp=QSpinBox(); temp.setRange(20,95); temp.setSuffix(' °C'); temp.setFixedWidth(90)
            speed=TouchSlider(Qt.Orientation.Horizontal); speed.setRange(0,100)
            value=QLabel('—%'); value.setFixedWidth(45)
            speed.valueChanged.connect(lambda n,l=value:l.setText(f'{n}%'))
            speed.valueChanged.connect(self.edit_fan_curve); temp.valueChanged.connect(self.edit_fan_curve)
            grid.addWidget(temp,i,0); grid.addWidget(speed,i,1); grid.addWidget(value,i,2)
            self.fan_points.append((temp,speed))
        scroll.setWidget(editor); dialog_layout.addWidget(scroll); dialog_layout.addWidget(self.button('Close',self.fan_dialog.close)); self.fan_dialog.resize(510,370)

    def load_fan_curve(self,curve,editable=False):
        self.fan_loading=True
        self.fan_graph.editable=editable
        if not editable: self.fan_graph.selected=None; self.fan_graph.dragging=False
        self.fan_graph.curve=curve; self.fan_graph.update()
        for i,(temp,speed) in enumerate(self.fan_points):
            temp.setRange(20,95); temp.setValue(round(curve['temperatures'][i]/1000)); speed.setValue(round(curve['pwm'][i]/2.55))
            temp.setEnabled(editable); speed.setEnabled(editable and i<6)
        self.fan_loading=False

    def edit_fan_curve(self,*args):
        if self.fan_loading: return
        self.fan_dirty=True
        self.fan_loading=True
        for i,(temp,speed) in enumerate(self.fan_points):
            low=self.fan_points[i-1][0].value()+1 if i else 20
            high=self.fan_points[i+1][0].value()-1 if i<6 else 95
            temp.setRange(low,high)
            speed.setValue(100 if i==6 else max(self.fan_points[i-1][1].value() if i else 0,min(self.fan_points[i+1][1].value(),speed.value())))
        self.fan_loading=False
        self.fan_graph.curve={'temperatures':[temp.value()*1000 for temp,speed in self.fan_points],'pwm':[round(speed.value()*2.55) for temp,speed in self.fan_points]}
        self.fan_graph.update()
        if not self.fan_edit_timer.isActive(): self.fan_edit_timer.start()

    def edit_fan_point(self,index,temp,percent):
        self.fan_loading=True
        temperature,speed=self.fan_points[index]
        temperature.setValue(temp); speed.setValue(percent)
        self.fan_loading=False; self.edit_fan_curve()

    def apply_fan_curve(self):
        curve=self.fan_graph.curve
        if not curve: return
        temps=curve['temperatures']; speeds=curve['pwm']
        if any(a>=b for a,b in zip(temps,temps[1:])) or any(a>b for a,b in zip(speeds,speeds[1:])) or speeds[-1]!=255:
            self.notify('Temperatures must rise, speeds must not fall, final speed must be 100%'); return
        self.set('fan-curve',list(map(str,temps+speeds)))

    def update_fan(self):
        performance=self.state.get('performance','standard')
        self.fan_performance.setText(tr({'quiet':'Quiet','standard':'Balanced','performance':'Performance','custom':'Custom'}.get(performance,performance)))
        self.fan_follow.show_value(self.state.get('fan_follow_performance',True))
        control=self.state.get('fan_control',{})
        self.fan_graph.temperature=control.get('temperature',0)/1000
        self.fan_graph.update()
        if self.fan_dirty or self.write_queue or self.fan_graph.dragging: return
        profile=self.state.get('fan_profile','moderate')
        if profile=='auto': profile='moderate'
        self.fan_profile.setText(tr({'quiet':'Quiet','moderate':'Balanced','aggressive':'Active cooling','custom':'Custom'}.get(profile,profile))); self.fan_sensor.show_value(self.state.get('fan_sensor_mode','max'))
        curve=control.get('curves',{}).get(profile)
        if curve: self.load_fan_curve(curve,profile=='custom')
        self.fan_reading.setText(f"{self.fan_graph.temperature:.1f} °C · {self.state.get('fan_rpm') or 0:.0f} RPM · PWM {self.state.get('fan_percent') or 0:.0f}%")

