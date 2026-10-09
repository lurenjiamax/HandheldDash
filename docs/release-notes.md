The first standalone release of HandheldDash: a touch-friendly dashboard and
system D-Bus hardware daemon for AYN Thor on Thorch Arch Linux ARM with KDE
Plasma/Wayland. Wider handheld support is planned.

Includes performance and fan controls, editable fan curves, dual-screen
brightness and window placement, task switching, screenshot modes, playback
volume, audio-reactive joystick lighting, color dials and vibration feedback,
Home/Back mappings, and Gamepad/Mouse profiles.

Install the attached Arch package with pacman -U on a compatible Thorch system;
see the bilingual installation documentation for required BSP interfaces and
manual service activation. The package is architecture-independent Python/data;
hardware compatibility is currently limited to AYN Thor. SHA256SUMS accompanies
the package. Android partition functionality is extremely experimental.

Original code: LGPL-3.0-or-later. Vendored components and runtime dependencies
retain their own licenses. Recent hardware behavior changes are user-verified
work in progress; this release does not claim a new full hardware test pass.
