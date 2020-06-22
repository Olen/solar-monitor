# solar-monitor

This utility monitors defined BLE-devices, and sends parsed data to a remote server using either MQTT or json/HTTP

Currently supported
- SRNE regulators (monitored by the SolarLink APP: https://play.google.com/store/apps/details?id=com.shuorigf&hl=en_SG
- Litium Batteries (monitored by the Meritsun APP: https://play.google.com/store/apps/details?id=com.meritsun.smartpower&hl=en_SG



# Requirements
Look at requirements.txt
Be aware that libscrc is NOT pip-installable on RPI, so you need to build it from source: https://github.com/hex-in/libscrc

It runs fine on a Raspberry Pi 4, making it ideal for monitoring places where there is no grid power, as it uses a minimal amount of power.



# Usage

You need the following:

* solar-monitor.py  The actual daemon 
* solardevice.py    Extension of blegatt and some classes to store the values that are read from the BLE-devices
* meritsumutil.py   Parsing and interpreting data from the Meritsun BLE-devices
* solarlinkutil.py  Parsing and interpreting data from the SolarLink BLE-devices
* datalogger.py     Class for pushing data to remote servers

Also

* solar-monitor.service - A systemd service-description for auto-starting the service
* solar-monitor.ini.dist  Configuration-file. To be modified and renamed to solar-monitor.ini

Copy solar-monitor.ini.dist to solar-monitor.ini, and add the correct mac addresses to your BLE devices (NOT your mobile phone with the app, but the actual battery/bluetooth adapter)

Run solar-monitor.py (might require root privileges to access bluetooth directly)

# Credits
A huge thanks to Pramod P K https://github.com/prapkengr/ for doing reverse engineering and decompiling of the Android Apps to figure out the protocols used.

