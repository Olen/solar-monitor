import os
import sys
import time
from time import sleep, strftime
from gpiozero import CPUTemperature
from datetime import datetime
import argparse
import requests

# Local to RPi CSV format log file
log_filename = "/home/pi/data_log-" + datetime.now().strftime("%Y-%m-%d")+".csv"
# "~/" for "/home/pi/" did not work

# Server related init's
auth_token='965e32b3aa2b96fc55686eb85a29e573'
URL = 'http://hytta.olen.net/solar/api/'


# Default for Command Line Params
poll_int = 5
dev_name = '120AH'
dev_type = 'MERITSUN'
serv_name = 'http://hytta.olen.net/solar/api/'


def log_csv_file(dname, daddr, cur, volt, soc, temp, cap, cyc, state, health):
    print ("File name is "+log_filename)

	file = open(log_filename, "a")
	i=0

	if os.stat(log_filename).st_size == 0:
		file.write("DeviceName,DeviceAddress,Current,Voltage,SoC,Temperature,Capacity,Cycles,Status,Health\n")

# now = datetime.now().strftime("%H:%M:%S")
# file.write(str(now)+","+str(temp)+","+str(i)+","+str(-i)+","+str(i-10)+","+str(i+5)+","+str(i*i)+"\n")
	file.write(str(dname)+","+str(daddr)+","+str(cur)+","+str(volt)+","+str(soc)+","+str(temp)+","+str(cap)+","+str(cyc)+","+str(state)+","+str(health)+"\n")
	file.flush()
	file.close()


def parse_command_line():
# count the arguments
	arguments = len(sys.argv) - 1
	print ("the script is called with %i arguments" %(arguments))

# python3 <file>.py --pint <polling-time-interval> --dev <ble-device-name> --type <type-of-ble-dev> --server <http-server-address>

	parser = argparse.ArgumentParser()
	parser.add_argument('--pint', nargs=1, type=int, choices=range(1, 1440), help='<polling-time-interval> the BLE device (Periodic) polling interval in minutes (up to 24 hrs)')
	parser.add_argument('--dev', nargs=1, help='<ble-device-name> the BLE device name to poll')
	parser.add_argument('--type', nargs=1, help='<type-of-ble-dev> «type» of bluetooth-device - e.g., MERITSUN, TBENERGY or SOLARLINK')
	parser.add_argument('--server', nargs=1, help='<http-server-address> http(s) server to send the captured data to, e.g. https://abc.com/')

	args = parser.parse_args()

	print("args= "+str(args)+"\n")

# now, namespace pint = <polling-time-interval>, dev = <ble-device-name> ... ... 
	# check for values 
	if args.pint:
		print("set <polling-time-interval> to %s\n" %args.pint)
		global poll_int
		poll_int = args.pint
	if args.dev:
		global dev_name
		dev_name = args.dev
	if args.type:
		global dev_type
		dev_type = args.type
	if args.server:
		global serv_name
		serv_name = args.server

	print("pint= "+str(args.pint)+" dev="+str(args.dev)+" type="+str(args.type)+" server="+str(args.server)+"\n")
# check for values 
	if args.pint:
		print("set <polling-time-interval> to %s" % args.pint)
	


# payload = { 
# 	'some': 'data', 
# 	'more': 'other data' 
# }
# {"battery_1_soc":"99","battery_1_volt":"13.3","battery_1_capacity":"105.1","battery_1_status":"Standby","battery_1_temperature":null,"panel_soc":null,"panel_volt":null,"panel_current":null,"panel_power":null,"load_volt":null,"load_current":null,"load_power":null,"load_switch":null,"last_updated":"2019-12-11 16:31:25"}

def send_to_server(payload):
	header1 = {'Content-type': 'application/json', 'Accept': 'text/plain', 'Authorization': 'Bearer ' + auth_token}
	try:
	   response = requests.post(url=URL, json=payload, headers=header1)
	except TimeoutError:
		print("Connection timed out!")
	else:
		print(response)



