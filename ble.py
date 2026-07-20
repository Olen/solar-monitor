"""Asyncio BLE transport (bleak) for solar-monitor.

Replaces the abandoned `gatt` library. One asyncio loop (owned by BleManager,
Task 3) runs in a daemon thread; each device gets one `maintain_device` task.
bleak uses AcquireNotify for notifications, which — unlike gatt's dbus-signal
StartNotify — keeps up with high-rate notifiers (the Meritsun batteries).
"""
import asyncio
import logging

from connection import backoff_seconds


async def _hold(dev, client, stop_event, poll_interval, sleep):
    """Hold a resolved connection, polling if the device needs it, until the
    link drops or shutdown is requested."""
    while not stop_event.is_set() and client.is_connected:
        if dev.need_polling and dev.device_write_characteristic_polling:
            data = dev.get_poll_data()
            if data:
                try:
                    await client.write_gatt_char(dev.device_write_characteristic_polling, data)
                except Exception as e:
                    logging.debug("[%s] poll write failed: %r", dev.logger_name, e)
                    break
        await sleep(poll_interval)


async def maintain_device(dev, connect_lock, client_factory, stop_event,
                          poll_interval=1.0, base_backoff=10.0, max_backoff=300.0,
                          jitter=5.0, rand=None, sleep=None):
    """Keep one device connected + notifying until stop_event is set.

    Establishment is serialized by `connect_lock` (the controller allows one LE
    Create Connection in flight at a time). After a good connection we retry
    promptly; after a failed attempt we back off exponentially (with jitter).
    """
    if sleep is None:
        sleep = asyncio.sleep
    attempt = 0
    while not stop_event.is_set():
        client = client_factory(dev.mac_address)
        connected = False
        try:
            async with connect_lock:
                logging.info("[%s] Connecting to %s", dev.logger_name, dev.mac_address)
                await client.connect()
                dev.on_connected(client)
                if dev.notify_uuid:
                    await client.start_notify(dev.notify_uuid, dev.notify_callback)
                connected = True
            await _hold(dev, client, stop_event, poll_interval, sleep)
        except Exception as e:
            logging.error("[%s] connection error: %r", dev.logger_name, e)
        finally:
            dev.on_disconnected()
            try:
                if getattr(client, "is_connected", False):
                    await client.disconnect()
            except Exception:
                pass
        if stop_event.is_set():
            break
        if connected:
            attempt = 0                              # had a good connection — retry promptly
            continue
        attempt += 1
        await sleep(backoff_seconds(attempt, base_backoff, max_backoff, jitter, rand))
