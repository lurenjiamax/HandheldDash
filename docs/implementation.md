# Screens, screenshot and audio lighting

The Screen control page offers a default output for newly opened application
windows: Desktop default, Top (DSI-2), or Bottom (DSI-1). Existing windows stay
where they are when the default changes.

Tasks show the current output of every application window. Hold a task for
550 ms to move it to either screen, remember that application's launch output,
or remove its override. Per-application rules use the KWin resource class and
apply to all windows of that class. A manual move alone does not save a rule.
KWin applies these choices through the existing user-session placement script.

Screenshot has Region, Top screen and Bottom screen modes. Tap the Control
page capture button to take a screenshot; hold it to select and remember the
mode. Screen control also provides a mode selector. Region opens Spectacle
selection; Top/Bottom crop a uniformly scaled desktop capture to the named
output. Captures hide the panel first, save a unique PNG to Pictures/AYN Thor
and show a notification. Errors reopen the panel and show the error message.

Thor exposes Speaker and Headphones audio sinks, not separate Top and Bottom
speaker devices. Volume controls operate on the default playback sink. Window
placement cannot split the physical speaker volume by display.

Lighting has Off, Battery, Static and Audio reactive modes. Audio reactive reads
stereo float PCM from the default playback sink's monitor using the installed
PipeWire PulseAudio compatibility utilities (pactl and parec). It never captures
the microphone and never writes recorded audio to disk. Changing the default
playback output reattaches capture at the next status refresh (about 2 seconds).

Left and right channel RMS levels separately drive the left and right joystick
LED rings, including all four multicolor LEDs in each ring. Each side has a
saved color and a two-point XY pad: X sets the minimum and maximum output
brightness, Y sets logarithmic sensitivity from 1x to 20x. Ring previews show
actual computed output. Soft compression expands quiet detail; time-based
90 ms attack and 280 ms release smooth both rising and falling brightness.
Missing short PCM batches preserve the envelope for 200 ms rather than
introducing artificial silence. True silence fades to zero regardless of the
configured minimum. Existing global brightness controls regular modes. Frames are
sent at most 20 times per second, with one in-flight D-Bus frame. The root daemon
validates each frame and writes the hardware channels in their reported
multi_index order. Frames are not persisted or routed through the general
settings queue. Silence fades to black; missing frames for 2 seconds also turn
both rings off. The UI remains running while hidden to keep the effect active.

User choices are in ~/.config/aynthor/settings.json. Audio reactive mode is
saved by the daemon in /var/lib/aynthor/preferences.json; the underlying BSP RGB
mode is Off so the battery service cannot overwrite the effect. Turning audio
mode off restores the selected regular BSP mode.

Runtime commands required by scripts/install.sh: spectacle, notify-send, wpctl,
pactl, parec, qdbus6. The target already provides these; no new Python dependency
was added. Earlier practical verification and screenshots are in artifacts/lighting-screen/.
The XY/smoothing and screenshot-mode update was deployed without further tests
at the user's request; previous screenshots describe the previous interface.

## Dynamic audio response and input modes

The audio envelope now uses one shared stereo RMS peak reference with a
5-second decay during non-silent input. Silence freezes the reference and closes
the output gate. Each channel is normalized against that reference, preserving
stereo balance. The pad's Y coordinate (S, 0–100%) controls a relative threshold
and response contrast instead of multiplying the audio level. The normal peak
target is 90% of the configured brightness span, leaving headroom. The existing
90 ms attack and 280 ms release remain time-based. This borrows the adaptive
normalization principle from WLED/LedFx, rather than their complete FFT or PI
controller implementations. It remains a volume effect; steady-volume input
has steady brightness.

The Control page Input mode button replaces Clear memory. It cycles Gamepad and
Mouse, with a hold menu. The daemon uses InputPlumber's existing default.yaml
and mouse_keyboard_wasd.yaml profiles. Mouse mode maps the right stick to mouse
motion and the left stick to WASD; this is separate from hardware button layout.

L3/R3 actions now enter the color action handler directly, bypassing configurable
Home/Back lookup. The daemon also observes BTN_THUMBL/BTN_THUMBR on the virtual
Xbox controller, with the existing duplicate-event debounce. A color ring opens
only while the Lighting page is visible. In Gamepad mode, stick-axis observation
supports dial rotation. Mouse mode remaps axes to mouse/keyboard events, so the
same gamepad-axis dial observation is not available there; touch selection
remains available. No functional tests were run for this update at the user's
request.
