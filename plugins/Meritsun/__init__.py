#!/usr/bin/env python3

# from __future__ import print_function
import os
import sys
import time
from datetime import datetime

# import duallog
import logging

# duallog.setup('SmartPower', minLevel=logging.INFO)


class Config():
    SEND_ACK  = False
    NEED_POLLING = False
    NOTIFY_SERVICE_UUID = "0000ffe0-0000-1000-8000-00805f9b34fb"
    NOTIFY_CHAR_UUID = "0000ffe4-0000-1000-8000-00805f9b34fb"

class Util():
    '''
    Class for reading and parsing data from various SmartPower-BLE-streams

    These devices encode the data in a really crazy way.
    Data is streamed continously, and you need to find certain "start of data" and "end of data"
    markers to get the correct values.
    The data is then divided into chuks of up to 122 bytes

    Example chunk: [56, 49, 51, 54, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 65, 48, 57, 65, 48, 49, 48, 48, 51, 53, 48, 48, 54, 52, 48, 48, 67, 56, 48, 65, 56, 48, 56, 56, 48, 55, 66, 54, 56, 50, 48, 69, 54, 50, 48, 68, 55, 53, 48, 68, 50, 56, 48, 68, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 54, 68, 56, 12, 12, 12, 12, 12, 12, 12, 12]

    Data is read as "little endian" and is ascii-encoded hex characters
    In the above example, the voltage is encoded in the first 8 bytes as follows:
        Read bytes 7 and 8 (48, 48)
        Encode these as ascii-characters "0, 0" (String: "00"
        Read bytes 5 and 6 (48, 48)
        Encode these as ascii-characters "0, 0" (Append to string: "0000")
        Read bytes 3 and 4 (51, 54)
        Encode these as ascii-characters "3, 6" (Append to string: "000036")
        Read bytes 1 and 2 (56, 49)
        Encode these as ascii-characters "8, 1" (Append to string: "00003681")

        convert this hex-string to decimal: 0x00003681 = 13953 = 13.953 V
    '''


    def __init__(self, power_device):
        self.SOI = 1
        self.INFO = 2
        self.EOI = 3
        self.START_VAL = 146
        self.END_VAL = 12
        self.RecvDataType = self.SOI
        self.RevBuf = [None] * 122
        self.Revindex = 0
        # self.TAG = "SmartPowerUtil"
        self.PowerDevice = power_device
        self.end = 0
        self.prev_values = []

    def getValue(self, buf, start, end):
        try:
            # bytes = buf[0:8]
            chars = list(map(chr, buf[start:end + 1]))
            values = [ ''.join(x) for x in zip(chars[0::2], chars[1::2]) ]
            return int("".join(reversed(values)), 16)
        except Exception as e:
            return 0




    def getValue_old(self, buf, start, end):
        # Reads "start" -> "end" from "buf" and return the hex-characters in the correct order
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
        # logging.debug(f"Checksum-calc: buf: {buf}")
        Chksum1 = 0
        Chksum2 = 0
        j = 1
        while j < self.end - 5:
            Chksum1 = self.getValue(buf, j, j + 1) + Chksum1
            # logging.debug(f"Checksum1-calc: j: {j} byteval: {self.getValue(buf, j, j + 1)}, Checksum1: {Chksum1}")
            j += 2
        # logging.debug("Checksum 1: {}".format(Chksum1))

        Chksum2 = (self.getValue(buf, j, j + 1) << 8) + self.getValue(buf, j + 2, j + 3)
        # logging.debug(f"Checksum2-calc: j: {j} byteval: {self.getValue(buf, j, j + 1)}, Shifted: {self.getValue(buf, j, j + 1) << 8}, Byteval2: {self.getValue(buf, j + 2, j + 3)}")

        # logging.debug("Checksum 2: {}".format(Chksum2))
        # logging.info("C1 {} C2 {}".format(Chksum1, Chksum2))
        if Chksum1 == Chksum2:
            return True
        return False


    def notificationUpdate(self, data, char):
        # Gets the binary data from the BLE-device and converts it to a list of hex-values
        logging.debug("broadcastUpdate Start {} {}".format(data, data.hex()))
        if self.PowerDevice.config.getboolean('monitor', 'debug', fallback=False):
            with open(f"/tmp/{self.PowerDevice.alias()}.log", 'a') as debugfile:
                debugfile.write(f"{datetime.now()} <- {data.hex()}\n")

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
                    # We have read more than 121 bytes, and don't care about the rest
                    # logging.debug("Revindex  > 121 - parsing done")
                    self.Revindex = 0
                    self.end = 0
                    self.RecvDataType = self.SOI

                if self.RecvDataType == self.SOI:
                    # 1. We start here, reading byte by byte until we get to the number 146 (hex 92)
                    # Example: 30 30 30 35 39 35 0c 0c 0c 0c 0c 0c 0c 0c 92 37 37
                    #                                                    ^^

                    if data[i] == self.START_VAL:
                        # When we find 146, we start filling the message buffer, and set a flag to read more data:
                        self.RecvDataType = self.INFO
                        self.RevBuf[self.Revindex] = data[i]
                        self.Revindex = self.Revindex + 1
                elif self.RecvDataType == self.INFO:
                    # 2. The INFO-flag i set, lets continue to fill the buffer

                    self.RevBuf[self.Revindex] = data[i]
                    self.Revindex = self.Revindex + 1

                    # The number 12 (hex 0C) marks the end of the message
                    if data[i] == self.END_VAL:
                        if self.end < 110:
                            # Not sure why we need this...
                            self.end = self.Revindex
                        if self.Revindex == 121:
                            # We have read 121 bytes and that marks the end of the buffer
                            self.RecvDataType = self.EOI
                elif self.RecvDataType == self.EOI:
                    # 3. We should now have a buffer with 121 bytes,
                    # starting with the first byte after value 146 (hex 92)

                    # logging.debug("RecvDataType == 3 -> EOI")
                    # logging.debug("Validate Checksum: {}".format(self.validateChecksum(self.RevBuf)))
                    if self.validateChecksum(self.RevBuf):
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
        # 2024-03-22 10:22:51,195 DEBUG   : handleMessage [56, 49, 51, 54, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 65, 48, 57, 65, 48, 49, 48, 48, 51, 53, 48, 48, 54, 52, 48, 48, 67, 56, 48, 65, 56, 48, 56, 56, 48, 55, 66, 54, 56, 50, 48, 69, 54, 50, 48, 68, 55, 53, 48, 68, 50, 56, 48, 68, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 48, 54, 68, 56, 12, 12, 12, 12, 12, 12, 12, 12]

        logging.debug("handleMessage {}".format(message))
        if message == None or "" == message:
            return False
        if message != self.prev_values:
            logging.debug("Response changed:")
            logging.debug(f"- {self.prev_values}")
            logging.debug(f"+ {message}:")
        self.prev_values = message

        if len(message) < 38:
            logging.info("len message < 38: {}".format(len(message)))
            return False

        self.PowerDevice.entities.msg = message
        # if self.DeviceType == '12V100Ah-027':
        self.PowerDevice.entities.mvoltage = self.getValue(message, 0, 7)
        mcurrent = self.getValue(message, 8, 15)
        if mcurrent > 2147483647:
            mcurrent = mcurrent - 4294967295
        self.PowerDevice.entities.mcurrent = mcurrent
        self.PowerDevice.entities.mcapacity = self.getValue(message, 16, 23)
        self.PowerDevice.entities.charge_cycles = self.getValue(message, 24, 27)
        self.PowerDevice.entities.soc = self.getValue(message, 28, 31)
        self.PowerDevice.entities.temperature = self.getValue(message, 32, 35)
        self.PowerDevice.entities.status = self.getValue(message, 36, 37)
        self.PowerDevice.entities.afestatus = self.getValue(message, 40, 41)
        i = 0
        while i < 16:
            self.PowerDevice.entities.cell_mvoltage = (i + 1, self.getValue(message, (i * 4) + 44, (i * 4) + 47))
            i = i + 1

        return True



