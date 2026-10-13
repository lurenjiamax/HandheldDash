// SPDX-License-Identifier: LGPL-3.0-or-later
// The script's registered name selects its JSON parameters over D-Bus.
const operation = readConfig('operation', '');
callDBus('org.aynthor.Control', '/Control', 'org.aynthor.Control',
    'DesktopScriptParameters', operation, function(raw) {
    const p = JSON.parse(raw);
    const windows = () => workspace.windowList();
    const find = () => windows().find(w => String(w.internalId) === p.identity);
    const focus = output => {
        const w = workspace.stackingOrder.slice().reverse().find(w =>
            w.normalWindow && !w.minimized && w.output && w.output.name === output &&
            !String(w.resourceClass).toLowerCase().includes('org.aynthor.control'));
        if (w) workspace.activeWindow = w;
    };
    if (p.operation === 'placement') {
        registerShortcut('HandheldDash Gamepad Focus', 'Focus selected gamepad screen', '', () => {
            if (p.gamepadFocus !== 'auto') focus(p.displays[p.gamepadFocus]);
        });
        function place(w, existing) {
            const prefix = 'HandheldDash Blank ';
            const app = String(w.resourceClass).toLowerCase();
            const blank = w.caption.startsWith(prefix);
            const panel = app.includes('org.aynthor.control');
            if (!blank && !panel && (existing || !w.normalWindow || w.skipTaskbar)) return;
            const name = blank ? w.caption.substring(prefix.length) : panel ? p.displays.bottom : p.rules[app] || p.defaultScreen;
            const screen = workspace.screens.find(s => s.name === name);
            if (!screen) return;
            workspace.sendClientToScreen(w, screen);
            if (blank || panel) { w.keepAbove = true; w.fullScreen = true; }
            if (panel) {
                const g = screen.geometry, f = w.frameGeometry;
                w.frameGeometry = {x:g.x+(g.width-f.width)/2, y:g.y+(g.height-f.height)/2, width:f.width, height:f.height};
            }
        }
        workspace.windowAdded.connect(w => place(w, false));
        windows().forEach(w => place(w, true));
        const report = () => callDBus('org.aynthor.Control', '/Control', 'org.aynthor.Control',
            'CursorPosition', JSON.stringify([workspace.cursorPos.x, workspace.cursorPos.y]));
        workspace.cursorPosChanged.connect(report); report();
    } else if (p.operation === 'touchpad') {
        focus(p.output);
        registerShortcut('HandheldDash Exit Touchpad', 'Exit HandheldDash touchpad mode', 'Esc', () =>
            callDBus('org.aynthor.Control', '/Control', 'org.aynthor.Control', 'ExitTouchpad'));
    } else if (p.operation === 'list') {
        const rows = windows().filter(w => w.normalWindow && !w.skipTaskbar && w.pid > 0 &&
            !String(w.resourceClass).toLowerCase().includes('org.aynthor.control'));
        callDBus('org.aynthor.Control', '/Control', 'org.aynthor.Control', 'WindowList', JSON.stringify(rows.map(w =>
            ({pid:w.pid, id:String(w.internalId), active:w.active, desktop:String(w.desktopFileName),
              caption:String(w.caption), app:String(w.resourceClass), screen:String(w.output ? w.output.name : '')}))));
    } else if (p.operation === 'move') {
        const w = find(), s = workspace.screens.find(s => s.name === p.output);
        if (w && s) workspace.sendClientToScreen(w, s);
    } else if (p.operation === 'activate') {
        const w = find(); if (w) { w.minimized = false; workspace.activeWindow = w; }
    } else if (p.operation === 'swap') {
        const w = workspace.activeWindow, screens = workspace.screens;
        if (w && screens.length > 1) workspace.sendClientToScreen(w,
            screens[(screens.findIndex(s => s.name === w.output.name)+1)%screens.length]);
    }
});
