#!/usr/bin/env python3

# from __future__ import print_function
from __future__ import absolute_import

import os
import sys
import blegatt

from slinkdata import SLinkData
from slink_modbusdata import ModbusData
# from solardevice import SolarDevice

from datalogger import DataLogger

import logging
import duallog

class MainCommon():

    SEND_UART_DATA = 4097
    SEND_UART_STRING = 4098
    START_SCAN = 4099
    TAG = "MainCommon"

    SOLARLINK_WRITEDATA_DEVICE_UUID =   '0000ffd1-0000-1000-8000-00805f9b34fb'
    SOLARLINK_WRITEDATA_SERVICE_UUID =  '0000ffd0-0000-1000-8000-00805f9b34fb'
    SOLARLINK_READDATA_DEVICE_UUID =    '0000fff1-0000-1000-8000-00805f9b34fb'

    mUartRecvCharacteristic = SOLARLINK_READDATA_DEVICE_UUID
    mUartSendCharacteristic = SOLARLINK_WRITEDATA_DEVICE_UUID

    def __init__(self, SolarDevice):
        self.SolarDevice = SolarDevice

    def SendUartData(self, bs):
        self.sendByteData(bs)

    def sendByteData(self, bs):
        logging.debug("DDDD" + "Send data 00-->:" + str(bs))
        logging.debug(self.TAG + ",USC:" + self.mUartSendCharacteristic )
        # self.mUartSendCharacteristic.setValue(bs)
        # self.mBluetoothLeService.writeCharacteristic(self.mUartSendCharacteristic)
        self.SolarDevice.write_value(str(bs))
        msg = "send data"
        for valueOf in bs:
            msg = str(msg) + str("[{:02x}] ".format(valueOf))
        logging.debug(self.TAG + msg)


    def SendUartString(self, str_):
        sendStrData(str_)

    def sendStrData(self, str_):
        logging.debug("DDDD" + "Send response data 22-->:" + str_)
        # self.mUartSendCharacteristic.setValue(str_)
        # self.mBluetoothLeService.writeCharacteristic(self.mUartSendCharacteristic)
        self.SolarDevice.write_value(str(bs))

    def Sleep(self, ms):
        try:
            Thread.sleep(long(ms))
        except InterruptedException as e:
            e.printStackTrace()

