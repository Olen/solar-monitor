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

# Match the uid that owns the mounted config and log directories on the host.
ARG UID=1000
ARG GID=1000
RUN groupadd --gid "$GID" solar \
    && useradd --uid "$UID" --gid "$GID" --no-create-home --shell /usr/sbin/nologin solar \
    && install -d -o "$UID" -g "$GID" /solar-monitor/solar-monitor

WORKDIR /solar-monitor
COPY --chown=$UID:$GID . .
USER solar

LABEL org.opencontainers.image.title="solar-monitor" \
      org.opencontainers.image.description="Reads solar regulators, inverters and battery BMSes over Bluetooth LE and publishes to MQTT or HTTP" \
      org.opencontainers.image.url="https://github.com/Olen/solar-monitor" \
      org.opencontainers.image.source="https://github.com/Olen/solar-monitor" \
      org.opencontainers.image.documentation="https://github.com/Olen/solar-monitor/blob/master/README.md" \
      org.opencontainers.image.licenses="GPL-3.0-only" \
      org.opencontainers.image.vendor="Olen" \
      org.opencontainers.image.base.name="docker.io/library/python:3.11-slim-bookworm"

ENTRYPOINT [ "python", "-u", "solar-monitor.py" ]
