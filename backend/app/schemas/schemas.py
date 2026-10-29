from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field

# --- Device Schemas ---
class DeviceBase(BaseModel):
    device_id: str = Field(..., max_length=64, description="Unique hardware identifier")
    device_name: Optional[str] = Field("ESP32 Baby Monitor", max_length=128)

class DeviceResponse(DeviceBase):
    id: int
    created_at: datetime
    last_seen_at: datetime
    connection_status: str

    model_config = {"from_attributes": True}


# --- Reading Schemas ---
class ReadingCreate(BaseModel):
    device_id: str = Field(..., max_length=64, description="Unique device ID")
    sound_level: float = Field(..., ge=0.0, le=140.0, description="Calculated sound level in dB")
    rms_amplitude: float = Field(..., ge=0.0, description="Root-mean-square amplitude")
    peak_amplitude: int = Field(..., ge=0, description="Maximum sample value")
    recorded_at: Optional[datetime] = Field(None, description="Client timestamp, defaults to server reception time")
    classification: Optional[str] = Field(None, description="Edge/device classification e.g. POSSIBLE_CRYING, HIGH_SOUND_ACTIVITY")
    pitch_hz: Optional[float] = Field(None, description="Estimated fundamental pitch in Hz")
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="Confidence score 0.0 to 1.0")

class ReadingResponse(BaseModel):
    id: int
    device_id: str
    sound_level: float
    rms_amplitude: float
    peak_amplitude: int
    recorded_at: datetime
    received_at: datetime

    model_config = {"from_attributes": True}


# --- Event Schemas ---
class EventResponse(BaseModel):
    id: int
    device_id: str
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_seconds: float
    classification: str
    confidence: float
    acknowledged: bool
    created_at: datetime

    model_config = {"from_attributes": True}

class EventAcknowledge(BaseModel):
    acknowledged: bool = True


# --- Stats & Overview Schemas ---
class StatsResponse(BaseModel):
    total_readings: int
    total_events: int
    unacknowledged_events: int
    latest_reading: Optional[ReadingResponse] = None
    active_device_count: int
    device_status: str  # "ONLINE", "OFFLINE"
    latest_event: Optional[EventResponse] = None


# --- Health Schema ---
class HealthResponse(BaseModel):
    status: str
    database: str
    timestamp: datetime
    version: str
