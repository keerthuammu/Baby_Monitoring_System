# Acoustic Audio Classification & Dataset Guide

## 1. Acoustic Science of Infant Crying

A core requirement of this MCA college project is demonstrating a scientifically grounded distinction between **general ambient room noise** and **authentic infant crying**.

```
                           Acoustic Spectrum Breakdown
 ┌──────────────────────┬──────────────────────┬────────────────────────────┐
 │ Low Ambient Hum / TV │ Adult Human Speech   │ Infant Crying Signature    │
 │ 50 Hz - 250 Hz       │ 85 Hz - 255 Hz       │ 350 Hz - 680 Hz (F0 Pitch) │
 └──────────────────────┴──────────────────────┴────────────────────────────┘
```

### Fundamental Characteristics of an Infant Cry
1. **Fundamental Frequency ($F_0$ / Pitch):**
   - The fundamental pitch of a newborn or infant cry ranges characteristically between **350 Hz and 680 Hz** (averaging ~450–500 Hz).
   - Adult male speech typically sits between **85 Hz and 180 Hz**, and adult female speech sits between **165 Hz and 255 Hz**.
   - Low rumble (air conditioners, vehicle traffic, door thuds) occurs below **250 Hz**.
2. **Formant Resonances:**
   - Infant cries show prominent acoustic energy concentrated in the **350 Hz to 2,500 Hz** band.
3. **Temporal Cry Rhythm:**
   - Infant crying is characterized by rhythmic expiratory phonation phases (typically 0.7s to 2.5s) followed by brief inspiratory pauses.
   - Continuous flat tones or abrupt transient clicks (applause, door slams) lack this physiological harmonic structure.

---

## 2. Classification Architecture Implemented

The system provides dual-mode classification in [backend/app/audio/](file:///e:/Baby_Monitoring_System/backend/app/audio/):

1. **Feature Extraction ([features.py](file:///e:/Baby_Monitoring_System/backend/app/audio/features.py)):**
   - **RMS & Decibel Sound Level ($dB$):** $20 \log_{10}(\text{RMS})$.
   - **Zero-Crossing Rate (ZCR):** Detects noise vs periodic vocal resonance.
   - **Normalized Autocorrelation ($F_0$ Pitch Estimation):** Detects fundamental frequency and harmonic periodicity.
   - **FFT Spectral Energy Ratio:** Measures the proportion of energy within the cry frequency band ($350\text{ Hz} - 2500\text{ Hz}$).
   - **Spectral Centroid:** Computes the acoustic brightness / center of mass of the frequency spectrum.

2. **Classification Decision Logic ([classifier.py](file:///e:/Baby_Monitoring_System/backend/app/audio/classifier.py)):**
   - 🟢 **`QUIET`**: Sound level $< 45\text{ dB}$.
   - 🟡 **`HIGH_SOUND_ACTIVITY`**: Sound level $\ge 65\text{ dB}$, but pitch and spectral features do NOT match an infant cry (e.g., adult voices, dog barks, TV, dropped objects).
   - 🔴 **`POSSIBLE_CRYING`**: Sound level $\ge 55\text{ dB}$ **AND** fundamental pitch $F_0 \in [350\text{ Hz}, 680\text{ Hz}]$ **AND** periodicity $\ge 0.30$ **AND** cry-band energy ratio $\ge 0.40$.
   - ⚪ **`UNCERTAIN`**: Borderline acoustic energy or weak periodicity.

3. **Audio Upload Endpoint (`POST /api/audio/classify`):**
   - Ingests audio WAV chunks, performs feature extraction, classifies the sound, logs the telemetry, and triggers visual alerts.
   - **Privacy Protection:** The audio file is decoded in volatile RAM and immediately discarded. No audio recordings are permanently stored on disk.

---

## 3. Public Datasets for Advanced Machine Learning

If training a deep neural network (e.g., 1D-CNN or MobileNet spectrogram classifier), the following benchmark datasets can be utilized:

1. **Donate-a-Cry Corpus:**
   - Curated by Appseeq; contains over 450 categorized audio clips of infant crying.
   - Publicly accessible for academic research on GitHub and Kaggle.
2. **Baby Chillanto Database:**
   - Collected by the National Institute of Astrophysics, Optics and Electronics (INAOE), Mexico.
   - Contains classified cry recordings from healthy and pathological neonates.
3. **ESC-50 (Dataset for Environmental Sound Classification):**
   - Provides 2,000 labeled environmental recordings (50 classes including crying babies, barking dogs, vacuum cleaners, door knocks, and rain) to train negative background classes.

---

## 4. Academic Disclaimer & Viva Defense Points

When presenting your MCA Major Project:

- **Assistive Scope:** State clearly that this system is an **assistive monitoring tool** for caregivers, not a medical diagnostic system.
- **Why Sound-Level Alone is Insufficient:** Explain to your evaluators that an ordinary decibel meter alarms on every dropped cup, traffic horn, or loud television dialogue. Your project implements acoustic spectral analysis to separate generic ambient noise from vocal crying signatures.
- **Medical Etiology Limitation:** Sound analysis alone **cannot** reliably diagnose infant medical conditions, hunger, pain, or fever without clinical sensors. The system intentionally avoids fabricated diagnostic claims.
