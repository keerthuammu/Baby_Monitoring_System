"""
ESP32 USB Serial Telemetry Forwarder (Campus Wi-Fi Bypass)
---------------------------------------------------------
Reads acoustic measurements directly from the ESP32 via USB Serial cable
and forwards them to the local FastAPI backend (http://localhost:8000/api/readings).
Useful for college demonstrations when campus Wi-Fi blocks peer-to-peer device traffic (AP Isolation).
"""

import sys
import re
import time
import requests
import serial.tools.list_ports

BACKEND_URL = "http://localhost:8000/api/readings"
API_KEY = "baby_monitor_device_secret_key_123"
HEADERS = {
    "Content-Type": "application/json",
    "X-API-Key": API_KEY
}

# Regex to extract: [SOUND] Level:  72.5 dB | RMS: 4199.5 | Peak:  4706
PATTERN = re.compile(r"Level:\s*([\d\.]+)\s*dB\s*\|\s*RMS:\s*([\d\.]+)\s*\|\s*Peak:\s*(\d+)")

def find_esp32_port():
    ports = list(serial.tools.list_ports.comports())
    for p in ports:
        desc = p.description.lower()
        if "cp210" in desc or "ch340" in desc or "uart" in desc or "usb" in desc:
            return p.device
    if ports:
        return ports[0].device
    return None

def main():
    import serial
    port = sys.argv[1] if len(sys.argv) > 1 else find_esp32_port()
    if not port:
        print("[ERROR] No USB Serial COM port detected for ESP32. Ensure USB cable is plugged in.")
        return

    print("=" * 65)
    print(f"Connecting to ESP32 on {port} at 115200 baud...")
    print(f"Forwarding live acoustic telemetry -> {BACKEND_URL}")
    print("=" * 65)

    try:
        ser = serial.Serial(port, 115200, timeout=1.0)
    except Exception as e:
        print(f"[ERROR] Could not open {port}: {e}")
        print("Tip: If Arduino IDE Serial Monitor is open, CLOSE IT so this script can read the port.")
        return

    while True:
        try:
            line = ser.readline().decode('utf-8', errors='ignore').strip()
            if not line:
                continue

            match = PATTERN.search(line)
            if match:
                sound_level = float(match.group(1))
                rms = float(match.group(2))
                peak = int(match.group(3))

                payload = {
                    "device_id": "esp32-nursery-01",
                    "sound_level": sound_level,
                    "rms_amplitude": rms,
                    "peak_amplitude": peak
                }

                res = requests.post(BACKEND_URL, json=payload, headers=HEADERS, timeout=2.0)
                if res.status_code == 201:
                    status_text = "LOUD / CRYING" if sound_level >= 65 else "QUIET / NORMAL"
                    print(f"[FORWARDED] {sound_level:5.1f} dB | RMS: {rms:6.1f} | Peak: {peak:5d} -> [{status_text}] HTTP 201 OK")
                else:
                    print(f"[BACKEND ERROR] {res.status_code}: {res.text}")

        except KeyboardInterrupt:
            print("\nStopped.")
            break
        except Exception as e:
            print(f"[WARN] {e}")
            time.sleep(1)

if __name__ == "__main__":
    main()
