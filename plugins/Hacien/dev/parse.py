#!/usr/bin/python

import json
import pprint
import re


def validCrc(msg: list) -> bool:
    return len(msg) > 0 and modbusCrc(msg) == 0

def modbusCrc(msg: list) -> int:
    crc = 0xFFFF
    for n in msg:
        crc ^= n
        for i in range(8):
            if crc & 1:
                crc >>= 1
                crc ^= 0xA001
            else:
                crc >>= 1
    return crc

# msg = [0x01, 0x03, 0xd0, 0x26, 0x00, 0x19, 0x5d, 0x0b]
# print(validCrc(msg))
# msg = [0x01, 0x03, 0xd0, 0x26, 0x00, 0x19]
# print(validCrc(msg))
# crc = modbusCrc(msg)
# print("0x%04X"%(crc))
# 
# ba = crc.to_bytes(2, byteorder='little')
# print("%02X %02X"%(ba[0], ba[1]))
# 
# sys.exit()
# 
f = open("bms-raw-2024-03-20.json")
data = json.load(f)

# pprint.pprint(data)
buffer = []
for packet in data:
    if 'btatt' in packet['_source']['layers']:
        # print(packet['_source']['layers']['frame']['frame.time'])
        if 'btgatt.nordic.uart_tx_raw' in packet['_source']['layers']['btatt']:
            buffer = []
            tx_string = packet['_source']['layers']['btatt']['btgatt.nordic.uart_tx_raw'][0]
            tx_splitted = re.findall('.{1,2}', tx_string)
            print("")
            print("->", " ".join(tx_splitted))
            # print(f"-> {packet['_source']['layers']['btatt']['btgatt.nordic.uart_tx_raw'][0]}")
            # print(f"   len: {len(packet['_source']['layers']['btatt']['btgatt.nordic.uart_tx'])}")
            # print(f"   bytes: {bytes(packet['_source']['layers']['btatt']['btgatt.nordic.uart_tx'], 'utf-8')}")
        if 'btgatt.nordic.uart_rx_raw' in packet['_source']['layers']['btatt']:
            string = packet['_source']['layers']['btatt']['btgatt.nordic.uart_rx_raw'][0]
            splitted = re.findall('.{1,2}', string)
            buffer = buffer + [int(i, 16) for i in splitted]
            # buffer = buffer + splitted
        if validCrc(buffer):
            checksum = buffer[-2:]
            if len(buffer) > 10 and buffer[2] == 0x4c:
                print(f"-> {tx_splitted}")
                cell1 = buffer[3]*256 + buffer[4]
                cell2 = buffer[5]*256 + buffer[6]
                cell3 = buffer[7]*256 + buffer[8]
                cell4 = buffer[9]*256 + buffer[10]
                c_voltage = buffer[-4]*256 + buffer[-3] 
                voltage = c_voltage / 100
                print(cell1, cell2, cell3, cell4, voltage)
            elif len(buffer) > 10 and buffer[2] == 0x32:
                print(f"-> {tx_splitted}")
                use = (buffer[29]*256 + buffer[30]) / 10
                soc1 = buffer[32]
                soc2 = buffer[34]
                current_ah = buffer[35]*256 + buffer[36]
                total_ah1 = buffer[37]*256 + buffer[38]
                total_ah2 = buffer[39]*256 + buffer[40]
                cycles    = buffer[42]
                print(use, soc1, soc2, current_ah, total_ah1, total_ah2, cycles)

                temp1 = buffer[3]*256+buffer[4]
                print("T1", temp1)
                temp2 = temp1 - 380
                print("T2", temp2)
                temp3 = temp2 / 10
                print("T3", temp3)

                # 0258 = 600      22
                # 0244 = 580      20      - 20
                # 0226 = 550      17      - 30
                # 
                # 017C = 380       0      - 170
                # 0000 =   0     -38
            buffer = []

            # elif len(buffer) > 10 and buffer[2] == 0x18:
            #     pass
            #     # temp1 = buffer[7]*256 + buffer[8]
            #     # print("T1", temp1)
            #     # temp2 = -50 + (temp1*175)/1650
            #     # # -50+(679*175)/1650

            #     # print("T2", temp2)
            #     # temp3  = (100-(-30))*temp1/1650-30
            #     # print("T3", temp3)
            #     # # print("T", temp)
            #     # # 02A7
            #     # # (100-(-30))*679/1650-30


            # else:
            #     pass
            #     # print(buffer)

            # print("<-", " ".join(splitted))
            # print(f"<- {packet['_source']['layers']['btatt']['btgatt.nordic.uart_rx_raw'][0]}")
            # print(f"   len: {len(packet['_source']['layers']['btatt']['btgatt.nordic.uart_rx'])}")
            # print(f"   bytes: {bytes(packet['_source']['layers']['btatt']['btgatt.nordic.uart_rx'], 'utf-8')}")
        # pprint.pprint(packet['_source']['layers']['btatt'])
