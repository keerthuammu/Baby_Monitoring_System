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
    _latest_authoritative_state: Optional[dict] = None

    @classmethod
    def set_authoritative_state(cls, state: dict):
        cls._latest_authoritative_state = state

    @classmethod
    def get_authoritative_status(cls, db: Session, staleness_seconds: float = 8.0) -> dict:
        now = utc_now()

        # Priority 1: Direct in-memory authoritative state from neural classifier or recent telemetry
        if cls._latest_authoritative_state:
            last_ts = cls._latest_authoritative_state.get("timestamp")
            if isinstance(last_ts, str):
                try:
                    last_ts = datetime.fromisoformat(last_ts)
                except Exception:
                    last_ts = None
            if last_ts:
                last_utc = to_utc(last_ts)
                age = (now - last_utc).total_seconds()
                if age <= staleness_seconds:
                    res = dict(cls._latest_authoritative_state)
                    res["seconds_since_update"] = round(age, 1)
                    res["is_fresh"] = True
                    return res

        # Priority 2: Check active neural classifier state directly
        try:
            from app.audio.yamnet_classifier import YamnetClassifier
            classifier = YamnetClassifier.get_instance()
            yamnet_status = classifier.get_current_status(staleness_seconds=staleness_seconds)
            if yamnet_status.get("is_fresh"):
                raw_code = yamnet_status.get("code", "NOT_BABY_CRYING")
                is_cry = (raw_code == "BABY_CRYING_DETECTED")
                is_unc = (raw_code == "UNCERTAIN")
                std_code = "BABY_CRYING_DETECTED" if is_cry else ("UNCERTAIN" if is_unc else "NOT_BABY_CRYING")
                std_label = "BABY CRYING DETECTED" if is_cry else ("UNCERTAIN" if is_unc else "NOT BABY CRYING")

                res = {
                    "classification": std_label,
                    "code": std_code,
                    "confidence": round(float(yamnet_status.get("confidence", 0.85)), 2),
                    "timestamp": yamnet_status.get("last_update") or now.isoformat(),
                    "reading_id": None,
                    "event_id": None,
                    "is_baby_crying": is_cry,
                    "is_fresh": True,
                    "model_status": "ONLINE",
                    "processing_status": "COMPLETED",
                    "engine": "Google YAMNet ONNX",
                    "source": "yamnet_neural_stream",
                    "sound_intensity": "MODERATE SOUND",
                    "sound_level_db": 55.0,
                    "seconds_since_update": yamnet_status.get("seconds_since_update", 0.0),
                    "top_classes": yamnet_status.get("top_classes", [])
                }
                cls._latest_authoritative_state = res
                return res
        except Exception:
            pass

        # Priority 3: Fallback to latest reading in database within freshness window
        latest_reading = db.query(SensorReading).order_by(desc(SensorReading.recorded_at)).first()
        if latest_reading and latest_reading.recorded_at:
            age = (now - to_utc(latest_reading.recorded_at)).total_seconds()
            if age <= staleness_seconds:
                raw_cls = (latest_reading.classification or "").upper()
                is_cry = "CRYING" in raw_cls
                is_unc = "UNCERTAIN" in raw_cls
                code = "BABY_CRYING_DETECTED" if is_cry else ("UNCERTAIN" if is_unc else "NOT_BABY_CRYING")
                disp = "BABY CRYING DETECTED" if is_cry else ("UNCERTAIN" if is_unc else "NOT BABY CRYING")
                conf = latest_reading.confidence or (0.92 if is_cry else 0.85)
                sound_level = latest_reading.sound_level or 0.0
                intensity = "HIGH SOUND" if sound_level >= 65.0 else ("MODERATE SOUND" if sound_level >= 45.0 else "LOW SOUND")

                state = {
                    "classification": disp,
                    "code": code,
                    "confidence": round(float(conf), 2),
                    "timestamp": latest_reading.recorded_at.isoformat(),
                    "reading_id": latest_reading.id,
                    "event_id": None,
                    "is_baby_crying": is_cry,
                    "is_fresh": True,
                    "model_status": "ONLINE",
                    "processing_status": "COMPLETED",
                    "engine": "Acoustic Telemetry Stream",
                    "source": "sensor_reading",
                    "sound_intensity": intensity,
                    "sound_level_db": sound_level,
                    "seconds_since_update": round(age, 1),
                    "top_classes": []
                }
                cls._latest_authoritative_state = state
                return state

        # Guard: If no fresh audio or telemetry arrived in the last staleness_seconds -> STRICTLY AUDIO UNAVAILABLE
        return {
            "classification": "AUDIO UNAVAILABLE",
            "code": "AUDIO_UNAVAILABLE",
            "confidence": 0.0,
            "timestamp": now.isoformat(),
            "reading_id": None,
            "event_id": None,
            "is_baby_crying": False,
            "is_fresh": False,
            "model_status": "AWAITING_STREAM",
            "processing_status": "UNAVAILABLE",
            "engine": "Offline / Awaiting Stream",
            "source": "freshness_guard",
            "sound_intensity": "OFFLINE",
            "sound_level_db": 0.0,
            "seconds_since_update": round(staleness_seconds + 1.0, 1),
            "top_classes": []
        }

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
        # Secondary authority: Verified infant cry pitch & edge episode latch
        is_yamnet_crying = (classification == "BABY_CRYING_DETECTED")
        is_yamnet_non_crying = (classification is not None and classification != "BABY_CRYING_DETECTED")

        # Edge crying is valid when:
        # 1. Edge explicitly flags crying episode (autocorrelation latch e.g. "POSSIBLE_CRYING"), OR
        # 2. Pitch is within the infant distress vocal frequency range (350 - 720 Hz) with elevated sound
        is_edge_crying = (
            not is_yamnet_non_crying and (
                ("CRYING" in detected_class and reading_in.sound_level >= 45.0) or
                (350.0 <= pitch <= 720.0 and reading_in.sound_level >= 48.0)
            )
        )
        is_high_sound = reading_in.sound_level >= settings.SOUND_HIGH_THRESHOLD

        final_reading_class = None
        final_reading_conf = detected_conf

        ev = None
        if is_yamnet_crying or is_edge_crying:
            final_reading_class = "BABY_CRYING_DETECTED"
            final_reading_conf = detected_conf if detected_conf is not None else 0.92
            event_class = "POSSIBLE_CRYING"
            ev = MonitorService._handle_elevated_sound_event(db, reading_in.device_id, now, event_class, final_reading_conf)
        elif "UNCERTAIN" in detected_class:
            final_reading_class = "UNCERTAIN"
            final_reading_conf = detected_conf if detected_conf is not None else 0.70
        else:
            # Sound intensity is decoupled from baby sound classification:
            # A loud door slam / loud noise (>= 65 dB) is HIGH SOUND, but NOT BABY CRYING
            final_reading_class = "NOT_BABY_CRYING"
            final_reading_conf = detected_conf if detected_conf is not None else 0.88
            if is_high_sound:
                event_class = "HIGH_SOUND_ACTIVITY"
                ev = MonitorService._handle_elevated_sound_event(db, reading_in.device_id, now, event_class, final_reading_conf)

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

        # Synchronize single authoritative classification state
        is_cry = (final_reading_class in ["BABY_CRYING_DETECTED", "POSSIBLE_CRYING"])
        is_unc = (final_reading_class == "UNCERTAIN")
        std_code = "BABY_CRYING_DETECTED" if is_cry else ("UNCERTAIN" if is_unc else "NOT_BABY_CRYING")
        std_label = "BABY CRYING DETECTED" if is_cry else ("UNCERTAIN" if is_unc else "NOT BABY CRYING")
        sound_level = reading.sound_level
        intensity = "HIGH SOUND" if sound_level >= 65.0 else ("MODERATE SOUND" if sound_level >= 45.0 else "LOW SOUND")

        auth_state = {
            "classification": std_label,
            "code": std_code,
            "confidence": round(float(final_reading_conf or 0.85), 2),
            "timestamp": recorded_at.isoformat(),
            "reading_id": reading.id,
            "event_id": ev.id if ev else None,
            "is_baby_crying": is_cry,
            "is_fresh": True,
            "model_status": "ONLINE",
            "processing_status": "COMPLETED",
            "engine": "Google YAMNet ONNX" if classification == "BABY_CRYING_DETECTED" else "Acoustic Telemetry Stream",
            "source": "live_ingestion",
            "sound_intensity": intensity,
            "sound_level_db": sound_level,
            "seconds_since_update": 0.0,
            "top_classes": []
        }
        MonitorService.set_authoritative_state(auth_state)

        return reading

    @staticmethod
    def _handle_elevated_sound_event(
        db: Session, 
        device_id: str, 
        current_time: datetime,
        classification: str = "HIGH_SOUND_ACTIVITY",
        confidence: float = 0.85
    ) -> Optional[CryingEvent]:
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
            return active_event
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
            return new_event

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

        # Seamless normalization: map every reading to authoritative standard states
        min_time = min((r.recorded_at for r in readings if r.recorded_at), default=None)
        max_time = max((r.recorded_at for r in readings if r.recorded_at), default=None)
        crying_events = []
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
            raw_c = (r.classification or "").upper()
            if "CRYING" in raw_c:
                r.classification = "BABY_CRYING_DETECTED"
            elif "UNCERTAIN" in raw_c:
                r.classification = "UNCERTAIN"
            else:
                # Check if reading falls within an active/recorded crying incident window
                is_during_cry = False
                if r.recorded_at and crying_events:
                    r_utc = to_utc(r.recorded_at)
                    for ev in crying_events:
                        ev_start = to_utc(ev.start_time) - timedelta(seconds=3)
                        ev_end = to_utc(ev.end_time or ev.start_time) + timedelta(seconds=max(3.0, (ev.duration_seconds or 0.0) + 3.0))
                        if ev_start <= r_utc <= ev_end and (r.sound_level or 0.0) >= 45.0:
                            r.classification = "BABY_CRYING_DETECTED"
                            r.confidence = ev.confidence or 0.92
                            is_during_cry = True
                            break
                if not is_during_cry:
                    r.classification = "NOT_BABY_CRYING"
                    if not r.confidence:
                        r.confidence = 0.88
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
