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

        # Load Pre-trained Baby Crying Dataset Embedding Profiles
        PROFILES_PATH = os.path.join(MODEL_DIR, "crying_dataset_profiles.npz")
        self.dataset_crying_embeddings = None
        self.crying_centroid = None

        if os.path.exists(PROFILES_PATH):
            try:
                npz = np.load(PROFILES_PATH)
                self.dataset_crying_embeddings = npz["pos_embs"]
                self.crying_centroid = npz["centroid"]
                logger.info(f"Loaded {len(self.dataset_crying_embeddings)} baby crying dataset profiles for direct microphone matching.")
            except Exception as e:
                logger.warning(f"Could not load crying dataset profiles: {e}")

        # State tracking for staleness and temporal accumulation
        self.window_history: List[Dict[str, Any]] = []
        self.active_crying_incident: bool = False
        self.last_confirmed_cry_time: Optional[datetime] = None
        self.rolling_noise_floor_db: float = 40.0
        self.last_update_time: Optional[datetime] = None
        self.last_classification: str = "AUDIO UNAVAILABLE"
        self.last_code: str = "AUDIO_UNAVAILABLE"
        self.last_confidence: float = 0.0
        self.last_top_classes: List[Dict[str, Any]] = []

    def reset_temporal_state(self):
        """Resets window accumulation and hysteresis incident trackers."""
        self.window_history.clear()
        self.active_crying_incident = False
        self.last_confirmed_cry_time = None

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

        # Normalize amplitude to [-1.0, 1.0] if clipping
        max_val = float(np.max(np.abs(signal)))
        if max_val > 1.0:
            signal = signal / max_val

        # Standard 0.975s window (15600 samples at 16kHz)
        if len(signal) < 15600:
            pad_len = 15600 - len(signal)
            signal = np.pad(signal, (0, pad_len), mode="constant")
        elif len(signal) > 15600:
            signal = signal[:15600]

        # Standard physical sound metrics (dB SPL & RMS)
        rms = float(np.sqrt(np.mean(signal ** 2)))
        signal_std = float(np.std(signal))
        sound_level_db = round(float(20.0 * np.log10(rms * 32768.0)) if rms > 1e-5 else 0.0, 1)
        peak_amp = int(max_val * 32768) if max_val <= 1.0 else int(max_val)
        crest_factor_db = float(20.0 * np.log10(max_val / rms)) if rms > 1e-6 else 0.0

        # Minimum-energy & zero/constant waveform gate:
        # If signal is silent, zero-energy, or constant DC offset (< 20 dB noise floor),
        # immediately return NOT_BABY_CRYING.
        if rms < 1e-4 or signal_std < 1e-4 or max_val < 1e-4 or sound_level_db < 20.0:
            return {
                'classification': 'NOT_BABY_CRYING',
                'display_label': 'NOT BABY CRYING',
                'code': 'NOT_BABY_CRYING',
                'confidence': 0.0,
                'crying_score': 0.0,
                'dominant_negative_score': 0.0,
                'is_baby_crying': False,
                'sound_level_db': 0.0,
                'rms_amplitude': 0.0,
                'peak_amplitude': 0,
                'top_sound': 'Silence',
                'top_classes': [{'class_name': 'Silence', 'score': 1.0}],
                'decision_rule': 'zero_energy_silence_gate',
                'dataset_similarity': 0.0,
                'dataset_matched': False,
                'dataset_comparison': None,
                'status': 'SILENCE'
            }

        # 1. Window Peak Normalization for YAMNet Neural Inference
        # Brings quiet or distant nursery audio into YAMNet's optimal training distribution (peak ~0.75)
        # Clamped to max_gain = 15.0x so ambient noise floor is never over-amplified
        if max_val > 1e-4:
            gain = min(0.75 / max_val, 15.0)
            inference_signal = np.clip(signal * gain, -1.0, 1.0)
        else:
            inference_signal = signal.copy()

        # 2. Adaptive Noise Floor Tracking (Exponential Moving Average)
        # Tracks true ambient baseline when audio is in calm/moderate room range (20 to 60 dB)
        if 20.0 <= sound_level_db <= 60.0:
            alpha = getattr(settings, "NOISE_FLOOR_ALPHA", 0.05)
            self.rolling_noise_floor_db = (1.0 - alpha) * self.rolling_noise_floor_db + alpha * sound_level_db

        margin_above_floor = sound_level_db - self.rolling_noise_floor_db
        min_gate_margin = getattr(settings, "ADAPTIVE_NOISE_FLOOR_MARGIN_DB", 6.0)
        is_above_noise_floor = (margin_above_floor >= min_gate_margin) or (sound_level_db >= 48.0)

        # 3. YAMNet Neural Inference (0.975s window)
        outputs = self.session.run(None, {self.input_name: inference_signal})
        scores = outputs[0]      # Shape: [num_frames, 521]
        embeddings = outputs[1]  # Shape: [num_frames, 1024]
        mean_scores = np.mean(scores, axis=0)

        # Direct Comparison: Microphone Input Embedding vs Baby Crying Dataset Profiles
        mic_embedding = np.mean(embeddings, axis=0) if len(embeddings.shape) > 1 and embeddings.shape[0] > 0 else embeddings.flatten()
        mic_norm = float(np.linalg.norm(mic_embedding))
        mic_unit = (mic_embedding / mic_norm) if mic_norm > 1e-9 else mic_embedding

        dataset_similarity = 0.0
        max_sample_similarity = 0.0
        best_matching_sample = None

        if self.crying_centroid is not None and mic_norm > 1e-9:
            centroid_norm = float(np.linalg.norm(self.crying_centroid))
            if centroid_norm > 1e-9:
                dataset_similarity = float(np.dot(mic_unit, self.crying_centroid / centroid_norm))
                dataset_similarity = float(np.clip(dataset_similarity, 0.0, 1.0))

        if self.dataset_crying_embeddings is not None and mic_norm > 1e-9:
            sims = []
            for idx, ref in enumerate(self.dataset_crying_embeddings):
                ref_norm = float(np.linalg.norm(ref))
                if ref_norm > 1e-9:
                    sims.append((float(np.dot(mic_unit, ref / ref_norm)), idx))
            if sims:
                best_sim, best_idx = max(sims, key=lambda x: x[0])
                max_sample_similarity = float(np.clip(best_sim, 0.0, 1.0))
                best_matching_sample = f"Dataset Baby Cry #{best_idx + 1}"

        dataset_match_score = round(max(dataset_similarity, max_sample_similarity), 3)
        dataset_matched = (dataset_match_score >= 0.65)

        # 4. Target Crying vs Competing Classes
        # AudioSet Class 20: 'Baby cry, infant cry', Class 19: 'Crying, sobbing', Class 21: 'Whimper'
        infant_cry_score = float(mean_scores[20])
        crying_sobbing_score = float(mean_scores[19])
        whimper_score = float(mean_scores[21])
        cry_score = max(infant_cry_score, crying_sobbing_score, whimper_score * 0.90)

        competing_indices = [
            0, 1, 2, 4, 5, 6, 7,     # Speech, Child speech, Conversation, Male, Female, Shout, Yell
            13, 14, 15,              # Laughter, Baby laughter, Snicker
            58, 62,                  # Clapping, Applause
            132,                     # Music
            494,                     # Silence
            348, 349, 351,           # Knock, Door, Slam
            74                       # Dog bark
        ]
        dominant_negative = float(max(mean_scores[idx] for idx in competing_indices))
        dominant_negative_idx = max(competing_indices, key=lambda idx: mean_scores[idx])
        dominant_negative_name = self.class_names[dominant_negative_idx]

        # 2. Transient / Impulse Veto (Clapping, Door Slams, Knocks)
        impulse_crest_thresh = getattr(settings, "CREST_FACTOR_IMPULSE_THRESHOLD", 15.0)
        is_transient_impulse = (crest_factor_db >= impulse_crest_thresh) and (dominant_negative >= cry_score) and (sound_level_db >= 58.0)

        # Top 5 detected sound classes
        top_indices = np.argsort(mean_scores)[::-1][:5]
        top_classes = [
            {"class_name": self.class_names[idx], "score": round(float(mean_scores[idx]), 3)}
            for idx in top_indices
        ]
        top_sound_name = top_classes[0]["class_name"] if top_classes else "Unknown"
        top_sound_score = top_classes[0]["score"] if top_classes else 0.0

        top_n_req = getattr(settings, "CRY_TOP_N_REQUIRED", 3)
        is_cry_in_top_n = any(idx in [20, 19, 21] for idx in top_indices[:top_n_req])
        is_cry_top1 = (top_indices[0] in [20, 19, 21])

        # 5. Precision-First Calibrated Rule Evaluation (Per-Window)
        conf_thresh = getattr(settings, "CRY_SCORE_CONFIRMED_THRESHOLD", 0.35)
        unc_thresh = getattr(settings, "CRY_SCORE_UNCERTAIN_THRESHOLD", 0.18)
        margin = getattr(settings, "CRY_SCORE_MARGIN", 0.05)

        rule_fired = "ambient_or_negative"
        if not is_above_noise_floor and cry_score < conf_thresh:
            raw_code = "NOT_BABY_CRYING"
            raw_confidence = 0.95
            rule_fired = "noise_floor_gate"
        elif is_transient_impulse:
            raw_code = "NOT_BABY_CRYING"
            raw_confidence = 0.90
            rule_fired = "transient_impulse_veto"
        else:
            # Must satisfy ALL of:
            # (a) cry score >= conf_thresh
            # (b) cry score beats dominant negative by margin
            # (c) cry class in top-N
            # Direct dataset comparison evidence:
            # If microphone embedding matches reference baby crying dataset (>= 65%), it strongly supports crying
            is_dataset_cry_match = dataset_matched and (cry_score >= unc_thresh)

            is_confirmed_cry = (
                (
                    ((cry_score >= conf_thresh) and (cry_score >= dominant_negative + margin))
                    or (is_dataset_cry_match and dominant_negative < 0.60)
                )
                and is_cry_in_top_n
            )

            # Uncertain: borderline evidence or close competing class
            is_uncertain = (
                (cry_score >= unc_thresh) and
                (is_cry_in_top_n or cry_score >= dominant_negative - 0.05) and
                (dominant_negative < 0.65)
            )

            if is_confirmed_cry:
                raw_code = "BABY_CRYING_DETECTED"
                raw_confidence = round(float(np.clip(max(cry_score, dataset_match_score), 0.70, 0.98)), 2)
                rule_fired = "dataset_matched_crying" if is_dataset_cry_match else "yamnet_confirmed_cry"
            elif is_uncertain:
                raw_code = "UNCERTAIN"
                raw_confidence = round(float(np.clip(cry_score, 0.50, 0.75)), 2)
                rule_fired = "yamnet_uncertain_band"
            else:
                raw_code = "NOT_BABY_CRYING"
                raw_confidence = round(float(np.clip(max(dominant_negative, 0.85), 0.70, 0.98)), 2)
                rule_fired = "yamnet_dominant_negative"

        # 6. Multi-Window Temporal Voting & Hysteresis
        staleness_limit = getattr(settings, "AUDIO_STALENESS_SECONDS", 8.0)
        if self.last_update_time is not None:
            if (now - self.last_update_time).total_seconds() > staleness_limit:
                self.window_history.clear()
                self.active_crying_incident = False
                self.last_confirmed_cry_time = None

        total_votes = getattr(settings, "CRY_WINDOW_VOTES_TOTAL", 4)
        req_votes = getattr(settings, "CRY_WINDOW_VOTES_REQUIRED", 3)
        pause_bridge_limit = getattr(settings, "CRY_PAUSE_BRIDGE_SECONDS", 4.0)

        self.window_history.append({
            "code": raw_code,
            "cry_score": cry_score,
            "time": now
        })
        if len(self.window_history) > total_votes:
            self.window_history.pop(0)

        cry_votes = sum(1 for w in self.window_history if w["code"] == "BABY_CRYING_DETECTED")
        immediate_cry = (raw_code == "BABY_CRYING_DETECTED") and (is_cry_top1 or is_cry_in_top_n) and (cry_score >= 0.28)

        if self.active_crying_incident:
            if raw_code == "BABY_CRYING_DETECTED":
                self.last_confirmed_cry_time = now
                final_code = "BABY_CRYING_DETECTED"
                final_confidence = raw_confidence
                decision_rule = "active_incident_maintained"
            else:
                time_since_cry = (now - self.last_confirmed_cry_time).total_seconds() if self.last_confirmed_cry_time else 999.0
                # Breath pause bridge: only extend within 4.0s IF YAMNet still shows residual cry evidence, NEVER on loudness alone!
                if time_since_cry <= pause_bridge_limit and (raw_code == "UNCERTAIN" or cry_score >= 0.12) and (dominant_negative < 0.40):
                    final_code = "BABY_CRYING_DETECTED"
                    final_confidence = round(max(0.70, (self.last_confidence or 0.85) * 0.92), 2)
                    decision_rule = f"breath_pause_bridge_{time_since_cry:.1f}s"
                else:
                    self.active_crying_incident = False
                    final_code = raw_code
                    final_confidence = raw_confidence
                    decision_rule = "incident_released"
        else:
            if immediate_cry:
                self.active_crying_incident = True
                self.last_confirmed_cry_time = now
                final_code = "BABY_CRYING_DETECTED"
                final_confidence = raw_confidence
                decision_rule = "immediate_cry_confirmed"
            elif cry_votes >= req_votes:
                self.active_crying_incident = True
                self.last_confirmed_cry_time = now
                final_code = "BABY_CRYING_DETECTED"
                final_confidence = raw_confidence
                decision_rule = "multi_window_confirmed"
            elif raw_code == "BABY_CRYING_DETECTED":
                # Single weak cry score (< 0.28) -> UNCERTAIN until confirmed by additional window
                final_code = "UNCERTAIN"
                final_confidence = raw_confidence
                decision_rule = "single_weak_spike_dampened_to_uncertain"
            else:
                final_code = raw_code
                final_confidence = raw_confidence
                decision_rule = rule_fired

        if final_code == "BABY_CRYING_DETECTED":
            final_label = "BABY CRYING DETECTED"
        elif final_code == "UNCERTAIN":
            final_label = "UNCERTAIN"
        else:
            final_label = "NOT BABY CRYING"

        # Update cache
        completion_time = datetime.now(timezone.utc)
        self.last_update_time = completion_time
        self.last_classification = final_label
        self.last_code = final_code
        self.last_confidence = final_confidence
        self.last_top_classes = top_classes

        self.last_dataset_similarity = dataset_match_score
        self.last_dataset_matched = dataset_matched
        logger.info(
            f"[INFERENCE] Audio: {len(signal)/sample_rate:.2f}s | "
            f"Result: {final_label} ({final_confidence*100:.0f}%) | "
            f"DatasetMatch: {dataset_match_score*100:.1f}% ({best_matching_sample or 'None'}) | "
            f"CryScore: {cry_score:.3f} | DomNeg: {dominant_negative:.3f} ({dominant_negative_name}) | "
            f"Rule: {decision_rule} | ActiveIncident: {self.active_crying_incident}"
        )

        return {
            "classification": final_code,
            "display_label": final_label,
            "confidence": final_confidence,
            "crying_score": round(cry_score, 3),
            "dominant_negative_score": round(dominant_negative, 3),
            "dominant_negative_class": dominant_negative_name,
            "dataset_similarity": dataset_match_score,
            "dataset_matched": dataset_matched,
            "dataset_comparison": {
                "dataset_match_score": dataset_match_score,
                "centroid_similarity": round(dataset_similarity, 3),
                "max_sample_similarity": round(max_sample_similarity, 3),
                "best_matching_sample": best_matching_sample,
                "dataset_matched": dataset_matched,
                "reference_dataset": "ESC-50 Infant Cry Benchmark"
            },
            "sound_level_db": sound_level_db,
            "rms_amplitude": round(rms * 32768.0, 1),
            "peak_amplitude": peak_amp,
            "top_classes": top_classes,
            "crying_score_raw": round(cry_score, 3),
            "is_baby_crying": (final_code == "BABY_CRYING_DETECTED"),
            "decision_rule": decision_rule,
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

                    if sample_rate != 16000 and sample_rate > 0:
                        target_len = int(len(signal) * 16000 / sample_rate)
                        signal = np.interp(
                            np.linspace(0, len(signal), target_len, endpoint=False),
                            np.arange(len(signal)),
                            signal
                        ).astype(np.float32)
                        sample_rate = 16000

                    if len(signal) >= 15600:
                        chunk_size = 15600
                        last_res = None
                        best_cry_res = None
                        for start_idx in range(0, max(1, len(signal) - 8000), 8000):
                            chunk = signal[start_idx : start_idx + chunk_size]
                            if len(chunk) < chunk_size:
                                chunk = np.pad(chunk, (0, chunk_size - len(chunk)))
                            last_res = self.classify_waveform(chunk, sample_rate=16000)
                            if last_res.get("classification") == "BABY_CRYING_DETECTED":
                                best_cry_res = last_res
                                break
                        return best_cry_res or last_res or self.classify_waveform(signal, sample_rate=16000)

                    return self.classify_waveform(signal, sample_rate=sample_rate)
            except Exception:
                pass

        # Raw 16-bit PCM fallback (standard ESP32 stream format)
        try:
            signal = np.frombuffer(wav_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            if len(signal) >= 15600:
                chunk_size = 15600
                last_res = None
                best_cry_res = None
                for start_idx in range(0, max(1, len(signal) - 8000), 8000):
                    chunk = signal[start_idx : start_idx + chunk_size]
                    if len(chunk) < chunk_size:
                        chunk = np.pad(chunk, (0, chunk_size - len(chunk)))
                    last_res = self.classify_waveform(chunk, sample_rate=16000)
                    if last_res.get("classification") == "BABY_CRYING_DETECTED":
                        best_cry_res = last_res
                        break
                return best_cry_res or last_res or self.classify_waveform(signal, sample_rate=16000)
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
            "dataset_similarity": getattr(self, "last_dataset_similarity", 0.0),
            "dataset_matched": getattr(self, "last_dataset_matched", False),
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
            "dataset_similarity": 0.0,
            "dataset_matched": False,
            "dataset_comparison": None,
            "status": "UNAVAILABLE",
            "is_fresh": False,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "top_classes": []
        }
