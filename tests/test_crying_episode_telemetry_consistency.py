import pytest
import wave
from datetime import datetime, timezone, timedelta
from app.core.config import settings
from app.services.monitor_service import MonitorService
from app.models.models import SensorReading, CryingEvent
from app.audio.yamnet_classifier import YamnetClassifier

def test_telemetry_inherits_yamnet_crying_episode(client):
    """
    Verifies that when YAMNet confirms baby crying, subsequent telemetry packets
    during the active crying incident maintain BABY_CRYING_DETECTED rather than
    overwriting it to NOT_BABY_CRYING or creating conflicting HIGH_SOUND_ACTIVITY events.
    """
    device_id = "test-node-crying-bridge"
    cry_file = "backend/app/audio/benchmark_dataset/positive_crying/2-107351-A-20.wav"
    wav_bytes = open(cry_file, "rb").read()

    # 1. YAMNet classifies audio sample
    headers = {"X-API-Key": settings.API_KEY, "X-Device-Id": device_id}
    files = {"file": ("cry.wav", wav_bytes, "audio/wav")}
    res = client.post("/api/audio/classify", files=files, headers=headers)
    assert res.status_code == 200
    res_json = res.json()
    assert res_json["classification"] == "BABY CRYING DETECTED"
    assert res_json["is_baby_crying"] is True

    # Authoritative status immediately shows crying
    status_res = client.get("/api/audio/status")
    assert status_res.status_code == 200
    status_data = status_res.json()
    assert status_data["classification"] == "BABY CRYING DETECTED"
    assert status_data["is_baby_crying"] is True

    # 2. ESP32 sends a subsequent high-sound telemetry packet (e.g., 71.4 dB, pitch 0) 2 seconds later
    telemetry_payload = {
        "device_id": device_id,
        "sound_level": 71.4,
        "rms_amplitude": 3719.7,
        "peak_amplitude": 18945,
        "classification": "HIGH_SOUND", # Edge pitch was 0 Hz
        "pitch_hz": 0.0,
        "confidence": 0.88,
        "source": "esp32_device"
    }
    telemetry_res = client.post("/api/readings", json=telemetry_payload, headers=headers)
    assert telemetry_res.status_code in [200, 201]

    # 3. Reading MUST inherit BABY_CRYING_DETECTED during the active crying incident!
    readings_res = client.get(f"/api/readings?device_id={device_id}&limit=5")
    assert readings_res.status_code == 200
    readings = readings_res.json()
    assert len(readings) >= 2
    latest_reading = readings[0]
    assert latest_reading["classification"] == "BABY_CRYING_DETECTED"
    assert latest_reading["sound_level"] == 71.4

    # 4. Authoritative classification status MUST remain BABY CRYING DETECTED (not overwritten)
    status_res2 = client.get("/api/audio/status")
    assert status_res2.status_code == 200
    status_data2 = status_res2.json()
    assert status_data2["classification"] == "BABY CRYING DETECTED"
    assert status_data2["is_baby_crying"] is True

    # 5. Events list MUST contain POSSIBLE_CRYING, NOT duplicate HIGH_SOUND_ACTIVITY
    events_res = client.get(f"/api/events?device_id={device_id}")
    assert events_res.status_code == 200
    events = events_res.json()
    assert len(events) >= 1
    assert events[0]["classification"] == "POSSIBLE_CRYING"
    assert all(e["classification"] != "HIGH_SOUND_ACTIVITY" for e in events)
