#!/bin/bash
# Usage: bash scripts/deploy-package.sh PACKAGE root@DEVICE [SESSION_USER]
set -euo pipefail
package=${1:?Package path required}; host=${2:?SSH destination required}; user=${3:-}
name=$(basename -- "$package")
[[ "$name" == handhelddash-*.pkg.tar.* ]] || { echo 'Expected a handhelddash pacman package' >&2; exit 1; }
[[ "$name" != *[!a-zA-Z0-9._+-]* ]] || exit 1
directory=/var/cache/handhelddash/packages
ssh "$host" "install -d '$directory'"
scp "$package" "$host:$directory/$name"
ssh "$host" bash -s -- "$directory/$name" "$user" <<'REMOTE'
set -euo pipefail
package=$1; user=$2
old_backend=$(sha256sum /usr/bin/aynthor-hardwared 2>/dev/null || true)
backend_modules() {
  find /usr/lib/aynthor/handhelddash -type f \( -name '*.py' -o -name '*.json' \) \
    ! -path '*/ui/*' ! -path '*/desktop/*' ! -name hardware_client.py ! -name buildinfo.py \
    -exec sha256sum {} \; 2>/dev/null | sort
}
old_modules=$(backend_modules || true)
# Legacy direct installs have unowned files. Only overwrite exact package paths
# proven unowned; never use a wildcard or overwrite another package's files.
overwrite=()
while IFS= read -r file; do
  [[ "$file" == */ || "$file" == .* ]] && continue
  [[ -e "/$file" || -L "/$file" ]] || continue
  owner=$(pacman -Qqo "/$file" 2>/dev/null || true)
  if [[ -z "$owner" ]]; then overwrite+=(--overwrite "$file")
  elif [[ "$owner" != handhelddash ]]; then
    echo "Refusing file owned by $owner: /$file" >&2; exit 1
  fi
done < <(bsdtar -tf "$package")
pacman -U --noconfirm "${overwrite[@]}" "$package"
systemctl daemon-reload
new_backend=$(sha256sum /usr/bin/aynthor-hardwared)
new_modules=$(backend_modules)
if [[ "$old_backend" != "$new_backend" || "$old_modules" != "$new_modules" ]]; then
  if systemctl is-active --quiet aynthor-hardwared.service; then systemctl restart aynthor-hardwared.service; fi
fi
if [[ -n "$user" ]]; then
  uid=$(id -u "$user")
  runuser -u "$user" -- env XDG_RUNTIME_DIR="/run/user/$uid" DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$uid/bus" systemctl --user daemon-reload
  runuser -u "$user" -- env XDG_RUNTIME_DIR="/run/user/$uid" DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$uid/bus" systemctl --user restart aynthor-control.service
fi
pacman -Q handhelddash
REMOTE
