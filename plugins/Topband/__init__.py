#!/usr/bin/env python3

# from __future__ import print_function
import os
import sys
import time
from datetime import datetime

# import duallog
import logging

import asciihex
from codec import INT32_MAX, UINT32_WRAP, to_signed

# duallog.setup('SmartPower', minLevel=logging.INFO)


class Config():
    SEND_ACK  = False
    NEED_POLLING = False
    NOTIFY_SERVICE_UUID = "0000ffe0-0000-1000-8000-00805f9b34fb"
    NOTIFY_CHAR_UUID = "0000ffe4-0000-1000-8000-00805f9b34fb"

class Util():
    '''
    Class for reading and parsing data from various Topband-Smartpower-BLE-streams
    '''

    def __init__(self, power_device):
        self.protocolHead = 94
        self.protocolEnd = 0
        self.SOI = 1
        self.INFO = 2
        self.EOI = 3
        self.RecvDataType = self.SOI
        self.RevBuf = [None] * 115
        self.Revindex = 0
        # self.TAG = "SmartPowerUtil"
        self.PowerDevice = power_device
        self.end = 0



    def notificationUpdate(self, data, char):
        # Gets the binary data from the BLE-device and converts it to a list of hex-values
        cmdData = ""
        if data != None and len(data):
            i = 0
            while i < len(data):
                if self.Revindex > 114:
                    self.Revindex = 0
                    self.end = 0
                    self.RecvDataType = self.SOI
                if self.RecvDataType == self.SOI:
                    if data[i] == self.protocolHead:
                        self.RecvDataType = self.INFO
                        self.RevBuf[self.Revindex] = data[i]
                        self.Revindex = self.Revindex + 1
                elif self.RecvDataType == self.INFO:
                    self.RevBuf[self.Revindex] = data[i]
                    self.Revindex = self.Revindex + 1

                    if data[i] == self.protocolEnd:
                        if self.end < 110:
                            self.end = self.Revindex
                        if self.Revindex == 114:
                            self.RecvDataType = self.EOI
                elif self.RecvDataType == self.EOI:
                    if asciihex.checksum_matches(self.RevBuf, self.end):
                        cmdData = self.RevBuf[1:self.Revindex]
                        self.Revindex = 0
                        self.end = 0
                        self.RecvDataType = self.SOI
                        return self.handleMessage(cmdData)
                    self.Revindex = 0
                    self.end = 0
                    self.RecvDataType = self.SOI
                i += 1
        return False






    def handleMessage(self, message):
        # Accepts a list of hex-characters, and returns the human readable values into the powerDevice object
        logging.debug("handleMessage {}".format(message))
        if message == None or "" == message:
            return False
        # logging.debug("test handleMessage == {}".format(message))
        if len(message) < 38:
            logging.info("len message < 38: {}".format(len(message)))
            return False
        # logging.info("Parsing data from a {}".format(self.DeviceType))

        self.PowerDevice.entities.msg = message
        # if self.DeviceType == '12V100Ah-027':
        self.PowerDevice.entities.mvoltage = asciihex.field_value(message, 0, 7)
        logging.debug("mVoltage: {}".format(asciihex.field_value(message, 0, 7)))
        mcurrent = to_signed(asciihex.field_value(message, 8, 15), UINT32_WRAP, INT32_MAX)
        self.PowerDevice.entities.mcurrent = mcurrent
        self.PowerDevice.entities.mcapacity = asciihex.field_value(message, 16, 23)
        self.PowerDevice.entities.charge_cycles = asciihex.field_value(message, 24, 27)
        self.PowerDevice.entities.soc = asciihex.field_value(message, 28, 31)
        self.PowerDevice.entities.temperature = asciihex.field_value(message, 32, 35)
        self.PowerDevice.entities.status = asciihex.field_value(message, 36, 37)
        self.PowerDevice.entities.afestatus = asciihex.field_value(message, 40, 41)
        i = 0
        while i < 16:
            self.PowerDevice.entities.cell_mvoltage = (i + 1, asciihex.field_value(message, (i * 4) + 44, (i * 4) + 47))
            i = i + 1

        return True