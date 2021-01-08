from datetime import datetime, timedelta
import time
import logging
import json
import requests
import paho.mqtt.client as paho
import socket




class DataLoggerMqtt():
    def __init__(self, broker, port, prefix=None, username=None, password=None):
        logging.debug("Creating new MQTT-logger")
        if prefix == None:
            prefix = "solar-monitor"
        self.broker = broker
        self.client = paho.Client("{}".format(socket.gethostname()))        #  create client object
        if username and password:
            self.client.username_pw_set(username=username,password=password)

        self.client.on_publish = self.on_publish                            # assign function to callback
        self.client.on_message = self.on_message                            # attach function to callback
        self.client.on_subscribe = self.on_subscribe                        # attach function to callback
        self.client.on_log = self.on_log

        self.client.connect(broker, port)                                   # establish connection
        self.client.loop_start()                                            # start the loop

        self.sensors = []
        self.sets = {}
        if not prefix.endswith("/"):
            prefix = prefix + "/"
        self._prefix = prefix
        self.trigger = {}

    @property
    def prefix(self):
        return self._prefix

    @prefix.setter
    def prefix(self, val):
        if not val.endswith("/"):
            val = val + "/"
        self._prefix = val

    def publish(self, device, var, val):
        topic = "{}{}/{}/state".format(self.prefix, device, var)
        if topic not in self.sensors:
            if "power_switch" in var:
                # self.delete_switch(device, var)
                # time.sleep(2)
                self.create_switch(device, var)
                self.create_listener(device, var)
            else:
                self.delete_sensor(device, var)
                time.sleep(2)
                self.create_sensor(device, var)
            self.sensors.append(topic)
            time.sleep(0.5)
        logging.debug("Publishing to MQTT {}: {} = {}".format(self.broker, topic, val))
        ret = self.client.publish(topic, val, retain=True)

    def create_switch(self, device, var):
        topic = "{}{}/{}/state".format(self.prefix, device, var)
        logging.debug("Creating MQTT-switch {}".format(topic))
        ha_topic = "homeassistant/switch/{}/{}/config".format(device, var)
        val = {
            "name": "{} {} {}".format(self.prefix[:-1].capitalize(), device.replace("_", " ").title(), var.replace("_", " ").title()),
            "unique_id": "{}_{}_{}".format(self.prefix[:-1], device, var),
            "state_topic": topic,
            "command_topic": "{}{}/{}/set".format(self.prefix, device, var),
            "payload_on": 1,
            "payload_off": 0,
        }
        ret = self.client.publish(ha_topic, json.dumps(val), retain=True)


    def create_sensor(self, device, var):
        topic = "{}{}/{}/state".format(self.prefix, device, var)
        logging.debug("Creating MQTT-sensor {}".format(topic))
        ha_topic = "homeassistant/sensor/{}/{}/config".format(device, var)
        val = {
            "name": "{} {} {}".format(self.prefix[:-1].capitalize(), device.replace("_", " ").title(), var.replace("_", " ").title()),
            "unique_id": "{}_{}_{}".format(self.prefix[:-1], device, var),
            "state_topic": topic,
            "force_update": True,
        }
        if var == "temperature":
            val['device_class'] = "temperature"
            val['unit_of_measurement'] = "°C"
        elif var == "soc":
            val['device_class'] = "battery"
            val['unit_of_measurement'] = "%"
        elif var == "power" or var == "charge_power" or var == "input_power":
            val['device_class'] = "power"
            val['unit_of_measurement'] = "W"
        elif var == "voltage" or var == "charge_voltage" or var == "input_voltage":
            val['icon'] = "mdi:flash"
            val['unit_of_measurement'] = "V"
        elif var == "current" or var == "charge_current" or var == "input_current":
            val['icon'] = "mdi:current-dc"
            val['unit_of_measurement'] = "A"
        elif var == "charge_cycles":
            val['icon'] = "mdi:recycle"
        elif var == "health":
            val['icon'] = "mdi:heart-flash"
        elif "battery" in device:
            val['icon'] = "mdi:battery"
        elif "regulator" in device:
            val['icon'] = "mdi:solar-power"
        elif "inverter" in device:
            val['icon'] = "mdi:current-ac"
        elif "rectifier" in device:
            val['icon'] = "mdi:current-ac"

        ret = self.client.publish(ha_topic, json.dumps(val), retain=True)

    def delete_switch(self, device, var):
        ha_topic = "homeassistant/switch/{}/{}/config".format(device, var)
        ret = self.client.publish(ha_topic, payload=None)

    def delete_sensor(self, device, var):
        ha_topic = "homeassistant/sensor/{}/{}/config".format(device, var)
        ret = self.client.publish(ha_topic, payload=None)

    def create_listener(self, device, var):
        topic = "{}{}/{}/set".format(self.prefix, device, var)
        logging.info("Creating MQTT-listener {}".format(topic))
        try:
            self.client.subscribe((topic, 0))
        except Exception as e:
            logging.error("MQTT: {}".format(e))
        self.sets[device] = []



    def on_publish(self, client, userdata, result):             #create function for callback
        logging.debug("Published to MQTT")

    def on_subscribe(self, client, userdata, mid, granted_qos):
        # logging.debug("Subscribed to MQTT topic {}".format(userdata))
        pass


    def on_message(self, client, userdata, message):
        topic = message.topic
        payload = message.payload.decode("utf-8")
        logging.info("MQTT message received {}".format(str(message.payload.decode("utf-8"))))
        logging.debug("MQTT message topic={}".format(message.topic))
        logging.debug("MQTT message qos={}".format(message.qos))
        logging.debug("MQTT message retain flag={}".format(message.retain))
        (prefix, device, var, crap) = topic.split("/")
        self.sets[device].append((var, payload))
        logging.info("MQTT set: {}".format(self.sets))
        if self.trigger[device]:
            self.trigger[device].set()

    def on_log(self, client, userdata, level, buf):
        logging.debug("MQTT {}".format(buf))




class DataLogger():
    def __init__(self, config):
        # config.get('datalogger', 'url'), config.get('datalogger', 'token')
        logging.debug("Creating new DataLogger")
        self.url = None
        self.mqtt = None
        if config.get('datalogger', 'url', fallback=None):
            self.url = config.get('datalogger', 'url')
            self.token = config.get('datalogger', 'token')
        if config.get('mqtt', 'broker', fallback=None):
            self.mqtt = DataLoggerMqtt(config.get('mqtt', 'broker'), 1883, prefix=config.get('mqtt', 'prefix'), username=config.get('mqtt', 'username'), password=config.get('mqtt', 'password'))
        self.logdata = {}

       
    # logdata  
    # - device_id
    #       var1:   
    #           ts: timestamp
    #           value: value     
    #
    #
    # }

    def log(self, device, var, val):
        # Only log modified data
        # <timestamp> <device> <var>: <val>
        device = device.strip()
        # ts = datetime.now().isoformat(' ', 'seconds')
        ts = datetime.now()
        if device not in self.logdata:
            self.logdata[device] = {}
        if var not in self.logdata[device]:
            self.logdata[device][var] = {}
            self.logdata[device][var]['ts'] = None
            self.logdata[device][var]['value'] = None

        if self.logdata[device][var]['value'] != val:
            self.logdata[device][var]['ts'] = ts
            self.logdata[device][var]['value'] = val
            logging.info("[{}] Sending new data {}: {}".format(device, var, val))
            self.send_to_server(device, var, val)
        elif self.logdata[device][var]['ts'] < datetime.now()-timedelta(minutes=15):
            self.logdata[device][var]['ts'] = ts
            self.logdata[device][var]['value'] = val
            # logging.debug("Sending data to server due to long wait")
            logging.info("[{}] Sending refreshed data {}: {}".format(device, var, val))
            self.send_to_server(device, var, val)




    def send_to_server(self, device, var, val):
        if self.mqtt:
            self.mqtt.publish(device, var, val)
        if self.url:
            ts = datetime.now().isoformat(' ', 'seconds')
            payload = {'device': device, var: val, 'ts': ts}
            header = {'Content-type': 'application/json', 'Accept': 'text/plain', 'Authorization': 'Bearer {}'.format(self.token)}
            try:
                response = requests.post(url=self.url, json=payload, headers=header)
            except TimeoutError:
                logging.error("Connection to {} timed out!".format(self.url))



