# Features and current limits

- Active-local-session D-Bus hardware controls with an unprivileged PyQt6 UI.
- Performance presets, CPU/GPU governors, boost and scheduler controls.
- Fan presets, actual temperature/RPM/PWM, continuous curves and editable custom curves.
- Fan linkage can follow performance presets (Quiet → Quiet, Standard → Balanced,
  Performance → Aggressive) or remain independent. Selecting a fan preset or
  applying a custom curve switches to independent mode. Curves interpolate
  linearly, slow down gradually on cooling and immediately reach 100% at the
  maximum temperature. This requires the updated `thorch-bsp` fan controller.
- UFS IRQ CPU placement under Performance settings: CPU0–2, CPU7, or restore
  original affinity. The daemon discovers ufshcd IRQs dynamically, shows requested
  and effective placement, retains the chosen policy and reapplies it on resume
  and every five seconds. CPU7 may use more power; no throughput gain is assumed.
- Independently blank either screen without disabling its output or moving apps.
  Black windows request no focus and block touches; the AYN panel key restores
  both screens. This does not power off panels or stop background rendering.
- Independent screen brightness, default launch output and per-app window rules.
- Application task items with icons, titles and their current output.
- Region, top-screen and bottom-screen screenshots saved in Pictures/AYN Thor.
- Default playback-sink volume and mute; no per-screen physical audio output.
- Battery/static/off lighting plus independently colored stereo audio-reactive rings.
- Dynamic peak normalization, silence gating, response sensitivity and smoothing.
- Enlarged color dials with names, L3/R3 activation and short detent vibration.
- Gamepad desktop focus modes: Automatic, Lock top screen and Lock bottom
  screen. A locked mode focuses the topmost eligible app on its screen on gamepad
  activity. Direct evdev/SDL readers may still receive input regardless of focus;
  this is not per-process gamepad isolation.
- Home/Back mappings, configurable commands and Gamepad/Mouse input profiles.
- Hold HOME and BACK together to recover a stuck bottom touchscreen by rebinding
  its driver. The chord suppresses both individual actions; single presses now
  execute on release. Both keys must be released before another recovery.
- The dashboard and Fan page share the same Follow performance / Independent
  control. The disabled-auto-lock state is labeled Caffine.
- FanControl-inspired graph editing: edit a preset as custom, drag seven nodes,
  inspect the selected temperature/PWM value and apply explicitly. Numeric
  controls are in a collapsed advanced panel; the final node stays at 100%.
  Design reference: https://getfancontrol.com/docs/#graph
- Settings tab management: pin pages, or open them temporarily from settings.
- Bottom-screen virtual multitouch touchpad with KDE acceleration, tap and scroll
  settings. Esc exits touchpad mode, including when the upper app has focus.
- Optional MangoHud wrapper, FPS display and limit controls.
- Extremely experimental Android partition discovery and read-only mount UI.

Only AYN Thor has been supported and previously used for real-device checks.
The latest audio mapping and input-interaction changes have not received a new
full hardware verification; the user chose to verify them directly. This release
adds packaging, not a new claim of validation. The CI verifies package creation,
not hardware behavior, and has no unit-test suite.

The touchpad mode exclusively grabs the physical bottom touchscreen, following
[TouchpadEmulator](https://github.com/CalcProgrammer1/TouchpadEmulator)'s input-ownership
approach. Each contact starting inside the pad goes only to the virtual touchpad;
outside contacts go to a cloned touchscreen mapped to DSI-1, keeping navigation
usable. The physical touchscreen never delivers duplicate
pad touches to KWin. Movement orientation is read from the current upper-screen QScreen orientation,
without a fixed 90-degree correction. Hit testing and ordinary touchscreen relaying
use the physical bottom touchscreen's current KDE calibration. Orientation changes
apply to the next contact, so ongoing swipes cannot jump mid-gesture. Ownership starts after the tab-selection finger lifts
and ends on page exit, client disconnection or inactive session. Source timestamps
and ongoing contact mappings are retained, independently of UI heartbeat delays.
Raw input is read on a dedicated thread so synchronous hardware and D-Bus queries
cannot hold up touch forwarding. Input-buffer overflow recovers the kernel's
current multitouch slots instead of discarding ongoing contacts.
KDE/libinput handles gestures and its touchpad settings remain available. The
touchpad fills the page without contact previews or a keyboard button. Esc is
registered through KWin only while touchpad mode is visible. The
initial raw-input migration keeps tapping on and disables tap-and-drag/drag lock;
subsequent KDE preferences are retained. Hardware still limits sampling; real
input was observed at approximately 50–55 moving frames per second. The latest
exclusive-routing interaction awaits user verification. No third-party project
code was copied into this implementation.

No verified controller-layout or bypass-charging driver interface is exposed.
Global game-rumble strength is not implemented. Stable-volume sound remains
stable brightness: this effect is not a beat detector. Color-dial stick rotation
requires Gamepad mode; in Mouse mode axes have been remapped. Android access may
fail entirely and carries the explicit warning that Android may become unable
to boot. Wider device support is planned.

Android userdata uses the separately provisioned private backend described in
[the Thor mounting guide](https://github.com/lurenjiamax/thorch/blob/feat/thor-custom-kernel/docs/android-userdata-mount.md).
Settings → Android reports backend readiness, service state and mount state;
userdata has explicit read/write mount and clean unmount actions, and opens
`/mnt/aynthor-android/userdata`, a bindfs view of `/mnt/android-data/media/0`.
The view grants the calling user access without rewriting existing Android
ownership or permissions; newly created entries use the shared directory owner.
Other supported partitions remain read-only.
Back up data and validate the backend before mounting. Close applications using
the mount before unmounting through the panel (it removes the bindfs view first);
do not switch systems while cleanup reports an
error. No automatic boot unlock, filesystem repair or private-key provisioning
is performed. A mounted filesystem alone does not prove user files are unlocked.

Control temperature can be changed with a long press; the sensor list includes
current readings. Power shows battery-side draw/charging watts rather than
capacity. Fast charging reflects reported USB PD/PPS or an input above 5.5 V.
Caffine retains its label while the lock icon reflects automatic locking.
Screen sliders share one row with their icons and labels. Tap the volume icon
to mute/unmute without changing volume. New-app output and governors use
tap-to-cycle/hold-to-select buttons. Screenshot mode is only on the control
screenshot button. Independent fan control selects the custom curve; graph
and popup numeric edits apply continuously with coalesced writes.

Settings → About displays the source repository, installed version, device support,
license and warranty statement. Manually deployed builds identify as development
builds; packaged builds read the version generated from PKGBUILD.

MangoHud has one configuration mode in Settings → Performance: Take over or
Release. Takeover automatically persists across restarts and manages system
logging, frame limits and overlay visibility. Release restores the original
configuration and disables the panel's frame-limit/overlay controls. Explicit
game-specific MangoHud overrides may take precedence. Frame limits use numeric
vector icons (30/60/120), with infinity for unlimited.

Buttons includes Back + Home; its default resets the lower touchscreen driver.
Task switching supports Chinese process names and other users' windows. Opening
the AYN panel preserves game focus; explicitly opening Settings accepts focus
for text input. GPU and power indicators use dedicated graphics-card, lightning
and charging-plug icons.
