#!/usr/bin/env python3

from __future__ import absolute_import
import sys
import asyncio
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
from slink_maincommon import MainCommon
from slink_modbusdata import ModbusData
from slink_realtimemonitor import SLinkRealTimeMonitor
from slinkdata import SLinkData




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
        self.services_write_list = []
        self.notify_list = []
        self.write_list = []
        self.device_write_characteristic = None
        self.datalogger = None
        self.MainCommon = MainCommon(self)
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



                # only for reading a characteristic
                # for descriptor in characteristic.descriptors:
                    # print("[%s]\t\t\tDescriptor [%s] (%s)" % (self.mac_address, descriptor.uuid, descriptor.read_value()))

        # for service in self.services:
        # device_notification_service = next(
        #     s for s in self.services
        #     if s.uuid in self.services_list)

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

        # device_notification_characteristic = next(
        #     c for c in device_notification_service.characteristics
        #     if c.uuid in self.notify_list)
        # logging.info("[{}] Found dev notify char [{}]".format(self.logger_name, device_notification_characteristic.uuid))
        # logging.info("[{}] Subscribing to notify char [{}]".format(self.logger_name, device_notification_characteristic.uuid))
        # device_notification_characteristic.enable_notifications()

        # self.device_write_characteristic = next(
        #     c for c in device_notification_service.characteristics
        #     if c.uuid in self.write_list)
        # logging.info("[{}] Found dev write char [{}]".format(self.logger_name, self.device_write_characteristic.uuid))


        if self.entities.need_polling:
            t = threading.Thread(target=self.thread_poll)
            t.daemon = True 
            t.start()

    def thread_poll(self):
        # c = 0
        while True:
            # c = c + 1
            self.async_poll_data('SolarPanelAndBatteryState')
            time.sleep(2)
            self.async_poll_data('BatteryParamInfo')
            time.sleep(2)
            self.async_poll_data('SolarPanelInfo')
            time.sleep(2)
            self.async_poll_data('ParamSettingData')
            time.sleep(5)
            # if c < 10:
            #    self.regulator_power("on")
            #else:
            #    self.regulator_power("off")
            # time.sleep(5)


    def async_poll_data(self, register):

        if register == 'SolarPanelAndBatteryState':
            ReadingRegId = SLinkData.SolarPanelAndBatteryState.REG_ADDR
            ReadingCount = SLinkData.SolarPanelAndBatteryState.READ_WORD
        elif register == 'BatteryParamInfo':
            ReadingRegId = SLinkData.BatteryParamInfo.REG_ADDR
            ReadingCount = SLinkData.BatteryParamInfo.READ_WORD
        elif register == 'SolarPanelInfo':
            ReadingRegId = SLinkData.SolarPanelInfo.REG_ADDR
            ReadingCount = SLinkData.SolarPanelInfo.READ_WORD
        elif register == 'ParamSettingData':
            ReadingRegId = SLinkData.ParamSettingData.REG_ADDR
            ReadingCount = 33
        elif register == 'RegulatorPowerOn':
            ReadingRegId = 266
            ReadingCount = 1
        elif register == 'RegulatorPowerOff':
            ReadingRegId = 266
            ReadingCount = 0
        data = ModbusData.BuildReadRegsCmd(self.entities.device_id, ReadingRegId, ReadingCount)
        self.entities.poll_register = register
        waitcount = 0
        while self.writing:
            logging.debug("Waiting for writing: {} {}".format(self.writing, waitcount))
            time.sleep(1)
            waitcount = waitcount + 1
            if waitcount > 5:
                return False
        logging.debug("Writing")
        self.characteristic_write_value(data)
        return True


    def regulator_power(self, state):
        if state == "on":
            self.async_poll_data('RegulatorPowerOn')
        else: 
            self.async_poll_data('RegulatorPowerOff')

    def regulator_init(self):
        logging.info("[{}] Sending magic packet to {}".format(self.logger_name, self.alias))
        # self.MainCommon.SendUartData(ModbusData.BuildReadRegsCmd(255, 255, 0))
        '''
        ReadingRegId = 12
        ReadingCount = 2
        data = ModbusData.BuildReadRegsCmd(self.entities.device_id, ReadingRegId, ReadingCount)
        self.write_buffer.append(data)
        '''
        # loop = asyncio.get_event_loop()
        # loop.create_task(self.async_poll_data('BatteryParamInfo'))
        # asyncio.ensure_future(self.async_poll_data('BatteryParamInfo'))  # fire and forget
        t = threading.Thread(target=self.async_poll_data, args=['BatteryParamInfo'])
        t.daemon = True 
        t.start()


        '''
        # self.characteristic_write_value(data)
        # while self.writing == True:
        #    logging.debug("Sleep a bit...")
        #     await asyncio.sleep(1)
        # time.sleep(1)
        self.entities.poll_register = 'BatteryParamInfo'        
        ReadingRegId = SLinkData.BatteryParamInfo.REG_ADDR
        ReadingCount = SLinkData.BatteryParamInfo.READ_WORD
        data = ModbusData.BuildReadRegsCmd(self.entities.device_id, ReadingRegId, ReadingCount)

        ReadingRegId = SLinkData.SolarPanelInfo.REG_ADDR
        ReadingCount = 4
        data = ModbusData.BuildReadRegsCmd(self.entities.device_id, ReadingRegId, ReadingCount)
        self.write_buffer.append(data)
        ReadingRegId = SLinkData.SolarPanelAndBatteryState.REG_ADDR
        ReadingCount = 3
        data = ModbusData.BuildReadRegsCmd(self.entities.device_id, ReadingRegId, ReadingCount)
        self.write_buffer.append(data)

        ReadingRegId = SLinkData.ParamSettingData.REG_ADDR
        ReadingCount = 33
        data = ModbusData.BuildReadRegsCmd(self.entities.device_id, ReadingRegId, ReadingCount)
        self.write_buffer.append(data)
        self.run_write_buffer()
        '''
        # self.run_write_buffer()
        return True

        # Repeat

        ReadingRegId = 256
        ReadingCount = 7
        data = ModbusData.BuildReadRegsCmd(self.entities.device_id, ReadingRegId, ReadingCount)
        self.write_buffer.append(data)

        ReadingRegId = SLinkData.SolarPanelInfo.REG_ADDR
        ReadingCount = 4
        data = ModbusData.BuildReadRegsCmd(self.entities.device_id, ReadingRegId, ReadingCount)
        self.write_buffer.append(data)

        ReadingRegId = SLinkData.SolarPanelAndBatteryState.REG_ADDR
        ReadingCount = 3
        data = ModbusData.BuildReadRegsCmd(self.entities.device_id, ReadingRegId, ReadingCount)
        self.write_buffer.append(data)

        ReadingRegId = SLinkData.ParamSettingData.REG_ADDR
        ReadingCount = 33
        data = ModbusData.BuildReadRegsCmd(self.entities.device_id, ReadingRegId, ReadingCount)
        self.write_buffer.append(data)


        self.run_write_buffer()

        # await self.characteristic_write_value(str(data))
        # time.sleep(1)

        # sys.exit()



    # only for reading a characteristic
    # def descriptor_read_value_failed(self, descriptor, error):
        # super().descriptor_read_value_failed(descriptor, error)
        # print('descriptor_value_failed')

    def characteristic_value_updated(self, characteristic, value):
        super().characteristic_value_updated(characteristic, value)
        # if "regulator" in self.logger_name:
        # logging.debug("[{}] Received update".format(self.logger_name))
        # logging.debug("[{}]  characteristic id {} value: {}".format(self.logger_name, characteristic.uuid, value))
        # logging.debug("[{}]  retCmdData value: {}".format(self.logger_name, retCmdData))
        # retCmdData = self.smartPowerUtil.broadcastUpdate(value)
        # if self.smartPowerUtil.handleMessage(retCmdData):
        if self.entities.send_ack:
            time.sleep(.5)
            msg = "main recv da ta[{0:02x}] [".format(value[0])
            self.characteristic_write_value(bytearray(msg, "ascii"))
            # self.characteristic_write_value(bytearray(msg, "ascii"))
            # self.run_write_buffer()
        if self.entities.parse_notification(value):
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
                self.datalogger.log(self.logger_name, 'temperature', self.entities.temperature_celsius)
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
                self.datalogger.log(self.logger_name, 'cycles', self.entities.charge_cycles)
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
            try:
                for cell in self.entities.cell_mvoltage:
                    if self.entities.cell_mvoltage[cell] > 0:
                        self.datalogger.log(self.logger_name, 'cell_{}'.format(cell), self.entities.cell_mvoltage[cell])
            except:
                pass

            # logging.info("Cell voltage: {}".format(self.entities.cell_voltage))

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

    def value_changed(self, var, was, val):
        if float(was) != float(val):
            logging.debug("Value of {} changed from {} to {}".format(var, was, val))
            self.dumpall()

    
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
        self._power_switch_status = 0
        self.solarLinkUtil = SolarLinkUtil(self.alias, self)  

    @property
    def device_id(self):
        return self._device_id

    @property
    def send_ack(self):
        return self._send_ack

    @property
    def power_switch_status(self):
        return self._power_switch_status

    @power_switch_status.setter
    def power_switch_status(self, value):
        self._power_switch_status = value


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





    def parse_notification(self, value):
        if self.solarLinkUtil.pollerUpdate(self.poll_register, value):
            return True
        else:
            logging.warning("Error during parse_notification")



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
        self.smartPowerUtil = SmartPowerUtil(self.alias, self)  

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
        if self.smartPowerUtil.broadcastUpdate(value):
            return True
        return False

    # def dumpall(self):
    #     logging.info("RAW voltage == {}, current == {}, soc == {}, capacity == {}, cycles == {}, status == {}, temperature == {}, health = {}".format(self.mvoltage, self.mcurrent, self.dsoc, self.mcapacity, self.charge_cycles, self.state, self.temperature, self.health))



