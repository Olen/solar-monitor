#!/usr/bin/env python3

from __future__ import print_function
import os
import sys
import blegatt
import time

# import duallog
import logging

# duallog.setup('SmartPower', minLevel=logging.INFO)



class BatteryEntity():
    # CREATOR = Creator()

    def createFromParcel(self, source):
        return BatteryEntity(source)

    def newArray(self, size):
        return BatteryEntity[size]

    afeStatus = 0
    bluetoothDevice = None
    mBatteryType = int()
    mCapacity = 0
    mCapacityOld1 = 0
    mCurrent = 0
    mCurrentOld1 = 0
    mCurrentOld2 = 0
    mCycles = 0
    mCyclesOld1 = 0
    mCyclesOld2 = 0
    mGetInfoStatus = 1
    mSoc = 0
    mSocOld1 = int()
    mSocOld2 = int()
    mStatus = 0
    mTemperature = 0
    mTemperatureOld1 = 0
    mTemperatureOld2 = 0
    mVoltage = 0
    mVoltageOld1 = 0
    mVoltageOld2 = 0
    msg = None

    #@overloaded
    def __init__(self, bluetoothDevice2):
        super(BatteryEntity, self).__init__()
        self.bluetoothDevice = bluetoothDevice2

    def getmCurrent(self):
        return self.mCurrent

    def setmCurrent(self, mCurrent2):
        self.mCurrentOld2 = self.mCurrentOld1
        self.mCurrentOld1 = mCurrent2
        self.mCurrent = mCurrent2

    def getmVoltage(self):
        return self.mVoltage

    def setmVoltage(self, mVoltage2):
        self.mVoltageOld2 = self.mVoltageOld1
        self.mVoltageOld1 = mVoltage2
        self.mVoltage = mVoltage2

    def getmCapacity(self):
        return self.mCapacity

    def setmCapacity(self, mCapacity2):
        self.mCapacityOld1 = self.mCapacity
        self.mCapacity = mCapacity2

    def getmCycles(self):
        return self.mCycles

    def setmCycles(self, mCycles2):
        self.mCyclesOld2 = self.mCyclesOld1
        self.mCyclesOld1 = mCycles2
        self.mCycles = mCycles2

    def setmStatus(self, mStatus2):
        self.mStatus = mStatus2

    def getmSoc(self):
        return self.mSoc

    def setmSoc(self, mSoc2):
        self.mSocOld2 = self.mSocOld1
        self.mSocOld1 = self.mSoc
        self.mSoc = mSoc2

    def getmTemperature(self):
        return self.mTemperature

    def setmTemperature(self, mTemperature2):
        self.mTemperatureOld2 = self.mTemperatureOld1
        self.mTemperatureOld1 = mTemperature2
        self.mTemperature = mTemperature2

    def setmBatteryType(self, mBatteryType2):
        self.mBatteryType = mBatteryType2

    def setMsg(self, msg2):
        self.msg = msg2

    def getmCapacityOld1(self):
        return self.mCapacityOld1

    def setAfeStatus(self, afeStatus2):
        self.afeStatus = afeStatus2

    # def writeToParcel(self, dest, flags):
        # dest.writeParcelable(self.bluetoothDevice, flags)
        # dest.writeInt(self.mCurrent)
        # dest.writeInt(self.mVoltage)
        # dest.writeInt(self.mCapacity)
        # dest.writeInt(self.mCycles)
        # dest.writeInt(self.mStatus)
        # dest.writeInt(self.mSoc)
        # dest.writeInt(self.mTemperature)
        # dest.writeInt(self.mBatteryType)
        # dest.writeString(self.msg)
        # dest.writeInt(self.mGetInfoStatus)
        # dest.writeInt(self.afeStatus)

    # @__init__.register(object, Parcel)
    def __init___1(self, in_):
        super(BatteryEntity, self).__init__()
        self.bluetoothDevice = in_.BluetoothDevice.__class__.getClassLoader()
        self.mCurrent = in_.readInt()
        self.mVoltage = in_.readInt()
        self.mCapacity = in_.readInt()
        self.mCycles = in_.readInt()
        self.mStatus = in_.readInt()
        self.mSoc = in_.readInt()
        self.mTemperature = in_.readInt()
        self.mBatteryType = in_.readInt()
        self.msg = in_.readString()
        self.mGetInfoStatus = in_.readInt()
        self.afeStatus = in_.readInt()


class SmartPowerUtil2():

    def __init__(self):
        logging.debug("Initiating new SmartPowerUtil2")
        self.Current = 0
        self.EOI = 3
        self.INFO = 2
        self.SOI = 1
        self.RecvDataType = self.SOI
        self.RevBuf = [None] * 122
        self.Revindex = 0
        self.Status = 0
        self.TAG = "SmartPowerUtil"
        self.end = 0
        self.soc = 0



    def getValue(self, buf, start, end):
        # Reads "start" -> "end" from "buf" and return the hex-characters in the correct order
        string = buf[start:end + 1]
        logging.debug(string)
        e = end + 1
        b = end - 1
        string = ""
        while b >= start:
            chrs = buf[b:e]
            logging.debug(chrs)
            e = b
            b = b - 2
            string += chr(chrs[0]) + chr(chrs[1])
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
        end = 114
        j = 1
        while j < self.end - 5:
            Chksum1 = int((self.asciitochar(buf[j], buf[j + 1]) + Chksum1))
            j += 2
        logging.debug("Checksum 1: {}".format(Chksum1))

        Chksum2 = ((int(self.asciitochar(buf[j], buf[j + 1]))) << 8) + (int(self.asciitochar(buf[j + 2], buf[j + 3])))
        logging.debug("Checksum 2: {}".format(Chksum2))
        if Chksum1 == Chksum2:
            return True
        return False


    def broadcastUpdate(self, data):
        # Gets the binary data from the BLE-device and converts it to a list of hex-values
        logging.debug("broadcastUpdate Start {} {}".format(data, self.RevBuf))
        logging.debug("RevIndex {}".format(self.Revindex))
        logging.debug("SOI {}".format(self.SOI))
        logging.debug("RecvDataType start {}".format(self.Revindex))
        cmdData = ""
        if data != None and len(data):
            i = 0
            while i < len(data):
                logging.debug("Revindex {} {}".format(i, self.Revindex))
                logging.debug("RevBuf begin {}".format(self.RevBuf))
                if self.Revindex > 121:
                    logging.debug("Revindex  > 121 - parsing done")
                    self.Revindex = 0
                    self.end = 0
                    self.RecvDataType = self.SOI
                logging.debug("RecvDataType {} {}".format(i, self.RecvDataType))
                if self.RecvDataType == self.SOI:
                    logging.debug("RecvDataType == 1 -> SOI")
                    logging.debug("Data_1 == {} &255 == {}".format(data[i], data[i] & 255))
                    if (data[i] & 255) == 146:
                        logging.debug("Data_1 & 255 == 146 start of info")
                        self.RecvDataType = self.INFO
                        self.RevBuf[self.Revindex] = data[i]
                        self.Revindex = self.Revindex + 1
                elif self.RecvDataType == self.INFO:
                    logging.debug("RecvDataType == 2 -> INFO")
                    logging.debug("Data_1 == {}".format(data[i]))
                    self.RevBuf[self.Revindex] = data[i]
                    self.Revindex = self.Revindex + 1

                    if data[i] == 12:
                        logging.debug("Data_i == 12 - end: {} Revindex {}".format(self.end, self.Revindex))
                        if self.end < 110:
                            self.end = self.Revindex
                        # if self.Revindex != 121 and self.Revindex != 66 and self.Revindex != 88:
                        # else:
                        if self.Revindex == 121 or self.Revindex == 66 or self.Revindex == 88:
                            self.RecvDataType = self.EOI
                    # else:
                elif self.RecvDataType == self.EOI:
                    logging.debug("RecvDataType == 3 -> EOI")
                    logging.debug("Validate Checksum: {}".format(self.validateChecksum(self.RevBuf)))
                    if self.validateChecksum(self.RevBuf):
                        # cmdData = str(self.RevBuf, 1, self.Revindex)
                        logging.debug("{} revindex: {}".format(self.TAG, self.Revindex))
                        cmdData = self.RevBuf[1:self.Revindex]
                        self.Status = self.getValue(self.RevBuf, 37, 38)
                        self.soc = self.getValue(self.RevBuf, 29, 32)
                        self.current = self.getValue(self.RevBuf, 9, 15)
                    self.Revindex = 0
                    self.end = 0
                    self.RecvDataType = self.SOI
                i += 1
        logging.debug("broadcastUpdate End cmdData: {} RevBuf {}".format(cmdData, self.RevBuf))
        return cmdData






    def handleMessage(self, message, batteryEntity):
        # Accepts a list of hex-characters, and returns the human readable values into the batteryEntity object
        if batteryEntity == None or message == None or "" == message:
            return False
        logging.debug("test handleMessage == {}".format(message))
        # RevBuf2 = str_.getBytes()
        RevBuf2 = message
        if len(RevBuf2) < 38:
            logging.debug("len message < 38: {}".format(len(RevBuf2)))
            return False

        # print("Voltage", GetValue(RevBuf2, 0, 7))
        # print("Current", GetValue(RevBuf2, 8, 15))
        # print("Capacity", GetValue(RevBuf2, 16, 23))
        # print("Cycles", GetValue(RevBuf2, 24, 27))
        voltage = self.getValue(RevBuf2, 0, 7)
        current = self.getValue(RevBuf2, 8, 15)
        capacity = self.getValue(RevBuf2, 16, 23)
        cycles = self.getValue(RevBuf2, 24, 27)
        soc2 = self.getValue(RevBuf2, 28, 31)
        temperature = self.getValue(RevBuf2, 32, 35)
        status = self.getValue(RevBuf2, 36, 37)
        unknown = self.getValue(RevBuf2, 38, 39)
        afestatus = self.getValue(RevBuf2, 40, 41)

        batteryEntity.setAfeStatus(afestatus)
        batteryEntity.setmVoltage(voltage)
        batteryEntity.setmCurrent(current)
        batteryEntity.setmSoc(soc2)
        if batteryEntity.getmCapacityOld1() <= 0:
            batteryEntity.setmCapacity(capacity)
        elif abs(capacity - batteryEntity.getmCapacityOld1()) < 10000:
            batteryEntity.setmCapacity(capacity)
        batteryEntity.setmCycles(cycles)
        batteryEntity.setmStatus(status)
        batteryEntity.setmTemperature(temperature)
        batteryEntity.setmBatteryType(len(message))
        batteryEntity.setMsg(message)
        # print("test voltage==", voltage, "==current==", current, "==soc==", soc2, "==capacity==", capacity, "==cycles==", cycles, "==status==", status, "==temperature==", temperature, "==str.length()==", len(str_))
        logging.info("Test voltage == {}, current == {}, soc == {}, capacity == {}, cycles == {}, status == {}, temperature == {}, len = {}".format(voltage, current, soc2, capacity, cycles, status, temperature, len(message)))
        return True






class SmartPowerUtil(object):
    Current = 0
    EOI = 3
    INFO = 2
    SOI = 1
    RecvDataType = SOI
    RevBuf = [None] * 122
    Revindex = 0
    Status = 0
    TAG = "SmartPowerUtil"
    end = 0
    soc = 0


#     broadcastUpdate Start b'\x0c\x0c\x0c\x923A330000B3020000' [None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None]
#     broadcastUpdate End  [146, 51, 65, 51, 51, 48, 48, 48, 48, 66, 51, 48, 50, 48, 48, 48, 48, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None]


    @classmethod
    def broadcastUpdate(cls, data):
        # Gets the binary data from the BLE-device and converts it to a list of hex-values
        print("broadcastUpdate Start", data, cls.RevBuf)
        print("RevIndex", cls.Revindex)
        print("SOI", cls.SOI)
        print("RecvDataType start", cls.Revindex)
        cmdData = ""
        if data != None and len(data):
            i = 0
            while i < len(data):
                print("Revindex ", i, cls.Revindex)
                print("RevBuf begin", cls.RevBuf)
                if cls.Revindex > 121:
                    print("Revindex  > 121")
                    cls.Revindex = 0
                    cls.end = 0
                    cls.RecvDataType = cls.SOI
                print("RecvDataType ", i, cls.RecvDataType)
                if cls.RecvDataType == 1:
                    print("RecvDataType == 1")
                    # if (data[i] & 255) != 146:
                    # else:
                    if (data[i] & 255) == 146:
                        print("Data_1 == 146")
                        print("RevBuf-01", cls.RevBuf)
                        cls.RecvDataType = cls.INFO
                        print("RevBuf-02", cls.RevBuf)
                        bArr = cls.RevBuf
                        print("RevBuf-03", cls.RevBuf)
                        i2 = cls.Revindex
                        print("RevBuf-04", cls.RevBuf)
                        cls.Revindex = i2 + 1
                        print("RevBuf-05", cls.RevBuf)
                        if bArr[i2] != data[i]:
                            print("X Old", bArr[i2], "New", data[i])
                        bArr[i2] = data[i]
                        print("RevBuf-06", cls.RevBuf)






# RevBuf-05 [None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None]
# RevBuf-06 [146, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None]
# Revindex  15 1
# RevBuf begin [146, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None]
# RecvDataType  15 2
# RecvDataType == 2
# Revindex  16 2
# RevBuf begin [146, 66, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None]
# RecvDataType  16 2
# RecvDataType == 2
# Revindex  17 3
# RevBuf begin [146, 66, 56, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None]



                elif cls.RecvDataType == 2:
                    print("RecvDataType == 2")
                    print("Data_i", data[i])
                    bArr2 = cls.RevBuf
                    i3 = cls.Revindex
                    cls.Revindex = i3 + 1
                    if bArr2[i3] != data[i]:
                        print("Y Old", bArr2[i3], "New", data[i])
                    bArr2[i3] = data[i]
                    if data[i] == 12:
                        print("Data_i == 12")
                        print("cls_end", cls.end)
                        print("cls_Revindex", cls.Revindex)
                        if cls.end < 110:
                            cls.end = cls.Revindex
                        # if cls.Revindex != 121 and cls.Revindex != 66 and cls.Revindex != 88:
                        # else:
                        if cls.Revindex == 121 or cls.Revindex == 66 or cls.Revindex == 88:
                            cls.RecvDataType = cls.EOI
                    # else:
                elif cls.RecvDataType == 3:
                    print("RecvDataType == 3")
                    Chksum = 0
                    cls.end = 114
                    j = 1
                    while j < cls.end - 5:
                        Chksum = int((cls.Asciitochar(cls.RevBuf[j], cls.RevBuf[j + 1]) + Chksum))
                        j += 2
                    i1 = 0
                    while i1 < len(cls.RevBuf):
                        if cls.RevBuf[i1] is not None:
                            print("test broadcastUpdate ==", i1, ":", cls.RevBuf[i1], chr(cls.RevBuf[i1]))
                        else:
                            print("test broadcastUpdate ==", i1, ":", cls.RevBuf[i1])
                        i1 += 1
                    print(cls.TAG, "broadcastUpdate: Chksum ==", Chksum)
                    print(cls.TAG, "broadcastUpdate: ", (((int(cls.Asciitochar(cls.RevBuf[cls.end - 5], cls.RevBuf[cls.end - 4]))) << 8) + (int(cls.Asciitochar(cls.RevBuf[cls.end - 3], cls.RevBuf[cls.end - 2])))))
                    print(cls.TAG, "broadcastUpdate: end ==", cls.end)
                    if Chksum == ((int(cls.Asciitochar(cls.RevBuf[cls.end - 5], cls.RevBuf[cls.end - 4]))) << 8) + (int(cls.Asciitochar(cls.RevBuf[cls.end - 3], cls.RevBuf[cls.end - 2]))):
                        # cmdData = str(cls.RevBuf, 1, cls.Revindex)
                        print(cls.TAG, "revindex:", cls.Revindex)
                        cmdData = cls.RevBuf[1:cls.Revindex]
                        cls.Status = cls.GetValue(cls.RevBuf, 37, 38)
                        cls.soc = cls.GetValue(cls.RevBuf, 29, 32)
                        cls.current = cls.GetValue(cls.RevBuf, 9, 15)
                        # cls.Status = cls.Asciitochar(cls.RevBuf[37], cls.RevBuf[38])
                        # cls.soc = cls.Asciitochar(cls.RevBuf[31], cls.RevBuf[32])
                        # cls.soc <<= 8
                        # cls.soc += cls.Asciitochar(cls.RevBuf[29], cls.RevBuf[30])
                        # cls.Current = cls.Asciitochar(cls.RevBuf[15], cls.RevBuf[16])
                        # cls.Current <<= 8
                        # cls.Current += cls.Asciitochar(cls.RevBuf[13], cls.RevBuf[14])
                        # cls.Current <<= 8
                        # cls.Current += cls.Asciitochar(cls.RevBuf[11], cls.RevBuf[12])
                        # cls.Current <<= 8
                        # cls.Current += cls.Asciitochar(cls.RevBuf[9], cls.RevBuf[10])
                    cls.Revindex = 0
                    cls.end = 0
                    cls.RecvDataType = cls.SOI
                i += 1
        print("broadcastUpdate End", cmdData, cls.RevBuf)
        return cmdData



    @classmethod
    def Asciitochar(cls, a, b):
        x = int()
        if a >= 48 and a <= 57:
            x = a - 48
        elif a < 65 or a > 70:
            x = 0
        else:
            x = (a - 65) + 10
        x2 = x << 4
        if b >= 48 and b <= 57:
            return x2 + (b - 48)
        if b < 65 or b > 70:
            return x2 + 0
        return x2 + (b - 65) + 10

    @classmethod
    def GetValue(cls, buf, start, end):
        # Reads "start" -> "end" from "buf" and return the hex-characters in the correct order
        string = buf[start:end + 1]
        print(string)
        e = end + 1
        b = end - 1
        string = ""
        while b >= start:
            chrs = buf[b:e]
            print(chrs)
            e = b
            b = b - 2
            string += chr(chrs[0]) + chr(chrs[1])
        return int(string, 16)


    @classmethod
    def handleMessage(cls, str_, batteryEntity):
        # Accepts a list of hex-characters, and returns the human readable values into the batteryEntity object
        if batteryEntity == None or str_ == None or "" == str_:
            print("Empty buffer:", str_)
            return False
        print("test handleMessage ==", str_)
        # RevBuf2 = str_.getBytes()
        RevBuf2 = str_
        if len(RevBuf2) < 38:
            print("Buffer < 38")
            return False

        # print("Voltage", GetValue(RevBuf2, 0, 7))
        # print("Current", GetValue(RevBuf2, 8, 15))
        # print("Capacity", GetValue(RevBuf2, 16, 23))
        # print("Cycles", GetValue(RevBuf2, 24, 27))
        voltage = cls.GetValue(RevBuf2, 0, 7)
        current = cls.GetValue(RevBuf2, 8, 15)
        capacity = cls.GetValue(RevBuf2, 16, 23)
        cycles = cls.GetValue(RevBuf2, 24, 27)
        soc2 = cls.GetValue(RevBuf2, 28, 31)
        temperature = cls.GetValue(RevBuf2, 32, 35)
        status = cls.GetValue(RevBuf2, 36, 37)
        unknown = cls.GetValue(RevBuf2, 38, 39)
        afestatus = cls.GetValue(RevBuf2, 40, 41)



        # voltage = (((((cls.Asciitochar(RevBuf2[6], RevBuf2[7]) << 8) + cls.Asciitochar(RevBuf2[4], RevBuf2[5])) << 8) + cls.Asciitochar(RevBuf2[2], RevBuf2[3])) << 8) + cls.Asciitochar(RevBuf2[0], RevBuf2[1])
        # current = (((((cls.Asciitochar(RevBuf2[14], RevBuf2[15]) << 8) + cls.Asciitochar(RevBuf2[12], RevBuf2[13])) << 8) + cls.Asciitochar(RevBuf2[10], RevBuf2[11])) << 8) + cls.Asciitochar(RevBuf2[8], RevBuf2[9])
        # capacity = (((((cls.Asciitochar(RevBuf2[22], RevBuf2[23]) << 8) + cls.Asciitochar(RevBuf2[20], RevBuf2[21])) << 8) + cls.Asciitochar(RevBuf2[18], RevBuf2[19])) << 8) + cls.Asciitochar(RevBuf2[16], RevBuf2[17])
        # cycles = (cls.Asciitochar(RevBuf2[26], RevBuf2[27]) << 8) + cls.Asciitochar(RevBuf2[24], RevBuf2[25])
        # soc2 = (cls.Asciitochar(RevBuf2[30], RevBuf2[31]) << 8) + cls.Asciitochar(RevBuf2[28], RevBuf2[29])
        # temperature = (cls.Asciitochar(RevBuf2[34], RevBuf2[35]) << 8) + cls.Asciitochar(RevBuf2[32], RevBuf2[33])
        # status = cls.Asciitochar(RevBuf2[36], RevBuf2[37])
        print(cls.TAG + "status: ", str(status))
        print(cls.TAG + "unknown: ", str(unknown))
        # batteryEntity.setAfeStatus(cls.Asciitochar(RevBuf2[40], RevBuf2[41]))
        batteryEntity.setAfeStatus(afestatus)
        batteryEntity.setmVoltage(voltage)
        batteryEntity.setmCurrent(current)
        batteryEntity.setmSoc(soc2)
        if batteryEntity.getmCapacityOld1() <= 0:
            batteryEntity.setmCapacity(capacity)
        elif abs(capacity - batteryEntity.getmCapacityOld1()) < 10000:
            batteryEntity.setmCapacity(capacity)
        batteryEntity.setmCycles(cycles)
        batteryEntity.setmStatus(status)
        batteryEntity.setmTemperature(temperature)
        batteryEntity.setmBatteryType(len(str_))
        batteryEntity.setMsg(str_)
        print("test voltage==", voltage, "==current==", current, "==soc==", soc2, "==capacity==", capacity, "==cycles==", cycles, "==status==", status, "==temperature==", temperature, "==str.length()==", len(str_))
        return True



# class ReaderActivity(BleProfileServiceReadyActivity, ReaderService, UARTBinder, ReaderInterface, AdapterView, OnItemSelectedListener):
class ReaderActivity():
    cumulativeLog = ""
    tvBattCur = None
    tvBattTemp = None
    tvBattVolt = None
    tvBattSoC = None
    tvCapacity = None
    tvCycles = None
    tvState = None
    tvHealth = None
    batteryEntity = None
    mServiceBinder = None
    smartPowerUtil = None

    def __init__(self, device):
        self.batteryEntity = BatteryEntity(device)
        if self.smartPowerUtil is None:
            self.smartPowerUtil = SmartPowerUtil2()

    def send(self, text):
        if self.mServiceBinder != None:
            self.mServiceBinder.send(text)

    # mBroadcastReceiver = BroadcastReceiver()

    # def onReceive(self, context, intent):
        # action = intent.getAction()
        # device = intent.getParcelableExtra(ReaderService.EXTRA_DEVICE)
        # if ReaderService.BROADCAST_UART_RX == action:
            # data = intent.getByteArrayExtra(ReaderService.EXTRA_DATA)
            # setValueOn(device, data)

    def setValueOn(self, device, data):
        logging.debug("setValueOn starting with data {} from {}".format(data, device))
        retCmdData = self.smartPowerUtil.broadcastUpdate(data)
        logging.debug("SmartPowerUtil.broadcastUpdate done - running handleMessage on {}".format(retCmdData))
        if self.smartPowerUtil.handleMessage(retCmdData, self.batteryEntity):
            logCumulativeData = [None] * 8
            #  for 8 fields to save to log file
            #  Current A
            # self.tvBattCur.setText("{:.1f}".format([None] * ))
            self.tvBattCur = self.batteryEntity.getmCurrent() / 1000;
            logging.info("Current: {}".format(self.tvBattCur))

            self.tvBattVolt = self.batteryEntity.getmVoltage() / 1000;
            logging.info("Voltage: {}".format(self.tvBattVolt))

            self.tvBattTemp = (self.batteryEntity.getmTemperature() - 2731) / 10
            logging.info("Temperature: {}".format(self.tvBattTemp))

            self.tvBattSoC = self.batteryEntity.getmSoc()
            logging.info("SoC {}%".format(self.tvBattSoC))

            self.tvCapacity = self.batteryEntity.getmCapacity() / 1000.0
            logging.info("Capacity {}".format(self.tvCapacity))

            self.tvCycles = self.batteryEntity.getmCycles()
            logging.info("Cycles {}".format(self.tvCycles))

            #  Status
            if (float(self.batteryEntity.getmCurrent())) > 20.0:
                self.tvState = "Charging"
                logCumulativeData[6] = "Charging"
            elif (float(self.batteryEntity.getmCurrent())) < -20.0:
                self.tvState = "Discharging"
                logCumulativeData[6] = "Discharging"
            else:
                self.tvState = "Standby"
                logCumulativeData[6] = "Standby"
            logging.info("State {}".format(self.tvState))
            #  Health
            if (float(self.batteryEntity.getmCycles())) > 2000.0:
                self.tvHealth = "Good"
                logCumulativeData[7] = "Good"
            else:
                self.tvHealth = "Perfect"
                logCumulativeData[7] = "Perfect"
            logging.info("Health {}".format(self.tvHealth))
            # writeLogToFile(logCumulativeData)

    def clearCumulativeLog(self):
        self.cumulativeLog = ""

