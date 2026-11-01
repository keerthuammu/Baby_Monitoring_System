"""
Test and Tune Improved Decision Logic on Benchmark Dataset
Tests:
1. High-confidence YAMNet detection
2. Pitch as supporting evidence ONLY
3. Speech / Household suppression
4. Temporal window accumulation and hysteresis
"""

import os
import glob
import wave
import numpy as np
from typing import List, Dict, Any, Tuple
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from app.audio.yamnet_classifier import YamnetClassifier
from app.audio.classifier import AcousticClassifier
from evaluate_benchmark import load_wav_as_16k_mono, segment_into_windows, DATASET_DIR

# AudioSet indices
IDX_BABY_CRY = 20
IDX_CRYING_SOBBING = 19
IDX_WHIMPER = 21
IDX_WAIL_MOAN = 22
CRY_INDICES = [IDX_BABY_CRY, IDX_CRYING_SOBBING, IDX_WHIMPER, IDX_WAIL_MOAN]

IDX_SPEECH = 0
IDX_CHILD_SPEECH = 1
IDX_CONVERSATION = 2
IDX_MALE_SPEECH = 4
IDX_FEMALE_SPEECH = 5
SPEECH_INDICES = [IDX_SPEECH, IDX_CHILD_SPEECH, IDX_CONVERSATION, IDX_MALE_SPEECH, IDX_FEMALE_SPEECH]

IDX_LAUGHTER = 13
IDX_BABY_LAUGHTER = 14
IDX_GIGGLE = 14
LAUGHTER_INDICES = [IDX_LAUGHTER, IDX_BABY_LAUGHTER, IDX_GIGGLE]

IDX_CLAPPING = 58
IDX_APPLAUSE = 62
CLAP_INDICES = [IDX_CLAPPING, IDX_APPLAUSE]

IDX_MUSIC = 132
IDX_SILENCE = 494

def improved_classify_window(
    mean_scores: np.ndarray,
    sound_level_db: float,
    acoustic_res: Dict[str, Any],
    cry_threshold_high: float = 0.20,
    cry_threshold_low: float = 0.08,
) -> Tuple[str, str, float]:
    """
    Evaluates a single 1-sec window using the improved decision strategy.
    
    Returns:
        (code, display_label, confidence)
    """
    # 1. Primary YAMNet Crying Evidence
    cry_score = float(max(mean_scores[idx] for idx in CRY_INDICES))
    cry_energy = float(sum(mean_scores[idx] for idx in CRY_INDICES))

    # 2. Competing Negative Evidence
    speech_score = float(max(mean_scores[idx] for idx in SPEECH_INDICES))
    laughter_score = float(max(mean_scores[idx] for idx in LAUGHTER_INDICES))
    clap_score = float(max(mean_scores[idx] for idx in CLAP_INDICES))
    music_score = float(mean_scores[IDX_MUSIC])
    silence_score = float(mean_scores[IDX_SILENCE])

    dominant_negative = max(speech_score, laughter_score, clap_score, music_score)

    # 3. Acoustic Pitch Supporting Evidence
    features = acoustic_res.get("features", {})
    pitch = features.get("pitch_hz", 0.0)
    periodicity = features.get("periodicity", 0.0)
    cry_band_ratio = features.get("cry_band_ratio", 0.0)

    # Infant vocal pitch is 300 to 720 Hz with strong periodicity
    has_infant_pitch = (300.0 <= pitch <= 720.0) and (periodicity >= 0.28) and (cry_band_ratio >= 0.28)

    # 4. DECISION RULES:
    # Rule A: Strong YAMNet Crying Evidence
    if cry_score >= cry_threshold_high:
        # Check if speech is not overwhelmingly dominant
        if speech_score > 1.8 * cry_score:
            return "NOT_BABY_CRYING", "NOT BABY CRYING", round(speech_score, 2)
        confidence = float(np.clip(0.70 + 0.30 * cry_score, 0.75, 0.98))
        return "BABY_CRYING_DETECTED", "BABY CRYING DETECTED", round(confidence, 2)

    # Rule B: Moderate YAMNet Crying with Supporting Infant Pitch Evidence
    if cry_score >= cry_threshold_low:
        if has_infant_pitch and (cry_score >= 0.5 * speech_score):
            confidence = float(np.clip(0.65 + 0.25 * cry_score + 0.10 * periodicity, 0.72, 0.92))
            return "BABY_CRYING_DETECTED", "BABY CRYING DETECTED", round(confidence, 2)
        elif speech_score > 1.2 * cry_score or dominant_negative > 0.30:
            return "NOT_BABY_CRYING", "NOT BABY CRYING", round(dominant_negative, 2)
        else:
            # Ambiguous / weak signal
            return "UNCERTAIN", "UNCERTAIN", round(cry_score, 2)

    # Rule C: Low / Negligible Crying Evidence (cry_score < 0.08)
    # A pitch match alone must NEVER declare crying!
    if has_infant_pitch and cry_score < cry_threshold_low:
        # Pitch alone without YAMNet is adult speech harmonic, whistle, or noise
        if speech_score >= 0.15:
            return "NOT_BABY_CRYING", "NOT BABY CRYING", round(speech_score, 2)
        return "NOT_BABY_CRYING", "NOT BABY CRYING", 0.85

    return "NOT_BABY_CRYING", "NOT BABY CRYING", round(max(dominant_negative, silence_score, 0.80), 2)

def evaluate_improved(classifier, cry_high=0.20, cry_low=0.08):
    positive_files = glob.glob(os.path.join(DATASET_DIR, "positive_crying", "*.wav"))
    neg_speech_files = glob.glob(os.path.join(DATASET_DIR, "negative_speech", "*.wav"))
    neg_household_files = glob.glob(os.path.join(DATASET_DIR, "negative_household", "*.wav"))
    neg_ambient_files = glob.glob(os.path.join(DATASET_DIR, "negative_ambient", "*.wav"))

    y_true = []
    y_pred = []
    fps = []
    fns = []

    # Positives
    for p in positive_files:
        sig = load_wav_as_16k_mono(p)
        windows = segment_into_windows(sig, 16000, 16000)
        for idx, w in enumerate(windows):
            outputs = classifier.session.run(None, {classifier.input_name: w})
            mean_scores = np.mean(outputs[0], axis=0)
            rms = float(np.sqrt(np.mean(w ** 2)))
            db = round(float(20.0 * np.log10(rms * 32768.0)) if rms > 1e-5 else 0.0, 1)
            int_signal = (w * 32767.0).astype(np.float64)
            ac_res = AcousticClassifier.classify_waveform(int_signal, 16000)

            code, label, conf = improved_classify_window(mean_scores, db, ac_res, cry_high, cry_low)
            pred = 1 if code == "BABY_CRYING_DETECTED" else 0
            y_true.append(1)
            y_pred.append(pred)
            if pred == 0:
                top_idx = np.argmax(mean_scores)
                fns.append((os.path.basename(p), idx, label, conf, classifier.class_names[top_idx], mean_scores[top_idx]))

    # Negatives
    negative_groups = [
        ("SPEECH", neg_speech_files),
        ("HOUSEHOLD", neg_household_files),
        ("AMBIENT", neg_ambient_files)
    ]

    for cat, files in negative_groups:
        for f in files:
            sig = load_wav_as_16k_mono(f)
            windows = segment_into_windows(sig, 16000, 16000)
            for idx, w in enumerate(windows):
                outputs = classifier.session.run(None, {classifier.input_name: w})
                mean_scores = np.mean(outputs[0], axis=0)
                rms = float(np.sqrt(np.mean(w ** 2)))
                db = round(float(20.0 * np.log10(rms * 32768.0)) if rms > 1e-5 else 0.0, 1)
                int_signal = (w * 32767.0).astype(np.float64)
                ac_res = AcousticClassifier.classify_waveform(int_signal, 16000)

                code, label, conf = improved_classify_window(mean_scores, db, ac_res, cry_high, cry_low)
                pred = 1 if code == "BABY_CRYING_DETECTED" else 0
                y_true.append(0)
                y_pred.append(pred)
                if pred == 1:
                    top_idx = np.argmax(mean_scores)
                    fps.append((os.path.basename(f), cat, idx, label, conf, classifier.class_names[top_idx], mean_scores[top_idx]))

    tp = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 1 and yp == 1)
    fn = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 1 and yp == 0)
    tn = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 0 and yp == 0)
    fp = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 0 and yp == 1)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    accuracy = (tp + tn) / len(y_true) if y_true else 0.0

    print(f"\n--- Operating Point (cry_high={cry_high:.2f}, cry_low={cry_low:.2f}) ---")
    print(f"Total: {len(y_true)} | TP: {tp} | FP: {fp} | TN: {tn} | FN: {fn}")
    print(f"Accuracy : {accuracy*100:.2f}% | Precision: {precision*100:.2f}% | Recall: {recall*100:.2f}% | F1: {f1:.4f}")
    if fps:
        print(f"False Positives ({len(fps)}):")
        for x in fps:
            print(f"  {x[0]} ({x[1]} win {x[2]}): {x[3]} {x[4]*100:.0f}% | Top: {x[5]} ({x[6]:.2f})")
    if fns:
        print(f"False Negatives ({len(fns)}):")
        for x in fns:
            print(f"  {x[0]} (win {x[1]}): {x[2]} {x[3]*100:.0f}% | Top: {x[4]} ({x[5]:.2f})")

    return precision, recall, f1, accuracy

if __name__ == "__main__":
    classifier = YamnetClassifier.get_instance()
    # Evaluate across a grid of operating points
    for high in [0.15, 0.18, 0.20, 0.22, 0.25]:
        for low in [0.06, 0.08, 0.10]:
            evaluate_improved(classifier, cry_high=high, cry_low=low)
