#!/usr/bin/env python3

from __future__ import absolute_import
# from __future__ import print_function

import os
import sys
import blegatt
import time
from datetime import datetime

from slinkdata import SLinkData
from slink_checksumcrc import ChecksumCRC
from slink_modbusdata import ModbusData
from slink_maincommon import MainCommon

from datalogger import DataLogger

import logging
import duallog


class SLinkRealTimeMonitor():
    TAG = "SLinkRealTimeMonitor"
    mDelayTimes = 10
    mExit = False
    mLoadOptMod = 0
    mLoadSwitchStatusSB = None
    # mMessageHandler = Handler()
    loadToggleSwitchOn = True

#  Base class

    mClearFifo = True
    mDeviceId = -1
    mFragmentType = -1
    mHandler = None
    mIsActive = False
    mReadingCount = 1
    mReadingRegId = 0
    mRefreshThreadRuning = False
    mUartRecvData = []
    mUartRecvFifo = []
    progressDialog = None
    mTimerout = 2000

    def __init__(self, timeout, device = None):
        # super(self).__init__()
        self.mTimerout = timeout
        self.mIsActive = True
        self.MainCommon = MainCommon(device)
        self.SendUartData = self.MainCommon.SendUartData

    def setDeviceId(self, id):
        self.mDeviceId = id

    def SetHandler(self, handler):
        self.mHandler = handler

    class Message:
        arg1 = None
        obj = None
        def __init__(self, arg, obj1):
            self.arg1 = arg
            self.obj = obj1

    def BasePostRecvMessage(self):
        if self.mUartRecvFifo == None:
            return False
        # self.mUartRecvData = None
        self.mUartRecvData = [None] * len(self.mUartRecvFifo)
        # System.arraycopy(self.mUartRecvFifo, 0, self.mUartRecvData, 0, self.mUartRecvFifo.length)
        self.mUartRecvData = self.mUartRecvFifo[:]
        if self.mUartRecvData == None or not ModbusData.DataCrcCorrect(self.mUartRecvData):
            logging.debug(self.TAG + str(self.mUartRecvData) + " - DataCrcCorrect failed!")
            return False
        logging.debug(self.TAG + self + "DataCrcCorrect success!")
        return True

    def OnRecvMessage(self, bs):
        if bs != None and len(bs) != 0:
            if self.mClearFifo or self.mUartRecvFifo == None:
                self.mUartRecvFifo = bs
                self.mClearFifo = False
            else:
                # System.arraycopy(self.mUartRecvFifo, 0, temp_data, 0, self.mUartRecvFifo.length)
                # temp_data = self.mUartRecvFifo[0:self.mUartRecvFifo.length()]
                temp_data = self.mUartRecvFifo[:]
                # System.arraycopy(bs, 0, temp_data, self.mUartRecvFifo.length, bs.length)
                temp_data[len(self.mUartRecvFifo)+1:] = bs[:]
                self.mUartRecvFifo = temp_data
            msg = "main recv data"
            for valueOf in bs:
            # for valueOf in self.mUartRecvFifo:
                msg = str(msg) + str("[{:02x}] ".format(valueOf))
            self.SendUartString(str(msg)+("\r\n"))
            logging.debug(self.TAG + msg)

            # retb = BasePostRecvMessage()
            retb = PostRecvMessage()
            if retb:
                self.mClearFifo = True

    def WaitPostMessage(self, timerout):
        timerout2 = timerout / 10
        while True:
            # if self.BasePostRecvMessage():
                # break
            if self.PostRecvMessage():
                break
            timerout3 = timerout2 - 1
            if timerout2 == 0:
                timerout2 = timerout3
                break
            else:
                i = timerout3
                time.sleep(0.01)
                timerout2 = timerout3
                return False
        logging.debug(self.TAG + self + "timerout:" + timerout2)
        if timerout2 <= 0:
            return False
        return True

#  // Base class

    def LoadSwitchOnClick(self):
        if loadToggleSwitchOn :
            self.MainCommon.SendUartData(ModbusData.BuildWriteRegCmd(self.mDeviceId, 266, 1))
        else :
            self.MainCommon.SendUartData(ModbusData.BuildWriteRegCmd(self.mDeviceId, 266, 0))


    def mMessageHandler(self, msg):
        bs = int(msg.obj)
        # if msg.arg1 == 256:
        if msg.arg1 == BatteryParamInfo.REG_ADDR:
            self.UpdateBatteryParamInfo(bs)
            return
        elif msg.arg1 == SLinkData.SolarPanelInfo.REG_ADDR:
            self.UpdateSolarPanelInfo(bs)
            return
        elif msg.arg1 == SLinkData.SolarPanelAndBatteryState.REG_ADDR:
            self.UpdateSolarPanelAndBatteryState(bs)
            return
        elif msg.arg1 == SLinkData.ParamSettingData.REG_ADDR:
            self.UpdateParamSettingData(bs)
            return
        else:
            return


    def RefreshThread(self):
        if not self.mRefreshThreadRuning:
            self.mRefreshThreadRuning = True
            times = 0
            while not self.mExit:
                self.mClearFifo = True
                time.sleep(0.1)
                self.mReadingRegId = 256
                self.mReadingCount = 7
                self.SendUartData(ModbusData.BuildReadRegsCmd(self.mDeviceId, self.mReadingRegId, self.mReadingCount))
                time.sleep(0.2)
                self.WaitPostMessage(1000)
                if self.mExit:
                    break
                self.mClearFifo = True
                self.mReadingRegId = SLinkData.SolarPanelInfo.REG_ADDR
                self.mReadingCount = 4
                self.SendUartData(ModbusData.BuildReadRegsCmd(self.mDeviceId, self.mReadingRegId, self.mReadingCount))
                time.sleep(0.2)
                self.WaitPostMessage(1000)
                if self.mExit:
                    break
                self.mClearFifo = True
                self.mReadingRegId = SLinkData.SolarPanelAndBatteryState.REG_ADDR
                self.mReadingCount = 3
                self.SendUartData(ModbusData.BuildReadRegsCmd(self.mDeviceId, self.mReadingRegId, self.mReadingCount))
                time.sleep(0.2)
                self.WaitPostMessage(1000)
                self.mClearFifo = True
                self.mReadingRegId = SLinkData.ParamSettingData.REG_ADDR
                self.mReadingCount = 33
                self.SendUartData(ModbusData.BuildReadRegsCmd(self.mDeviceId, self.mReadingRegId, self.mReadingCount))
                time.sleep(0.2)
                self.WaitPostMessage(5000)
                if self.mExit:
                    break
                times += 1
                if times % 2 == 0:
                    while True:
                        realTimeMonitoringFragment = self
                        access4 = realTimeMonitoringFragment.mDelayTimes
                        realTimeMonitoringFragment.mDelayTimes = access4 - 1
                        if access4 <= 0:
                            break
                        time.sleep(1.0)
                    self.mDelayTimes = 10
            logging.debug(self.TAG + "exit thread")
            self.mExit = True
            self.mRefreshThreadRuning = False

    def PostRecvMessage(self):
        if not self.BasePostRecvMessage():
            return False
        bs = self.mUartRecvData
        logging.debug(self.TAG + "PostRecvMessage")
        msg = "recv data"
        for valueOf in bs:
            # msg = StringBuilder(str(msg)).append("[{:02x}] ".format([None] * )).__str__()
            msg = str(msg) + "[{:02x}] ".format(valueOf)
        logging.debug(self.TAG + msg)
        if self.mReadingCount * 2 != (bs[2] & 255) or len(bs) < 3:
            return False
        message = Message()
        message.arg1 = self.mReadingRegId
        message.obj = bs
        # self.mMessageHandler.sendMessage(message)
        self.mMessageHandler(message)
        self.mReadingRegId = 0
        return True

    def UpdateSolarPanelAndBatteryState(self, bs):
        z = True
        state = SLinkData.SolarPanelAndBatteryState(bs)
        # logging.debug([None] * [state.mBatteryState])
        tv_charging_state_value = ["val00h: Charging is not turned on", "val01h: Start charging", "val02h: MPPT charge mode", "val03h: Balanced charging mode", "val04h: Boost charge mode", "val05h: Floating charge mode", "val06h: Constant Current mode"]
        logging.debug(tv_charging_state_value[state.mBatteryState])
        battery_plate_sate_str = ["Battery over discharged", "Battery high volt", "Batt under-volt alert", "Load short circuit", "Load over current", "Device over-heating", "Ambient (external) temp over limit", "Over-limit PV input", "PV input short circt", "PV input over-volt", "PV reverse current", "PV work volt over limit", "PV reverse connection", "Anti-reverse MOS short", "circuit, charge MOS short circuit", "Normal"]
        controllerInfoStr = "Normal"
        batteryStateInfoStr = "Normal"
        loadState = "Open"
        if state.mSolarPanelState == 0:
            loadState = "Closed"
        if state.mControllerInfo != 0:
            i = 0
            while len(battery_plate_sate_str):
                if i < 7 or i > 14:
                    if i < 0 or i > 2:
                        if i == 3 or i == 4:
                            if (state.mControllerInfo & 8) != 0:
                                loadState = battery_plate_sate_str[3]
                            elif (state.mControllerInfo & (1 << i)) != 0:
                                loadState = battery_plate_sate_str[i]
                    elif (state.mControllerInfo & (1 << i)) != 0:
                        batteryStateInfoStr = battery_plate_sate_str[i]
                elif (state.mControllerInfo & (1 << i)) != 0:
                    controllerInfoStr = battery_plate_sate_str[i]
                i += 1
        logging.debug(batteryStateInfoStr)
        logging.debug(controllerInfoStr)
        logging.debug(loadState)
        switchButton = self.mLoadSwitchStatusSB
        if state.mSolarPanelState != 1:
            z = False
        switchButton.setChecked(z)

    def UpdateParamSettingData(self, bs):
        self.mLoadOptMod = SLinkData.ParamSettingData(bs).mData[28]
        logging.debug(self.TAG + "mLoadOptMod:" + self.mLoadOptMod)
        if self.mLoadOptMod == 15:
            self.mLoadSwitchStatusSB.setEnabled(True)
        else:
            self.mLoadSwitchStatusSB.setEnabled(False)

    def UpdateSolarPanelInfo(self, bs):
        spinfo = SLinkData.SolarPanelInfo(bs)
        logging.debug("{0:.1f}V".format(spinfo.mVoltage))
        logging.debug("{0:.2f}A".format(spinfo.mElectricity))
        logging.debug(spinfo.mChargingPower + "W")

    def UpdateBatteryParamInfo(self, bs):
        bec = BatteryParamInfo(bs)
        logging.debug(str(bec.mCapacity) + "%")
        # logging.debug(StringBuilder(str((float(round(bec.mVoltage * 100.0))) / 100.0)).append("V").__str__())
        logging.debug(str((float(round(bec.mVoltage * 100.0))) / 100.0) +" V " )
        logging.debug("{0:.2f}A".format(bec.mElectricity))
        logging.debug(bec.mBatteryTemperature + " deg C ")
        # logging.debug(StringBuilder(str((float(round(bec.mLoadVoltage * 100.0))) / 100.0)).append("V").__str__())
        logging.debug(str((float(round(bec.mLoadVoltage * 100.0))) / 100.0) +" V ")
        logging.debug("{0:.2f}A".format(bec.mLoadElectricity))
        logging.debug(bec.mLoadPower + "W")
