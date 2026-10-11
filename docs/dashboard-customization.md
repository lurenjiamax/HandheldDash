# Custom dashboard / 自定义中控

## Optional status types / 可选状态类型

Only selected status cards request their samplers. Removing a card stops its data sampling; CPU/GPU collect only the selected percentage or frequency representation. Removed fan monitoring stops its icon timer, and hidden FPS monitoring stops CSV scans. Re-added rate cards start a fresh two-sample baseline. Device names are enumerated only when opening the interface/disk chooser. Header battery information and independent hardware control/safety reads remain active.

Use **edit → + → Add metric** to choose System load, Network speed or Disk IO. They are optional and do not overwrite existing selections. The status area still has six slots: remove an existing card through its long-press menu when full.

- System load shows **1-minute · 5-minute · 15-minute** load averages (not CPU percentages).
- Network speed shows **↓receive ↑send**, in bytes per second. Hold it while editing, then choose **Interface**: a named interface or `all` (all non-loopback interfaces).
- Disk IO shows **R read / W write** throughput. Hold it while editing, then choose **Disk**: a named whole block device or `all`. Aggregate mode counts device-backed disks only, not partitions, loop/zram or stacked virtual devices.
- `K/M/G` use powers of 1024. Counters require two samples; absent/unplugged selected devices show `—` rather than silently switching to another device.
- Source choices, order and visibility save only with the checkmark. Existing selections remain intact.

Open the pencil icon on the Control page, or **Settings → Customize dashboard**.

The dashboard uses design C: six monitoring readings, two wide slots and ten smaller slots arranged in five columns and two rows. Performance/fan are no longer locked: all selected tiles can be moved or removed. Main pages have no sliders or dashboard scrollbars.

Editing stays on the dashboard. The pencil only enters editing, then hides; independent plus, cancel and check icons add, discard and save. Control tiles and monitoring cards share tap-select/swap, same-section drag reordering and long-press object menus. Each object menu has add/remove; CPU/GPU menus additionally select their own percent or MHz display. Percent shows actual utilization (— when unavailable); MHz shows current / maximum. No monitoring-wide configuration popup or exchange icon remains. Deleted monitors expose plus slots while editing. Editing never operates hardware; only the checkmark saves the draft.

**Done** saves the draft; **Cancel** discards it. **Reset** stages the default layout and still requires Done to save. **Show metrics** controls the compact monitoring summary. The edit button remains reachable even if all tiles and metrics are hidden.

Move current app is an optional independent tile. Existing selected shortcuts are preserved: remove a control before adding another when all twelve slots are occupied. Lighting tiles highlight whenever lighting is active, including animated and audio modes.

Brightness, volume and lighting-brightness sliders live in bounded, centered panel-local popups. Tapping outside dismisses the popup without activating an underlying control. The separate Screen control tab is removed; brightness now includes screen visibility and new-application screen selection. Tap the speaker icon integrated into the volume slider row to mute/unmute; no separate mute action is added.

Layouts are stored in `dashboard_layout` inside `$XDG_CONFIG_HOME/aynthor/settings.json` (normally `~/.config/aynthor/settings.json`): `{"version":4,"tiles":["performance","fan_link"],"metrics":true}`. IDs are validated and duplicate/unknown tiles are ignored. Older layouts migrate on read; saving requires the checkmark. No executable commands or user-supplied plugins are accepted. See [Plasma settings](plasma-settings.md) for the lower-screen status bar and native Docked Mode.

`handhelddash --customize` and the session D-Bus method `org.aynthor.Control.Customize` open the editor directly, without pointer-coordinate automation.

## 中文

点击中控右上角铅笔图标，或打开 **设置 → 自定义中控**。

- 首页为两张宽卡、十张小卡和六个监控位置，不出现滚动条。
- 普通控制和监控统一使用点选交换、同区拖动排序、长按对象编辑菜单；可添加、移除和配置项目。
- CPU/GPU 分别选择百分比或当前 / 最大 MHz。未添加的项目不独立采样。
- ＋仅添加、铅笔仅进入编辑、对号仅保存；取消丢弃草稿。

默认首页包含性能、风扇联动、输入模式、手柄焦点、Caffine、震动、截图和 FPS 浮层。还可添加灯光、概览、亮度、音量。亮度、音量、灯光亮度滑块放在二级弹窗，主页面只显示点击入口。监控数据不再使用类似滑块的进度条。配色继续跟随 KDE。

Esc／映射为 Esc 的返回键不收起中控；触控板模式下只返回中控。手机模式状态栏控制暂缓，未包含在本次修改中。

## Verification

Run `python3 -m unittest discover -s tests -v`. Offscreen tests cover migration, tile pagination, direct add/remove, drag/drop handling, draft isolation, saving/cancellation, widget ownership, Escape, layout geometry and sliders confined to dialogs. Local tests and screenshots do not establish physical-touch drag reliability; that still needs handheld user testing.
