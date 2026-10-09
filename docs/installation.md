# Installation and use

## Supported system

Only AYN Thor with the Thorch Arch Linux ARM BSP, KDE Plasma on Wayland, and
InputPlumber is currently supported and has prior hardware verification. The
reference system uses thorch-bsp 1-38, thorch-kde-defaults 1-37 and
thorch-inputplumber 0.78.0. The locally updated BSP tools must provide
`thorch-hardwarectl status-json`, `thorch-fancontrol status-json`, custom fan
curve keys and automatic fan-config reload. HandheldDash does not ship a kernel,
BSP or a replacement for those package-owned tools. Stock Arch Linux alone is
not sufficient; other handhelds are planned but unverified.

## Package

Download the package and SHA256SUMS from the release. In their directory:

```sh
sha256sum -c SHA256SUMS
sudo pacman -U handhelddash-1.0.0-1-any.pkg.tar.zst
sudo systemctl enable --now inputplumber.service aynthor-hardwared.service
systemctl --user enable --now aynthor-control.service
handhelddash
```

The `any` architecture means the package contains Python and data rather than
compiled binaries. It does not mean arbitrary hardware is supported. Thor-only
runtime dependencies come from the Thorch repositories; pacman cannot retrieve
them from the generic Arch repositories. The installer does not enable hardware
services automatically. The daemon and interface retain the existing
`aynthor-*` executables, service names, D-Bus names and settings locations so
existing Thor installations keep their preferences. `handhelddash` and
`handhelddash-daemon` are convenience aliases.

For a previous manual installation, preserve the old files first. Remove only
unowned files that conflict with the package, or explicitly allow those exact
paths with pacman's `--overwrite` option. Do not overwrite unrelated files or
BSP-owned helpers. Existing manually installed units in `/etc/systemd/system`
and D-Bus policies in `/etc/dbus-1/system.d` override packaged files; compare
and retire those duplicates when appropriate. Preferences in
`~/.config/aynthor/settings.json` and `/var/lib/aynthor/preferences.json` are not
owned or replaced by this package.

For an upgrade, install the new package, then:

```sh
sudo systemctl daemon-reload
sudo systemctl restart aynthor-hardwared.service
systemctl --user daemon-reload
systemctl --user restart aynthor-control.service
```

## Build from source

```sh
git clone https://github.com/lurenjiamax/HandheldDash.git
cd HandheldDash
makepkg -s
sudo pacman -U handhelddash-*.pkg.tar.zst
```

Run makepkg as a normal user. The recipe fetches the release tag. For a specific
checkout, use `HANDHELDDASH_REF=commit=$(git rev-parse HEAD) makepkg -s`. Generic
Arch CI deliberately uses `--nodeps` only to construct this Python/data package;
runtime dependencies still remain in the package metadata and are required on
the device. The GitHub workflow builds every main push and pull request, and
publishes a GitHub release with the package and checksums for `v*` tags matching
the PKGBUILD version. It runs no unit tests.

## Controls

Press AYN to show/hide the panel; use `handhelddash --settings` for settings.
Tap state buttons to cycle and hold to choose. Hold a task to move its window or
remember its screen. Tap the screenshot button to capture; hold to choose
Region, Top or Bottom. In Lighting, tap a stick preview or press L3/R3 to open
its dial, rotate the stick in Gamepad mode to choose a color, and press again to
close. Input mode is managed through the daemon by InputPlumber: Mouse maps the
right stick to pointer motion and the left stick to WASD. Mouse mode's remapped
axes do not drive the color dial; touch still works.
