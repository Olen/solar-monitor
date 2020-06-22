#!/usr/bin/env python3

# from __future__ import print_function
import os
import sys
import blegatt
import time
from datetime import datetime

# import duallog
import logging

# duallog.setup('SmartPower', minLevel=logging.INFO)



class MeritsunUtil():
    '''
    Class for reading and parsing data from various SpartPower-BLE-streams
    '''

    def __init__(self, device_type, power_device):
        self.SOI = 1
        self.INFO = 2
        self.EOI = 3
        self.RecvDataType = self.SOI
        self.RevBuf = [None] * 122
        self.Revindex = 0
        # self.TAG = "SmartPowerUtil"
        self.DeviceType = device_type
        self.PowerDevice = power_device
        self.end = 0



    def getValue(self, buf, start, end):
        # Reads "start" -> "end" from "buf" and return the hex-characters in the correct order
        string = buf[start:end + 1]
        # logging.debug(string)
        e = end + 1
        b = end - 1
        string = ""
        while b >= start:
            chrs = buf[b:e]
            # logging.debug(chrs)
            e = b
            b = b - 2
            string += chr(chrs[0]) + chr(chrs[1])
            # logging.debug(string)
        try: 
            ret = int(string, 16)
        except Exception as e:
            ret = 0
        return ret


    def asciitochar(self, a, b):
        x1 = 0
        if a >= 48 and a <= 57:
            x1 = a - 48
        elif a < 65 or a > 70:
            x1 = 0
        else:
            x1 = (a - 65) + 10
        x2 = x1 << 4
        if b >= 48 and b <= 57:
            return x2 + (b - 48)
        if b < 65 or b > 70:
            return x2 + 0
        return x2 + (b - 65) + 10


    def validateChecksum(self, buf):
        Chksum1 = 0
        Chksum2 = 0
        # end = 114
        j = 1
        while j < self.end - 5:
            # Chksum1 = int((self.asciitochar(buf[j], buf[j + 1]) + Chksum1))
            Chksum1 = self.getValue(buf, j, j + 1) + Chksum1
            j += 2
        # logging.debug("Checksum 1: {}".format(Chksum1))

        # Chksum2 = ((int(self.asciitochar(buf[j], buf[j + 1]))) << 8) + (int(self.asciitochar(buf[j + 2], buf[j + 3])))
        Chksum2 = (self.getValue(buf, j, j + 1) << 8) + self.getValue(buf, j + 2, j + 3)

        # logging.debug("Checksum 2: {}".format(Chksum2))
        # logging.info("C1 {} C2 {}".format(Chksum1, Chksum2))
        if Chksum1 == Chksum2:
            return True
        return False


    def broadcastUpdate(self, data):
        # Gets the binary data from the BLE-device and converts it to a list of hex-values
        # logging.debug("broadcastUpdate Start {} {}".format(data, self.RevBuf))
        # logging.debug("RevIndex {}".format(self.Revindex))
        # logging.debug("SOI {}".format(self.SOI))
        # logging.debug("RecvDataType start {}".format(self.Revindex))
        cmdData = ""
        if data != None and len(data):
            i = 0
            while i < len(data):
                # logging.debug("Revindex {} {} Data: {}".format(i, self.Revindex, data[i]))
                # logging.debug("RevBuf begin {}".format(self.RevBuf))
                if self.Revindex > 121:
                    # logging.debug("Revindex  > 121 - parsing done")
                    self.Revindex = 0
                    self.end = 0
                    self.RecvDataType = self.SOI
                # if data[i] == 146:
                    # logging.debug("Data_1 == 146 start of info")
                    # self.RecvDataType = self.INFO
                    # self.Revindex = 0
                # logging.debug("RecvDataType {} {}".format(i, self.RecvDataType))
                if self.RecvDataType == self.SOI:
                    # logging.debug("RecvDataType == 1 -> SOI")
                    # logging.debug("Data_1 == {} &255 == {}".format(data[i], data[i] & 255))
                    if data[i] == 146:
                        # logging.debug("Data_1 & 255 == 146 start of info")
                        self.RecvDataType = self.INFO
                        self.RevBuf[self.Revindex] = data[i]
                        self.Revindex = self.Revindex + 1
                elif self.RecvDataType == self.INFO:
                    # logging.debug("RecvDataType == 2 -> INFO")
                    # logging.debug("Revindex {} Data_1 == {}".format(self.Revindex, data[i]))
                    self.RevBuf[self.Revindex] = data[i]
                    self.Revindex = self.Revindex + 1

                    if data[i] == 12:
                        # logging.debug("Data_i == 12 - end: {} Revindex {}".format(self.end, self.Revindex))
                        if self.end < 110:
                            self.end = self.Revindex
                        # if self.Revindex != 121 and self.Revindex != 66 and self.Revindex != 88:
                        # else:
                    # if self.Revindex == 121 or self.Revindex == 66 or self.Revindex == 88:
                        if self.Revindex == 121:
                            self.RecvDataType = self.EOI
                    # else:
                elif self.RecvDataType == self.EOI:
                    # logging.debug("RecvDataType == 3 -> EOI")
                    # logging.debug("Validate Checksum: {}".format(self.validateChecksum(self.RevBuf)))
                    if self.validateChecksum(self.RevBuf):
                        # cmdData = str(self.RevBuf, 1, self.Revindex)
                        # logging.debug("{} revindex: {}".format(self.TAG, self.Revindex))
                        cmdData = self.RevBuf[1:self.Revindex]
                        self.Revindex = 0
                        self.end = 0
                        self.RecvDataType = self.SOI
                        return self.handleMessage(cmdData)
                    self.Revindex = 0
                    self.end = 0
                    self.RecvDataType = self.SOI
                i += 1
        # logging.debug("broadcastUpdate End cmdData: {} RevBuf {}".format(cmdData, self.RevBuf))
        return False






    def handleMessage(self, message):
        # Accepts a list of hex-characters, and returns the human readable values into the powerDevice object
        if message == None or "" == message:
            return False
        # logging.debug("test handleMessage == {}".format(message))
        if len(message) < 38:
            logging.info("len message < 38: {}".format(len(message)))
            return False
        # logging.info("Parsing data from a {}".format(self.DeviceType))

        self.PowerDevice.msg = message
        if self.DeviceType == '12V100Ah-027':
            self.PowerDevice.mvoltage = self.getValue(message, 0, 7)
            self.PowerDevice.mcurrent = self.getValue(message, 8, 15)
            self.PowerDevice.mcapacity = self.getValue(message, 16, 23)
            self.PowerDevice.charge_cycles = self.getValue(message, 24, 27)
            self.PowerDevice.soc = self.getValue(message, 28, 31)
            self.PowerDevice.temperature = self.getValue(message, 32, 35)
            self.PowerDevice.status = self.getValue(message, 36, 37)
            self.PowerDevice.afestatus = self.getValue(message, 40, 41)
            i = 0
            while i < 16:
                self.PowerDevice.cell_mvoltage = (i + 1, self.getValue(message, (i * 4) + 44, (i * 4) + 47))
                i = i + 1

        return True



