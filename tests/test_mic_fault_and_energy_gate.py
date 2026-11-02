import sys
import os
import unittest
import numpy as np

# Ensure backend is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

from app.core.config import settings
from app.audio.yamnet_classifier import YamnetClassifier
from app.services.monitor_service import MonitorService
from app.schemas.schemas import ReadingCreate
from app.core.database import SessionLocal, Base, engine
from app.models.models import SensorReading

class TestMicFaultAndEnergyGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)
        cls.classifier = YamnetClassifier.get_instance()
        cls.db = SessionLocal()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_zero_energy_waveform_silence_gate(self):
        """Zero-energy all-zeros signal must immediately return NOT_BABY_CRYING."""
        silent_pcm = np.zeros(16000, dtype=np.float32)
        res = self.classifier.classify_waveform(silent_pcm, sample_rate=16000)
        self.assertEqual(res["classification"], "NOT_BABY_CRYING")
        self.assertEqual(res["display_label"], "NOT BABY CRYING")
        self.assertFalse(res["is_baby_crying"])
        self.assertEqual(res["decision_rule"], "zero_energy_silence_gate")

    def test_constant_dc_waveform_gate(self):
        """Constant DC flatline signal must immediately return NOT_BABY_CRYING."""
        flatline = np.full(16000, 0.4, dtype=np.float32)
        res = self.classifier.classify_waveform(flatline, sample_rate=16000)
        self.assertEqual(res["classification"], "NOT_BABY_CRYING")
        self.assertFalse(res["is_baby_crying"])

    def test_zero_energy_reading_cannot_be_crying(self):
        """A telemetry reading with rms=0, peak=0 must NEVER produce BABY_CRYING_DETECTED."""
        reading_in = ReadingCreate(
            device_id="test-dead-mic-device",
            sound_level=0.0,
            rms_amplitude=0.0,
            peak_amplitude=0,
            classification="POSSIBLE_CRYING", # Even if edge erroneously tagged it
            confidence=0.92,
            source="esp32_device"
        )
        saved = MonitorService.record_reading(self.db, reading_in)
        self.assertNotEqual(saved.classification, "BABY_CRYING_DETECTED")
        self.assertNotEqual(saved.classification, "POSSIBLE_CRYING")

    def test_dead_mic_consecutive_packets(self):
        """3 consecutive zero-energy packets must transition status to AUDIO UNAVAILABLE / MIC_FAULT."""
        dev = "test-unplugged-mic-01"
        MonitorService._consecutive_dead_packets[dev] = 0

        for i in range(3):
            reading_in = ReadingCreate(
                device_id=dev,
                sound_level=0.0,
                rms_amplitude=0.0,
                peak_amplitude=0,
                source="esp32_device"
            )
            saved = MonitorService.record_reading(self.db, reading_in)

        # On the 3rd consecutive packet, it must flag AUDIO_UNAVAILABLE
        self.assertEqual(saved.classification, "AUDIO_UNAVAILABLE")
        self.assertIsNone(saved.confidence)

        auth = MonitorService.get_authoritative_status(self.db, staleness_seconds=8.0)
        self.assertEqual(auth["classification"], "AUDIO UNAVAILABLE")
        self.assertEqual(auth["code"], "AUDIO_UNAVAILABLE")
        self.assertEqual(auth["model_status"], "MIC_FAULT")
        self.assertIn("Microphone not producing signal", auth.get("reason", ""))

if __name__ == "__main__":
    unittest.main()
