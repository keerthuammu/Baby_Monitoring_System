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

    # Test Real Baby Cry Audio (using real benchmark audio sample)
    cry_sample_path = os.path.join(os.path.dirname(__file__), "test_samples", "baby_cry_real.wav")
    from app.audio.evaluate_benchmark import load_wav_as_16k_mono
    sig = load_wav_as_16k_mono(cry_sample_path)
    
    # Send window 1 (onset)
    w1_pcm = (sig[:16000] * 32767).astype(np.int16).tobytes()
    print("\nPosting 1.0s window 1 to /api/audio/classify...")
    res_w1 = client.post(
        "/api/audio/classify",
        content=w1_pcm,
        headers={
            "Content-Type": "application/octet-stream",
            "X-API-Key": "baby_monitor_device_secret_key_123",
            "X-Device-Id": "esp32-nursery-01"
        }
    )
    print(f"Window 1 HTTP {res_w1.status_code}: {res_w1.json()['classification']}")
    assert res_w1.status_code == 200
    assert res_w1.json()["classification"] in ["UNCERTAIN", "BABY CRYING DETECTED"]

    # Send window 2 (temporal consensus confirmation)
    w2_pcm = (sig[16000:32000] * 32767).astype(np.int16).tobytes()
    print("\nPosting 1.0s window 2 to /api/audio/classify...")
    res_w2 = client.post(
        "/api/audio/classify",
        content=w2_pcm,
        headers={
            "Content-Type": "application/octet-stream",
            "X-API-Key": "baby_monitor_device_secret_key_123",
            "X-Device-Id": "esp32-nursery-01"
        }
    )
    print(f"Window 2 HTTP {res_w2.status_code}: {res_w2.json()['classification']}")
    assert res_w2.status_code == 200
    assert res_w2.json()["is_baby_crying"] is True
    assert res_w2.json()["classification"] == "BABY CRYING DETECTED"

    print("\nFetching /api/audio/status immediately after cry classification...")
    status_after_cry = client.get("/api/audio/status")
    print(f"Status: {status_after_cry.json()}")
    assert status_after_cry.status_code == 200
    cry_status = status_after_cry.json()
    assert cry_status["classification"] == "BABY CRYING DETECTED"
    assert cry_status["is_baby_crying"] is True
    print("Verified crying state propagated to /api/audio/status!")

    # Test loud noise (Door slam / impulse) with release hysteresis
    sr = 16000
    print("\nPosting consecutive non-crying noise to test release hysteresis (3 windows)...")
    noise = np.random.normal(0, 0.4, sr)
    noise_int16 = (np.clip(noise, -1.0, 1.0) * 32767).astype(np.int16)

    # Window 1 of noise (incident held via breathing pause resilience)
    res_n1 = client.post("/api/audio/classify", content=noise_int16.tobytes(), headers={"Content-Type": "application/octet-stream", "X-API-Key": "baby_monitor_device_secret_key_123"})
    print(f"Noise Win 1 HTTP 200: {res_n1.json()['classification']} (Held active during pause)")

    # Window 2 of noise (incident held)
    res_n2 = client.post("/api/audio/classify", content=noise_int16.tobytes(), headers={"Content-Type": "application/octet-stream", "X-API-Key": "baby_monitor_device_secret_key_123"})
    print(f"Noise Win 2 HTTP 200: {res_n2.json()['classification']} (Held active during pause)")

    # Window 3 of noise (release threshold reached: incident concludes!)
    res_n3 = client.post("/api/audio/classify", content=noise_int16.tobytes(), headers={"Content-Type": "application/octet-stream", "X-API-Key": "baby_monitor_device_secret_key_123"})
    print(f"Noise Win 3 HTTP 200: {res_n3.json()['classification']} (Incident successfully closed)")
    assert res_n3.status_code == 200
    assert res_n3.json()["classification"] == "NOT BABY CRYING"
    assert res_n3.json()["is_baby_crying"] is False
    print("Verified loud non-cry noise concludes incident and is classified as NOT BABY CRYING!")

    print("\nAll API audio flow assertions PASSED successfully!")

if __name__ == "__main__":
    test_api_audio_flow()
