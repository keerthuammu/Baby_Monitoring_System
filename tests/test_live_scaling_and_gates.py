import os
import sys
import unittest
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

from tests.compare_live_vs_dataset import load_wav
from app.audio.yamnet_classifier import YamnetClassifier
from app.services.monitor_service import MonitorService
from app.schemas.schemas import ReadingCreate
from app.core.database import SessionLocal, Base, engine

class TestLiveScalingAndGates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)
        cls.classifier = YamnetClassifier.get_instance()
        cls.db = SessionLocal()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_zero_signal_and_dead_mic_safety(self):
        """Hard rule: All-zeros, flatlines, and dead mics must NEVER trigger crying."""
        silent = np.zeros(16000, dtype=np.float32)
        res = self.classifier.classify_waveform(silent)
        self.assertEqual(res["classification"], "NOT_BABY_CRYING")
        self.assertFalse(res["is_baby_crying"])
        self.assertEqual(res["decision_rule"], "zero_energy_silence_gate")

        flatline = np.full(16000, 0.3, dtype=np.float32)
        res2 = self.classifier.classify_waveform(flatline)
        self.assertEqual(res2["classification"], "NOT_BABY_CRYING")
        self.assertFalse(res2["is_baby_crying"])

    def test_live_quiet_cry_detection(self):
        """Quiet cry with live INMP441-level amplitude (RMS ~150 in int16) must be detected via window normalization."""
        dataset_sig = load_wav("backend/app/audio/benchmark_dataset/positive_crying/1-211527-C-20.wav")
        # Attenuate to mimic distance from INMP441 mic (RMS ~150 in int16 = ~0.0045 in float)
        live_chunk = dataset_sig * (150.0 / (np.sqrt(np.mean(dataset_sig[:15600]**2)) * 32768.0))
        self.classifier.reset_temporal_state()
        res = self.classifier.classify_waveform(live_chunk[:15600])
        self.assertIn(res["classification"], ["BABY_CRYING_DETECTED", "UNCERTAIN"])
        self.assertGreater(res["crying_score"], 0.20)

    def test_live_loud_clap_rejection(self):
        """Loud clapping must produce NOT_BABY_CRYING despite high physical sound intensity."""
        clap_sig = load_wav("backend/app/audio/benchmark_dataset/negative_household/clapping_1.wav")
        self.classifier.reset_temporal_state()
        res = self.classifier.classify_waveform(clap_sig[:15600])
        self.assertEqual(res["classification"], "NOT_BABY_CRYING")
        self.assertFalse(res["is_baby_crying"])

    def test_normal_speech_rejection(self):
        """Normal speech (male and female) must produce NOT_BABY_CRYING."""
        female_sig = load_wav("backend/app/audio/benchmark_dataset/negative_speech/female_speech_1.wav")
        male_sig = load_wav("backend/app/audio/benchmark_dataset/negative_speech/male_speech_1.wav")
        
        self.classifier.reset_temporal_state()
        res_f = self.classifier.classify_waveform(female_sig[:15600])
        self.assertEqual(res_f["classification"], "NOT_BABY_CRYING")

        self.classifier.reset_temporal_state()
        res_m = self.classifier.classify_waveform(male_sig[:15600])
        self.assertEqual(res_m["classification"], "NOT_BABY_CRYING")

    def test_room_noise_and_silence_rejection(self):
        """Ambient room noise and hum must produce NOT_BABY_CRYING."""
        room_sig = load_wav("backend/app/audio/benchmark_dataset/negative_ambient/quiet_room_noise.wav")
        hum_sig = load_wav("backend/app/audio/benchmark_dataset/negative_ambient/electrical_hum.wav")

        self.classifier.reset_temporal_state()
        res_r = self.classifier.classify_waveform(room_sig[:15600])
        self.assertEqual(res_r["classification"], "NOT_BABY_CRYING")

        self.classifier.reset_temporal_state()
        res_h = self.classifier.classify_waveform(hum_sig[:15600])
        self.assertEqual(res_h["classification"], "NOT_BABY_CRYING")

    def test_four_authoritative_states_enforced(self):
        """Only the 4 standard states can ever be returned."""
        valid_states = {"BABY CRYING DETECTED", "NOT BABY CRYING", "UNCERTAIN", "AUDIO UNAVAILABLE"}
        status = MonitorService.get_authoritative_status(self.db, staleness_seconds=8.0)
        self.assertIn(status["classification"], valid_states)

if __name__ == "__main__":
    unittest.main()

