#!/usr/bin/env python3

from __future__ import absolute_import
import sys
from argparse import ArgumentParser
import configparser
import blegatt
import time

from solardevice import SolarDeviceManager, SolarDevice, PowerDevice, BatteryDevice, RegulatorDevice
from smartpowerutil import SmartPowerUtil
from datalogger import DataLogger

from smartpower_battery_util_rpi import *

import logging 
import duallog
duallog.setup('solar-monitor', minLevel=logging.INFO)
# duallog.setup('solar-monitor', minLevel=logging.DEBUG)
# logging.basicConfig(level=logging.DEBUG)


#####
#  
#  Moved to .ini-config

dev_services_list = []
dev_notify_list = []

device_manager = None
datalogger = None
config = None

dev_found_list = []
cur_batt_service = None

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

# implementation of blegatt.DeviceManager, discovers any GATT device
class SolarDeviceManager(blegatt.DeviceManager):
    def device_discovered(self, device):
        logging.info("[{}] Discovered, alias = {}".format(device.mac_address, device.alias()))
        # self.stop_discovery()   # in case to stop after discovered one device

    def make_device(self, mac_address):
        return SolarDevice(mac_address=mac_address, manager=self)


# implementation of blegatt.Device, connects to selected GATT device
class SolarDevice(blegatt.Device):
    global config      
    def __init__(self, mac_address, manager, logger_name = 'unknown'):
        super().__init__(mac_address=mac_address, manager=manager)
        self.auto_reconnect = config.getboolean('monitor', 'reconnect')
        self.reader_activity = None
        self.logger_name = logger_name

        if "battery" in self.logger_name:
            self.entities = BatteryDevice()
        elif "regulator" in self.logger_name:
            self.entities = RegulatorDevice()
        else:
            self.entities = PowerDevice()

        self.smartPowerUtil = SmartPowerUtil(self.alias, self.entities)  

    @property
    def alias(self):
        return super().alias().strip()

    def connect(self):
        logging.info("[{}] Connecting to {}".format(self.logger_name, self.mac_address))
        super().connect()

    def connect_succeeded(self):
        super().connect_succeeded()
        logging.info("[{}] Connected to {}".format(self.logger_name, self.alias))

    def connect_failed(self, error):
        super().connect_failed(error)
        logging.info("[{}] Connection failed: {}".format(self.logger_name, str(error)))

    def disconnect_succeeded(self):
        super().disconnect_succeeded()
        logging.info("[{}] Disconnected".format(self.logger_name))
        if self.auto_reconnect:
            self.connect()

    def services_resolved(self):
        super().services_resolved()
        logging.info("[{}] Connected to {}".format(self.logger_name, self.alias))

        logging.info("[{}] Resolved services".format(self.logger_name))
        for service in self.services:
            logging.info("[{}]  Service [{}]".format(self.logger_name, service.uuid))
            for characteristic in service.characteristics:
                logging.info("[{}]    Characteristic [{}]".format(self.logger_name, characteristic.uuid))
                # only for reading a characteristic
                # for descriptor in characteristic.descriptors:
                    # print("[%s]\t\t\tDescriptor [%s] (%s)" % (self.mac_address, descriptor.uuid, descriptor.read_value()))

        device_notification_service = next(
            s for s in self.services
            if s.uuid in dev_services_list)
        logging.info("[{}] Found dev notify serv [{}]".format(self.logger_name, device_notification_service.uuid))

        device_notification_characteristic = next(
            c for c in device_notification_service.characteristics
            if c.uuid in dev_notify_list)
        logging.info("[{}] Found dev notify char [{}]".format(self.logger_name, device_notification_characteristic.uuid))

        logging.info("[{}] Subscribing to notify char [{}]".format(self.logger_name, device_notification_characteristic.uuid))
        device_notification_characteristic.enable_notifications()

    # only for reading a characteristic
    # def descriptor_read_value_failed(self, descriptor, error):
        # super().descriptor_read_value_failed(descriptor, error)
        # print('descriptor_value_failed')

    def characteristic_value_updated(self, characteristic, value):
        super().characteristic_value_updated(characteristic, value)
        logging.debug("[{}] Received update".format(self.logger_name))
        logging.debug("[{}]  characteristic id {} value: {}".format(self.logger_name, characteristic.uuid, value))
        # logging.debug("[{}]  retCmdData value: {}".format(self.logger_name, retCmdData))
        # retCmdData = self.smartPowerUtil.broadcastUpdate(value)
        # if self.smartPowerUtil.handleMessage(retCmdData):
        if self.smartPowerUtil.broadcastUpdate(value):
            datalogger.log(self.logger_name, 'current', self.entities.current)
            datalogger.log(self.logger_name, 'voltage', self.entities.voltage)
            datalogger.log(self.logger_name, 'temperature', self.entities.temperature_celsius)
            datalogger.log(self.logger_name, 'soc', self.entities.soc)
            datalogger.log(self.logger_name, 'capacity', self.entities.capacity)
            datalogger.log(self.logger_name, 'cycles', self.entities.charge_cycles)
            datalogger.log(self.logger_name, 'state', self.entities.state)
            datalogger.log(self.logger_name, 'health', self.entities.health)
            for cell in self.entities.cell_mvoltage:
                if self.entities.cell_mvoltage[cell] > 0:
                    datalogger.log(self.logger_name, 'cell_{}'.format(cell), self.entities.cell_mvoltage[cell])

            # logging.info("Cell voltage: {}".format(self.entities.cell_voltage))

    def characteristic_enable_notifications_succeeded(self, characteristic):
        super().characteristic_enable_notifications_succeeded(characteristic)
        logging.info("[{}] Notifications enabled for: [{}]".format(self.logger_name, characteristic.uuid))

    def characteristic_enable_notifications_failed(self, characteristic, error):
        super().characteristic_enable_notifications_failed(characteristic, error)
        logging.warning("[{}] Enabling notifications failed for: [{}] with error [{}]".format(self.logger_name, characteristic.uuid, str(error)))



def main():
    global config      
    global device_manager
    global dev_services_list
    global dev_services_list
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
        dev_services_list.append(item[1])
    for item in config.items("characteristics"):
        dev_notify_list.append(item[1])

    device_manager = SolarDeviceManager(adapter_name=config['monitor']['adapter'])
    logging.info("Adapter status - Powered: {}".format(device_manager.is_adapter_powered))
    if not device_manager.is_adapter_powered:
        logging.info("Powering on the adapter ...")
        device_manager.is_adapter_powered = True
        logging.info("Powered on")

    datalogger = DataLogger(config.get('datalogger', 'url'), config.get('datalogger', 'token'))

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
    print(devices)
    for dev in device_manager.devices():
        # if dev.mac_address != "d8:64:8c:66:f4:d4" and dev.mac_address != "7c:01:0a:41:ca:f9":
        # if dev.mac_address != "d8:64:8c:66:f4:d4":
        if dev.mac_address in devices:
            device = SolarDevice(mac_address=dev.mac_address, manager=device_manager, logger_name=devices[dev.mac_address])
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
