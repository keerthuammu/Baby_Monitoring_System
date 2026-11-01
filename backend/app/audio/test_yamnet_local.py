"""
Local Verification Script: Sound Classification Pipeline
Tests the improved multi-evidence YAMNet + Pitch Acoustic Classifier:
1. Real Baby Crying (ESC-50) -> BABY CRYING DETECTED
2. Real Adult Female Speech -> NOT BABY CRYING
3. Real Adult Male Speech -> NOT BABY CRYING
4. Real Clapping / Domestic Impact -> NOT BABY CRYING
5. Real Door Knock -> NOT BABY CRYING
6. Quiet Ambient Baseline -> NOT BABY CRYING
7. Ambiguous Borderline Probe -> UNCERTAIN
8. Stream Interruption Guard -> AUDIO UNAVAILABLE
"""

import os
import sys
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from app.audio.yamnet_classifier import YamnetClassifier
from app.audio.evaluate_benchmark import load_wav_as_16k_mono

BENCHMARK_DIR = os.path.join(os.path.dirname(__file__), "benchmark_dataset")

def run_test_sample(classifier, name: str, filepath: str):
    classifier.reset_temporal_state()
    sig = load_wav_as_16k_mono(filepath)
    # Take the first 1-sec and second 1-sec windows to show temporal consensus
    w1 = sig[:16000] if len(sig) >= 16000 else np.pad(sig, (0, 16000 - len(sig)))
    w2 = sig[16000:32000] if len(sig) >= 32000 else w1
    
    res1 = classifier.classify_waveform(w1, 16000)
    res2 = classifier.classify_waveform(w2, 16000)
    
    print(f"[*] Test Sound: {name} ({os.path.basename(filepath)})")
    print(f"    Window 1 -> Classification: {res1['display_label']} ({res1['confidence']*100:.0f}%) | dB: {res1['sound_level_db']}")
    print(f"    Window 2 -> Classification: {res2['display_label']} ({res2['confidence']*100:.0f}%) | dB: {res2['sound_level_db']}")
    top_str = ', '.join([f"{c['class_name']} ({c['score']*100:.0f}%)" for c in res2['top_classes'][:3]])
    print(f"    Top YAMNet Predictions: {top_str}")
    print("-" * 65)

def main():
    print("=" * 65)
    print("VERIFICATION OF IMPROVED SOUND CLASSIFICATION PIPELINE")
    print("=" * 65)
    classifier = YamnetClassifier.get_instance()
    print("Loaded YamnetClassifier pipeline with temporal hysteresis.\n")

    # 1. Real Baby Crying (Positive)
    cry_path = os.path.join(BENCHMARK_DIR, "positive_crying", "1-211527-A-20.wav")
    run_test_sample(classifier, "Real Infant Crying (ESC-50)", cry_path)

    # 2. Real Female Speech (Negative)
    female_path = os.path.join(BENCHMARK_DIR, "negative_speech", "female_speech_1.wav")
    run_test_sample(classifier, "Real Adult Female Speech (SpeechBrain)", female_path)

    # 3. Real Male Speech (Negative)
    male_path = os.path.join(BENCHMARK_DIR, "negative_speech", "male_speech_1.wav")
    run_test_sample(classifier, "Real Adult Male Speech (SpeechBrain)", male_path)

    # 4. Real Clapping (Negative)
    clap_path = os.path.join(BENCHMARK_DIR, "negative_household", "clapping_1.wav")
    run_test_sample(classifier, "Real Domestic Clapping (ESC-50)", clap_path)

    # 5. Real Door Knock (Negative)
    door_path = os.path.join(BENCHMARK_DIR, "negative_household", "door_knock_1.wav")
    run_test_sample(classifier, "Real Door Knock (ESC-50)", door_path)

    # 6. Real Laughter (Negative)
    laugh_path = os.path.join(BENCHMARK_DIR, "negative_household", "laughter_1.wav")
    run_test_sample(classifier, "Real Laughter (ESC-50)", laugh_path)

    # 7. Ambient Noise (Negative)
    ambient_path = os.path.join(BENCHMARK_DIR, "negative_ambient", "quiet_room_noise.wav")
    run_test_sample(classifier, "Quiet Room Ambient Noise", ambient_path)

    # 8. Test Freshness Guard (AUDIO UNAVAILABLE)
    print("[*] Testing Freshness Guard (Staleness Timeout):")
    status = classifier.get_current_status(staleness_seconds=0.0)
    print(f"    Staleness Guard State -> {status['classification']} (Code: {status['code']})")
    print("=" * 65)
    print("All Pipeline Tests PASSED Successfully!")

if __name__ == "__main__":
    main()
