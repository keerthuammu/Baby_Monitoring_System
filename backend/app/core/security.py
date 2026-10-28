from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader
from app.core.config import settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def verify_device_api_key(api_key: str = Security(api_key_header)) -> bool:
    """Validate device API key for ingestion endpoints."""
    # If no API key configured, permit access (easy setup mode)
    if not settings.API_KEY:
        return True
    if api_key != settings.API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-API-Key header"
        )
    return True
