**HandheldDash** 是掌机触控中控应用及系统 D-Bus 硬件服务。目前已验证的环境为**使用 Thorch BSP 与 KWin 的 AYN Thor**。[英文文档](README.md)。<img src="docs/images/control-panel.png" alt="AYN Thor 上的 HandheldDash 中控界面" width="620">

提供性能配置、风扇配置与可编辑曲线、双屏亮度及应用屏幕位置、任务切换、区域／上屏／下屏截图、播放音量、左右摇杆灯光与音频律动及色环、震动、返回／主页键自定义、手柄／鼠标输入切换。处于活动本地会话的普通用户可通过 daemon 操作已支持硬件，无需以 root 运行界面。[功能与限制](docs/features.zh-CN.md)。

**手柄焦点限制：**仅在检测到手柄活动时请求 KWin 聚焦指定屏幕上的窗口，**不隔离或路由手柄输入**。直接通过 SDL／evdev 读取手柄的游戏可能不受桌面焦点影响，多个游戏仍可能同时响应。“自动”表示不干预焦点。此功能依赖 KWin 和已识别的控制器，尚未验证可靠的双游戏输入隔离。

**输入方案来源：**手柄／鼠标模式加载系统安装的 InputPlumber 方案（`/usr/share/inputplumber/profiles/default.yaml` 和 `mouse_keyboard_wasd.yaml`），并在运行时补充 HandheldDash 按键映射。基础方案由系统的 InputPlumber 安装提供，**不随 HandheldDash 包附带**；受支持的 Thorch 环境需要提供这些文件及兼容的控制器配置。

设备配置、桌面适配、监控采样与通用 UI 控件已分层整理。其他 WM 使用受能力限制的通用适配，不执行 KDE 专属修改；这不代表新增硬件已经受支持。开发和部署统一使用 pacman 包，参见[适配边界与打包部署](docs/portability.md)。

在兼容的 Thorch 系统上，从 [Releases](https://github.com/lurenjiamax/HandheldDash/releases) 下载 `handhelddash-1.3.0-1-any.pkg.tar.zst`，执行 `sudo pacman -U handhelddash-1.3.0-1-any.pkg.tar.zst`，再执行 `sudo systemctl enable --now inputplumber.service aynthor-hardwared.service`，并在 KDE 会话中执行 `systemctl --user enable --now aynthor-control.service`。使用 `handhelddash` 启动中控、`handhelddash --settings` 打开设置，或按 AYN 键唤出中控。[安装、升级与源码打包](docs/installation.zh-CN.md)。限帧与可选的游戏内叠加层需要显式通过 MangoHud 启动应用，例如 `mangohud eden`；中控不采集或显示 FPS。接管 MangoHud 配置不会自动为应用加载 MangoHud。

本项目原创代码采用 **LGPL-3.0-or-later**，见 [LICENSE](LICENSE) 与 [COPYING](COPYING)。内置 lpunpack 与 Lucide 图标保留各自 LGPL、ISC 授权；依赖保留各自许可证，包括 PyQt6 的 GPL／商业许可条款。本项目为无担保的社区软件，不应假定支持 AYN Thor 之外的硬件。Android 分区功能属于**极端实验性：可能完全无法工作，甚至导致 Android 无法启动**。未来计划拓展硬件；未支持的手柄布局及旁路供电不会宣称可用。[第三方声明](docs/third-party.md)。
