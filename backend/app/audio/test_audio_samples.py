import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.audio.yamnet_classifier import YamnetClassifier

c = YamnetClassifier.get_instance()

test_files = [
    ("Baby Crying", "backend/app/audio/benchmark_dataset/positive_crying/baby_cry_real_0.wav"),
    ("Baby Crying 2", "backend/app/audio/benchmark_dataset/positive_crying/1-187207-A-20.wav"),
    ("Adult Speech", "backend/app/audio/benchmark_dataset/negative_speech/female_speech_1.wav"),
    ("Male Speech", "backend/app/audio/benchmark_dataset/negative_speech/male_speech_1.wav"),
    ("Clapping", "backend/app/audio/benchmark_dataset/negative_household/clapping_1.wav"),
    ("Door Knock/Slam", "backend/app/audio/benchmark_dataset/negative_household/door_knock_1.wav"),
    ("Dog Bark", "backend/app/audio/benchmark_dataset/negative_household/dog_bark_1.wav"),
    ("Room Silence", "backend/app/audio/benchmark_dataset/negative_ambient/room_silence.wav")
]

print("=" * 75)
print(f"{'Audio Category':<18} | {'Display Label':<22} | {'Code':<22} | {'Confidence'}")
print("=" * 75)

for label, path in test_files:
    c.reset_temporal_state()
    with open(path, "rb") as f:
        data = f.read()
    res = c.classify_wav_bytes(data)
    disp = res["display_label"]
    code = res["classification"]
    conf = f"{res['confidence']*100:.1f}%"
    print(f"{label:<18} | {disp:<22} | {code:<22} | {conf}")

print("=" * 75)
