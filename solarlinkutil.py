import logging                                                     
import libscrc





class SolarLinkUtil():
    def __init__(self, device_type, power_device):                  
        self.DeviceType = device_type     
        self.PowerDevice = power_device                  
        self.function_READ = 3
        self.function_WRITE = 6


        self.param_buffer = b""
        self.param_expect = 0
        self.param_data = []
        self.poll_loop_count = 0
        self.poll_data = None

    def pollerUpdate(self, register, value):
        '''
        Fortunately we read a different number of bytes from each register, so we can 
        abuse the "length" field (byte #3 in the response) as an "id"
        '''
        logging.debug("REG: {} VAL: {}".format(register, value))
        if not self.Validate(value):
            logging.warning("PollerUpdate - Invalid data: {}".format(value))
            return False

        if value[0] == self.PowerDevice.device_id and value[1] == self.function_READ:
            # This is the first packet in a read-response
            if value[2] == self.BatteryParamInfo.READ_WORD * 2:
                self.updateBatteryParamInfo(value)
            if value[2] == self.SolarPanelAndBatteryState.READ_WORD * 2:
                self.updateSolarPanelAndBatteryState(value)
            if value[2] == self.SolarPanelInfo.READ_WORD * 2:
                self.updateSolarPanelInfo(value)
            if value[2] == self.ParamSettingData.READ_WORD * 2:
                self.updateParamSettingData(value)

        elif value[0] == self.PowerDevice.device_id and value[1] == self.function_WRITE:
            # This is the first packet in a write-response
            # Ignore for now
            pass
        elif value[0] != self.PowerDevice.device_id and len(self.param_buffer) < self.param_expect:
            # Lets assume this is a follow up packet 
            self.updateParamSettingData(value)
        else:
            logging.warning("Unknown packet received: {}".format(value))
            return False

        return True


    def buildRequest(self, function, start, data):
        device_id = self.PowerDevice.device_id
        bytes = []
        bytes.append(device_id)
        bytes.append(function)
        bytes.append(self.Int2Bytes(start, 0))
        bytes.append(self.Int2Bytes(start, 1))
        bytes.append(self.Int2Bytes(data, 0))
        bytes.append(self.Int2Bytes(data, 1))

        crc = libscrc.modbus(bytearray(bytes))
        bytes.append(self.Int2Bytes(crc, 1))
        bytes.append(self.Int2Bytes(crc, 0))
        logging.debug("{} {}".format("BuildRequest", bytes))
        return bytes




    '''

# >>> format(32145, '016b')[:8]
'01111101'
# >>> format(32145, '016b')[8:]
'10010001'



Start -> 16 bit nummer

7     = 0000000000000111
65280 = 1111111100000000

7 & 65280 = 0

7     => 00000000, 00000111
32145 => 01111101, 10010001



32145 = 0111110110010001
65280 = 1111111100000000
        0111110100000000
32145 & 65280 = 01111101 = 125





>> 8 == /256


    def BuildRequestBasis(self, function_, dev_addr):
    function == 3 -> READ
    function == 6 -> WRITE

BatteryParamInfo VAL: b'\xff\x03\x0e\x00]\x00\x83\x00\x00\x15\x14\x00\x00\x00\x00\x00\x00/\xec'

        elif register == 'BatteryParamInfo':
        READ_WORD = 7
        REG_ADDR = 256

            ReadingRegId = SLinkData.BatteryParamInfo.REG_ADDR
            ReadingCount = SLinkData.BatteryParamInfo.READ_WORD

                @classmethod
    def DataCrcCorrect(cls, bs):
        logging.debug("{} {}".format("DataCrcCorrect", bs))
        if bs == None or len(bs)<2:
            return False
        crc = ChecksumCRC.calcCrc16(bs, 0, (len(bs) - 2))
        # crc = libscrc.modbus(bytearray(bytes))
        crc_cmp = (bs[len(bs) - 2] & 255) | ((bs[len(bs) - 1] & 255) << 8)
        logging.debug(" " + "crc:" + crc + ",crc_cmp:" + crc_cmp)
        if crc == crc_cmp:
            return True
        return False

    @classmethod
    def DataCorrect(cls, bs, word):
        if bs == None or len(bs) < 5:
            return False
        crc_ok = cls.DataCrcCorrect(bs)
        if (bs[2] & 255) != word * 2 or not crc_ok:
            return False
        return True

    '''

    class BatteryParamInfo():
        REG_ADDR  = 256
        READ_WORD = 7
        RESP_ID   = 14
    class SolarPanelAndBatteryState():
        REG_ADDR  = 288
        READ_WORD = 3
        RESP_ID   = 6
    class SolarPanelInfo():
        REG_ADDR  = 263
        READ_WORD = 4
        RESP_ID   = 8
    class ParamSettingData():
        REG_ADDR = 57345
        READ_WORD = 33
        RESP_ID   = 66


    class RegulatorPower():
        REG_ADDR = 266
        on       = 1
        off      = 0



    def updateBatteryParamInfo(self, bs):
        logging.debug("mSOC {} {} => {} %".format(int(bs[3]), int(bs[4]), self.Bytes2Int(bs, 3, 2)))
        self.PowerDevice.soc = self.Bytes2Int(bs, 3, 2)
        logging.debug("mVoltage {} {} => {} V".format(int(bs[5]), int(bs[6]), self.Bytes2Int(bs, 5, 2) * 0.1))
        self.PowerDevice.charge_voltage = self.Bytes2Int(bs, 5, 2) * 0.1
        logging.debug("mElectricity {} {} => {} A".format(int(bs[7]), int(bs[8]), self.Bytes2Int(bs, 7, 2) * 0.01))
        self.PowerDevice.charge_current = self.Bytes2Int(bs, 7, 2) * 0.01
        logging.debug("mDeviceTemperature {}".format(int(bs[9])))
        self.PowerDevice.temperature_celsius = self.Bytes2Int(bs, 9, 1)
        logging.debug("mBatteryTemperature {}".format(int(bs[10])))
        logging.debug("mLoadVoltage {} {} => {} V".format(int(bs[11]), int(bs[12]), self.Bytes2Int(bs, 11, 2) * 0.1))
        self.PowerDevice.voltage = self.Bytes2Int(bs, 11, 2) * 0.1
        logging.debug("mLoadElectricity {} {} => {} A".format(int(bs[13]), int(bs[14]), self.Bytes2Int(bs, 13, 2) * 0.01))
        self.PowerDevice.current = self.Bytes2Int(bs, 13, 2) * 0.01
        logging.debug("mLoadPower {} {} => {} W".format(int(bs[15]), int(bs[16]), self.Bytes2Int(bs, 15, 2)))
        self.PowerDevice.power = self.Bytes2Int(bs, 15, 2)
        return



    def updateSolarPanelAndBatteryState(self, bs):
        logging.debug("mSolarPanelState {} => {}".format(int(bs[3]), self.Bytes2Int(bs, 3, 1) >> 7))
        logging.debug("mBatteryState {} => {}".format(int(bs[4]), self.Bytes2Int(bs, 4, 1)))
        logging.debug("mControllerInfo {} {} {} {} => {}".format(int(bs[5]), int(bs[6]), int(bs[7]), int(bs[8]), self.Bytes2Int(bs, 5, 4)))
        return

    def updateSolarPanelInfo(self, bs):
        logging.debug("mVoltage {} {} => {}".format(int(bs[3]), int(bs[4]), self.Bytes2Int(bs, 3, 2) * 0.1))
        self.PowerDevice.input_voltage = self.Bytes2Int(bs, 3, 2) * 0.1
        logging.debug("mElectricity {} {} => {}".format(int(bs[5]), int(bs[6]), self.Bytes2Int(bs, 5, 2) * 0.01))
        self.PowerDevice.input_current = self.Bytes2Int(bs, 5, 2) * 0.01
        logging.debug("mChargingPower {} {} => {}".format(int(bs[7]), int(bs[8]), self.Bytes2Int(bs, 7, 2)))
        self.PowerDevice.input_power = self.Bytes2Int(bs, 7, 2)
        logging.debug("mSwitch {} {} => {}".format(int(bs[9]), int(bs[10]), self.Bytes2Int(bs, 9, 2)))
        self.PowerDevice.power_switch_state = self.Bytes2Int(bs, 9, 2)
        logging.debug("mUnkown {} {} => {}".format(int(bs[11]), int(bs[12]), self.Bytes2Int(bs, 11, 2)))


    def updateParamSettingData(self, bs):
        i = 0
        header = 3
        checksum = 2
        if bs[0] == 255 and bs[1] == 3:
            i = 3
            self.param_data = []
            self.param_buffer = b""
            self.param_expect = bs[2]
        self.param_buffer = self.param_buffer + bs[i:]
        logging.debug("Param-buffer ({}): {}".format(len(self.param_buffer), self.param_buffer))

        if len(self.param_buffer) == self.param_expect + header + checksum:
            while i < 66:
                self.param_data.append(int.from_bytes(self.param_buffer[i:i+2], byteorder='big'))
                i = i + 2
        logging.debug("ParamSettingData: {}".format(self.param_data))
        '''
        i = 0
        while i<len(bs) / 2:
            self.mData.append(self.Bytes2Int(bs, (i * 2) + adder, 2))
            logging.debug("BS len: {} - reading from byte {} to byte {}".format(len(bs), (i * 2) + adder, (i * 2) + adder + 1))

            i += 1
        if len(self.mData) >= 28:
            mLoadOptMod = self.mData[28]
            logging.debug("mLoadOptMod: {}".format(mLoadOptMod))
            if mLoadOptMod == 15:
                logging.debug("Switch on")
            else:
                logging.debug("Switch off")
        '''



    def Bytes2Int(self, bs, offset, length):
        # Reads data from a list of bytes, and converts to an int
        # Bytes2Int(bs, 3, 2)
        ret = 0
        if len(bs) < (offset + length):
            return ret
        if length > 0:
            # offset = 11, length = 2 => 11 - 12
            byteorder='big'
            start = offset
            end = offset + length
        else:
            # offset = 11, length = -2 => 10 - 11
            byteorder='little'
            start = offset + length + 1
            end = offset + 1
        # logging.debug("Reading byte {} to {} of string {}".format(start, end, bs))
        # Easier to read than the bitshifting below
        return int.from_bytes(bs[start:end], byteorder=byteorder)

        i = 0
        s = offset + length - 1
        while s >= offset:
            # logging.debug("Reading from bs {} pos {}".format(bs, s))
            # logging.debug("Value {}".format(bs[s]))
            # Start at the back, and read each byte, multiply with 256 i times for each new byte
            if i == 0:
                ret = bs[s]
            else:
                ret = ret + bs[s] * (256 * i)
            i = i + 1
            s = s - 1
        return ret
        '''


        ret = 0
        i = 0
        while i < length:
            ret |= (bs[offset + i] & 255) << (((length - i) - 1) * 8)
            i += 1
        return ret
        '''

    def Int2Bytes(self, i, pos = 0):
        # Converts an integer into 2 bytes (16 bits)
        # Returns either the first or second byte as an int
        if pos == 0:
            return int(format(i, '016b')[:8], 2)
        if pos == 1:
            return int(format(i, '016b')[8:], 2)
        return 0

    def Validate(self, bs):
        header = 3
        checksum = 2
        if bs == None or len(bs) < header + checksum:
            logging.warning("Invalid BS {}".format(bs))
            return False

        
        function = bs[1]
        if function == 6:
            # Response to write-function.  Ignore
            return True
        length = bs[2]
        if len(bs) - (header + checksum) != int(length):
            logging.warning("Invalid BS (wrong length) {}".format(bs))
            return False


        crc = libscrc.modbus(bytearray(bs[:-2]))
        check = self.Bytes2Int(bs, offset=len(bs)-1, length=-2)
        if crc == check:
            return True
        logging.warning("CRC Failed: {} - Check: {}".format(crc, check))
        return False

    def ackData(self, value):
        return bytearray("main recv da ta[{0:02x}] [".format(value[0]), "ascii")

    def pollData(self, force = None):
        data = None
        if force is not None:
            return self.do_poll(force)

        self.poll_loop_count = self.poll_loop_count + 1
        if self.poll_loop_count == 1:
            data = self.do_poll('BatteryParamInfo')
        if self.poll_loop_count == 3:
            data = self.do_poll('SolarPanelInfo')
        # if self.poll_loop_count == 5:
        #     self.do_poll('SolarPanelAndBatteryState')
        # if self.poll_loop_count == 7:
        #     self.do_poll('ParamSettingData')
        if self.poll_loop_count == 10:
            data = self.poll_loop_count = 0
        return data

    def do_poll(self, cmd):                             
        data = None                                
        function = self.function_READ                          
        if cmd == 'SolarPanelAndBatteryState':                    
            regAddr = self.SolarPanelAndBatteryState.REG_ADDR                   
            readWrd = self.SolarPanelAndBatteryState.READ_WORD
        elif cmd == 'BatteryParamInfo':                                                                                                                      
            regAddr = self.BatteryParamInfo.REG_ADDR
            readWrd = self.BatteryParamInfo.READ_WORD
        elif cmd == 'SolarPanelInfo':               
            regAddr = self.SolarPanelInfo.REG_ADDR                           
            readWrd = self.SolarPanelInfo.READ_WORD                    
        elif cmd == 'ParamSettingData':                                                   
            regAddr = self.ParamSettingData.REG_ADDR 
            readWrd = self.ParamSettingData.READ_WORD                                         
        elif cmd == 'RegulatorPowerOn':  
            regAddr = self.RegulatorPower.REG_ADDR
            readWrd = self.RegulatorPower.on                                       
            function = self.function_WRITE                           
        elif cmd == 'RegulatorPowerOff':                                                                                                          
            regAddr = self.RegulatorPower.REG_ADDR
            readWrd = self.RegulatorPower.off                                                                         
            function = self.function_WRITE                                     
                                                             
        self.poll_register = cmd                                          
        return self.buildRequest(function, regAddr, readWrd)                                                                                


