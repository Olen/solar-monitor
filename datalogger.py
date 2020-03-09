from datetime import datetime
import logging
import requests



class DataLogger():
    def __init__(self, url, token):
        self.url = url
        self.token = token
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
        ts = datetime.now().isoformat(' ', 'seconds')
        if device not in self.logdata:
            self.logdata[device] = {}
        if var not in self.logdata[device]:
            self.logdata[device][var] = {}
            self.logdata[device][var]['ts'] = None
            self.logdata[device][var]['value'] = None

        if self.logdata[device][var]['value'] != val:
            self.logdata[device][var]['ts'] = ts
            self.logdata[device][var]['value'] = val
            logging.info("{} {} {}: {}".format(ts, device, var, val))
            self.send_to_server(device, var, val)
                                


    def send_to_server(self, device, var, val):
        ts = datetime.now().isoformat(' ', 'seconds')
        payload = {'device': device, var: val, 'ts': ts}
        # logging.info("Sending to server {}".format(payload))
        # return
        header = {'Content-type': 'application/json', 'Accept': 'text/plain', 'Authorization': 'Bearer {}'.format(self.token)}
        try:
            response = requests.post(url=self.url, json=payload, headers=header)
        except TimeoutError:
            logging.error("Connection to {} timed out!".format(self.url))
        else:
            logging.debug(response)


