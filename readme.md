# App Timer (Parental Control)

Control apps usage time with a command line application.

The python daemon will watch for the apps executable and store usage time for them. It can block an app if the usage is off limits.

I'm using this at a raspberry pi gaming station (retropie) to enforce usage limits. Other use cases are very plausible, like any other gaming platform or even enforcing a pomodoro timer for your coding time. Be creative and let me know.

## Config

```yaml
# how often should the script check for apps runtime?
check-interval: 1
# optional http status endpoint configuration
status-server:
  host: 127.0.0.1
  port: 8090
# timers: list of apps that will be watched
timers:
  # the app name (list key)
  gaming:
    # list of the app executables
    apps:
      - retroarch
      - minecraft
    # how many minutes of usage
    time-limit: 60
    # within how many hours of interval
    limit-interval: 12
    # optional: warn N minutes before the limit is reached
    warn-threshold: 5
    # run on every loop inside the warning window (anything executable)
    warn-command: "notify-send 'App Timer' 'Only {time_left_int} minutes left'"
    # run only on the final loop before apps are blocked
    final-warn-command: "notify-send 'App Timer' 'Last minute before shutdown'"
```

`warn-threshold` is measured in minutes and triggers the `warn-command` every loop while there is still time remaining. `final-warn-command` fires once on the last loop before the timer exceeds its limit (based on `check-interval`). All commands are executed through the shell, so they can show desktop notifications, play sounds, etc. You can interpolate values in the command string using `{timer_name}`, `{time_left}`, `{time_left_int}`, `{time_left_floor}`, and `{time_left_seconds}` (any Python format specifiers are supported, e.g. `{time_left:.1f}`).

If the systemd service runs as `root`, wrap desktop commands so they execute inside your session:

```yaml
warn-command: >
  runuser -l randogoth -c 'DISPLAY=:0 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus notify-send "App Timer" "{timer_name}: {time_left_int} minutes left"'
```

The status server shows timer usage at `http://host:port/` (defaults `127.0.0.1:8090`). Override the bind address or port via the `status-server` block, or keep using the `APP_TIMER_STATUS_HOST` / `APP_TIMER_STATUS_PORT` environment variables if you prefer exporting them in your service unit.

## Installation

There's a systemd service file ready for use.

```bash
  # download the sources
  cd /opt/
  git clone https://github.com/thiagof/app-timer
  cd app-timer
  # yaml dependency
  sudo -H pip3 install -r requirements.txt
  # setup the daemon
  sudo cp ./app-timer.service /etc/systemd/system/app-timer.service
  sudo systemctl enable app-timer
  # check the service
  sudo systemctl status app-timer
```

You must edit the file `config.yaml` for your timers setup.

In the code there is some python 3 so this is required. For testing the timer and check it's outputs/configs, run `python3 timer.py`.
