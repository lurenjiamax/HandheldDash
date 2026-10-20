// SPDX-License-Identifier: LGPL-3.0-or-later
registerShortcut('HandheldDash Exit Touchpad', 'Exit HandheldDash touchpad mode', 'Esc', function() {
    callDBus('org.aynthor.Control', '/Control', 'org.aynthor.Control', 'ExitTouchpad');
});
