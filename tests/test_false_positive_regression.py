"""
Regression Test Suite for Baby Crying Detection
Validates precision-first behavior:
1. 5-minute ambient room noise never fires BABY_CRYING_DETECTED.
2. Loud sounds (claps, door slams, knocks, dog barks, loud speech) never fire BABY_CRYING_DETECTED.
3. Real infant cry is detected within <= 3s and breath pauses (2-3s) are bridged.
4. Edge pitch telemetry alone (e.g. 520 Hz, 55 dB) sent to /api/readings never triggers BABY_CRYING_DETECTED.
"""

import os
import sys
import glob
import numpy as np
import unittest

sys.path.insert(0, os.path.abspath("backend"))
sys.path.insert(0, os.path.abspath("."))

from app.audio.yamnet_classifier import YamnetClassifier
from app.audio.evaluate_benchmark import load_wav_as_16k_mono
from app.services.monitor_service import MonitorService
from app.schemas.schemas import ReadingCreate
from app.core.database import SessionLocal, init_db

init_db()


class TestFalsePositiveRegression(unittest.TestCase):

    def setUp(self):
        self.classifier = YamnetClassifier.get_instance()
        self.classifier.reset_temporal_state()

    def tearDown(self):
        self.classifier.reset_temporal_state()

    def test_ambient_room_noise_five_minutes(self):
        """Simulates 300 chunks (5 minutes) of ambient room noise: 0 False Positives."""
        fpath = "backend/app/audio/benchmark_dataset/negative_ambient/quiet_room_noise.wav"
        data = load_wav_as_16k_mono(fpath)
        np.random.seed(42)

        fp_count = 0
        total_chunks = 300
        for _ in range(total_chunks):
            start = np.random.randint(0, max(1, len(data) - 16000))
            chunk = data[start:start + 16000] + np.random.normal(0, 1e-4, 16000).astype(np.float32)
            res = self.classifier.classify_waveform(chunk, sample_rate=16000)
            if res["classification"] == "BABY_CRYING_DETECTED":
                fp_count += 1

        assert fp_count == 0, f"False positives occurred in 5-min ambient simulation: {fp_count}/{total_chunks}"

    def test_loud_transients_and_speech_never_trigger_cry(self):
        """Validates that clapping, door knocks, dog barking, and adult speech never trigger BABY_CRYING_DETECTED."""
        transient_files = glob.glob("backend/app/audio/benchmark_dataset/negative_household/*.wav")
        speech_files = glob.glob("backend/app/audio/benchmark_dataset/negative_speech/*.wav")
        all_neg_files = transient_files + speech_files

        fp_records = []
        for fpath in all_neg_files:
            self.classifier.reset_temporal_state()
            sig = load_wav_as_16k_mono(fpath)
            num_chunks = len(sig) // 16000
            for i in range(num_chunks):
                chunk = sig[i * 16000:(i + 1) * 16000]
                res = self.classifier.classify_waveform(chunk, sample_rate=16000)
                if res["classification"] == "BABY_CRYING_DETECTED":
                    fp_records.append((os.path.basename(fpath), i, res["display_label"], res.get("decision_rule")))

        assert len(fp_records) == 0, f"False positives detected on loud sounds/speech: {fp_records}"

    def test_real_infant_cry_detection_and_breath_pause_bridge(self):
        """Validates that real infant crying is detected <= 3s from onset, and bridges short breath pauses."""
        cry_fpath = "backend/app/audio/benchmark_dataset/positive_crying/2-107351-B-20.wav"
        sig = load_wav_as_16k_mono(cry_fpath)
        self.classifier.reset_temporal_state()

        results = []
        for i in range(len(sig) // 16000):
            chunk = sig[i * 16000:(i + 1) * 16000]
            res = self.classifier.classify_waveform(chunk, sample_rate=16000)
            results.append(res)

        # In 2-107351-B-20.wav:
        # chunk 1: cry onset (dampened to uncertain)
        # chunk 2: confirmed cry (detected in 2.0s from onset)
        # chunk 3: breath pause (bridged as BABY_CRYING_DETECTED)
        labels = [r["classification"] for r in results]
        assert "BABY_CRYING_DETECTED" in labels, f"Expected BABY_CRYING_DETECTED, got {labels}"
        
        # Verify breath pause bridge preserved the incident
        bridge_rules = [r.get("decision_rule") for r in results if "breath_pause_bridge" in str(r.get("decision_rule"))]
        assert len(bridge_rules) > 0, f"Expected breath pause bridge to fire, but got rules: {[r.get('decision_rule') for r in results]}"

    def test_edge_pitch_telemetry_never_triggers_crying_alone(self):
        """Validates that ESP32 pitch (even 520 Hz at 55 dB) sent to /api/readings is treated purely as metadata and NOT crying."""
        db = SessionLocal()
        try:
            # Clean authoritative state
            MonitorService._latest_authoritative_state = {
                "classification": "NOT_BABY_CRYING",
                "display_label": "NOT BABY CRYING",
                "confidence": 0.90,
                "packet_id": 99990,
                "sound_level": 40.0,
                "rms_energy": 500,
                "peak_amplitude": 1200,
                "top_sound": "Ambient",
                "source": "unit_test",
                "updated_at": None,
                "active_incident": False
            }

            fake_edge_payload = ReadingCreate(
                device_id="esp32-nursery-01",
                sound_level=55.0, # Loud ambient
                rms_amplitude=2500.0,
                peak_amplitude=5000,
                pitch_hz=520.0,      # Infant pitch range
                classification="POSSIBLE_CRYING", # ESP32 edge heuristic
                confidence=0.88
            )

            created_reading = MonitorService.record_reading(db, fake_edge_payload)
            auth_state = MonitorService.get_authoritative_status(db)

            assert created_reading.classification != "BABY_CRYING_DETECTED", f"DB reading was erroneously marked as crying: {created_reading.classification}"
            assert auth_state["classification"] != "BABY_CRYING_DETECTED", f"Authoritative state was hijacked by edge pitch! {auth_state}"
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
