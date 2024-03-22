# Reverse engineering the protocols

Many of these devices use different protocols between the device and the app.
They might be similar, but it seems lke every vendor want to invent the wheel, and to be frank - the wheels have a varying degree of roundness...

Something is documented, something can be found in other github-repos where someone else has done the same, and some must just be guessed.

But after working woth some of the devices for a while, you learn what to look for, and how to interpret the different data.

## Requirements
The easiest way to start is to use an Android phone (maybe an iPhone, I have no idea how those work), the app for the device you want to reverse engieer, a computer with Wireshark and a USB cable for your phone.

## To begin
* Install wireshark on your computer
* Install the app on your phone and make sure it connects to the device.  Hopefully, there are no passwords or pin codes or other things you need to worry about
* Enable bluetooth-debugging (HCI snooping) on your phone.  
* * Exactly how this is done varies from model to model and different Android versions.  Google it.
* Start the app again
* Look a bit around.  Take some notes of the values you see (Voltage, current, temperature, charge cycles...). Also note down the timestamp
* Leave everything for a minute or so to keep some steady values.
* Connect a charger. Note the timestamp.  Check what the app reports of charge power, changes in voltage etc.
* Leave everything for a minute or so to keep some steady values.
* Disconnect the charger. Note down new values from the app, along with the timestamp of the disconnect.
* Leave everything for a minute or so to keep some steady values.
* Connect some load - some lamps, something whatever that will draw power from the battery
* Note down the values from the app and the timestamps
* Disconnect the load
* Stop the app
* Disable bluetooth debugging on your phone and retrieve the bluetooth logs
* * Exactly how this is done varies from model to model and different Android versions.  Google it.


## Interpreting the data
Now you should have a dump of the bluetooth traffic.

Start by opening the bluetooth-dump in Wireshark.

Create a filter with `bluetooth.addr=xx:xx:xx:xx:xx` (the mac-address of your device)

Now you take out your notes and start looking for patterns.

First you start looking whether there are typical "Send Write Command", followed by one or more "Rcvd Handle Value Notification", or if there are just a bunch of "Rcvd Handle Value Notification"
- If you see a lot of Write Commands, it probably means that your device needs polling.
- Look at the write command packets, and see if they repeat in some kind of pattern.  There will typically be 2-3-4-5 different Write Commands that are repeated at regular intervals.
- In Wireshark, you can then find the data that is sent, and note it down.

In the "Value Notifications", you can find the data from the device.  In Wireshark you will typically see the data as hex-values, use a hex-calculator (can easily be found online if you dont have one), and try out the different values.

If you have multiple Value Notificatons following each other within a short timeframe, or just after a "Write Command", they probably belong together, so you should add them together as one string.

For example, if you have received the following hex stream: `01034c0d010d050d030d01ee49ee49ee49ee49ee49ee49ee49ee49ee49ee49ee49ee49ee49ee49ee49ee49ee49ee49ee49ee49ee49ee49ee49ee49ee49ee49ee49ee490d050d0100020001000405338ad0` split it up into bytes:

`01 03 4c 0d 01 0d 05 0d 03 0d 01 ee 49 ee 49 ee 49 ee 49 ee 49 ee 49 ee 49 ee 49 ee 49 ee 49 ee 49 ee 49 ee 49 ee 49 ee 49 ee 49 ee 49 ee 49 ee 49 ee 49 ee 49 ee 49 ee 49 ee 49 ee 49 ee 49 ee 49 ee 49 0d 05 0d 01 00 02 00 01 00 04 05 33 8a d0`

One thing to remeber is that quite often, the Notifications will begin with some kind of ID, there is a big chance one of the first bytes represents the "length" of the string, and there is usually some kind of checksum at the end.

So lets check this out.  From my dump, I can easily see that all the Notifications starts with "0103", so that is probably some kind of ID or "Beginning of message" code.

What about `4c`?

`4C` = 76 - and look. The message is 81 bytes long...Two bytes header, the length-field is 1 byte, and maybe the last two bytes are a checksum?

Let's check https://crccalc.com/

Dump all the bytes except the last two into the text field, select "Input: HEX" and click "CRC-16"

CRC16/MODBUS comes back as "0xD08A", while the last two bytes in the tring si `8ad0`. It's the same bytes, but in the opposite order - but that is just big/little endian, so we are pretty sure those last two bytes are a checksum.

Next we have a series of `0d 01 0d 05 0d 03 0d 01`  what are those?

`0D` = 13, could this be the voltage?
`01` =  1, so if the reading from the app was 13.1, that could be it?

But we have 0d 05 - 13 and 5? And then 0d 03 - 13 and 3, and then 0d 01 again.  So it looks a bit strange.

What if these are two byte long values?

`0D01` is 3329 - wasn't that exactly what the value for Voltage in Cell 1?
`0D05` is 3333 and `0D03` is 3331 - They to matches the Voltage in Cell 2 and 3. And 4 was 3329 again. We are on to something!

Note this, and check if these matches also in the later packet dumps when we have connected a charger and some load.

The we get a bunch of `ee 49`.  So many repetitions?  Probably some kind of filler. Nothing to worry about for now.

The we get to the end: `...0d 05 0d 01 00 02 00 01 00 04 05 33 8a d0`

0D05 and 0D01 looks kind of like a repetition of Cell 2 and 4 or something?  Let's see if they change in later packets.

`00 01`, `00 02` and `00 04` might have some meaning.  Some kind of status?  Let's see if they change in later packets.

`05` .. maybe?

But `05 31` - this equals 1331, and lo! The app showed 13.31 V.  

Quite happy so far. Lets verify the cell data and voltage in the later packets.

### Another Notification:

`010332025800000000000000000000026c00000000026c026c0258000000000064006430d330d430d4000600000000000000000000a1c2`


`01 03 32 02 58 00 00 00 00 00 00 00 00 00 00 02 6c 00 00 00 00 02 6c 02 6c 02 58 00 00 00 00 00 64 00 64 30 d3 30 d4 30 d4 00 06 00 00 00 00 00 00 00 00 00 00 a1 c2`

Ok, again 0103 in the beginning.  Nice.

Lets verify the checksum again.  Use the online tool, and check that CRC16/MODBUS comes back as `C2A1`.  Different byte order, same bytes.  We're happy with that.

`32` = 50 and the packet is 55 bytes long.  So that confirms 2 byte ID, 1 byte length 50 bytes of data and 2 bytes checksum.

Let's look at the data again:

* `02` is a 2. Could be anything.
* `58` = 88 - Could be the SOC? Does it match the SOC in the app?
* `0258` = 600 - Does not ring a bell
* `5800` = 22582 - Not matching anything in the app...

A bunch of 0.  Let's just check if any of these change when we start charging or using the battery

* `026C` = 620.  Nah
* `6C` = 108.  Can't find anything there.
* `6C00` = 27648.  Still nothing.
* `6C02` = 27650 ...

Then this 0258 comes again. But still unknwon

More zeros.  But then a 64.

`64` = 100, and the app reported 100% SOC.  Could be worth looking at.

One more `64` and then `30D3`

`30D3` is 12499 - Woho!  Didn't the app just report that the battery currently had 124.99 Ah?
And that means that `30D4` = 12500, and the total capacity of the battery is 125 Ah.  This looks promising!

Just after those, we have a `06` and the app did report 6 charge cycles.  Lets not this down and keep an eye on it after a few charges.

And then just 0 until the checksum.  

### Summary

This is a very simple example.  I have seen devices that use far more complex protocols than just reading the values directly.  See for instance the [Meritsun plugin](https://github.com/Olen/solar-monitor/blob/07d39817d3f345994e886ebea3bdb830234820d3/plugins/Meritsun/__init__.py#L25) in this project.

And even for this, for instance the temperature is quite hard to figure out.  It is actually hidden in the "0258" in the beginning of the last Notification,

It turns out you need to read the 2 bytes `0258`, which equals 600. Then you need to subtract 380, and you get 220, which is 22°C.  This means that it will report values from `00 00` - Which is -38°C, and that 0°C is `01 7C`.

I found this after placing the battery outdoors for a few hours, and noticing that these values changed, and then it was just a matter of trying to match these values with that the app reported.

But it is hopefully a simple guide to get you started.  

Good luck.


