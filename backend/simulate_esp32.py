"""
ESP32 DevKit V1 Hardware Simulator
----------------------------------
Simulates telemetry transmission from the INMP441 microphone on an ESP32.
Used for local testing, frontend verification, and college demonstrations.
Sends clearly labeled measurements to the local FastAPI backend.
"""

import time
import random
import requests

BACKEND_URL = "http://localhost:8000/api/readings"
API_KEY = "baby_monitor_device_secret_key_123"
DEVICE_ID = "esp32-devkit-v1-simulated"

HEADERS = {
    "Content-Type": "application/json",
    "X-API-Key": API_KEY
}

def generate_reading(mode: str = "normal") -> dict:
    """
    Generates synthetic sound features simulating the INMP441 output.
    Modes:
      - 'quiet': Ambient background noise in a quiet nursery (30 - 45 dB)
      - 'normal': Moderate noise, movement or muffled speech (45 - 60 dB)
      - 'loud': High noise or crying episode (68 - 85 dB)
    """
    if mode == "quiet":
        sound_level = round(random.uniform(32.0, 44.0), 2)
        rms = round(random.uniform(15.0, 45.0), 2)
        peak = random.randint(80, 220)
    elif mode == "loud":
        sound_level = round(random.uniform(68.0, 84.0), 2)
        rms = round(random.uniform(350.0, 850.0), 2)
        peak = random.randint(1200, 3200)
    else:
        sound_level = round(random.uniform(46.0, 58.0), 2)
        rms = round(random.uniform(60.0, 180.0), 2)
        peak = random.randint(300, 750)

    return {
        "device_id": DEVICE_ID,
        "sound_level": sound_level,
        "rms_amplitude": rms,
        "peak_amplitude": peak
    }

def run_simulation(interval: float = 2.0, count: int = 50):
    print("=" * 60)
    print(f"Starting ESP32 Hardware Simulator -> {BACKEND_URL}")
    print(f"Simulated Device ID: {DEVICE_ID}")
    print(f"Interval: {interval}s per reading")
    print("=" * 60)

    for i in range(1, count + 1):
        # Trigger an elevated sound burst every 10 readings for testing alerts
        if i % 10 in [7, 8, 9]:
            mode = "loud"
            label = "[LOUD / CRYING]"
        elif i % 5 == 0:
            mode = "normal"
            label = "[MODERATE NOISE]"
        else:
            mode = "quiet"
            label = "[QUIET ROOM]"

        payload = generate_reading(mode=mode)

        try:
            response = requests.post(BACKEND_URL, json=payload, headers=HEADERS, timeout=3.0)
            if response.status_code == 201:
                print(f"[{i}/{count}] {label} Sent: {payload['sound_level']} dB | RMS: {payload['rms_amplitude']} | Status: 201 Created")
            else:
                print(f"[{i}/{count}] [ERROR] Server returned {response.status_code}: {response.text}")
        except requests.exceptions.ConnectionError:
            print(f"[{i}/{count}] [WARN] Connection Error: Ensure backend is running at {BACKEND_URL}")
        except Exception as e:
            print(f"[{i}/{count}] [ERROR] {e}")

        time.sleep(interval)

    print("\nSimulation finished.")

if __name__ == "__main__":
    import sys
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    run_simulation(interval=2.0, count=count)
