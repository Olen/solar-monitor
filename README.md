# solar-monitor

This utility monitors defined BLE-devices, and sends parsed data to a remote server using either MQTT or json/HTTP

Currently supported

| Device | Plugin | Vendor app |
|---|---|---|
| SRNE regulators | `SolarLink` | [SolarLink](https://play.google.com/store/apps/details?id=com.shuorigf) |
| Renogy BT-1 | `SolarLink` | same protocol as SRNE |
| Lithium batteries | `Meritsun` | [Meritsun](https://play.google.com/store/apps/details?id=com.meritsun.smartpower) |
| Lithium batteries | `RenogyBatt` | [Renogy DC Home](https://play.google.com/store/apps/details?id=com.renogy.dchome) |
| Lithium batteries | `Topband` | [TBEnergy](https://play.google.com/store/apps/details?id=com.topband.smartpower) |
| Victron VE.Direct | `VEDirect` | Phoenix inverters tested; other devices in progress |
| Hacien / HC batteries | `Hacien` | [HC Battery](https://play.google.com/store/apps/details?id=com.chiptrip.hcbattery) — in progress |

Adding a device family means writing one plugin — see [PLUGINS.md](PLUGINS.md).


# Update 2026-08-10

- **Home Assistant discovery over MQTT** — sensors appear automatically, grouped per physical unit, and controllable devices get switches.
- **Per-device validation limits, tunable from the ini.** Readings outside a plausible range are rejected rather than published; the bounds are configurable for hardware the defaults do not fit, such as a 24 V array. See [Tuning the value limits](#tuning-the-value-limits).
- **Configurable resend interval** for values that have not changed, for consumers that treat a long gap as a stale sensor.
- **Every device is held connected continuously**, which notify-only batteries require to deliver anything at all. A healthy adapter holds several links at once. See [docs/BLUETOOTH.md](docs/BLUETOOTH.md).
- **Runs as a non-root user**, both in the container and under the supplied systemd unit, which is sandboxed and keeps its code and config read-only.
- **Self-contained image**, with pinned dependencies kept current by dependabot.


# Update 2025-01-31
The latest updates adds threading to the application, so it will now poll each device in its own thread, and log data in a different thread.

This ensures that issues with one connected device should no longer block and stop the other devices from logging.  I am running ths version myself, and it seems to work fine, but any threading application is a potential risk, especially when it comes to resource usage, so please watch carefully after upgrading.

# Requirements
Look at requirements.txt

Be aware that libscrc is NOT pip-installable on all versions of RPI, so you need to build it from source: https://github.com/hex-in/libscrc

The monitor runs fine on a Raspberry Pi zero, making it ideal for monitoring places where there is no grid power, as it uses a minimal amount of power.

# Docker

Images are published to the GitHub container registry for `linux/amd64` and
`linux/arm64`:

```
ghcr.io/olen/solar-monitor:latest
ghcr.io/olen/solar-monitor:2026.8      # latest patch of that series
ghcr.io/olen/solar-monitor:2026.8.0    # exact release
```

To run the service as a container, you can use the included `docker-compose.yaml`

* Copy `solar-monitor.ini.dist` to e.g `~/solar-monitor/solar-monitor.ini`
* Edit the ini-file as per the instructions below.
* Ensure that docker-compose.yaml has the right path to the ini-file
* Run:

```
docker compose pull && docker compose up -d
```
in the same dir as you downloaded these files.

To build the image yourself instead of pulling it, use `docker compose up -d
--build`. That compiles `libscrc` and takes a while on a Raspberry Pi.

The container runs as uid 1000. If the ini-file and log directory on the host
belong to a different user, build with `--build-arg UID=... --build-arg GID=...`
to match.

Check the logs with

```
docker logs solar-monitor
```

`network=host` is needed because access to bluetooth devices requires host network.


# Running as a service

You need the following:

* solar-monitor.py  The actual daemon 
* solardevice.py    Extension of ble gatt and some classes to store the values that are read from the BLE-devices
* duallog.py        CLI and file-logger with multiple destinations
* datalogger.py     Class for pushing data to remote servers
* plugins/*         Implemetation of vendor specific BLE parsing

Also

* solar-monitor.service - A systemd service-description for auto-starting the service
* solar-monitor.ini.dist  Configuration-file. To be modified and renamed to solar-monitor.ini

Install the code somewhere the service user cannot write, keep the config
separate, and run as a dedicated user:

```sh
sudo useradd --system --no-create-home --shell /usr/sbin/nologin solar-monitor

sudo install -d -o root -g root /opt/solar-monitor
sudo cp -r *.py plugins /opt/solar-monitor/

sudo install -d -o root -g solar-monitor -m 750 /etc/solar-monitor
sudo install -o root -g solar-monitor -m 640 solar-monitor.ini /etc/solar-monitor/
```

The ini holds your MQTT password and datalogger token, so it is readable by the
service and nobody else. The shipped unit expects exactly these paths.

```sh
sudo cp solar-monitor.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now solar-monitor
```

BlueZ is reached over the system D-Bus, which the policy shipped with bluez
allows for any user, so the service needs no capabilities and no group
membership.

Alternatively just run `solar-monitor.py` in something like termux or screen (might require root privileges to access bluetooth directly)


# Resend interval

A value is published when it changes. A value that has *not* changed is resent
every 10 minutes, so consumers that treat a long gap as a stale sensor stay
happy. Set it per install in the `[datalogger]` section:

```ini
[datalogger]
refresh = 30
```

Minutes. A longer interval means less traffic; a shorter one keeps graphs and
external loggers from complaining when a value is genuinely steady. It applies
to MQTT publishing as well as the HTTP datalogger.

# Tuning the value limits

Every reading is checked against bounds before it is published: a hard `min` and
`max`, and a `maxdiff` limiting how far a value may move between readings. This
is deliberate — these devices report occasional nonsense, and an unfiltered spike
shows up as a dip in your graphs or a false alert.

The shipped defaults suit the hardware this was written against. Other hardware
legitimately exceeds them: two 24 V panels in series reach nearly 70 V, well past
the default input-voltage ceiling, and every reading is then rejected as out of
bands with a warning in the log.

Override any bound in that device's own section. The option is the value's name
followed by `_min`, `_max` or `_maxdiff`:

```ini
[regulator]
type = SolarLink
mac = 11:11:11:11:11:11
input_mvoltage_max = 96000       # 96 V panel input instead of the default
input_mvoltage_maxdiff = 48000
```

Values are stored at the best available resolution, so **the units are milli-**
**whatever**: millivolts, milliamps, milliwatts. Temperature is /10 kelvin and
soc is /10 %. `96000` above is 96 V.

Tunable names, depending on device type:

| | |
|---|---|
| voltage | `mvoltage`, `input_mvoltage`, `charge_mvoltage` |
| current | `mcurrent`, `input_mcurrent`, `charge_mcurrent` |
| power | `mpower`, `input_mpower`, `charge_mpower` |
| capacity | `mcapacity`, `max_capacity`, `exp_capacity` |
| other | `dsoc`, `dkelvin`, `bkelvin`, `charge_cycles` |

Each override is logged at startup, so `Changed input_mvoltage max: 48000 -> 96000`
in the log confirms it was picked up. An unparseable value is ignored with a
warning and the default kept.

If a reading is rejected but you believe the device, the log line names the value,
the bound and both numbers — that tells you which option to set and to what.

# Output
```
2020-06-22 13:34:09,149 INFO    : Adapter status - Powered: True
2020-06-22 13:34:09,284 INFO    : Starting discovery...
2020-06-22 13:34:24,429 INFO    : Found 2 BLE-devices
2020-06-22 13:34:24,430 INFO    : Trying to connect...
2020-06-22 13:34:24,464 INFO    : [regulator] Connecting to d4:36:39:xx:xx:xx
2020-06-22 13:34:24,836 INFO    : [regulator] Connected to BT-TH-39xxxxxx
2020-06-22 13:34:24,836 INFO    : [regulator] Resolved services
(...)
2020-06-22 13:34:24,843 INFO    : [regulator] Found dev notify char [0000fff1-0000-1000-8000-00805f9b34fb]
2020-06-22 13:34:24,843 INFO    : [regulator] Subscribing to notify char [0000fff1-0000-1000-8000-00805f9b34fb]
2020-06-22 13:34:24,843 INFO    : [regulator] Found dev write char [0000ffd1-0000-1000-8000-00805f9b34fb]
2020-06-22 13:34:24,844 INFO    : [regulator] Subscribing to notify char [0000ffd1-0000-1000-8000-00805f9b34fb]
2020-06-22 13:34:24,847 INFO    : [battery_1] Connecting to 7c:01:0a:xx:xx:xx
2020-06-22 13:34:25,147 INFO    : [battery_1] Connected to 12V100Ah-027
2020-06-22 13:34:25,148 INFO    : [battery_1] Resolved services
(...)
2020-06-22 13:34:25,155 INFO    : [battery_1] Found dev notify char [0000ffe4-0000-1000-8000-00805f9b34fb]
2020-06-22 13:34:25,155 INFO    : [battery_1] Subscribing to notify char [0000ffe4-0000-1000-8000-00805f9b34fb]
2020-06-22 13:34:25,155 INFO    : Terminate with Ctrl+C
(...)
2020-06-22 13:34:27,431 INFO    : [regulator] Sending new data current: 0.5
2020-06-22 13:34:27,432 INFO    : [regulator] Sending new data charge_current: 1.8
2020-06-22 13:34:27,433 INFO    : [regulator] Sending new data voltage: 13.4
2020-06-22 13:34:27,434 INFO    : [regulator] Sending new data charge_voltage: 13.4
2020-06-22 13:34:27,435 INFO    : [regulator] Sending new data power: 7.0
2020-06-22 13:34:27,436 INFO    : [regulator] Sending new data soc: 100.0
2020-06-22 13:34:27,438 INFO    : [battery_1] Value of state changed from None to charging
2020-06-22 13:34:27,438 INFO    : [battery_1] Value of health changed from None to perfect
2020-06-22 13:34:27,439 INFO    : [battery_1] Sending new data current: 0.9
2020-06-22 13:34:27,440 INFO    : [battery_1] Sending new data voltage: 13.6
2020-06-22 13:34:27,442 INFO    : [battery_1] Sending new data power: 0.0
```
Updates can be sent to a remote server using either MQTT or JSON over HTTP(s)


## MQTT
By using MQTT you will also get a listener for each topic, that can be used to set certain parameteres
E.g. the app is sending MQTT states as
`prefix/regulator/power_switch_state/state = 0`

And you can turn power on and off by sending
`prefix/regulator/power_switch_state/set = 1`
from another MQTT client connected to the broker.  *So do NOT connect to public brokers!*

The MQTT-implemetation will automatically create sensors and switches in Home Assistant according to this spec: https://www.home-assistant.io/docs/mqtt/discovery/

## JSON
The data will be posted as JSON to a given URL as an object:
```
{"device": "battery_1", "current": -0.5, "ts": "2020-04-19 21:36:55"}
{"device": "battery_1", "state": "discharging", "ts": "2020-04-19 21:36:55"}
{"device": "regulator", "power_switch_state": 0, "ts": "2020-04-19 21:36:56"}
{"device": "battery_1", "current": 0.0, "ts": "2020-04-19 21:36:56"}
{"device": "battery_1", "state": "standby", "ts": "2020-04-19 21:36:57"}
{"device": "battery_1", "capacity": 105.1, "ts": "2020-04-19 21:41:26"}
```

This allows you to remotely monitor the data from your installation:

<img src="https://github.com/Olen/solar-monitor/blob/master/img/SRNE-Screenshot.png?raw=true">

<img src="https://github.com/Olen/solar-monitor/blob/master/img/Battery-Screenshot.png?raw=true">



# Plugins

Each supported device family has a plugin under `plugins/`, responsible for that
device's framing and decoding. [PLUGINS.md](PLUGINS.md) describes what a plugin
must provide.


# Releases

Pushing a `v`-prefixed tag builds and publishes the image:

```
git tag -a v2026.8.0 -m "..."
git push origin v2026.8.0
```

Versions are `vYYYY.M.PATCH`. The tag produces `2026.8.0`, `2026.8` and
`latest`, each carrying `org.opencontainers.image.*` metadata — source, revision,
version, licence and build time:

```
docker buildx imagetools inspect ghcr.io/olen/solar-monitor:latest
```

Nothing is published on an ordinary push to `master`. Pull requests that touch
the `Dockerfile`, `requirements.txt` or the workflow build both architectures
without pushing.


# Licence

GPLv3. See [LICENSE](LICENSE).


# Credits
A huge thanks to Pramod P K https://github.com/prapkengr/ for doing reverse engineering and decompiling of the Android Apps to figure out the protocols used.

<a href="https://www.buymeacoffee.com/olatho" target="_blank">
<img src="https://user-images.githubusercontent.com/203184/184674974-db7b9e53-8c5a-40a0-bf71-c01311b36b0a.png" style="height: 50px !important;"> 
</a>
