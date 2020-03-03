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


class SmartPowerUtil():

    def __init__(self):
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
        logging.info("Test voltage == {}, current == {}, soc == {}, capacity == {}, cycles == {}, status == {}, temperature == {}, len = {}".format(voltage, current, soc2, capacity, cycles, status, temperature, len(message)))
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
            self.smartPowerUtil = SmartPowerUtil()

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

