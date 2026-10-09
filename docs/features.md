# Features and current limits

- Active-local-session D-Bus hardware controls with an unprivileged PyQt6 UI.
- Performance presets, CPU/GPU governors, boost and scheduler controls.
- Fan presets, actual temperature/RPM/PWM, step curves and editable custom curves.
- Independent screen brightness, default launch output and per-app window rules.
- Application task items with icons, titles and their current output.
- Region, top-screen and bottom-screen screenshots saved in Pictures/AYN Thor.
- Default playback-sink volume and mute; no per-screen physical audio output.
- Battery/static/off lighting plus independently colored stereo audio-reactive rings.
- Dynamic peak normalization, silence gating, response sensitivity and smoothing.
- Enlarged color dials with names, L3/R3 activation and short detent vibration.
- Home/Back mappings, configurable commands and Gamepad/Mouse input profiles.
- Optional MangoHud wrapper, FPS display and limit controls.
- Extremely experimental Android partition discovery and read-only mount UI.

Only AYN Thor has been supported and previously used for real-device checks.
The latest audio mapping and input-interaction changes have not received a new
full hardware verification; the user chose to verify them directly. This release
adds packaging, not a new claim of validation. The CI verifies package creation,
not hardware behavior, and has no unit-test suite.

No verified controller-layout or bypass-charging driver interface is exposed.
Global game-rumble strength is not implemented. Stable-volume sound remains
stable brightness: this effect is not a beat detector. Color-dial stick rotation
requires Gamepad mode; in Mouse mode axes have been remapped. Android access may
fail entirely and carries the explicit warning that Android may become unable
to boot. Wider device support is planned.
