HandheldDash 1.3.0 improves touch controls and reduces background work on AYN Thor
running the Thorch BSP with KDE Plasma/Wayland.

- Touch-only CPU affinity in the Tasks long-press menu. Select individual cores
  or capacity tiers; each core shows its hardware maximum frequency. Apply updates
  existing threads of the selected user-owned process. Existing child processes
  and future launch rules are not changed.
- Independent swipe paging for monitoring, primary tiles and shortcuts, with
  animated transitions. Page indicators appear only while editing.
- An editable FPS-limit tile, a simplified header and an icon-only edit button.
  The dashboard no longer collects FPS logs or displays FPS. MangoHud limits and
  the optional in-game overlay remain available for explicitly wrapped apps.
- One asynchronous resident KWin script replaces repeated synchronous script
  reloads. Showing Dash clears stale KWin highlight previews without disabling
  desktop effects.
- Hidden-panel monitoring stops; theme/menu changes use filesystem watchers.
  Android enumeration is asynchronous and page-gated; fan status is cached and
  audio subprocess lifetimes are bounded.

Install `handhelddash-1.3.0-1-any.pkg.tar.zst` with `pacman -U` on the supported
Thorch installation. `SHA256SUMS` and `.SRCINFO` accompany the package.

Validation used real AYN Thor package deployments, live process-affinity changes,
isolated UI operation and compositor screenshots. No unit tests were run. The
architecture-independent package does not imply support for other devices.

Known limitation: touching the lower-screen desktop can move focus away from an
upper-screen game, after which some games minimize. This release does not claim
to resolve that behavior. Android userdata access remains experimental and
requires device-private backends not bundled here. Keyboard Native Input changes
are maintained separately in the fcitx5-osk fork.
