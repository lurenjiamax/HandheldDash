# 安装与使用

目前仅支持采用 Thorch Arch Linux ARM BSP、KDE Plasma/Wayland 和 InputPlumber 的
AYN Thor。参考环境为 thorch-bsp 1-38、thorch-kde-defaults 1-37、thorch-inputplumber
0.78.0，并使用已更新的硬件控制与风扇工具。BSP 必须提供 `thorch-hardwarectl
status-json`、`thorch-fancontrol status-json`、自定义曲线配置及风扇配置自动重载。
本包不包含内核、BSP，也不会替换 BSP 所属文件。普通 Arch 安装并不自动具备这些接口。

从 Release 下载包与 SHA256SUMS，执行：

```sh
sha256sum -c SHA256SUMS
sudo pacman -U handhelddash-1.0.0-1-any.pkg.tar.zst
sudo systemctl enable --now inputplumber.service aynthor-hardwared.service
systemctl --user enable --now aynthor-control.service
handhelddash
```

`any` 表示包内为 Python 与数据，不代表支持任意硬件。Thor 专用依赖须从 Thorch
软件源获取。服务需要手动启用。保留旧的 aynthor 可执行文件名、服务、D-Bus 和配置位置，
并提供 handhelddash 与 handhelddash-daemon 别名，避免改变现有用户设置。

如果此前通过脚本手动安装，应先备份，只处理本包冲突的未归属文件，或使用 pacman
`--overwrite` 明确指定这些路径；不要覆盖 BSP 文件。`/etc/systemd/system` 的旧 unit
和 `/etc/dbus-1/system.d` 的旧 policy 可能优先于包内版本，需比较后处理。包不会替换
`~/.config/aynthor/settings.json` 与 `/var/lib/aynthor/preferences.json`。
升级后执行 `sudo systemctl daemon-reload`、`sudo systemctl restart aynthor-hardwared`、
`systemctl --user daemon-reload` 与 `systemctl --user restart aynthor-control`。

源码打包：克隆仓库后，由普通用户执行 `makepkg -s`，再用 `sudo pacman -U` 安装。
默认获取发布标签；打包指定提交可用 `HANDHELDDASH_REF=commit=$(git rev-parse HEAD)
makepkg -s`。CI 的普通 Arch 环境仅用 `--nodeps` 构建 Python/数据包，运行依赖仍保留
在包元数据中。推送 main 或 PR 会构建；与 PKGBUILD 版本一致的 v 开头标签会创建 Release
并发布包与校验和。不运行单元测试。

AYN 键唤出／隐藏中控；`handhelddash --settings` 打开设置。状态按钮点击轮换、长按选择；
任务长按可移动或记住屏幕。截图点击执行、长按选择区域／上屏／下屏。在灯光页点击预览或
按 L3/R3 打开色环，手柄模式下转动对应摇杆选色，再按一次关闭。鼠标模式由 daemon 通过
InputPlumber 切换，右摇杆控制指针、左摇杆对应 WASD；该模式下色环使用触控选择。
