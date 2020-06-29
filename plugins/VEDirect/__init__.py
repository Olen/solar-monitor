import logging                                                     

class Config():
    SEND_ACK  = False
    NEED_POLLING = False

class Util():

    def __init__(self, power_device):                  
        self.PowerDevice = power_device                  

    def notificationUpdate(self):
        # Run when we receive a BLE-notification
        pass

    def pollRequest(self):
        # Create a poll-request to ask for new data
        pass

    def cmdRequest(self):
        # Create a command-request to run a command on the device
        pass

    def ackData(self):
        # Create an ack-packet
        pass

    def validate(self):
        pass
