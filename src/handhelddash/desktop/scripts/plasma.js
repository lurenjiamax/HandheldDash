// SPDX-License-Identifier: LGPL-3.0-or-later
function handhelddashPanel(p) {
    var ids = [];
    desktops().concat(panels()).forEach(function(item) {
        if (item.screen >= 0 && ids.indexOf(item.screen) < 0) ids.push(item.screen);
    });
    var matches = ids.filter(function(id) {
        var r = screenGeometry(id), t = p.target;
        return r.x === t.x && r.y === t.y && r.width === t.width && r.height === t.height;
    });
    if (matches.length !== 1) throw new Error('Cannot uniquely resolve the configured display in Plasma');
    var screen = matches[0];
    var matching = panels().filter(function(panel) {
        return panel.type === 'org.kde.plasma.mobile.panel' && panel.screen === screen;
    });
    if (p.operation === 'list') {
        print(JSON.stringify(matching.map(function(panel) { return {height:panel.height,location:panel.location}; })));
    } else {
        if (p.visible && !matching.length) {
            var panel = new Panel('org.kde.plasma.mobile.panel');
            panel.screen = screen; panel.location = p.location; panel.height = p.height;
        } else if (!p.visible) matching.forEach(function(panel) { panel.remove(); });
        print('ok');
    }
}
