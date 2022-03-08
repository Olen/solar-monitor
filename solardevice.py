#!/usr/bin/env python3

from __future__ import absolute_import
import sys
import threading

from argparse import ArgumentParser
import configparser
import time
import os
import sys
import gatt
import time
from datetime import datetime

# import duallog
import logging

# duallog.setup('SmartPower', minLevel=logging.INFO)

from datalogger import DataLogger



# implementation of blegatt.DeviceManager, discovers any GATT device
class SolarDeviceManager(gatt.DeviceManager):
    def device_discovered(self, device):
        logging.info("[{}] Discovered, alias = {}".format(device.mac_address, device.alias()))
        # self.stop_discovery()   # in case to stop after discovered one device

    def make_device(self, mac_address):
        return SolarDevice(mac_address=mac_address, manager=self)


# implementation of blegatt.Device, connects to selected GATT device
class SolarDevice(gatt.Device):
    def __init__(self, mac_address, manager, logger_name = 'unknown', reconnect = False, type=None, datalogger=None, config=None):
        super().__init__(mac_address=mac_address, manager=manager)
        self.reader_activity = None
        self.logger_name = logger_name
        self.service_notify = None
        self.service_write = None
        self.char_notify = None
        self.char_write = None
        self.device_id = None
        self.send_ack = None
        self.need_polling = None
        self.util = None
        self.type = None
        self.module = None
        self.device_write_characteristic_polling = None
        self.device_write_characteristic_commands = None
        self.datalogger = datalogger
        self.run_device_poller = False
        self.poller_thread = None
        self.run_command_poller = False
        self.command_thread = None
        self.command_trigger = None
        if config:
            self.auto_reconnect = config.getboolean('monitor', 'reconnect', fallback=False)
            self.type = config.get(logger_name, 'type', fallback=None)
        self.writing = False

        if not self.type:
            return

        try:
            mod = __import__("plugins." + self.type)
            self.module = getattr(mod, self.type)
            logging.info("Successfully imported {}.".format(self.type))
        except ImportError:
            logging.error("Error importing {}".format(self.type))
            raise ImportError()

        self.service_notify = getattr(self.module.Config, "NOTIFY_SERVICE_UUID", None)
        self.service_write = getattr(self.module.Config, "WRITE_SERVICE_UUID", None)
        self.char_notify = getattr(self.module.Config, "NOTIFY_CHAR_UUID", None)
        self.char_write_polling = getattr(self.module.Config, "WRITE_CHAR_UUID_POLLING", None)
        self.char_write_commands = getattr(self.module.Config, "WRITE_CHAR_UUID_COMMANDS", None)
        self.device_id = getattr(self.module.Config, "DEVICE_ID", None)
        self.need_polling = getattr(self.module.Config, "NEED_POLLING", None)
        self.send_ack = getattr(self.module.Config, "SEND_ACK", None)

        if "battery" in self.logger_name:
            if "renogy" in self.logger_name:
                self.entities = RenogyBatteryDevice(parent=self)
            else:
                self.entities = BatteryDevice(parent=self)
        elif "regulator" in self.logger_name:
            self.entities = RegulatorDevice(parent=self)
        elif "inverter" in self.logger_name:
            self.entities = InverterDevice(parent=self)
        elif "rectifier" in self.logger_name:
            self.entities = RectifierDevice(parent=self)
        else:
            self.entities = PowerDevice(parent=self)



    def alias(self):
        alias = super().alias()
        if alias:
            return alias.strip()
        return None

    def connect(self):
        logging.info("[{}] Connecting to {}".format(self.logger_name, self.mac_address))
        super().connect()

    def connect_succeeded(self):
        super().connect_succeeded()
        logging.info("[{}] Connected to {}".format(self.logger_name, self.alias()))

    def connect_failed(self, error):
        super().connect_failed(error)
        logging.info("[{}] Connection failed: {}".format(self.logger_name, str(error)))
        if self.poller_thread:
            self.run_device_poller = False
            logging.info("[{}] Stopping poller-thread".format(self.logger_name))
        if self.command_thread:
            logging.info("[{}] Stopping command-thread".format(self.logger_name))
            self.run_command_poller = False
            self.command_trigger.set()
        if self.auto_reconnect:
            logging.info("[{}] Reconnecting in 10 seconds".format(self.logger_name))
            time.sleep(10)
            self.connect()


    def disconnect_succeeded(self):
        super().disconnect_succeeded()
        logging.info("[{}] Disconnected".format(self.logger_name))
        if self.poller_thread:
            self.run_device_poller = False
            logging.info("[{}] Stopping poller-thread".format(self.logger_name))
        if self.command_thread:
            logging.info("[{}] Stopping command-thread".format(self.logger_name))
            self.run_command_poller = False
            self.command_trigger.set()
        if self.auto_reconnect:
            logging.info("[{}] Reconnecting in 10 seconds".format(self.logger_name))
            time.sleep(10)
            self.connect()

    def services_resolved(self):
        super().services_resolved()
        logging.info("[{}] Connected to {}".format(self.logger_name, self.alias()))
        logging.info("[{}] Resolved services".format(self.logger_name))
        self.util = self.module.Util(self)

        device_notification_service = None
        device_write_service = None
        for service in self.services:
            logging.info("[{}]  Service [{}]".format(self.logger_name, service.uuid))
            if self.service_notify and service.uuid == self.service_notify:
                logging.info("[{}]  - Found dev notify service [{}]".format(self.logger_name, service.uuid))
                device_notification_service = service
            if self.service_write and service.uuid == self.service_write:
                logging.info("[{}]  - Found dev write service [{}]".format(self.logger_name, service.uuid))
                device_write_service = service
            for characteristic in service.characteristics:
                logging.info("[{}]    Characteristic [{}]".format(self.logger_name, characteristic.uuid))


        if device_notification_service:
            for c in device_notification_service.characteristics:
                if self.char_notify and c.uuid in self.char_notify:
                    logging.info("[{}] Found dev notify char [{}]".format(self.logger_name, c.uuid))
                    logging.info("[{}] Subscribing to notify char [{}]".format(self.logger_name, c.uuid))
                    c.enable_notifications()
        if device_write_service:
            for c in device_write_service.characteristics:
                if self.char_write_polling and c.uuid == self.char_write_polling:
                    logging.info("[{}] Found dev write polling char [{}]".format(self.logger_name, c.uuid))
                    self.device_write_characteristic_polling = c
                if self.char_write_commands and c.uuid == self.char_write_commands:
                    logging.info("[{}] Found dev write polling char [{}]".format(self.logger_name, c.uuid))
                    self.device_write_characteristic_commands = c


        if self.need_polling:
            self.poller_thread = threading.Thread(target=self.device_poller)
            self.poller_thread.daemon = True
            self.poller_thread.name = "Device-poller-thread {}".format(self.logger_name)
            self.poller_thread.start()

        # We only need and MQTT-poller thread if we have a write characteristic to send data to
        if self.char_write_commands:
            self.command_trigger = threading.Event()
            self.datalogger.mqtt.trigger[self.logger_name] = self.command_trigger
            self.command_thread = threading.Thread(target=self.mqtt_poller, args=(self.command_trigger,))
            self.command_thread.daemon = True
            self.command_thread.name = "MQTT-poller-thread {}".format(self.logger_name)
            self.command_thread.start()




    def characteristic_value_updated(self, characteristic, value):
        super().characteristic_value_updated(characteristic, value)

        # logging.debug("[{}] [{}] Received update".format(self.logger_name, threading.currentThread().name))
        # logging.debug("[{}]  characteristic id {} value: {}".format(self.logger_name, characteristic.uuid, value))
        # logging.debug("[{}]  retCmdData value: {}".format(self.logger_name, retCmdData))

        if self.send_ack:
            data = self.util.ackData(value)
            self.characteristic_write_value(data, self.device_write_characteristic_polling)

        if self.util.notificationUpdate(value, characteristic.uuid):
            # We received some new data. Lets push it to the datalogger
            items = ['current', 'input_current', 'charge_current',
                     'voltage', 'input_voltage', 'charge_voltage',
                     'power',   'input_power',   'charge_power',
                     'soc', 'capacity', 'charge_cycles', 'state', 'health', 'power_switch'
                    ]
            for item in items:
                try:
                    self.datalogger.log(self.logger_name, item, getattr(self.entities, item))
                except Exception as e:
                    logging.debug("[{}] Could not find {}".format(self.logger_name, item))
                    pass

            # We want celsius, not kelvin
            try:
                self.datalogger.log(self.logger_name, 'temperature', self.entities.temperature_celsius)
                self.datalogger.log(self.logger_name, 'battery_temperature', self.entities.battery_temperature_celsius)

            except:
                pass

            # And all cells if a battery
            try:
                for cell in self.entities.cell_mvoltage:
                    if self.entities.cell_mvoltage[cell]['val'] > 0:
                        self.datalogger.log(self.logger_name, 'cell_{}'.format(cell), self.entities.cell_mvoltage[cell]['val'])
            except:
                pass

    def characteristic_enable_notifications_succeeded(self, characteristic):
        super().characteristic_enable_notifications_succeeded(characteristic)
        logging.info("[{}] Notifications enabled for: [{}]".format(self.logger_name, characteristic.uuid))

    def characteristic_enable_notifications_failed(self, characteristic, error):
        super().characteristic_enable_notifications_failed(characteristic, error)
        logging.warning("[{}] Enabling notifications failed for: [{}] with error [{}]".format(self.logger_name, characteristic.uuid, str(error)))


    def characteristic_write_value(self, value, write_characteristic):
        logging.debug("[{}] Writing data to {} - {} ({})".format(self.logger_name, write_characteristic.uuid, value, bytearray(value).hex()))
        self.writing = value
        write_characteristic.write_value(value)

    def characteristic_write_value_succeeded(self, characteristic):
        super().characteristic_write_value_succeeded(characteristic)
        logging.debug("[{}] Write to characteristic done for: [{}]".format(self.logger_name, characteristic.uuid))
        self.writing = False

    def characteristic_write_value_failed(self, characteristic, error):
        super().characteristic_write_value_failed(characteristic, error)
        logging.warning("[{}] Write to characteristic failed for: [{}] with error [{}]".format(self.logger_name, characteristic.uuid, str(error)))
        if error == "In Progress" and self.writing is not False:
            time.sleep(0.1)
            self.characteristic_write_value(self.writing, characteristic)
        else:
            self.writing = False

    # Pollers
    # Implement polling in separate threads to be able to
    # sleep without blocking notifications

    def device_poller(self):
        # Loop every second - the device plugin is responsible for not overloading the device with requests
        logging.info("[{}] Starting new thread {}".format(self.logger_name, threading.current_thread().name))
        self.run_device_poller = True
        while self.run_device_poller:
            logging.debug("[{}] Looping thread {}".format(self.logger_name, threading.current_thread().name))
            data = self.util.pollRequest()
            if data:
                self.characteristic_write_value(data, self.device_write_characteristic_polling)
            time.sleep(1)
        logging.info("[{}] Ending thread {}".format(self.logger_name, threading.current_thread().name))


    def mqtt_poller(self, trigger):
        # Loop to fetch MQTT-commands
        logging.info("[{}] Starting new thread {}".format(self.logger_name, threading.current_thread().name))
        self.run_command_poller = True
        while self.run_command_poller:
            mqtt_sets = []
            datas = []
            logging.info("[{}] {} Waiting for event...".format(self.logger_name, threading.current_thread().name))
            trigger.wait()
            logging.info("[{}] {} Event happened...".format(self.logger_name, threading.current_thread().name))
            trigger.clear()
            try:
                mqtt_sets = self.datalogger.mqtt.sets[self.logger_name]
                self.datalogger.mqtt.sets[self.logger_name] = []
            except Exception as e:
                logging.error("[{}] {} Something bad happened: {}".format(self.logger_name, threading.current_thread().name, e))
                pass
            for msg in mqtt_sets:
                var = msg[0]
                message = msg[1]
                logging.info("[{}] MQTT-msg: {} -> {}".format(self.logger_name, var, message))
                datas = self.util.cmdRequest(var, message)
                if len(datas) > 0:
                    for data in datas:
                        logging.debug("[{}] Sending data to device: {}".format(self.logger_name, data))
                        self.characteristic_write_value(data, self.device_write_characteristic_commands)
                        time.sleep(0.2)
                else:
                    logging.debug("[{}] Unknown MQTT-command {} -> {}".format(self.logger_name, var, message))
        logging.info("[{}] Ending thread {}".format(self.logger_name, threading.current_thread().name))


class PowerDevice():
    '''
    General class for different PowerDevices
    Stores the values read from the devices with the best available resolution (milli-whatever)
    Temperature is stored as /10 kelvin
    Soc is stored as /10 %
    Most setters will validate the input to guard against false Zero-values
    '''
    def __init__(self, parent=None):
        logging.debug("New PowerDevice")
        self._parent = parent
        self._cell_mvoltage = {}
        self._power_switch = 0
        self._dsoc = {
            'val': 0,
            'min': 1,
            'max': 1000,
            'maxdiff': 200
        }
        self._dkelvin = {
            'val': 2731,
            'min': 1731,
            'max': 3731,
            'maxdiff': 20
        }
        self._bkelvin = {
            'val': 2731,
            'min': 1731,
            'max': 3731,
            'maxdiff': 20
        }
        self._mcapacity = {
            'val': 0,
            'min': 0,
            'max': 250000,
            'maxdiff': 10
        }
        self._mcurrent = {
            'val': 0,
            'min': 0,
            'max': 30000,
            'maxdiff': 10000
        }
        self._mpower = {
            'val': 0,
            'min': 0,
            'max': 200000,
            'maxdiff': 100000
        }
        self._mvoltage = {
            'val': 0,
            'min': 0,
            'max': 48000,
            'maxdiff': 12000
        }
        self._input_mcurrent = {
            'val': 0,
            'min': 0,
            'max': 30000,
            'maxdiff': 10000
        }
        self._input_mpower = {
            'val': 0,
            'min': 0,
            'max': 200000,
            'maxdiff': 100000
        }
        self._input_mvoltage = {
            'val': 0,
            'min': 0,
            'max': 48000,
            'maxdiff': 12000
        }
        self._charge_mcurrent = {
            'val': 0,
            'min': 0,
            'max': 30000,
            'maxdiff': 10000
        }
        self._charge_mpower = {
            'val': 0,
            'min': 0,
            'max': 200000,
            'maxdiff': 100000
        }
        self._charge_mvoltage = {
            'val': 0,
            'min': 0,
            'max': 48000,
            'maxdiff': 12000
        }
        self._mvoltage = {
            'val': 0,
            'min': 0,
            'max': 15000,
            'maxdiff': 15000
        }
        self._msg = None
        self._status = None

    @property
    def device_id(self):
        return self._device_id
    @device_id.setter
    def device_id(self, value):
        self._device_id = int(value)


    @property
    def need_polling(self):
        return self._need_polling

    @need_polling.setter
    def need_polling(self, value):
        if value == True:
            logging.info("Enabling BLE-polling")
        self._need_polling = value

    @property
    def send_ack(self):
        return self._send_ack
    @send_ack.setter
    def send_ack(self, value):
        self._send_ack = value


    @property
    def poll_register(self):
        return self._poll_register

    @poll_register.setter
    def poll_register(self, value):
        self._poll_register = value

    @property
    def parent(self):
        return self._parent

    @property
    def name(self):
        return self.parent.logger_name

    def alias(self):
        return self.parent.alias()


    @property
    def datalogger(self):
        return self.parent.datalogger

    @property
    def dsoc(self):
        return self._dsoc['val']
    @dsoc.setter
    def dsoc(self, value):
        self.validate('_dsoc', value)

    @property
    def soc(self):
        return (self.dsoc / 10)
    @soc.setter
    def soc(self, value):
        self.dsoc = value * 10

    @property
    def temperature(self):
        return self._dkelvin['val']
    @temperature.setter
    def temperature(self, value):
        self.validate('_dkelvin', value)

    @property
    def battery_temperature(self):
        return self._bkelvin['val']
    @battery_temperature.setter
    def battery_temperature(self, value):
        self.validate('_bkelvin', value)

    @property
    def temperature_celsius(self):
        return round((self.temperature - 2731) * 0.1, 1)
    @temperature_celsius.setter
    def temperature_celsius(self, value):
        self.temperature = (value * 10) + 2731

    @property
    def temperature_fahrenheit(self):
        return round(((self.temperature * 0.18) - 459.67), 1)
    @temperature_fahrenheit.setter
    def temperature_fahrenheit(self, value):
        self.temperature = (value + 459.67) * (5/9) * 10

    @property
    def battery_temperature_celsius(self):
        return round((self.battery_temperature - 2731) * 0.1, 1)
    @battery_temperature_celsius.setter
    def battery_temperature_celsius(self, value):
        self.battery_temperature = (value * 10) + 2731

    @property
    def battery_temperature_fahrenheit(self):
        return round(((self.temperature * 0.18) - 459.67), 1)
    @battery_temperature_fahrenheit.setter
    def battery_temperature_fahrenheit(self, value):
        self.temperature = (value + 459.67) * (5/9) * 10


    @property
    def mcapacity(self):
        return self._mcapacity['val']
    @mcapacity.setter
    def mcapacity(self, value):
        self.validate('_mcapacity', value)

    @property
    def capacity(self):
        return round(self.mcapacity / 1000, 1)
    @capacity.setter
    def capacity(self, value):
        self.mcapacity = value * 1000

    # Voltage
    @property
    def mvoltage(self):
        return self._mvoltage['val']
    @mvoltage.setter
    def mvoltage(self, value):
        self.validate('_mvoltage', value)

    @property
    def voltage(self):
        return round(self.mvoltage / 1000, 1)
    @voltage.setter
    def voltage(self, value):
        self.mvoltage = value * 1000

    @property
    def input_mvoltage(self):
        return self._input_mvoltage['val']
    @input_mvoltage.setter
    def input_mvoltage(self, value):
        self.validate('_input_mvoltage', value)

    @property
    def input_voltage(self):
        return round(self.input_mvoltage / 1000, 1)
    @input_voltage.setter
    def input_voltage(self, value):
        self.input_mvoltage = value * 1000


    @property
    def charge_mvoltage(self):
        return self._charge_mvoltage['val']
    @charge_mvoltage.setter
    def charge_mvoltage(self, value):
        self.validate('_charge_mvoltage', value)

    @property
    def charge_voltage(self):
        return round(self.charge_mvoltage / 1000, 1)
    @charge_voltage.setter
    def charge_voltage(self, value):
        self.charge_mvoltage = value * 1000

    # current
    @property
    def mcurrent(self):
        return self._mcurrent['val']
    @mcurrent.setter
    def mcurrent(self, value):
        self.validate('_mcurrent', value)

    @property
    def current(self):
        return round(self.mcurrent / 1000, 1)
    @current.setter
    def current(self, value):
        self.mcurrent = value * 1000


    @property
    def input_mcurrent(self):
        return self._input_mcurrent['val']
    @input_mcurrent.setter
    def input_mcurrent(self, value):
        self.validate('_input_mcurrent', value)

    @property
    def input_current(self):
        return round(self.input_mcurrent / 1000, 1)
    @input_current.setter
    def input_current(self, value):
        self.input_mcurrent = value * 1000

    @property
    def charge_mcurrent(self):
        return self._charge_mcurrent['val']
    @charge_mcurrent.setter
    def charge_mcurrent(self, value):
        self.validate('_charge_mcurrent', value)

    @property
    def charge_current(self):
        return round(self.charge_mcurrent / 1000, 1)
    @charge_current.setter
    def charge_current(self, value):
        self.charge_mcurrent = value * 1000


    # power
    @property
    def mpower(self):
        return self._mpower['val']
    @mpower.setter
    def mpower(self, value):
        self.validate('_mpower', value)

    @property
    def power(self):
        return round(self.mpower / 1000, 1)
    @power.setter
    def power(self, value):
        self.mpower = value * 1000


    @property
    def input_mpower(self):
        return self._input_mpower['val']
    @input_mpower.setter
    def input_mpower(self, value):
        self.validate('_input_mpower', value)

    @property
    def input_power(self):
        return round(self.input_mpower / 1000, 1)
    @input_power.setter
    def input_power(self, value):
        self.input_mpower = value * 1000

    @property
    def charge_mpower(self):
        return self._charge_mpower['val']
    @charge_mpower.setter
    def charge_mpower(self, value):
        self.validate('_charge_mpower', value)

    @property
    def charge_power(self):
        return round(self.charge_mpower / 1000, 1)
    @charge_power.setter
    def charge_power(self, value):
        self.charge_mpower = value * 1000


    @property
    def power_switch(self):
        return self._power_switch

    @power_switch.setter
    def power_switch(self, value):
        if str(value).lower() == "on":
            value = 1
        if str(value).lower() == "off":
            value = 0
        if value != self._power_switch:
            self._power_switch = value
            try:
                self.datalogger.log(self.logger_name, 'power_switch', self.power_switch)
            except:
                pass



    @property
    def msg(self):
        return self._msg
    @msg.setter
    def msg(self, message):
        self._msg = message

    @property
    def status(self):
        return self._status
    @status.setter
    def status(self, value):
        self._status = value

    def dumpAll(self):
        out = "RAW "
        for var in self.__dict__:
            if var != "_msg":
                out = "{} {} == {},".format(out, var, self.__dict__[var])
        logging.debug(out)


    def validate(self, var, val):
        definition = getattr(self, var)
        val = float(val)
        if val == definition['val']:
            logging.debug("[{}] Value of {} out of bands: Changed from {} to {} (no diff)".format(self.name, var, definition['val'], val))
            return False
        if val > definition['max']:
            logging.warning("[{}] Value of {} out of bands: Changed from {} to {} (> max {})".format(self.name, var, definition['val'], val, definition['max']))
            return False
        if val < definition['min']:
            logging.warning("[{}] Value of {} out of bands: Changed from {} to {} (< min {})".format(self.name, var, definition['val'], val, definition['min']))
            return False
        if (definition['val'] != 0 and definition['val'] != 2731) and abs(val - definition['val']) > definition['maxdiff']:
            logging.warning("[{}] Value of {} out of bands: Changed from {} to {} (> maxdiff {})".format(self.name, var, definition['val'], val, definition['maxdiff']))
            return False
        logging.debug("[{}] Value of {} changed from {} to {}".format(self.name, var, definition['val'], val))
        self.__dict__[var]['val'] = val


class InverterDevice(PowerDevice):
    '''
    Special class for Regulator-devices.  (DC-AC)
    Extending PowerDevice class with more properties specifically for the regulators
    '''
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        logging.debug("New InverterDevice")
        self._input_mvoltage = {
            'val': 0,
            'min': 0,
            'max': 50000,
            'maxdiff': 50000
        }
        self._mvoltage = {
            'val': 0,
            'min': 0,
            'max': 250000,
            'maxdiff': 250000
        }


class RectifierDevice(PowerDevice):
    '''
    Special class for Rectifier-devices  (AC-DC).
    Extending PowerDevice class with more properties specifically for the regulators
    '''
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        logging.debug("New RectifierDevice")
        self._input_mvoltage = {
            'val': 0,
            'min': 0,
            'max': 250000,
            'maxdiff': 250000
        }
        self._mvoltage = {
            'val': 0,
            'min': 0,
            'max': 50000,
            'maxdiff': 50000
        }


class RegulatorDevice(PowerDevice):
    '''
    Special class for Regulator-devices.
    Extending PowerDevice class with more properties specifically for the regulators
    '''
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        logging.debug("New RegulatorDevice")







    def parse_notification(self, value):
        if self.deviceUtil.notificationUpdate(self.poll_register, value):
            # logging.debug("parse_notification {} success".format(self.poll_register))
            if self.poll_register == 'ParamSettingData' and len(self.deviceUtil.param_data) < 33:
                pass
            else:
                self.poll_register = None
            return True
        else:
            logging.warning("Error during parse_notification {}".format(self.poll_register))
            self.poll_register = None
            return False



class BatteryDevice(PowerDevice):
    '''
    Special class for Battery-devices.
    Extending PowerDevice class with more properties specifically for the batteries
    '''

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        logging.debug("New BatteryDevice")
        self._health = None
        self._state = None
        self._mcurrent = {
            'val': 0,
            'min': -500000,
            'max': 500000,
            'maxdiff': 100000
        }
        self._mvoltage = {
            'val': 0,
            'min': 10000,
            'max': 15000,
            'maxdiff': 12000
        }
        self._charge_cycles = {
            'val': 0,
            'min': 0,
            'max': 10000,
            'maxdiff': 1
        }
        i = 0
        while i < 16:
            i = i + 1
            self._cell_mvoltage[i] = {
                'val': 0,
                'min': 2000,
                'max': 4000,
                'maxdiff': 500
            }

    @property
    def charge_cycles(self):
        return self._charge_cycles['val']

    @charge_cycles.setter
    def charge_cycles(self, value):
        self.validate('_charge_cycles', value)
        if value > 0:
            was = self.health
            if value > 2000:
                self._health = 'good'
            else:
                self._health = 'perfect'
            self.health_changed(was)

    @property
    def mcurrent(self):
        return super().mcurrent
    @property
    def current(self):
        return super().current

    @mcurrent.setter
    def mcurrent(self, value):
        super(BatteryDevice, self.__class__).mcurrent.fset(self, value)
        if value == 0 and (self.mcurrent > 500 or self.mcurrent < -500):
            return
        was = self.state
        if value > 20:
            self._state = 'charging'
        elif value < -20:
            self._state = 'discharging'
        else:
            self._state = 'standby'
        self.state_changed(was)

    @current.setter
    def current(self, value):
        super(BatteryDevice, self.__class__).current.fset(self, value)
        if value == 0 and (self.mcurrent > 500 or self.mcurrent < -500):
            return
        was = self.state
        if value > 0.02:
            self._state = 'charging'
        elif value < -0.02:
            self._state = 'discharging'
        else:
            self._state = 'standby'
        self.state_changed(was)

    @property
    def cell_mvoltage(self):
        return self._cell_mvoltage
    @cell_mvoltage.setter
    def cell_mvoltage(self, value):
        cell = value[0]
        new_value = value[1]
        current_value = self._cell_mvoltage[cell]['val']
        if new_value > 0 and abs(new_value - current_value) > 10:
            self._cell_mvoltage[cell]['val'] = new_value

    @property
    def afestatus(self):
        return self._afestatus
    @afestatus.setter
    def afestatus(self, value):
        self._afestatus = value

    @property
    def health(self):
        return self._health
    @property
    def state(self):
        return self._state

    def state_changed(self, was):
        if was != self.state:
            logging.info("[{}] Value of {} changed from {} to {}".format(self.name, 'state', was, self.state))

    def health_changed(self, was):
        if was != self.health:
            logging.info("[{}] Value of {} changed from {} to {}".format(self.name, 'health', was, self.health))


class RenogyBatteryDevice():
#    '''
#    Special class for new Renogy Battery-devices.
#    '''
#
    def __init__(self, parent=None):
        logging.debug("New RenogyBatteryDevice")
        self._parent = parent
        self._cell_mvoltage = {}
        self._state = None
        self._dsoc = {
            'val': 0,
            'min': 1,
            'max': 1000,
            'maxdiff': 1000
        }
        self._dkelvin = {
            'val': 2731,
            'min': 1731,
            'max': 3731,
            'maxdiff': 20
        }
        self._mcapacity = {
            'val': 0,
            'min': 0,
            'max': 250000,
            'maxdiff': 200000
        }
        self._mvoltage = {
            'val': 0,
            'min': 10000,
            'max': 15000,
            'maxdiff': 12000
        }
        self._mcurrent = {
            'val': 0,
            'min': -500000,
            'max': 500000,
            'maxdiff': 400000
        }

        i = 0
        while i < 16:
            i = i + 1
            self._cell_mvoltage[i] = {
                'val': 0,
                'min': 2000,
                'max': 4000,
                'maxdiff': 500
            }
        self._msg = None
        self._status = None

    @property
    def device_id(self):
        return self._device_id
    @device_id.setter
    def device_id(self, value):
        self._device_id = int(value)

    @property
    def need_polling(self):
        return self._need_polling

    @need_polling.setter
    def need_polling(self, value):
        if value == True:
            logging.info("Enabling BLE-polling")
        self._need_polling = value

    @property
    def send_ack(self):
        return self._send_ack
    @send_ack.setter
    def send_ack(self, value):
        self._send_ack = value

    @property
    def poll_register(self):
        return self._poll_register

    @poll_register.setter
    def poll_register(self, value):
        self._poll_register = value

    @property
    def parent(self):
        return self._parent

    @property
    def name(self):
        return self.parent.logger_name

    def alias(self):
        return self.parent.alias()

    @property
    def datalogger(self):
        return self.parent.datalogger

    # SOC
    @property
    def dsoc(self):
        return self._dsoc['val']
    @dsoc.setter
    def dsoc(self, value):
        self.validate('_dsoc', value)

    @property
    def soc(self):
        return (self.dsoc / 10)
    @soc.setter
    def soc(self, value):
        self.dsoc = value * 10

    # Temperature
    @property
    def temperature(self):
        return self._dkelvin['val']
    @temperature.setter
    def temperature(self, value):
        self.validate('_dkelvin', value)

    # current
    @property
    def mcurrent(self):
        return self._mcurrent['val']

    @property
    def current(self):
        return round(self.mcurrent / 1000, 1)

    @mcurrent.setter
    def mcurrent(self, value):
        self.validate('_mcurrent', value)

    @current.setter
    def current(self, value):
        if value > 400:
            value = value - 655.35
        self.mcurrent = value * 1000
        if value == 0 and (self.mcurrent > 500 or self.mcurrent < -500):
            return
        was = self.state
        if value > 0.02:
            self._state = 'charging'
        elif value < -0.02:
            self._state = 'discharging'
        else:
            self._state = 'standby'
        self.state_changed(was)

    # Voltage
    @property
    def mvoltage(self):
        return self._mvoltage['val']
    @mvoltage.setter
    def mvoltage(self, value):
        self.validate('_mvoltage', value)

    @property
    def voltage(self):
        return round(self.mvoltage / 1000, 1)
    @voltage.setter
    def voltage(self, value):
        self.mvoltage = value * 1000

    @property
    def cell_mvoltage(self):
        return self._cell_mvoltage
    @cell_mvoltage.setter
    def cell_mvoltage(self, value):
        cell = value[0]
        new_value = value[1]
        current_value = self._cell_mvoltage[cell]['val']
        if new_value > 0 and abs(new_value - current_value) > 0:
            self._cell_mvoltage[cell]['val'] = new_value

    # capacity
    @property
    def mcapacity(self):
        return self._mcapacity['val']
    @mcapacity.setter
    def mcapacity(self, value):
        self.validate('_mcapacity', value)

    @property
    def capacity(self):
        return round(self.mcapacity / 1000, 1)
    @capacity.setter
    def capacity(self, value):
        self.mcapacity = value * 1000

    # state and status
    @property
    def state(self):
        return self._state
    def state_changed(self, was):
        if was != self.state:
            logging.info("[{}] Value of {} changed from {} to {}".format(self.name, 'state', was, self.state))

    @property
    def status(self):
        return self._status
    @status.setter
    def status(self, value):
        self._status = value

    def dumpAll(self):
        out = "RAW "
        for var in self.__dict__:
            if var != "_msg":
                out = "{} {} == {},".format(out, var, self.__dict__[var])
        logging.debug(out)


    def validate(self, var, val):
        definition = getattr(self, var)
        val = float(val)
        if val == definition['val']:
            logging.debug("[{}] Value of {} out of bands: Changed from {} to {} (no diff)".format(self.name, var, definition['val'], val))
            return False
        if val > definition['max']:
            logging.warning("[{}] Value of {} out of bands: Changed from {} to {} (> max {})".format(self.name, var, definition['val'], val, definition['max']))
            return False
        if val < definition['min']:
            logging.warning("[{}] Value of {} out of bands: Changed from {} to {} (< min {})".format(self.name, var, definition['val'], val, definition['min']))
            return False
        if (definition['val'] != 0 and definition['val'] != 2731) and abs(val - definition['val']) > definition['maxdiff']:
            logging.warning("[{}] Value of {} out of bands: Changed from {} to {} (> maxdiff {})".format(self.name, var, definition['val'], val, definition['maxdiff']))
            return False
        logging.debug("[{}] Value of {} changed from {} to {}".format(self.name, var, definition['val'], val))
        self.__dict__[var]['val'] = val

