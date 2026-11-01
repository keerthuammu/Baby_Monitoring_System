from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status, BackgroundTasks
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import verify_device_api_key
from app.schemas.schemas import ReadingCreate, ReadingResponse
from app.services.monitor_service import MonitorService
from app.services.cloud_sync import forward_reading_to_cloud

router = APIRouter(prefix="/api/readings", tags=["Readings"])

@router.post("", response_model=ReadingResponse, status_code=status.HTTP_201_CREATED)
def submit_reading(
    reading_in: ReadingCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _authorized: bool = Depends(verify_device_api_key)
):
    """
    Accepts sound-feature readings from the ESP32 IoT node.
    Supports on-device edge classification (POSSIBLE_CRYING, HIGH_SOUND_ACTIVITY, pitch_hz).
    Requires X-API-Key header.
    Mirrors reading to Render cloud backend in background.
    """
    reading = MonitorService.record_reading(
        db,
        reading_in
    )

    # Asynchronously mirror telemetry to Render without blocking ESP32 response
    payload = reading_in.model_dump(mode="json")
    background_tasks.add_task(forward_reading_to_cloud, payload)

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
