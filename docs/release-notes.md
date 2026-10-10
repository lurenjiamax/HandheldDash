HandheldDash 1.1.0 adds a lower-screen touchpad, configurable resident tabs,
independent custom fan curves, screen placement controls, and expanded hardware
settings for AYN Thor on Thorch Arch Linux ARM with KDE Plasma/Wayland.

MangoHud configuration takeover now manages FPS sampling, frame limits and the
overlay for external games using the system configuration. Takeover persists
across restarts; releasing it restores the original configuration. Games that
explicitly override MangoHud settings may require their own configuration.
The frame-limit button uses numeric vector icons. Task switching handles Chinese
process names and windows owned by other users. Opening the AYN panel preserves
the game's focus through a KWin window rule; opening Settings allows text input.

Back + Home is configurable in Buttons and defaults to resetting the lower
screen's touch driver. The release also includes temperature sensor selection,
updated power/GPU icons, instant fan curve editing, audio-reactive joystick
lighting, CPU-affinity controls for the panel, and reduced background polling.

Install handhelddash-1.1.0-1-any.pkg.tar.zst using pacman -U on a compatible Thorch
system. SHA256SUMS and .SRCINFO accompany the package. This Python/data package
is architecture-independent; hardware support is currently tested only on AYN
Thor. Wider handheld support is planned. See the English and Chinese installation
and feature documentation for BSP dependencies and service activation.

Android userdata access requires the matching private device backend, kernel and
keys, which are not bundled. Android partition features remain extremely
experimental. The separate experimental keyboard build is not included.
Original code is LGPL-3.0-or-later; third-party components retain their licenses.
Changes were checked on the device during development; no unit tests or new full
hardware validation pass were performed for this release.
