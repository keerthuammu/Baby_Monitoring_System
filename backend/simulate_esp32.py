"""
ESP32 DevKit V1 Hardware Simulator
----------------------------------
Simulates telemetry transmission from the INMP441 microphone on an ESP32.
Used for local testing, frontend verification, and college demonstrations.
Sends clearly labeled measurements to the local FastAPI backend.
"""

import time
import os
import sys
import random
import requests

# Target Ingestion Endpoint (Render Cloud by default, or localhost via CLI/env):
DEFAULT_BACKEND = "https://baby-monitor-backend-8m8o.onrender.com/api/readings"
BACKEND_URL = sys.argv[1] if (len(sys.argv) > 1 and sys.argv[1].startswith("http")) else os.getenv("BACKEND_URL", DEFAULT_BACKEND)
API_KEY = os.getenv("API_KEY", "baby_monitor_device_secret_key_123")
DEVICE_ID = "esp32-devkit-v1-simulated"

HEADERS = {
    "Content-Type": "application/json",
    "X-API-Key": API_KEY
}

def generate_reading(mode: str = "normal") -> dict:
    """
    Generates synthetic sound features simulating the INMP441 output.
    Modes:
      - 'quiet': Ambient background noise in a quiet nursery (30 - 44 dB)
      - 'normal': Moderate noise, movement or muffled speech (45 - 60 dB)
      - 'loud': High environmental noise, slamming door, adult speech (68 - 85 dB)
      - 'crying': Infant crying episode with characteristic 350-650 Hz vocal pitch (70 - 85 dB)
    """
    if mode == "crying":
        sound_level = round(random.uniform(72.0, 84.0), 2)
        rms = round(random.uniform(550.0, 950.0), 2)
        peak = random.randint(1800, 3800)
        pitch = round(random.uniform(430.0, 520.0), 1)
        return {
            "device_id": DEVICE_ID,
            "sound_level": sound_level,
            "rms_amplitude": rms,
            "peak_amplitude": peak,
            "classification": "POSSIBLE_CRYING",
            "pitch_hz": pitch,
            "confidence": 0.92
        }
    elif mode == "loud":
        sound_level = round(random.uniform(68.0, 84.0), 2)
        rms = round(random.uniform(350.0, 850.0), 2)
        peak = random.randint(1200, 3200)
        return {
            "device_id": DEVICE_ID,
            "sound_level": sound_level,
            "rms_amplitude": rms,
            "peak_amplitude": peak,
            "classification": "HIGH_SOUND_ACTIVITY",
            "pitch_hz": round(random.uniform(100.0, 180.0), 1),
            "confidence": 0.85
        }
    elif mode == "quiet":
        sound_level = round(random.uniform(32.0, 44.0), 2)
        rms = round(random.uniform(15.0, 45.0), 2)
        peak = random.randint(80, 220)
        return {
            "device_id": DEVICE_ID,
            "sound_level": sound_level,
            "rms_amplitude": rms,
            "peak_amplitude": peak,
            "classification": "QUIET",
            "pitch_hz": 0.0,
            "confidence": 0.95
        }
    else:
        sound_level = round(random.uniform(46.0, 58.0), 2)
        rms = round(random.uniform(60.0, 180.0), 2)
        peak = random.randint(300, 750)
        return {
            "device_id": DEVICE_ID,
            "sound_level": sound_level,
            "rms_amplitude": rms,
            "peak_amplitude": peak,
            "classification": "MODERATE_SOUND",
            "pitch_hz": 0.0,
            "confidence": 0.75
        }

def run_simulation(interval: float = 2.0, count: int = 50):
    print("=" * 60)
    print(f"Starting ESP32 Hardware Simulator -> {BACKEND_URL}")
    print(f"Simulated Device ID: {DEVICE_ID}")
    print(f"Interval: {interval}s per reading")
    print("=" * 60)

    for i in range(1, count + 1):
        # Rotate through Quiet -> Moderate -> Infant Crying -> Loud Impulsive Noise
        cycle = i % 12
        if cycle in [5, 6, 7]:
            mode = "crying"
            label = "[🚨 BABY CRYING (480 Hz)]"
        elif cycle in [9, 10]:
            mode = "loud"
            label = "[🔊 LOUD / GENERAL NOISE]"
        elif cycle in [3, 4]:
            mode = "normal"
            label = "[💬 MODERATE SOUND]"
        else:
            mode = "quiet"
            label = "[🌿 QUIET ROOM]"

        payload = generate_reading(mode=mode)

        try:
            response = requests.post(BACKEND_URL, json=payload, headers=HEADERS, timeout=6.0)
            if response.status_code == 201:
                print(f"[{i}/{count}] {label} Sent: {payload['sound_level']} dB | Class: {payload.get('classification')} | Pitch: {payload.get('pitch_hz')} Hz -> 201 Created")
            else:
                print(f"[{i}/{count}] [ERROR] Server returned {response.status_code}: {response.text}")
        except requests.exceptions.ConnectionError:
            print(f"[{i}/{count}] [WARN] Connection Error: Ensure backend is running at {BACKEND_URL}")
        except Exception as e:
            print(f"[{i}/{count}] [ERROR] {e}")

        time.sleep(interval)

    print("\nSimulation finished.")

if __name__ == "__main__":
    count = 30
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        count = int(sys.argv[1])
    run_simulation(interval=2.0, count=count)
