#!/bin/bash
# Package the current checkout, including uncommitted work, without a source clone.
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
mkdir -p "$root/build/packages"
export HANDHELDDASH_SOURCE_ROOT="$root"
export BUILDDIR="$root/build/packages"
export PKGDEST="$root/build/packages"
cd "$root"
exec makepkg --noextract --skipinteg --nodeps --force "$@"
