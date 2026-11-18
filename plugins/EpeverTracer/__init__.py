#!/usr/bin/env python3

"""
EPever Tracer Solar Charge Controller Plugin for Olen/solar-monitor coupled to
a BLE-RJ45-D RJ45 Bluetooth adapter (www.epever.com/product/epever-ble-rj45-d)
Tested with a Photonic Universe branded Epever Tracer (P)TR3210AN.
"""
# pylint: disable=line-too-long, too-few-public-methods, invalid-name

import logging
import struct
import threading
import time

logger = logging.getLogger(__name__)


class Config:
    """
    Configuration class for solar-monitor for Epever Tracer over a BLE-RJ45-D.
    """

    # --- Device & Protocol Behavior Flags ---
    DEVICE_ID = 1           # Default Modbus Unit ID
    NEED_POLLING = True     # Device requires active query polling
    SEND_ACK = False        # Host does not need to send explicit ACK frames

    # --- GATT Service & Characteristic UUIDs ---
    NOTIFY_SERVICE_UUID = "00002b00-0000-1000-8000-00805f9b34fb"
    WRITE_SERVICE_UUID = "00002b00-0000-1000-8000-00805f9b34fb"

    # Characteristics under service 00002b00-...
    NOTIFY_CHAR_UUID = "00002b10-0000-1000-8000-00805f9b34fb"
    WRITE_CHAR_UUID_POLLING = "00002b11-0000-1000-8000-00805f9b34fb"
    WRITE_CHAR_UUID_COMMANDS = "00002b11-0000-1000-8000-00805f9b34fb"

    # --- Modbus Function Codes ---
    FC_READ_INPUT = 0x04
    FC_WRITE_COIL = 0x05

    # --- Modbus Register Block Addresses ---
    REG_LIVE_DATA = 0x3100  # 18 Registers (36 bytes: PV, Batt, Load, Temps)
    REG_BATTERY_SOC = 0x311A  # 1 Register (2 bytes: Battery SOC %)
    REG_STATUS = 0x3201  # 2 Registers (4 bytes: Charging & Discharging Flags)
    REG_ENERGY_STATS = 0x330C  # 8 Registers (16 bytes: Today/Month/Year/Total Energy)
    COIL_LOAD_CTRL = 0x0002  # Load Switch Coil Address

    # --- Status Lookup Tables ---
    CHARGING_STATES = {
        0: "Standby",
        1: "Float",
        2: "Boost (PWM/MPPT)",
        3: "Equalization"
    }


class Util:
    """
    Stateful device protocol engine matching the solar-monitor Util interface.
    Enables modbus commands to the Epever Tracer.
    """
    # pylint: disable=too-many-instance-attributes

    def __init__(self, device):
        self.device = device

        # Safely bind to device.data dictionary object
        if hasattr(self.device, "data") and isinstance(self.device.data, dict):
            self.data = self.device.data
        else:
            self.data = {}
            if hasattr(self.device, "data"):
                self.device.data = self.data

        # Convert ConfigParser / SectionProxy or dict safely into a standard dict
        raw_config = getattr(device, "config", {})
        if hasattr(raw_config, "items"):
            self.config = dict(raw_config.items())
        elif isinstance(raw_config, dict):
            self.config = raw_config
        else:
            self.config = {}

        # Read unit_id and include_history
        self.unit_id = int(self.config.get("unit_id", getattr(Config, "DEVICE_ID", 1)))

        history_val = self.config.get("include_history", False)
        if isinstance(history_val, str):
            self.include_history = history_val.lower() in ("true", "1", "yes")
        else:
            self.include_history = bool(history_val)

        # Polling state and timeout tracking.
        # NOTE: solar-monitor's device_poller() calls pollRequest() on a
        # fixed 1-second tick regardless of whether a response has arrived
        # yet, and always writes whatever it gets back. The 0x330C energy
        # stats block answers noticeably slower than the live-data/status
        # registers (it's pulled from flash-backed counters, not live ADC
        # values), so treating "1 tick without a reply" as a timeout was
        # re-sending a fresh query before the controller had finished
        # assembling its previous answer, pre-empting it every time. We
        # track real elapsed time instead, and only actually retransmit
        # once RESPONSE_TIMEOUT_S has genuinely passed - staying quiet
        # (pollRequest returns nothing, so the core skips writing that
        # tick) while a response may still be on its way. The same value
        # also bounds how long we'll wait for a command's ACK (see
        # cmd_pending below) - both are just "how long is reasonable to
        # wait for this device to answer anything", so one constant covers
        # both rather than two numbers that have to be kept in sync.
        self.RESPONSE_TIMEOUT_S = 3.5
        self.last_request_time = None
        self.poll_index = 0
        self.awaiting_response = False
        self.stage_retries = 0
        self.max_retries = 3

        # solar-monitor drives pollRequest() from the device_poller thread
        # and cmdRequest() from a separate mqtt_poller thread - both write
        # to the same characteristic independently. If a coil command goes
        # out while a poll request is also in flight, the controller's
        # BLE-serial bridge can return a single notification that mashes
        # the two responses together (e.g. an 8-byte ACK bleeding into a
        # 36-byte stage response), corrupting both. _state_lock protects
        # the shared poll/command bookkeeping below, which is touched from
        # three different threads: device_poller (pollRequest), mqtt_poller
        # (cmdRequest), and the BLE notification callback (notificationUpdate).
        self._state_lock = threading.Lock()
        self.cmd_pending = False
        self.cmd_sent_time = None

        # Standardized solar-monitor schema keys matching RegulatorDevice expectations
        default_keys = {
            "voltage": 0.0, "current": 0.0, "power": 0.0,
            "charge_voltage": 0.0, "charge_current": 0.0, "charge_power": 0.0,
            "input_voltage": 0.0, "input_current": 0.0, "input_power": 0.0,
            "temperature": 0.0, "battery_temperature": 0.0,
            "soc": 0, "power_switch": 0, "state": "Disconnected", "load_state": "OFF",
            "energy_today": 0.0, "energy_month": 0.0, "energy_year": 0.0, "energy_total": 0.0
        }

        # Initialize default values into self.data and device.entities.<key>.value
        self._update_data(default_keys)

        logger.debug("EPever: Plugin initialized (Unit ID: %s, History: %s)",
                     self.unit_id,
                     self.include_history)

    # Keys that don't map 1:1 onto a PowerDevice property name.
    # ("temperature"/"battery_temperature" properties on PowerDevice store
    # raw deci-Kelvin and are validated against a 1731-3731 range, so we
    # must go through the *_celsius setters instead, or every reading gets
    # silently rejected by validate().)
    _ENTITY_KEY_MAP = {
        "temperature": "temperature_celsius",
        "battery_temperature": "battery_temperature_celsius"
    }

    def _set_entity_value(self, key: str, value):
        """
        Updates self.data (local cache) AND writes straight through to the
        matching property on self.device.entities, since solar-monitor's
        PowerDevice/RegulatorDevice classes expose telemetry as validated
        properties (e.g. `.voltage`), not as a dict of "entity" objects
        with a `.value` attribute.
        Keys with no matching PowerDevice property (e.g. pv_*, load_*, energy_*)
        simply stay in self.data/self.device.data.
        """

        self.data[key] = value

        if hasattr(self.device, "data") and isinstance(self.device.data, dict):
            self.device.data[key] = value

        if hasattr(self.device, "entities"):
            ents = self.device.entities
            attr = self._ENTITY_KEY_MAP.get(key, key)

            if hasattr(ents, attr):
                try:
                    setattr(ents, attr, value)
                except Exception as e:  # pylint: disable=broad-exception-caught
                    logger.debug("EPever: Could not set entities.%s = %s (%s)",
                                 attr, value, e)

    def _update_data(self, updates_dict: dict):
        """
        Updates multiple telemetry entities in batch.
        """

        for k, v in updates_dict.items():
            self._set_entity_value(k, v)

    # --- Byte & Bit Utilities ---

    def Bytes2Int(self, data: bytes, offset: int = 0, length: int = 2, signed: bool = False, little_endian: bool = False) -> int:
        """
        Converts raw byte slices into integer values.
        """
        # pylint: disable=too-many-arguments

        slice_bytes = data[offset: offset + length]
        if not slice_bytes or len(slice_bytes) < length:
            logger.debug("EPever: Bytes2Int failed - insufficient data length at offset %s",
                         offset)
            return 0

        if length == 2:
            fmt = (
                "<h"
                if (signed and little_endian)
                else (">h" if signed else ("<H" if little_endian else ">H"))
            )
            return struct.unpack(fmt, slice_bytes)[0]
        if length == 4:
            if little_endian:
                # EPever 32-bit registers store Low Word then High Word
                low = struct.unpack(">H", slice_bytes[0:2])[0]
                high = struct.unpack(">H", slice_bytes[2:4])[0]
                val = low | (high << 16)
                if signed and (val & 0x80000000):
                    val -= 1 << 32
                return val

            fmt = ">i" if signed else ">I"
            return struct.unpack(fmt, slice_bytes)[0]
        return 0

    def Int2Bytes(self, value: int, length: int = 2) -> bytes:
        """
        Converts integer values into Modbus big-endian bytes.
        """

        if length == 2:
            return struct.pack(">H", value & 0xFFFF)
        if length == 4:
            return struct.pack(">I", value & 0xFFFFFFFF)
        return b""

    # --- CRC16 & Protocol Frame Helpers ---

    def _crc16(self, data: bytes) -> int:
        """
        Calculates Modbus RTU CRC16.
        """

        crc = 0xFFFF
        for byte in data:
            crc ^= byte
            for _ in range(8):
                if crc & 0x0001:
                    crc = (crc >> 1) ^ 0xA001
                else:
                    crc >>= 1
        return crc

    def _verify_crc(self, payload: bytes) -> bool:
        """
        Validates payload length and trailing CRC16 bytes.
        """

        if len(payload) < 4:
            logger.warning("EPever: Payload too short for CRC validation (%s bytes)",
                           len(payload))
            return False
        data, received_crc = payload[:-2], payload[-2:]
        expected_crc = struct.pack("<H", self._crc16(data))
        valid = received_crc == expected_crc
        if not valid:
            logger.warning("EPever: CRC Mismatch! Expected 0x%s, Got 0x%s",
                           expected_crc.hex(), received_crc.hex())
        return valid

    def _build_frame(self, func: int, reg: int, val_or_count: int) -> bytes:
        """
        Builds a Modbus RTU frame with trailing CRC16.
        """

        pdu = struct.pack(">BBHH", self.unit_id, func, reg, val_or_count)
        frame = pdu + struct.pack("<H", self._crc16(pdu))
        logger.debug("EPever: Built Modbus frame [FC: 0x%02X, Reg: 0x%04X, Val/Count: %d] -> %s",
                     func, reg, val_or_count, frame.hex())
        return frame

    # --- Core Polling and Command Requests ---

    def _get_stages(self):
        """
        Single source of truth for the poll cycle: what to request, and how to
        handle the response once it comes back. pollRequest() uses (func, reg,
        count) to build the query; notificationUpdate() uses (expected_bytes,
        handler) to validate and parse the reply. Both always agree on which
        stage self.poll_index refers to, so responses can't be misrouted.
        """

        stages = [
            (Config.FC_READ_INPUT, Config.REG_LIVE_DATA, 18, 36, self.updateSolarPanelAndBatteryState),
            (Config.FC_READ_INPUT, Config.REG_BATTERY_SOC, 1, 2, self.updateBatteryParamInfo),
            (Config.FC_READ_INPUT, Config.REG_STATUS, 2, 4, self.updateParamSettingData),
        ]
        if self.include_history:
            stages.append((Config.FC_READ_INPUT, Config.REG_ENERGY_STATS, 8, 16, self.updateSolarPanelInfo))
        return stages

    def pollRequest(self) -> bytes:
        """
        Generates the next polling query, but only actually transmits when
        appropriate: on the first request for a stage, or once a real
        RESPONSE_TIMEOUT_S has elapsed without a response. Returning b""
        while still within the timeout window tells solar-monitor's
        device_poller() to skip writing this tick, so we don't stomp on a
        response the controller may still be assembling.
        The actual transmission is done by device_poller() in solardevice.py.
        """

        with self._state_lock:
            if self.cmd_pending:
                elapsed = time.time() - self.cmd_sent_time
                if elapsed < self.RESPONSE_TIMEOUT_S:
                    # A command write/ACK round-trip is in progress - stay
                    # off the wire entirely so we don't collide with it.
                    return b""
                # Safety net: the ACK never came back (dropped notification,
                # etc). Don't stall polling forever - log it and resume.
                logger.warning("EPever: No ACK seen %.1fs after command; resuming polling.",
                               elapsed)
                self.cmd_pending = False

            stages = self._get_stages()

            if self.poll_index >= len(stages):
                self.poll_index = 0

            if self.awaiting_response:
                elapsed = time.time() - self.last_request_time
                if elapsed < self.RESPONSE_TIMEOUT_S:
                    # Still within the window - stay quiet and keep waiting.
                    return b""

                self.stage_retries += 1
                if self.stage_retries > self.max_retries:
                    logger.warning("EPever: Timeout on stage %d after %d retries. Advancing stage.",
                                   self.poll_index + 1, self.max_retries)
                    self.poll_index = (self.poll_index + 1) % len(stages)
                    self.stage_retries = 0
                else:
                    logger.debug("EPever: Retry %d/%d for stage %d/%d",
                                 self.stage_retries, self.max_retries, self.poll_index + 1, len(stages))
            else:
                self.stage_retries = 0

            func, reg, count, _, _ = stages[self.poll_index]
            self.awaiting_response = True
            self.last_request_time = time.time()

        logger.debug("EPever: Executing poll request stage %d/%d",
                     self.poll_index + 1, len(stages))

        return self._build_frame(func, reg, count)

    def cmdRequest(self, command: str, value) -> list:
        """
        Generates a control frame payload (e.g. toggling load state).
        The actual transmission is done by mqtt_poller() in solardevice.py.
        """

        logger.debug("EPever: Command request received: '%s' = %s",
                     command, value)
        if command in ["load", "load_state", "toggle_load", "power_switch"]:
            with self._state_lock:
                # Raise the statte_lock *before* building the frame, not after:
                # the GIL can switch threads at any bytecode boundary, so if we
                # built the frame first there'd be a real (if narrow) window
                # where pollRequest() on the poller thread could still see
                # cmd_pending == False and slip a poll write out right before
                # this command's write goes out.
                self.cmd_pending = True
                self.cmd_sent_time = time.time()

            is_on = str(value).lower() in ("1", "true", "on") or value == 1 or value is True
            val = 0xFF00 if is_on else 0x0000
            frame = self._build_frame(Config.FC_WRITE_COIL, Config.COIL_LOAD_CTRL, val)

            return [frame]
        logger.warning("EPever: Unhandled command request '%s'",
                       command)
        return []

    # --- Incoming Data Parsers ---

    def notificationUpdate(self, data: bytes, uuid: str = None) -> dict:
        """
        Main entry point for incoming BLE notification frames.
        Validates frame CRC, updates dictionary in-place, advances polling stage,
        and returns self.data ONLY when the poll cycle is fully finished.
        """

        raw = data
        logger.debug("EPever: Raw notification packet received (%d bytes) on UUID %s: %s",
                     len(raw), uuid, raw.hex())

        # Strip leading null bytes
        while len(raw) > 0 and raw[0] == 0x00:
            raw = raw[1:]

        if not self._verify_crc(raw) or len(raw) < 5:
            logger.error("EPever: Frame validation failed or payload invalid.")
            return None

        func_code = raw[1]
        is_cycle_complete = False

        # Route Write Coil Response (FC 0x05)
        if func_code == Config.FC_WRITE_COIL:
            logger.debug("EPever: Routing FC 0x05 (Write Coil) ACK response: %s",
                         raw.hex())
            self.ackData(raw)

            with self._state_lock:
                self.cmd_pending = False

            return self.data.copy()

        # Route Read Input Registers Response (FC 0x04)
        if func_code == Config.FC_READ_INPUT:
            byte_cnt = raw[2]
            payload = raw[3: 3 + byte_cnt]

            with self._state_lock:
                stages = self._get_stages()
                if self.poll_index >= len(stages):
                    self.poll_index = 0
                _, _, _, expected_bytes, handler = stages[self.poll_index]

                if not self.awaiting_response:
                    # Nothing pending (e.g. a duplicate/late notification after we
                    # already gave up on this stage) - ignore it rather than
                    # guessing what it belongs to.
                    logger.debug("EPever: Ignoring unexpected Read Input response; nothing awaited.")
                    return None

                if byte_cnt != expected_bytes:
                    # A stale response for a stage we've already moved past
                    # (or genuine corruption). Don't apply it - just wait for
                    # the real response, or let the retry/timeout logic recover.
                    logger.warning("EPever: Ignoring mismatched response for stage %d/%d (expected %d bytes, got %d).",
                                   self.poll_index + 1, len(stages), expected_bytes, byte_cnt)
                    return None

                logger.debug("EPever: Routing stage %d/%d response (%d bytes)",
                             self.poll_index + 1, len(stages), byte_cnt)

                self.awaiting_response = False
                self.stage_retries = 0

                handler(payload)

                self.poll_index += 1
                if self.poll_index >= len(stages):
                    self.poll_index = 0
                    is_cycle_complete = True

        else:
            logger.warning("EPever: Unhandled function code 0x%02X",
                           func_code)

        # Return telemetry snapshot ONLY upon full cycle completion
        if is_cycle_complete:
            logger.debug("EPever: Full poll cycle completed. Dispatching telemetry to solar-monitor.")
            return self.data.copy()

        return None

    def ackData(self, payload: bytes):
        """
        Processes write command acknowledgement responses.
        """

        if len(payload) >= 8:
            coil_addr = self.Bytes2Int(payload, offset=2, length=2)
            coil_val = self.Bytes2Int(payload, offset=4, length=2)
            logger.debug("EPever DEBUG: FC05 ACK decoded: coil=0x%04X value=0x%04X",
                         coil_addr, coil_val,)

            if coil_addr == Config.COIL_LOAD_CTRL:
                state_str = "ON" if coil_val == 0xFF00 else "OFF"
                self._update_data({
                    "load_state": state_str,
                    "power_switch": 1 if state_str == "ON" else 0
                })
                logger.debug("EPever: ACK processed - Load switch updated to %s",
                             state_str)

    def updateSolarPanelAndBatteryState(self, payload: bytes):
        """
        Unpacks live telemetry: PV, Battery, Load, and Temperatures (0x3100).
        """

        logger.debug("EPever: Parsing Live Telemetry (0x3100)...")

        # EPever PV offsets: 0x3100 (byte 0) PV Volts, 0x3101 (byte 2) PV Amps, 0x3102-0x3103 (byte 4) PV Watts
        pv_volts = round(self.Bytes2Int(payload, offset=0, length=2) / 100.0, 2)
        pv_amps = round(self.Bytes2Int(payload, offset=2, length=2) / 100.0, 2)
        pv_watts = round(self.Bytes2Int(payload, offset=4, length=4, little_endian=True) / 100.0, 2)

        # EPever Battery offsets: 0x3104 (byte 8) Batt Volts, 0x3105 (byte 10) Batt Amps, 0x3106-0x3107 (byte 12) Batt Watts
        batt_volts = round(self.Bytes2Int(payload, offset=8, length=2) / 100.0, 2)
        batt_amps = round(self.Bytes2Int(payload, offset=10, length=2) / 100.0, 2)
        batt_watts = round(self.Bytes2Int(payload, offset=12, length=4, little_endian=True) / 100.0, 2)

        # EPever Load offsets: 0x310C (byte 24) Load Volts, 0x310D (byte 26) Load Amps, 0x310E (byte 28) Load Watts
        load_volts = round(self.Bytes2Int(payload, offset=24, length=2) / 100.0, 2)
        load_amps = round(self.Bytes2Int(payload, offset=26, length=2) / 100.0, 2)
        load_watts = round(self.Bytes2Int(payload, offset=28, length=4, little_endian=True) / 100.0, 2)

        # Temp offsets: 0x3110 (byte 32) Battery Temp, 0x3111 (byte 34) Controller Temp
        batt_temp = round(self.Bytes2Int(payload, offset=32, length=2, signed=True) / 100.0, 1)
        ctrl_temp = round(self.Bytes2Int(payload, offset=34, length=2, signed=True) / 100.0, 1)

        self._update_data({
            "voltage": load_volts,
            "current": load_amps,
            "power": load_watts,
            "charge_voltage": batt_volts,
            "charge_current": batt_amps,
            "charge_power": batt_watts,
            "input_voltage": pv_volts,
            "input_current": pv_amps,
            "input_power": pv_watts,
            "battery_temperature": batt_temp,
            "temperature": ctrl_temp
        })

        logger.debug("EPever: Parsed Live Telemetry -> PV: %sV/%sW, Batt: %sV/%sA, Load: %sV/%sW",
                     pv_volts, pv_watts, batt_volts, batt_amps, load_volts, load_watts)

    def updateBatteryParamInfo(self, payload: bytes):
        """
        Unpacks Battery SOC percentage (0x311A) - Battery State of Charge
        """

        logger.debug("EPever: Parsing Battery SOC (0x311A)...")
        # EPever SOC offset: 0x311A (byte 0) Battery State of Charge
        soc = self.Bytes2Int(payload, offset=0, length=2)
        self._update_data({
            "soc": soc
        })
        logger.debug("EPever: Parsed Battery SOC -> %s%%",
                     soc)

    def updateParamSettingData(self, payload: bytes):
        """
        Unpacks Charging State and Load Discharge Status flags (0x3201).
        """

        logger.debug("EPever: Parsing Status Flags (0x3201)...")
        # EPever Status offsets: 0x3201 (byte 0) Charging Equipment Status, 0x3202 (byte 2) Discharging Equipment Status
        charging_raw = self.Bytes2Int(payload, offset=0, length=2)
        discharging_raw = self.Bytes2Int(payload, offset=2, length=2)

        charge_code = (charging_raw >> 2) & 0x03
        charge_state = Config.CHARGING_STATES.get(charge_code, f"Unknown ({charge_code})")
        load_is_on = bool(discharging_raw & 0x0001)

        self._update_data({
            "power_switch": 1 if load_is_on else 0,
            "state": charge_state,
            "load_state": "ON" if load_is_on else "OFF"
        })
        logger.debug("EPever: Parsed Status -> Charging State: %s, Load: %s",
                     charge_state, "ON" if load_is_on else "OFF")

    def updateSolarPanelInfo(self, payload: bytes):
        """
        Unpacks historical energy yield stats (0x330C).
        """

        logger.debug("EPever: Parsing Energy Yield Stats (0x330C)...")

        # EPever Energy offsets: 0x330C-0x330D (byte 0) Generated Today, 0x330E-0x330F (byte 4) Generated This Month,
        # 0x3310-0x3311 (byte 8) Generated This Year, 0x3312-0x3313 (byte 12) Total Generated
        e_today = round(self.Bytes2Int(payload, offset=0, length=4, little_endian=True) / 100.0, 2)
        e_month = round(self.Bytes2Int(payload, offset=4, length=4, little_endian=True) / 100.0, 2)
        e_year = round(self.Bytes2Int(payload, offset=8, length=4, little_endian=True) / 100.0, 2)
        e_total = round(self.Bytes2Int(payload, offset=12, length=4, little_endian=True) / 100.0, 2)

        self._update_data({
            "energy_today": e_today,
            "energy_month": e_month,
            "energy_year": e_year,
            "energy_total": e_total
        })
        logger.debug("EPever: Parsed Energy Stats -> Today: %skWh, Total: %skWh",
                     e_today, e_total)

