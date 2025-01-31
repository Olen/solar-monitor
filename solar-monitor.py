#!/usr/bin/env python3

from argparse import ArgumentParser
import configparser
import time
import logging
import sys

from solardevice import SolarDeviceManager, SolarDevice
from datalogger import DataLogger
import duallog

import concurrent.futures
import queue
import threading





# Read arguments
arg_parser = ArgumentParser(description="Solar Monitor")
arg_parser.add_argument(
    '--adapter',
    help="Name of Bluetooth adapter. Overrides what is set in .ini")
arg_parser.add_argument(
    '-d', '--debug', action='store_true',
    help="Enable debug")
arg_parser.add_argument(
    '--ini',
    help="Path to .ini-file. Defaults to 'solar-monior.ini'")
args = arg_parser.parse_args()

# Read config
config = configparser.ConfigParser()

ini_file = "solar-monitor.ini"
if args.ini:
    ini_file = args.ini

try:
    config.read(ini_file)
except:
    print(f"Unable to read ini-file {ini_file}")
    sys.exit(1)


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

# Create the message queue
pipeline = queue.Queue(maxsize=10000)

# Set up data logging
# datalogger = None
try:
    datalogger = DataLogger(config)
except Exception as e:
    logging.error("Unable to set up datalogger")
    logging.error(e)
    sys.exit(1)

def threaded_logger(queue, datalogger):
    x = time.time()
    try:
        while True:
            if not queue.empty():
                y = time.time()
                if y > x + 1:
                    logging.debug(f"Queue size = {queue.qsize()}")
                    x = y
                logger_name, item, value = queue.get()
                datalogger.log(logger_name, item, value)
    except Exception as e:
        logging.error(e)
        sys.exit(299)

executor = concurrent.futures.ThreadPoolExecutor(max_workers=100)

executor.submit(threaded_logger, pipeline, datalogger)

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

def threaded_poller(dev, device_manager, logger_name, config, datalogger, queue):
    logging.info("Trying to connect to {}...".format(dev.mac_address))
    try:
        device = SolarDevice(mac_address=dev.mac_address, manager=device_manager, logger_name=logger_name, config=config, datalogger=datalogger, queue=queue)
    except Exception as e:
        logging.error(e)
        return
    device.connect()


for dev in device_manager.devices():
    logging.debug("Processing device {} {}".format(dev.mac_address, dev.alias()))
    for section in config.sections():
        if config.get(section, "mac", fallback=None) and config.get(section, "type", fallback=None):
            mac = config.get(section, "mac").lower()
            if dev.mac_address.lower() == mac:
                executor.submit(threaded_poller, dev, device_manager, section, config, datalogger, pipeline)
                logging.info("Waiting for device to connect")
                time.sleep(1)

logging.debug("Waiting for devices to connect...")
time.sleep(10)
logging.info("Terminate with Ctrl+C")
try:
    device_manager.run()
except KeyboardInterrupt:
    pass

for dev in device_manager.devices():
    try:
        dev.disconnect()
    except:
        pass



