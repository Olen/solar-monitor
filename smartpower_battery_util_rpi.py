#!/usr/bin/env python

from __future__ import print_function

class BatteryEntity(Parcelable):
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
    rssi = 0

    @overloaded
    def __init__(self, bluetoothDevice2, rssi2):
        super(BatteryEntity, self).__init__()
        self.bluetoothDevice = bluetoothDevice2
        self.rssi = rssi2

    # @__init__.register(object, BluetoothDevice)
    # def __init___0(self, bluetoothDevice2):
        # super(BatteryEntity, self).__init__()
        # self.bluetoothDevice = bluetoothDevice2
        # self.rssi = 0

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
        # dest.writeInt(self.rssi)
        # dest.writeInt(self.mBatteryType)
        # dest.writeString(self.msg)
        # dest.writeInt(self.mGetInfoStatus)
        # dest.writeInt(self.afeStatus)

    @__init__.register(object, Parcel)
    def __init___1(self, in_):
        super(BatteryEntity, self).__init__()
        self.bluetoothDevice = in_. (BluetoothDevice.__class__.getClassLoader())
        self.mCurrent = in_.readInt()
        self.mVoltage = in_.readInt()
        self.mCapacity = in_.readInt()
        self.mCycles = in_.readInt()
        self.mStatus = in_.readInt()
        self.mSoc = in_.readInt()
        self.mTemperature = in_.readInt()
        self.rssi = in_.readInt()
        self.mBatteryType = in_.readInt()
        self.msg = in_.readString()
        self.mGetInfoStatus = in_.readInt()
        self.afeStatus = in_.readInt()


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

    @classmethod
    def broadcastUpdate(cls, data):
        cmdData = ""
        if data != None and len(data):
            i = 0
            while len(data):
                if cls.Revindex > 121:
                    cls.Revindex = 0
                    cls.end = 0
                    cls.RecvDataType = cls.SOI
                if cls.RecvDataType == 1:
                    if (data[i] & 255) != 146:
                    else:
                        cls.RecvDataType = cls.INFO
                        bArr = cls.RevBuf
                        i2 = cls.Revindex
                        cls.Revindex = i2 + 1
                        bArr[i2] = data[i]
                elif cls.RecvDataType == 2:
                    bArr2 = cls.RevBuf
                    i3 = cls.Revindex
                    cls.Revindex = i3 + 1
                    bArr2[i3] = data[i]
                    if data[i] == 12:
                        if cls.end < 110:
                            cls.end = cls.Revindex
                        if cls.Revindex != 121 and cls.Revindex != 66 and cls.Revindex != 88:
                        else:
                            cls.RecvDataType = cls.EOI
                    else:
                elif cls.RecvDataType == 3:
                    Chksum = 0
                    cls.end = 114
                    j = 1
                    while j < cls.end - 5:
                        Chksum = int((Asciitochar(cls.RevBuf[j], cls.RevBuf[j + 1]) + Chksum))
                        j += 2
                    i1 = 0
                    while len(RevBuf):
                        print("test broadcastUpdate==" + i1 + ":" + cls.RevBuf[i1])
                        i1 += 1
                    print(cls.TAG + "broadcastUpdate: Chksum==" + Chksum)
                    print(cls.TAG + "broadcastUpdate: " + (((int(Asciitochar(cls.RevBuf[cls.end - 5], cls.RevBuf[cls.end - 4]))) << 8) + (int(Asciitochar(cls.RevBuf[cls.end - 3], cls.RevBuf[cls.end - 2])))))
                    print(cls.TAG + "broadcastUpdate: end==" + cls.end)
                    if Chksum == ((int(Asciitochar(cls.RevBuf[cls.end - 5], cls.RevBuf[cls.end - 4]))) << 8) + (int(Asciitochar(cls.RevBuf[cls.end - 3], cls.RevBuf[cls.end - 2]))):
                        cmdData = str(cls.RevBuf, 1, cls.Revindex)
                        cls.Status = Asciitochar(cls.RevBuf[37], cls.RevBuf[38])
                        cls.soc = Asciitochar(cls.RevBuf[31], cls.RevBuf[32])
                        cls.soc <<= 8
                        cls.soc += Asciitochar(cls.RevBuf[29], cls.RevBuf[30])
                        cls.Current = Asciitochar(cls.RevBuf[15], cls.RevBuf[16])
                        cls.Current <<= 8
                        cls.Current += Asciitochar(cls.RevBuf[13], cls.RevBuf[14])
                        cls.Current <<= 8
                        cls.Current += Asciitochar(cls.RevBuf[11], cls.RevBuf[12])
                        cls.Current <<= 8
                        cls.Current += Asciitochar(cls.RevBuf[9], cls.RevBuf[10])
                    cls.Revindex = 0
                    cls.end = 0
                    cls.RecvDataType = cls.SOI
                i += 1
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
    def handleMessage(cls, str_, batteryEntity):
        if batteryEntity == None or str_ == None or "" == str_:
            return False
        print("test handleMessage==" + str_)
        RevBuf2 = str_.getBytes()
        if len(RevBuf2):
            return False
        voltage = (((((cls.Asciitochar(RevBuf2[6], RevBuf2[7]) << 8) + cls.Asciitochar(RevBuf2[4], RevBuf2[5])) << 8) + cls.Asciitochar(RevBuf2[2], RevBuf2[3])) << 8) + cls.Asciitochar(RevBuf2[0], RevBuf2[1])
        current = (((((cls.Asciitochar(RevBuf2[14], RevBuf2[15]) << 8) + cls.Asciitochar(RevBuf2[12], RevBuf2[13])) << 8) + cls.Asciitochar(RevBuf2[10], RevBuf2[11])) << 8) + cls.Asciitochar(RevBuf2[8], RevBuf2[9])
        capacity = (((((cls.Asciitochar(RevBuf2[22], RevBuf2[23]) << 8) + cls.Asciitochar(RevBuf2[20], RevBuf2[21])) << 8) + cls.Asciitochar(RevBuf2[18], RevBuf2[19])) << 8) + cls.Asciitochar(RevBuf2[16], RevBuf2[17])
        cycles = (cls.Asciitochar(RevBuf2[26], RevBuf2[27]) << 8) + cls.Asciitochar(RevBuf2[24], RevBuf2[25])
        soc2 = (cls.Asciitochar(RevBuf2[30], RevBuf2[31]) << 8) + cls.Asciitochar(RevBuf2[28], RevBuf2[29])
        temperature = (cls.Asciitochar(RevBuf2[34], RevBuf2[35]) << 8) + cls.Asciitochar(RevBuf2[32], RevBuf2[33])
        status = cls.Asciitochar(RevBuf2[36], RevBuf2[37])
        print(cls.TAG + "status: " + str(status))
        batteryEntity.setAfeStatus(cls.Asciitochar(RevBuf2[40], RevBuf2[41]))
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
        print("test voltage==" + voltage + "==current==" + current + "==soc==" + soc2 + "==capacity==" + capacity + "==cycles==" + cycles + "==status==" + status + "==temperature==" + temperature + "==str.length()==" + len(str_))
        return True



class ReaderActivity(BleProfileServiceReadyActivity, ReaderService, UARTBinder, ReaderInterface, AdapterView, OnItemSelectedListener):
    TAG = "ReaderActivity"
    cumulativeLog = ""
    mConnectButton = None
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

    def onStart(self):
        intent = getIntent()
        if not isDeviceConnected() and intent.hasExtra(MainActivity.EXTRA_ADDRESS):
            bluetoothAdapter = BluetoothAdapter.getDefaultAdapter()
            value = intent.getStringExtra(MainActivity.EXTRA_ADDRESS)
            print(self.TAG + "onStart : device value=" + value)
            device = bluetoothAdapter.getRemoteDevice(value)
            #  BluetoothDevice String
            name = intent.getStringExtra(MainActivity.EXTRA_NAME)
            onDeviceSelected(device, device.__name__)
            print(self.TAG + "onStart : device=" + device + "  getName =" + device.__name__ + " name= " + name)
            intent.removeExtra(MainActivity.EXTRA_NAME)
            intent.removeExtra(MainActivity.EXTRA_ADDRESS)
            self.batteryEntity = BatteryEntity(device)

    def onDeviceSelected(self, device, name):
        #  The super method starts the service
        super(ReaderActivity, self).onDeviceSelected(device, name)

    def getDefaultDeviceName(self):
        return R.string.template_default_name

    def getAboutTextId(self):
        return R.string.uart_about_text

    def send(self, text):
        if self.mServiceBinder != None:
            self.mServiceBinder.send(text)

    def onActivityResult(self, requestCode, resultCode, data):
        super(ReaderActivity, self).onActivityResult(requestCode, resultCode, data)
        if resultCode == Activity.RESULT_CANCELED:
            return

    mBroadcastReceiver = BroadcastReceiver()

    def onReceive(self, context, intent):
        action = intent.getAction()
        device = intent.getParcelableExtra(ReaderService.EXTRA_DEVICE)
        if ReaderService.BROADCAST_UART_RX == action:
            data = intent.getByteArrayExtra(ReaderService.EXTRA_DATA)
            setValueOnView(device, data)

    def setValueOnView(self, device, data):
        if SmartPowerUtil.handleMessage(SmartPowerUtil.broadcastUpdate(self, data), self.batteryEntity):
            logCumulativeData = [None] * 8
            #  for 8 fields to save to log file
            #  Current A 
            self.tvBattCur.setText("{:.1f}".format([None] * ))
            logCumulativeData[0] = "{:.1f}".format([None] * )
            if abs(float(self.batteryEntity.getmCurrent())) <= 20.0:
                self.tvBattCur.setText("0.0")
                logCumulativeData[0] = "0.0"
            elif abs(float(self.batteryEntity.getmCurrent())) > 200000.0:
                if self.batteryEntity.getmCurrent() > 600000:
                    self.tvBattCur.setText("600.0")
                    logCumulativeData[0] = "600.0"
                elif self.batteryEntity.getmCurrent() < -600000:
                    self.tvBattCur.setText("-600.0")
                    logCumulativeData[0] = "-600.0"
            #  Temperature deg C 
            if (float((self.batteryEntity.getmTemperature() - 2731))) / 10.0 >= -40.0:
                self.tvBattTemp.setText("{:.1f}".format([None] * ))
                logCumulativeData[1] = "{:.1f}".format([None] * )
            elif self.batteryEntity.getmTemperature() == 0:
                self.tvBattTemp.setText("null")
                logCumulativeData[1] = "null"
            else:
                self.tvBattTemp.setText("-40")
                logCumulativeData[1] = "-40"
            #  Voltage V 
            self.tvBattVolt.setText("{:.1f}".format([None] * ))
            logCumulativeData[2] = "{:.1f}".format([None] * )
            #  State of charge SoC 
            self.tvBattSoC.setText(Integer.toString(self.batteryEntity.getmSoc()))
            logCumulativeData[3] = Integer.toString(self.batteryEntity.getmSoc())
            #  Capacity Ah 
            self.tvCapacity.setText("{:.1f}".format([None] * ))
            logCumulativeData[4] = "{:.1f}".format([None] * )
            #  Charge Cycles 
            self.tvCycles.setText(Integer.toString(self.batteryEntity.getmCycles()))
            logCumulativeData[5] = Integer.toString(self.batteryEntity.getmCycles())
            #  Status 
            if (float(self.batteryEntity.getmCurrent())) > 20.0:
                self.tvState.setText(getString(R.string.Status_Charging))
                logCumulativeData[6] = getString(R.string.Status_Charging)
            elif (float(self.batteryEntity.getmCurrent())) < -20.0:
                self.tvState.setText(getString(R.string.Status_Discharging))
                logCumulativeData[6] = getString(R.string.Status_Discharging)
            else:
                self.tvState.setText(getString(R.string.Status_Standby))
                logCumulativeData[6] = getString(R.string.Status_Standby)
            #  Health 
            if (float(self.batteryEntity.getmCycles())) > 2000.0:
                self.tvHealth.setText(getString(R.string.Health_Good))
                logCumulativeData[7] = getString(R.string.Health_Good)
            else:
                self.tvHealth.setText(getString(R.string.Health_Perfect))
                logCumulativeData[7] = getString(R.string.Health_Perfect)
            writeLogToFile(logCumulativeData)

    def clearCumulativeLog(self):
        self.cumulativeLog = ""


