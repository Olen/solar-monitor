# Write your own plugin

Plugins are simple python modules, and only need two classes that are used by the main process. 

`class Config()` and `class Util()`

They can be put in their own sub directory under "plugins/" and only require a `__init__.py` file so they can be imported by the solardevice.py script.

See the existing plugins for examples.

Reading and writing to a BT device is done using Service UUIDs and Characteristic UUIDs, where a Service UUID is the "parent" of one or more Characteristics.

Typically, you can have a hierarchy like

- Service UUID: 0000ffe**0**-0000-1000-8000-00805f9b34fb
  - Characteristics: 0000ffe**1**-0000-1000-8000-00805f9b34fb 
  - Characteristics: 0000ffe**2**-0000-1000-8000-00805f9b34fb 
  - Characteristics: 0000ffe**3**-0000-1000-8000-00805f9b34fb 
  - Characteristics: 0000ffe**4**-0000-1000-8000-00805f9b34fb 

We then *subscribe to* or *write to* one or more of these characteristics.

These UUIDs can be found either by reverse engineering the original app, by sniffing the packets going over the bluetooth connection from the original app, or by using various tools to connect directly to the device with bluetooth and poke around until you find something of interest.  But note that many devices need some kind of "init" before they send any data.  The easiest is probably to run e.g. wireshark to sniff the packets going over the air, and try to figure out what happens.

## Config
The Config class defines some parameters for the plugin:

- `DEVICE_ID` - Some devices send this as part of the notifications
- `SEND_ACK` - Some devices require that an "ack" is returned for all received packets.  If this parameter is set to `True` the `Util` class needs a function `ackData` that generates the ack packets
- `NEED_POLLING` - Some devices require active polling, while others will just send a continous stream of updates.  If this is set to `True`, the device will be polled every second for updates
- `NOTIFY_SERVICE_UUID` - The UUID that contains the notifications
- `NOTIFY_CHAR_UUID` - The characteristics within the `NOTIFY_SERVICE_UUID` that we will subscribe to.  Can be a single UUID or a list of UUIDs
- `WRITE_SERVICE_UUID`- The service UUID containing the characteristics we will send write requests to 
- `WRITE_CHAR_UUID_POLLING` - The charactersitcs UUID we send polling requests, acks etc. to
- `WRITE_CHAR_UUID_COMMANDS` - The characteristics UUID we send data to for commands.  E.g turing power on or off on a regulator etc.



## Util

The Util class is bound to a PowerDevice object and is used to read, write and parse data from the physical devices.  There is only a few functions that need to be exposed to the PowerDevice object:

### init
__init__() of the class expects a `PowerDevice` (an object defined in `solardevice.py`)  as its only parameter.  The plugin will then update this device-object as data is recieved.

### Updates
When we recieve an update, the class function `notificationUpdate(data, char)` is called with the raw data and the UUID of the characteristic we recieved the data from.  This function is then responsible for parsing the data and will then update the `PowerDevice` object.  The function should return True if the message was understood and handled, and False if it was not.

### Ack
The class function `ackData(data)` is required if the device expects an ack for each notification it sends. This function must generate and return a valid "ack-packet" for the received `data`

### Polling
If polling is required, the class function `pollRequest()` must return the packet we need to send to the device to poll if for new data.

### Commands
Some devices accept commands, such as turning power on and off on an inverter.  To send commands to a device, we call the function `cmdRequest(command, value)` with two paramters, the *command*, and a *value*. E.g. *command* = `power_switch` and *value* = `1  or `0` for "on" or "off".

The function must return a *list* of packets that should be sent to the device.


