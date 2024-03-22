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
    Class for reading and parsing data from various Hacien-batteries (App: HC BLE)

    Reading values is pretty straight forward
    The batteries need to be polled, polling strings from the app is easily found
    Values are simple 1 or 2 byte integers, little endian, so they can be read more or less directly

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
        self.prev_values = {}


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

    def getValue(self, buf: bytearray, start: int, length: int = 1) -> int:
        ''' Reads length bytes from buf '''
        if length == 1:
            return int(buf[start])
        if length == 2:
            return int(buf[start]*256 + buf[start + 1])
        return 0



    def notificationUpdate(self, data, char):
        logging.debug("broadcastUpdate Start {} {}".format(data, data.hex()))
        if self.PowerDevice.config.getboolean('monitor', 'debug', fallback=False):
            with open(f"/tmp/{self.PowerDevice.alias()}.log", 'a') as debugfile:
                debugfile.write(f"{datetime.now()} <- {data.hex()}\n")
        if data[0] == 1 and data[1] == 3:
            # New message
            self.buffer = []
        for char in data:
            self.buffer.append(char)
        if self.validate(self.buffer):
            # The checksum is correct, so we assume we have a complete message
            return self.handleMessage(self.buffer)
        return False

    def handleMessage(self, message):
        # Accepts a list of hex-characters, and returns the human readable values into the powerDevice object
        if message == None or "" == message:
            return False
        logging.debug("handleMessage {}".format(message))
        if message[2] in self.prev_values:
            if message != self.prev_values[message[2]]:
                logging.debug("Response changed:")
                logging.debug(f"- {self.prev_values[message[2]]}")
                logging.debug(f"+ {message}:")
        self.prev_values[message[2]] = message

        # logging.debug("test handleMessage == {}".format(message))
        self.PowerDevice.entities.msg = message
        '''
        Fortunately we read a different number of bytes from each register, so we can
        abuse the "length" field (byte #3 in the response) as an "id"
        '''

        if len(message) > 10 and message[2] == 0x32:

            # DEBUG: broadcastUpdate Start b'\x01\x032\x01\xe0\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01\xea\x00\x00' 01033201e00000000000000000000001ea0000
            # DEBUG: broadcastUpdate Start b'\x00\x00\x02\x12\x01\xea\x01\xe0\x00G\x00\x00\x00d\x00d0\xd40\xd4' 0000021201ea01e0004700000064006430d430d4
            # DEBUG: broadcastUpdate Start b'0\xd4\x00\x06\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x04\xa6' 30d400060000000000000000000004a6
            # 
            #         0103 32 01e0 00 00 00 00 00 00 00 00 00 00 01 ea 00 00
            #         0000 02 12 01 ea 01e0 0047 00000064006430d430d4
            #         30d400060000000000000000000004a6
            # 
            #           0  1   2  3    4  5  6  7  8  9 10 11 12 13 14 15   16 17 18 19 20 21  22 23   24 25  26  27 28
            # DEBUG: - [1, 3, 50, 1, 224, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 234, 0, 0, 0, 0, 2, 18, 1, 234, 1, 224, 0,  0, 0, 0, 0, 100, 0, 100, 48, 212, 48, 212, 48, 212, 0, 6, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 248, 29]
            # DEBUG: + [1, 3, 50, 1, 224, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 234, 0, 0, 0, 0, 2, 18, 1, 234, 1, 224, 0, 71, 0, 0, 0, 100, 0, 100, 48, 212, 48, 212, 48, 212, 0, 6, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 4, 166]:
            # 



            self.PowerDevice.entities.temperature_celsius = int(((message[3]*256 + message[4]) - 380) / 10)
            # Charge
            charge_current = (message[27]*256 + message[28]) * 100
            # Usage
            draw_current = (message[29]*256 + message[30]) * 100
            if draw_current > 0:
                self.PowerDevice.entities.mcurrent = draw_current * -1
            else:
                self.PowerDevice.entities.mcurrent = charge_current
            self.PowerDevice.entities.exp_capacity = (message[35]*256 + message[36]) / 100
            self.PowerDevice.entities.mcapacity = (message[37]*256 + message[38]) * 10
            # print(message[37]*256 + message[38])
            # self.PowerDevice.entities.max_capacity = message[37]*256 + message[38]
            self.PowerDevice.entities.charge_cycles = message[42]
            self.PowerDevice.entities.soc = message[32]
            self.PowerDevice.entities.battery_temperature_celsius = self.PowerDevice.entities.temperature_celsius
            return True
            
            # current_ah = message[35]*256 + message[36]
            # total_ah1 = message[37]*256 + message[38]
            # total_ah2 = message[39]*256 + message[40]
            # cycles    = message[42]
            # print(use, soc1, soc2, current_ah, total_ah1, total_ah2, cycles)

            # temp1 = message[3]*256+buffer[4]
            # print("T1", temp1)
            # temp2 = temp1 - 380
            # print("T2", temp2)
            # temp3 = temp2 / 10
            # print("T3", temp3)
        elif len(message) > 10 and message[2] == 0x4c:
            self.PowerDevice.entities.mvoltage = (message[-4]*256 + message[-3]) * 10
            i = 0
            while i < 8:
                cellid = i / 2
                # print(i, cellid)
                # print(message[i + 3], message[i + 4])
                if message[i + 3] != 238 and message[i + 4] != 73:
                    self.PowerDevice.entities.cell_mvoltage = (int(cellid) + 1, message[i + 3]*256 + message[i + 4])
                    # print(self.PowerDevice.entities.cell_mvoltage)
                i = i + 2
            return True
        # No changes, so we return False
        return False


    def pollRequest(self, force = None):
        data = None
        if self.pollnum == 1:
            data = [0x01, 0x03, 0xd0, 0x00, 0x00, 0x26, 0xfc, 0xd0]
        elif self.pollnum == 2:
            data = [0x01, 0x03, 0xd0, 0x00, 0x00, 0x26, 0xfc, 0xd0]
            data = None
        elif self.pollnum == 3:
            data = [0x01, 0x03, 0xd0, 0x26, 0x00, 0x19, 0x5d, 0x0b]
        elif self.pollnum == 4:
            data = [0x01, 0x03, 0xd1, 0x15, 0x00, 0x0c, 0x6d, 0x37]
            data = None
        elif self.pollnum == 5:
            data = [0x01, 0x03, 0xd1, 0x00, 0x00, 0x15, 0xbd, 0x39]
            data = None
        elif self.pollnum == 6:
            data = [0x01, 0x03, 0x23, 0x1c, 0x00, 0x04, 0x8e, 0x4b]
            data = None
        elif self.pollnum == 7:
            data = [0x01, 0x03, 0xd2, 0x00, 0x00, 0x01, 0xbd ,0x72]
            data = None
        elif self.pollnum == 10:
            self.pollnum = 0
        self.pollnum = self.pollnum + 1
        if data and self.PowerDevice.config.getboolean('monitor', 'debug', fallback=False):
            with open(f"/tmp/{self.PowerDevice.alias()}.log", 'a') as debugfile:
                debugfile.write(f"{datetime.now()} -> {bytearray(data).hex()}\n")
        return data

    def ackData(self):
        return []
        # [0x01, 0x03, 0xd0, 0x00, 0x00, 0x26, 0xfc, 0xd0]

