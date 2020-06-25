from datetime import datetime, timedelta
import logging
import json
import requests
import paho.mqtt.client as paho




class DataLoggerMqtt():
    def __init__(self, broker, port, prefix=None):
        logging.debug("Creating new MQTT-logger")
        if prefix == None:
            prefix = "solar-monitor"
        self.broker = broker
        self.client = paho.Client(prefix)                                   # create client object
        self.client.on_publish = self.on_publish                            # assign function to callback
        self.client.on_message = self.on_message                            # attach function to callback
        self.client.on_subscribe = self.on_subscribe                        # attach function to callback
        self.client.on_log = self.on_log

        self.client.connect(broker, port)                                   # establish connection
        self.client.loop_start()                                            # start the loop

        self.sensors = []
        self.sets = []
        if not prefix.endswith("/"):
            prefix = prefix + "/"
        self._prefix = prefix

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
            self.create_sensor(device, var)
            self.create_listener(device, var)
        logging.debug("Publishing to MQTT {}: {} = {}".format(self.broker, topic, val))
        ret = self.client.publish(topic, val, retain=True)


    def create_sensor(self, device, var):
        topic = "{}{}/{}/state".format(self.prefix, device, var)
        logging.debug("Creating MQTT-sensor {}".format(topic))
        ha_topic = "homeassistant/sensor/{}/{}/config".format(device, var)
        val = {
            "name": "{}_{}_{}".format(self.prefix[:-1], device, var),
            "state_topic": topic
        }
        ret = self.client.publish(ha_topic, json.dumps(val), retain=True)
        self.sensors.append(topic)


    def create_listener(self, device, var):
        topic = "{}{}/{}/set".format(self.prefix, device, var)
        logging.debug("Creating MQTT-listener {}".format(topic))
        try:
            self.client.subscribe((topic, 0))
        except Exception as e:
            logging.error("MQTT: {}".format(e))



    def on_publish(self, client, userdata, result):             #create function for callback
        logging.debug("Published to MQTT")

    def on_subscribe(self, client, userdata, mid, granted_qos):
        # logging.debug("Subscribed to MQTT topic {}".format(userdata))
        pass


    def on_message(self, client, userdata, message):
        topic = message.topic
        payload = message.payload.decode("utf-8")
        self.sets.append((topic, payload))
        logging.debug("MQTT message received {}".format(str(message.payload.decode("utf-8"))))
        logging.debug("MQTT message topic={}".format(message.topic))
        logging.debug("MQTT message qos={}".format(message.qos))
        logging.debug("MQTT message retain flag={}".format(message.retain))

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
            self.mqtt = DataLoggerMqtt(config.get('mqtt', 'broker'), 1883, prefix=config.get('mqtt', 'prefix'))
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


