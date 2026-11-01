"""
Benchmark Dataset Downloader for Smart Baby Monitor Evaluation
Downloads verified, legally accessible open audio samples:
1. Positive: ESC-50 Category 20 (crying_baby) - diverse infants, whimpers, environments
2. Negative Speech: SpeechBrain / DeepSpeech - adult male and female speech
3. Negative Domestic: ESC-50 - door knocks, clapping, laughing, coughing, domestic noise
4. Negative Ambient: Room silence, ambient noise
"""

import os
import urllib.request
import csv
import io
import wave
import numpy as np

DATASET_DIR = os.path.join(os.path.dirname(__file__), "benchmark_dataset")
POSITIVE_DIR = os.path.join(DATASET_DIR, "positive_crying")
NEGATIVE_SPEECH_DIR = os.path.join(DATASET_DIR, "negative_speech")
NEGATIVE_HOUSEHOLD_DIR = os.path.join(DATASET_DIR, "negative_household")
NEGATIVE_AMBIENT_DIR = os.path.join(DATASET_DIR, "negative_ambient")

for d in [POSITIVE_DIR, NEGATIVE_SPEECH_DIR, NEGATIVE_HOUSEHOLD_DIR, NEGATIVE_AMBIENT_DIR]:
    os.makedirs(d, exist_ok=True)

ESC50_BASE_URL = "https://raw.githubusercontent.com/karoldvl/ESC-50/master/audio/"

# 1. Selected ESC-50 crying files (category 20) across different folds/recordings
ESC50_CRYING_FILES = [
    "1-187207-A-20.wav", "1-211527-A-20.wav", "1-211527-B-20.wav", "1-211527-C-20.wav",
    "1-22694-A-20.wav", "2-107351-A-20.wav", "2-107351-B-20.wav", "2-107412-A-20.wav",
    "3-149177-A-20.wav", "3-157695-A-20.wav", "4-161303-A-20.wav", "4-161303-B-20.wav",
    "5-198891-A-20.wav", "5-198891-B-20.wav", "5-21437-A-20.wav"
]

# 2. Selected ESC-50 household & domestic negative files
# 14/30: door knock, 22/26: clapping/applause, 24: coughing, 0/26: laughter/laughing, 35: washing machine
ESC50_HOUSEHOLD_FILES = [
    ("1-100038-A-14.wav", "door_knock_1.wav"),
    ("1-34495-A-14.wav", "door_knock_2.wav"),
    ("1-1791-A-26.wav", "clapping_1.wav"),
    ("1-30039-A-26.wav", "clapping_2.wav"),
    ("1-100032-A-0.wav", "laughter_1.wav"),
    ("1-110389-A-0.wav", "laughter_2.wav"),
    ("1-26177-A-24.wav", "coughing_1.wav"),
    ("2-107228-A-35.wav", "washing_machine_1.wav"),
    ("1-10021-A-36.wav", "vacuum_cleaner_1.wav"),
    ("1-17124-A-42.wav", "siren_alarm_1.wav"),
    ("1-30226-A-0.wav", "laughter_3.wav"),
    ("2-117615-A-30.wav", "door_knock_3.wav")
]

# 3. Speech samples (adult male and female speech)
SPEECH_FILES = [
    ("https://raw.githubusercontent.com/speechbrain/speechbrain/develop/tests/samples/ASR/spk1_snt1.wav", "female_speech_1.wav"),
    ("https://raw.githubusercontent.com/speechbrain/speechbrain/develop/tests/samples/ASR/spk1_snt2.wav", "female_speech_2.wav"),
    ("https://raw.githubusercontent.com/speechbrain/speechbrain/develop/tests/samples/ASR/spk1_snt3.wav", "female_speech_3.wav"),
    ("https://raw.githubusercontent.com/speechbrain/speechbrain/develop/tests/samples/ASR/spk2_snt1.wav", "male_speech_1.wav"),
    ("https://raw.githubusercontent.com/speechbrain/speechbrain/develop/tests/samples/ASR/spk2_snt2.wav", "male_speech_2.wav"),
    ("https://raw.githubusercontent.com/speechbrain/speechbrain/develop/tests/samples/ASR/spk2_snt3.wav", "male_speech_3.wav"),
    ("https://raw.githubusercontent.com/mozilla/DeepSpeech/master/data/smoke_test/LDC93S1.wav", "male_speech_timit.wav")
]

def download_file(url: str, dest_path: str):
    if os.path.exists(dest_path) and os.path.getsize(dest_path) > 1000:
        return
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read()
            with open(dest_path, "wb") as f:
                f.write(data)
        print(f"Downloaded: {os.path.basename(dest_path)} ({len(data)} bytes)")
    except Exception as e:
        print(f"Failed to download {url}: {e}")

def create_ambient_files():
    # Generate controlled ambient baseline files (silence, white noise, room rumble)
    sr = 16000
    duration = 4.0
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)

    # 1. Pure room silence
    silence = np.zeros(len(t), dtype=np.int16)
    write_wav(os.path.join(NEGATIVE_AMBIENT_DIR, "room_silence.wav"), silence, sr)

    # 2. Quiet air conditioner / room noise (-45 dB)
    room_noise = (np.random.normal(0, 150.0, len(t))).astype(np.int16)
    write_wav(os.path.join(NEGATIVE_AMBIENT_DIR, "quiet_room_noise.wav"), room_noise, sr)

    # 3. Low-frequency electrical hum (50/60 Hz)
    hum = (800.0 * np.sin(2 * np.pi * 50.0 * t) + 300.0 * np.sin(2 * np.pi * 100.0 * t)).astype(np.int16)
    write_wav(os.path.join(NEGATIVE_AMBIENT_DIR, "electrical_hum.wav"), hum, sr)

def write_wav(path: str, data: np.ndarray, sr: int):
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(data.tobytes())
    print(f"Created synthetic ambient: {os.path.basename(path)}")

def main():
    print("Downloading positive baby crying samples...")
    for f in ESC50_CRYING_FILES:
        url = ESC50_BASE_URL + f
        dest = os.path.join(POSITIVE_DIR, f)
        download_file(url, dest)

    print("\nDownloading negative household samples...")
    for remote_name, local_name in ESC50_HOUSEHOLD_FILES:
        url = ESC50_BASE_URL + remote_name
        dest = os.path.join(NEGATIVE_HOUSEHOLD_DIR, local_name)
        download_file(url, dest)

    print("\nDownloading negative adult speech samples...")
    for url, local_name in SPEECH_FILES:
        dest = os.path.join(NEGATIVE_SPEECH_DIR, local_name)
        download_file(url, dest)

    print("\nCreating ambient baseline files...")
    create_ambient_files()

    print("\nDataset download complete!")

if __name__ == "__main__":
    main()
