import blegatt
from argparse import ArgumentParser

HR_SVC_UUID =        '0000180d-0000-1000-8000-00805f9b34fb'
HR_MSRMT_UUID =      '00002a37-0000-1000-8000-00805f9b34fb'
BODY_SNSR_LOC_UUID = '00002a38-0000-1000-8000-00805f9b34fb'
HR_CTRL_PT_UUID =    '00002a39-0000-1000-8000-00805f9b34fb'
MERITSUN_NOTIFY_UUID = 	 '0000ffe4-0000-1000-8000-00805f9b34fb'
MERITSUN_SERVICE_UUID =  '0000ffe0-0000-1000-8000-00805f9b34fb'
TBENERGY_NOTIFY_UUID = 	 '0000ffe4-0000-1000-8000-00805f9b34fb'
TBENERGY_SERVICE_UUID =  '0000ffe0-0000-1000-8000-00805f9b34fb'
SOLARLINK_NOTIFY_UUID =	 '0000fff1-0000-1000-8000-00805f9b34fb'
SOLARLINK_SERVICE_UUID = '0000fff0-0000-1000-8000-00805f9b34fb'


class ConnectAnyDevice(blegatt.Device):
    def connect_succeeded(self):
        super().connect_succeeded()
        print("[%s] Connected" % (self.mac_address))

    def connect_failed(self, error):
        super().connect_failed(error)
        print("[%s] Connection failed: %s" % (self.mac_address, str(error)))

    def disconnect_succeeded(self):
        super().disconnect_succeeded()
        print("[%s] Disconnected" % (self.mac_address))

    def services_resolved(self):
        super().services_resolved()

        print("[%s] Resolved services" % (self.mac_address))
        for service in self.services:
            print("[%s]  Service [%s]" % (self.mac_address, service.uuid))
            for characteristic in service.characteristics:
                print("[%s]    Characteristic [%s]" % (self.mac_address, characteristic.uuid))

class DiscoverAnyDeviceManager(blegatt.DeviceManager):
    def device_discovered(self, device):
        print("[%s] Discovered, alias = %s" % (device.mac_address, device.alias()))

def scan_device():
    manager = DiscoverAnyDeviceManager(adapter_name='hci0')
    manager.start_discovery([HR_SVC_UUID])
    manager.run()

def connect_device():
    arg_parser = ArgumentParser(description="GATT Connect Demo")
    arg_parser.add_argument('mac_address', help="MAC address of device to connect")
    args = arg_parser.parse_args()
    print("Connecting...")
    manager = blegatt.DeviceManager(adapter_name='hci0')
    device = ConnectAnyDevice(manager=manager, mac_address=args.mac_address)
    device.connect()
    manager.run()

