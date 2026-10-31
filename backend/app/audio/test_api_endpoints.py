import os
import sys
import numpy as np
from fastapi.testclient import TestClient

# Ensure backend root is on path
backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.main import app

def test_api_audio_flow():
    client = TestClient(app)
    
    print("Testing /api/audio/status endpoint...")
    status_res = client.get("/api/audio/status")
    print(f"Status HTTP {status_res.status_code}: {status_res.json()}")
    assert status_res.status_code == 200
    initial_data = status_res.json()
    assert "classification" in initial_data
    assert initial_data["classification"] in ["BABY CRYING DETECTED", "NOT BABY CRYING", "UNCERTAIN", "AUDIO UNAVAILABLE"]
    print(f"Verified initial classification label: {initial_data['classification']}")

    # Generate 1.0 second of baby cry tone (450 Hz + harmonics)
    sr = 16000
    t = np.linspace(0, 1.0, sr, endpoint=False)
    freq = 450.0 + 35.0 * np.sin(2 * np.pi * 3.5 * t)
    phase = 2 * np.pi * np.cumsum(freq) / sr
    sig = 0.65 * np.sin(phase) + 0.35 * np.sin(2 * phase) + 0.15 * np.sin(3 * phase)
    sig_int16 = (sig * 32767).astype(np.int16)
    pcm_bytes = sig_int16.tobytes()

    print("\nPosting 1.0s raw PCM to /api/audio/classify...")
    classify_res = client.post(
        "/api/audio/classify",
        content=pcm_bytes,
        headers={
            "Content-Type": "application/octet-stream",
            "X-API-Key": "baby_monitor_device_secret_key_123",
            "X-Device-Id": "esp32-nursery-01"
        }
    )
    print(f"Classify HTTP {classify_res.status_code}: {classify_res.json()}")
    assert classify_res.status_code == 200
    c_data = classify_res.json()
    assert c_data["is_baby_crying"] is True
    assert c_data["classification"] == "BABY CRYING DETECTED"

    print("\nFetching /api/audio/status immediately after cry classification...")
    status_after_cry = client.get("/api/audio/status")
    print(f"Status: {status_after_cry.json()}")
    assert status_after_cry.status_code == 200
    cry_status = status_after_cry.json()
    assert cry_status["classification"] == "BABY CRYING DETECTED"
    assert cry_status["is_baby_crying"] is True
    print("Verified crying state propagated to /api/audio/status!")

    # Test loud noise (Door slam / impulse)
    print("\nPosting 1.0s loud noise to /api/audio/classify...")
    noise = np.random.normal(0, 0.4, sr)
    noise_int16 = (np.clip(noise, -1.0, 1.0) * 32767).astype(np.int16)
    classify_res2 = client.post(
        "/api/audio/classify",
        content=noise_int16.tobytes(),
        headers={
            "Content-Type": "application/octet-stream",
            "X-API-Key": "baby_monitor_device_secret_key_123",
            "X-Device-Id": "esp32-nursery-01"
        }
    )
    print(f"Noise Classify HTTP {classify_res2.status_code}: {classify_res2.json()}")
    assert classify_res2.status_code == 200
    assert classify_res2.json()["classification"] == "NOT BABY CRYING"
    assert classify_res2.json()["is_baby_crying"] is False
    print("Verified loud non-cry noise is classified as NOT BABY CRYING!")

    print("\nAll API audio flow assertions PASSED successfully!")

if __name__ == "__main__":
    test_api_audio_flow()
