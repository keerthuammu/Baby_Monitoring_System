from datetime import datetime, timezone, timedelta
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from app.models.models import Device, SensorReading, CryingEvent
from app.schemas.schemas import ReadingCreate
from app.core.config import settings

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

def to_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Ensures a datetime is timezone-aware in UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

class MonitorService:
    @staticmethod
    def get_or_create_device(db: Session, device_id: str, device_name: str = "ESP32 Baby Monitor") -> Device:
        device = db.query(Device).filter(Device.device_id == device_id).first()
        now = utc_now()
        if not device:
            device = Device(
                device_id=device_id,
                device_name=device_name,
                created_at=now,
                last_seen_at=now,
                connection_status="ONLINE"
            )
            db.add(device)
            db.commit()
            db.refresh(device)
        else:
            device.last_seen_at = now
            device.connection_status = "ONLINE"
            db.commit()
        return device

    @staticmethod
    def record_reading(db: Session, reading_in: ReadingCreate) -> SensorReading:
        now = utc_now()
        recorded_at = reading_in.recorded_at or now

        # Ensure device exists and update its heartbeat
        MonitorService.get_or_create_device(db, reading_in.device_id)

        # Create reading
        reading = SensorReading(
            device_id=reading_in.device_id,
            sound_level=reading_in.sound_level,
            rms_amplitude=reading_in.rms_amplitude,
            peak_amplitude=reading_in.peak_amplitude,
            recorded_at=recorded_at,
            received_at=now
        )
        db.add(reading)

        # Acoustic Event Handling
        # Check if reading exceeds high sound threshold
        if reading_in.sound_level >= settings.SOUND_HIGH_THRESHOLD:
            MonitorService._handle_elevated_sound_event(db, reading_in.device_id, now)

        db.commit()
        db.refresh(reading)
        return reading

    @staticmethod
    def _handle_elevated_sound_event(db: Session, device_id: str, current_time: datetime):
        """
        Groups continuous loud sound into an ongoing event (debouncing)
        rather than creating hundreds of duplicate event rows.
        """
        recent_threshold = current_time - timedelta(seconds=10)
        active_event = (
            db.query(CryingEvent)
            .filter(
                CryingEvent.device_id == device_id,
                CryingEvent.end_time >= recent_threshold
            )
            .order_by(desc(CryingEvent.start_time))
            .first()
        )

        if active_event:
            # Update existing event duration
            active_event.end_time = current_time
            start = to_utc(active_event.start_time)
            curr = to_utc(current_time)
            if start and curr:
                active_event.duration_seconds = max(1.0, (curr - start).total_seconds())
        else:
            # Create a new event
            new_event = CryingEvent(
                device_id=device_id,
                start_time=current_time,
                end_time=current_time,
                duration_seconds=1.0,
                classification="HIGH_SOUND_ACTIVITY",
                confidence=0.85,
                acknowledged=False,
                created_at=current_time
            )
            db.add(new_event)

    @staticmethod
    def get_latest_reading(db: Session, device_id: Optional[str] = None) -> Optional[SensorReading]:
        query = db.query(SensorReading)
        if device_id:
            query = query.filter(SensorReading.device_id == device_id)
        return query.order_by(desc(SensorReading.recorded_at)).first()

    @staticmethod
    def get_readings(db: Session, device_id: Optional[str] = None, limit: int = 50, offset: int = 0) -> List[SensorReading]:
        query = db.query(SensorReading)
        if device_id:
            query = query.filter(SensorReading.device_id == device_id)
        return query.order_by(desc(SensorReading.recorded_at)).offset(offset).limit(limit).all()

    @staticmethod
    def get_events(db: Session, device_id: Optional[str] = None, limit: int = 20, offset: int = 0, unack_only: bool = False) -> List[CryingEvent]:
        query = db.query(CryingEvent)
        if device_id:
            query = query.filter(CryingEvent.device_id == device_id)
        if unack_only:
            query = query.filter(CryingEvent.acknowledged == False)
        return query.order_by(desc(CryingEvent.start_time)).offset(offset).limit(limit).all()

    @staticmethod
    def acknowledge_event(db: Session, event_id: int) -> Optional[CryingEvent]:
        event = db.query(CryingEvent).filter(CryingEvent.id == event_id).first()
        if event:
            event.acknowledged = True
            db.commit()
            db.refresh(event)
        return event

    @staticmethod
    def get_devices(db: Session) -> List[Device]:
        now = utc_now()
        devices = db.query(Device).all()
        # Mark as OFFLINE if no heartbeat in last 15 seconds
        for d in devices:
            last_seen = to_utc(d.last_seen_at)
            if last_seen and (now - last_seen).total_seconds() > 15:
                if d.connection_status != "OFFLINE":
                    d.connection_status = "OFFLINE"
                    db.commit()
        return devices

    @staticmethod
    def get_stats(db: Session) -> dict:
        total_readings = db.query(func.count(SensorReading.id)).scalar() or 0
        total_events = db.query(func.count(CryingEvent.id)).scalar() or 0
        unack_events = db.query(func.count(CryingEvent.id)).filter(CryingEvent.acknowledged == False).scalar() or 0
        latest_reading = MonitorService.get_latest_reading(db)
        latest_event = db.query(CryingEvent).order_by(desc(CryingEvent.start_time)).first()
        
        devices = MonitorService.get_devices(db)
        active_devices = [d for d in devices if d.connection_status == "ONLINE"]
        status_str = "ONLINE" if active_devices else "OFFLINE"

        return {
            "total_readings": total_readings,
            "total_events": total_events,
            "unacknowledged_events": unack_events,
            "latest_reading": latest_reading,
            "active_device_count": len(active_devices),
            "device_status": status_str,
            "latest_event": latest_event
        }
