# KDE integration

HandheldDash follows the current KDE `kdeglobals` window, button, text and selection colors. Changes are picked up without restarting the panel. Touch geometry is retained.

Application-menu entries receive standard desktop actions: **Open on top screen** and **Open on bottom screen**. HandheldDash writes per-user overrides in `$XDG_DATA_HOME/applications` and preserves existing desktop actions. System desktop files are not modified. Existing local desktop entries are backed up under `$XDG_CONFIG_HOME/aynthor/desktop-backups`. The application list is refreshed at startup and once per minute. Each launch uses a short-lived KWin placement script; desktop IDs and `StartupWMClass` identify the application's windows. Applications exposing neither identity may need their existing per-application screen rule. On Thor, `DSI-2` is the top screen and `DSI-1` is the bottom screen.

**Caffine On** manually inhibits sleep and screen locking through KDE's PowerManagement and ScreenSaver D-Bus interfaces. **Caffine Off** releases both inhibits. This no longer rewrites the user's automatic lock settings. Exiting HandheldDash also releases its D-Bus inhibits. The selected state is restored when HandheldDash starts.

The header battery icon distinguishes fast charging, ordinary charging, and unplugged battery levels (low: up to 20%; medium: up to 60%; high: above 60%). Charging state and protocol come from the existing hardware daemon. Selecting a running task keeps the dashboard open.

## 中文

配色跟随 KDE，保留触控布局。应用菜单右键新增“在上屏打开”和“在下屏打开”；使用用户目录的 desktop 覆盖文件，不修改系统应用文件，并保留原有快捷操作。列表每分钟刷新。部分没有正确窗口标识的应用仍需单独设置屏幕规则。

Caffine On 手动阻止休眠和锁屏，Off 释放限制，不再改写系统自动锁屏设置。顶部电池图标区分快充、普通充电和未充电的高、中、低电量。切换任务后面板保持打开。

## Source language and icons

Python source strings and comments use English. Chinese translations reside in `packaging/translations.json`. Library icons are vendored from Lucide (ISC) and Tabler (MIT, including the coffee/coffee-off pair and numeric FPS icons); `packaging/icons/sources.json` records their original URLs and SHA-256 hashes. Small application-specific SVGs use the same 24-pixel vector style. The 120 FPS choice uses the library gauge icon because the numeric library does not supply a 120 glyph.

Task long-press menus provide Force close. The daemon validates PID and start time, then sends SIGKILL through a pidfd. It permits the active user's processes and root GUI processes belonging to that user's graphical session. Forced termination can lose unsaved work.

Control icons are monochrome and follow KDE foreground color. Only the status-bar battery uses an accent for fast charging. Caffine On uses Tabler coffee; Caffine Off uses Tabler coffee-off.
