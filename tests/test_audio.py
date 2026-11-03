import io
import wave
import pytest
import numpy as np
from app.audio.features import extract_features
from app.audio.classifier import AcousticClassifier
from app.core.config import settings

def create_synthetic_audio(freq_hz=440.0, duration_s=1.0, sample_rate=16000, amplitude=16000):
    t = np.linspace(0, duration_s, int(sample_rate * duration_s), endpoint=False)
    # Pure tone
    audio = amplitude * np.sin(2 * np.pi * freq_hz * t)
    return audio.astype(np.int16)

def create_in_memory_wav(audio_data: np.ndarray, sample_rate=16000):
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2) # 16-bit
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(audio_data.tobytes())
    buffer.seek(0)
    return buffer.read()

def test_feature_extraction_pitch():
    # 440 Hz test tone
    audio_440 = create_synthetic_audio(freq_hz=440.0)
    features = extract_features(audio_440, sample_rate=16000)
    
    assert features["pitch_hz"] is not None
    # Allow small tolerance
    assert 430.0 <= features["pitch_hz"] <= 450.0
    assert features["sound_level_db"] > 40.0

def test_classifier_quiet():
    # Low amplitude noise / quiet
    quiet_sig = create_synthetic_audio(freq_hz=100.0, amplitude=50)
    result = AcousticClassifier.classify_waveform(quiet_sig, sample_rate=16000)
    
    assert result["classification"] in ["QUIET", "NOT_BABY_CRYING"]

def test_classifier_possible_crying():
    # 450 Hz tone inside baby crying range (350-700 Hz) with sufficient amplitude
    cry_sig = create_synthetic_audio(freq_hz=450.0, duration_s=1.0, amplitude=10000)
    result = AcousticClassifier.classify_waveform(cry_sig, sample_rate=16000)
    
    assert result["classification"] in ["POSSIBLE_CRYING", "BABY_CRYING_DETECTED"]
    assert result["confidence"] >= 0.70

def test_classifier_non_crying_noise():
    # 100 Hz tone (e.g., motor hum)
    rumble_sig = create_synthetic_audio(freq_hz=100.0, duration_s=1.0, amplitude=12000)
    result = AcousticClassifier.classify_waveform(rumble_sig, sample_rate=16000)
    
    # Must NOT classify as crying!
    assert result["classification"] != "POSSIBLE_CRYING"
    assert result["classification"] in ["HIGH_SOUND_ACTIVITY", "UNCERTAIN", "NOT_BABY_CRYING"]

def test_audio_endpoint_upload_crying(client):
    cry_file = "backend/app/audio/benchmark_dataset/positive_crying/2-107351-A-20.wav"
    wav_bytes = open(cry_file, "rb").read()

    headers = {"X-API-Key": settings.API_KEY}
    files = {"file": ("test_cry.wav", wav_bytes, "audio/wav")}
    data = {"device_id": "esp32-audio-test-01"}

    response = client.post("/api/audio/classify", files=files, data=data, headers=headers)
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["status"] == "success"
    assert res_data["classification"] == "BABY CRYING DETECTED"
    assert res_data["confidence"] >= 0.70

    # Verify event logged in database
    events_res = client.get("/api/events?device_id=esp32-audio-test-01")
    assert events_res.status_code == 200
    events = events_res.json()
    assert len(events) >= 1
    assert events[0]["classification"] == "BABY_CRYING_DETECTED"

def test_audio_endpoint_unauthorized(client):
    sig = create_synthetic_audio(freq_hz=480.0)
    wav_bytes = create_in_memory_wav(sig)
    files = {"file": ("test.wav", wav_bytes, "audio/wav")}
    response = client.post("/api/audio/classify", files=files)
    assert response.status_code == 401

def test_audio_status_endpoint(client):
    """Verifies the GET /api/audio/status endpoint and freshness response."""
    response = client.get("/api/audio/status")
    assert response.status_code == 200
    data = response.json()
    assert "classification" in data
    assert "code" in data
    assert data["classification"] in [
        "BABY CRYING DETECTED",
        "NOT BABY CRYING",
        "UNCERTAIN",
        "AUDIO UNAVAILABLE"
    ]
    assert data["code"] in [
        "BABY_CRYING_DETECTED",
        "NOT_BABY_CRYING",
        "UNCERTAIN",
        "AUDIO_UNAVAILABLE"
    ]
