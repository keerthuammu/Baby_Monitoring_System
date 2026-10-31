"""
YAMNet Audio Classification Service
-----------------------------------
Integrates Google's YAMNet neural network via local ONNX Runtime on Windows.

Outputs:
- "Possible Baby Crying" (AudioSet classes: 'Baby cry, infant cry', 'Crying, sobbing')
- "Other Sound" (Speech, dog bark, door slam, environmental noise, music)
- "Uncertain" (Borderline, ambiguous acoustic profile)
- "Microphone or connection unavailable" (Staleness / heartbeat timeout)

Disclaimer:
This software provides automated acoustic sound estimates for home monitoring.
It is NOT a medical diagnostic device and cannot determine the cause of crying.
"""

import logging
import os
import csv
import io
import wave
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
import numpy as np
import scipy.signal
import onnxruntime as ort
from app.audio.classifier import AcousticClassifier

logger = logging.getLogger("yamnet_classifier")

MODEL_DIR = os.path.join(os.path.dirname(__file__), "models")
MODEL_PATH = os.path.join(MODEL_DIR, "yamnet.onnx")
CLASS_MAP_PATH = os.path.join(MODEL_DIR, "yamnet_class_map.csv")

class YamnetClassifier:
    _instance: Optional["YamnetClassifier"] = None

    def __init__(self):
        if not os.path.exists(MODEL_PATH) or not os.path.exists(CLASS_MAP_PATH):
            raise FileNotFoundError(f"YAMNet model or class map not found in {MODEL_DIR}")

        # Initialize ONNX inference session
        logger.info(f"Loading YAMNet ONNX model from: {MODEL_PATH}")
        self.session = ort.InferenceSession(
            MODEL_PATH,
            providers=["CPUExecutionProvider"]
        )
        self.input_name = self.session.get_inputs()[0].name
        logger.info("YAMNet ONNX session initialized successfully on CPUExecutionProvider.")

        # Load AudioSet class mapping
        self.class_names: List[str] = []
        with open(CLASS_MAP_PATH, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader)  # Skip header
            for row in reader:
                self.class_names.append(row[2])
        logger.info(f"Loaded {len(self.class_names)} AudioSet class definitions.")

        # State tracking for staleness and consecutive detections
        self.recent_cry_scores: List[float] = []
        self.last_update_time: Optional[datetime] = None
        self.last_classification: str = "AUDIO UNAVAILABLE"
        self.last_code: str = "AUDIO_UNAVAILABLE"
        self.last_confidence: float = 0.0
        self.last_top_classes: List[Dict[str, Any]] = []

    @classmethod
    def get_instance(cls) -> "YamnetClassifier":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def classify_waveform(self, waveform: np.ndarray, sample_rate: int = 16000) -> Dict[str, Any]:
        """
        Classifies an audio waveform.
        Requires 16 kHz sample rate (resamples if necessary).
        """
        now = datetime.now(timezone.utc)

        # Handle empty/invalid input
        if len(waveform) == 0:
            return self._format_unavailable("Empty audio signal")

        # Convert to float32 mono
        signal = waveform.astype(np.float32)
        if len(signal.shape) > 1:
            signal = signal.mean(axis=1)

        # Resample to 16 kHz if necessary (lightning fast linear interpolation)
        if sample_rate != 16000 and sample_rate > 0:
            target_samples = int(len(signal) * 16000 / sample_rate)
            signal = np.interp(
                np.linspace(0, len(signal), target_samples, endpoint=False),
                np.arange(len(signal)),
                signal
            ).astype(np.float32)

        # Normalize amplitude to [-1.0, 1.0]
        max_val = float(np.max(np.abs(signal)))
        if max_val > 1.0:
            signal = signal / max_val

        # Pad to at least 0.975 seconds (15600 samples) if needed by YAMNet
        if len(signal) < 15600:
            pad_len = 15600 - len(signal)
            signal = np.pad(signal, (0, pad_len), mode="constant")

        # Calculate standard physical sound metrics (dB & RMS)
        rms = float(np.sqrt(np.mean(signal ** 2)))
        sound_level_db = round(float(20.0 * np.log10(rms * 32768.0)) if rms > 1e-5 else 0.0, 1)
        peak_amp = int(max_val * 32768) if max_val <= 1.0 else int(max_val)

        # Run YAMNet inference locally
        outputs = self.session.run(None, {self.input_name: signal})
        scores = outputs[0]  # Shape: [num_frames, 521]

        # Average prediction scores across frames
        mean_scores = np.mean(scores, axis=0)

        # YAMNet AudioSet indices for infant crying and vocal distress:
        # Index 20: "Baby cry, infant cry"
        # Index 19: "Crying, sobbing"
        # Index 21: "Whimper"
        # Index 22: "Wail, moan"
        # Index 11: "Screaming"
        cry_score = float(max(
            mean_scores[20],
            mean_scores[19],
            mean_scores[21],
            mean_scores[22],
            mean_scores[11]
        ))

        # Also evaluate physical acoustic profile (F0 pitch & cry band energy)
        # Scale to 16-bit amplitude range for standard dB SPL calculations
        int_signal = (signal * 32767.0).astype(np.float64)
        acoustic_res = AcousticClassifier.classify_waveform(int_signal, sample_rate)
        acoustic_class = acoustic_res.get("classification")
        acoustic_conf = acoustic_res.get("confidence", 0.5)

        # Reset smoothing buffer if more than 4.0 seconds elapsed since previous audio chunk
        if self.last_update_time is not None:
            if (now - self.last_update_time).total_seconds() > 4.0:
                self.recent_cry_scores.clear()

        # If current frame is clearly non-crying (cry_score < 0.05), clear old crying history
        if cry_score < 0.05:
            self.recent_cry_scores.clear()

        # Smooth across last 3 inferences (rolling window) to prevent isolated spikes
        self.recent_cry_scores.append(cry_score)
        if len(self.recent_cry_scores) > 3:
            self.recent_cry_scores.pop(0)
        smoothed_cry_score = float(np.mean(self.recent_cry_scores))

        # Top 5 detected sound events from YAMNet
        top_indices = np.argsort(mean_scores)[::-1][:5]
        top_classes = [
            {"class_name": self.class_names[idx], "score": round(float(mean_scores[idx]), 3)}
            for idx in top_indices
        ]

        # Classification decision boundaries:
        CRY_CLASS_NAMES = {
            "Baby cry, infant cry",
            "Crying, sobbing",
            "Whimper",
            "Wail, moan",
            "Screaming"
        }
        any_top_cry = any(c["class_name"] in CRY_CLASS_NAMES and c["score"] >= 0.10 for c in top_classes[:3])

        # 1. BABY CRYING DETECTED: YAMNet AudioSet cry >= 0.20 OR top cry class OR physical infant cry profile
        if (smoothed_cry_score >= 0.20 and sound_level_db >= 38.0) or any_top_cry or (acoustic_class == "POSSIBLE_CRYING"):
            code = "BABY_CRYING_DETECTED"
            display_label = "BABY CRYING DETECTED"
            confidence = max(round(smoothed_cry_score, 2), round(acoustic_conf, 2), 0.88)
        elif smoothed_cry_score >= 0.10:
            # Borderline / ambiguous crying signal
            code = "UNCERTAIN"
            display_label = "UNCERTAIN"
            confidence = round(smoothed_cry_score, 2)
        else:
            # Definite non-crying sound (speech, music, door slam, claps, ambient)
            code = "NOT_BABY_CRYING"
            display_label = "NOT BABY CRYING"
            primary_other = top_classes[0]["score"] if top_classes else 0.80
            confidence = round(primary_other, 2)

        # Update service cache with inference completion timestamp
        completion_time = datetime.now(timezone.utc)
        self.last_update_time = completion_time
        self.last_classification = display_label
        self.last_code = code
        self.last_confidence = confidence
        self.last_top_classes = top_classes

        logger.info(
            f"[INFERENCE] Completed in {len(signal)/sample_rate:.2f}s audio | "
            f"Result: {display_label} ({confidence*100:.0f}%) | "
            f"dB: {sound_level_db} | Top: {top_classes[0]['class_name'] if top_classes else 'N/A'}"
        )

        return {
            "classification": code,
            "display_label": display_label,
            "confidence": confidence,
            "sound_level_db": sound_level_db,
            "rms_amplitude": round(rms * 32768.0, 1),
            "peak_amplitude": peak_amp,
            "top_classes": top_classes,
            "crying_score_raw": round(cry_score, 3),
            "is_baby_crying": (code == "BABY_CRYING_DETECTED"),
            "timestamp": completion_time.isoformat(),
            "status": "ACTIVE"
        }

    def classify_wav_bytes(self, wav_bytes: bytes) -> Dict[str, Any]:
        """Classifies a WAV container or raw 16-bit mono 16kHz PCM from bytes."""
        if len(wav_bytes) == 0:
            return self._format_unavailable("Empty audio signal")

        # Check for standard RIFF / WAV header
        if len(wav_bytes) > 44 and wav_bytes[:4] == b"RIFF":
            try:
                with wave.open(io.BytesIO(wav_bytes), "rb") as wav:
                    sample_rate = wav.getframerate()
                    n_channels = wav.getnchannels()
                    sample_width = wav.getsampwidth()
                    n_frames = wav.getnframes()
                    raw_data = wav.readframes(n_frames)

                    if sample_width == 2:
                        signal = np.frombuffer(raw_data, dtype=np.int16).astype(np.float32) / 32768.0
                    elif sample_width == 4:
                        signal = np.frombuffer(raw_data, dtype=np.int32).astype(np.float32) / 2147483648.0
                    else:
                        signal = np.frombuffer(raw_data, dtype=np.int8).astype(np.float32) / 128.0

                    if n_channels > 1:
                        signal = signal.reshape(-1, n_channels).mean(axis=1)

                    return self.classify_waveform(signal, sample_rate=sample_rate)
            except Exception:
                pass

        # Raw 16-bit PCM fallback (standard ESP32 stream format)
        try:
            signal = np.frombuffer(wav_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            return self.classify_waveform(signal, sample_rate=16000)
        except Exception as e:
            return self._format_unavailable(f"Invalid audio format: {str(e)}")

    def get_current_status(self, staleness_seconds: float = 6.0) -> Dict[str, Any]:
        """
        Returns the latest classification status, enforcing a freshness guard.
        If no audio update has been received within staleness_seconds,
        marks the status as 'AUDIO UNAVAILABLE'.
        """
        now = datetime.now(timezone.utc)

        if self.last_update_time is None:
            return self._format_unavailable("Waiting for microphone audio stream")

        time_since_update = (now - self.last_update_time).total_seconds()
        if time_since_update > staleness_seconds:
            return {
                "classification": "AUDIO UNAVAILABLE",
                "code": "AUDIO_UNAVAILABLE",
                "is_baby_crying": False,
                "confidence": 0.0,
                "status": "UNAVAILABLE",
                "is_fresh": False,
                "seconds_since_update": round(time_since_update, 1),
                "last_update": self.last_update_time.isoformat(),
                "top_classes": []
            }

        return {
            "classification": self.last_classification,
            "code": getattr(self, "last_code", "NOT_BABY_CRYING"),
            "is_baby_crying": (getattr(self, "last_code", "") == "BABY_CRYING_DETECTED"),
            "confidence": self.last_confidence,
            "status": "ACTIVE",
            "is_fresh": True,
            "seconds_since_update": round(time_since_update, 1),
            "last_update": self.last_update_time.isoformat(),
            "top_classes": self.last_top_classes
        }

    def _format_unavailable(self, reason: str) -> Dict[str, Any]:
        return {
            "classification": "AUDIO UNAVAILABLE",
            "code": "AUDIO_UNAVAILABLE",
            "is_baby_crying": False,
            "confidence": 0.0,
            "status": "UNAVAILABLE",
            "is_fresh": False,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "top_classes": []
        }
