# libscrc publishes no wheels, so it is compiled here and the toolchain stays
# out of the runtime image.
FROM python:3.11-slim-bookworm AS builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc python3-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt


FROM python:3.11-slim-bookworm

# bluez provides bluetoothctl, which ble.set_trusted shells out to. bleak
# reaches D-Bus through pure-python dbus-fast and needs nothing else.
RUN apt-get update \
    && apt-get install -y --no-install-recommends bluez \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels requirements.txt

WORKDIR /solar-monitor
COPY . .

ENTRYPOINT [ "python", "-u", "solar-monitor.py" ]
