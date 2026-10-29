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

@router.get("/status", status_code=status.HTTP_200_OK)
def get_audio_classification_status(db: Session = Depends(get_db)):
    """
    Returns the real-time audio sound classification and confidence.
    1. Returns YAMNet neural classification if live raw audio is streamed.
    2. Gracefully falls back to real-time acoustic telemetry classification
       (dB, RMS, active events) if the IoT device is online.
    3. Returns unavailable/offline if no telemetry or audio is active.
    """
    classifier = YamnetClassifier.get_instance()
    status_data = classifier.get_current_status(staleness_seconds=10.0)

    # If raw neural audio classification is fresh, return it
    if status_data.get("is_fresh"):
        status_data["engine"] = "Local YAMNet"
        return status_data

    # Telemetry-based Acoustic Classifier fallback
    devices = MonitorService.get_devices(db)
    is_online = any(d.connection_status == "ONLINE" for d in devices)
    latest_reading = MonitorService.get_latest_reading(db)
    latest_event = db.query(CryingEvent).order_by(desc(CryingEvent.start_time)).first()

    if is_online and latest_reading:
        now = datetime.now(timezone.utc)
        reading_time = to_utc(latest_reading.recorded_at) or now
        time_diff = (now - reading_time).total_seconds()

        # Reading within reasonable window (e.g. 15s)
        if time_diff <= 15.0:
            has_active_event = (
                latest_event is not None and (
                    not latest_event.acknowledged or 
                    (now - to_utc(latest_event.end_time or latest_event.start_time)).total_seconds() < 15.0
                )
            )

            if has_active_event and latest_event.classification == "POSSIBLE_CRYING":
                classification = "Possible Baby Crying"
                confidence = round(latest_event.confidence or 0.85, 2)
            elif has_active_event or latest_reading.sound_level >= 65.0:
                classification = "High Sound Activity"
                confidence = round(latest_event.confidence if has_active_event else 0.85, 2)
            elif latest_reading.sound_level >= 45.0:
                classification = "Moderate Sound"
                confidence = 0.75
            else:
                classification = "Quiet / Ambient"
                confidence = 0.95

            return {
                "classification": classification,
                "confidence": confidence,
                "status": "ACTIVE",
                "is_fresh": True,
                "engine": "Acoustic Classifier",
                "source": "telemetry",
                "seconds_since_update": round(time_diff, 1),
                "last_update": reading_time.isoformat(),
                "sound_level_db": latest_reading.sound_level,
                "top_classes": [
                    {"class_name": classification, "score": confidence}
                ]
            }

    return status_data

@router.post("/classify", status_code=status.HTTP_200_OK)
async def classify_audio_sample(
    request: Request,
    db: Session = Depends(get_db),
    _auth: bool = Depends(verify_device_api_key)
):
    """
    Ingests and classifies an audio sample chunk locally using Google YAMNet ONNX.
    Supports both multipart form upload and direct raw WAV/PCM streaming.
    Differentiates between:
    - 'Possible Baby Crying'
    - 'Other Sound'
    - 'Uncertain'
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
        "confidence": confidence,
        "sound_level_db": result["sound_level_db"],
        "top_classes": result.get("top_classes", [])
    }

