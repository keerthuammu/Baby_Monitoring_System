"""
Phase 7 Live End-to-End Regression Verification
Tests the running system across all criteria:
1. Real baby cry audio upload -> Possible Baby Crying
2. Real non-crying audio (dog bark) -> Other Sound
3. Door slam / noise impulse -> Other Sound (High volume != Crying)
4. Freshness guard / Disconnection test -> Unavailable after timeout
5. Telemetry ingestion (dB / RMS / Peak)
6. Stats & Events acknowledge
"""

import time
import requests
import numpy as np
import io
import wave

BASE_URL = "http://localhost:8000"
API_KEY = "baby_monitor_device_secret_key_123"
HEADERS = {"X-API-Key": API_KEY}

def create_impulse_wav(duration_s=1.0, sample_rate=16000):
    t = np.linspace(0, duration_s, int(sample_rate * duration_s), endpoint=False)
    # Fast decaying loud impact
    signal = (np.exp(-t * 20.0) * np.sin(2 * np.pi * 80 * t) * 28000).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(signal.tobytes())
    return buf.getvalue()

def run_tests():
    print("=" * 60)
    print("PHASE 7: FULL SYSTEM REGRESSION & ACCEPTANCE TESTING")
    print("=" * 60)

    # 1. Server Health Check
    r = requests.get(f"{BASE_URL}/health")
    assert r.status_code == 200, f"Health check failed: {r.status_code}"
    print("[PASS] 1. Backend Server Health: OK (Status: 200)")

    # 2. Test Real Baby Crying Audio Upload
    cry_path = "backend/app/audio/test_samples/baby_cry_real.wav"
    with open(cry_path, "rb") as f:
        r = requests.post(
            f"{BASE_URL}/api/audio/classify",
            headers={"X-API-Key": API_KEY, "Content-Type": "audio/wav", "X-Device-Id": "esp32-nursery-01"},
            data=f.read()
        )
    assert r.status_code == 200, f"Cry classify failed: {r.status_code} {r.text}"
    cry_res = r.json()
    assert cry_res["classification"] == "POSSIBLE_CRYING", f"Expected POSSIBLE_CRYING, got {cry_res['classification']}"
    print(f"[PASS] 2. Real Baby Cry Classified -> {cry_res['classification']} (Confidence: {cry_res['confidence']*100:.1f}%)")

    # 3. Check Real-Time Audio Status Endpoint (Freshness = True)
    r = requests.get(f"{BASE_URL}/api/audio/status")
    status_data = r.json()
    assert status_data["classification"] == "Possible Baby Crying", f"Expected 'Possible Baby Crying', got {status_data['classification']}"
    assert status_data["is_fresh"] is True
    print(f"[PASS] 3. Audio Status Polling -> '{status_data['classification']}' (Freshness: True)")

    # 4. Test Environmental Non-Crying Audio (Dog Bark)
    dog_path = "backend/app/audio/test_samples/dog_bark_real.wav"
    with open(dog_path, "rb") as f:
        r = requests.post(
            f"{BASE_URL}/api/audio/classify",
            headers={"X-API-Key": API_KEY, "Content-Type": "audio/wav", "X-Device-Id": "esp32-nursery-01"},
            data=f.read()
        )
    assert r.status_code == 200
    dog_res = r.json()
    assert dog_res["classification"] == "OTHER_SOUND", f"Expected OTHER_SOUND, got {dog_res['classification']}"
    print(f"[PASS] 4. Environmental Sound (Dog Bark) -> {dog_res['classification']} (Cry Confidence: {dog_res.get('crying_score_raw', 0)*100:.1f}%)")

    # 5. Test Loud Door Slam / Impact (High Volume != Crying)
    impulse_wav = create_impulse_wav()
    r = requests.post(
        f"{BASE_URL}/api/audio/classify",
        headers={"X-API-Key": API_KEY, "Content-Type": "audio/wav", "X-Device-Id": "esp32-nursery-01"},
        data=impulse_wav
    )
    assert r.status_code == 200
    slam_res = r.json()
    assert slam_res["classification"] == "OTHER_SOUND", f"Expected OTHER_SOUND for door slam, got {slam_res['classification']}"
    print(f"[PASS] 5. Loud Door Slam Classified -> {slam_res['classification']} (Sound Level: {slam_res['sound_level_db']} dB)")

    # 6. Test Standard Periodic Telemetry (POST /api/readings)
    r = requests.post(
        f"{BASE_URL}/api/readings",
        headers=HEADERS,
        json={"device_id": "esp32-nursery-01", "sound_level": 48.5, "rms_amplitude": 650.0, "peak_amplitude": 1200}
    )
    assert r.status_code == 201
    print("[PASS] 6. Periodic Sound Level Telemetry (/api/readings) -> Created (201)")

    # 7. Test Dashboard Stats
    r = requests.get(f"{BASE_URL}/api/stats")
    assert r.status_code == 200
    stats = r.json()
    assert stats["device_status"] == "ONLINE"
    print(f"[PASS] 7. Dashboard Stats -> Node Status: {stats['device_status']} (Packets: {stats['total_readings']})")

    # 8. Test Freshness Guard / Microphone Disconnection
    print("[*] 8. Testing Freshness Guard (waiting 10.5s to verify disconnection fallback)...")
    time.sleep(10.5)
    r = requests.get(f"{BASE_URL}/api/audio/status")
    stale_data = r.json()
    assert stale_data["classification"] == "Microphone or connection unavailable", f"Expected unavailable, got {stale_data['classification']}"
    assert stale_data["is_fresh"] is False
    print(f"[PASS] 8. Freshness Guard Verified -> '{stale_data['classification']}' (is_fresh: False)")

    print("=" * 60)
    print("ALL 8 REGRESSION CRITERIA PASSED SUCCESSFULLY!")
    print("=" * 60)

if __name__ == "__main__":
    run_tests()
