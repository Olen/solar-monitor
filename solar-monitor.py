#!/usr/bin/env python3

from __future__ import absolute_import
import sys
from argparse import ArgumentParser
import configparser
import blegatt
import time

from solardevice import SolarDeviceManager, SolarDevice, PowerDevice, BatteryDevice, RegulatorDevice
from datalogger import DataLogger

import logging 
import duallog

c = configparser.ConfigParser()
c.read('solar-monitor.ini')


if c.getboolean('monitor', 'debug', fallback=False):
    print("Debug enabled")
    level = logging.DEBUG
else:
    level = logging.INFO

duallog.setup('solar-monitor', minLevel=level, fileLevel=level, rotation='daily', keep=30)
# duallog.setup('solar-monitor', minLevel=logging.DEBUG)
# logging.basicConfig(level=logging.DEBUG)


#####
#  
#  Moved to .ini-config

dev_services_list = []
dev_notify_list = []
dev_services_write_list = []
dev_write_list = []

device_manager = None
datalogger = None
config = None

dev_found_list = []
cur_batt_service = None

loop = None

def validate_service_uuid(uuid):
    global cur_batt_service
    if uuid == MERITSUN_SERVICE_UUID:
        cur_batt_service = ('MERITSUN_SERVICE', uuid)
    elif uuid == TBENERGY_SERVICE_UUID:
        cur_batt_service = ('TBENERGY_SERVICE', uuid)
    elif uuid == SOLARLINK_SERVICE_UUID:
        cur_batt_service = ('SOLARLINK_SERVICE', uuid)
    elif uuid == SOLARLINK2_SERVICE_UUID:
        cur_batt_service = ('SOLARLINK2_SERVICE', uuid)
    else:
        logging.warning('Unrecognized Service / Solar device : {}'.format(uuid))


def main():
    global device_manager
    global datalogger
    config = configparser.ConfigParser()
    config.read('solar-monitor.ini')

    arg_parser = ArgumentParser(description="GATT SDK Demo")
    arg_parser.add_argument(
        '--adapter',
        # default='hci0',
        help="Name of Bluetooth adapter, defaults to 'hci0'")
    arg_commands_group = arg_parser.add_mutually_exclusive_group(required=False)
    # arg_commands_group.add_argument(
        # '--auto',
        # metavar='address',
        # type=str,
        # help="Connect and automatically reconnect to a GATT device with a given MAC address")
    arg_commands_group.add_argument(
        '--disconnect',
        metavar='address',
        type=str,
        help="Disconnect a GATT device with a given MAC address")
    args = arg_parser.parse_args()

    if args.adapter:
        config.set('monitor', 'adapter', args.adapter)

    for item in config.items("services"):
        if 'write' in item[0]:
            dev_services_write_list.append(item[1])
        else:
            dev_services_list.append(item[1])
    for item in config.items("characteristics"):
        if 'notify' in item[0]:
            dev_notify_list.append(item[1])
        if 'write' in item[0]:
            dev_write_list.append(item[1])

    device_manager = SolarDeviceManager(adapter_name=config['monitor']['adapter'])
    logging.info("Adapter status - Powered: {}".format(device_manager.is_adapter_powered))
    if not device_manager.is_adapter_powered:
        logging.info("Powering on the adapter ...")
        device_manager.is_adapter_powered = True
        logging.info("Powered on")

    # datalogger = DataLogger(config.get('datalogger', 'url'), config.get('datalogger', 'token'))
    datalogger = DataLogger(config)

    device_manager.update_devices()
    logging.info("Starting discovery...")
    # scan all the advertisements from the services list
    device_manager.start_discovery(dev_services_list[0:])
    # delay / sleep for 10 ~ 15 sec to complete the scanning
    time.sleep(15)
    device_manager.stop_discovery()
    logging.info("Found {} BLE-devices".format(len(device_manager.devices())))
    logging.info("Trying to connect...")
    # device = ConnectAnyDevice(mac_address=args.connect, manager=device_manager)
    # device.connect()
    devices = {}
    for item in config.items("devices"):
        devices[item[1]] = item[0]
    for dev in device_manager.devices():
        # if dev.mac_address != "d8:64:8c:66:f4:d4" and dev.mac_address != "7c:01:0a:41:ca:f9":
        # if dev.mac_address != "d8:64:8c:66:f4:d4":
        if dev.mac_address in devices:
            device = SolarDevice(mac_address=dev.mac_address, manager=device_manager, logger_name=devices[dev.mac_address], reconnect=config.getboolean('monitor', 'reconnect'))
            device.add_services(dev_services_list, dev_notify_list, dev_services_write_list, dev_write_list)
            device.add_datalogger(datalogger)
            device.connect()

    # elif args.auto:
        # device = ConnectAnyDevice(mac_address=args.auto, manager=device_manager, auto_reconnect=True)
        # device.connect()
    # elif args.disconnect:
    if args.disconnect:
        device = SolarAnyDevice(mac_address=args.disconnect, manager=device_manager)
        device.disconnect()
        return

    logging.info("Terminate with Ctrl+C")
    try:
        device_manager.run()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
