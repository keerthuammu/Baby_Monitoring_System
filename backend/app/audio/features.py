"""
Audio Feature Extraction Module for Acoustic Monitoring
-------------------------------------------------------
Calculates acoustic features including:
- Root-Mean-Square (RMS) amplitude
- Zero-Crossing Rate (ZCR)
- Fundamental Frequency (F0 / Pitch) via Autocorrelation
- Spectral Energy Distribution in Infant Cry Band (350 Hz - 2500 Hz)
- Spectral Centroid
"""

import numpy as np
from typing import Tuple, Dict, Any

def compute_rms(signal: np.ndarray) -> float:
    """Computes Root-Mean-Square amplitude."""
    if len(signal) == 0:
        return 0.0
    return float(np.sqrt(np.mean(signal.astype(float) ** 2)))

def compute_zcr(signal: np.ndarray) -> float:
    """Computes Zero-Crossing Rate."""
    if len(signal) < 2:
        return 0.0
    zero_crossings = np.nonzero(np.diff(signal > 0))[0]
    return float(len(zero_crossings) / (len(signal) - 1))

def estimate_pitch_autocorr(signal: np.ndarray, sample_rate: int = 16000) -> Tuple[float, float]:
    """
    Estimates fundamental frequency (F0) using normalized autocorrelation.
    Infant cries typically have fundamental pitch F0 in the 350 Hz to 650 Hz range
    (much higher than typical adult speech: 85-255 Hz).
    
    Returns:
        (pitch_hz, periodicity_strength)
    """
    if len(signal) < 256:
        return 0.0, 0.0

    # Subtract mean
    sig = signal.astype(float) - np.mean(signal)
    
    # Lag bounds for human pitch (80 Hz to 900 Hz)
    min_lag = int(sample_rate / 900)  # ~17 samples at 16kHz
    max_lag = int(sample_rate / 80)   # ~200 samples at 16kHz
    
    if max_lag >= len(sig):
        max_lag = len(sig) - 1

    # Autocorrelation
    corr = np.correlate(sig, sig, mode='full')
    corr = corr[len(sig)-1:] # Keep non-negative lags
    
    if corr[0] == 0:
        return 0.0, 0.0
        
    norm_corr = corr / corr[0]
    
    # Search within human pitch lag window
    search_window = norm_corr[min_lag:max_lag]
    if len(search_window) == 0:
        return 0.0, 0.0
        
    peak_idx = np.argmax(search_window)
    peak_val = search_window[peak_idx]
    
    lag = min_lag + peak_idx
    if lag == 0:
        return 0.0, 0.0
        
    pitch_hz = sample_rate / lag
    periodicity = float(np.clip(peak_val, 0.0, 1.0))
    
    return float(pitch_hz), periodicity

def compute_spectral_features(signal: np.ndarray, sample_rate: int = 16000) -> Dict[str, float]:
    """
    Computes spectral energy distribution and centroid via FFT.
    Infant crying concentrates high acoustic energy between 350 Hz and 2500 Hz.
    """
    if len(signal) < 128:
        return {"cry_band_ratio": 0.0, "spectral_centroid": 0.0}

    # Windowing
    windowed = signal * np.hanning(len(signal))
    fft_vals = np.abs(np.fft.rfft(windowed))
    freqs = np.fft.rfftfreq(len(signal), d=1.0/sample_rate)

    total_energy = np.sum(fft_vals ** 2)
    if total_energy == 0:
        return {"cry_band_ratio": 0.0, "spectral_centroid": 0.0}

    # Infant cry primary energy band: 350 Hz - 2500 Hz
    cry_band_mask = (freqs >= 350) & (freqs <= 2500)
    cry_band_energy = np.sum(fft_vals[cry_band_mask] ** 2)
    cry_band_ratio = float(cry_band_energy / total_energy)

    # Spectral centroid (brightness of sound)
    centroid = float(np.sum(freqs * fft_vals) / (np.sum(fft_vals) + 1e-9))

    return {
        "cry_band_ratio": cry_band_ratio,
        "spectral_centroid": centroid
    }

def extract_features(signal: np.ndarray, sample_rate: int = 16000) -> Dict[str, Any]:
    """Extracts a complete acoustic feature vector from an audio slice."""
    rms = compute_rms(signal)
    sound_level = 20.0 * np.log10(rms) if rms > 1.0 else 0.0
    zcr = compute_zcr(signal)
    pitch_hz, periodicity = estimate_pitch_autocorr(signal, sample_rate)
    spectral = compute_spectral_features(signal, sample_rate)

    return {
        "rms": rms,
        "sound_level_db": round(float(sound_level), 2),
        "peak_amplitude": int(np.max(np.abs(signal))) if len(signal) > 0 else 0,
        "zcr": round(zcr, 4),
        "pitch_hz": round(pitch_hz, 1),
        "periodicity": round(periodicity, 3),
        "cry_band_ratio": round(spectral["cry_band_ratio"], 3),
        "spectral_centroid": round(spectral["spectral_centroid"], 1)
    }
