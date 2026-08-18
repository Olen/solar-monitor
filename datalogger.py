from datetime import datetime, timedelta
import time
import logging
import json
import requests
import paho.mqtt.client as paho
import socket




class DataLoggerMqtt():
    def __init__(self, broker, port, prefix=None, username=None, password=None, hostname=None, device_types=None):
        logging.debug("Creating new MQTT-logger")
        if prefix == None:
            prefix = "solar-monitor"
        self.broker = broker
        # section -> plugin type (e.g. "battery_1" -> "Meritsun"); used to group
        # each physical unit's entities into a Home Assistant Device.
        self.device_types = device_types or {}
        # section -> BLE advertised alias (e.g. "12V100Ah-081"); filled in when a
        # device resolves, shown as the HA Device model.
        self.aliases = {}
        # Command (.../set) topics we must stay subscribed to. The broker drops
        # subscriptions on every reconnect (clean session), so on_connect
        # re-subscribes these — without it, switches stop responding after the
        # first network blip on an unreliable link.
        self._command_topics = set()
        if not hostname:
            hostname = socket.gethostname()

        # A UNIQUE, stable client id. Using the bare hostname collides with any
        # other service on the host that connects as the hostname; MQTT brokers
        # evict the older client on a duplicate id, so the two keep kicking each
        # other off — endless reconnects, and command subscriptions torn down
        # every time. on_connect re-subscribes all command topics after any
        # reconnect, which keeps switches working over an unreliable link.
        client_id = "solar-monitor-{}".format(hostname)
        cb_api_version = getattr(paho, "CallbackAPIVersion", None)
        if cb_api_version is not None:                                     #  create client object on paho-mqtt>=2.x
            self.client = paho.Client(paho.CallbackAPIVersion.VERSION1, client_id)
        else:                                                              #  create client object on older paho-mqtt
            self.client = paho.Client(client_id)

        if username and password:
            self.client.username_pw_set(username=username,password=password)

        self.client.on_publish = self.on_publish                            # assign function to callback
        self.client.on_message = self.on_message                            # attach function to callback
        self.client.on_subscribe = self.on_subscribe                        # attach function to callback
        self.client.on_connect = self.on_connect                            # re-subscribe on (re)connect
        self.client.on_log = self.on_log

        self.client.connect(broker, port)                                   # establish connection
        self.client.loop_start()                                            # start the loop

        self.sensors = []
        self.sets = {}
        if not prefix.endswith("/"):
            prefix = prefix + "/"
        self._prefix = prefix
        self.trigger = {}
        self._listener_created = {}

    @property
    def prefix(self):
        return self._prefix

    @prefix.setter
    def prefix(self, val):
        if not val.endswith("/"):
            val = val + "/"
        self._prefix = val

    def publish(self, device, var, val, refresh=False):
        topic = "{}{}/{}/state".format(self.prefix, device, var)
        if topic not in self.sensors or refresh:
            if "power_switch" in var:
                self.create_switch(device, var)
                self.create_listener(device, var)
            else:
                # Publish (or refresh) the retained discovery config. Do NOT
                # delete it first: a retained config republish updates HA in
                # place, whereas deleting removes the entity and — if the
                # recreate is lost on an unreliable link — leaves it gone in HA
                # even though the broker still retains the config. This is why
                # entities went missing after a container restart, which resets
                # self.sensors and so re-ran this block for every entity.
                self.create_sensor(device, var)
            self.sensors.append(topic)
        logging.debug("Publishing to MQTT {}: {} = {}".format(self.broker, topic, val))
        # Switch state at QoS 1 so a toggle during a disconnect is delivered on
        # reconnect rather than silently dropped; high-frequency sensor state
        # stays QoS 0 (it refreshes constantly anyway).
        qos = 1 if "power_switch" in var else 0
        ret = self.client.publish(topic, val, qos=qos, retain=True)
        if "power_switch" in var and time.time() > self._listener_created[device, var] + 300:
            self.create_listener(device, var)

    def _device_block(self, device):
        """The Home Assistant 'device' object shared by every entity of one
        physical unit. Entities carrying the same identifiers are grouped under
        a single Device in HA (e.g. all of battery_1's sensors)."""
        block = {
            "identifiers": ["{}_{}".format(self.prefix[:-1], device)],
            "name": "{} {}".format(self.prefix[:-1].capitalize(),
                                    device.replace("_", " ").title()),
        }
        dtype = self.device_types.get(device)
        if dtype:
            block["manufacturer"] = dtype        # plugin/protocol, e.g. Meritsun
        alias = self.aliases.get(device)
        if alias:
            block["model"] = alias               # BLE advertised name, e.g. 12V100Ah-081
        elif dtype:
            block["model"] = dtype
        return block

    def set_device_alias(self, device, alias):
        """Record a device's BLE advertised alias for its HA Device 'model'.
        Called when the device resolves, before its entities are created."""
        if alias:
            self.aliases[device.strip()] = alias.strip()

    def set_available(self, device, online):
        """Publish a device's availability so HA shows all its entities as
        'Unavailable' (not a stale value) when it is not connected."""
        topic = "{}{}/availability".format(self.prefix, device.strip())
        self.client.publish(topic, "online" if online else "offline", qos=1, retain=True)

    def create_switch(self, device, var):
        topic = "{}{}/{}/state".format(self.prefix, device, var)
        logging.debug("Creating MQTT-switch {}".format(topic))
        ha_topic = "homeassistant/switch/{}/{}/config".format(device, var)
        val = {
            "name": var.replace("_", " ").title(),
            "unique_id": "{}_{}_{}".format(self.prefix[:-1], device, var),
            "state_topic": topic,
            "command_topic": "{}{}/{}/set".format(self.prefix, device, var),
            "payload_on": 1,
            "payload_off": 0,
            "device": self._device_block(device),
            "availability_topic": "{}{}/availability".format(self.prefix, device),
            "payload_available": "online",
            "payload_not_available": "offline",
        }
        # QoS 1: discovery configs must survive an unreliable link, or the entity
        # never appears in Home Assistant.
        ret = self.client.publish(ha_topic, json.dumps(val), qos=1, retain=True)


    def create_sensor(self, device, var):
        topic = "{}{}/{}/state".format(self.prefix, device, var)
        logging.debug("Creating MQTT-sensor {}".format(topic))
        ha_topic = "homeassistant/sensor/{}/{}/config".format(device, var)
        val = {
            "name": var.replace("_", " ").title(),
            "unique_id": "{}_{}_{}".format(self.prefix[:-1], device, var),
            "state_topic": topic,
            "force_update": True,
            "device": self._device_block(device),
            "availability_topic": "{}{}/availability".format(self.prefix, device),
            "payload_available": "online",
            "payload_not_available": "offline",
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
            val['device_class'] = "voltage"
            val['icon'] = "mdi:flash"
            val['unit_of_measurement'] = "V"
        elif var == "current" or var == "charge_current" or var == "input_current":
            val['device_class'] = "current"
            val['icon'] = "mdi:current-dc"
            val['unit_of_measurement'] = "A"
        elif var.endswith("_state"):
            val['device_class'] = "enum"
            val['options'] = ["charging", "standby", "discharging"]
        elif var == "charge_cycles":
            val['icon'] = "mdi:recycle"
        elif var == "health":
            val['icon'] = "mdi:heart-flash"
        elif "battery" in device and "cell" in var:
            val['icon'] = "mdi:battery"
            val['unit_of_measurement'] = "mV"
            val['device_class'] = "voltage"
        elif "battery" in device:
            val['icon'] = "mdi:battery"
        elif "regulator" in device:
            val['icon'] = "mdi:solar-power"
        elif "inverter" in device:
            val['icon'] = "mdi:current-ac"
        elif "rectifier" in device:
            val['icon'] = "mdi:current-ac"

        # QoS 1: discovery configs must survive an unreliable link, or the entity
        # never appears in Home Assistant.
        ret = self.client.publish(ha_topic, json.dumps(val), qos=1, retain=True)

    def delete_switch(self, device, var):
        ha_topic = "homeassistant/switch/{}/{}/config".format(device, var)
        ret = self.client.publish(ha_topic, payload=None)

    def delete_sensor(self, device, var):
        ha_topic = "homeassistant/sensor/{}/{}/config".format(device, var)
        ret = self.client.publish(ha_topic, payload=None)

    def create_listener(self, device, var):
        topic = "{}{}/{}/set".format(self.prefix, device, var)
        logging.info("Creating MQTT-listener {}".format(topic))
        self._command_topics.add(topic)
        try:
            self.client.subscribe((topic, 1))
            self._listener_created[device, var] = time.time()
        except Exception as e:
            logging.error("MQTT: {}".format(e))
        self.sets.setdefault(device, [])



    def on_publish(self, client, userdata, result):             #create function for callback
        logging.debug("Published to MQTT")

    def on_connect(self, client, userdata, flags, rc):
        # The broker drops subscriptions on reconnect (clean session), so
        # re-subscribe every command topic here — otherwise switches go dead
        # after the first network blip. Runs on the initial connect too.
        if self._command_topics:
            logging.info("MQTT (re)connected (rc=%s); re-subscribing %d command topic(s)",
                         rc, len(self._command_topics))
        for topic in self._command_topics:
            try:
                client.subscribe((topic, 1))
            except Exception as e:
                logging.error("MQTT re-subscribe failed for {}: {}".format(topic, e))

    def on_subscribe(self, client, userdata, mid, granted_qos):
        # granted_qos of 128 (0x80) means the broker DENIED the subscription
        # (usually an ACL) — the client would then silently never receive on
        # that topic, which is exactly how a command/switch subscription fails.
        try:
            denied = [q for q in granted_qos if q is not None and q >= 128]
        except TypeError:
            denied = []
        if denied:
            logging.error("MQTT subscription DENIED by broker (mid=%s granted_qos=%s) — check broker ACL", mid, granted_qos)
        else:
            logging.info("MQTT subscribed ok (mid=%s granted_qos=%s)", mid, granted_qos)


    def on_message(self, client, userdata, message):
        # This runs on the paho network-loop thread. An unhandled exception here
        # kills that thread and takes the whole MQTT client down (no more state
        # published, no more commands received) until the process restarts — so
        # everything is guarded, and a device we don't yet track is created on
        # the fly rather than raising KeyError.
        try:
            topic = message.topic
            payload = message.payload.decode("utf-8")
            logging.info("MQTT command received on {}: {}".format(topic, payload))
            parts = topic.split("/")
            if len(parts) < 4:                 # expect {prefix}/{device}/{var}/set
                return
            device, var = parts[-3], parts[-2]
            self.sets.setdefault(device, []).append((var, payload))
            trigger = self.trigger.get(device)
            if trigger is not None:
                trigger.set()
        except Exception as e:
            logging.error("MQTT on_message failed for {}: {}".format(
                getattr(message, "topic", "?"), e))

    def on_log(self, client, userdata, level, buf):
        logging.debug("MQTT {}".format(buf))


# 2021-07-07 17:46:22,051 INFO    : MQTT message received 1                     
# 2021-07-07 17:46:22,052 INFO    : MQTT set: {'regulator': [('power_switch', '1')], 'battery_1': [], 'battery_2': [], 'inverter_1': []}                                                                             
# 2021-07-07 17:46:22,054 INFO    : [regulator] MQTT-poller-thread regulator Event happened...
# 2021-07-07 17:46:22,055 INFO    : [regulator] MQTT-msg: power_switch -> 1     
# 2021-07-07 17:46:22,136 INFO    : [battery_2] Sending new data current: -1.4  
# 2021-07-07 17:46:22,156 INFO    : [inverter_1] Sending new data voltage: 230.0   
# 2021-07-07 17:46:22,260 WARNING : [regulator] Write to characteristic failed for: [0000ffd1-0000-1000-8000-00805f9b34fb] with error [In Progress]         


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
            device_types = {}
            for section in config.sections():
                dtype = config.get(section, 'type', fallback=None)
                if dtype and config.get(section, 'mac', fallback=None):
                    device_types[section] = dtype
            self.mqtt = DataLoggerMqtt(
                config.get('mqtt', 'broker'),
                config.get('mqtt', 'port', fallback=1883),
                prefix=config.get('mqtt', 'prefix', fallback=None),
                username=config.get('mqtt', 'username', fallback=None),
                password=config.get('mqtt', 'password', fallback=None),
                hostname=config.get('mqtt', 'hostname', fallback=None),
                device_types=device_types
            )
        self.logdata = {}

       
    # logdata  
    # - device_id
    #       var1:   
    #           ts: timestamp
    #           value: value     
    #
    #
    # }

    def set_device_alias(self, device, alias):
        """Record a device's BLE alias so the MQTT logger can show it as the HA
        Device model. No-op when MQTT is not configured."""
        if self.mqtt:
            self.mqtt.set_device_alias(device, alias)

    def set_available(self, device, online):
        """Mark a device online/offline in HA. No-op without MQTT."""
        if self.mqtt:
            self.mqtt.set_available(device, online)

    def log(self, device, var, val):
        # Only log modified data
        # <timestamp> <device> <var>: <val>
        device = device.strip()
        # ts = datetime.now().isoformat(' ', 'seconds')
        ts = datetime.now()
        logging.debug("[{}] All data {}: {}".format(device, var, val))
        if device not in self.logdata:
            self.logdata[device] = {}
        if var not in self.logdata[device]:
            self.logdata[device][var] = {}
            self.logdata[device][var]['ts'] = ts
            self.logdata[device][var]['value'] = None

        if self.logdata[device][var]['value'] != val:
            self.logdata[device][var]['ts'] = ts
            self.logdata[device][var]['value'] = val
            logging.info("[{}] Sending new data {}: {}".format(device, var, val))
            self.send_to_server(device, var, val)
        elif self.logdata[device][var]['ts'] < datetime.now()-timedelta(minutes=10):
            self.logdata[device][var]['ts'] = ts
            self.logdata[device][var]['value'] = val
            # logging.debug("Sending data to server due to long wait")
            logging.info("[{}] Sending refreshed data {}: {}".format(device, var, val))
            self.send_to_server(device, var, val, True)




    def send_to_server(self, device, var, val, refresh=False):
        if self.mqtt:
            self.mqtt.publish(device, var, val, refresh)
        if self.url:
            logging.info("[{}] Sending data to {}".format(device, self.url))
            ts = datetime.now().isoformat(' ', 'seconds')
            payload = {'device': device, var: val, 'ts': ts}
            header = {'Content-type': 'application/json', 'Accept': 'text/plain', 'Authorization': 'Bearer {}'.format(self.token)}
            try:
                response = requests.post(url=self.url, json=payload, headers=header, timeout=(5, 10))
            except requests.exceptions.RequestException as e:
                logging.error("Failed to POST to {}: {}".format(self.url, e))



