FROM python:3.11-slim-bullseye

RUN apt update && apt -y install --no-install-recommends bluetooth build-essential cmake autoconf automake pkg-config libdbus-1-dev libglib2.0-dev libgirepository1.0-dev gcc libcairo2-dev pkg-config python3-dev gir1.2-gtk-3.0

WORKDIR /solar-monitor
COPY . .

RUN pip install -r requirements.txt

ENTRYPOINT [ "python", "-u", "solar-monitor.py" ]

