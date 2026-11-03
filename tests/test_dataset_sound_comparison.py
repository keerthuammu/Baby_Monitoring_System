import pytest
import wave
import numpy as np
from app.audio.yamnet_classifier import YamnetClassifier
from app.core.config import settings

def test_microphone_audio_compared_with_dataset():
    """
    Verifies that incoming microphone audio is explicitly compared against
    the reference baby crying dataset profiles (cosine similarity with centroid
    and individual reference samples).
    """
    classifier = YamnetClassifier.get_instance()
    assert classifier.crying_centroid is not None, "Crying dataset centroid must be loaded"
    assert classifier.dataset_crying_embeddings is not None, "Dataset crying profiles must be loaded"
    assert len(classifier.dataset_crying_embeddings) >= 8, "Expected at least 8 dataset reference samples"

    # 1. Test positive baby crying audio from dataset
    cry_file = "backend/app/audio/benchmark_dataset/positive_crying/2-107351-A-20.wav"
    cry_bytes = open(cry_file, "rb").read()
    cry_res = classifier.classify_wav_bytes(cry_bytes)

    assert "dataset_similarity" in cry_res, "dataset_similarity must be in classification output"
    assert "dataset_matched" in cry_res, "dataset_matched must be in classification output"
    assert "dataset_comparison" in cry_res, "dataset_comparison must be in classification output"
    
    # Real crying audio must have high dataset match (>= 0.70)
    assert cry_res["dataset_similarity"] >= 0.70, f"Expected high dataset similarity, got {cry_res['dataset_similarity']}"
    assert cry_res["dataset_matched"] is True
    assert cry_res["is_baby_crying"] is True

    # 2. Test adult speech audio
    speech_file = "backend/app/audio/benchmark_dataset/negative_speech/female_speech_1.wav"
    speech_bytes = open(speech_file, "rb").read()
    speech_res = classifier.classify_wav_bytes(speech_bytes)

    # Speech must have low dataset match (< 0.50)
    assert speech_res["dataset_similarity"] < 0.50, f"Expected low dataset similarity for speech, got {speech_res['dataset_similarity']}"
    assert speech_res["dataset_matched"] is False
    assert speech_res["is_baby_crying"] is False

    # 3. Test ambient noise
    noise_file = "backend/app/audio/benchmark_dataset/negative_ambient/quiet_room_noise.wav"
    noise_bytes = open(noise_file, "rb").read()
    noise_res = classifier.classify_wav_bytes(noise_bytes)

    assert noise_res["dataset_similarity"] < 0.40, f"Expected low dataset similarity for ambient noise, got {noise_res['dataset_similarity']}"
    assert noise_res["dataset_matched"] is False
    assert noise_res["is_baby_crying"] is False

def test_api_returns_dataset_comparison(client):
    """Verifies that /api/audio/classify and /api/audio/status return dataset comparison metrics."""
    cry_file = "backend/app/audio/benchmark_dataset/positive_crying/2-107351-A-20.wav"
    cry_bytes = open(cry_file, "rb").read()

    headers = {"X-API-Key": settings.API_KEY, "X-Device-Id": "esp32-dataset-test"}
    files = {"file": ("mic_audio.wav", cry_bytes, "audio/wav")}

    res = client.post("/api/audio/classify", files=files, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "dataset_similarity" in data
    assert "dataset_matched" in data
    assert "dataset_comparison" in data
    assert data["dataset_similarity"] >= 0.70
    assert data["dataset_matched"] is True

    # Check status endpoint
    status_res = client.get("/api/audio/status")
    assert status_res.status_code == 200
    sdata = status_res.json()
    assert "dataset_similarity" in sdata
    assert sdata["dataset_similarity"] >= 0.70

