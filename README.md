# Smart Baby Monitoring System (IoT + Full-Stack Web Application)

An IoT-based assistive nursery monitoring system that detects acoustic activity and alerts caregivers to possible infant crying without video cameras. Developed as an MCA College Major Project.

---

## 📌 Features

- **Privacy-First (No Camera)**: Uses a digital MEMS microphone (INMP441) connected to an ESP32 microcontroller over I²S.
- **Local Network Architecture**: Operates within your home/lab Wi-Fi without relying on third-party cloud subscriptions.
- **FastAPI Backend**: High-performance asynchronous REST API built with Python, Pydantic, and SQLAlchemy.
- **PostgreSQL Persistence**: Stores device status, time-series sensor readings, and alert logs.
- **Modern Dashboard**: Responsive React + Vite web dashboard styled with Tailwind CSS, featuring Recharts telemetry graphs and visual alert notifications.
- **Crying vs. Noise Distinction**: Explicitly separates general ambient sound activity from suspected crying episodes.

---

## 📂 Repository Structure

```
Baby_Monitoring_System/
├── .env.example                       # Template for environment configuration
├── .gitignore                         # Standard git ignore rules
├── README.md                          # Project overview and instructions
├── backend/                           # FastAPI Python backend
│   ├── app/
│   │   ├── api/                       # API route definitions
│   │   ├── audio/                     # Audio feature extraction and ML logic
│   │   ├── core/                      # Config, security, database session
│   │   ├── models/                    # SQLAlchemy database models
│   │   ├── schemas/                   # Pydantic schemas
│   │   └── services/                  # Business logic (event management, device tracking)
│   ├── requirements.txt               # Backend Python dependencies
├── esp32_firmware/                    # Arduino sketches
│   ├── inmp441_test/                  # Baseline standalone microphone test sketch
│   │   └── inmp441_test.ino
│   └── smart_baby_monitor/            # Full IoT firmware with Wi-Fi & HTTP reporting
├── frontend/                          # React + Vite web application
├── tests/                             # Automated test scripts (backend & API)
└── docs/                              # Project documentation & college report guides
    └── architecture_and_plan.md       # Detailed system architecture & plan
```

---

## 🔌 Hardware Setup (Confirmed Pinout)

- **Microcontroller**: ESP32 DevKit V1
- **Microphone**: INMP441 I²S Digital MEMS Microphone Module

| INMP441 Pin | ESP32 Pin | Note |
|---|---|---|
| **VDD** | **3V3** | **Do NOT connect to 5V** |
| **GND** | **GND** | Ground |
| **SD**  | **GPIO 33** | Serial Data |
| **WS**  | **GPIO 25** | Word Select (Left-Right Clock) |
| **SCK** | **GPIO 26** | Serial Clock |
| **L/R** | **GND** | Left channel selection |

---

## 🚀 Development Phases

- **Phase 1: Inspect & Plan** *(Completed)*
- **Phase 2: Local Backend & Database**
- **Phase 3: Frontend Dashboard**
- **Phase 4: ESP32 Firmware Integration**
- **Phase 5: Audio Processing & Crying Detection**
- **Phase 6: Optional Room Sensor (DHT11)**
- **Phase 7: End-to-End Testing & Demonstration**

---

## ⚠️ Assistive Prototype Disclaimer

This system is an experimental assistive tool designed for academic evaluation. It is **not** a certified medical diagnostic device and cannot guarantee an infant's safety or determine why a baby is crying. Direct human caregiver supervision is always essential.
