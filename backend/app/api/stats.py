from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.schemas.schemas import StatsResponse, DeviceResponse
from app.services.monitor_service import MonitorService

router = APIRouter(prefix="/api", tags=["Monitoring & Devices"])

@router.get("/stats", response_model=StatsResponse)
def get_dashboard_stats(db: Session = Depends(get_db)):
    """Returns aggregated monitoring statistics for the frontend dashboard."""
    stats = MonitorService.get_stats(db)
    return stats

@router.get("/devices", response_model=List[DeviceResponse])
def list_devices(db: Session = Depends(get_db)):
    """Returns registered monitoring devices and their current status."""
    devices = MonitorService.get_devices(db)
    return devices
