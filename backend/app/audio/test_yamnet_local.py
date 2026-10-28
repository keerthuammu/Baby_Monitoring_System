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

def run_inference(session, class_names, waveform: np.ndarray, sample_rate: int = 16000):
    # Ensure float32 1D array normalized [-1.0, 1.0]
    wav = waveform.astype(np.float32)
    if np.max(np.abs(wav)) > 1.0:
        wav = wav / np.max(np.abs(wav))

    input_name = session.get_inputs()[0].name
    outputs = session.run(None, {input_name: wav})
    scores = outputs[0]  # Shape: [num_frames, 521]

    # Mean score across frames
    mean_scores = np.mean(scores, axis=0)

    # Class 19: Crying, sobbing
    # Class 20: Baby cry, infant cry
    # Class 11: Screaming
    crying_score = float(max(mean_scores[19], mean_scores[20]))
    
    top_indices = np.argsort(mean_scores)[::-1][:5]
    top_predictions = [(class_names[idx], float(mean_scores[idx])) for idx in top_indices]

    # Classification logic with confidence & uncertain state
    if crying_score >= 0.40:
        classification = "Possible Baby Crying"
        confidence = crying_score
    elif crying_score >= 0.20:
        classification = "Uncertain"
        confidence = crying_score
    else:
        classification = "Other Sound"
        confidence = float(mean_scores[top_indices[0]])

    return {
        "classification": classification,
        "crying_confidence": round(crying_score, 4),
        "primary_label": classification,
        "top_predictions": top_predictions
    }

def main():
    print("=" * 60)
    print("PHASE 3: LOCAL YAMNET ONNX MODEL EVALUATION")
    print("=" * 60)
    print(f"Loading ONNX Model from: {MODEL_PATH}")
    session = ort.InferenceSession(MODEL_PATH)
    class_names = load_class_names()
    print(f"Loaded {len(class_names)} AudioSet class definitions.\n")

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
    # Add vocal tract resonance envelope
    envelope = (np.sin(2 * np.pi * 1.5 * t) ** 2)
    cry = cry * envelope
    test_cases.append(("Infant Cry Acoustic Simulation", cry.astype(np.float32)))

    print("Evaluating test sounds through YAMNet:\n")
    for name, signal in test_cases:
        res = run_inference(session, class_names, signal, sample_rate)
        print(f"[*] Test Sound: {name}")
        print(f"    -> Classification: {res['classification']}")
        print(f"    -> Cry Confidence: {res['crying_confidence'] * 100:.1f}%")
        print(f"    -> Top 3 Predictions: {', '.join([f'{c} ({s*100:.1f}%)' for c, s in res['top_predictions'][:3]])}")
        print("-" * 60)

    print("\nPhase 3 Model Verification Complete!")

if __name__ == "__main__":
    main()
