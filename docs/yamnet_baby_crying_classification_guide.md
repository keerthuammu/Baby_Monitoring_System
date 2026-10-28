# Smart Baby Monitoring System — Baby Crying Sound Classification Guide
> **IoT Edge Telemetry + Local Neural Sound Classification (Google YAMNet ONNX)**

---

## 1. System Overview

This enhancement adds local deep-learning audio classification to the Smart Baby Monitoring System using **Google YAMNet** (trained on 521 AudioSet event categories) running natively via **ONNX Runtime** on Windows.

### Core Architectural Principle: Decoupled Volume & Classification
Sound volume and sound classification are treated as **two completely independent measurements**:
- **Sound Intensity (Volume):** Categorized strictly by decibel level ($< 45\text{ dB}$ = *Low Sound*, $45 - 65\text{ dB}$ = *Moderate Sound*, $\ge 65\text{ dB}$ = *High Sound*).
- **Sound Classification (Neural Audio Recognition):** Identifies the *type* of sound independent of volume:
  - **`Possible Baby Crying`** (AudioSet classes: *Baby cry, infant cry*, *Crying, sobbing*)
  - **`Other Sound`** (Door slams, barking, speech, ambient noise)
  - **`Uncertain`** (Borderline / ambiguous acoustic profile)
  - **`Microphone or connection unavailable`** (Freshness guard: automatically triggers when no audio is received for $> 10$ seconds)

> [!NOTE]
> **Privacy First:** 100% of audio processing occurs locally in memory on your Windows computer. Zero audio is ever transmitted to third-party cloud services or paid APIs.

---

## 2. Hardware Wiring (INMP441 Microphone)

The hardware connections remain 100% identical and unchanged:

| INMP441 Pin | ESP32 DevKit V1 Pin | Function | Notes |
| :--- | :--- | :--- | :--- |
| **VDD** | **3V3** | Power Supply | **WARNING:** Never connect to 5V (damages INMP441)! |
| **GND** | **GND** | Ground | Common system ground |
| **SD** | **GPIO 33** | Serial Data | I²S DMA audio input |
| **WS** | **GPIO 25** | Word Select (LRCLK) | Frame sync (16,000 Hz) |
| **SCK** | **GPIO 26** | Serial Clock (BCLK) | Bit clock |
| **L/R** | **GND** | Channel Select | Tied to GND for Left channel |

---

## 3. Quick Startup Guide (Beginner Friendly)

### Terminal 1: Start the Local FastAPI Backend
Open PowerShell in the project directory:
```powershell
cd E:\Baby_Monitoring_System
& "backend\.venv\Scripts\uvicorn.exe" app.main:app --app-dir backend --host 0.0.0.0 --port 8000
```
*Expected Output:*
```text
INFO:     Started server process
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### Terminal 2: Start the React Frontend Dashboard
Open a second PowerShell window:
```powershell
cd E:\Baby_Monitoring_System\frontend
npm run dev
```
*Expected Output:*
```text
  VITE v6.4.5  ready in 579 ms
  ➜  Local:   http://localhost:5173/
```
Open **[http://localhost:5173](http://localhost:5173)** in Google Chrome or Microsoft Edge.

### Step 3: Flash the ESP32 Firmware
1. Connect your ESP32 to your PC via a Micro-USB data cable.
2. Open the Arduino IDE.
3. Open the sketch:
   ```text
   E:\Baby_Monitoring_System\esp32_firmware\smart_baby_monitor\smart_baby_monitor.ino
   ```
4. Verify your Wi-Fi credentials at lines 39–40:
   ```cpp
   const char* WIFI_SSID     = "Your_WiFi_Name";
   const char* WIFI_PASSWORD = "Your_WiFi_Password";
   ```
5. Click **Upload** (Arrow icon).
6. Open the **Serial Monitor** (`115200` baud).

---

## 4. Verification & Testing

### 1. Run the Automated Test Suite (18 Tests)
In PowerShell:
```powershell
& "e:\Baby_Monitoring_System\backend\.venv\Scripts\python.exe" -m pytest -v
```
*Result:* All 18 unit and integration tests pass.

### 2. Run the Live Regression Test
With the backend running on port 8000:
```powershell
& "e:\Baby_Monitoring_System\backend\.venv\Scripts\python.exe" "tests/regression_live_test.py"
```
*Tests executed:*
1. Backend Server Health (`GET /health`)
2. Real Baby Crying Audio (`baby_cry_real.wav`) $\rightarrow$ `POSSIBLE_CRYING` (85.0% confidence)
3. Audio Status Polling (`GET /api/audio/status`) $\rightarrow$ `'Possible Baby Crying'` (Freshness: True)
4. Environmental Sound (`dog_bark_real.wav`) $\rightarrow$ `OTHER_SOUND` (Cry confidence: 0.0%)
5. High-Volume Door Slam (70 dB impulse) $\rightarrow$ `OTHER_SOUND` (Proves loud sounds $\neq$ crying)
6. Periodic Sound Level Telemetry (`POST /api/readings`) $\rightarrow$ `201 Created`
7. Dashboard Stats $\rightarrow$ Node Status: `ONLINE`
8. Freshness Guard $\rightarrow$ Automatically switches to `'Microphone or connection unavailable'` after 10s of silence

---

## 5. Changed Files Summary

| Component | File | Action | Purpose |
| :--- | :--- | :---: | :--- |
| **Dependencies** | `backend/requirements.txt` | Modified | Added `onnxruntime>=1.20.0` |
| **Model Files** | `backend/app/audio/models/yamnet.onnx` | Added | Google YAMNet AudioSet neural model (~16 MB) |
| **Model Labels** | `backend/app/audio/models/yamnet_class_map.csv` | Added | Official AudioSet 521 class definitions |
| **Model Service** | `backend/app/audio/yamnet_classifier.py` | Added | ONNX inference wrapper, cry probability, temporal smoothing, freshness guard |
| **API Router** | `backend/app/api/audio.py` | Modified | Added `GET /api/audio/status` and direct binary audio streaming |
| **Firmware** | `esp32_firmware/smart_baby_monitor/smart_baby_monitor.ino` | Modified | Added 16kHz PCM audio chunk buffer and local Wi-Fi transmission |
| **Firmware Backup** | `esp32_firmware/smart_baby_monitor/smart_baby_monitor_backup.ino` | Added | Exact safety backup of original firmware |
| **Frontend Cards** | `frontend/src/components/MetricCards.jsx` | Modified | Added dedicated Sound Classification card; decoupled volume |
| **Frontend State** | `frontend/src/App.jsx` & `frontend/src/services/api.js` | Modified | Polling loop integration for `/api/audio/status` |
| **Test Suite** | `tests/test_audio.py` & `tests/regression_live_test.py` | Added/Updated | End-to-end regression validation |

---

## 6. Troubleshooting

### Problem: Dashboard shows "Microphone or connection unavailable"
- **Cause:** No audio chunks have been received by the backend for $> 10$ seconds.
- **Solution:**
  1. Check the ESP32 Serial Monitor to ensure it connected to Wi-Fi.
  2. Verify your computer's local IP address using `ipconfig` (e.g., `192.168.55.208`).
  3. Ensure `AUDIO_CLASSIFY_URL` in `smart_baby_monitor.ino` matches your computer's current IP address and port 8000.

### Problem: Door slam causes high dB but does not trigger crying
- **Expected Behavior:** This is working as intended! A door slam has high decibels but lacks infant vocal harmonic resonance. It will register as **"High Sound"** on the volume gauge, but **"Other Sound"** on the sound classification card.

---

## 7. Rollback Procedure

If you ever wish to completely revert all changes and return to the baseline version of the project:

```powershell
git checkout main
```
This will instantly restore your repository to the exact commit prior to this feature branch.

---

## 8. Medical & Safety Disclaimer

> [!CAUTION]
> **Assistive Prototype Only:** This project is an engineering prototype and academic demonstration tool. It is **not** a medical device, is not FDA/CE-cleared, and must not be used as a substitute for adult supervision. It cannot determine the underlying cause of crying (such as hunger, fever, colic, or pain), and the absence of a crying detection does not guarantee an infant's safety or comfort.
