# Features and limits

- Performance presets and editable fan curves through the Thorch backend.
- Screen brightness, audio volume, vibration and controller-plan popups.
- Movable control cards and optional monitoring cards.
- KWin window placement, task switching and screenshots.
- Window focus provides Automatic / top / bottom focus selection.
- Lock top screen makes Dash non-activating. Explicit screen locks cover the opposite bare desktop with a transparent, non-focusable touch guard below ordinary applications. Automatic removes the guard. Other applications and explicit Settings can still take focus; this does not provide independent per-screen keyboard focus.
- Dark-screen mode sets brightness to zero and exclusively inhibits that touchscreen without removing the output. The physical Dash key restores original brightness and touch. Panel scanning may continue. Client disconnection restores screens, and hardware-service restart recovers saved brightness.
- Hold a task to select CPU affinity by touch, with per-core hardware maximum frequencies and capacity-tier shortcuts.
- Joystick lighting, configurable hardware keys and optional Android storage access.

Popup selections apply immediately. Tap outside to close. Dashboard edits are saved with the checkmark.

CPU affinity requires Apply. The initial selection follows the main thread; applying updates existing threads, not existing child processes or future launch rules. Core tiers use hardware capacity, falling back to maximum frequency when capacity is unavailable.

Only selected monitoring cards request their samplers. Missing data is shown as a dash.

AYN Thor with the Thorch BSP and KWin is the verified target. Unsupported capabilities are disabled. Gamepad focus does not isolate controller input between games. MangoHud provides frame limits and an optional in-game overlay; the dashboard does not collect FPS logs.

Android storage access is experimental and may affect Android bootability. Bypass charging and controller-layout switching have no verified backend.
