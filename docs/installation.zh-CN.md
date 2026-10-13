# 安装

已验证的环境为采用 Thorch BSP、InputPlumber 与 KWin 的 AYN Thor。

从发行页面下载软件包后安装：

```sh
sudo pacman -U handhelddash-VERSION-any.pkg.tar.zst
sudo systemctl enable --now inputplumber.service aynthor-hardwared.service
systemctl --user enable --now aynthor-control.service
```

运行 `handhelddash`，或按 AYN 键唤出面板。设置可通过 `handhelddash --settings` 打开。

## 打包当前源码

```sh
bash scripts/build-package.sh --noconfirm
```

使用普通用户执行打包。部署统一通过 pacman 软件包完成。

升级保留用户设置。手工安装的服务覆盖文件可能优先于软件包中的配置。

Android 存储访问需要另行配置匹配的内核与解锁后端。
