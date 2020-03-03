#!/usr/bin/env python3

from __future__ import absolute_import
import sys
from argparse import ArgumentParser
import blegatt
import time


from smartpower_battery_util_rpi import *

import logging 
# import duallog
# duallog.setup('solar-monitor', minLevel=logging.INFO)
logging.basicConfig(level=logging.DEBUG)


# test
HR_SVC_UUID =        '0000180d-0000-1000-8000-00805f9b34fb'
HR_MSRMT_UUID =      '00002a37-0000-1000-8000-00805f9b34fb'
# BODY_SNSR_LOC_UUID = '00002a38-0000-1000-8000-00805f9b34fb'
# HR_CTRL_PT_UUID =    '00002a39-0000-1000-8000-00805f9b34fb'
# BIT16_SVC_UUID =     '1523'

# Device service and their characteristic UUID's
MERITSUN_NOTIFY_UUID = 	 '0000ffe4-0000-1000-8000-00805f9b34fb'
MERITSUN_SERVICE_UUID =  '0000ffe0-0000-1000-8000-00805f9b34fb'
TBENERGY_NOTIFY_UUID = 	 '0000ffe4-0000-1000-8000-00805f9b34fb'
TBENERGY_SERVICE_UUID =  '0000ffe0-0000-1000-8000-00805f9b34fb'
SOLARLINK_NOTIFY_UUID =	 '0000fff1-0000-1000-8000-00805f9b34fb'
SOLARLINK_SERVICE_UUID = '0000fff0-0000-1000-8000-00805f9b34fb'
# as new device service, add to this list.
# only devices with these Service UUID's will be scanned & connected to.
# dev_services_list = [HR_SVC_UUID, MERITSUN_SERVICE_UUID, TBENERGY_SERVICE_UUID, SOLARLINK_SERVICE_UUID, BIT16_SVC_UUID]
dev_services_list = [MERITSUN_SERVICE_UUID, TBENERGY_SERVICE_UUID, SOLARLINK_SERVICE_UUID]
device_manager = None

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
    else:
        logging.warning('Unrecognized Service / Solar device : {}'.format(uuid))

# implementation of blegatt.DeviceManager, discovers any GATT device
class DiscoverAnyDeviceManager(blegatt.DeviceManager):
    def device_discovered(self, device):
        logging.info("[{}] Discovered, alias = {}".format(device.mac_address, device.alias()))
        # self.stop_discovery()   # in case to stop after discovered one device

    def make_device(self, mac_address):
        return ConnectAnyDevice(mac_address=mac_address, manager=self)


# implementation of blegatt.Device, connects to any GATT device
class ConnectAnyDevice(blegatt.Device):
    def __init__(self, mac_address, manager, auto_reconnect=False):
        super().__init__(mac_address=mac_address, manager=manager)
        self.auto_reconnect = auto_reconnect
        self.reader_activity = None

    def connect(self):
        logging.info("[{}] Connecting...".format(self.mac_address))
        super().connect()

    def connect_succeeded(self):
        super().connect_succeeded()
        logging.info("[{}] Connected".connecting(self.mac_address))

    def connect_failed(self, error):
        super().connect_failed(error)
        logging.info("[{}] Connection failed: {}".format(self.mac_address, str(error)))

    def disconnect_succeeded(self):
        super().disconnect_succeeded()
        logging.info("[{}] Disconnected".format(self.mac_address))
        if self.auto_reconnect:
            self.connect()

    def services_resolved(self):
        super().services_resolved()

        logging.info("[{}] Resolved services".format(self.mac_address))
        for service in self.services:
            logging.info("[{}]  Service [{}]".format(self.mac_address, service.uuid))
            for characteristic in service.characteristics:
                logging.info("[{}]    Characteristic [{}]".format(self.mac_address, characteristic.uuid))
                # only for reading a characteristic
                # for descriptor in characteristic.descriptors:
                    # print("[%s]\t\t\tDescriptor [%s] (%s)" % (self.mac_address, descriptor.uuid, descriptor.read_value()))

        device_notification_service = next(
            s for s in self.services
            if s.uuid == MERITSUN_SERVICE_UUID or s.uuid == TBENERGY_SERVICE_UUID or s.uuid == SOLARLINK_SERVICE_UUID or s.uuid == HR_SVC_UUID)
            # if s.uuid == HR_SVC_UUID)
        logging.info("[{}] Found dev notify serv [{}]".format(self.mac_address, device_notification_service))

        device_notification_characteristic = next(
            c for c in device_notification_service.characteristics
            if c.uuid == MERITSUN_NOTIFY_UUID or c.uuid == TBENERGY_NOTIFY_UUID or c.uuid == SOLARLINK_NOTIFY_UUID or c.uuid == HR_MSRMT_UUID)
            # if c.uuid == HR_MSRMT_UUID)
        logging.info("[{}] Found dev notify char [{}]".format(self.mac_address, device_notification_characteristic))

        # if c.uuid == BODY_SNSR_LOC_UUID)

        logging.info("[{}] Subscribing to notify char [{}]".format(self.mac_address, device_notification_characteristic))
        device_notification_characteristic.enable_notifications()

    # only for reading a characteristic
    # def descriptor_read_value_failed(self, descriptor, error):
        # super().descriptor_read_value_failed(descriptor, error)
        # print('descriptor_value_failed')

    def characteristic_value_updated(self, characteristic, value):
        super().characteristic_value_updated(characteristic, value)
        if self.reader_activity is None:
            self.reader_activity = ReaderActivity(blegatt.Device)
            logging.debug("ReaderActivity: {}".format(self.reader_activity))
        # print("characteristic value:", value.decode("utf-8"))
        logging.debug("[{}] Received update".format(self.mac_address))
        logging.debug("[{}]  characteristic id {} value: {}".format(self.mac_address, characteristic.uuid, value))
        # process the received "value"
        self.reader_activity.setValueOn(blegatt.Device, value)
        # ReaderActivity.setValueOn(ReaderActivity(blegatt.Device), blegatt.Device, value)
        # Disable notifications - enable_notifications(False)  !?

    def characteristic_enable_notifications_succeeded(self, characteristic):
        super().characteristic_enable_notifications_succeeded(characteristic)
        logging.info("[{}] Notifications enabled for: [{}]".format(self.mac_address, characteristic.uuid))

    def characteristic_enable_notifications_failed(self, characteristic, error):
        super().characteristic_enable_notifications_failed(characteristic, error)
        logging.warning("[{}] Enabling notifications failed for: [{}] with error [{}]".format(self.mac_address, characteristic.uuid, str(error)))


def main():
    arg_parser = ArgumentParser(description="GATT SDK Demo")
    arg_parser.add_argument(
        '--adapter',
        default='hci0',
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

    global device_manager
    device_manager = DiscoverAnyDeviceManager(adapter_name=args.adapter)

    logging.info("Device status - Powered: {}".format(device_manager.is_adapter_powered))
    if not device_manager.is_adapter_powered:
        logging.info("Powering on the device ...")
        device_manager.is_adapter_powered = True
        logging.info("Powered on")

    device_manager.update_devices()
    logging.info("Starting discovery...")
    global dev_services_list
    # scan all the advertisements from the services list
    device_manager.start_discovery(dev_services_list[0:])
    # delay / sleep for 10 ~ 15 sec to complete the scanning
    time.sleep(15)
    device_manager.stop_discovery()
    logging.info("Found {} Solar / battery services".format(len(device_manager.devices())))
    logging.info("Trying to connect...")
    # device = ConnectAnyDevice(mac_address=args.connect, manager=device_manager)
    # device.connect()
    global dev_found_list
    dev_found_list = device_manager.devices()
    for dev in device_manager.devices():
        if dev.mac_address != "d8:64:8c:66:f4:d4":
            device = ConnectAnyDevice(mac_address=dev.mac_address, manager=device_manager)
            device.connect()

    # elif args.auto:
        # device = ConnectAnyDevice(mac_address=args.auto, manager=device_manager, auto_reconnect=True)
        # device.connect()
    # elif args.disconnect:
    if args.disconnect:
        device = ConnectAnyDevice(mac_address=args.disconnect, manager=device_manager)
        device.disconnect()
        return

    logging.info("Terminate with Ctrl+C")
    try:
        device_manager.run()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
