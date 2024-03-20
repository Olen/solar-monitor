#!/usr/bin/python

import json
import pprint
import re


f = open("bms-raw-2024-03-20.json")
data = json.load(f)

# pprint.pprint(data)
for packet in data:
    if 'btatt' in packet['_source']['layers']:
        # print(packet['_source']['layers']['frame']['frame.time'])
        if 'btgatt.nordic.uart_tx_raw' in packet['_source']['layers']['btatt']:
            string = packet['_source']['layers']['btatt']['btgatt.nordic.uart_tx_raw'][0]
            splitted = re.findall('.{1,2}', string)
            print("")
            print("->", " ".join(splitted))
            # print(f"-> {packet['_source']['layers']['btatt']['btgatt.nordic.uart_tx_raw'][0]}")
            # print(f"   len: {len(packet['_source']['layers']['btatt']['btgatt.nordic.uart_tx'])}")
            # print(f"   bytes: {bytes(packet['_source']['layers']['btatt']['btgatt.nordic.uart_tx'], 'utf-8')}")
        if 'btgatt.nordic.uart_rx_raw' in packet['_source']['layers']['btatt']:
            string = packet['_source']['layers']['btatt']['btgatt.nordic.uart_rx_raw'][0]
            splitted = re.findall('.{1,2}', string)
            print("<-", " ".join(splitted))
            # print(f"<- {packet['_source']['layers']['btatt']['btgatt.nordic.uart_rx_raw'][0]}")
            # print(f"   len: {len(packet['_source']['layers']['btatt']['btgatt.nordic.uart_rx'])}")
            # print(f"   bytes: {bytes(packet['_source']['layers']['btatt']['btgatt.nordic.uart_rx'], 'utf-8')}")
        # pprint.pprint(packet['_source']['layers']['btatt'])
