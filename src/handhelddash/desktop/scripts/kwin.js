// SPDX-License-Identifier: LGPL-3.0-or-later
// The latest script stays resident for placement/cursor signals. Each command
// starts it directly, avoiding global-shortcut registration and invocation.
let preferences = {rules:{}, displays:{}, defaultScreen:'', gamepadFocus:'auto'};
let touchpad = false, panelRequested = false, previousWindow = null;
const windows = () => workspace.windowList();
const isGuard = w => String(w.caption) === 'HandheldDash Desktop Touch Guard' &&
    String(w.resourceClass).toLowerCase().includes('org.aynthor.control');
const isPanel = w => String(w.resourceClass).toLowerCase().includes('org.aynthor.control') &&
    String(w.caption).startsWith('HandheldDash') && !isGuard(w);
const send = (method, data) => callDBus('org.aynthor.Control', '/Control', 'org.aynthor.Control', method, data);
function focus(output) {
    const w = workspace.stackingOrder.slice().reverse().find(w =>
        w.normalWindow && !w.minimized && w.output && w.output.name === output && !isPanel(w) && !isGuard(w));
    if (w) workspace.activeWindow = w;
}
function activatePanel(w) {
    if (!panelRequested || !isPanel(w)) return;
    if (preferences.gamepadFocus === 'top' && String(w.caption) === 'HandheldDash') return;
    const active = workspace.activeWindow;
    if (active && !isPanel(active) && !previousWindow) previousWindow = active;
    w.minimized = false; w.keepAbove = true; workspace.activeWindow = w;
}
function place(w, existing) {
    if (isGuard(w)) {
        const opposite = preferences.gamepadFocus === 'top' ? 'bottom' : 'top';
        const output = workspace.screens.find(s => s.name === preferences.displays[opposite]);
        if (output) workspace.sendClientToScreen(w, output);
        w.keepAbove = false; w.keepBelow = true; return;
    }
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
    const rows = windows().filter(w => w.normalWindow && !w.skipTaskbar && !isPanel(w) && !isGuard(w));
    send('WindowList', JSON.stringify(rows.map(w => ({pid:Number(w.pid) || 0, id:String(w.internalId), active:w.active,
        desktop:String(w.desktopFileName), caption:String(w.caption), app:String(w.resourceClass),
        screen:String(w.output ? w.output.name : ''), fullscreen:w.fullScreen,
        maximized:w.maximizeMode === 3, minimized:w.minimized, keep_above:w.keepAbove,
        can_maximize:w.maximizable !== false, can_minimize:w.minimizable !== false}))));
}
function dispatch(p) {
    const find = () => windows().find(w => String(w.internalId) === p.identity);
    switch (p.operation) {
    case 'placement': preferences = p; windows().forEach(w => place(w, true)); break;
    case 'panel-show': panelRequested = true; windows().filter(isPanel).forEach(activatePanel); break;
    case 'panel-hide':
        panelRequested = false;
        if (previousWindow && windows().includes(previousWindow) && !previousWindow.minimized &&
            (!workspace.activeWindow || isPanel(workspace.activeWindow))) workspace.activeWindow = previousWindow;
        previousWindow = null; break;
    case 'touchpad': touchpad = true; focus(p.output); reportCursor(); break;
    case 'touchpad-stop': touchpad = false; break;
    case 'gamepad-focus':
        if (preferences.gamepadFocus !== 'auto' && (!panelRequested || preferences.gamepadFocus === 'top'))
            focus(preferences.displays[preferences.gamepadFocus]);
        break;
    case 'list': reportWindows(); break;
    case 'move': {
        const w = find(), s = workspace.screens.find(s => s.name === p.output);
        if (w && s) workspace.sendClientToScreen(w, s); break;
    }
    case 'activate': {
        const w = find(); if (w) { previousWindow = null; w.minimized = false; workspace.activeWindow = w; } break;
    }
    case 'window-action': {
        const w = find();
        if (w) {
            switch (p.action) {
            case 'maximize':
                if (w.maximizable !== false) { w.fullScreen = false; w.minimized = false; w.setMaximize(true, true); }
                break;
            case 'minimize': if (w.minimizable !== false) w.minimized = true; break;
            case 'windowed': w.fullScreen = false; w.minimized = false; w.setMaximize(false, false); break;
            case 'keep-above': if (p.enabled) w.keepBelow = false; w.keepAbove = !!p.enabled; break;
            }
        }
        reportWindows(); break;
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
callDBus('org.aynthor.Control', '/Control', 'org.aynthor.Control', 'DesktopNextCommand', function(raw) {
    let p;
    try { p = JSON.parse(raw); } catch (error) { send('DesktopScriptFailed', String(error)); return; }
    if (!p.serial) return;
    let error = '';
    try {
        if (p.preferences && p.preferences.operation === 'placement') preferences = p.preferences;
        touchpad = !!p.touchpadActive; panelRequested = !!p.panelRequested;
        previousWindow = windows().find(w => String(w.internalId) === p.previousWindow) || null;
        workspace.windowAdded.connect(w => place(w, false));
        workspace.cursorPosChanged.connect(reportCursor);
        dispatch(p);
    } catch (failure) { error = String(failure); }
    send('DesktopCommandDone', JSON.stringify({serial:p.serial, error:error,
        previousWindow:previousWindow && windows().includes(previousWindow) ? String(previousWindow.internalId) : ''}));
});
