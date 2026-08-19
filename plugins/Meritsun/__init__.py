#!/usr/bin/env python3

# from __future__ import print_function
import os
import sys
import time
from datetime import datetime

# import duallog
import logging

import asciihex
from codec import INT32_MAX, UINT32_WRAP, to_signed

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
        self._frames_ok = 0
        self._frames_bad = 0

    def notificationUpdate(self, data, char):
        # Gets the binary data from the BLE-device and converts it to a list of hex-values
        if self.PowerDevice.config.getboolean('monitor', 'debug', fallback=False):
            with open(f"/tmp/{self.PowerDevice.alias()}.log", 'a') as debugfile:
                debugfile.write(f"{datetime.now()} <- {data.hex()}\n")

        if not data:
            return False

        # The device streams frames back-to-back behind two markers, 0x92 and
        # 0xC9, both carrying the same layout. Neither marker, nor the END_VAL
        # (0x0C) padding, appears inside the ASCII-hex payload, so they delimit
        # packets unambiguously. Accumulating and re-syncing on every marker
        # keeps a lost or reframed notification from desyncing the parser.
        # Unknown, short or corrupt packets are skipped.
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
        # The checksum spans the frame up to its trailing 0x0C padding: the last
        # padding byte before offset 110, not the first 0x0C in the packet.
        end = 0
        for i in range(1, min(len(packet), 122)):
            if packet[i] == self.END_VAL and end < 110:
                end = i + 1
        return end

    def _handleDataPacket(self, packet):
        # The protocol checksum is the only invariant that holds across pack
        # states; field values that look constant are not.
        buf = [0] * 122
        for k in range(min(len(packet), 122)):
            buf[k] = packet[k]
        self.RevBuf = buf
        self.Revindex = min(len(packet), 121)
        self.end = self._frameEnd(packet)
        if self.end < 60 or not asciihex.checksum_matches(buf, self.end):
            self._frames_bad += 1
            logging.debug("[%s] frame rejected: len=%d end=%d",
                          self.PowerDevice.alias(), len(packet), self.end)
            return False
        self._frames_ok += 1
        return self.handleMessage(buf[1:self.Revindex], full=len(packet) <= 130)

    def frame_health(self):
        """Frames accepted and rejected since the last call."""
        counts = (self._frames_ok, self._frames_bad)
        self._frames_ok = self._frames_bad = 0
        return counts


    def _readField(self, message, start, end):
        """Field value, or None when its characters are not ASCII-hex.

        A byte corrupted onto a "00" pair contributes 0 to the additive checksum
        whether it parses or not, so the checksum cannot see it and the field
        silently reads 0. Only the affected field is dropped; the rest of the
        frame is still good.
        """
        if end >= len(message) or not all(
                0x30 <= char <= 0x39 or 0x41 <= char <= 0x46
                for char in message[start:end + 1]):
            return None
        return asciihex.field_value(message, start, end)

    def handleMessage(self, message, full=True):
        # Accepts a list of hex-characters, and returns the human readable values into the powerDevice object
        logging.debug("handleMessage {}".format(message))
        if not message or len(message) < 38:
            return False
        self.prev_values = message

        # A real pack always reports a nonzero pack voltage; a frame decoding it as
        # 0 is not a data frame at all -- a cheap backstop behind the checksum.
        mvoltage = self._readField(message, 0, 7)
        if mvoltage is None or mvoltage < 1000:
            return False

        # Scalar fields occupy the first 38 bytes of the frame. They sit at the
        # head, before the region the duplicated fragments corrupt, so they are
        # decoded on every framed packet; each entity setter validates its own
        # value against physical bounds and rejects any that slipped through.
        mcurrent = self._readField(message, 8, 15)
        mcapacity = self._readField(message, 16, 23)
        charge_cycles = self._readField(message, 24, 27)
        soc = self._readField(message, 28, 31)
        temperature = self._readField(message, 32, 35)
        status = self._readField(message, 36, 37)

        # A run of ASCII '0' sums to zero and the checksum field it lands on
        # reads zero too, so the frame checksum accepts it. A frame carrying a
        # voltage and nothing else is that run, not a reading.
        if not any(value for value in
                   (mcurrent, mcapacity, charge_cycles, soc, temperature, status)
                   if value is not None):
            logging.debug("[%s] frame rejected: only the voltage is set",
                          self.PowerDevice.alias())
            return False

        self.PowerDevice.entities.msg = message
        self.PowerDevice.entities.mvoltage = mvoltage
        if mcurrent is not None:
            self.PowerDevice.entities.mcurrent = to_signed(mcurrent, UINT32_WRAP, INT32_MAX)
        if mcapacity is not None:
            self.PowerDevice.entities.mcapacity = mcapacity
        if charge_cycles is not None:
            self.PowerDevice.entities.charge_cycles = charge_cycles
        if soc is not None:
            self.PowerDevice.entities.soc = soc
        if temperature is not None:
            self.PowerDevice.entities.temperature = temperature
        if status is not None:
            self.PowerDevice.entities.status = status
        # Per-cell voltages start past byte 40 -- exactly the region fragment
        # duplication corrupts. Only trust them on non-bloated ("full") frames;
        # a bloated frame's scalar head is fine but its cells are garbage.
        if full:
            self.PowerDevice.entities.afestatus = asciihex.field_value(message, 40, 41)
            # The frame carries up to 16 cell slots, but these packs have far fewer
            # real cells; slots past the last real cell hold padding (0) or a
            # different field. Stop at the first empty slot. Some frames also carry
            # a corrupt low reading (~200 mV) in an otherwise-real cell slot -- a
            # real cell is ~2.0-4.0 V, so skip anything outside a plausible cell
            # range silently instead of letting the entity log it out-of-bounds.
            i = 0
            while i < 16:
                cell_mv = asciihex.field_value(message, (i * 4) + 44, (i * 4) + 47)
                if cell_mv == 0:
                    break
                if 1000 <= cell_mv <= 5000:
                    self.PowerDevice.entities.cell_mvoltage = (i + 1, cell_mv)
                i = i + 1

        return True



