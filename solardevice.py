#!/usr/bin/env python3

from __future__ import absolute_import
import sys
import threading

from argparse import ArgumentParser
import configparser
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
from solarlinkutil import SolarLinkUtil



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
        self.services_write_list = []
        self.notify_list = []
        self.write_list = []
        self.device_write_characteristic = None
        self.datalogger = None
        self.writing = False
        self.write_buffer = []

        if "battery" in self.logger_name:
            self.entities = BatteryDevice(name=self.logger_name, alias=self.alias)
        elif "regulator" in self.logger_name:
            self.entities = RegulatorDevice(name=self.logger_name, alias=self.alias)
        else:
            self.entities = PowerDevice(name=self.logger_name, alias=self.alias)


    def add_services(self, services_list, notify_list, services_write_list, write_list):
        self.services_list = services_list
        self.notify_list = notify_list
        self.write_list = write_list
        self.services_write_list = services_write_list
    def add_datalogger(self, datalogger):
        self.datalogger = datalogger
        self.entities.add_datalogger(datalogger)

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
        device_notification_service = None
        device_write_service = None

        for service in self.services:
            logging.info("[{}]  Service [{}]".format(self.logger_name, service.uuid))
            if service.uuid in self.services_list:
                logging.info("[{}]  - Found dev notify service [{}]".format(self.logger_name, service.uuid))
                device_notification_service = service
            if service.uuid in self.services_write_list:
                logging.info("[{}]  - Found dev write service [{}]".format(self.logger_name, service.uuid))
                device_write_service = service
            for characteristic in service.characteristics:
                logging.info("[{}]    Characteristic [{}]".format(self.logger_name, characteristic.uuid))



        if device_notification_service:
            for c in device_notification_service.characteristics:
                if c.uuid in self.notify_list:
                    logging.info("[{}] Found dev notify char [{}]".format(self.logger_name, c.uuid))
                    logging.info("[{}] Subscribing to notify char [{}]".format(self.logger_name, c.uuid))
                    c.enable_notifications()
        if device_write_service:
            for c in device_write_service.characteristics:
                if c.uuid in self.write_list:
                    logging.info("[{}] Found dev write char [{}]".format(self.logger_name, c.uuid))
                    logging.info("[{}] Subscribing to notify char [{}]".format(self.logger_name, c.uuid))
                    self.device_write_characteristic = c


        if self.entities.need_polling:
            t = threading.Thread(target=self.thread_poll)
            t.daemon = True 
            t.name = "Poller-thread"
            logging.debug("Starting new thread")
            t.start()

    def thread_poll(self):
        # Implement polling in a separate thread to be able to
        # sleep without blocking notifications

        c = 0
        while True:
            logging.debug("Looping thread {} {}".format(threading.currentThread().name, c))
            c = c + 1
            if c == 1:
                self.async_poll_data('BatteryParamInfo')
            if c == 3:
                self.async_poll_data('SolarPanelInfo')
            # if c == 5:
            #     self.async_poll_data('SolarPanelAndBatteryState')
            # if c == 7:
            #     self.async_poll_data('ParamSettingData')

            cmds = self.entities.mqtt_poller()
            if len(cmds) > 0: 
                for cmd in cmds:
                    if cmd == 'cmdPowerSwitchOff':
                        self.entities.power_switch_state = 0
                        self.async_poll_data('RegulatorPowerOff')
                    if cmd == 'cmdPowerSwitchOn':
                        self.entities.power_switch_state = 1
                        self.async_poll_data('RegulatorPowerOn')
                    logging.info("CMD: {}".format(cmd))
                    time.sleep(1)
                # Refresh data after cmd
                self.async_poll_data('SolarPanelInfo')
                time.sleep(1)
                self.async_poll_data('BatteryParamInfo')

            time.sleep(1)
            if c == 10:
                c = 0


    def async_poll_data(self, cmd):
        data = None
        function = self.entities.deviceUtil.function_READ
        if cmd == 'SolarPanelAndBatteryState':
            regAddr = self.entities.deviceUtil.SolarPanelAndBatteryState.REG_ADDR
            readWrd = self.entities.deviceUtil.SolarPanelAndBatteryState.READ_WORD
        elif cmd == 'BatteryParamInfo':
            regAddr = self.entities.deviceUtil.BatteryParamInfo.REG_ADDR
            readWrd = self.entities.deviceUtil.BatteryParamInfo.READ_WORD
        elif cmd == 'SolarPanelInfo':
            regAddr = self.entities.deviceUtil.SolarPanelInfo.REG_ADDR
            readWrd = self.entities.deviceUtil.SolarPanelInfo.READ_WORD
        elif cmd == 'ParamSettingData':
            regAddr = self.entities.deviceUtil.ParamSettingData.REG_ADDR
            readWrd = self.entities.deviceUtil.ParamSettingData.READ_WORD
        elif cmd == 'RegulatorPowerOn':
            regAddr = self.entities.deviceUtil.RegulatorPower.REG_ADDR
            readWrd = self.entities.deviceUtil.RegulatorPower.on
            function = self.entities.deviceUtil.function_WRITE
        elif cmd == 'RegulatorPowerOff':
            regAddr = self.entities.deviceUtil.RegulatorPower.REG_ADDR
            readWrd = self.entities.deviceUtil.RegulatorPower.off
            function = self.entities.deviceUtil.function_WRITE

        data = self.entities.deviceUtil.buildRequest(function, regAddr, readWrd)

        self.entities.poll_register = cmd
        waitcount = 0
        while self.writing:
            logging.debug("Waiting for writing: {} {}".format(self.writing, waitcount))
            time.sleep(1)
            waitcount = waitcount + 1
            if waitcount > 5:
                return False
        logging.debug("Writing poll")
        self.characteristic_write_value(data)
        return True



    def characteristic_value_updated(self, characteristic, value):
        super().characteristic_value_updated(characteristic, value)

        # logging.debug("[{}] [{}] Received update".format(self.logger_name, threading.currentThread().name))
        # logging.debug("[{}]  characteristic id {} value: {}".format(self.logger_name, characteristic.uuid, value))
        # logging.debug("[{}]  retCmdData value: {}".format(self.logger_name, retCmdData))

        if self.entities.send_ack:
            time.sleep(.5)
            msg = "main recv da ta[{0:02x}] [".format(value[0])
            self.characteristic_write_value(bytearray(msg, "ascii"))

        if self.entities.parse_notification(value):
            # We received some new data. Lets push it to the datalogger
            items = ['current', 'input_current', 'charge_current',
                     'voltage', 'input_voltage', 'charge_voltage',
                     'power',   'input_power',   'charge_power',
                     'soc', 'capacity', 'charge_cycles', 'state', 'health', 'power_switch_state'
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
            except:
                pass

            try:
                for cell in self.entities.cell_mvoltage:
                    if self.entities.cell_mvoltage[cell] > 0:
                        self.datalogger.log(self.logger_name, 'cell_{}'.format(cell), self.entities.cell_mvoltage[cell])
            except:
                pass
            '''
            try:
                self.datalogger.log(self.logger_name, 'current', self.entities.current)
            except Exception as e:
                pass
            try:
                self.datalogger.log(self.logger_name, 'input_current', self.entities.input_current)
            except:
                pass
            try:
                self.datalogger.log(self.logger_name, 'charge_current', self.entities.charge_current)
            except:
                pass
            try:
                self.datalogger.log(self.logger_name, 'voltage', self.entities.voltage)
            except:
                pass
            try:
                self.datalogger.log(self.logger_name, 'input_voltage', self.entities.input_voltage)
            except:
                pass
            try:
                self.datalogger.log(self.logger_name, 'charge_voltage', self.entities.charge_voltage)
            except:
                pass
            try:
                self.datalogger.log(self.logger_name, 'power', self.entities.power)
            except:
                pass
            try:
                self.datalogger.log(self.logger_name, 'input_power', self.entities.input_power)
            except:
                pass
            try:
                self.datalogger.log(self.logger_name, 'charge_power', self.entities.charge_power)
            except:
                pass
            try:
                self.datalogger.log(self.logger_name, 'soc', self.entities.soc)
            except:
                pass
            try:
                self.datalogger.log(self.logger_name, 'capacity', self.entities.capacity)
            except:
                pass
            try:
                self.datalogger.log(self.logger_name, 'charge_cycles', self.entities.charge_cycles)
            except:
                pass
            try:
                self.datalogger.log(self.logger_name, 'state', self.entities.state)
            except:
                pass
            try:
                self.datalogger.log(self.logger_name, 'power_switch_state', self.entities.power_switch_state)
            except:
                pass
            try:
                self.datalogger.log(self.logger_name, 'health', self.entities.health)
            except:
                pass

            # logging.info("Cell voltage: {}".format(self.entities.cell_voltage))
            '''

    def characteristic_enable_notifications_succeeded(self, characteristic):
        super().characteristic_enable_notifications_succeeded(characteristic)
        logging.info("[{}] Notifications enabled for: [{}]".format(self.logger_name, characteristic.uuid))

    def characteristic_enable_notifications_failed(self, characteristic, error):
        super().characteristic_enable_notifications_failed(characteristic, error)
        logging.warning("[{}] Enabling notifications failed for: [{}] with error [{}]".format(self.logger_name, characteristic.uuid, str(error)))


    def run_write_buffer(self):
        if self.writing == False and len(self.write_buffer) > 0:
            data = self.write_buffer.pop(0)
            self.characteristic_write_value(data)

    def characteristic_write_value(self, value):
        if self.device_write_characteristic:
            logging.debug("[{}] Writing data to {} - {} ({})".format(self.logger_name, self.device_write_characteristic.uuid, value, bytearray(value).hex()))
            self.writing = value
            self.device_write_characteristic.write_value(value)
        else:
            logging.warning("[{}] No write characteristic created".format(self.logger_name))

    def characteristic_write_value_succeeded(self, characteristic):
        super().characteristic_write_value_succeeded(characteristic)
        logging.debug("[{}] Write to characteristic done for: [{}]".format(self.logger_name, characteristic.uuid))
        self.writing = False

    def characteristic_write_value_failed(self, characteristic, error):
        super().characteristic_write_value_failed(characteristic, error)
        logging.warning("[{}] Write to characteristic failed for: [{}] with error [{}]".format(self.logger_name, characteristic.uuid, str(error)))
        self.writing = False




class PowerDevice():
    '''
    General class for different PowerDevices
    Stores the values read from the devices with the best available resolution (milli-whatever)
    Temperature is stored as /10 kelvin
    Soc is stored as /10 %
    Most setters will validate the input to guard against false Zero-values
    '''
    def __init__(self, alias=None, name=None):
        self._alias = alias
        self._name = name
        self._device_id = 0
        self.datalogger = None
        self._mcurrent = {
            'val': 0,
            'min': 0,
            'max': 30000,
            'maxdiff': 2000
        }
        self._mpower = {
            'val': 0,
            'min': 0,
            'max': 200000,
            'maxdiff': 50000
        }
        self._dsoc = {
            'val': 0,
            'min': 1,
            'max': 1000,
            'maxdiff': 20
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
            'maxdiff': 10
        }
        self._mvoltage = {
            'val': 0,
            'min': 0,
            'max': 48000,
            'maxdiff': 12000
        }
        self._msg = None
        self._status = None
        self._poll_register = None
        self._need_poll = False
        self._send_ack = False

    @property
    def need_polling(self):
        return self._need_poll

    @property
    def poll_register(self):
        return self._poll_register

    @poll_register.setter
    def poll_register(self, value):
        self._poll_register = value

    @property
    def name(self):
        return self._name

    @property
    def alias(self):
        return self._alias

    def add_datalogger(self, datalogger):
        self.datalogger = datalogger

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
    def temperature_celsius(self):
        return round((self.temperature - 2731) * 0.1, 1)
    @temperature_celsius.setter
    def temperature_celsius(self, value):
        self.dkelvin = (value * 10) + 2731

    @property
    def temperature_fahrenheit(self):
        return round(((self.temperature * 0.18) - 459.67), 1)
    @temperature_fahrenheit.setter
    def temperature_fahrenheit(self, value):
        self.dkelvin = (value + 459.67) * (5/9) * 10




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
        
    def mqtt_poller(self):
        return []



class RegulatorDevice(PowerDevice):
    '''
    Special class for Regulator-devices.  
    Extending PowerDevice class with more properties specifically for the regulators
    '''
    def __init__(self, alias=None, name=None):
        super().__init__(alias=alias, name=name)
        self._device_id = 255
        self._send_ack = True
        self._need_poll = True
        self._input_mcurrent = {
            'val': 0,
            'min': 0,
            'max': 30000,
            'maxdiff': 2000
        }
        self._input_mpower = {
            'val': 0,
            'min': 0,
            'max': 200000,
            'maxdiff': 50000
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
            'maxdiff': 2000
        }
        self._charge_mpower = {
            'val': 0,
            'min': 0,
            'max': 200000,
            'maxdiff': 50000
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
        self._power_switch_state = 0
        self.deviceUtil = SolarLinkUtil(self.alias, self)  

    @property
    def device_id(self):
        return self._device_id

    @property
    def send_ack(self):
        return self._send_ack


    # Voltage

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
    def power_switch_state(self):
        return self._power_switch_state

    @power_switch_state.setter
    def power_switch_state(self, value):
        if value != self._power_switch_state:
            self._power_switch_state = value
            try:
                self.datalogger.log(self.logger_name, 'power_switch_state', self.power_switch_state)
            except:
                pass


    def mqtt_poller(self):
        logging.debug("Running MQTT-poller")
        mqtt_sets = []
        ret = []
        try:
            mqtt_sets = self.datalogger.mqtt.sets
            self.datalogger.mqtt.sets = []
        except Exception as e:
            pass
        for msg in mqtt_sets:
            logging.debug("MQTT-msg: {} -> {}".format(msg[0], msg[1]))
            topic = msg[0]
            message = msg[1]
            if topic == 'leveld/regulator/power_switch_state/set':
                logging.info("Switching Power Switch to {}".format(message))
                if int(message) == 0:
                    ret.append('cmdPowerSwitchOff')
                    self.power_switch_state = 0
                if int(message) == 1:
                    ret.append('cmdPowerSwitchOn')
                    self.power_switch_state = 1
        return ret
            
            


    def parse_notification(self, value):
        if self.deviceUtil.pollerUpdate(self.poll_register, value):
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

    def __init__(self, alias=None, name=None):
        super().__init__(alias=alias, name=name)
        self._health = None
        self._state = None
        self._charge_cycles = {
            'val': 0,
            'min': 0,
            'max': 10000,
            'maxdiff': 1
        }
        self._cell_mvoltage = {}
        i = 0
        while i < 16:
            i = i + 1
            self._cell_mvoltage[i] = {
                'val': 0,
                'min': 2000,
                'max': 4000,
                'maxdiff': 500
            }
        self.deviceUtil = SmartPowerUtil(self.alias, self)  

    @property
    def device_id(self):
        return self._device_id

    @property
    def send_ack(self):
        return self._send_ack

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
        # super().mcurrent = value
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
        # super().current(value)
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

    def parse_notification(self, value):
        if self.deviceUtil.broadcastUpdate(value):
            return True
        return False

    # def dumpall(self):
    #     logging.info("RAW voltage == {}, current == {}, soc == {}, capacity == {}, cycles == {}, status == {}, temperature == {}, health = {}".format(self.mvoltage, self.mcurrent, self.dsoc, self.mcapacity, self.charge_cycles, self.state, self.temperature, self.health))



