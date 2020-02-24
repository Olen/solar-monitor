#!/usr/bin/env python3

from argparse import ArgumentParser
import blegatt
import time

# HR_SVC_UUID =        '0000180d-0000-1000-8000-00805f9b34fb'
# HR_MSRMT_UUID =      '00002a37-0000-1000-8000-00805f9b34fb'
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
        print('Unrecognized Service / Solar device : ' + uuid)

# implementation of blegatt.DeviceManager, discovers any GATT device
class DiscoverAnyDeviceManager(blegatt.DeviceManager):
    def device_discovered(self, device):
        print("[%s] Discovered, alias = %s" % (device.mac_address, device.alias()))
        # self.stop_discovery()   # in case to stop after discovered one device

    def make_device(self, mac_address):
        return ConnectAnyDevice(mac_address=mac_address, manager=self)


# implementation of blegatt.Device, connects to any GATT device
class ConnectAnyDevice(blegatt.Device):
    def __init__(self, mac_address, manager, auto_reconnect=False):
        super().__init__(mac_address=mac_address, manager=manager)
        self.auto_reconnect = auto_reconnect

    def connect(self):
        print("Connecting...")
        super().connect()

    def connect_succeeded(self):
        super().connect_succeeded()
        print("[%s] Connected" % (self.mac_address))

    def connect_failed(self, error):
        super().connect_failed(error)
        print("[%s] Connection failed: %s" % (self.mac_address, str(error)))

    def disconnect_succeeded(self):
        super().disconnect_succeeded()
        print("[%s] Disconnected" % (self.mac_address))
        if self.auto_reconnect:
            self.connect()

    def services_resolved(self):
        super().services_resolved()

        print("[%s] Resolved services" % (self.mac_address))
        for service in self.services:
            print("[%s]  Service [%s]" % (self.mac_address, service.uuid))
            for characteristic in service.characteristics:
                print("[%s]    Characteristic [%s]" % (self.mac_address, characteristic.uuid))
                # only for reading a characteristic
                # for descriptor in characteristic.descriptors:
                    # print("[%s]\t\t\tDescriptor [%s] (%s)" % (self.mac_address, descriptor.uuid, descriptor.read_value()))

        device_notification_service = next(
            s for s in self.services
            if s.uuid == HR_SVC_UUID)
        print("Found dev notify serv [%s]" % device_notification_service)

        device_notification_characteristic = next(
            c for c in device_notification_service.characteristics
            if c.uuid == HR_MSRMT_UUID)
        print("Found dev notify char [%s] , [%s]" %(device_notification_characteristic, c))
          
        # if c.uuid == BODY_SNSR_LOC_UUID)

        print("Subscribing to notify char [%s]" % device_notification_characteristic)
        device_notification_characteristic.enable_notifications()

    # only for reading a characteristic
    # def descriptor_read_value_failed(self, descriptor, error):
        # super().descriptor_read_value_failed(descriptor, error)
        # print('descriptor_value_failed')

    def characteristic_value_updated(self, characteristic, value):
        super().characteristic_value_updated(characteristic, value)
        print("characteristic value:", value.decode("utf-8"))
        # process the received "value" 
        # Disable notifications - enable_notifications(False)  !?

    def characteristic_enable_notifications_succeeded(self, characteristic):
        super().characteristic_enable_notifications_succeeded(characteristic)
        print("Notifications enabled for: [%s]" %(characteristic.uuid))

    def characteristic_enable_notifications_failed(self, characteristic, error):
        super().characteristic_enable_notifications_failed(characteristic, error)
        print("Enabling notifications failed for: [%s] with error [%s]" %(characteristic.uuid, str(error)))


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

    print("Device status - Powered: ", device_manager.is_adapter_powered)
    if not device_manager.is_adapter_powered:
        print("Powering on the device ...")
        device_manager.is_adapter_powered = True
        print("Powered on")

    device_manager.update_devices()
    print("Starting discovery...")
    global dev_services_list
    # scan all the advertisements from the services list
    device_manager.start_discovery(dev_services_list[0:])
    # delay / sleep for 10 ~ 15 sec to complete the scanning
    time.sleep(15)
    device_manager.stop_discovery()
    print("Found Solar / battery services: ",len(device_manager.devices()))
    print("Trying to connect...")
    # device = ConnectAnyDevice(mac_address=args.connect, manager=device_manager)
    # device.connect()
    global dev_found_list
    dev_found_list = device_manager.devices()
    for dev in device_manager.devices():
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

    print("Terminate with Ctrl+C")
    try:
        device_manager.run()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
