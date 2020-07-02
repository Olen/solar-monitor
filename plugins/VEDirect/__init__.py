import logging                                                     
import time

class Config():
    SEND_ACK  = False
    NEED_POLLING = True
    NOTIFY_SERVICE_UUID = "306b0001-b081-4037-83dc-e59fcc3cdfd0"
    NOTIFY_CHAR_UUID = ["306b0002-b081-4037-83dc-e59fcc3cdfd0",
                        "306b0003-b081-4037-83dc-e59fcc3cdfd0",
                        "306b0004-b081-4037-83dc-e59fcc3cdfd0"
    ]
    WRITE_SERVICE_UUID = "306b0001-b081-4037-83dc-e59fcc3cdfd0"
    WRITE_CHAR_UUID_POLLING  = "306b0002-b081-4037-83dc-e59fcc3cdfd0"
    WRITE_CHAR_UUID_COMMANDS = "306b0003-b081-4037-83dc-e59fcc3cdfd0"


class Util():

    def __init__(self, power_device):                  
        self.PowerDevice = power_device
        self._char_buffer = b""
        self._is_initialized = False
        self.poll_loop_count = 0

    def notificationUpdate(self, value, char):
        # Run when we receive a BLE-notification
        # print("[{}] Changed to {}".format(characteristic.uuid, value))
        if char == "306b0004-b081-4037-83dc-e59fcc3cdfd0":
            self.set_bulk_values(char, value)
        elif char == "306b0003-b081-4037-83dc-e59fcc3cdfd0":
            self.set_values(value)
        else:
            logging.debug("[{}] Changed to {}".format(char, value))
            self.set_values(value)
        return True

    def pollRequest(self):
        data = None
        if not self._is_initialized and self.poll_loop_count == 2:
            self.send_magic_packets()
            self._is_initialized = True
        elif self.poll_loop_count == 30:
           data = self.create_poll_request("PollData")
           self.poll_loop_count = 0
        self.poll_loop_count = self.poll_loop_count + 1
        return data
        # # Create a poll-request to ask for new data
        # c = charactersistcs["306b0002-b081-4037-83dc-e59fcc3cdfd0"]
        # hs = "f941"
        # b  = bytearray.fromhex(hs)
        # c.write_value(b);


    def cmdRequest(self, command, value):
        # Create a command-request to run a command on the device
        cmd = None
        datas = []
        logging.debug("{} {} => {}".format('cmdRequest', command, value))
        if command == 'power_switch':
            if int(value) == 0:
                cmd = 'PowerOff'
            elif int(value) == 1:
                cmd = 'PowerOn'
            elif int(value) == 5:
                cmd = 'PowerEco'
        if cmd:
            datas.append(self.create_poll_request(cmd))
        return datas


    def ackData(self):
        # Create an ack-packet
        pass

    def create_poll_request(self, cmd):
        logging.debug("{} {}".format("create_poll_request", cmd))
        data = None
        if cmd == 'PollData':
            val = 'f941'
        if cmd == 'PowerOn':
            val = "0603821902004105"        # Eco instead of "on"
            # val = "0603821902004102"
        if cmd == 'PowerOff':
            val = "0603821902004104"
        if cmd == 'PowerEco':
            val = "0603821902004105"
        if val:
            data = bytearray.fromhex(val)
        return data

    def send_magic_packets(self):
        # Some kind of magic session init
        write_characteristic = self.PowerDevice.device_write_characteristic_polling
        # c = charactersistcs["306b0002-b081-4037-83dc-e59fcc3cdfd0"]
        hs = "fa80ff"
        value  = bytearray.fromhex(hs)
        self.PowerDevice.characteristic_write_value(value, write_characteristic)
        time.sleep(0.1)
        
        hs = "f980"
        value = bytearray.fromhex(hs)
        self.PowerDevice.characteristic_write_value(value, write_characteristic)
        time.sleep(0.1)
        # c.write_value(b);
        
        hs = "01"
        value = bytearray.fromhex(hs)
        self.PowerDevice.characteristic_write_value(value, write_characteristic)
        time.sleep(0.1)
        # c.write_value(b);
        
        write_characteristic = self.PowerDevice.device_write_characteristic_commands
        # c = charactersistcs["306b0003-b081-4037-83dc-e59fcc3cdfd0"]
        
        hs = "01"
        value = bytearray.fromhex(hs)
        self.PowerDevice.characteristic_write_value(value, write_characteristic)
        time.sleep(0.1)
        
        hs = "0300"
        value = bytearray.fromhex(hs)
        self.PowerDevice.characteristic_write_value(value, write_characteristic)
        time.sleep(0.1)
        
        hs = "060082189342102703010303"
        value  = bytearray.fromhex(hs)
        self.PowerDevice.characteristic_write_value(value, write_characteristic)
        time.sleep(0.1)
        
        write_characteristic = self.PowerDevice.device_write_characteristic_polling
        # c = charactersistcs["306b0002-b081-4037-83dc-e59fcc3cdfd0"]
        hs = "f941"
        value  = bytearray.fromhex(hs)
        self.PowerDevice.characteristic_write_value(value, write_characteristic)
        time.sleep(0.1)
        # c.write_value(b);
        

    def validate(self):
        pass

    def set_bulk_values(self, char, value):
        start = int.from_bytes(value[0:2], byteorder="little")
        if start == 776:
            self._char_buffer = value
        else:
            self._char_buffer = self._char_buffer + value[:]
        if len(self._char_buffer) > 20:
            i = 0
            while i + 8 <= len(self._char_buffer):
                val = self._char_buffer[i:i+8]
                self.set_values(val)
                i = i + 8
            self._char_buffer = b""



    def set_values(self, value):
        if len(value) == 8:
            ptype = int.from_bytes(value[3:5], byteorder="little")
            pval  = int.from_bytes(value[6:8], byteorder="little")
            if ptype == 34:
                logging.debug("Output voltage: {} V".format(pval * 0.01))
                self.PowerDevice.entities.voltage = pval * 0.01
                if self.PowerDevice.entities.voltage < 1:
                    self.PowerDevice.entities.voltage = 0
                if pval > 10000:
                    self.PowerDevice.entities.power_switch = 1
                else:
                    self.PowerDevice.entities.power_switch = 0
            elif ptype == 36333:
                logging.debug("Input voltage: {} V".format(pval * 0.01))
                self.PowerDevice.entities.input_voltage = pval * 0.01
            elif ptype == 290:
                if pval == 0:
                    logging.debug("Output Power turned off")
                    self.PowerDevice.entities.power_switch = 0
                    self.PowerDevice.entities.current = 0
                elif pval == 65534:
                    logging.debug("Output Power turned on")
                    self.PowerDevice.entities.power_switch = 1
                elif pval == 65533:
                    logging.debug("Output Power ended")
                    self.PowerDevice.entities.current = 0
                else:
                    logging.debug("Current: {} A".format(pval * 0.1))
                    self.PowerDevice.entities.current = pval * 0.1
            else:
                logging.debug("?? {}: {}".format(ptype, pval))
        if len(value) == 7:
            ptype = int(str(value[4]), 16)
            pval  = int(str(value[6]), 16)
            state = "?"
            if ptype == 0:
                if pval == 2:
                    logging.debug("Output Power turned on")
                    self.PowerDevice.entities.power_switch = 1
                if pval == 4:
                    logging.debug("Output Power turned off")
                    self.PowerDevice.entities.power_switch = 0
                if pval == 5:
                    logging.debug("Output Power turned to eco - setting switch to on")
                    self.PowerDevice.entities.power_switch = 1
            if ptype == 1:
                if pval == 0:
                    logging.debug("Output Power state turned off")
                    self.PowerDevice.entities.power_switch = 0
                if pval == 1:
                    logging.debug("Output Power state turned to eco")
                    self.PowerDevice.entities.power_switch = 1
                if pval == 9:
                    logging.debug("Output Power state turned on")
                    self.PowerDevice.entities.power_switch = 1
