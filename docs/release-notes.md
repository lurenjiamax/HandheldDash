HandheldDash 1.4.2 improves startup, audio controls, Android shared storage and window management.

- Fixed incomplete fullscreen placement that could leave black strips at screen edges.
- Wait for the Wayland display before creating the Qt interface, and refresh stale
  systemd user display variables on startup. Missing displays exit cleanly.
- Added per-device System default / Software volume / Hardware volume choices for
  ALSA and Bluetooth outputs using WirePlumber 0.5+. Software mode bypasses coarse
  hardware volume steps. Switching briefly reconnects audio while retaining the
  output, volume and mute setting. Bluetooth reconnection explicitly targets the
  original headset, including during error recovery. Hardware mode depends on
  device support; System default removes only Dash's override for that device.
- Replaced the Android shared-storage FUSE view with a kernel idmapped bind mount.
  User and Android media-directory ownership are mapped dynamically without
  rewriting existing file ownership. Other valid Linux IDs retain identity
  mappings. The view allows execution, retains nosuid/nodev and survives hardware
  service restarts without a userspace filesystem process. The bindfs dependency
  and implementation have been removed. Native permissions, ACLs and xattr
  semantics apply. A compatible kernel/filesystem and util-linux 2.39+ are required.
- Restored task listing and added Maximize, Minimize, Windowed and checkable
  Always on top actions to task long-press menus. Desktop commands execute directly
  through KWin scripting instead of global-shortcut dispatch. Windows remain
  listed when process metadata is unavailable, with process-specific actions
  disabled when their target cannot be verified. Duplicate interface owners are
  rejected to prevent commands reaching a stale instance.

Verified on AYN Thor with Thorch BSP and KWin using installed pacman packages,
real Bluetooth mode changes, shared-storage file operations and real window
controls. Android storage remains experimental. Intermittent retained touch
contacts and keyboard/touchpad coexistence are reported issues still under
investigation; this release does not claim to fix them.
