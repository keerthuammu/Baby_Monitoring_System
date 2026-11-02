import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

from app.audio.yamnet_classifier import YamnetClassifier

c = YamnetClassifier.get_instance()
cry_files = sorted(glob.glob('backend/app/audio/benchmark_dataset/positive_crying/*.wav'))
neg_files = sorted(glob.glob('backend/app/audio/benchmark_dataset/negative_household/*.wav') + 
                    glob.glob('backend/app/audio/benchmark_dataset/negative_speech/*.wav') + 
                    glob.glob('backend/app/audio/benchmark_dataset/negative_ambient/*.wav'))

print("--- CRY FILES VIA classify_wav_bytes ---")
cry_passed = 0
for cf in cry_files:
    fname = os.path.basename(cf)
    with open(cf, 'rb') as f:
        data = f.read()
    c.reset_temporal_state()
    res = c.classify_wav_bytes(data)
    is_cry = (res["classification"] == "BABY_CRYING_DETECTED")
    if is_cry:
        cry_passed += 1
    print(f"[{'PASS' if is_cry else 'FAIL'}] {fname:<22} -> {res['display_label']:<22} (Score: {res['crying_score']:.3f}, Rule: {res['decision_rule']})")

print(f"\nCry Recall: {cry_passed} / {len(cry_files)} ({cry_passed/len(cry_files)*100:.1f}%)")

print("\n--- NEGATIVE FILES VIA classify_wav_bytes ---")
neg_passed = 0
for nf in neg_files:
    fname = os.path.basename(nf)
    with open(nf, 'rb') as f:
        data = f.read()
    c.reset_temporal_state()
    res = c.classify_wav_bytes(data)
    is_not_cry = (res["classification"] == "NOT_BABY_CRYING")
    if is_not_cry:
        neg_passed += 1
    print(f"[{'PASS' if is_not_cry else 'FAIL'}] {fname:<22} -> {res['display_label']:<22} (Score: {res['crying_score']:.3f}, Rule: {res['decision_rule']})")

print(f"\nNegative Specificity: {neg_passed} / {len(neg_files)} ({neg_passed/len(neg_files)*100:.1f}%)")

