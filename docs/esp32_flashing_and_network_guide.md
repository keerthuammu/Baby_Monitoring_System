# ESP32 Firmware Flashing & Local Network Setup Guide

This guide walks you through configuring, compiling, and flashing the ESP32 IoT node using the Arduino IDE on your Windows development computer.

---

## 1. Important Network Concept: Local IP vs. Localhost

> [!IMPORTANT]
> When programming the ESP32, **never** set the backend URL to `http://localhost:8000` or `http://127.0.0.1:8000`.
>
> On the ESP32, `localhost` refers to the **ESP32 microcontroller itself**, which is not running the FastAPI backend.
> To reach your computer from the ESP32, you must use your computer's **Local IPv4 Address** on your Wi-Fi network.

### Your Detected Development Computer IP:
- **Local IPv4 Address:** `192.168.60.178`
- **Backend Port:** `8000`
- **Target Ingestion URL:** `http://192.168.60.178:8000/api/readings`

*(If you ever change Wi-Fi networks, you can re-check your IP anytime in PowerShell by typing `ipconfig` and looking at the `IPv4 Address` under your active Wi-Fi adapter).*

---

## 2. Windows Firewall Configuration for Port 8000

By default, Windows Defender Firewall may block incoming HTTP connections from external devices on your local Wi-Fi to your laptop.

To allow the ESP32 to send readings to port 8000, run this single command in **PowerShell as Administrator**:

```powershell
New-NetFirewallRule -DisplayName "Baby Monitor FastAPI Port 8000" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow
```

*(This rule only allows connections on your local network on port 8000; it does not expose your computer to the public internet).*

---

## 3. Hardware Connections (Double-Check Before Powering On)

Ensure your breadboard connections match this table:

| INMP441 Pin | ESP32 DevKit V1 Pin | Important Notes |
| :--- | :--- | :--- |
| **VDD** | **3V3** | **Do NOT connect to 5V or VIN! 3.3V ONLY.** |
| **GND** | **GND** | Common ground |
| **SD** | **GPIO 33** | I²S Serial Data Input |
| **WS** | **GPIO 25** | I²S Word Select (Left/Right Clock) |
| **SCK** | **GPIO 26** | I²S Serial Clock |
| **L/R** | **GND** | Left Channel selection |

---

## 4. Flashing Instructions in Arduino IDE

1. **Open the Sketch:**
   - Launch **Arduino IDE**.
   - Go to `File` -> `Open...` and select:
     `E:\Baby_Monitoring_System\esp32_firmware\smart_baby_monitor\smart_baby_monitor.ino`

2. **Update Wi-Fi Credentials:**
   At lines 38–39, enter your 2.4 GHz Wi-Fi network name and password:
   ```cpp
   const char* WIFI_SSID     = "Your_WiFi_Name";
   const char* WIFI_PASSWORD = "Your_WiFi_Password";
   ```

3. **Verify the Backend URL:**
   Line 43 is already pre-configured to:
   ```cpp
   const char* BACKEND_URL   = "http://192.168.60.178:8000/api/readings";
   ```

4. **Select Board and Port:**
   - Go to `Tools` -> `Board` -> `esp32` -> **ESP32 Dev Module**.
   - Go to `Tools` -> `Port` -> select the COM port of your connected ESP32 (e.g., `COM3`, `COM4`, etc.).

5. **Upload the Code:**
   - Click the **Upload** arrow button (or press `Ctrl + U`).
   - If the Arduino IDE shows `Connecting........_____.....`, press and hold the **BOOT** button on the ESP32 for 2 seconds until uploading starts.

6. **Open Serial Monitor:**
   - Click the magnifying glass in the top right (or `Ctrl + Shift + M`).
   - Set the baud rate in the bottom right corner to **115200 baud**.
   - You will see the initialization sequence:
     ```text
     =======================================================
        Smart Baby Monitoring System — ESP32 IoT Node   
     =======================================================
     [OK] INMP441 I2S Microphone configured successfully.
     [WIFI] Connected! Assigned IP: 192.168.60.xxx
     [SOUND] Level:  42.5 dB | RMS:   38.2 | Peak:   190 | STATUS: [QUIET]
     [HTTP 201] Sent -> 42.5 dB | RMS: 38.2 | Peak: 190
     ```

---

## 5. End-to-End Verification Checklist

1. **Backend Server Running:**
   ```powershell
   cd E:\Baby_Monitoring_System
   .\backend\.venv\Scripts\uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000 --reload
   ```
2. **Frontend Dashboard Running:**
   ```powershell
   cd E:\Baby_Monitoring_System\frontend
   npm run dev
   ```
3. **Open Dashboard:**
   Visit `http://localhost:5173` in your browser.
4. **Speak or Clap near the Microphone:**
   - Watch the Serial Monitor print elevated decibels.
   - Watch the dashboard status change from **Quiet** 🟢 to **Moderate** 🔵 or **High Sound Activity** 🟡.
   - Notice the telemetry graph and readings table update live every 2.5 seconds.
