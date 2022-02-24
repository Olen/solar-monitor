import logging
import libscrc
import dateutil.parser
import re
from datetime import datetime

class Config():
    NOTIFY_SERVICE_UUID = "0000fff0-0000-1000-8000-00805f9b34fb"
    NOTIFY_CHAR_UUID = "0000fff1-0000-1000-8000-00805f9b34fb"
    WRITE_SERVICE_UUID = "0000ffd0-0000-1000-8000-00805f9b34fb"
    WRITE_CHAR_UUID_POLLING  = "0000ffd1-0000-1000-8000-00805f9b34fb"
    WRITE_CHAR_UUID_COMMANDS = "0000ffd1-0000-1000-8000-00805f9b34fb"
    SEND_ACK  = True
    NEED_POLLING = True
    DEVICE_ID = 48

class Util():

    class TotalCapacityState():
        #this actually grabs model name that contains capacity val
        REG_ADDR = 2
        READ_WORD = 8
    class VoltageAndCurrentState():
        REG_ADDR  = 178
        READ_WORD = 6
    class TemperatureState():
        REG_ADDR  = 153
        READ_WORD = 7
    class CellVoltageState():
        REG_ADDR  = 136
        READ_WORD = 17

    def __init__(self, power_device):
        self.PowerDevice = power_device
        self.function_READ = 3
        self.function_WRITE = 6
        self.total_capacity = 0
        self.time_int = datetime.now()
        self.param_buffer = b""
        self.param_expect = 0
        self.param_data = []
        self.poll_loop_count = 0
        self.poll_data = None
        self.poll_register = None

    def notificationUpdate(self, value, char):
        '''
        Fortunately we read a different number of bytes from each register, so we can
        abuse the "length" field (byte #3 in the response) as an "id"
        '''

        if not self.Validate(value):
            logging.warning("PollerUpdate - Invalid data: {}".format(value))
            return False

        if value[0] == self.PowerDevice.device_id and value[1] == self.function_READ:
            if value[2] == self.VoltageAndCurrentState.READ_WORD * 2:
                self.updateVoltageAndCurrent(value)
            if value[2] == self.CellVoltageState.READ_WORD * 2:
                self.updateCellVoltage(value)
            if value[2] == self.TemperatureState.READ_WORD * 2:
                self.updateTemperature(value)
            if value[2] == self.TotalCapacityState.READ_WORD * 2:
                self.updateTotalCapacity(value)
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


    def pollRequest(self, force = None):
        data = None
        self.poll_loop_count = self.poll_loop_count + 1
        if self.poll_loop_count == 1:
            data = self.create_poll_request('TotalCapacity')
        if self.poll_loop_count == 3:
            data = self.create_poll_request('VoltageAndCurrent')
        elif self.poll_loop_count == 5:
            data = self.create_poll_request('CellVoltage')
        elif self.poll_loop_count == 7:
            data = self.create_poll_request('Temperature')
        elif self.poll_loop_count == 9:
        #Voltage and Current change more often, check these more
            data = self.create_poll_request('VoltageAndCurrent')
        elif self.poll_loop_count == 11:
            data = self.create_poll_request('VoltageAndCurrent')
        elif self.poll_loop_count == 13:
            data = self.create_poll_request('VoltageAndCurrent')
        elif self.poll_loop_count == 15:
            data = self.create_poll_request('VoltageAndCurrent')
        elif self.poll_loop_count == 17:
            #run TotalCapacity only once
            self.poll_loop_count = 2
        return data


    def ackData(self, value):
        return bytearray("main recv da ta[{0:02x}] [".format(value[0]), "ascii")

    def voltageToCapacity(self):
        #Hard-set the remaining capacity based on voltage to resync readings
        prev_capacity = self.PowerDevice.entities.capacity
        new_voltage = self.PowerDevice.entities.voltage
        if new_voltage == 0:
            return
        if self.total_capacity == 0:
            return
        #Current makes Voltage to Capacity unreliable, return if Current too high
        if abs(self.PowerDevice.entities.current) > 2:
            return

        percent = 100
        if new_voltage >= 13.5:
            percent = 100
        elif new_voltage >= 13.4:
            percent = 99
        elif new_voltage >= 13.3:
            percent = 90
        elif new_voltage >= 13.2:
            #special case for 13.2 since volt drop so small here
            if prev_capacity == 0:
                #new batt, no data, assume middle
                percent = 70
            elif (prev_capacity/self.total_capacity) > 85:
                percent = 80
            elif (prev_capacity/self.total_capacity) < 45:
                percent = 50
        elif new_voltage >= 13.1:
            percent = 40
        elif new_voltage >= 13.0:
            percent = 30
        elif new_voltage >= 12.9:
            percent = 20
        elif new_voltage >= 12.0:
            percent = new_voltage * 10 - 111
        elif new_voltage >= 11.8:
            percent = (new_voltage * 10 - 100) / 2 - 1
        elif new_voltage >= 10.0:
            percent = (new_voltage * 10 - 100) / 2
        new_capacity = (self.total_capacity * percent)/100
        logging.debug("old capacity is {} and new is {}".format(prev_capacity, new_capacity))
        # reset only if dysnc is large - otherwise, we trust our reading
        if abs(prev_capacity - new_capacity)/self.total_capacity > .1:
            self.PowerDevice.entities.capacity = new_capacity
        return


    def updateVoltageAndCurrent(self, bs):
        logging.debug("Voltage {} {} => {}".format(
            int(bs[5]), int(bs[6]), self.Bytes2Int(bs, 5, 2) * .1))
        logging.debug("Current {} {} => {}".format(
            int(bs[3]), int(bs[4]), self.Bytes2Int(bs, 3, 2)* .01))
        self.PowerDevice.entities.current = self.Bytes2Int(bs, 3, 2) * .01
        self.updateCapacityFromCurrent()
        self.PowerDevice.entities.voltage = self.Bytes2Int(bs, 5, 2) * .1
        # hard-set capacity based on voltage to reset desync
        self.voltageToCapacity()


    def updateCellVoltage(self, bs):
        logging.debug("CellCount {}".format(int(bs[4])))
        self.PowerDevice.entities.cell_count = int(bs[4])
        for j in range(int(bs[4])):
            local_s = 5 + (j*2)
            logging.debug("CellmVoltage {} {} => {}".format(
                int(bs[local_s]),int(bs[local_s+1]), self.Bytes2Int(bs, local_s, 2) * .1))
            self.PowerDevice.entities.cell_mvoltage = (j+1,self.Bytes2Int(bs, local_s, 2) * .1)
        return


    def updateTemperature(self, bs):
        logging.debug("TemperatureCount {}".format(int(bs[4])))
        for j in range(int(bs[4])):
            local_s = 5 + (j*2)
            logging.debug("Temperature {} {} => {}".format(
                int(bs[local_s]),int(bs[local_s+1]), self.Bytes2Int(bs, local_s, 2) * .1))
            self.PowerDevice.entities.temperature_celsius = self.Bytes2Int(bs, local_s, 2) * .1
            self.PowerDevice.entities.battery_temperature_celsius = self.Bytes2Int(bs, local_s, 2) * .1
        return


    def updateTotalCapacity(self, bs):
        #extract total capacity from model name
        device_str = bs.decode(errors='ignore')
        logging.debug("Device name is {}".format(device_str))
        capacity_match = re.search("RBT(\d+)",device_str)
        total_capacity = int(capacity_match.group(1))
        logging.debug("TotalCapacity is: {}".format(total_capacity))
        self.total_capacity = total_capacity
        return


    # Remaining Capacity reading from battery could be... improved
    # Here we run our own updating of capacity.
    # Since voltage changes, we convert to watts (per second),
    # subtract, then convert back to amps
    def updateCapacityFromCurrent(self):
        #time since last update, we (unfortunately) assume same current whole time
        cur_time = datetime.now()
        charge_watts = self.PowerDevice.entities.current * self.PowerDevice.entities.voltage
        logging.debug("Seconds pass is {}".format((cur_time - self.time_int).total_seconds()))
        charge_watts = charge_watts * (cur_time - self.time_int).total_seconds()
        self.time_int = cur_time
        #capacity rounds for display, use mcapacity
        capacity_watts = ((self.PowerDevice.entities.mcapacity/1000) * 12.8 * 60 * 60)
        new_watts = capacity_watts + charge_watts
        capacity_amps = new_watts/(12.8 * 60 * 60)
        self.PowerDevice.entities.capacity = capacity_amps
        return


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

        crc = libscrc.modbus(bytes(bs[:-2]))
        check = self.Bytes2Int(bs, offset=len(bs)-1, length=-2)
        if crc == check:
            return True
        logging.warning("CRC Failed: {} - Check: {}".format(crc, check))
        return False


    def create_poll_request(self, cmd):
        logging.debug("{} {}".format("create_poll_request", cmd))
        data = None
        function = self.function_READ
        device_id = self.PowerDevice.device_id
        self.poll_register = cmd
        regAddr = 0
        if cmd == 'VoltageAndCurrent':
            regAddr = self.VoltageAndCurrentState.REG_ADDR
            readWrd = self.VoltageAndCurrentState.READ_WORD
        elif cmd == 'Temperature':
            regAddr = self.TemperatureState.REG_ADDR
            readWrd = self.TemperatureState.READ_WORD
        elif cmd == 'CellVoltage':
            regAddr = self.CellVoltageState.REG_ADDR
            readWrd = self.CellVoltageState.READ_WORD
        elif cmd == 'TotalCapacity':
            regAddr = self.TotalCapacityState.REG_ADDR
            readWrd = self.TotalCapacityState.READ_WORD

        if regAddr:
            data = []
            data.append(self.PowerDevice.device_id)
            data.append(function)
            if cmd == 'TotalCapacity':
                data.append(20)
            else:
                data.append(19)
            data.append(regAddr)
            data.append(0)
            data.append(readWrd)
            crc = libscrc.modbus(bytes(data))
            data.append(self.Int2Bytes(crc, 1))
            data.append(self.Int2Bytes(crc, 0))
            logging.debug("{} {} => {}".format("create_poll_request", cmd, data))
            return data

