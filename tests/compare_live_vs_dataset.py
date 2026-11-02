import os
import sys
import wave
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

from app.audio.yamnet_classifier import YamnetClassifier

def load_wav(path):
    with wave.open(path, 'rb') as wf:
        sr = wf.getframerate()
        n_ch = wf.getnchannels()
        sw = wf.getsampwidth()
        frames = wf.readframes(wf.getnframes())
        if sw == 2:
            signal = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
        elif sw == 4:
            signal = np.frombuffer(frames, dtype=np.int32).astype(np.float32) / 2147483648.0
        else:
            signal = np.frombuffer(frames, dtype=np.int8).astype(np.float32) / 128.0
        if n_ch > 1:
            signal = signal.reshape(-1, n_ch).mean(axis=1)
        if sr != 16000:
            target_len = int(len(signal) * 16000 / sr)
            signal = np.interp(np.linspace(0, len(signal), target_len, endpoint=False), np.arange(len(signal)), signal).astype(np.float32)
        return signal

def analyze_audio(name, signal):
    classifier = YamnetClassifier.get_instance()
    
    # 0.975s window (15600 samples)
    if len(signal) > 15600:
        sig_window = signal[:15600]
    else:
        sig_window = np.pad(signal, (0, 15600 - len(signal)))
        
    sig_min = float(np.min(sig_window))
    sig_max = float(np.max(sig_window))
    sig_mean = float(np.mean(sig_window))
    sig_std = float(np.std(sig_window))
    rms = float(np.sqrt(np.mean(sig_window**2)))
    peak = float(np.max(np.abs(sig_window)))
    db = float(20.0 * np.log10(rms * 32768.0)) if rms > 1e-6 else 0.0

    # Run inference directly
    outputs = classifier.session.run(None, {classifier.input_name: sig_window})
    scores = outputs[0]
    mean_scores = np.mean(scores, axis=0)
    top10_idx = np.argsort(mean_scores)[::-1][:10]

    print("=" * 70)
    print(f"AUDIO: {name}")
    print("=" * 70)
    print(f"Amplitude stats (in [-1.0, 1.0] scale):")
    print(f"  Min:  {sig_min:+.5f}")
    print(f"  Max:  {sig_max:+.5f}")
    print(f"  Mean: {sig_mean:+.5f}")
    print(f"  Std:  {sig_std:.5f}")
    print(f"  RMS:  {rms:.5f} (in int16: {rms*32768.0:.1f})")
    print(f"  Peak: {peak:.5f} (in int16: {peak*32768.0:.0f})")
    print(f"  dB:   {db:.1f} dB")
    print(f"\nTop-10 YAMNet Classes & Scores:")
    for rank, idx in enumerate(top10_idx, 1):
        cname = classifier.class_names[idx]
        sc = mean_scores[idx]
        is_cry = " *** [CRY TARGET] ***" if idx in [19, 20] else ""
        print(f"  {rank:2d}. {cname:<35} : {sc:.4f}{is_cry}")
    print(f"Cry class 20 ('Baby cry, infant cry'): score = {mean_scores[20]:.4f}")
    print(f"Cry class 19 ('Crying, sobbing')      : score = {mean_scores[19]:.4f}")
    print("=" * 70 + "\n")

if __name__ == "__main__":
    cry_wav = "backend/app/audio/benchmark_dataset/positive_crying/1-187207-A-20.wav"
    dataset_sig = load_wav(cry_wav)
    analyze_audio("Dataset Cry WAV (1-187207-A-20.wav)", dataset_sig)

    # Simulate live unboosted chunk (RMS ~150, peak ~1200 as observed in live packets)
    live_unboosted = dataset_sig * (150.0 / (np.sqrt(np.mean(dataset_sig[:15600]**2)) * 32768.0))
    analyze_audio("Live Unboosted Cry Chunk (INMP441 level: RMS ~150, Peak ~1200)", live_unboosted)

