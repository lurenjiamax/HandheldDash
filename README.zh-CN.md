**HandheldDash** 是面向 Arch Linux 与 KDE Plasma/Wayland 的掌机触控中控应用及系统 D-Bus 硬件 daemon。目前**仅支持并在使用 Thorch BSP 的 AYN Thor 上验证过**，未来计划扩展其他掌机。[English](README.md)。<img src="docs/images/control-panel.png" alt="AYN Thor 上的 HandheldDash 中控界面" width="620">

提供性能配置、风扇配置与可编辑曲线、双屏亮度及应用屏幕位置、任务切换、区域／上屏／下屏截图、播放音量、左右摇杆灯光与音频律动及色环、震动、返回／主页键自定义、手柄／鼠标输入切换。处于活动本地会话的普通用户可通过 daemon 操作已支持硬件，无需以 root 运行界面。[功能与限制](docs/features.zh-CN.md)。

在兼容的 Thorch 系统上，从 [Releases](https://github.com/lurenjiamax/HandheldDash/releases) 下载 `handhelddash-1.0.0-1-any.pkg.tar.zst`，执行 `sudo pacman -U handhelddash-1.0.0-1-any.pkg.tar.zst`，再执行 `sudo systemctl enable --now inputplumber.service aynthor-hardwared.service`，并在 KDE 会话中执行 `systemctl --user enable --now aynthor-control.service`。使用 `handhelddash` 启动中控、`handhelddash --settings` 打开设置，或按 AYN 键唤出中控。[安装、升级与源码打包](docs/installation.zh-CN.md)。

本项目原创代码采用 **LGPL-3.0-or-later**，见 [LICENSE](LICENSE) 与 [COPYING](COPYING)。内置 lpunpack 与 Lucide 图标保留各自 LGPL、ISC 授权；依赖保留各自许可证，包括 PyQt6 的 GPL／商业许可条款。本项目为无担保的社区软件，不应假定支持 AYN Thor 之外的硬件。Android 分区功能属于**极端实验性：可能完全无法工作，甚至导致 Android 无法启动**。未来计划拓展硬件；未支持的手柄布局及旁路供电不会宣称可用。[第三方声明](docs/third-party.md)。
