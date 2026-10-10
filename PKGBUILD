# Maintainer: lurenjiamax <1932231507@outlook.com>
pkgname=handhelddash
pkgver=1.1.0
pkgrel=1
pkgdesc='Touch-friendly handheld dashboard and privileged hardware daemon for AYN Thor'
arch=('any')
url='https://github.com/lurenjiamax/HandheldDash'
license=('LGPL-3.0-or-later' 'ISC')
depends=('python' 'python-dbus' 'python-gobject' 'python-evdev' 'python-yaml' 'python-pyqt6' 'qt6-wayland' 'qt6-tools' 'spectacle' 'libpulse' 'libnotify' 'wireplumber' 'systemd' 'util-linux' 'plasma-workspace' 'kwin' 'thorch-bsp' 'thorch-kde-defaults' 'thorch-inputplumber')
makedepends=('git')
optdepends=('mangohud: FPS sampling, overlay and frame limits' 'bindfs: Android shared storage access for ordinary users')
install=handhelddash.install
_gitref="${HANDHELDDASH_REF:-tag=v${pkgver}}"
source=("HandheldDash::git+${url}.git#${_gitref}")
sha256sums=('SKIP') # Git sources are selected by tag, or the exact CI commit.

package() {
  cd "$srcdir/HandheldDash"
  install -Dm755 src/app.py "$pkgdir/usr/bin/aynthor-control"
  install -Dm755 src/daemon.py "$pkgdir/usr/bin/aynthor-hardwared"
  ln -s aynthor-control "$pkgdir/usr/bin/handhelddash"
  ln -s aynthor-hardwared "$pkgdir/usr/bin/handhelddash-daemon"
  install -Dm644 src/localization.py "$pkgdir/usr/lib/aynthor/localization.py"
  install -Dm644 vendor/lpunpack/lpunpack.py "$pkgdir/usr/lib/aynthor/lpunpack.py"
  install -d "$pkgdir/usr/share/aynthor/icons"
  printf '%s\n' "$pkgver" > "$pkgdir/usr/share/aynthor/version"
  install -m644 packaging/icons/*.svg "$pkgdir/usr/share/aynthor/icons/"
  install -Dm644 packaging/aynthor-hardwared.service "$pkgdir/usr/lib/systemd/system/aynthor-hardwared.service"
  install -Dm644 packaging/handhelddash-fps.conf "$pkgdir/usr/lib/tmpfiles.d/handhelddash-fps.conf"
  install -Dm644 packaging/aynthor-control.service "$pkgdir/usr/lib/systemd/user/aynthor-control.service"
  install -Dm644 packaging/org.aynthor.Hardware1.conf "$pkgdir/usr/share/dbus-1/system.d/org.aynthor.Hardware1.conf"
  install -Dm644 packaging/99-handhelddash-touchscreen-relay.rules "$pkgdir/usr/lib/udev/rules.d/99-handhelddash-touchscreen-relay.rules"
  for file in packaging/org.aynthor.*.desktop; do install -Dm644 "$file" "$pkgdir/usr/share/applications/${file##*/}"; done
  install -Dm644 packaging/aynthor-control.desktop "$pkgdir/etc/xdg/autostart/aynthor-control.desktop"
  for file in LICENSE COPYING; do install -Dm644 "$file" "$pkgdir/usr/share/licenses/$pkgname/$file"; done
  install -Dm644 packaging/icons/LICENSE-lucide "$pkgdir/usr/share/licenses/$pkgname/lucide-ISC"
  install -Dm644 vendor/lpunpack/LICENSE.md "$pkgdir/usr/share/licenses/$pkgname/lpunpack-LGPL"
  install -Dm644 vendor/lpunpack/README.md "$pkgdir/usr/share/doc/$pkgname/lpunpack-provenance.md"
  for file in README.md README.zh-CN.md; do install -Dm644 "$file" "$pkgdir/usr/share/doc/$pkgname/${file##*/}"; done
  for file in docs/*.md; do install -Dm644 "$file" "$pkgdir/usr/share/doc/$pkgname/docs/${file##*/}"; done
  install -Dm644 docs/images/control-panel.png "$pkgdir/usr/share/doc/$pkgname/docs/images/control-panel.png"
}
