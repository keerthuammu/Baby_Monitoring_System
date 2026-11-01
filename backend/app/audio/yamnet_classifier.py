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
from app.core.config import settings

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

        # State tracking for staleness and temporal accumulation
        self.window_history: List[Dict[str, Any]] = []
        self.active_crying_incident: bool = False
        self.consecutive_non_cry_count: int = 0
        self.recent_cry_scores: List[float] = []
        self.last_update_time: Optional[datetime] = None
        self.last_classification: str = "AUDIO UNAVAILABLE"
        self.last_code: str = "AUDIO_UNAVAILABLE"
        self.last_confidence: float = 0.0
        self.last_top_classes: List[Dict[str, Any]] = []

    def reset_temporal_state(self):
        """Resets window accumulation and hysteresis incident trackers."""
        self.window_history.clear()
        self.active_crying_incident = False
        self.consecutive_non_cry_count = 0
        self.recent_cry_scores.clear()

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

        # Calculate standard physical sound metrics (dB & RMS) on raw acoustic signal
        rms = float(np.sqrt(np.mean(signal ** 2)))
        sound_level_db = round(float(20.0 * np.log10(rms * 32768.0)) if rms > 1e-5 else 0.0, 1)
        peak_amp = int(max_val * 32768) if max_val <= 1.0 else int(max_val)

        # Dynamic Range Normalization (AGC) for YAMNet Neural Input
        # YAMNet was trained on audio normalized across standard dynamic range.
        # If signal is non-silent (peak > 0.005) but quiet, scale it so neural features aren't suppressed.
        inference_signal = signal.copy()
        if max_val > 0.005 and max_val < 0.50:
            gain = min(0.50 / max_val, 10.0)
            inference_signal = inference_signal * gain

        # Run YAMNet inference locally
        outputs = self.session.run(None, {self.input_name: inference_signal})
        scores = outputs[0]  # Shape: [num_frames, 521]

        # Average prediction scores across frames
        mean_scores = np.mean(scores, axis=0)

        # AudioSet Class Indices for Baby Crying and Competing Sound Classes
        # Crying classes
        cry_indices = [20, 19, 21, 22]  # Baby cry, Crying/sobbing, Whimper, Wail/moan
        # Competing non-crying classes
        speech_indices = [0, 1, 2, 4, 5, 6, 7]  # Speech, Child speech, Conversation, Male, Female, Shout, Yell
        laughter_indices = [13, 14, 15]  # Laughter, Baby laughter/giggle, Snicker
        clap_indices = [58, 62]  # Clapping, Applause
        music_index = 132
        silence_index = 494
        door_indices = [348, 349, 351]

        # 1. Primary YAMNet Crying Evidence
        cry_score = float(max(mean_scores[idx] for idx in cry_indices))
        cry_energy = float(sum(mean_scores[idx] for idx in cry_indices))

        # 2. Competing Negative Evidence (Inhibition)
        speech_score = float(max(mean_scores[idx] for idx in speech_indices))
        laughter_score = float(max(mean_scores[idx] for idx in laughter_indices))
        clap_score = float(max(mean_scores[idx] for idx in clap_indices))
        music_score = float(mean_scores[music_index])
        silence_score = float(mean_scores[silence_index])
        door_score = float(max(mean_scores[idx] for idx in door_indices))
        dominant_negative = max(speech_score, laughter_score, clap_score, music_score, door_score)

        # 3. Acoustic Pitch & Spectral Supporting Evidence
        int_signal = (signal * 32767.0).astype(np.float64)
        acoustic_res = AcousticClassifier.classify_waveform(int_signal, sample_rate)
        features = acoustic_res.get("features", {})
        pitch = features.get("pitch_hz", 0.0)
        periodicity = features.get("periodicity", 0.0)
        cry_band_ratio = features.get("cry_band_ratio", 0.0)

        # Infant vocal fundamental pitch is between 300 - 720 Hz with distinct harmonic periodicity
        has_infant_pitch = (300.0 <= pitch <= 720.0) and (periodicity >= 0.28) and (cry_band_ratio >= 0.28)

        # Top 5 detected sound events from YAMNet for explainability
        top_indices = np.argsort(mean_scores)[::-1][:5]
        top_classes = [
            {"class_name": self.class_names[idx], "score": round(float(mean_scores[idx]), 3)}
            for idx in top_indices
        ]
        top_sound_name = top_classes[0]["class_name"] if top_classes else "Unknown"
        top_sound_score = top_classes[0]["score"] if top_classes else 0.0

        CRY_CLASS_NAMES = {
            "Baby cry, infant cry",
            "Crying, sobbing",
            "Whimper",
            "Wail, moan"
        }
        is_cry_in_top3 = any(c["class_name"] in CRY_CLASS_NAMES for c in top_classes[:3])
        is_cry_top1 = top_sound_name in CRY_CLASS_NAMES

        # 4. Calibrated Multi-Evidence Decision Strategy (Per-Window)
        high_thresh = getattr(settings, "CRY_SCORE_HIGH_THRESHOLD", 0.20)
        low_thresh = getattr(settings, "CRY_SCORE_LOW_THRESHOLD", 0.12)

        # Rule A: Strong YAMNet Crying Evidence (crying is top-ranked or cumulative crying energy dominates competing sounds)
        if (is_cry_top1 and (cry_score >= high_thresh or cry_energy >= 0.26)) or (is_cry_in_top3 and (cry_score >= 0.20 or cry_energy >= 0.26) and cry_energy >= 0.7 * top_sound_score):
            raw_code = "BABY_CRYING_DETECTED"
            raw_confidence = float(np.clip(0.72 + 0.28 * max(cry_score, cry_energy * 0.5), 0.75, 0.98))
        # Rule B: Moderate YAMNet Crying in Top 3 with Supporting Infant Vocal Pitch (380 - 680 Hz)
        elif is_cry_in_top3 and (cry_score >= low_thresh or cry_energy >= 0.16) and has_infant_pitch and (cry_energy >= 0.5 * top_sound_score):
            raw_code = "BABY_CRYING_DETECTED"
            raw_confidence = float(np.clip(0.68 + 0.22 * cry_score + 0.10 * periodicity, 0.72, 0.92))
        # Rule C: Ambiguous / Borderline Evidence (crying present but weak or conflicting)
        elif is_cry_in_top3 and (cry_score >= 0.08 or cry_energy >= 0.12):
            raw_code = "UNCERTAIN"
            raw_confidence = round(max(cry_score, cry_energy * 0.5), 2)
        # Rule D: Definite Non-Crying Sound (Adult speech, conversation, music, clapping, doors, alarms, ambient)
        else:
            raw_code = "NOT_BABY_CRYING"
            raw_confidence = round(max(top_sound_score, silence_score, 0.85), 2)

        # 5. Temporal Accumulation & Hysteresis Decision Mechanism
        # Reset history if stream had a significant interruption (> 6.0s)
        if self.last_update_time is not None:
            if (now - self.last_update_time).total_seconds() > 6.0:
                self.window_history.clear()
                self.active_crying_incident = False
                self.consecutive_non_cry_count = 0

        max_history = getattr(settings, "CRY_HISTORY_WINDOW_SIZE", 5)
        attack_req = getattr(settings, "CRY_ATTACK_WINDOWS", 2)
        release_req = getattr(settings, "CRY_RELEASE_WINDOWS", 2)

        self.window_history.append({
            "code": raw_code,
            "cry_score": cry_score,
            "confidence": raw_confidence,
            "time": now
        })
        if len(self.window_history) > max_history:
            self.window_history.pop(0)

        # Apply State Transition with Hysteresis
        if self.active_crying_incident:
            if raw_code == "BABY_CRYING_DETECTED":
                self.consecutive_non_cry_count = 0
                final_code = "BABY_CRYING_DETECTED"
                final_label = "BABY CRYING DETECTED"
                final_confidence = raw_confidence
            else:
                self.consecutive_non_cry_count += 1
                if self.consecutive_non_cry_count < release_req and dominant_negative < 0.40:
                    # Short breathing pause resilience: hold active only if loud competing negative hasn't taken over
                    final_code = "BABY_CRYING_DETECTED"
                    final_label = "BABY CRYING DETECTED"
                    final_confidence = round(max(0.70, (self.last_confidence or 0.85) * 0.90), 2)
                else:
                    # Non-crying verified: incident concluded
                    self.active_crying_incident = False
                    final_code = raw_code
                    final_label = "NOT BABY CRYING" if raw_code == "NOT_BABY_CRYING" else "UNCERTAIN"
                    final_confidence = raw_confidence
        else:
            recent_codes = [w["code"] for w in self.window_history[-3:]]
            recent_crying_count = recent_codes.count("BABY_CRYING_DETECTED")

            has_immediate_cry = (raw_code == "BABY_CRYING_DETECTED") and (
                (is_cry_top1 and cry_score >= 0.22) or (cry_energy >= 0.28) or (has_infant_pitch and cry_score >= 0.14)
            )

            if recent_crying_count >= attack_req or has_immediate_cry:
                # Consistent crying verified across consecutive windows or clear strong crying -> immediate alert
                self.active_crying_incident = True
                self.consecutive_non_cry_count = 0
                final_code = "BABY_CRYING_DETECTED"
                final_label = "BABY CRYING DETECTED"
                final_confidence = raw_confidence
            elif raw_code == "BABY_CRYING_DETECTED":
                # Single borderline spike without temporal corroboration -> UNCERTAIN (prevents false alarms)
                final_code = "UNCERTAIN"
                final_label = "UNCERTAIN"
                final_confidence = raw_confidence
            else:
                final_code = raw_code
                final_label = "NOT BABY CRYING" if raw_code == "NOT_BABY_CRYING" else "UNCERTAIN"
                final_confidence = raw_confidence

        # Update service cache with inference completion timestamp
        completion_time = datetime.now(timezone.utc)
        self.last_update_time = completion_time
        self.last_classification = final_label
        self.last_code = final_code
        self.last_confidence = final_confidence
        self.last_top_classes = top_classes

        logger.info(
            f"[INFERENCE] Completed in {len(signal)/sample_rate:.2f}s audio | "
            f"Result: {final_label} ({final_confidence*100:.0f}%) | "
            f"dB: {sound_level_db} | Top: {top_classes[0]['class_name'] if top_classes else 'N/A'} | "
            f"Active Incident: {self.active_crying_incident}"
        )

        return {
            "classification": final_code,
            "display_label": final_label,
            "confidence": final_confidence,
            "sound_level_db": sound_level_db,
            "rms_amplitude": round(rms * 32768.0, 1),
            "peak_amplitude": peak_amp,
            "top_classes": top_classes,
            "crying_score_raw": round(cry_score, 3),
            "is_baby_crying": (final_code == "BABY_CRYING_DETECTED"),
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
