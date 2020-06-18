from datetime import datetime, timedelta
import logging
import json
import requests
import paho.mqtt.client as paho




class DataLoggerMqtt():
    def __init__(self, broker, port):
        self.broker = broker
        self.client = paho.Client("home-assistant")                           #create client object
        self.client.on_publish = self.on_publish                          #assign function to callback
        self.client.connect(broker,port)                                 #establish connection
        self.sensors = []

    def create_sensor(self, device, var):
        topic = "homeassistant/sensor/{}/{}/config".format(device, var)
        val = {
            "name": "leveld_{}_{}".format(device, var),
            "state_topic": "leveld/sensor/{}/{}/state".format(device, var)
        }
        # if var ==
        ret = self.client.publish(topic, json.dumps(val))
        self.sensors.append("leveld/sensor/{}/{}/state".format(device, var))


    def on_publish(self, client, userdata, result):             #create function for callback
        logging.debug("Published to MQTT")

    def publish(self, device, var, val):
        topic = "leveld/sensor/{}/{}/state".format(device, var)
        if topic not in self.sensors:
            logging.debug("Creating MQTT-sensor {}/{}".format(device, var))
            self.create_sensor(device, var)
        logging.debug("Publishing to MQTT {}: {}/{}/state = {}".format(self.broker, device, var, val))
        ret = self.client.publish(topic, val)





class DataLogger():
    def __init__(self, url, token):
        self.url = url
        self.token = token
        self.logdata = {}
        self.mqtt = DataLoggerMqtt('ha.olen.net', 1883)

       
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
            logging.info("Sending new data {} {} {}: {}".format(ts.isoformat(' ', 'seconds'), device, var, val))
            self.send_to_server(device, var, val)
        elif self.logdata[device][var]['ts'] < datetime.now()-timedelta(minutes=15):
            self.logdata[device][var]['ts'] = ts
            self.logdata[device][var]['value'] = val
            # logging.debug("Sending data to server due to long wait")
            logging.info("Sending refreshed data {} {} {}: {}".format(ts.isoformat(' ', 'seconds'), device, var, val))
            self.send_to_server(device, var, val)




    def send_to_server(self, device, var, val):
        self.mqtt.publish(device, var, val)
        ts = datetime.now().isoformat(' ', 'seconds')
        payload = {'device': device, var: val, 'ts': ts}
        # logging.info("Sending to server {}".format(payload))
        # return
        header = {'Content-type': 'application/json', 'Accept': 'text/plain', 'Authorization': 'Bearer {}'.format(self.token)}
        try:
            response = requests.post(url=self.url, json=payload, headers=header)
        except TimeoutError:
            logging.error("Connection to {} timed out!".format(self.url))
        '''
        # else:
        #     logging.debug(response)
        '''


