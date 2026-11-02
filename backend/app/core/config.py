import os
from typing import List, Union
from pydantic_settings import BaseSettings
from pydantic import field_validator

class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    BACKEND_HOST: str = "0.0.0.0"
    BACKEND_PORT: int = 8000
    SECRET_KEY: str = "default_secret_key"
    API_KEY: str = "baby_monitor_device_secret_key_123"
    
    # Database
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/baby_monitor_db"
    
    # CORS
    CORS_ORIGINS: Union[str, List[str]] = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000"
    
    # Thresholds
    SOUND_HIGH_THRESHOLD: float = 65.0
    CRYING_CONFIDENCE_THRESHOLD: float = 0.70
    AUDIO_RETENTION_DAYS: int = 7
    
    # Acoustic & Temporal Decision Thresholds (Precision-Calibrated)
    CRY_SCORE_CONFIRMED_THRESHOLD: float = 0.35  # YAMNet cry score for confirmed cry
    CRY_SCORE_UNCERTAIN_THRESHOLD: float = 0.18  # Lower bound for UNCERTAIN state
    CRY_SCORE_MARGIN: float = 0.05               # Cry score must exceed dominant negative class by this margin
    CRY_TOP_N_REQUIRED: int = 4                  # Crying class must be in top-N predictions
    
    # Adaptive Noise Floor & Gate
    ADAPTIVE_NOISE_FLOOR_MARGIN_DB: float = 8.0  # Must be at least 8 dB above rolling noise floor
    NOISE_FLOOR_ALPHA: float = 0.05              # Exponential moving average smoothing factor
    
    # Transient / Impulse Veto (Claps, Door Slams, Knocks)
    CREST_FACTOR_IMPULSE_THRESHOLD: float = 14.5 # dB: Peak-to-RMS ratio above 14.5 dB flags transient impulse
    
    # Temporal Multi-Window Voting & Hysteresis
    CRY_WINDOW_VOTES_REQUIRED: int = 2           # Require at least 2 cry windows
    CRY_WINDOW_VOTES_TOTAL: int = 3              # Out of the last 3 windows
    CRY_PAUSE_BRIDGE_SECONDS: float = 4.0        # Max breath pause bridge duration (seconds)
    
    # Edge Pitch Telemetry & Freshness
    ENABLE_PITCH_CONFIDENCE_BOOST: bool = True   # Edge pitch can add confidence, but never triggers cry alone
    AUDIO_STALENESS_SECONDS: float = 8.0
    
    # Cloud Synchronization
    ENABLE_CLOUD_FORWARDING: bool = True
    CLOUD_BACKEND_URL: str = "https://baby-monitor-backend-8m8o.onrender.com"

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def fix_postgres_scheme(cls, v: str) -> str:
        if v and v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql://", 1)
        return v

    @field_validator("CORS_ORIGINS", mode="after")
    @classmethod
    def parse_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    model_config = {
        "env_file": os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"),
        "env_file_encoding": "utf-8",
        "extra": "ignore"
    }

settings = Settings()
