#!/usr/bin/env bash
# Experimental Android userdata backend; load matching modules only when invoked.
set -euo pipefail
[[ $(id -u) == 0 ]] || { echo 'Run on Thor as root' >&2; exit 1; }
release=$(uname -r)
base=/var/lib/aynthor/android
mode=${1:---test-metadata-readonly}
case "$mode" in
    --test-metadata-readonly|--test-userdata-mount-readonly|--test-user0-readonly|--verify-user0-test-file-readonly|--inspect-checkpoint-readonly|--inspect-fsck-readonly|--inspect-sit-readonly|--inspect-fsck-trace-readonly|--inspect-fsck-direct-readonly) ;;
    --repair-fsck-snapshot) test "${AYNTHOR_RECOVERY_SNAPSHOT:-}" = 1 ;;
    --repair-fsck-original-with-journal) test "${AYNTHOR_AUTHORIZE_ORIGINAL_REPAIR:-}" = 1; test "${AYNTHOR_RECOVERY_SNAPSHOT:-0}" = 0 ;;
    --mount-user0-rw) test -z "$(pgrep -x fsck.f2fs || true)" ;;
    *) echo 'Only read-only probe modes are accepted' >&2; exit 2 ;;
esac
modules="$base/tme-modules/$release"
for name in aynthor_qmp tme_overlay_loader aynthor_tme; do
    [[ -d /sys/module/$name ]] && continue
    if modinfo -n "$name" >/dev/null 2>&1; then
        modprobe "$name"
    else
        module="$modules/$name.ko"
        [[ -f "$module" ]] || { echo "Missing module $name for running kernel $release" >&2; exit 1; }
        vermagic=$(modinfo -F vermagic "$module")
        [[ "${vermagic%% *}" == "$release" ]] || { echo "Module $name does not match running kernel $release" >&2; exit 1; }
        insmod "$module"
    fi
done
modprobe dm-default-key
modprobe quota_v2
env AYNTHOR_TEE_SHM_PROBE=1 \
    LD_LIBRARY_PATH="$base/keymint-runtime/lib64" \
    LD_PRELOAD="$base/keymint-runtime/lib64/conversion-compat.so:$base/keymint-runtime/lib64/libaynthor-mink-bridge.so" \
    "$base/keymint-runtime/bin/linker64" "$base/keymint-runtime/bin/native-convert" \
    "$base/keymint-private/metadata.keyblob" "$mode"
