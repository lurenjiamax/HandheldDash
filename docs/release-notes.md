HandheldDash 1.4.0 adds window-focus controls and touch-locked dark screens.

- The former Gamepad focus tile is now Window focus, retaining the existing
  Automatic / top / bottom focus selection. Obsolete minimization rules are
  removed automatically. Lock top screen keeps Dash non-activating. Explicit
  screen locks add a transparent, non-focusable touch guard over the opposite
  bare desktop, below normal applications; Automatic removes it. Other apps
  and explicit Settings can still take focus. This is not independent keyboard
  focus for both screens. Physical touch acceptance remains manual.
- Dark-screen controls no longer create black top-level windows. They set the
  panel brightness to zero and exclusively inhibit its physical touchscreen,
  stopping the lower-screen touchpad relay first. Display geometry is unchanged.
  This is dimming, not a promise that panel scanning or power is fully stopped.
- The hardware Dash key restores both displays and touch before notifying the
  interface. Client disconnection also restores the screen. Saved brightness is
  recovered when the hardware service restarts.
- Error notices expire after five seconds. Duplicate background failures do not
  keep the notice visible; a new explicit operation can show a fresh failure.

Screen inhibition requires an explicit touchscreen-to-backlight mapping in the
device profile. Unsupported mappings are disabled. The verified target remains
AYN Thor with Thorch BSP and KWin. No unit tests are run; verification uses actual
runtime operations and device package deployment.
