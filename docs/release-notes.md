HandheldDash 1.2.0 introduces a customizable control dashboard for AYN Thor
running the Thorch BSP on Arch Linux with KDE Plasma/Wayland.

- Two wide cards and ten compact control slots, with centered content and
  improved wrapping for long English labels. All cards can be moved or removed.
- Unified editing for control and monitoring cards: tap-select/swap, drag to
  reorder, and long-press object menus. Pencil enters editing, plus adds cards,
  and the checkmark saves the draft.
- Optional system-load, network-speed and disk-IO monitoring, with interface or
  disk selection and aggregate modes. CPU/GPU cards independently select
  utilization or current / maximum MHz.
- Only selected monitoring cards request sampling. GPU utilization uses real
  MSM DRM engine counters; inactive samplers, fan animations and FPS CSV scans
  are stopped. Missing measurements are not replaced with fabricated values.
- Bounded, theme-aware brightness and volume popups that dismiss on outside
  taps. Screen controls live in the brightness popup; the integrated speaker
  icon toggles mute. Move-current-app is an independent control card.
- Native Plasma Mobile status-bar visibility and Docked Mode settings. The
  lower-screen status bar is resolved by actual DSI-1 geometry, not Qt screen
  enumeration. Docked Mode is a global Plasma Mobile setting.
- JSON translation catalogs, refreshed vector icons, KDE application-menu
  screen actions, and an updated English dashboard screenshot.
- Signed net battery power: discharge carries a minus sign, charging does not.
  Fast/slow charging labels describe the connected charging source, not a
  separately measured adapter-input wattage.

Install `handhelddash-1.2.0-1-any.pkg.tar.zst` with `pacman -U` on a compatible
Thorch installation. `SHA256SUMS` and `.SRCINFO` accompany the package. Hardware
support remains limited to the tested AYN Thor configuration; the architecture-
independent package does not imply support for other devices.

FPS controls still require applications to be explicitly launched with MangoHud.
Android partition/userdata features remain extremely experimental and require
matching device-private modules, keys and backends that are not bundled.

The interface was iteratively deployed during development. No unit tests or new
full hardware validation pass were run for this release. Original code remains
LGPL-3.0-or-later; Tabler SVGs retain MIT and Lucide assets retain ISC licensing.
