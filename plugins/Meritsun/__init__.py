#!/usr/bin/env python3

# from __future__ import print_function
import os
import sys
import time
from datetime import datetime

# import duallog
import logging

from codec import INT32_MAX, UINT32_WRAP, ascii_hex_value, to_signed

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
        return ascii_hex_value(buf, start, end)




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
        if self.PowerDevice.config.getboolean('monitor', 'debug', fallback=False):
            with open(f"/tmp/{self.PowerDevice.alias()}.log", 'a') as debugfile:
                debugfile.write(f"{datetime.now()} <- {data.hex()}\n")

        if not data:
            return False

        # The device streams frames back-to-back behind two markers, 0x92 and
        # 0xC9. Both carry the same layout -- every checksum-valid frame decodes
        # identically regardless of marker, and 0xC9 carries about two thirds of
        # them -- so both start a frame.
        # Neither marker, nor the END_VAL (0x0C) padding, ever appears inside the
        # ASCII-hex payload, so the markers delimit packets unambiguously. We
        # accumulate the stream and re-sync on every marker, so a single lost or
        # reframed notification can no longer desync the parser permanently the
        # way the old fixed-121-byte logic did (which, after the trixie/BlueZ 5.82
        # notification-framing change, gave up after the first frame). Unknown,
        # short or corrupt packets are simply skipped.
        if not hasattr(self, '_stream'):
            self._stream = bytearray()
        self._stream.extend(data)
        # Bound the buffer so a marker-less run can't grow without limit.
        if len(self._stream) > 512:
            keep = max(self._stream.rfind(self.START_VAL), self._stream.rfind(0xC9))
            self._stream = self._stream[keep:] if keep > 0 else self._stream[-256:]

        updated = False
        while True:
            start = -1
            for mark in (self.START_VAL, 0xC9):
                q = self._stream.find(mark)
                if q >= 0 and (start < 0 or q < start):
                    start = q
            if start < 0:
                # No frame forming; drop the (unhandled) leading bytes.
                self._stream.clear()
                break
            nxt = -1
            for mark in (self.START_VAL, 0xC9):
                p = self._stream.find(mark, start + 1)
                if p >= 0 and (nxt < 0 or p < nxt):
                    nxt = p
            if nxt < 0:
                # Packet not terminated yet (next marker unseen); keep it buffered.
                if start > 0:
                    del self._stream[:start]
                break
            packet = self._stream[start:nxt]   # START_VAL + payload + 0x0C padding
            del self._stream[:nxt]             # consume; keep next marker as the new start
            if self._handleDataPacket(packet):
                updated = True
        return updated

    def _frameEnd(self, packet):
        # The checksum spans the frame up to its trailing 0x0C padding. `find`
        # stops at the first 0x0C, which in this stream sits far too early; the
        # device's own rule is the last padding byte before offset 110.
        end = 0
        for i in range(1, min(len(packet), 122)):
            if packet[i] == self.END_VAL and end < 110:
                end = i + 1
        return end

    def _handleDataPacket(self, packet):
        # Gate on the protocol checksum -- the only invariant that holds. The
        # previous signature gate keyed on bytes that turned out to be live data:
        # it matched 142/363 frames in July and 0/122 in August.
        buf = [0] * 122
        for k in range(min(len(packet), 122)):
            buf[k] = packet[k]
        self.RevBuf = buf
        self.Revindex = min(len(packet), 121)
        self.end = self._frameEnd(packet)
        if self.end < 60 or not self.validateChecksum(buf):
            logging.debug("[%s] frame rejected: len=%d end=%d",
                          self.PowerDevice.alias(), len(packet), self.end)
            return False
        return self.handleMessage(buf[1:self.Revindex], full=len(packet) <= 130)


    def handleMessage(self, message, full=True):
        # Accepts a list of hex-characters, and returns the human readable values into the powerDevice object
        logging.debug("handleMessage {}".format(message))
        if not message or len(message) < 38:
            return False
        self.prev_values = message

        # A real pack always reports a nonzero pack voltage; a frame decoding it as
        # 0 is not a data frame at all -- a cheap backstop behind the checksum.
        mvoltage = self.getValue(message, 0, 7)
        if mvoltage < 1000:
            return False

        self.PowerDevice.entities.msg = message
        # Scalar fields occupy the first 38 bytes of the frame. They sit at the
        # head, before the region the duplicated fragments corrupt, so they are
        # decoded on every framed packet; each entity setter validates its own
        # value against physical bounds and rejects any that slipped through.
        self.PowerDevice.entities.mvoltage = mvoltage
        mcurrent = to_signed(self.getValue(message, 8, 15), UINT32_WRAP, INT32_MAX)
        self.PowerDevice.entities.mcurrent = mcurrent
        self.PowerDevice.entities.mcapacity = self.getValue(message, 16, 23)
        self.PowerDevice.entities.charge_cycles = self.getValue(message, 24, 27)
        self.PowerDevice.entities.soc = self.getValue(message, 28, 31)
        self.PowerDevice.entities.temperature = self.getValue(message, 32, 35)
        self.PowerDevice.entities.status = self.getValue(message, 36, 37)
        # Per-cell voltages start past byte 40 -- exactly the region fragment
        # duplication corrupts. Only trust them on non-bloated ("full") frames;
        # a bloated frame's scalar head is fine but its cells are garbage.
        if full:
            self.PowerDevice.entities.afestatus = self.getValue(message, 40, 41)
            # The frame carries up to 16 cell slots, but these packs have far fewer
            # real cells; slots past the last real cell hold padding (0) or a
            # different field. Stop at the first empty slot. Some frames also carry
            # a corrupt low reading (~200 mV) in an otherwise-real cell slot -- a
            # real cell is ~2.0-4.0 V, so skip anything outside a plausible cell
            # range silently instead of letting the entity log it out-of-bounds.
            i = 0
            while i < 16:
                cell_mv = self.getValue(message, (i * 4) + 44, (i * 4) + 47)
                if cell_mv == 0:
                    break
                if 1000 <= cell_mv <= 5000:
                    self.PowerDevice.entities.cell_mvoltage = (i + 1, cell_mv)
                i = i + 1

        return True



