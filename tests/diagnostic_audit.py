import os
import sys
sys.path.insert(0, os.path.abspath("backend"))
import glob
import numpy as np
import wave
from app.audio.yamnet_classifier import YamnetClassifier
from app.services.monitor_service import MonitorService
from app.schemas.schemas import ReadingCreate
from app.core.database import SessionLocal, init_db

init_db()
db = SessionLocal()

classifier = YamnetClassifier.get_instance()

def load_wav(path):
    with wave.open(path, 'rb') as wav:
        n_channels = wav.getnchannels()
        sampwidth = wav.getsampwidth()
        framerate = wav.getframerate()
        n_frames = wav.getnframes()
        raw = wav.readframes(n_frames)
        if sampwidth == 2:
            data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        elif sampwidth == 4:
            data = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
        else:
            data = np.frombuffer(raw, dtype=np.int8).astype(np.float32) / 128.0
        if n_channels > 1:
            data = data.reshape(-1, n_channels).mean(axis=1)
        if framerate != 16000 and framerate > 0:
            target_len = int(len(data) * 16000 / framerate)
            data = np.interp(
                np.linspace(0, len(data), target_len, endpoint=False),
                np.arange(len(data)),
                data
            ).astype(np.float32)
            framerate = 16000
        return data, framerate

print("=" * 100)
print("STEP 1 DIAGNOSTIC AUDIT: EVALUATING CURRENT CLASSIFIER ON BENCHMARK DATASET")
print("=" * 100)

categories = {
    "Ambient / Room Noise": glob.glob("backend/app/audio/benchmark_dataset/negative_ambient/*.wav"),
    "Household (Clap/Door/Bark)": glob.glob("backend/app/audio/benchmark_dataset/negative_household/*.wav"),
    "Speech (Male/Female)": glob.glob("backend/app/audio/benchmark_dataset/negative_speech/*.wav"),
    "Real Baby Crying": glob.glob("backend/app/audio/benchmark_dataset/positive_crying/*.wav")
}

for cat_name, files in categories.items():
    print(f"\n--- Category: {cat_name} ({len(files)} files) ---")
    for f in sorted(files):
        fname = os.path.basename(f)
        classifier.reset_temporal_state()
        data, sr = load_wav(f)
        
        # Test in 1-second chunks
        chunk_len = 16000
        for chunk_idx in range(0, max(1, len(data) // chunk_len)):
            chunk = data[chunk_idx * chunk_len : (chunk_idx + 1) * chunk_len]
            if len(chunk) < 8000:
                continue
            
            res = classifier.classify_waveform(chunk, sample_rate=sr)
            top5 = ", ".join([f"{c['class_name']}:{c['score']:.2f}" for c in res['top_classes'][:3]])
            print(f"[{fname[:18]:<18} c{chunk_idx}] dB:{res['sound_level_db']:<4.1f} | CryScore:{res['crying_score_raw']:.2f} | DatMatch:{res.get('dataset_match_score',0):.2f} | Top3: {top5} | Final: {res['display_label']}")

print("\n--- Diagnostic check on Edge Pitch Alone in MonitorService ---")
# Simulate an edge reading where edge detected pitch 480 Hz with 52 dB (e.g. ambient fan/TV) without YAMNet
reading_fake = ReadingCreate(
    device_id="esp32-test-edge",
    sound_level=52.0,
    rms_amplitude=1200.0,
    peak_amplitude=2500,
    pitch_hz=480.0,
    classification="POSSIBLE_CRYING",
    confidence=0.88
)
r_out = MonitorService.record_reading(db, reading_fake)
auth_state = MonitorService.get_authoritative_status(db)
print(f"Edge Packet (pitch 480 Hz, 52 dB, POSSIBLE_CRYING) -> DB Reading: {r_out.classification} | Authoritative Status: {auth_state['classification']}")

# Simulate edge reading with pitch 480 Hz but classification was QUIET or not provided
reading_pitch_only = ReadingCreate(
    device_id="esp32-test-edge2",
    sound_level=50.0,
    rms_amplitude=1100.0,
    peak_amplitude=2200,
    pitch_hz=520.0,
    classification="QUIET",
    confidence=0.85
)
r_out2 = MonitorService.record_reading(db, reading_pitch_only)
auth_state2 = MonitorService.get_authoritative_status(db)
print(f"Edge Packet (pitch 520 Hz, 50 dB, QUIET) -> DB Reading: {r_out2.classification} | Authoritative Status: {auth_state2['classification']}")

db.close()
