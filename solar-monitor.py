from argparse import ArgumentParser
import configparser
import time
import logging 
import sys

from solardevice import SolarDeviceManager, SolarDevice
from datalogger import DataLogger
import duallog



# Read config
config = configparser.ConfigParser()
config.read('solar-monitor.ini')




# Read arguments
arg_parser = ArgumentParser(description="Solar Monitor")
arg_parser.add_argument(
    '--adapter',
    help="Name of Bluetooth adapter. Overrides what is set in .ini")
arg_parser.add_argument(
    '-d', '--debug', action='store_true',
    help="Enable debug")
args = arg_parser.parse_args()

if args.adapter:
    config.set('monitor', 'adapter', args.adapter)
if args.debug:
    config.set('monitor', 'debug', '1')


# Set up logging
if config.getboolean('monitor', 'debug', fallback=False):
    print("Debug enabled")
    level = logging.DEBUG
else:
    level = logging.INFO
duallog.setup('solar-monitor', minLevel=level, fileLevel=level, rotation='daily', keep=30)

# Set up data logging
# datalogger = None
datalogger = DataLogger(config)


# Set up device manager and adapter
device_manager = SolarDeviceManager(adapter_name=config['monitor']['adapter'])
logging.info("Adapter status - Powered: {}".format(device_manager.is_adapter_powered))
if not device_manager.is_adapter_powered:
    logging.info("Powering on the adapter ...")
    device_manager.is_adapter_powered = True
    logging.info("Powered on")




# Run discovery
device_manager.update_devices()
logging.info("Starting discovery...")
# scan all the advertisements from the services list
device_manager.start_discovery()
discovering = True
wait = 15
found = []
# delay / sleep for 10 ~ 15 sec to complete the scanning
while discovering:
    time.sleep(1)
    f = len(device_manager.devices())
    logging.debug("Found {} BLE-devices so far".format(f))
    found.append(f)
    if len(found) > 5:
        if found[len(found) - 5] == f:
            # We did not find any new devices the last 5 seconds
            discovering = False
    wait = wait - 1
    if wait == 0:
        discovering = False

device_manager.stop_discovery()
logging.info("Found {} BLE-devices".format(len(device_manager.devices())))


for dev in device_manager.devices():
    for section in config.sections():
        if config.get(section, "mac", fallback=None) and config.get(section, "type", fallback=None):
            mac = config.get(section, "mac").lower()
            if dev.mac_address.lower() == mac:
                logging.info("Trying to connect to {}...".format(dev.mac_address))
                try:
                    device = SolarDevice(mac_address=dev.mac_address, manager=device_manager, logger_name=section, config=config, datalogger=datalogger)
                except Exception as e:
                    logging.error(e)
                    continue
                device.connect()
logging.info("Terminate with Ctrl+C")
try:
    device_manager.run()
except KeyboardInterrupt:
    pass


sys.exit()


devices = {}
for item in config.items("devices"):
    devices[item[1].lower()] = item[0].lower()

    # logging.info("Looking at {}...".format(dev.mac_address))
    # if dev.mac_address != "d8:64:8c:66:f4:d4" and dev.mac_address != "7c:01:0a:41:ca:f9":
    # if dev.mac_address != "d8:64:8c:66:f4:d4":
    if dev.mac_address.lower() in devices:
        logging.info("Trying to connect to {}...".format(dev.mac_address))
        device = SolarDevice(mac_address=dev.mac_address, manager=device_manager, logger_name=devices[dev.mac_address], reconnect=config.getboolean('monitor', 'reconnect'))
        device.add_services(dev_services_list, dev_notify_list, dev_services_write_list, dev_write_list)
        device.add_datalogger(datalogger)
        device.connect()






 
            



types = []
macs  = []

for x in c:
    print(x)
    if c.get(x, "mac", fallback=None) and c.get(x, "type", fallback=None):
        t = c.get(x, "type")
        if t not in types:
            types.append(t)

        macs.append(c.get(x, "mac"))

modules = {}
for x in types:
    try:
        mod = __import__("plugins." + x)
        modules[x] = getattr(mod, x)
        print ("Successfully imported ", x, '.')
    except ImportError:
        print ("Error importing ", x, '.')

# dev = modules["SolarLink"].Util()
# print(dev)

dev_services_list = []
dev_notify_list = []
dev_services_write_list = []
dev_write_list = []



for m in modules:
    print(m)
    dev_services_list.append(getattr(modules[m].Config, "NOTIFY_SERVICE_UUID", None))
    dev_notify_list.append(getattr(modules[m].Config, "NOTIFY_CHAR_UUID", None))
    dev_services_write_list.append(getattr(modules[m].Config, "WRITE_SERVICE_UUID", None))
    dev_write_list.append(getattr(modules[m].Config, "WRITE_CHAR_UUID", None))
print(dev_services_list)
print(dev_notify_list)
print(dev_services_write_list)
print(dev_write_list)



