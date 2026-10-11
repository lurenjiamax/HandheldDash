# Plasma 设置

设置 → Plasma：

屏幕定位按 DSI-1 的实际逻辑坐标和尺寸与 Plasma `screenGeometry()` 精确匹配，不使用 Qt 屏幕枚举序号。找不到唯一匹配时禁用开关并停止操作，绝不退回主屏。

- **副屏状态栏**：显示/隐藏 DSI-1 顶部时间、网络、电量状态栏（`org.kde.plasma.mobile.panel`）。只移除/恢复该副屏 Mobile 面板，不修改主屏桌面面板或底部导航栏；保留位置和高度供恢复。
- **Plasma Docked Mode**：使用 Plasma Mobile 原生 `plasmamobilerc` 的 `General/convergenceModeEnabled`。通过 `kwriteconfig6 --notify` 通知运行中的 shell，不重启桌面。

Docked Mode 是 Plasma Mobile **全局**选项，不能宣传为原生逐屏隔离开关。本机只有副屏使用 Mobile 面板，但全局 Mobile 行为可能随设置变化。设置页明确注明此限制。初始化读取现有状态，不强行开启、关闭或覆盖用户桌面选择。
