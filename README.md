# Smart Baby Monitoring System (IoT + Full-Stack Web Application)

An IoT-based assistive nursery monitoring system that detects acoustic activity and alerts caregivers to possible infant crying without video cameras. Developed as an MCA College Major Project.

---

## 📌 Project Overview

- **Privacy-First (No Camera)**: Captures acoustic features using a digital MEMS microphone (INMP441) connected to an ESP32 microcontroller over I²S.
- **Local Network Architecture**: Operates within your local Wi-Fi without relying on third-party cloud subscriptions or transmitting private nursery audio outside your home.
- **High-Performance FastAPI Backend**: Asynchronous Python REST API with secure `X-API-Key` ingestion, Pydantic validation, and SQLAlchemy ORM.
- **PostgreSQL 18 Persistence**: Robust persistence of sensor readings, detected events, and device heartbeats.
- **Modern React 19 Dashboard**: Responsive Vite + Tailwind CSS dashboard with Recharts live telemetry curves and visual alert dismissal.
- **Scientific Crying vs. Noise Distinction**: Uses fundamental pitch frequency ($F_0$ in the 350–680 Hz range) and FFT cry-band energy ratios to separate ambient room noise from authentic crying signatures.

---

## 🔌 Hardware Setup (Confirmed Pinout)

- **Microcontroller**: ESP32 DevKit V1 (30-pin)
- **Acoustic Sensor**: INMP441 I²S Digital MEMS Microphone Module

| INMP441 Pin | ESP32 Pin | Note |
|---|---|---|
| **VDD** | **3V3** | **CRITICAL: Connect to 3.3V ONLY (Never 5V)** |
| **GND** | **GND** | Ground |
| **SD**  | **GPIO 33** | Serial Data Input |
| **WS**  | **GPIO 25** | Word Select (Left-Right Clock) |
| **SCK** | **GPIO 26** | Serial Clock |
| **L/R** | **GND** | Left channel selection |

---

## 📂 Repository Structure

```
Baby_Monitoring_System/
├── backend/                           # FastAPI Python backend
│   ├── app/
│   │   ├── api/                       # REST endpoints (readings, events, stats, audio)
│   │   ├── audio/                     # Acoustic feature extraction & classifier
│   │   ├── core/                      # Config, security, database session
│   │   ├── models/                    # SQLAlchemy models (devices, readings, events)
│   │   ├── schemas/                   # Pydantic schemas
│   │   └── services/                  # Business logic & debouncing
│   ├── requirements.txt               # Backend Python dependencies
│   └── simulate_esp32.py              # Hardware simulator script
├── esp32_firmware/                    # Arduino sketches
│   ├── inmp441_test/                  # Baseline standalone microphone test sketch
│   │   └── inmp441_test.ino
│   └── smart_baby_monitor/            # Full IoT production firmware with Wi-Fi
│       └── smart_baby_monitor.ino
├── frontend/                          # React 19 + Vite web application
│   ├── src/
│   │   ├── components/                # Header, AlertBanner, MetricCards, SoundChart, Tables
│   │   ├── services/api.js            # Backend API fetch client
│   │   └── App.jsx                    # Polling orchestrator & layout
├── tests/                             # Automated test suite (17 tests)
│   ├── conftest.py                    # Shared Pytest database fixtures
│   ├── test_api.py                    # REST API & database persistence tests
│   └── test_audio.py                  # Audio classification & pitch estimation tests
└── docs/                              # College documentation & guides
    ├── architecture_and_plan.md       # Technical architecture & phase roadmap
    ├── esp32_flashing_and_network_guide.md  # Step-by-step flashing & firewall guide
    ├── audio_classification_and_dataset_guide.md # Acoustic science & datasets
    └── college_project_report_and_demo_checklist.md # Master project report outline & viva checklist
```

---

## 🚀 Quick Start Guide (Windows)

### 1. Start the FastAPI Backend
```powershell
cd E:\Baby_Monitoring_System
.\backend\.venv\Scripts\uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000 --reload
```
Interactive API documentation: `http://localhost:8000/docs`

### 2. Start the React Frontend Dashboard
```powershell
cd E:\Baby_Monitoring_System\frontend
npm run dev
```
Open Dashboard: `http://localhost:5173`

### 3. Flash the ESP32
Open `esp32_firmware/smart_baby_monitor/smart_baby_monitor.ino` in Arduino IDE, set your 2.4 GHz Wi-Fi SSID/password, and upload to your ESP32.

### 4. Run Automated Tests
```powershell
cd E:\Baby_Monitoring_System
.\backend\.venv\Scripts\pytest.exe -v tests/
```

---

## ⚠️ Assistive Prototype Disclaimer

This system is an academic engineering prototype designed for caregiver assistance. It is **not** a certified medical diagnostic device and cannot guarantee an infant's safety or determine why a baby is crying. Direct human parental supervision is always required.
