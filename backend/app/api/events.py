from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.schemas.schemas import EventResponse, EventAcknowledge
from app.services.monitor_service import MonitorService

router = APIRouter(prefix="/api/events", tags=["Events"])

@router.get("", response_model=List[EventResponse])
def list_events(
    device_id: Optional[str] = Query(None, description="Optional device filter"),
    unacknowledged_only: bool = Query(False, description="Filter unacknowledged events only"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """Returns detected or suspected sound/crying events."""
    events = MonitorService.get_events(
        db,
        device_id=device_id,
        limit=limit,
        offset=offset,
        unack_only=unacknowledged_only
    )
    return events

@router.patch("/{event_id}/acknowledge", response_model=EventResponse)
def acknowledge_event(
    event_id: int,
    db: Session = Depends(get_db)
):
    """Allows caregiver to acknowledge or dismiss an alert."""
    event = MonitorService.acknowledge_event(db, event_id)
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Event with id {event_id} not found"
        )
    return event
