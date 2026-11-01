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
    def record_reading(
        db: Session, 
        reading_in: ReadingCreate,
        classification: Optional[str] = None,
        confidence: Optional[float] = None
    ) -> SensorReading:
        now = utc_now()
        recorded_at = reading_in.recorded_at or now

        # Ensure device exists and update its heartbeat
        MonitorService.get_or_create_device(db, reading_in.device_id)

        # Acoustic Event Handling
        detected_class = (classification or reading_in.classification or "").upper()
        detected_conf = confidence if confidence is not None else reading_in.confidence
        pitch = getattr(reading_in, "pitch_hz", None) or 0.0

        # Primary authority: YAMNet neural network inference (if provided)
        # Secondary authority: Verified infant cry pitch (380 - 680 Hz) explicitly flagged as crying by edge device
        is_yamnet_crying = (classification == "BABY_CRYING_DETECTED")
        is_yamnet_non_crying = (classification is not None and classification != "BABY_CRYING_DETECTED")

        # Edge crying is only accepted if YAMNet didn't classify it as non-crying,
        # AND edge classification explicitly claims POSSIBLE_CRYING,
        # AND pitch is strictly in the true infant distress vocal band (380 - 680 Hz),
        # AND sound level is elevated (>= 52 dB).
        is_edge_crying = (
            not is_yamnet_non_crying and
            ("CRYING" in detected_class) and
            (380.0 <= pitch <= 680.0) and
            (reading_in.sound_level >= 52.0)
        )
        is_high_sound = reading_in.sound_level >= settings.SOUND_HIGH_THRESHOLD

        final_reading_class = None
        final_reading_conf = detected_conf

        if is_yamnet_crying:
            final_reading_class = "BABY_CRYING_DETECTED"
            final_reading_conf = detected_conf if detected_conf is not None else 0.96
            event_class = "POSSIBLE_CRYING"
            MonitorService._handle_elevated_sound_event(db, reading_in.device_id, now, event_class, final_reading_conf)
        elif is_edge_crying:
            final_reading_class = "POSSIBLE_CRYING"
            final_reading_conf = detected_conf if detected_conf is not None else 0.90
            event_class = "POSSIBLE_CRYING"
            MonitorService._handle_elevated_sound_event(db, reading_in.device_id, now, event_class, final_reading_conf)
        elif is_high_sound:
            final_reading_class = "HIGH_SOUND_ACTIVITY"
            final_reading_conf = detected_conf if detected_conf is not None else 0.85
            event_class = "HIGH_SOUND_ACTIVITY"
            MonitorService._handle_elevated_sound_event(db, reading_in.device_id, now, event_class, final_reading_conf)
        else:
            final_reading_class = detected_class or "NORMAL"

        # Create reading with persistent classification
        reading = SensorReading(
            device_id=reading_in.device_id,
            sound_level=reading_in.sound_level,
            rms_amplitude=reading_in.rms_amplitude,
            peak_amplitude=reading_in.peak_amplitude,
            classification=final_reading_class,
            confidence=final_reading_conf,
            recorded_at=recorded_at,
            received_at=now
        )
        db.add(reading)

        db.commit()
        db.refresh(reading)
        return reading

    @staticmethod
    def _handle_elevated_sound_event(
        db: Session, 
        device_id: str, 
        current_time: datetime,
        classification: str = "HIGH_SOUND_ACTIVITY",
        confidence: float = 0.85
    ):
        """
        Groups continuous loud sound into an ongoing event (debouncing)
        rather than creating hundreds of duplicate event rows.
        Upgrades event to POSSIBLE_CRYING if infant vocalization is detected.
        """
        recent_threshold = current_time - timedelta(seconds=10)
        # Check for ANY active ongoing event for this device (within 10s)
        active_event = (
            db.query(CryingEvent)
            .filter(
                CryingEvent.device_id == device_id,
                CryingEvent.end_time >= recent_threshold,
                CryingEvent.acknowledged == False
            )
            .order_by(desc(CryingEvent.end_time))
            .first()
        )

        if active_event:
            # If active event is already crying, preserve crying classification across brief pauses
            if active_event.classification == "POSSIBLE_CRYING":
                active_event.end_time = current_time
                active_event.confidence = max(active_event.confidence, confidence)
            elif classification == "POSSIBLE_CRYING":
                # Upgrade existing HIGH_SOUND_ACTIVITY to confirmed infant crying!
                active_event.classification = "POSSIBLE_CRYING"
                active_event.end_time = current_time
                active_event.confidence = max(active_event.confidence, confidence)
            else:
                # Both are HIGH_SOUND_ACTIVITY: extend duration
                active_event.end_time = current_time
                active_event.confidence = max(active_event.confidence, confidence)

            start = to_utc(active_event.start_time)
            curr = to_utc(current_time)
            if start and curr:
                active_event.duration_seconds = max(1.0, (curr - start).total_seconds())
        else:
            # Create a separate new event
            new_event = CryingEvent(
                device_id=device_id,
                start_time=current_time,
                end_time=current_time,
                duration_seconds=1.0,
                classification=classification,
                confidence=confidence,
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
        readings = query.order_by(desc(SensorReading.recorded_at)).offset(offset).limit(limit).all()

        # Seamless fallback: backfill unclassified historical packets matching active/recorded crying events
        has_unclassified = any(r.classification is None for r in readings)
        if has_unclassified and readings:
            min_time = min((r.recorded_at for r in readings if r.recorded_at), default=None)
            max_time = max((r.recorded_at for r in readings if r.recorded_at), default=None)
            if min_time and max_time:
                crying_events = (
                    db.query(CryingEvent)
                    .filter(
                        CryingEvent.classification.ilike("%CRYING%"),
                        CryingEvent.start_time <= max_time + timedelta(seconds=5),
                    )
                    .all()
                )
                for r in readings:
                    if r.classification is None and r.recorded_at:
                        r_utc = to_utc(r.recorded_at)
                        for ev in crying_events:
                            ev_start = to_utc(ev.start_time) - timedelta(seconds=3)
                            ev_end = to_utc(ev.end_time or ev.start_time) + timedelta(seconds=max(3.0, (ev.duration_seconds or 0.0) + 3.0))
                            if ev_start <= r_utc <= ev_end and r.sound_level >= 45.0:
                                r.classification = "POSSIBLE_CRYING"
                                r.confidence = ev.confidence or 0.90
                                break
        return readings

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
        # Mark as OFFLINE if no heartbeat in last 10 seconds
        for d in devices:
            last_seen = to_utc(d.last_seen_at)
            if last_seen and (now - last_seen).total_seconds() > 10:
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
        
        now = utc_now()
        devices = MonitorService.get_devices(db)
        active_devices = [d for d in devices if d.connection_status == "ONLINE"]

        # Also check if latest sensor reading arrived within last 10 seconds
        is_fresh_reading = False
        if latest_reading:
            reading_time = to_utc(latest_reading.received_at or latest_reading.recorded_at)
            if reading_time and (now - reading_time).total_seconds() <= 10:
                is_fresh_reading = True

        status_str = "ONLINE" if (active_devices or is_fresh_reading) else "OFFLINE"

        return {
            "total_readings": total_readings,
            "total_events": total_events,
            "unacknowledged_events": unack_events,
            "latest_reading": latest_reading,
            "active_device_count": len(active_devices) if active_devices else (1 if is_fresh_reading else 0),
            "device_status": status_str,
            "latest_event": latest_event
        }
