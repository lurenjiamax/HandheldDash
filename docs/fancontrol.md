# Thorch Fan Curve Quick Guide

HandheldDash exposes fan profiles and custom curves through its Fan page. On
AYN Thor it uses the Thorch BSP backend described below; fan policy is userspace
functionality, not a feature unique to the custom kernel.

Thorch controls the Thor fan with `thorch-fancontrol`. The service reads
temperatures from thermal sysfs sensors, chooses a PWM value from the configured
profile, and writes that value to the fan PWM sysfs node.

When multiple thermal sensors are readable, Thorch follows the hottest selected
sensor by default. This reacts more like Android thermal policy than a broad
sensor average, where idle or cooler zones can hide a hot CPU/GPU spot.

For a quieter or more aggressive curve, start with the built-in profiles:

```bash
sudo sed -i 's/^THORCH_FAN_PROFILE=.*/THORCH_FAN_PROFILE=quiet/' /etc/thorch/hardware.conf
sudo systemctl start thorch-fancontrol.service
sudo thorch-fancontrol status
```

`THORCH_FAN_PROFILE` can be:

- `quiet`: later fan ramp, lower noise.
- `moderate`: balanced default.
- `aggressive`: earlier fan ramp.
- `custom`: user-defined temperature thresholds and PWM speeds.

## Control Panel

Open `aynthor-control` and select **Fan**. The chart shows the service's actual
continuous interpolated curve and current control temperature. Choose Quiet, Balanced, Aggressive,
or Custom. Use **Copy to custom** to edit seven temperature/PWM points and
**Apply custom curve** to save them. The panel requires increasing temperatures,
nondecreasing speeds, and a final speed of 100%.

Configuration changes reload within the polling interval (3 seconds by default)
without restarting the systemd unit. This avoids hitting the startup rate limit
when switching profiles repeatedly.

## Custom Curve

Persistent settings live in `/etc/thorch/hardware.conf`. Temperatures are in
millidegrees Celsius, so `65000` means 65 C. PWM speeds are integers from `0` to
`255`.

Edit the config:

```bash
sudo nano /etc/thorch/hardware.conf
```

Example custom curve:

```bash
THORCH_FAN_PROFILE=custom
THORCH_FAN_POLL_SECONDS=3
THORCH_FAN_SENSOR_MODE=max

THORCH_FAN_T1=50000
THORCH_FAN_T2=55000
THORCH_FAN_T3=60000
THORCH_FAN_T4=65000
THORCH_FAN_T5=70000
THORCH_FAN_T6=75000
THORCH_FAN_MAX_TEMP=80000

THORCH_FAN_CUSTOM_SPEED1=51
THORCH_FAN_CUSTOM_SPEED2=77
THORCH_FAN_CUSTOM_SPEED3=102
THORCH_FAN_CUSTOM_SPEED4=119
THORCH_FAN_CUSTOM_SPEED5=153
THORCH_FAN_CUSTOM_SPEED6=204
THORCH_FAN_CUSTOM_MAX_SPEED=255
```

Custom-only speed keys keep preset curves unchanged. Legacy
`THORCH_FAN_SPEED1..6` and `THORCH_FAN_MAX_SPEED` remain shared overrides.

The running service automatically reloads the file. To start it if stopped:

```bash
sudo systemctl start thorch-fancontrol.service
sudo thorch-fancontrol status
```

The fan interpolates between temperature/PWM nodes. The first ramp starts
5 C below the first node, and the maximum temperature forces full speed.

Thresholds must increase from `THORCH_FAN_T1` through
`THORCH_FAN_MAX_TEMP`. Speeds may stay flat or increase, but values outside
`0..255` are rejected.

## Testing

Check the detected PWM path, selected sensors, current control temperature, and
target PWM:

```bash
sudo thorch-fancontrol status
sudo thorch-fancontrol status-json
```

Apply the current curve once without leaving a daemon running:

```bash
sudo systemctl stop thorch-fancontrol.service
sudo thorch-fancontrol once
```

Start the normal boot service again:

```bash
sudo systemctl enable --now thorch-fancontrol.service
```

Follow service logs while tuning:

```bash
journalctl -fu thorch-fancontrol.service
```

## Sensor And PWM Overrides

Most users should leave hardware paths empty so Thorch can autodetect them. For
bring-up or debugging, the config can pin paths explicitly:

```bash
THORCH_FAN_PWM_PATH=/sys/class/hwmon/hwmon0/pwm1
THORCH_FAN_TEMP_SENSORS="/sys/devices/virtual/thermal/thermal_zone0/temp /sys/devices/virtual/thermal/thermal_zone1/temp"
```

`THORCH_FAN_TEMP_SENSORS` is a space-separated list. When more than one sensor
is configured, `THORCH_FAN_SENSOR_MODE=max` uses the hottest readable value
before selecting the fan speed. Set `THORCH_FAN_SENSOR_MODE=average` to restore
the quieter ROCKNIX-style broad sensor average.

## Safety Notes

Lower-noise curves also mean higher temperatures. Keep a terminal open with
`thorch-fancontrol status` or `journalctl -fu thorch-fancontrol.service` while
tuning, and avoid disabling the service for normal use.

If a custom curve fails validation, `thorch-fancontrol` exits without applying
it. Fix `/etc/thorch/hardware.conf`, then restart the service.

Curves linearly interpolate between temperature/PWM nodes, starting the first ramp
5 °C below the first node. Cooling slows PWM down by about 5% every three seconds;
rising temperatures apply immediately and the maximum temperature forces 100%.
HandheldDash can follow performance presets or keep the fan independent; manually
choosing a fan preset or applying a custom curve enables independent mode.
