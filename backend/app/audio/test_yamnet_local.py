"""
Phase 3 Local Model Verification Script
Tests Google's YAMNet ONNX model locally on Windows against multiple sound types:
1. Ambient Silence / Low Noise
2. Door Slam / Broadband Impact
3. Adult Speech Simulation (130 Hz fundamental)
4. Infant Crying Simulation (480 Hz fundamental with harmonic vibrato)
5. Uncertain / Ambiguous Low-Volume Signal
"""

import os
import csv
import numpy as np
import onnxruntime as ort

MODEL_PATH = os.path.join(os.path.dirname(__file__), "models", "yamnet.onnx")
CLASS_MAP_PATH = os.path.join(os.path.dirname(__file__), "models", "yamnet_class_map.csv")

def load_class_names():
    class_names = []
    with open(CLASS_MAP_PATH, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader)  # Header: index,mid,display_name
        for row in reader:
            class_names.append(row[2])
    return class_names

def run_inference(classifier, waveform: np.ndarray, sample_rate: int = 16000):
    res = classifier.classify_waveform(waveform, sample_rate)
    return {
        "classification": res.get("display_label", res.get("classification")),
        "cry_code": res.get("classification"),
        "confidence": res.get("confidence", 0.0),
        "sound_level_db": res.get("sound_level_db", 0.0),
        "top_predictions": [(c["class_name"], c["score"]) for c in res.get("top_classes", [])]
    }

def main():
    import sys
    sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))
    from app.audio.yamnet_classifier import YamnetClassifier

    print("=" * 60)
    print("PHASE 3: LOCAL YAMNET ONNX & ACOUSTIC EVALUATION")
    print("=" * 60)
    classifier = YamnetClassifier.get_instance()
    print("Loaded YamnetClassifier pipeline.\n")

    sample_rate = 16000
    duration = 1.0  # 1 second test clips
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)

    test_cases = []

    # 1. Ambient Silence / Background Noise
    noise = np.random.normal(0, 0.01, len(t)).astype(np.float32)
    test_cases.append(("Quiet Ambient Background", noise))

    # 2. Door Slam / Abrupt Impact (decaying exponential burst)
    impulse = np.exp(-t * 25.0) * np.sin(2 * np.pi * 90 * t) + np.random.normal(0, 0.05, len(t))
    test_cases.append(("Door Slam / Loud Impulse", impulse.astype(np.float32)))

    # 3. Adult Speech (130 Hz fundamental + harmonics)
    speech = (
        np.sin(2 * np.pi * 130 * t) +
        0.5 * np.sin(2 * np.pi * 260 * t) +
        0.3 * np.sin(2 * np.pi * 390 * t)
    ) * np.hanning(len(t))
    test_cases.append(("Adult Speech Simulation", speech.astype(np.float32)))

    # 4. Baby Crying Simulation (480 Hz fundamental + pitch wobble + formants)
    f0 = 480 + 35 * np.sin(2 * np.pi * 4.5 * t)  # 480 Hz with 4.5 Hz vocal vibrato
    phase = 2 * np.pi * np.cumsum(f0) / sample_rate
    cry = (
        0.6 * np.sin(phase) +
        0.5 * np.sin(2 * phase) +
        0.35 * np.sin(3 * phase) +
        0.2 * np.sin(4 * phase)
    )
    envelope = (np.sin(2 * np.pi * 1.5 * t) ** 2)
    cry = cry * envelope
    test_cases.append(("Infant Cry Acoustic Simulation", cry.astype(np.float32)))

    print("Evaluating test sounds through pipeline:\n")
    for name, signal in test_cases:
        res = run_inference(classifier, signal, sample_rate)
        print(f"[*] Test Sound: {name}")
        print(f"    -> Classification: {res['classification']} (Code: {res['cry_code']})")
        print(f"    -> Confidence: {res['confidence'] * 100:.1f}% | dB: {res['sound_level_db']}")
        print(f"    -> Top 3 Predictions: {', '.join([f'{c} ({s*100:.1f}%)' for c, s in res['top_predictions'][:3]])}")
        print("-" * 60)

    print("\nPhase 3 Model Verification Complete!")

if __name__ == "__main__":
    main()
