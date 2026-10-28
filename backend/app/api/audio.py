import io
import wave
import numpy as np
from typing import Optional
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import verify_device_api_key
from app.audio.yamnet_classifier import YamnetClassifier
from app.audio.classifier import AcousticClassifier
from app.services.monitor_service import MonitorService
from app.schemas.schemas import ReadingCreate

router = APIRouter(prefix="/api/audio", tags=["Audio Classification"])

@router.get("/status", status_code=status.HTTP_200_OK)
def get_audio_classification_status():
    """
    Returns the real-time audio sound classification and confidence.
    Enforces a freshness guard: if no audio is ingested within 6 seconds,
    automatically marks status as 'Microphone or connection unavailable'.
    """
    classifier = YamnetClassifier.get_instance()
    return classifier.get_current_status(staleness_seconds=6.0)

@router.post("/classify", status_code=status.HTTP_200_OK)
async def classify_audio_sample(
    file: UploadFile = File(..., description="Audio file in WAV format (mono, 16-bit PCM, 16kHz recommended)"),
    device_id: str = Form("esp32-nursery-01"),
    db: Session = Depends(get_db),
    _auth: bool = Depends(verify_device_api_key)
):
    """
    Ingests and classifies an audio sample chunk locally using Google YAMNet ONNX.
    Differentiates between:
    - 'Possible Baby Crying'
    - 'Other Sound'
    - 'Uncertain'
    
    Privacy Protection:
    Audio chunks are processed entirely in memory and immediately discarded.
    """
    try:
        content = await file.read()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read audio payload: {str(e)}"
        )

    classifier = YamnetClassifier.get_instance()
    result = classifier.classify_wav_bytes(content)

    if result.get("status") == "UNAVAILABLE":
        # Fallback to AcousticClassifier if WAV header was non-standard
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("reason", "Invalid audio container")
        )

    classification = result["classification"]
    confidence = result["confidence"]

    # Record reading in database to update sound metrics
    reading_in = ReadingCreate(
        device_id=device_id,
        sound_level=result["sound_level_db"],
        rms_amplitude=result["rms_amplitude"],
        peak_amplitude=result["peak_amplitude"]
    )
    MonitorService.record_reading(
        db, 
        reading_in, 
        classification=classification, 
        confidence=confidence
    )

    return {
        "status": "success",
        "device_id": device_id,
        "classification": classification,
        "confidence": confidence,
        "sound_level_db": result["sound_level_db"],
        "top_classes": result.get("top_classes", [])
    }

