# Thor RGB Quick Guide

Use HandheldDash's lighting controls for normal operation. The commands below
describe the optional Thorch BSP backend on AYN Thor; they are not custom-kernel
features and are not supplied by HandheldDash on every platform.

Thorch controls the Thor joystick LEDs with `thorch-rgb`. Each color is an RGB
triple: red, green, and blue values from `0` to `255`.

Examples:

```bash
sudo thorch-rgb set 255 0 0      # red
sudo thorch-rgb set 0 255 0      # green
sudo thorch-rgb set 0 0 255      # blue
sudo thorch-rgb set 255 128 0    # orange
sudo thorch-rgb set 0 128 255    # cyan-blue
sudo thorch-rgb off              # turn LEDs off
sudo thorch-rgb battery          # restore battery-status color mode
```

## Commands

`sudo thorch-rgb status` prints the current mode, brightness, saved static
color, detected LED backend, and battery status.

`sudo thorch-rgb set R G B` saves a static color in `/etc/thorch/rgb.conf` and
applies it immediately. Use this when you want the color to survive reboot.

`sudo thorch-rgb apply R G B` applies a color immediately without saving it.
This is useful for scripts, testing, or one-off effects.

`sudo thorch-rgb battery` switches back to battery-status mode. In this mode the
LEDs update from battery charge:

- Green: full, nearly full, or above 40%.
- Yellow/orange: mid battery.
- Red: low battery.
- Orange while charging below 95%.

`sudo thorch-rgb off` saves the off mode and turns the LEDs off.

## Config

Persistent defaults live in `/etc/thorch/rgb.conf`:

```bash
THORCH_RGB_MODE=battery
THORCH_RGB_BRIGHTNESS=255
THORCH_RGB_STATIC_R=0
THORCH_RGB_STATIC_G=128
THORCH_RGB_STATIC_B=255
THORCH_RGB_POLL_SECONDS=15
```

`THORCH_RGB_MODE` can be `battery`, `static`, or `off`.

`THORCH_RGB_BRIGHTNESS` scales every mode from `0` to `255`; leave the color
values alone and lower this when the LEDs are too bright.

`THORCH_RGB_STATIC_R`, `THORCH_RGB_STATIC_G`, and `THORCH_RGB_STATIC_B` are the
saved static color values.

`THORCH_RGB_POLL_SECONDS` controls how often battery mode refreshes.

After editing the file by hand, apply it with:

```bash
sudo thorch-rgb apply-config
```

## Services

`thorch-rgb.service` applies the configured mode at boot.

`thorch-rgb-battery.service` keeps battery-status mode updating when
`THORCH_RGB_MODE=battery`.
