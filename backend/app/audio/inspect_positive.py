import os
import sys
import glob
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from app.audio.yamnet_classifier import YamnetClassifier
from app.audio.evaluate_benchmark import load_wav_as_16k_mono

classifier = YamnetClassifier.get_instance()
positive_files = sorted(glob.glob("backend/app/audio/benchmark_dataset/positive_crying/*.wav"))

print(f"Total positive files: {len(positive_files)}")

for filepath in positive_files:
    fname = os.path.basename(filepath)
    classifier.reset_temporal_state()
    sig = load_wav_as_16k_mono(filepath)
    num_windows = min(5, len(sig) // 16000)
    results = []
    for w_idx in range(num_windows):
        w = sig[w_idx*16000:(w_idx+1)*16000]
        res = classifier.classify_waveform(w, 16000)
        results.append(res)
    
    crying_wins = sum(1 for r in results if r["display_label"] == "BABY CRYING DETECTED")
    labels = [r["display_label"] for r in results]
    top_classes = [r["top_classes"][0]["class_name"] for r in results]
    print(f"{fname:20s} | Detected: {crying_wins}/{num_windows} wins")
    if fname == "1-187207-A-20.wav":
        for i, r in enumerate(results):
            top_str = ", ".join([f"{c['class_name']}: {c['score']:.3f}" for c in r['top_classes'][:5]])
            print(f"   Win {i}: {top_str}")
