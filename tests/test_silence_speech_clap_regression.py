"""
End-to-End Regression Test Suite:
Validates that:
1. Silence (room_silence.wav) does NOT return BABY CRYING DETECTED.
2. Room noise (quiet_room_noise.wav) does NOT return BABY CRYING DETECTED.
3. Speech (female_speech_1.wav) does NOT return BABY CRYING DETECTED.
4. Clapping (clapping_1.wav) does NOT return BABY CRYING DETECTED.
5. Real baby cry (2-107351-A-20.wav) DOES return BABY CRYING DETECTED.
6. Database storage & authoritative API status consistency: 'NOT_BABY_CRYING' is never converted to 'BABY_CRYING_DETECTED'.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath("backend"))
sys.path.insert(0, os.path.abspath("."))

from app.audio.yamnet_classifier import YamnetClassifier
from app.audio.evaluate_benchmark import load_wav_as_16k_mono
from app.services.monitor_service import MonitorService
from app.schemas.schemas import ReadingCreate
from app.core.database import SessionLocal, init_db

init_db()


class TestSilenceSpeechClapRegression(unittest.TestCase):

    def setUp(self):
        self.classifier = YamnetClassifier.get_instance()
        self.classifier.reset_temporal_state()
        self.db = SessionLocal()

    def tearDown(self):
        self.classifier.reset_temporal_state()
        self.db.close()

    def test_silence_never_crying(self):
        """Silence must return NOT_BABY_CRYING via noise floor gate."""
        sig = load_wav_as_16k_mono("backend/app/audio/benchmark_dataset/negative_ambient/room_silence.wav")
        res = self.classifier.classify_waveform(sig[:16000], sample_rate=16000)
        self.assertEqual(res["classification"], "NOT_BABY_CRYING")
        self.assertEqual(res["display_label"], "NOT BABY CRYING")
        self.assertFalse(res["is_baby_crying"])

    def test_room_noise_never_crying(self):
        """Ambient room noise must return NOT_BABY_CRYING via noise floor gate."""
        sig = load_wav_as_16k_mono("backend/app/audio/benchmark_dataset/negative_ambient/quiet_room_noise.wav")
        res = self.classifier.classify_waveform(sig[:16000], sample_rate=16000)
        self.assertEqual(res["classification"], "NOT_BABY_CRYING")
        self.assertEqual(res["display_label"], "NOT BABY CRYING")
        self.assertFalse(res["is_baby_crying"])

    def test_adult_speech_never_crying(self):
        """Adult speech must return NOT_BABY_CRYING via dominant negative class."""
        sig = load_wav_as_16k_mono("backend/app/audio/benchmark_dataset/negative_speech/female_speech_1.wav")
        res = self.classifier.classify_waveform(sig[:16000], sample_rate=16000)
        self.assertEqual(res["classification"], "NOT_BABY_CRYING")
        self.assertEqual(res["display_label"], "NOT BABY CRYING")
        self.assertFalse(res["is_baby_crying"])

    def test_clapping_never_crying(self):
        """Clapping / transient sounds must return NOT_BABY_CRYING via transient impulse veto."""
        sig = load_wav_as_16k_mono("backend/app/audio/benchmark_dataset/negative_household/clapping_1.wav")
        res = self.classifier.classify_waveform(sig[:16000], sample_rate=16000)
        self.assertEqual(res["classification"], "NOT_BABY_CRYING")
        self.assertEqual(res["display_label"], "NOT BABY CRYING")
        self.assertFalse(res["is_baby_crying"])

    def test_real_baby_cry_returns_crying(self):
        """Real infant cry file must return BABY_CRYING_DETECTED."""
        with open("backend/app/audio/benchmark_dataset/positive_crying/2-107351-A-20.wav", "rb") as f:
            wav_bytes = f.read()
        res = self.classifier.classify_wav_bytes(wav_bytes)
        self.assertEqual(res["classification"], "BABY_CRYING_DETECTED")
        self.assertEqual(res["display_label"], "BABY CRYING DETECTED")
        self.assertTrue(res["is_baby_crying"])

    def test_database_and_authoritative_status_never_confuse_not_baby_crying(self):
        """Ingesting quiet/ambient reading must never be converted to BABY_CRYING_DETECTED."""
        reading_payload = ReadingCreate(
            device_id="esp32-nursery-01",
            sound_level=35.0,
            rms_amplitude=100.0,
            peak_amplitude=300,
            pitch_hz=0.0,
            classification="QUIET",
            confidence=0.95
        )
        saved = MonitorService.record_reading(self.db, reading_payload)
        self.assertEqual(saved.classification, "NOT_BABY_CRYING")

        auth = MonitorService.get_authoritative_status(self.db)
        self.assertEqual(auth["code"], "NOT_BABY_CRYING")
        self.assertEqual(auth["classification"], "NOT BABY CRYING")
        self.assertFalse(auth["is_baby_crying"])

        # Also verify get_readings does not mutate NOT_BABY_CRYING into crying
        all_readings = MonitorService.get_readings(self.db, limit=5)
        for r in all_readings:
            if r.id == saved.id:
                self.assertEqual(r.classification, "NOT_BABY_CRYING")


if __name__ == "__main__":
    unittest.main()

