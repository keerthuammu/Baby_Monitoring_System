import io
import wave
import pytest
import numpy as np

from app.core.config import settings
from app.audio.features import extract_features, estimate_pitch_autocorr
from app.audio.classifier import AcousticClassifier

def create_synthetic_audio(freq_hz: float, duration_s: float = 1.0, sample_rate: int = 16000, amplitude: int = 8000) -> np.ndarray:
    """Creates a synthetic sine tone for controlled acoustic testing."""
    t = np.linspace(0, duration_s, int(sample_rate * duration_s), endpoint=False)
    signal = amplitude * np.sin(2 * np.pi * freq_hz * t)
    return signal.astype(np.int16)

def create_in_memory_wav(signal: np.ndarray, sample_rate: int = 16000) -> bytes:
    """Encodes a numpy int16 signal into in-memory WAV container bytes."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2) # 16-bit
        wav.setframerate(sample_rate)
        wav.writeframes(signal.tobytes())
    return buf.getvalue()

def test_feature_extraction_pitch():
    # 480 Hz tone (infant cry range: 350 - 650 Hz)
    sig = create_synthetic_audio(freq_hz=480.0, duration_s=0.5, amplitude=10000)
    pitch, periodicity = estimate_pitch_autocorr(sig, sample_rate=16000)
    
    # Pitch should be within 5% of 480 Hz
    assert abs(pitch - 480.0) < 25.0
    assert periodicity > 0.8

def test_classifier_quiet():
    # Very faint noise (< 40 dB)
    quiet_sig = (np.random.randn(8000) * 10).astype(np.int16)
    result = AcousticClassifier.classify_waveform(quiet_sig, sample_rate=16000)
    assert result["classification"] == "QUIET"

def test_classifier_possible_crying():
    # High-pitched vocal frequency (460 Hz) at elevated sound level
    cry_sig = create_synthetic_audio(freq_hz=460.0, duration_s=1.0, amplitude=12000)
    result = AcousticClassifier.classify_waveform(cry_sig, sample_rate=16000)
    assert result["classification"] == "POSSIBLE_CRYING"
    assert result["confidence"] >= 0.70

def test_classifier_non_crying_noise():
    # Low frequency drone (100 Hz rumble) or white noise - elevated volume but NOT crying
    rumble_sig = create_synthetic_audio(freq_hz=100.0, duration_s=1.0, amplitude=12000)
    result = AcousticClassifier.classify_waveform(rumble_sig, sample_rate=16000)
    
    # Must NOT classify as crying!
    assert result["classification"] != "POSSIBLE_CRYING"
    assert result["classification"] in ["HIGH_SOUND_ACTIVITY", "UNCERTAIN"]

def test_audio_endpoint_upload_crying(client):
    cry_sig = create_synthetic_audio(freq_hz=480.0, duration_s=1.0, amplitude=12000)
    wav_bytes = create_in_memory_wav(cry_sig)

    headers = {"X-API-Key": settings.API_KEY}
    files = {"file": ("test_cry.wav", wav_bytes, "audio/wav")}
    data = {"device_id": "esp32-audio-test-01"}

    response = client.post("/api/audio/classify", files=files, data=data, headers=headers)
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["status"] == "success"
    assert res_data["classification"] == "POSSIBLE_CRYING"
    assert res_data["confidence"] >= 0.70

    # Verify event logged in database
    events_res = client.get("/api/events?device_id=esp32-audio-test-01")
    assert events_res.status_code == 200
    events = events_res.json()
    assert len(events) >= 1
    assert events[0]["classification"] == "POSSIBLE_CRYING"

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
    assert "status" in data
    assert data["classification"] in [
        "Possible Baby Crying",
        "Other Sound",
        "Uncertain",
        "Microphone or connection unavailable"
    ]

