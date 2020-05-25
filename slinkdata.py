#!/usr/bin/env python3

from __future__ import absolute_import
# from __future__ import print_function

import os
import sys
import blegatt
import time
from datetime import datetime

from slink_modbusdata import ModbusData

from datalogger import DataLogger

import logging
import duallog

class SLinkData(object):
    class BatteryParamInfo(object):
        READ_WORD = 7
        REG_ADDR = 256
        mBatteryTemperature = 20
        mCapacity = 0
        mDataIsCorrect = False
        mDeviceTemperature = -10
        mElectricity = 0.0
        mLoadElectricity = 0.0
        mLoadPower = 0
        mLoadVoltage = 0.0
        mVoltage = 0.0
        Byte_MAX_VALUE = 127

        def __init__(self, bs):
            self.mDataIsCorrect = ModbusData.DataCorrect(bs, 7)
            if self.mDataIsCorrect:
                self.mCapacity = SLinkData.Bytes2Int(bs, 3, 2)
                self.mVoltage = (float(SLinkData.Bytes2Int(bs, 5, 2))) * 0.1
                self.mElectricity = (float(SLinkData.Bytes2Int(bs, 7, 2))) * 0.01
                self.mDeviceTemperature = bs[9] & Byte_MAX_VALUE
                self.mBatteryTemperature = bs[10] & Byte_MAX_VALUE
                if (bs[9] & 128) != 0:
                    self.mDeviceTemperature = -self.mDeviceTemperature
                if (bs[10] & 128) != 0:
                    self.mBatteryTemperature = -self.mBatteryTemperature
                self.mLoadVoltage = (float(SLinkData.Bytes2Int(bs, 11, 2))) * 0.1
                self.mLoadElectricity = (float(SLinkData.Bytes2Int(bs, 13, 2))) * 0.01
                self.mLoadPower = SLinkData.Bytes2Int(bs, 15, 2)


    class HistoricalChartData(object):
        READ_WORD = 10
        REG_ADDR = 61440
        mDataIsCorrect = False
        mDayBatteryMaxVoltage = 0.0
        mDayBatteryMinVoltage = 0.0
        mDayChargeAmpHour = 0
        mDayChargeMaxPower = 0
        mDayConsumptionPower = 0
        mDayDischargeAmpHour = 0
        mDayDischargeMaxPower = 0
        mDayProductionPower = 0

        def __init__(self, bs):
            self.mDataIsCorrect = ModbusData.DataCorrect(bs, 10)
            if self.mDataIsCorrect:
                self.mDayBatteryMinVoltage = (float(SLinkData.Bytes2Int(bs, 3, 2))) * 0.1
                self.mDayBatteryMaxVoltage = (float(SLinkData.Bytes2Int(bs, 5, 2))) * 0.1
                self.mDayChargeMaxPower = SLinkData.Bytes2Int(bs, 11, 2)
                self.mDayDischargeMaxPower = SLinkData.Bytes2Int(bs, 13, 2)
                self.mDayChargeAmpHour = SLinkData.Bytes2Int(bs, 15, 2)
                self.mDayDischargeAmpHour = SLinkData.Bytes2Int(bs, 17, 2)
                self.mDayProductionPower = SLinkData.Bytes2Int(bs, 19, 2)
                self.mDayConsumptionPower = SLinkData.Bytes2Int(bs, 21, 2)

    class HistoricalData():
        READ_WORD = 21
        REG_ADDR = 267
        mAllConsumptionPower = 0
        mAllProductionPower = 0
        mAllRunDays = 0
        mBatteryAllDischargeTimes = 0
        mBatteryChargeAllApmHour = 0
        mBatteryDischargeAllApmHour = 0
        mDataIsCorrect = False
        mDayBatteryMaxVoltage = 0.0
        mDayBatteryMinVoltage = 0.0
        mDayChargeAmpHour = 0
        mDayChargeMaxPower = 0
        mDayConsumptionPower = 0
        mDayDischargeAmpHour = 0
        mDayDischargeMaxPower = 0
        mDayProductionPower = 0
        mbatteryChargeFullTimes = 0

        def __init__(self, bs):
            # super(HistoricalData, self).__init__()
            self.mDataIsCorrect = ModbusData.DataCorrect(bs, 21)
            if self.mDataIsCorrect:
                self.mDayBatteryMinVoltage = (float(SLinkData.Bytes2Int(bs, 3, 2))) * 0.1
                self.mDayBatteryMaxVoltage = (float(SLinkData.Bytes2Int(bs, 5, 2))) * 0.1
                self.mDayChargeMaxPower = SLinkData.Bytes2Int(bs, 11, 2)
                self.mDayDischargeMaxPower = SLinkData.Bytes2Int(bs, 13, 2)
                self.mDayChargeAmpHour = SLinkData.Bytes2Int(bs, 15, 2)
                self.mDayDischargeAmpHour = SLinkData.Bytes2Int(bs, 17, 2)
                self.mDayProductionPower = SLinkData.Bytes2Int(bs, 19, 2)
                self.mDayConsumptionPower = SLinkData.Bytes2Int(bs, 21, 2)
                self.mAllRunDays = SLinkData.Bytes2Int(bs, 23, 2)
                self.mBatteryAllDischargeTimes = SLinkData.Bytes2Int(bs, 25, 2)
                self.mbatteryChargeFullTimes = SLinkData.Bytes2Int(bs, 27, 2)
                self.mBatteryChargeAllApmHour = SLinkData.Bytes2Long(bs, 29, 4)
                self.mBatteryDischargeAllApmHour = SLinkData.Bytes2Long(bs, 33, 4)
                self.mAllProductionPower = SLinkData.Bytes2Long(bs, 37, 4)
                self.mAllConsumptionPower = SLinkData.Bytes2Long(bs, 41, 4)

        def SyncHistoricalChartData(self, data):
            self.mDayBatteryMinVoltage = data.mDayBatteryMinVoltage
            self.mDayBatteryMaxVoltage = data.mDayBatteryMaxVoltage
            self.mDayChargeMaxPower = data.mDayChargeMaxPower
            self.mDayDischargeMaxPower = data.mDayDischargeMaxPower
            self.mDayChargeAmpHour = data.mDayChargeAmpHour
            self.mDayDischargeAmpHour = data.mDayDischargeAmpHour
            self.mDayProductionPower = data.mDayProductionPower
            self.mDayConsumptionPower = data.mDayConsumptionPower

    class ParamSettingData(object):
        READ_WORD = 33
        REG_ADDR = 57345
        mData = [None] * 33
        mDataIsCorrect = False

        def __init__(self, bs):
            self.mDataIsCorrect = ModbusData.DataCorrect(bs, 33)
            if self.mDataIsCorrect:
                i = 0
                while i<len(self.mData):
                    self.mData[i] = SLinkData.Bytes2Int(bs, (i * 2) + 3, 2)
                    i += 1

    class SolarPanelAndBatteryState(object):
        READ_WORD = 3
        REG_ADDR = 288
        mBatteryState = 0
        mControllerInfo = 0
        mDataIsCorrect = False
        mSolarPanelState = 0

        def __init__(self, bs):
            self.mDataIsCorrect = ModbusData.DataCorrect(bs, 3)
            if self.mDataIsCorrect:
                self.mSolarPanelState = SLinkData.Bytes2Int(bs, 3, 1) >> 7
                self.mBatteryState = SLinkData.Bytes2Int(bs, 4, 1)
                if self.mBatteryState > 6:
                    self.mBatteryState = 0
                self.mControllerInfo = SLinkData.Bytes2Int(bs, 5, 4)

    class SolarPanelInfo(object):
        READ_WORD = 4
        REG_ADDR = 263
        mChargingPower = 0
        mDataIsCorrect = False
        mElectricity = 0.0
        mSwitch = 1
        mVoltage = 0.0

        def __init__(self, bs):
            self.mDataIsCorrect = ModbusData.DataCorrect(bs, 4)
            if self.mDataIsCorrect:
                self.mVoltage = (float(SLinkData.Bytes2Int(bs, 3, 2))) * 0.1
                self.mElectricity = (float(SLinkData.Bytes2Int(bs, 5, 2))) * 0.01
                self.mChargingPower = SLinkData.Bytes2Int(bs, 7, 2)
                self.mSwitch = SLinkData.Bytes2Int(bs, 9, 2)

    class SystemlVoltageApm(object):
        READ_WORD = 1
        REG_ADDR = 10
        mDataIsCorrect = False
        mElectricity = 0
        mVoltage = 0

        def __init__(self, bs):
            self.mDataIsCorrect = ModbusData.DataCorrect(bs, 1)
            if self.mDataIsCorrect:
                self.mVoltage = SLinkData.Bytes2Int(bs, 3, 1)
                self.mElectricity = SLinkData.Bytes2Int(bs, 4, 1)

    @classmethod
    def Bytes2Int(cls, bs, offset, length):
        ret = 0
        if len(bs) < (offset + len):
            return 0
        i = 0
        while i < length:
            ret |= (bs[offset + i] & 255) << (((length - i) - 1) * 8)
            i += 1
        return ret

    @classmethod
    def Bytes2Long(cls, bs, offset, length):
        ret = 0
        if len(bs) < (offset + length):
            return 0
        i = 0
        while i < length:
            ret |= long(((bs[offset + i] & 255) << (((length - i) - 1) * 8)))
            i += 1
        return ret

    @classmethod
    def Bytes2String(cls, bs, offset, length):
        temp_data = [None] * length
        ret = ""
        if len(bs) < (offset + length):
            return ret
        # System.arraycopy(bs, offset, temp_data, 0, length)
        temp_data = bs[offset:offset+length]
        return str(temp_data)

