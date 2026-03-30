# ATMS — Autonomous Traffic Monitoring System

A full-stack Vision AI + IoT project that simulates how modern adaptive traffic systems work — the same concept behind smart intersections and industrial SCADA systems.

## Demo

[Watch the demo video]:https://youtube.com/shorts/b-CrNN_raKI?feature=share

---

## How It Works

A camera watches a live traffic feed. YOLOv8 detects every vehicle in real-time and ByteTrack gives each one a unique ID so the same car is never counted twice. When a vehicle crosses the counting line, the counter increments.

Every 2 seconds, the system calculates the traffic state and sends it over MQTT to an ESP32 microcontroller. The ESP32 runs a Finite State Machine that controls the LEDs based on live traffic density. If traffic stays stalled for over 30 seconds, an analytics dashboard is automatically generated locally — no cloud required.

---

## System Architecture
```
Camera → YOLOv8 + ByteTrack → MQTT Broker → ESP32 FSM → LED Output
                                    ↓
                          Analytics Dashboard
```

---

## Traffic States

| State | Condition | LED |
|-------|-----------|-----|
| CLEAR | < 5 vehicles | 🟢 Green |
| MODERATE | 5–9 vehicles | 🟡 Yellow |
| CONGESTED | 10+ vehicles | 🔴 Red + Yellow |
| STOPPED | Stalled 30+ seconds | 🔴 Red |

---

## Tech Stack

- **Python** — main edge vision pipeline
- **YOLOv8** — real-time vehicle detection
- **ByteTrack** — multi-object tracking
- **MQTT** — IoT messaging protocol
- **ESP32 + C++** — embedded hardware control
- **Finite State Machine** — adaptive LED logic
- **Matplotlib** — offline analytics dashboard

---

## Project Structure
```
ATMS/
├── carcount.py          # Main pipeline — detection, tracking, MQTT
├── publisher.py         # MQTT publisher
├── reporter.py          # Analytics dashboard generator
└── esp32_firmware/
    ├── main.cpp         # ESP32 FSM + MQTT subscriber
    └── platformio.ini   # PlatformIO build config
```

---

## Getting Started

**Requirements**
```bash
pip install ultralytics opencv-python paho-mqtt matplotlib python-dotenv
```

**Run**
```bash
# Start MQTT broker
mosquitto -c /opt/homebrew/etc/mosquitto/mosquitto.conf -d

# Run the system
python3 carcount.py
```

**ESP32 Firmware**

Open `esp32_firmware/` in PlatformIO and upload to your ESP32.

---

*Built as part of a Vision AI + IoT systems project.*
