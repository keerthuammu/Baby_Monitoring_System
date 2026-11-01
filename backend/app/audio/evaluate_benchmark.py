"""
Benchmark Evaluation Script
Tests the audio classifier against real labeled audio recordings:
- True Positives (TP): Real baby cry correctly classified as BABY_CRYING_DETECTED
- False Positives (FP): Speech/Household/Ambient incorrectly classified as BABY_CRYING_DETECTED
- True Negatives (TN): Speech/Household/Ambient correctly classified as NOT_BABY_CRYING or UNCERTAIN
- False Negatives (FN): Real baby cry missed (classified as NOT_BABY_CRYING or UNCERTAIN)
"""

import os
import glob
import wave
import numpy as np
from typing import List, Dict, Any, Tuple
import sys

# Ensure backend is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from app.audio.yamnet_classifier import YamnetClassifier

DATASET_DIR = os.path.join(os.path.dirname(__file__), "benchmark_dataset")

def load_wav_as_16k_mono(filepath: str) -> np.ndarray:
    """Loads any WAV file and resamples to 16kHz float32 mono [-1.0, 1.0]."""
    with wave.open(filepath, "rb") as wf:
        sr = wf.getframerate()
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)

    if sampwidth == 2:
        signal = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif sampwidth == 4:
        signal = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        signal = np.frombuffer(raw, dtype=np.int8).astype(np.float32) / 128.0

    if n_channels > 1:
        signal = signal.reshape(-1, n_channels).mean(axis=1)

    if sr != 16000 and sr > 0:
        target_len = int(len(signal) * 16000 / sr)
        signal = np.interp(
            np.linspace(0, len(signal), target_len, endpoint=False),
            np.arange(len(signal)),
            signal
        ).astype(np.float32)

    return signal

def segment_into_windows(signal: np.ndarray, window_size: int = 16000, hop_size: int = 16000) -> List[np.ndarray]:
    """Slices audio into 1.0 second windows."""
    if len(signal) < window_size:
        return [np.pad(signal, (0, window_size - len(signal)), mode="constant")]
    
    windows = []
    for i in range(0, len(signal) - window_size + 1, hop_size):
        windows.append(signal[i:i + window_size])
    return windows

def evaluate_pipeline(classifier, verbose: bool = False):
    positive_files = glob.glob(os.path.join(DATASET_DIR, "positive_crying", "*.wav"))
    neg_speech_files = glob.glob(os.path.join(DATASET_DIR, "negative_speech", "*.wav"))
    neg_household_files = glob.glob(os.path.join(DATASET_DIR, "negative_household", "*.wav"))
    neg_ambient_files = glob.glob(os.path.join(DATASET_DIR, "negative_ambient", "*.wav"))

    y_true = []  # 1 for Crying, 0 for Non-Crying
    y_pred = []  # 1 for BABY_CRYING_DETECTED, 0 for NOT_BABY_CRYING / UNCERTAIN
    results_detail = []

    # 1. Evaluate Positives
    for p in positive_files:
        sig = load_wav_as_16k_mono(p)
        windows = segment_into_windows(sig, 16000, 16000)
        # Reset temporal state between independent test files
        classifier.reset_temporal_state()
            
        for idx, w in enumerate(windows):
            res = classifier.classify_waveform(w, 16000)
            pred = 1 if res["classification"] == "BABY_CRYING_DETECTED" else 0
            y_true.append(1)
            y_pred.append(pred)
            results_detail.append({
                "file": os.path.basename(p),
                "window": idx,
                "true_label": "CRYING",
                "pred_label": res["display_label"],
                "confidence": res["confidence"],
                "top": res.get("top_classes", [{}])[0].get("class_name", "")
            })

    # 2. Evaluate Negatives (Speech, Household, Ambient)
    negative_groups = [
        ("SPEECH", neg_speech_files),
        ("HOUSEHOLD", neg_household_files),
        ("AMBIENT", neg_ambient_files)
    ]

    for category, files in negative_groups:
        for f in files:
            sig = load_wav_as_16k_mono(f)
            windows = segment_into_windows(sig, 16000, 16000)
            classifier.reset_temporal_state()
                
            for idx, w in enumerate(windows):
                res = classifier.classify_waveform(w, 16000)
                pred = 1 if res["classification"] == "BABY_CRYING_DETECTED" else 0
                y_true.append(0)
                y_pred.append(pred)
                results_detail.append({
                    "file": os.path.basename(f),
                    "category": category,
                    "window": idx,
                    "true_label": "NOT_CRYING",
                    "pred_label": res["display_label"],
                    "confidence": res["confidence"],
                    "top": res.get("top_classes", [{}])[0].get("class_name", "")
                })

    # Compute metrics
    tp = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 1 and yp == 1)
    fn = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 1 and yp == 0)
    tn = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 0 and yp == 0)
    fp = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 0 and yp == 1)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    accuracy = (tp + tn) / len(y_true) if y_true else 0.0

    print("=" * 65)
    print("BENCHMARK EVALUATION RESULTS")
    print("=" * 65)
    print(f"Total Evaluated 1-sec Audio Windows: {len(y_true)}")
    print(f"True Positive (TP) : {tp:<4} | False Positive (FP): {fp:<4}")
    print(f"False Negative (FN): {fn:<4} | True Negative (TN) : {tn:<4}")
    print("-" * 65)
    print(f"Accuracy : {accuracy * 100:.2f}%")
    print(f"Precision: {precision * 100:.2f}%")
    print(f"Recall   : {recall * 100:.2f}%")
    print(f"F1 Score : {f1:.4f}")
    print("=" * 65)

    if fp > 0:
        print("\n[!] Breakdown of FALSE POSITIVES (Non-crying misclassified as crying):")
        for r in results_detail:
            if r["true_label"] == "NOT_CRYING" and r["pred_label"] == "BABY CRYING DETECTED":
                print(f"  - File: {r['file']} (Win {r['window']}) -> Top YAMNet: {r['top']} | Conf: {r['confidence']*100:.0f}%")

    if fn > 0:
        print("\n[!] Breakdown of FALSE NEGATIVES (Real baby cries missed):")
        for r in results_detail:
            if r["true_label"] == "CRYING" and r["pred_label"] != "BABY CRYING DETECTED":
                print(f"  - File: {r['file']} (Win {r['window']}) -> Classified as: {r['pred_label']} | Top: {r['top']}")

    return {
        "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "precision": precision, "recall": recall, "f1": f1, "accuracy": accuracy,
        "details": results_detail
    }

if __name__ == "__main__":
    classifier = YamnetClassifier.get_instance()
    evaluate_pipeline(classifier)
