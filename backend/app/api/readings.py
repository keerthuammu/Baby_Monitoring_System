from typing import List, Optional
from fastapi import APIRouter, Depends, Query, Request, status, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.config import settings
from app.core.security import verify_device_api_key
from app.schemas.schemas import ReadingCreate, ReadingResponse
from app.services.monitor_service import MonitorService
from app.services.cloud_sync import forward_reading_to_cloud

router = APIRouter(prefix="/api/readings", tags=["Readings"])

@router.post("", response_model=ReadingResponse, status_code=status.HTTP_201_CREATED)
def submit_reading(
    reading_in: ReadingCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _authorized: bool = Depends(verify_device_api_key)
):
    """
    Accepts sound-feature readings from the ESP32 IoT node.
    Supports on-device edge classification (POSSIBLE_CRYING, HIGH_SOUND_ACTIVITY, pitch_hz).
    Requires X-API-Key header.
    Mirrors reading to Render cloud backend in background when running locally.
    Enforces DEMO_MODE guard against simulated data injection in production.
    """
    # Guard: Require valid non-empty device_id
    if not reading_in.device_id or len(reading_in.device_id.strip()) < 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid reading: 'device_id' is required and must be at least 3 characters"
        )

    # Guard: Reject mock/simulated data unless DEMO_MODE is explicitly enabled
    is_simulation = (
        reading_in.source == "demo" or 
        "simulat" in reading_in.device_id.lower() or 
        reading_in.device_id == "esp32-devkit-v1-simulated"
    )
    if is_simulation and not getattr(settings, "DEMO_MODE", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Simulation data rejected: DEMO_MODE is disabled on this server. Set DEMO_MODE=true in environment to permit mock hardware data."
        )

    reading = MonitorService.record_reading(
        db,
        reading_in,
        source="demo" if is_simulation else (reading_in.source or "esp32_device")
    )

    # Prevent loop: only mirror if request did NOT originate from another bridge forwarder
    if not request.headers.get("X-Forwarded-From-Local"):
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
