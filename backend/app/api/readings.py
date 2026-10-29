from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import verify_device_api_key
from app.schemas.schemas import ReadingCreate, ReadingResponse
from app.services.monitor_service import MonitorService

router = APIRouter(prefix="/api/readings", tags=["Readings"])

@router.post("", response_model=ReadingResponse, status_code=status.HTTP_201_CREATED)
def submit_reading(
    reading_in: ReadingCreate,
    db: Session = Depends(get_db),
    _authorized: bool = Depends(verify_device_api_key)
):
    """
    Accepts sound-feature readings from the ESP32 IoT node.
    Supports on-device edge classification (POSSIBLE_CRYING, HIGH_SOUND_ACTIVITY, pitch_hz).
    Requires X-API-Key header.
    """
    reading = MonitorService.record_reading(
        db,
        reading_in,
        classification=reading_in.classification,
        confidence=reading_in.confidence
    )
    return reading

@router.get("/latest", response_model=Optional[ReadingResponse])
def get_latest_reading(
    device_id: Optional[str] = Query(None, description="Optional device filter"),
    db: Session = Depends(get_db)
):
    """Fetches the most recent acoustic reading."""
    reading = MonitorService.get_latest_reading(db, device_id)
    return reading

@router.get("", response_model=List[ReadingResponse])
def list_readings(
    device_id: Optional[str] = Query(None, description="Optional device filter"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """Fetches paginated historical readings."""
    readings = MonitorService.get_readings(db, device_id=device_id, limit=limit, offset=offset)
    return readings
