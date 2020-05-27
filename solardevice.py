#!/usr/bin/env python3

from __future__ import absolute_import
import sys
from argparse import ArgumentParser
import configparser
import blegatt
import time
import os
import sys
import blegatt
import time
from datetime import datetime

# import duallog
import logging

# duallog.setup('SmartPower', minLevel=logging.INFO)

from datalogger import DataLogger
from smartpowerutil import SmartPowerUtil
from slink_maincommon import MainCommon


import logging 
import duallog

# implementation of blegatt.DeviceManager, discovers any GATT device
class SolarDeviceManager(blegatt.DeviceManager):
    def device_discovered(self, device):
        logging.info("[{}] Discovered, alias = {}".format(device.mac_address, device.alias()))
        # self.stop_discovery()   # in case to stop after discovered one device

    def make_device(self, mac_address):
        return SolarDevice(mac_address=mac_address, manager=self)


# implementation of blegatt.Device, connects to selected GATT device
class SolarDevice(blegatt.Device):
    def __init__(self, mac_address, manager, logger_name = 'unknown', reconnect = False):
        super().__init__(mac_address=mac_address, manager=manager)
        self.auto_reconnect = reconnect
        self.reader_activity = None
        self.logger_name = logger_name
        self.services_list = []
        self.notify_list = []
        self.datalogger = None

        if "battery" in self.logger_name:
            self.entities = BatteryDevice()
        elif "regulator" in self.logger_name:
            self.entities = RegulatorDevice()
        else:
            self.entities = PowerDevice()

        self.smartPowerUtil = SmartPowerUtil(self.alias, self.entities)  

    def add_services(self, services_list, notify_list):
        self.services_list = services_list
        self.notify_list = notify_list
    def add_datalogger(self, datalogger):
        self.datalogger = datalogger

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
            if s.uuid in self.services_list)
        logging.info("[{}] Found dev notify serv [{}]".format(self.logger_name, device_notification_service.uuid))

        device_notification_characteristic = next(
            c for c in device_notification_service.characteristics
            if c.uuid in self.notify_list)
        logging.info("[{}] Found dev notify char [{}]".format(self.logger_name, device_notification_characteristic.uuid))

        logging.info("[{}] Subscribing to notify char [{}]".format(self.logger_name, device_notification_characteristic.uuid))
        device_notification_characteristic.enable_notifications()

    # only for reading a characteristic
    # def descriptor_read_value_failed(self, descriptor, error):
        # super().descriptor_read_value_failed(descriptor, error)
        # print('descriptor_value_failed')

    def characteristic_value_updated(self, characteristic, value):
        super().characteristic_value_updated(characteristic, value)
        # logging.debug("[{}] Received update".format(self.logger_name))
        # logging.debug("[{}]  characteristic id {} value: {}".format(self.logger_name, characteristic.uuid, value))
        # logging.debug("[{}]  retCmdData value: {}".format(self.logger_name, retCmdData))
        # retCmdData = self.smartPowerUtil.broadcastUpdate(value)
        # if self.smartPowerUtil.handleMessage(retCmdData):
        if self.smartPowerUtil.broadcastUpdate(value):
            self.datalogger.log(self.logger_name, 'current', self.entities.current)
            self.datalogger.log(self.logger_name, 'voltage', self.entities.voltage)
            self.datalogger.log(self.logger_name, 'temperature', self.entities.temperature_celsius)
            self.datalogger.log(self.logger_name, 'soc', self.entities.soc)
            self.datalogger.log(self.logger_name, 'capacity', self.entities.capacity)
            self.datalogger.log(self.logger_name, 'cycles', self.entities.charge_cycles)
            self.datalogger.log(self.logger_name, 'state', self.entities.state)
            self.datalogger.log(self.logger_name, 'health', self.entities.health)
            for cell in self.entities.cell_mvoltage:
                if self.entities.cell_mvoltage[cell] > 0:
                    self.datalogger.log(self.logger_name, 'cell_{}'.format(cell), self.entities.cell_mvoltage[cell])

            # logging.info("Cell voltage: {}".format(self.entities.cell_voltage))

    def characteristic_enable_notifications_succeeded(self, characteristic):
        super().characteristic_enable_notifications_succeeded(characteristic)
        logging.info("[{}] Notifications enabled for: [{}]".format(self.logger_name, characteristic.uuid))

    def characteristic_enable_notifications_failed(self, characteristic, error):
        super().characteristic_enable_notifications_failed(characteristic, error)
        logging.warning("[{}] Enabling notifications failed for: [{}] with error [{}]".format(self.logger_name, characteristic.uuid, str(error)))

    def write_value(self, val):
        device_service = next(
            s for s in self.services
            if s.uuid == MainCommon.SOLARLINK_WRITEDATA_SERVICE_UUID)
        rx_characteristic = next(
            c for c in device_service.characteristics
            if c.uuid == MainCommon.mUartSendCharacteristic)
        rx_characteristic.write_value(val.encode('ascii'))

    def characteristic_write_value_succeeded(self, characteristic):
        super().characteristic_write_value_succeeded(characteristic)
        logging.info("[{}] Write to characteristic done for: [{}]".format(self.logger_name, characteristic.uuid))

    def characteristic_write_value_failed(self, characteristic, error):
        super().characteristic_write_value_failed(characteristic, error)
        logging.warning("[{}] Write to characteristic failed for: [{}] with error [{}]".format(self.logger_name, characteristic.uuid, str(error)))



class PowerDevice():
    '''
    General class for different PowerDevices
    Stores the values read from the devices with the best available resolution (milli-whatever)
    Temperature is stored as /10 kelvin
    Soc is stored as /10 %
    Most setters will validate the input to guard against false Zero-values
    '''
    _mcapacity = 0
    _mcurrent = 0
    _mvoltage = 0
    _dkelvin = 0
    _dsoc = 0
    _msg = None
    _status = None


    @property
    def mcurrent(self):
        return self._mcurrent
    @mcurrent.setter
    def mcurrent(self, value):
        if value == 0 and (self._mcurrent > 500 or self._mcurrent < -500):
            # Ignore probable invalid values
            return 
        self.value_changed('mcurrent', self.mcurrent, value)
        self._mcurrent = value

    @property
    def current(self):
        return round(self._mcurrent / 1000, 1)
    @current.setter
    def current(self, value):
        if value == 0 and (self._mcurrent > 500 or self._mcurrent < -500):
            # Ignore probable invalid values
            return
        self.value_changed('current', self.current, value)
        self._mcurrent = value * 1000


    @property 
    def dsoc(self):
        return self._dsoc
    @dsoc.setter
    def dsoc(self, value):
        if value > 0:
            self.value_changed('dsoc', self.dsoc, value)
            self._dsoc = value
    @property 
    def soc(self):
        return (self._dsoc / 10)
    @soc.setter
    def soc(self, value):
        if value > 0:
            self.value_changed('soc', self.soc, value)
            self._dsoc = value * 10

    @property
    def temperature(self):
        return self._dkelvin
    @temperature.setter
    def temperature(self, value):
        if value > 0 and (value > self.temperature + 2 or value < self.temperature - 2):
            # Ignore probable invalid values
            self.value_changed('temperature', self.temperature, value)
            self._dkelvin = value
    @property
    def temperature_celsius(self):
        return (self._dkelvin - 2731) / 10 

    @temperature_celsius.setter
    def temperature_celsius(self, value):
        if value == 0 and (self._dkelvin > (2731 + 50) or self._dkelvin < (2731 - 50)):
            # Ignore probable invalid values (sudden drops of +/- 5 degrees ending on exactly 0)
            return
        self.value_changed('temperature_celsius', self.temperature_celsius, value)
        self._dkelvin = (value * 10) + 2731

    @property
    def mcapacity(self):
        return self._mcapacity
    @mcapacity.setter
    def mcapacity(self, value):
        if value > 10000:
            self.value_changed('mcapacity', self.mcapacity, value)
            self._mcapacity = value

    @property
    def capacity(self):
        return round(self._mcapacity / 1000, 1)

    @capacity.setter
    def capacity(self, value):
        if value > 10:
            self.value_changed('capacity', self.capacity, value)
            self._mcapacity = value * 1000

    @property
    def mvoltage(self):
        return self._mvoltage

    @mvoltage.setter
    def mvoltage(self, value):
        if value > 0 and (value > self.mvoltage + 10 or value < self.mvoltage - 10):
            self.value_changed('mvoltage', self.mvoltage, value)
            self._mvoltage = value

    @property
    def voltage(self):
        return round(self._mvoltage / 1000, 1)

    @voltage.setter
    def voltage(self, value):
        if value > 0:
            self.value_changed('voltage', self.voltage, value)
            self._mvoltage = value * 1000

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

    def dumpall(self):
        out = "RAW "
        for var in self.__dict__:
            if var != "_msg":
                out = "{} {} == {},".format(out, var, self.__dict__[var])
        logging.debug(out)

    def value_changed(self, var, was, val):
        if float(was) != float(val):
            logging.debug("Value of {} changed from {} to {}".format(var, was, val))
            self.dumpall()




class RegulatorDevice(PowerDevice):
    '''
    Special class for Regulator-devices.  
    Extending PowerDevice class with more properties specifically for the regulators
    '''
    _power_switch_status = 0
    @property
    def power_switch_status(self):
        return self._power_switch_status

    @power_switch_status.setter
    def power_switch_status(self, value):
        self._power_switch_status = value





class BatteryDevice(PowerDevice):
    '''
    Special class for Battery-devices.  
    Extending PowerDevice class with more properties specifically for the batteries
    '''
    _charge_cycles = 0
    _health = None
    _state = None
    _cell_mvoltage = {}

    def __init__(self):
        super().__init__()
        i = 0
        while i < 16:
            i = i + 1
            self._cell_mvoltage[i] = 0

    @property
    def charge_cycles(self):
        return self._charge_cycles

    @charge_cycles.setter
    def charge_cycles(self, value):
        if value > 0:
            self.value_changed('charge_cycles', self.charge_cycles, value)
            self._charge_cycles = value
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
        # super().mcurrent = value
        if value == 0 and (self._mcurrent > 500 or self._mcurrent < -500):
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
        # super().current(value)
        if value == 0 and (self._mcurrent > 500 or self._mcurrent < -500):
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
        current_value = self._cell_mvoltage[cell]
        if new_value > 0 and (new_value > current_value + 10 or new_value < current_value - 10):
            self._cell_mvoltage[cell] = new_value

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
            logging.info("Value of {} changed from {} to {}".format('state', was, self.state))

    def health_changed(self, was):
        if was != self.health:
            logging.info("Value of {} changed from {} to {}".format('health', was, self.health))


    # def dumpall(self):
    #     logging.info("RAW voltage == {}, current == {}, soc == {}, capacity == {}, cycles == {}, status == {}, temperature == {}, health = {}".format(self.mvoltage, self.mcurrent, self.dsoc, self.mcapacity, self.charge_cycles, self.state, self.temperature, self.health))



