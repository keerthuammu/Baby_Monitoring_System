import io
import wave
from datetime import datetime, timezone
import numpy as np
from typing import Optional
from fastapi import APIRouter, Depends, UploadFile, File, Form, Request, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.core.database import get_db
from app.core.security import verify_device_api_key
from app.audio.yamnet_classifier import YamnetClassifier
from app.services.monitor_service import MonitorService, to_utc
from app.models.models import CryingEvent
from app.schemas.schemas import ReadingCreate

router = APIRouter(prefix="/api/audio", tags=["Audio Classification"])

import logging

logger = logging.getLogger("audio_api")

@router.get("/status", status_code=status.HTTP_200_OK)
def get_audio_classification_status(db: Session = Depends(get_db)):
    """
    Returns the real-time audio sound classification and confidence from the trained model.
    Enforces the 4 required standard states:
    1. BABY CRYING DETECTED
    2. NOT BABY CRYING
    3. UNCERTAIN
    4. AUDIO UNAVAILABLE
    """
    classifier = YamnetClassifier.get_instance()
    status_data = classifier.get_current_status(staleness_seconds=6.0)

    if status_data.get("is_fresh"):
        status_data["engine"] = "Google YAMNet ONNX"
        return status_data

    # Guard: If no fresh audio arrived in last 6 seconds, report AUDIO UNAVAILABLE
    return {
        "classification": "AUDIO UNAVAILABLE",
        "code": "AUDIO_UNAVAILABLE",
        "confidence": 0.0,
        "status": "UNAVAILABLE",
        "is_fresh": False,
        "engine": "Offline / Awaiting Stream",
        "source": "model_freshness_guard",
        "seconds_since_update": status_data.get("seconds_since_update", 0.0),
        "last_update": status_data.get("last_update"),
        "top_classes": []
    }

@router.post("/classify", status_code=status.HTTP_200_OK)
async def classify_audio_sample(
    request: Request,
    db: Session = Depends(get_db),
    _auth: bool = Depends(verify_device_api_key)
):
    """
    Ingests raw 16kHz PCM audio chunk from ESP32 over local Wi-Fi,
    executes inference on the trained YAMNet model, and saves telemetry.
    """
    target_device = request.headers.get("X-Device-Id") or "esp32-nursery-01"
    content_type = request.headers.get("content-type", "")

    try:
        if "multipart/form-data" in content_type:
            form = await request.form()
            file = form.get("file")
            if file is not None and hasattr(file, "read"):
                content = await file.read()
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Missing 'file' in multipart form data"
                )
            if "device_id" in form and form["device_id"]:
                target_device = str(form["device_id"])
        else:
            content = await request.body()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[AUDIO] Failed to read incoming audio payload: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read audio payload: {str(e)}"
        )

    bytes_len = len(content)
    duration_sec = (bytes_len / 2) / 16000.0 if bytes_len > 0 else 0.0
    logger.info(f"[AUDIO RECEIVED] Device: {target_device} | Bytes: {bytes_len} | Estimated Duration: {duration_sec:.2f}s @ 16kHz")

    classifier = YamnetClassifier.get_instance()
    result = classifier.classify_wav_bytes(content)

    if result.get("status") == "UNAVAILABLE":
        logger.warning(f"[AUDIO] Classification unavailable: {result.get('reason')}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("reason", "Invalid audio container")
        )

    classification = result["classification"]
    display_label = result.get("display_label", classification)
    confidence = result["confidence"]

    logger.info(f"[MODEL INFERENCE] Device: {target_device} | Predicted: {display_label} | Confidence: {confidence*100:.0f}%")

    # Record reading in database to update sound metrics
    reading_in = ReadingCreate(
        device_id=target_device,
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
        "device_id": target_device,
        "classification": display_label,
        "code": classification,
        "is_baby_crying": (classification == "BABY_CRYING_DETECTED" or display_label == "BABY CRYING DETECTED"),
        "confidence": confidence,
        "sound_level_db": result["sound_level_db"],
        "top_classes": result.get("top_classes", [])
    }

@router.post("/test-classify", status_code=status.HTTP_200_OK)
async def test_classify_audio(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Interactive test endpoint for browser-based sound verification (microphone or file upload).
    Directly feeds audio to Google YAMNet without requiring device API key.
    Records reading in database so live telemetry and classification cards update immediately.
    """
    target_device = request.headers.get("X-Device-Id") or "dashboard-test-node"
    content_type = request.headers.get("content-type", "")

    try:
        if "multipart/form-data" in content_type:
            form = await request.form()
            file = form.get("file")
            if file is not None and hasattr(file, "read"):
                content = await file.read()
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Missing 'file' in multipart form data"
                )
            if "device_id" in form and form["device_id"]:
                target_device = str(form["device_id"])
        else:
            content = await request.body()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read audio payload: {str(e)}"
        )

    classifier = YamnetClassifier.get_instance()
    result = classifier.classify_wav_bytes(content)

    if result.get("status") == "UNAVAILABLE":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("reason", "Invalid audio container")
        )

    classification = result["classification"]
    confidence = result["confidence"]

    # Record reading in database to update sound metrics
    reading_in = ReadingCreate(
        device_id=target_device,
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
        "device_id": target_device,
        "classification": classification,
        "display_label": result.get("display_label", classification),
        "confidence": confidence,
        "sound_level_db": result["sound_level_db"],
        "top_classes": result.get("top_classes", []),
        "crying_score_raw": result.get("crying_score_raw", 0.0)
    }

