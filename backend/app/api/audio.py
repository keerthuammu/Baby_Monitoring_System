import io
import wave
import numpy as np
from typing import Optional
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import verify_device_api_key
from app.audio.classifier import AcousticClassifier
from app.services.monitor_service import MonitorService
from app.schemas.schemas import ReadingCreate

router = APIRouter(prefix="/api/audio", tags=["Audio Classification"])

@router.post("/classify", status_code=status.HTTP_200_OK)
async def classify_audio_sample(
    file: UploadFile = File(..., description="Audio file in WAV format (mono, 16-bit PCM, 16kHz recommended)"),
    device_id: str = Form("esp32-nursery-01"),
    db: Session = Depends(get_db),
    _auth: bool = Depends(verify_device_api_key)
):
    """
    Ingests and classifies an audio sample chunk.
    Extracts acoustic features (F0 Pitch, RMS, Spectral Cry Band Ratio)
    and determines whether the sound is Quiet, High Noise, or Possible Infant Crying.
    
    Privacy Protection:
    The raw audio file is processed in memory and discarded immediately
    without permanent disk retention.
    """
    try:
        content = await file.read()
        
        # Read WAV container
        with wave.open(io.BytesIO(content), "rb") as wav:
            n_channels = wav.getnchannels()
            sample_width = wav.getsampwidth()
            framerate = wav.getframerate()
            n_frames = wav.getnframes()
            
            raw_data = wav.readframes(n_frames)
            
            # Convert to numpy array
            if sample_width == 2:
                signal = np.frombuffer(raw_data, dtype=np.int16)
            elif sample_width == 4:
                signal = np.frombuffer(raw_data, dtype=np.int32)
            else:
                signal = np.frombuffer(raw_data, dtype=np.int8)

            # If stereo, convert to mono
            if n_channels > 1:
                signal = signal.reshape(-1, n_channels).mean(axis=1)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to decode audio file. Ensure it is a valid WAV audio file: {str(e)}"
        )

    # Classify waveform
    result = AcousticClassifier.classify_waveform(signal, sample_rate=framerate)
    features = result["features"]
    classification = result["classification"]
    confidence = result["confidence"]

    # Log reading and handle alert in database
    reading_in = ReadingCreate(
        device_id=device_id,
        sound_level=features["sound_level_db"],
        rms_amplitude=features["rms"],
        peak_amplitude=features["peak_amplitude"]
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
        "features": features
    }
