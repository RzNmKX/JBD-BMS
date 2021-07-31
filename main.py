#!/usr/bin/env python3 
# from https://github.com/tgalarneau/bms

from bluepy.btle import Peripheral, DefaultDelegate, BTLEException
import struct
import argparse
import json
import time
import binascii
import atexit
import paho.mqtt.client as paho
import logging
import sys
  
parser = argparse.ArgumentParser(description='Fetches and outputs JBD bms data')
parser.add_argument("-b", "--BLEaddress", help="Device BLE Address", default="a4:c1:38:1d:d6:5d", required=False)
parser.add_argument("-i", "--interval", type=int, help="Data fetch interval", default=60, required=False)
parser.add_argument("-m", "--meter", help="meter name", default="jbdbms", required=False)
parser.add_argument("-v", '--verbose', help='Enable verbose output to stdout', default=False, action='store_true')
args = parser.parse_args() 
z = args.interval
meter = args.meter

if args.verbose:
	logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
else:
	logging.basicConfig(stream=sys.stdout, level=logging.INFO)

topic ="data/bms/bms_info"
gauge ="data/bms/cell_info"
broker="mqtt"
meter_name = "bms"
port=1883

def disconnect():
	mqtt.disconnect()
	logging.info("broker disconnected")

def cellinfo1(data):			# process pack info
	infodata = data
	i = 4                       # Unpack into variables, skipping header bytes 0-3
	volts, amps, remain, capacity, cycles, mdate, balance1, balance2 = struct.unpack_from('>HhHHHHHH', infodata, i)
	volts=volts/100
	amps = amps/100
	capacity = capacity/100
	remain = remain/100
	watts = volts*amps  							# adding watts field for dbase
	message1 = {
		"meter": meter_name,
		"volts": volts,
		"amps": amps,
		"watts": watts, 
		"remain": remain, 
		"capacity": capacity, 
		"cycles": cycles 
	}
	ret = mqtt.publish(gauge, payload=json.dumps(message1), qos=0, retain=False) # not sending mdate (manufacture date)
	logging.debug(f"current battery info: {message1}")    
	bal1 = (format(balance1, "b").zfill(16))		
	message2 = {
		"meter": meter_name,							# using balance1 bits for 16 cells
		"c16" : int(bal1[0:1]), 
		"c15" : int(bal1[1:2]),                 # balance2 is for next 17-32 cells - not using
		"c14" : int(bal1[2:3]), 							
		"c13" : int(bal1[3:4]), 
		"c12" : int(bal1[4:5]), 				# bit shows (0,1) charging on-off			
		"c11" : int(bal1[5:6]), 
		"c10" : int(bal1[6:7]), 
		"c09" : int(bal1[7:8]), 
		"c08" : int(bal1[8:9]), 
		"c07" : int(bal1[9:10]), 
		"c06" : int(bal1[10:11]), 		
		"c05" : int(bal1[11:12]), 
		"c04" : int(bal1[12:13]) , 
		"c03" : int(bal1[13:14]), 
		"c02" : int(bal1[14:15]), 
		"c01" : int(bal1[15:16])
	}
	ret = mqtt.publish(gauge, payload=json.dumps(message2), qos=0, retain=False)
	logging.debug(f"balancing status: {message2}")
def cellinfo2(data):
	infodata = data  
	i = 0                          # unpack into variables, ignore end of message byte '77'
	protect,vers,percent,fet,cells,sensors,temp1,temp2,b77 = struct.unpack_from('>HBBBBBHHB', infodata, i)
	temp1 = (temp1-2731)/10
	temp2 = (temp2-2731)/10			# fet 0011 = 3 both on ; 0010 = 2 disch on ; 0001 = 1 chrg on ; 0000 = 0 both off
	prt = (format(protect, "b").zfill(16))		# protect trigger (0,1)(off,on)
	message1 = {
		"meter": meter_name,
		"ovp" : int(prt[0:1]), 			# overvoltage
		"uvp" : int(prt[1:2]), 			# undervoltage
		"bov" : int(prt[2:3]), 		# pack overvoltage
		"buv" : int(prt[3:4]),			# pack undervoltage 
		"cot" : int(prt[4:5]),		# current over temp
		"cut" : int(prt[5:6]),			# current under temp
		"dot" : int(prt[6:7]),			# discharge over temp
		"dut" : int(prt[7:8]),			# discharge under temp
		"coc" : int(prt[8:9]),		# charge over current
		"duc" : int(prt[9:10]),		# discharge under current
		"sc" : int(prt[10:11]),		# short circuit
		"ic" : int(prt[11:12]),        # ic failure
		"cnf" : int(prt[12:13])	    # config problem
	}
	ret = mqtt.publish(topic, payload=json.dumps(message1), qos=0, retain=False)
	logging.debug(f"alarm statuses: {message1}")
	message2 = {
		"meter": meter_name,
		"protect": protect,
		"percent": percent,
		"fet": fet,
		"cells": cells,
		"temp1": temp1,
		"temp2": temp2
	}
	ret = mqtt.publish(topic, payload=json.dumps(message2), qos=0, retain=False)    # not sending version number or number of temp sensors
	logging.debug(f"basic BMS current condition info: {message2}")
def cellvolts1(data):			# process cell voltages
	global cells1
	celldata = data             # Unpack into variables, skipping header bytes 0-3
	i = 4
	cell1, cell2, cell3, cell4, cell5, cell6, cell7, cell8 = struct.unpack_from('>HHHHHHHH', celldata, i)
	cells1 = [cell1, cell2, cell3, cell4, cell5, cell6, cell7, cell8] 	# needed for max, min, delta calculations
	message = {
		"meter" : meter_name, 
		"cell1": cell1, 
		"cell2": cell2,
		"cell3": cell3, 
		"cell4": cell4,
		"cell5": cell5, 
		"cell6": cell6, 
		"cell7": cell7, 
		"cell8": cell8 
	}
	ret = mqtt.publish(gauge, payload=json.dumps(message), qos=0, retain=False)
	logging.debug(f"cell voltages: {message}")
	cellsmin = min(cells1)          # min, max, delta
	cellsmax = max(cells1)
	delta = cellsmax-cellsmin
	mincell = (cells1.index(min(cells1))+1)
	maxcell = (cells1.index(max(cells1))+1)
	message1 = {
		"meter": meter,
		"mincell": mincell,
		"cellsmin": cellsmin,
		"maxcell": maxcell,
		"cellsmax": cellsmax,
		"delta": delta
	}
	ret = mqtt.publish(gauge, payload=json.dumps(message1), qos=0, retain=False)
	#really don't need this data. it can be inferred from other messages
	#print(f"cellvolts1 - message1: {message1}")
class MyDelegate(DefaultDelegate):		    # notification responses
	def __init__(self):
		DefaultDelegate.__init__(self)
	def handleNotification(self, cHandle, data):
		hex_data = binascii.hexlify(data) 		# Given raw bytes, get an ASCII string representing the hex values
		text_string = hex_data.decode('utf-8')  # check incoming data for routing to decoding routines
		if text_string.find('dd04') != -1:	                             # x04 (1-8 cells)	
			cellvolts1(data)
		elif text_string.find('dd03') != -1:                             # x03
			cellinfo1(data)
		elif text_string.find('77') != -1 and len(text_string) == 28 or len(text_string) == 36:	 # x03
			cellinfo2(data)		
try:
	logging.info("starting MPP BMS monitoring")
	logging.info(f"attempting to connect to BLE device {args.BLEaddress}")		
	bms = Peripheral(args.BLEaddress,addrType="public")
except BTLEException as ex:
	logging.warn("unable to connect. waiting 10 seconds and trying again.")
	time.sleep(10)
	logging.warn(f"attempting to connect again to BLE device {args.BLEaddress}")
	bms = Peripheral(args.BLEaddress,addrType="public")
except BTLEException as ex:
	logging.critical("unable to connect to BLE device, exiting")
	exit()
else:
	logging.info(f"connected to {args.BLEaddress}")

atexit.register(disconnect)
mqtt = paho.Client("control3")      #create and connect mqtt client
mqtt.connect(broker,port)     
bms.setDelegate(MyDelegate())		# setup bt delegate for notifications

	# write empty data to 0x15 for notification request   --  address x03 handle for info & x04 handle for cell voltage
	# using waitForNotifications(5) as less than 5 seconds has caused some missed notifications
while True:
	result = bms.writeCharacteristic(0x15,b'\xdd\xa5\x03\x00\xff\xfd\x77',False)		# write x03 w/o response cell info
	bms.waitForNotifications(5)
	result = bms.writeCharacteristic(0x15,b'\xdd\xa5\x04\x00\xff\xfc\x77',False)		# write x04 w/o response cell voltages
	bms.waitForNotifications(5)
	time.sleep(z)
   
