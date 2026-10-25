// SPDX-License-Identifier: LGPL-3.0-or-later
// One resident script; all dynamic data arrives over D-Bus.
let preferences = {rules:{}, displays:{}, defaultScreen:'', gamepadFocus:'auto'};
let touchpad = false, panelRequested = false, previousWindow = null;
const windows = () => workspace.windowList();
const isPanel = w => String(w.resourceClass).toLowerCase().includes('org.aynthor.control') &&
    String(w.caption).startsWith('HandheldDash');
const send = (method, data) => callDBus('org.aynthor.Control', '/Control', 'org.aynthor.Control', method, data);
function focus(output) {
    const w = workspace.stackingOrder.slice().reverse().find(w =>
        w.normalWindow && !w.minimized && w.output && w.output.name === output && !isPanel(w));
    if (w) workspace.activeWindow = w;
}
function activatePanel(w) {
    if (!panelRequested || !isPanel(w)) return;
    const active = workspace.activeWindow;
    if (active && !isPanel(active) && !previousWindow) previousWindow = active;
    w.minimized = false; w.keepAbove = true; workspace.activeWindow = w;
}
function place(w, existing) {
    const prefix = 'HandheldDash Blank ', blank = String(w.caption).startsWith(prefix);
    const panel = isPanel(w), app = String(w.resourceClass).toLowerCase();
    if (!blank && !panel && (existing || !w.normalWindow || w.skipTaskbar)) return;
    const name = blank ? w.caption.substring(prefix.length) : panel ? preferences.displays.bottom :
        preferences.rules[app] || preferences.defaultScreen;
    const screen = workspace.screens.find(s => s.name === name);
    if (screen) {
        workspace.sendClientToScreen(w, screen);
        if (blank || panel) { w.keepAbove = true; w.fullScreen = true; }
    }
    if (panel) activatePanel(w);
}
function reportWindows() {
    const rows = windows().filter(w => w.normalWindow && !w.skipTaskbar && w.pid > 0 && !isPanel(w));
    send('WindowList', JSON.stringify(rows.map(w => ({pid:w.pid, id:String(w.internalId), active:w.active,
        desktop:String(w.desktopFileName), caption:String(w.caption), app:String(w.resourceClass),
        screen:String(w.output ? w.output.name : ''), fullscreen:w.fullScreen}))));
}
function reportFocusTargets() {
    const targets = preferences.preventMinimize ? windows().filter(w =>
        w.normalWindow && !isPanel(w) && w.fullScreen && w.output &&
        w.output.name === preferences.protectedOutput).map(w =>
        ({app:String(w.resourceClass),caption:String(w.caption)})) : [];
    send('FocusTargets',JSON.stringify(targets));
}
function watchWindow(w) {
    place(w,false);
    w.fullScreenChanged.connect(reportFocusTargets);
    w.outputChanged.connect(reportFocusTargets);
    w.captionChanged.connect(reportFocusTargets);
    reportFocusTargets();
}
function dispatch(p) {
    const find = () => windows().find(w => String(w.internalId) === p.identity);
    switch (p.operation) {
    case 'placement': preferences = p; windows().forEach(w => place(w, true)); reportFocusTargets(); break;
    case 'panel-show': panelRequested = true; windows().filter(isPanel).forEach(activatePanel); break;
    case 'panel-hide':
        panelRequested = false;
        if (previousWindow && windows().includes(previousWindow) && !previousWindow.minimized &&
            (!workspace.activeWindow || isPanel(workspace.activeWindow))) workspace.activeWindow = previousWindow;
        previousWindow = null; break;
    case 'touchpad': touchpad = true; focus(p.output); reportCursor(); break;
    case 'touchpad-stop': touchpad = false; break;
    case 'list': reportWindows(); break;
    case 'move': {
        const w = find(), s = workspace.screens.find(s => s.name === p.output);
        if (w && s) workspace.sendClientToScreen(w, s); break;
    }
    case 'activate': {
        const w = find(); if (w) { previousWindow = null; w.minimized = false; workspace.activeWindow = w; } break;
    }
    case 'swap': {
        const w = workspace.activeWindow, screens = workspace.screens;
        if (w && screens.length > 1) workspace.sendClientToScreen(w,
            screens[(screens.findIndex(s => s.name === w.output.name)+1)%screens.length]); break;
    }
    }
}
function reportCursor() {
    if (touchpad) send('CursorPosition', JSON.stringify([workspace.cursorPos.x, workspace.cursorPos.y]));
}
registerShortcut('HandheldDash Dispatch', 'HandheldDash desktop command', '', () => {
    callDBus('org.aynthor.Control', '/Control', 'org.aynthor.Control', 'DesktopNextCommand', function(raw) {
        const p = JSON.parse(raw);
        try { dispatch(p); } finally { send('DesktopCommandDone', String(p.serial || 0)); }
    });
});
registerShortcut('HandheldDash Gamepad Focus', 'Focus selected gamepad screen', '', () => {
    if (!panelRequested && preferences.gamepadFocus !== 'auto') focus(preferences.displays[preferences.gamepadFocus]);
});
windows().forEach(watchWindow);
workspace.windowAdded.connect(watchWindow);
workspace.windowRemoved.connect(reportFocusTargets);
workspace.cursorPosChanged.connect(reportCursor);
callDBus('org.aynthor.Control', '/Control', 'org.aynthor.Control', 'DesktopScriptReady');
