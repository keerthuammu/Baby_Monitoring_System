from datetime import datetime, timezone
from sqlalchemy import Column, Integer, BigInteger, String, Float, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from app.core.database import Base

def utc_now():
    return datetime.now(timezone.utc)

class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer().with_variant(BigInteger, "postgresql"), primary_key=True, index=True, autoincrement=True)
    device_id = Column(String(64), unique=True, index=True, nullable=False)
    device_name = Column(String(128), default="ESP32 Baby Monitor")
    created_at = Column(DateTime(timezone=True), default=utc_now)
    last_seen_at = Column(DateTime(timezone=True), default=utc_now)
    connection_status = Column(String(20), default="ONLINE")  # ONLINE, OFFLINE

    # Relationships
    readings = relationship("SensorReading", back_populates="device", cascade="all, delete-orphan")
    events = relationship("CryingEvent", back_populates="device", cascade="all, delete-orphan")
    environment_readings = relationship("RoomEnvironment", back_populates="device", cascade="all, delete-orphan")


class SensorReading(Base):
    __tablename__ = "sensor_readings"

    id = Column(Integer().with_variant(BigInteger, "postgresql"), primary_key=True, index=True, autoincrement=True)
    device_id = Column(String(64), ForeignKey("devices.device_id", ondelete="CASCADE"), index=True, nullable=False)
    sound_level = Column(Float, nullable=False)          # dB score
    rms_amplitude = Column(Float, nullable=False)        # Root-mean-square amplitude
    peak_amplitude = Column(Integer, nullable=False)      # Peak sample value
    recorded_at = Column(DateTime(timezone=True), default=utc_now, index=True)
    received_at = Column(DateTime(timezone=True), default=utc_now)

    device = relationship("Device", back_populates="readings")

    __table_args__ = (
        Index("idx_reading_device_time", "device_id", "recorded_at"),
    )


class CryingEvent(Base):
    __tablename__ = "crying_events"

    id = Column(Integer().with_variant(BigInteger, "postgresql"), primary_key=True, index=True, autoincrement=True)
    device_id = Column(String(64), ForeignKey("devices.device_id", ondelete="CASCADE"), index=True, nullable=False)
    start_time = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=True)
    duration_seconds = Column(Float, default=0.0)
    classification = Column(String(50), nullable=False)   # POSSIBLE_CRYING, HIGH_SOUND_ACTIVITY, UNCERTAIN
    confidence = Column(Float, default=0.0)               # 0.0 to 1.0
    acknowledged = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now)

    device = relationship("Device", back_populates="events")

    __table_args__ = (
        Index("idx_event_device_start", "device_id", "start_time"),
    )


class RoomEnvironment(Base):
    __tablename__ = "room_environment"

    id = Column(Integer().with_variant(BigInteger, "postgresql"), primary_key=True, index=True, autoincrement=True)
    device_id = Column(String(64), ForeignKey("devices.device_id", ondelete="CASCADE"), index=True, nullable=False)
    temperature = Column(Float, nullable=False)           # Celsius
    humidity = Column(Float, nullable=False)              # Percentage
    recorded_at = Column(DateTime(timezone=True), default=utc_now)

    device = relationship("Device", back_populates="environment_readings")
