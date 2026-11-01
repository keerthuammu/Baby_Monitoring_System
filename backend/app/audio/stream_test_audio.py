"""
Simulate streaming a positive crying audio file to the backend
Usage:
  python backend/app/audio/stream_test_audio.py [filename]

Streams 1-second 16kHz PCM chunks to http://localhost:8000/api/audio/test-classify
and updates the dashboard live in real-time.
"""

import os
import sys
import time
import requests
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from app.audio.evaluate_benchmark import load_wav_as_16k_mono

DATASET_DIR = os.path.join(os.path.dirname(__file__), "benchmark_dataset", "positive_crying")

def stream_audio(wav_filename="baby_cry_real_0.wav", target_url=None):
    if target_url is None:
        target_url = os.environ.get("STREAM_TARGET_URL", "https://baby-monitor-backend-8m8o.onrender.com/api/audio/test-classify")
    filepath = os.path.join(DATASET_DIR, wav_filename) if not os.path.exists(wav_filename) else wav_filename
    if not os.path.exists(filepath):
        print(f"[ERROR] File not found: {filepath}")
        return

    sig = load_wav_as_16k_mono(filepath)
    print("=" * 65)
    print(f"STREAMING REAL BABY CRYING AUDIO: {os.path.basename(filepath)}")
    print(f"Total Duration: {len(sig)/16000:.1f}s | Target Endpoint: {target_url}")
    print("=" * 65)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "X-Device-Id": "esp32-nursery-01"
    }

    num_windows = len(sig) // 16000
    for w_idx in range(num_windows):
        window_samples = sig[w_idx * 16000 : (w_idx + 1) * 16000]
        pcm_int16 = (window_samples * 32767.0).astype("int16").tobytes()

        # Send as multipart form file for maximum compatibility with Cloudflare and ASGI
        files = {
            "file": (f"chunk_{w_idx}.pcm", pcm_int16, "application/octet-stream")
        }

        try:
            resp = requests.post(target_url, files=files, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                top_str = ", ".join([f"{c['class_name']} ({c['score']*100:.0f}%)" for c in data.get("top_classes", [])[:2]])
                print(f"[Window {w_idx+1}/{num_windows}] HTTP 200 -> {data.get('classification')} ({data.get('confidence',0)*100:.0f}%) | Level: {data.get('sound_level_db',0):.1f} dB | Top: {top_str}")
            else:
                print(f"[Window {w_idx+1}] HTTP {resp.status_code}: {resp.text[:100]}")
        except Exception as e:
            print(f"[Window {w_idx+1}] Stream failed: {e}")

        time.sleep(1.5)

    print("=" * 65)
    print("[SUCCESS] Audio stream completed. Check your dashboard to observe live detection!")
    print("=" * 65)

if __name__ == "__main__":
    target_file = sys.argv[1] if len(sys.argv) > 1 else "baby_cry_real_0.wav"
    stream_audio(target_file)
