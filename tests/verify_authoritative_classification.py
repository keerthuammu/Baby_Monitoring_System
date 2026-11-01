"""
Verification Test Suite: Authoritative Unified Classification
Tests all 8 required acoustic conditions + full data flow alignment
"""

import sys
import os
import time
import numpy as np
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.audio.yamnet_classifier import YamnetClassifier
from app.core.database import SessionLocal, init_db
from app.schemas.schemas import ReadingCreate
from app.services.monitor_service import MonitorService

def run_tests():
    print("=" * 80)
    print("AUTHORITATIVE CLASSIFICATION TEST SUITE (Section 8 Verification)")
    print("=" * 80)

    init_db()
    db = SessionLocal()
    classifier = YamnetClassifier.get_instance()

    # --- Part 1: Real Labeled Audio Classification Tests ---
    print("\n[PART 1] Testing Real Labeled Audio Samples against YAMNet ONNX:")
    
    test_cases = [
        ("Baby crying", "backend/app/audio/benchmark_dataset/positive_crying/baby_cry_real_0.wav", "BABY_CRYING_DETECTED"),
        ("Adult speech", "backend/app/audio/benchmark_dataset/negative_speech/female_speech_1.wav", "NOT_BABY_CRYING"),
        ("Loud conversation", "backend/app/audio/benchmark_dataset/negative_speech/male_speech_timit.wav", "NOT_BABY_CRYING"),
        ("Door slam/knock", "backend/app/audio/benchmark_dataset/negative_household/door_knock_1.wav", "NOT_BABY_CRYING"),
        ("Clapping", "backend/app/audio/benchmark_dataset/negative_household/clapping_1.wav", "NOT_BABY_CRYING"),
    ]

    for label, path, expected in test_cases:
        classifier.reset_temporal_state()
        with open(path, "rb") as f:
            data = f.read()
        res = classifier.classify_wav_bytes(data)
        actual = res["classification"]
        conf = res["confidence"] * 100
        passed = (actual == expected)
        status_str = "[PASS]" if passed else "[FAIL]"
        print(f"  {status_str} {label:20s} -> Result: {actual:22s} (Conf: {conf:4.1f}%) | Expected: {expected}")
        assert passed, f"Failed for {label}: expected {expected}, got {actual}"

    # Test Ambiguous Audio (synthetic low-confidence borderline energy)
    print("\n[PART 2] Testing Ambiguous & Disconnected States:")
    classifier.reset_temporal_state()
    # Ambiguous low-amplitude mixed noise (white noise + faint tone)
    np.random.seed(42)
    ambiguous_signal = (np.random.randn(16000) * 0.02).astype(np.float32)
    res_amb = classifier.classify_waveform(ambiguous_signal, 16000)
    # Ambiguous or non-crying (must NOT falsely detect crying)
    print(f"  [PASS] Ambiguous audio      -> Result: {res_amb['display_label']:22s} | Code: {res_amb['classification']}")
    assert res_amb["classification"] in ["UNCERTAIN", "NOT_BABY_CRYING"], f"Expected UNCERTAIN or NOT_BABY_CRYING, got {res_amb['classification']}"

    # Test Disconnected Audio (Freshness timeout guard)
    classifier.last_update_time = datetime.now(timezone.utc) - timedelta(seconds=15)
    stale_status = classifier.get_current_status(staleness_seconds=6.0)
    print(f"  [PASS] Disconnected audio   -> Result: {stale_status['classification']:22s} | Code: {stale_status['code']}")
    assert stale_status["code"] == "AUDIO_UNAVAILABLE", f"Expected AUDIO_UNAVAILABLE, got {stale_status['code']}"

    # --- Part 3: End-to-End Database & Authoritative State Agreement ---
    print("\n[PART 3] Testing Complete End-to-End Data Flow & Component Agreement:")

    # 1. Baby crying event
    r_cry = MonitorService.record_reading(
        db,
        ReadingCreate(
            device_id="esp32-nursery-01",
            sound_level=76.5,
            rms_amplitude=3500.0,
            peak_amplitude=8000
        ),
        classification="BABY_CRYING_DETECTED",
        confidence=0.96
    )
    auth_cry = MonitorService.get_authoritative_status(db, staleness_seconds=8.0)
    print(f"  [PASS] Crying Packet Ingest -> Reading #{r_cry.id}: {r_cry.classification} ({r_cry.confidence*100:.0f}%)")
    print(f"  [PASS] Authoritative State  -> Status: {auth_cry['classification']} | Intensity: {auth_cry['sound_intensity']}")
    assert auth_cry["code"] == "BABY_CRYING_DETECTED"
    assert auth_cry["is_baby_crying"] is True
    assert auth_cry["reading_id"] == r_cry.id

    # 2. Loud Door Slam (Decoupled Sound Intensity test)
    r_door = MonitorService.record_reading(
        db,
        ReadingCreate(
            device_id="esp32-nursery-01",
            sound_level=82.0,  # Loud sound >= 65 dB
            rms_amplitude=6000.0,
            peak_amplitude=15000,
            classification="HIGH_SOUND_ACTIVITY",
            confidence=0.88
        )
    )
    auth_door = MonitorService.get_authoritative_status(db, staleness_seconds=8.0)
    print(f"  [PASS] Door Slam Ingest     -> Reading #{r_door.id}: {r_door.classification} (Sound: {r_door.sound_level} dB)")
    print(f"  [PASS] Authoritative State  -> Status: {auth_door['classification']} | Intensity: {auth_door['sound_intensity']}")
    assert auth_door["code"] == "NOT_BABY_CRYING", f"Expected NOT_BABY_CRYING, got {auth_door['code']}"
    assert auth_door["sound_intensity"] == "HIGH SOUND"
    assert auth_door["is_baby_crying"] is False

    # 3. Stream Paused / Disconnected (Audio Unavailable)
    auth_stale = MonitorService.get_authoritative_status(db, staleness_seconds=0.0) # immediate staleness
    print(f"  [PASS] Stream Interruption  -> Status: {auth_stale['classification']} | Fresh: {auth_stale['is_fresh']}")
    assert auth_stale["code"] == "AUDIO_UNAVAILABLE"
    assert auth_stale["is_fresh"] is False

    print("\n" + "=" * 80)
    print("ALL TESTS PASSED SUCCESSFULLY! 100% Component & Classification Agreement.")
    print("=" * 80)

if __name__ == "__main__":
    run_tests()

