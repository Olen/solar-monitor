# solar-monitor

This utility monitors defined BLE-devices, and sends parsed data to a remote server

# Usage

* solar-monitor.py  The actual daemon 
* solardevice.py    Extension of blegatt and some classes to store the values that are read from the BLE-devices
* powerutil.py      Utils for parsing and interpreting data from the BLE-devices
* datalogger.py     Class for pushing data to remote servers

