#!/usr/bin/env python3

from __future__ import absolute_import
import os
import sys
import libscrc


from datalogger import DataLogger
from slink_checksumcrc import ChecksumCRC

import logging
import duallog
# duallog.setup('srne', minLevel=logging.DEBUG, rotation='daily', keep=30)


class ModbusData(object):
    ER_CLEAR_HISTORY = 249
    ER_READ_REG = 131
    ER_RESET_FACTORY = 248
    ER_WRITE_MUXREG = 144
    ER_WRITE_SIGREG = 134
    EX_CLIENT_EXE = 4
    EX_CRC = 5
    EX_NOT_SUPPORT = 1
    EX_PUD_ADDR_LENGTH = 2
    EX_REG_RW = 3
    FC_CLEAR_HISTORY = 121
    FC_READ_REG = 3
    FC_RESET_FACTORY = 120
    FC_WRITE_MUXREG = 16
    FC_WRITE_SIGREG = 6
    ACTION_POINTER_INDEX_MASK = 65280

    @classmethod
    def BuildRequestBasis(self, function_, dev_addr):
        bytes = [None]*2
        # bytes[0] = int(dev_addr.split(":")[-1], 16)
        # bytes[0] = int(dev_addr.split(":")[0], 16)
        bytes[0] = int(dev_addr)
        bytes[1] = int(function_)
        return bytes

    @classmethod
    def BuildReadRegsCmd(self, dev_addr, start, count):
        bytes = [None]*8
        basis = self.BuildRequestBasis(3, dev_addr)
        # System.arraycopy(basis, 0, bytes, 0, )
        bytes = basis[:]
        logging.debug("{} {}".format("BuildReadRegsCmd 1", bytes))
        bytes.append(int(((start & self.ACTION_POINTER_INDEX_MASK) >> 8)))
        # bytes.append(int(((start & self.ACTION_POINTER_INDEX_MASK) >> 8)))
        bytes.append(int((start & 255)))
        bytes.append(int(((count & self.ACTION_POINTER_INDEX_MASK) >> 8)))
        bytes.append(int((count & 255)))
        logging.debug("{} {}".format("BuildReadRegsCmd 2", bytes))
        crc = libscrc.modbus(bytearray(bytes))
        logging.debug("{} {}".format("CRC: ", crc))

        # crc = ChecksumCRC.calcCrc16(bytes, 0, 6)
        bytes.append(int((crc & 255)))
        # bytes.append(int((crc & 255)))
        bytes.append(int(((crc & self.ACTION_POINTER_INDEX_MASK) >> 8)))
        logging.debug("{} {}".format("BuildReadRegsCmd 3", bytes))
        return bytes

    @classmethod
    def BuildWriteRegsCmd(self, dev_addr, start, data):
        bytes = [None]*8
        basis = self.BuildRequestBasis(6, dev_addr)
        # System.arraycopy(basis, 0, bytes, 0, )
        bytes = basis[:]
        logging.debug("{} {}".format("BuildWriteRegsCmd 1", bytes))
        bytes.append(int(((start & self.ACTION_POINTER_INDEX_MASK) >> 8)))
        bytes.append(int((start & 255)))
        bytes.append(int(((data & self.ACTION_POINTER_INDEX_MASK) >> 8)))
        bytes.append(int((data & 255)))
        logging.debug("{} {}".format("BuildWriteRegsCmd 2", bytes))
        # crc = ChecksumCRC.calcCrc16(bytes, 0, 6)
        crc = libscrc.modbus(bytearray(bytes))
        logging.debug("{} {}".format("CRC: ", crc))
        bytes.append(int((crc & 255)))
        bytes.append(int(((crc & self.ACTION_POINTER_INDEX_MASK) >> 8)))
        logging.debug("{} {}".format("BuildWriteRegsCmd 3", bytes))
        return bytes


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
