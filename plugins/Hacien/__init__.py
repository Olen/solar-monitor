#!/usr/bin/env python3

# from __future__ import print_function
import os
import sys
import time
from datetime import datetime

import logging


class Config():
    SEND_ACK  = False
    NEED_POLLING = True
    NOTIFY_SERVICE_UUID      = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
    NOTIFY_CHAR_UUID         = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
    WRITE_SERVICE_UUID       = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
    WRITE_CHAR_UUID_POLLING  = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"

class Util():
    '''
    Class for reading and parsing data from various SmartPower-BLE-streams
    '''

    def __init__(self, power_device):
        self.SOI = 0x0103
        self.INFO = None
        self.EOI = None
        self.buffer = []
        self.pollnum = 0
        self.RecvDataType = self.SOI
        self.RevBuf = [None] * 122
        self.Revindex = 0
        # self.TAG = "SmartPowerUtil"
        self.PowerDevice = power_device
        self.end = 0


    def validate(self, msg: list) -> bool:
        return len(msg) > 0 and self.modbusCrc(msg) == 0
    
    def modbusCrc(self, msg: list) -> int:
        crc = 0xFFFF
        for n in msg:
            crc ^= n
            for i in range(8): 
                if crc & 1:
                    crc >>= 1
                    crc ^= 0xA001
                else:
                    crc >>= 1
        return crc
    

    def notificationUpdate(self, data, char):

        logging.debug("broadcastUpdate Start {} {}".format(data, data.hex()))
        if data[0] == 1 and data[1] == 3:
            # New message
            self.buffer = []
        for char in data:
            self.buffer.append(char)
        if self.validate(self.buffer):
            return self.handleMessage(self.buffer)
        return False

    def handleMessage(self, message):
        # Accepts a list of hex-characters, and returns the human readable values into the powerDevice object
        logging.debug("handleMessage {}".format(message))
        if message == None or "" == message:
            return False
        # logging.debug("test handleMessage == {}".format(message))
        self.PowerDevice.entities.msg = message
        '''
        Fortunately we read a different number of bytes from each register, so we can
        abuse the "length" field (byte #3 in the response) as an "id"
        '''

        if len(self.buffer) > 10 and self.buffer[2] == 0x4c:
            # cell1 = self.buffer[3]*256 + self.buffer[4]
            # cell2 = self.buffer[5]*256 + self.buffer[6]
            # cell3 = self.buffer[7]*256 + self.buffer[8]
            # cell4 = self.buffer[9]*256 + self.buffer[10]
            self.PowerDevice.entities.mvoltage = (self.buffer[-4]*256 + self.buffer[-3]) * 10
            i = 0
            while i < 8:
                cellid = i / 2
                # print(i, cellid)
                # print(self.buffer[i + 3], self.buffer[i + 4])
                if self.buffer[i + 3] != 238 and self.buffer[i + 4] != 73:
                    self.PowerDevice.entities.cell_mvoltage = (int(cellid) + 1, self.buffer[i + 3]*256 + self.buffer[i + 4])
                    # print(self.PowerDevice.entities.cell_mvoltage)
                i = i + 2
            return True

        elif len(self.buffer) > 10 and self.buffer[2] == 0x32:
            self.PowerDevice.entities.mcurrent = (self.buffer[29]*256 + self.buffer[30]) * 10
            self.PowerDevice.entities.exp_capacity = self.buffer[35]*256 + self.buffer[36] / 100
            self.PowerDevice.entities.mcapacity = (self.buffer[37]*256 + self.buffer[38]) * 10
            print(self.buffer[37]*256 + self.buffer[38])
            # self.PowerDevice.entities.max_capacity = self.buffer[37]*256 + self.buffer[38]
            self.PowerDevice.entities.charge_cycles = self.buffer[42]
            self.PowerDevice.entities.soc = self.buffer[32]
            self.PowerDevice.entities.temperature_celsius = int(((self.buffer[3]*256 + self.buffer[4]) - 380) / 10)
            self.PowerDevice.entities.battery_temperature_celsius = self.PowerDevice.entities.temperature_celsius
            
            # current_ah = self.buffer[35]*256 + self.buffer[36]
            # total_ah1 = self.buffer[37]*256 + self.buffer[38]
            # total_ah2 = self.buffer[39]*256 + self.buffer[40]
            # cycles    = self.buffer[42]
            # print(use, soc1, soc2, current_ah, total_ah1, total_ah2, cycles)

            # temp1 = self.buffer[3]*256+buffer[4]
            # print("T1", temp1)
            # temp2 = temp1 - 380
            # print("T2", temp2)
            # temp3 = temp2 / 10
            # print("T3", temp3)
            return True
        # No changes, so we return False
        return False


    def pollRequest(self, force = None):
        data = None
        if self.pollnum == 1:
            data = [0x01, 0x03, 0xd0, 0x00, 0x00, 0x26, 0xfc, 0xd0]
        elif self.pollnum == 5:
            data = [0x01, 0x03, 0xd0, 0x26, 0x00, 0x19, 0x5d, 0x0b]
        elif self.pollnum == 9:
            self.pollnum = 0
        self.pollnum = self.pollnum + 1
        return data

    def ackData(self):
        return []
        # [0x01, 0x03, 0xd0, 0x00, 0x00, 0x26, 0xfc, 0xd0]

