"""
Acoustic Crying Classifier Engine
----------------------------------
Distinguishes:
1. QUIET: Low ambient sound level.
2. HIGH_SOUND_ACTIVITY: Elevated acoustic energy that is NOT baby crying
   (e.g., slamming doors, television, talking adults, traffic horns).
3. POSSIBLE_CRYING: Acoustic patterns matching infant crying features
   (Fundamental pitch F0 between 350 - 650 Hz, high spectral energy in 400-2500 Hz,
   and elevated sound level >= 55 dB).
4. UNCERTAIN: Borderline or low-confidence acoustic signals.

Note: This is an assistive acoustic classifier, not a medical diagnostic tool.
"""

import numpy as np
from typing import Dict, Any, Tuple
from app.audio.features import extract_features

class AcousticClassifier:
    """
    Rule-based & acoustic-feature heuristic classifier with confidence estimation.
    Designed for real-time edge/backend inference without heavy GPU dependencies.
    """

    # Empirical infant cry acoustic parameters:
    CRY_PITCH_MIN_HZ = 350.0
    CRY_PITCH_MAX_HZ = 680.0
    CRY_BAND_ENERGY_MIN = 0.40
    CRY_DECIBEL_MIN = 55.0

    @classmethod
    def classify_waveform(cls, signal: np.ndarray, sample_rate: int = 16000) -> Dict[str, Any]:
        """Classifies raw audio samples and returns classification details."""
        features = extract_features(signal, sample_rate)
        classification, confidence = cls.classify_features(features)

        return {
            "classification": classification,
            "confidence": confidence,
            "features": features
        }

    @classmethod
    def classify_features(cls, features: Dict[str, Any]) -> Tuple[str, float]:
        """
        Classifies extracted acoustic features.
        
        Returns:
            (classification_label, confidence_score)
        """
        db = features.get("sound_level_db", 0.0)
        pitch = features.get("pitch_hz", 0.0)
        periodicity = features.get("periodicity", 0.0)
        cry_band_ratio = features.get("cry_band_ratio", 0.0)

        # 1. Quiet Condition
        if db < 45.0:
            confidence = max(0.60, min(0.99, (45.0 - db) / 45.0 + 0.60))
            return "QUIET", round(confidence, 2)

        # 2. Check for Infant Cry Characteristics
        # Infant cries have:
        # a) Fundamental pitch (F0) typically in 350 - 680 Hz range
        # b) Sustained periodicity (voiced vocalization)
        # c) Majority of acoustic energy in the 350 Hz - 2500 Hz band
        # d) Elevated sound level >= 55 dB
        is_pitch_match = (cls.CRY_PITCH_MIN_HZ <= pitch <= cls.CRY_PITCH_MAX_HZ)
        is_periodic = (periodicity >= 0.30)
        is_spectral_match = (cry_band_ratio >= cls.CRY_BAND_ENERGY_MIN)
        is_elevated_db = (db >= cls.CRY_DECIBEL_MIN)

        if is_pitch_match and is_periodic and is_spectral_match and is_elevated_db:
            # High alignment with infant cry acoustic profile
            # Confidence weighted by pitch centrality (optimal center ~480 Hz) and band energy
            pitch_score = 1.0 - abs(pitch - 480.0) / 250.0
            spectral_score = cry_band_ratio
            confidence = float(np.clip(0.55 + 0.25 * pitch_score + 0.20 * spectral_score, 0.65, 0.95))
            return "POSSIBLE_CRYING", round(confidence, 2)

        # 3. High Sound Activity (Elevated noise, but NOT matching cry pitch/spectrum)
        if db >= 65.0:
            # It is loud, but pitch is adult speech, bass rumble, or abrupt broadband noise
            confidence = 0.85
            return "HIGH_SOUND_ACTIVITY", round(confidence, 2)

        # 4. Moderate sound or uncertain classification
        if db >= 45.0:
            if is_pitch_match and is_periodic:
                # Borderline pitch match at lower volume
                return "UNCERTAIN", 0.50
            return "HIGH_SOUND_ACTIVITY", 0.60

        return "UNCERTAIN", 0.40
