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

Short UUIDs are shorthand for the Bluetooth Base UUID
`0000xxxx-0000-1000-8000-00805f9b34fb`, so `ffe0` and the 128-bit form above
name the same service. Vendor-defined UUIDs sit outside that base, and have no
short form: Victron uses `306b0001-…`, Nordic `6e400001-…`.

We then *subscribe to* or *write to* one or more of these characteristics.

Finding these UUIDs, and working out what the bytes mean, is a job of its own:
[REVERSE-ENGNEER.md](REVERSE-ENGNEER.md) walks through sniffing the vendor app
with Wireshark. Note that many devices send nothing at all until they receive
some kind of init.

## Read the standard services first

Two SIG-assigned services need no reverse engineering:

- `0000180f-…` **Battery Service** — characteristic `00002a19-…` is the state of
  charge, a single byte, 0–100.
- `0000180a-…` **Device Information** — `00002a29-…` manufacturer, `00002a24-…`
  model, `00002a26-…` firmware revision, all plain strings.

A pack that exposes `180f` gives you SOC for free, and `180a` tells you which
protocol family to expect.


## A service UUID identifies the module, not the protocol

The shipped plugins use these:

| Service | Notify characteristic | Used by |
|---|---|---|
| `0000ffe0-…` | `0000ffe4-…` | Meritsun, Topband |
| `0000fff0-…` | `0000fff1-…` | SolarLink (SRNE), RenogyBatt |
| `306b0001-…` | `306b0002/0003/0004-…` | VEDirect |
| `6e400001-…` (Nordic UART) | `6e400003-…` | Hacien |

A match narrows the transport, not the protocol. `0000ffe0-…`/`0000ffe1-…` is
the factory default of the HM-10 (TI CC2541) serial module, changeable by AT
command and left alone by most vendors; none of `ffe0`, `fff0`, `ff00` or `ffd0`
is SIG-assigned. Of the 43 protocols decoded in
[aiobmsble](https://github.com/patman15/aiobmsble), a dozen mutually
incompatible ones sit on `ffe0` and another dozen on `fff0`. Nordic UART and
Microchip/ISSC transparent UART (`49535343-…`) are generic serial-over-BLE
services in the same way.

The vendor is sometimes in the UUID itself — hex-decode the leading groups.
`49535343` is ASCII `ISSC`, `57616c6b697a` is `Walkiz`, and Felicity's
`49535458`/`49535258` are `ISTX`/`ISRX`.

## Config
The Config class defines some parameters for the plugin:

- `DEVICE_ID` - Some devices send this as part of the notifications
- `SEND_ACK` - Some devices require that an "ack" is returned for all received packets.  If this parameter is set to `True` the `Util` class needs a function `ackData` that generates the ack packets
- `NEED_POLLING` - Some devices require active polling, while others will just send a continous stream of updates.  If this is set to `True`, the device will be polled every second for updates
- `NOTIFY_SERVICE_UUID` - The UUID that contains the notifications
- `NOTIFY_CHAR_UUID` - The characteristics within the `NOTIFY_SERVICE_UUID` that we will subscribe to.  Can be a single UUID or a list of UUIDs.  Every characteristic in the list is subscribed to: VEDirect spreads its data across three, and subscribing to one of them yields no data and a link the device drops
- `WRITE_SERVICE_UUID`- The service UUID containing the characteristics we will send write requests to 
- `WRITE_CHAR_UUID_POLLING` - The charactersitcs UUID we send polling requests, acks etc. to
- `WRITE_CHAR_UUID_COMMANDS` - The characteristics UUID we send data to for commands.  E.g turing power on or off on a regulator etc.



## Util

The Util class is bound to a PowerDevice object and is used to read, write and parse data from the physical devices.  There is only a few functions that need to be exposed to the PowerDevice object:

### init
__init__() of the class expects a `PowerDevice` (an object defined in `solardevice.py`)  as its only parameter.  The plugin will then update this device-object as data is recieved.

### Updates
When we recieve an update, the class function `notificationUpdate(data, char)` is called with the raw data and the UUID of the characteristic we recieved the data from.  This function is then responsible for parsing the data and will then update the `PowerDevice` object.  The function should return True if the message was understood and handled, and False if it was not.

A notification carries at most ATT_MTU − 3 bytes, 20 by default. Frames longer
than that arrive split across several calls, and one call can hold the tail of
one frame and the head of the next, so anything longer needs reassembly:
`Meritsun` buffers the stream and re-syncs on its marker bytes rather than
trusting notification boundaries.

### Ack
The class function `ackData(data)` is required if the device expects an ack for each notification it sends. This function must generate and return a valid "ack-packet" for the received `data`

### Polling
If polling is required, the class function `pollRequest()` must return the packet we need to send to the device to poll if for new data.

### Commands
Some devices accept commands, such as turning power on and off on an inverter.  To send commands to a device, we call the function `cmdRequest(command, value)` with two paramters, the *command*, and a *value*. E.g. *command* = `power_switch` and *value* = `1  or `0` for "on" or "off".

The function must return a *list* of packets that should be sent to the device.


### Payloads

Everything written to the device — from `pollRequest()`, `ackData()` and
`cmdRequest()` — must be bytes-like: `bytes` or `bytearray`. A plain list of
ints is coerced on the way out, but returning bytes directly says what you mean.


## Decoding helpers

Three modules cover the wire formats the shipped plugins use. A device speaking
something similar should use them rather than growing its own copy:

- `modbus.py` — `bytes_to_int()`, `high_byte()`, `low_byte()`,
  `validate_frame()` (length, function code and CRC-16/MODBUS) and
  `ack_payload()`. Used by `SolarLink` and `RenogyBatt`.
- `asciihex.py` — `field_value()` for ASCII-hex fields written least significant
  pair first, and `checksum_matches()` for the 16-bit additive checksum. Used by
  `Meritsun` and `Topband`. The same family is documented independently as
  Topband/Ective in
  [aiobmsble](https://github.com/patman15/aiobmsble/blob/main/aiobmsble/bms/topband_bms.py)
  — different frame length and marker bytes, same ASCII-hex payload,
  little-endian fields, additive checksum and deci-Kelvin temperature.
- `codec.py` — `to_signed()` and the two's-complement wrap constants, for signed
  readings in any format.


## Capturing what your plugin receives

Wireshark shows what the *vendor app* exchanges. Once your plugin connects, you
want the bytes your own code receives, which is a different question — framing
can differ between what the app negotiates and what you get.

The `Meritsun` and `Hacien` plugins write every notification to
`/tmp/<device-alias>.log` when `debug = True` is set in `[monitor]`:

```python
if self.PowerDevice.config.getboolean('monitor', 'debug', fallback=False):
    with open(f"/tmp/{self.PowerDevice.alias()}.log", 'a') as debugfile:
        debugfile.write(f"{datetime.now()} <- {data.hex()}\n")
```

Each line is one notification, timestamped, exactly as the parser sees it. These
files grow by a few MB per minute per device, so turn debug off when finished.


## Testing

Captured notifications make a test that needs no hardware: replay them and
assert the decoded values. `tests/test_meritsun_parser.py` does this with six
real notifications and pins voltage, SOC, temperature and capacity — enough to
catch a framing change without a battery on the desk.
