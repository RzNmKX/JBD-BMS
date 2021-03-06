#!/usr/bin/env python
# -*- coding: utf-8 -*-
# from https://github.com/KHoos/mqtt-to-influxdb-forwarder

# forwarder.py - forwards IoT sensor data from MQTT to InfluxDB
#
# Copyright (C) 2016 Michael Haas <haas@computerlinguist.org>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software Foundation,
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301  USA

import argparse
import paho.mqtt.client as mqtt
from influxdb import InfluxDBClient
import json
import re
import logging
import sys
import requests.exceptions

class MessageStore(object):

	def store_msg(self, node_name, measurement_name, value):
		raise NotImplementedError()

class InfluxStore(MessageStore):

	logger = logging.getLogger("forwarder.InfluxStore")

	def __init__(self, host, port, username, password_file, database):
		password = "power" #open(password_file).read().strip()
		self.influx_client = InfluxDBClient(
			host=host, port=port, username=username, password=password, database=database)
		self.influx_client.create_database(database)


	def store_msg(self, database, sensor, value):
		influx_msg = {
			'measurement': database,
			'tags': {'sensor': sensor},
			'fields': {'value' : value}
		}
		self.logger.debug("Writing InfluxDB point: %s", influx_msg)
		try:
			self.influx_client.write_points([influx_msg])
		except requests.exceptions.ConnectionError as e:
			self.logger.exception(e)
		except Exception as e:
			self.logger.exception(e)

class MessageSource(object):

	def register_store(self, store):
		if not hasattr(self, '_stores'):
			self._stores = []
		self._stores.append(store)

	@property
	def stores(self):
		# return copy
		return list(self._stores)

def isFloat(str_val):
  try:
    float(str_val)
    return True
  except ValueError:
    return False
 
def convertToFloat(str_val):
    if isFloat(str_val):
        fl_result = float(str_val)
        return fl_result
    else:
        return str_val

class MQTTSource(MessageSource):

	logger = logging.getLogger("forwarder.MQTTSource")

	def __init__(self, host, port, node_names, stringify_values_for_measurements):
		self.host = host
		self.port = port
		self.node_names = node_names
		self.stringify = stringify_values_for_measurements
		self._setup_handlers()

	def _setup_handlers(self):
		self.client = mqtt.Client()

		def on_connect(client, userdata, flags, rc):
			self.logger.info("Connected with result code  %s", rc)
			# subscribe to /node_name/wildcard
			#for node_name in self.node_names:
			# topic = "{node_name}/#".format(node_name=node_name)
			topic = "JBD-BMS/#"
			self.logger.info("Subscribing to topic %s", topic)
			client.subscribe(topic)

		def on_message(client, userdata, msg):
			self.logger.debug("Received MQTT message for topic %s with payload %s", msg.topic, msg.payload)
			list_of_topics = msg.topic.split('/')
			measurement = list_of_topics[1]
			if list_of_topics[len(list_of_topics)-1] == 'unit':
				value = None
			else:
				decoded_payload = msg.payload.decode('UTF-8')
				decoded_json = json.loads(decoded_payload)
				for key in decoded_json:
					if isFloat(decoded_json[key]):
						for store in self.stores:
							#print(f"about to write {measurement}---{key}---{float(decoded_json[key])}")
							store.store_msg(measurement,key,float(decoded_json[key])	)

		self.client.on_connect = on_connect
		self.client.on_message = on_message

	def start(self):
		logging.info(f"connecting to mqtt on host: {self.host} and port: {self.port}")
		self.client.connect(self.host, self.port)
		# Blocking call that processes network traffic, dispatches callbacks and
		# handles reconnecting.
		# Other loop*() functions are available that give a threaded interface and a
		# manual interface.
		self.client.loop_forever()


def main():
	parser = argparse.ArgumentParser(
		description='MQTT to InfluxDB bridge for IOT data.')
	parser.add_argument('--mqtt-host', default="mqtt", help='MQTT host')
	parser.add_argument('--mqtt-port', default=1883, help='MQTT port')
	parser.add_argument('--influx-host', default="dashboard", help='InfluxDB host')
	parser.add_argument('--influx-port', default=8086, help='InfluxDB port')
	parser.add_argument('--influx-user', default="power", help='InfluxDB username')
	parser.add_argument('--influx-pass-file', default="pass.file", help='InfluxDB password file')
	parser.add_argument('--influx-db', default="power", help='InfluxDB database')
	parser.add_argument('--node-name', default='JDB-BMS', help='Sensor node name', action="append")
	parser.add_argument('--stringify-values-for-measurements', required=False,	help='Force str() on measurements of the given name', action="append")
	parser.add_argument('--verbose', help='Enable verbose output to stdout', default=False, action='store_true')
	args = parser.parse_args()

	if args.verbose:
		logging.basicConfig(format="%(asctime)s:%(levelname)s:%(message)s", stream=sys.stdout, level=logging.DEBUG)
	else:
		logging.basicConfig(format="%(asctime)s:%(levelname)s:%(message)s", stream=sys.stdout, level=logging.INFO)
		
	print("creating influxstore")
	store = InfluxStore(host=args.influx_host, port=args.influx_port, username=args.influx_user, password_file=args.influx_pass_file, database=args.influx_db)
	print("creating mqttsource")
	source = MQTTSource(host=args.mqtt_host,
						port=args.mqtt_port, node_names=args.node_name,
						stringify_values_for_measurements=args.stringify_values_for_measurements)
	print("registering store")
	source.register_store(store)
	print("start")
	source.start()

#if __name__ == '__main__':
main()