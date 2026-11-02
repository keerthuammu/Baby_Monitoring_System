import os
import sys
sys.path.insert(0, os.path.abspath("backend"))
sys.path.insert(0, os.path.abspath("."))
import glob
import numpy as np
import wave
from app.audio.yamnet_classifier import YamnetClassifier
from tests.diagnostic_audit import load_wav

classifier = YamnetClassifier.get_instance()

def analyze_dataset():
    pos_files = glob.glob("backend/app/audio/benchmark_dataset/positive_crying/*.wav")
    neg_files = glob.glob("backend/app/audio/benchmark_dataset/negative_*/*.wav")
    
    cry_indices = [20, 19] # Baby cry, Crying/sobbing
    comp_indices = [0, 1, 2, 4, 5, 6, 7, 13, 14, 15, 58, 62, 132, 494, 348, 349, 351, 74] # speech, laugh, clap, music, silence, door, dog
    
    print("=" * 80)
    print("CALIBRATION ANALYSIS: POSITIVE (BABY CRYING) SAMPLES")
    print("=" * 80)
    pos_stats = []
    for f in sorted(pos_files):
        data, sr = load_wav(f)
        for c_idx in range(0, max(1, len(data) // 16000)):
            chunk = data[c_idx*16000 : (c_idx+1)*16000]
            if len(chunk) < 8000:
                continue
            
            # calculate crest factor: peak / rms
            rms = np.sqrt(np.mean(chunk**2))
            peak = np.max(np.abs(chunk))
            crest_factor_db = 20.0 * np.log10(peak / rms) if rms > 1e-6 else 0.0
            
            # Run raw YAMNet
            if len(chunk) < 15600:
                chunk = np.pad(chunk, (0, 15600 - len(chunk)))
            out = classifier.session.run(None, {classifier.input_name: chunk})
            mean_sc = np.mean(out[0], axis=0)
            
            c_score = float(max(mean_sc[20], mean_sc[19]))
            d_neg = float(max(mean_sc[idx] for idx in comp_indices))
            margin = c_score - d_neg
            
            # Top class
            top_idx = np.argmax(mean_sc)
            top_name = classifier.class_names[top_idx]
            
            pos_stats.append((os.path.basename(f), c_idx, c_score, d_neg, margin, crest_factor_db, top_name))
            print(f"POS [{os.path.basename(f)[:16]:<16} c{c_idx:02d}] CrySc: {c_score:.3f} | DomNeg: {d_neg:.3f} | Margin: {margin:+.3f} | Crest: {crest_factor_db:4.1f}dB | Top: {top_name}")

    print("\n" + "=" * 80)
    print("CALIBRATION ANALYSIS: NEGATIVE (AMBIENT, SPEECH, CLAP, DOOR, LAUGH) SAMPLES")
    print("=" * 80)
    neg_stats = []
    for f in sorted(neg_files):
        data, sr = load_wav(f)
        for c_idx in range(0, max(1, len(data) // 16000)):
            chunk = data[c_idx*16000 : (c_idx+1)*16000]
            if len(chunk) < 8000:
                continue
            
            rms = np.sqrt(np.mean(chunk**2))
            peak = np.max(np.abs(chunk))
            crest_factor_db = 20.0 * np.log10(peak / rms) if rms > 1e-6 else 0.0
            
            if len(chunk) < 15600:
                chunk = np.pad(chunk, (0, 15600 - len(chunk)))
            out = classifier.session.run(None, {classifier.input_name: chunk})
            mean_sc = np.mean(out[0], axis=0)
            
            c_score = float(max(mean_sc[20], mean_sc[19]))
            d_neg = float(max(mean_sc[idx] for idx in comp_indices))
            margin = c_score - d_neg
            
            top_idx = np.argmax(mean_sc)
            top_name = classifier.class_names[top_idx]
            
            neg_stats.append((os.path.basename(f), c_idx, c_score, d_neg, margin, crest_factor_db, top_name))
            if c_score > 0.05 or crest_factor_db > 14.0:
                print(f"NEG [{os.path.basename(f)[:16]:<16} c{c_idx:02d}] CrySc: {c_score:.3f} | DomNeg: {d_neg:.3f} | Margin: {margin:+.3f} | Crest: {crest_factor_db:4.1f}dB | Top: {top_name}")

    max_neg_cry = max(s[2] for s in neg_stats)
    print("\n" + "=" * 80)
    print(f"SUMMARY STATISTICS:")
    print(f"Maximum cry score among ALL negative audio samples: {max_neg_cry:.4f}")
    print(f"Minimum cry score on active cry frames: {min(s[2] for s in pos_stats if s[2] > 0.10):.4f}")
    print("=" * 80)

if __name__ == "__main__":
    analyze_dataset()
