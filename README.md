# solar-monitor

This utility monitors defined BLE-devices, and sends parsed data to a remote server using either MQTT or json/HTTP

Currently supported
- SRNE regulators (monitored by the SolarLink APP: https://play.google.com/store/apps/details?id=com.shuorigf
- Lithium Batteries (monitored by the Meritsun APP: https://play.google.com/store/apps/details?id=com.meritsun.smartpower
        or monitored by Renogy DC Home APP: https://play.google.com/store/apps/details?id=com.renogy.dchome)
- Victron Energy - VE.Direct devices - currently only Phoenix inverters are tested.  Work in progress to add more devices
- Renogy BT-1 (uses the same protocol as the SolarLink/SRNE)

# Requirements
Look at requirements.txt

Be aware that libscrc is NOT pip-installable on RPI, so you need to build it from source: https://github.com/hex-in/libscrc

The monitor runs fine on a Raspberry Pi zero, making it ideal for monitoring places where there is no grid power, as it uses a minimal amount of power.



# Usage

You need the following:

* solar-monitor.py  The actual daemon 
* solardevice.py    Extension of ble gatt and some classes to store the values that are read from the BLE-devices
* duallog.py        CLI and file-logger with multiple destinations
* datalogger.py     Class for pushing data to remote servers
* plugins/*         Implemetation of vendor specific BLE parsing

Also

* solar-monitor.service - A systemd service-description for auto-starting the service
* solar-monitor.ini.dist  Configuration-file. To be modified and renamed to solar-monitor.ini

Copy solar-monitor.ini.dist to solar-monitor.ini, and add the correct mac addresses to your BLE devices (NOT your mobile phone with the app, but the actual battery/bluetooth adapter)

Run solar-monitor.py (might require root privileges to access bluetooth directly)


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



# Credits
A huge thanks to Pramod P K https://github.com/prapkengr/ for doing reverse engineering and decompiling of the Android Apps to figure out the protocols used.

<a href="https://www.buymeacoffee.com/olatho" target="_blank">
<img src="https://user-images.githubusercontent.com/203184/184674974-db7b9e53-8c5a-40a0-bf71-c01311b36b0a.png" style="height: 50px !important;"> 
</a>
