# Maintainer: lurenjiamax <1932231507@outlook.com>
pkgname=handhelddash
pkgver=1.4.0
pkgrel=2
pkgdesc='Touch-friendly handheld dashboard and privileged hardware daemon for AYN Thor'
arch=('any')
url='https://github.com/lurenjiamax/HandheldDash'
license=('LGPL-3.0-or-later' 'ISC' 'MIT')
depends=('python' 'python-dbus' 'python-gobject' 'python-evdev' 'python-yaml' 'python-pyqt6' 'qt6-wayland' 'libpulse' 'libnotify' 'wireplumber' 'systemd' 'util-linux')
makedepends=('git')
optdepends=('qt6-tools: KWin D-Bus scripting integration' 'kwin: window placement and focus adapter' 'plasma-workspace: Plasma panel adapter' 'spectacle: KDE screenshot capture' 'thorch-bsp: AYN Thor hardware backend' 'thorch-kde-defaults: AYN Thor desktop defaults' 'thorch-inputplumber: controller mapping and rumble on AYN Thor' 'kmod: load optional Android userdata kernel modules' 'mangohud: overlay and frame limits' 'bindfs: Android shared storage access for ordinary users')
install=handhelddash.install
_gitref="${HANDHELDDASH_REF:-tag=v${pkgver}}"
source=("HandheldDash::git+${url}.git#${_gitref}")
sha256sums=('SKIP') # Git sources are selected by tag, or the exact CI commit.

package() {
  cd "${HANDHELDDASH_SOURCE_ROOT:-$srcdir/HandheldDash}"
  install -Dm755 src/app.py "$pkgdir/usr/bin/aynthor-control"
  install -Dm755 src/userdata-mount.sh "$pkgdir/usr/lib/aynthor/userdata-mount"
  install -Dm755 src/daemon.py "$pkgdir/usr/bin/aynthor-hardwared"
  ln -s aynthor-control "$pkgdir/usr/bin/handhelddash"
  ln -s aynthor-hardwared "$pkgdir/usr/bin/handhelddash-daemon"
  install -Dm755 src/desktop_launch.py "$pkgdir/usr/lib/aynthor/desktop_launch.py"
  install -Dm644 src/localization.py "$pkgdir/usr/lib/aynthor/localization.py"
  while IFS= read -r -d '' file; do
    install -Dm644 "$file" "$pkgdir/usr/lib/aynthor/${file#src/}"
   done < <(find src/handhelddash -type f \( -name '*.py' -o -name '*.json' -o -name '*.js' \) -print0)
  install -Dm644 vendor/lpunpack/lpunpack.py "$pkgdir/usr/lib/aynthor/lpunpack.py"
  install -Dm644 packaging/translations.json "$pkgdir/usr/share/aynthor/translations.json"
  install -Dm644 packaging/icons/sources.json "$pkgdir/usr/share/aynthor/icons/sources.json"
  install -d "$pkgdir/usr/share/aynthor/icons"
  printf '%s\n' "$pkgver-$pkgrel" > "$pkgdir/usr/share/aynthor/version"
  python scripts/write-build-info.py "$pkgdir" "$PWD" "$pkgver-$pkgrel"
  install -m644 packaging/icons/*.svg "$pkgdir/usr/share/aynthor/icons/"
  install -Dm644 packaging/aynthor-hardwared.service "$pkgdir/usr/lib/systemd/system/aynthor-hardwared.service"
  install -Dm644 packaging/aynthor-control.service "$pkgdir/usr/lib/systemd/user/aynthor-control.service"
  install -Dm644 packaging/org.aynthor.Hardware1.conf "$pkgdir/usr/share/dbus-1/system.d/org.aynthor.Hardware1.conf"
  install -Dm644 packaging/99-handhelddash-touchscreen-relay.rules "$pkgdir/usr/lib/udev/rules.d/99-handhelddash-touchscreen-relay.rules"
  install -Dm644 packaging/org.aynthor.Control.desktop "$pkgdir/usr/share/applications/org.aynthor.Control.desktop"
  install -Dm644 packaging/aynthor-control.desktop "$pkgdir/etc/xdg/autostart/aynthor-control.desktop"
  for file in LICENSE COPYING; do install -Dm644 "$file" "$pkgdir/usr/share/licenses/$pkgname/$file"; done
  install -Dm644 packaging/icons/LICENSE-tabler "$pkgdir/usr/share/licenses/$pkgname/tabler-MIT"
  install -Dm644 packaging/icons/LICENSE-lucide "$pkgdir/usr/share/licenses/$pkgname/lucide-ISC"
  install -Dm644 vendor/lpunpack/LICENSE.md "$pkgdir/usr/share/licenses/$pkgname/lpunpack-LGPL"
  install -Dm644 vendor/lpunpack/README.md "$pkgdir/usr/share/doc/$pkgname/lpunpack-provenance.md"
  for file in README.md README.zh-CN.md; do install -Dm644 "$file" "$pkgdir/usr/share/doc/$pkgname/${file##*/}"; done
  for file in features.md features.zh-CN.md installation.md installation.zh-CN.md dashboard-customization.md portability.md release-notes.md third-party.md; do
    install -Dm644 "docs/$file" "$pkgdir/usr/share/doc/$pkgname/docs/$file"
  done
  install -Dm644 docs/images/control-panel.png "$pkgdir/usr/share/doc/$pkgname/docs/images/control-panel.png"
}
