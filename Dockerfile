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

ENTRYPOINT [ "python", "-u", "solar-monitor.py" ]
