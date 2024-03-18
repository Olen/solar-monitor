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
    # https://community.victronenergy.com/storage/attachments/2273-vecan-registers-public.pdf
    VREG_COMMANDS = {
        'VREC': 0x0001,
        'VACK': 0x0002,
        'VPING': 0x0003,
        'DEFAULTS': 0x0004,
    }
    # All ints are unsigned
    VREG_RESPONSES = {
        'ProductID': { 'key': 0x0100, 'format': { 'id': 'un8', 'prodid': 'un16', 'flags': 'un8'}},
        'Revision': { 'key': 0x0101, 'format': { 'id': 'un8', 'revision': 'un16'}},
        'FwVersion': { 'key': 0x0102, 'format': { 'id': 'un8', 'fw': 'un24'}},
        'MinVersion': { 'key': 0x0103, 'format': { 'id': 'un8', 'fw': 'un24'}},
        'GroupID': { 'key': 0x0104, 'format': { 'groupid': 'un8'}},
        'HwRevision': { 'key': 0x0105, 'format': { 'hwrev': 'un8'}},
        'SerialNumber': { 'key': 0x010a, 'format': { 'serial': 'string32' }},
        'ModelName': { 'key': 0x010b, 'format': { 'model': 'string32' }},
        'Description1': { 'key': 0x010c, 'format': { 'model': 'string' }},
        'Description2': { 'key': 0x010d, 'format': { 'model': 'string' }},
        'Identify': { 'key': 0x010e, 'format': { 'identify': 'un8'}},
        'UdfVersion': { 'key': 0x0110, 'format': { 'version': 'un24', 'flags': 'un8' }},
        'Uptime': { 'key': 0x0120, 'format': { 'uptime': 'un32'}},
        'CanHwOverflows': { 'key': 0x0130, 'format': { 'overflows': 'un32'}},
        'CanSwOverflows': { 'key': 0x0131, 'format': { 'overflows': 'un32'}},
        'CanErrors': { 'key': 0x0132, 'format': { 'errors': 'un32'}},
        'CanBusOff': { 'key': 0x0133, 'format': { 'bussoff': 'un32'}},
    }

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
        logging.debug("{} {} => {}".format('pollRequest', self.poll_loop_count, self._is_initialized))
        data = None
        if not self._is_initialized and self.poll_loop_count == 2:
            self.send_magic_packets()
            self._is_initialized = True
        elif self.poll_loop_count == 5:
            self.keep_alive()
            self.poll_loop_count = 0
        #    data = self.create_poll_request("PollData")
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
            # val = "0603821902004105"        # Eco instead of "on"
            val = "0603821902004102"
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

        hs = "fa80ff"
        value  = bytearray.fromhex(hs)
        self.PowerDevice.characteristic_write_value(value, write_characteristic)
        time.sleep(0.1)

        hs = "f980"
        value = bytearray.fromhex(hs)
        self.PowerDevice.characteristic_write_value(value, write_characteristic)
        time.sleep(0.1)
        # c.write_value(b);

        # Skal ikke dit...
        # hs = "01"
        # value = bytearray.fromhex(hs)
        # self.PowerDevice.characteristic_write_value(value, write_characteristic)
        # time.sleep(0.1)
        # c.write_value(b);

        # Send some data to the command-characteristics
        write_characteristic = self.PowerDevice.device_write_characteristic_commands

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

        # Poll for data
        write_characteristic = self.PowerDevice.device_write_characteristic_polling
        # c = charactersistcs["306b0002-b081-4037-83dc-e59fcc3cdfd0"]
        hs = "f941"
        value  = bytearray.fromhex(hs)
        self.PowerDevice.characteristic_write_value(value, write_characteristic)
        time.sleep(0.1)
        # c.write_value(b);

    def keep_alive(self):
        # ("0024", "0600821893421027"),
        # ("0021", "f941"),
        write_characteristic = self.PowerDevice.device_write_characteristic_commands
        hs = "060082189342102703010303"
        value  = bytearray.fromhex(hs)
        self.PowerDevice.characteristic_write_value(value, write_characteristic)
        time.sleep(0.1)

        write_characteristic = self.PowerDevice.device_write_characteristic_polling
        hs = "f941"
        value  = bytearray.fromhex(hs)
        self.PowerDevice.characteristic_write_value(value, write_characteristic)
        time.sleep(0.1)


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

        logging.debug(f"Got packet of len: {len(value)} {value}")
        if len(value) == 8:
            ptype = int.from_bytes(value[3:5], byteorder="little")
            pval  = int.from_bytes(value[6:8], byteorder="little")
            logging.debug("8 Byte Data: {} {} {} {} {} {} {} {}".format(
                value[0],
                value[1],
                value[2],
                value[3],
                value[4],
                value[5],
                value[6],
                value[7]))
            logging.debug("ptype {}: pval {}".format(ptype, pval))
            if ptype == 34:
                logging.debug("Output voltage: {} V".format(pval * 0.01))
                self.PowerDevice.entities.voltage = pval * 0.01
                if self.PowerDevice.entities.voltage < 1:
                    self.PowerDevice.entities.voltage = 0
                if pval > 10000:
                    self.PowerDevice.entities.power_switch = 1
                # else:
                #     self.PowerDevice.entities.power_switch = 0
            elif ptype == 36333:
                logging.debug("Input voltage: {} V".format(pval * 0.01))
                self.PowerDevice.entities.input_voltage = pval * 0.01
            elif ptype == 36845: #current
                # 2^16 value
                # negative starts from 2^16
                # and goes down
                if pval > 2**16/2: # probably negative
                    pval = 2**16 - pval
                    pval *= -1
                logging.debug("Current: {} A".format(pval * 0.1))
                self.PowerDevice.entities.current = pval * 0.1

            elif ptype == 290:
                if pval == 0:
                    # logging.info("Output Power turned off #1")
                    logging.debug("No output current")
                    self.PowerDevice.entities.current = 0
                elif pval == 65535:
                    logging.debug("Unknown data pval 65535: {}".format(value))
                    # self.PowerDevice.entities.power_switch = 1
                elif pval == 65534:
                    logging.debug("Output Power turned on #2")
                    self.PowerDevice.entities.power_switch = 1
                elif pval == 65533:
                    # logging.info("Output Power ended")
                    logging.debug("Checking output current")
                    self.PowerDevice.entities.current = 0
                else:
                    logging.debug("Current: {} A".format(pval * 0.1))
                    self.PowerDevice.entities.current = pval * 0.1
            else:
                logging.debug("Unknown-8 {}: {}".format(ptype, pval))
        elif len(value) == 7:
            ptype = int(str(value[4]), 16)
            pval  = int(str(value[6]), 16)
            state = "?"
            if ptype == 0:
                if pval == 2:
                    logging.info("Output Power turned on")
                    self.PowerDevice.entities.power_switch = 1
                if pval == 4:
                    logging.info("Output Power turned off")
                    self.PowerDevice.entities.power_switch = 0
                if pval == 5:
                    logging.info("Output Power turned to eco")
                    self.PowerDevice.entities.power_switch = 1
            elif ptype == 1:
                if pval == 0:
                    logging.debug("Output Power state turned off ptype 1 pval 0")
                    self.PowerDevice.entities.power_switch = 0
                if pval == 1:
                    logging.debug("Output Power state turned to eco ptype 1 pval 1")
                    self.PowerDevice.entities.power_switch = 1
                if pval == 9:
                    logging.debug("Output Power state turned on ptype 1 pval 9")
                    self.PowerDevice.entities.power_switch = 1
            else:
                logging.debug("Unknown-7 {}: {}".format(ptype, pval))
        else:
            logging.debug("Unknown packet: {}".format(value))
