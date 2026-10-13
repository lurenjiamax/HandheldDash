# SPDX-License-Identifier: LGPL-3.0-or-later
from handhelddash.ui.common import DEVICE, Path, QApplication, QImage, QProcess, QStandardPaths, time, tr

class CapturePageMixin:
    @staticmethod
    def screenshot_choices():
        return [('region','Region capture','camera'),('top','Top screen capture','monitor'),('bottom','Bottom screen capture','monitor')]

    def set_screenshot_mode(self,value):
        if value not in ('region','top','bottom'): return
        self.set_pref('screenshot_mode',value)
        self.shot.show_value(value)

    def screenshot(self):
        if not self.desktop.supports('screenshot'):
            self.notify('Screenshot is not supported by '+self.desktop.name); return
        if getattr(self,'screenshot_process',None): return
        mode = self.prefs.get('screenshot_mode','top')
        if mode not in ('region','top','bottom'): mode='top'
        geometries = {screen.name():screen.geometry() for screen in QApplication.screens()}
        name = DEVICE.screen_name(mode,QApplication.screens())
        if mode != 'region' and name not in geometries:
            self.error_text = tr('Capture screen is unavailable'); self.notify(self.error_text); return
        folder = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.PicturesLocation))/'AYN Thor'
        try: folder.mkdir(parents=True,exist_ok=True)
        except OSError as exc: self.error_text=str(exc); self.notify(self.error_text); return
        target = folder/(time.strftime('%Y%m%d-%H%M%S')+f'-{mode}-{time.time_ns()%1000000000:09d}.png')
        process = QProcess(self); self.screenshot_process = process
        def done(code=1,*args):
            if self.screenshot_process is not process: return
            self.screenshot_process = None
            error = bytes(process.readAllStandardError()).decode(errors='replace')
            success = code == 0 and target.is_file() and target.stat().st_size
            if success and mode != 'region':
                image = QImage(str(target)); bounds = next(iter(geometries.values()))
                for geometry in geometries.values(): bounds = bounds.united(geometry)
                sx = image.width()/bounds.width(); sy = image.height()/bounds.height()
                if image.isNull() or abs(sx-sy)*max(bounds.width(),bounds.height()) > 2:
                    success = False; error = tr('Capture size does not match screen layout')
                else:
                    g = geometries[name]
                    x = round((g.x()-bounds.x())*sx); y = round((g.y()-bounds.y())*sy)
                    right = round((g.x()+g.width()-bounds.x())*sx); bottom = round((g.y()+g.height()-bounds.y())*sy)
                    success = image.copy(x,y,right-x,bottom-y).save(str(target))
            if success: self.start('notify-send',tr('Screenshot'),str(target))
            elif mode == 'region' and code == 0 and not target.exists(): self.showFullScreen()
            else:
                self.error_text = tr('Screenshot failed')+' · '+error
                self.showFullScreen(); self.notify(self.error_text)
            process.deleteLater()
        process.finished.connect(done)
        process.errorOccurred.connect(lambda e:done() if e == QProcess.ProcessError.FailedToStart else None)
        self.hide()
        self.desktop.capture(process,mode,target)

