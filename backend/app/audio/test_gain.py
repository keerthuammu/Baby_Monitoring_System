import sys, os, numpy as np
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from app.audio.yamnet_classifier import YamnetClassifier
from app.audio.evaluate_benchmark import load_wav_as_16k_mono

c = YamnetClassifier.get_instance()
sig = load_wav_as_16k_mono("backend/app/audio/test_samples/baby_cry_real.wav")[:16000]

# Full volume
c.reset_temporal_state()
res1 = c.classify_waveform(sig, 16000)
top1 = ", ".join([f"{cl['class_name']}: {cl['score']:.2f}" for cl in res1['top_classes'][:3]])

# Attenuated 10x (mimicking quiet phone speaker)
c.reset_temporal_state()
res2 = c.classify_waveform(sig * 0.1, 16000)
top2 = ", ".join([f"{cl['class_name']}: {cl['score']:.2f}" for cl in res2['top_classes'][:3]])

print("Full volume ->", res1["display_label"], "| Top:", top1)
print("Quiet (0.1x) ->", res2["display_label"], "| Top:", top2)
