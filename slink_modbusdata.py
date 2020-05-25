#!/usr/bin/env python3

from __future__ import absolute_import
import os
import sys

from datalogger import DataLogger
from slink_checksumcrc import ChecksumCRC

import logging
import duallog

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
    def BuildRequestBasis(cls, function_, dev_addr):
        bytes = [None]*2
        bytes[1] = int(function_)
        bytes[0] = int(dev_addr)
        return bytes

    @classmethod
    def BuildReadRegsCmd(cls, dev_addr, start, count):
        bytes = [None]*8
        basis = cls.BuildRequestBasis(3, dev_addr)
        # System.arraycopy(basis, 0, bytes, 0, )
        bytes = basis[:]
        bytes[2] = int(((start & ACTION_POINTER_INDEX_MASK) >> 8))
        bytes[3] = int((start & 255))
        bytes[4] = int(((count & ACTION_POINTER_INDEX_MASK) >> 8))
        bytes[5] = int((count & 255))
        crc = ChecksumCRC.calcCrc16(bytes, 0, 6)
        bytes[7] = int(((crc & ACTION_POINTER_INDEX_MASK) >> 8))
        bytes[6] = int((crc & 255))
        return bytes

    @classmethod
    def BuildWriteRegCmd(cls, dev_addr, start, data):
        bytes = [None]*8
        basis = cls.BuildRequestBasis(6, dev_addr)
        # System.arraycopy(basis, 0, bytes, 0, )
        bytes = basis[:]
        bytes[2] = int(((start & ACTION_POINTER_INDEX_MASK) >> 8))
        bytes[3] = int((start & 255))
        bytes[4] = int(((data & ACTION_POINTER_INDEX_MASK) >> 8))
        bytes[5] = int((data & 255))
        crc = ChecksumCRC.calcCrc16(bytes, 0, 6)
        bytes[7] = int(((crc & ACTION_POINTER_INDEX_MASK) >> 8))
        bytes[6] = int((crc & 255))
        return bytes


    @classmethod
    def DataCrcCorrect(cls, bs):
        if bs == None or len(bs)<2:
            return False
        crc = ChecksumCRC.calcCrc16(bs, 0, (len(bs) - 2))
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
