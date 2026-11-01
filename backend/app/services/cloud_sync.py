import logging
import httpx
from typing import Dict, Any
from app.core.config import settings

logger = logging.getLogger("cloud_sync")

def forward_reading_to_cloud(reading_payload: Dict[str, Any]):
    """
    Non-blocking background forwarder.
    Mirror IoT acoustic reading to Render Cloud backend so both local
    and remote deployments remain online with synchronized metrics.
    """
    if not getattr(settings, "ENABLE_CLOUD_FORWARDING", True):
        return

    cloud_base = getattr(settings, "CLOUD_BACKEND_URL", "").rstrip("/")
    if not cloud_base or not cloud_base.startswith("http"):
        return

    url = f"{cloud_base}/api/readings"
    headers = {
        "X-API-Key": settings.API_KEY,
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }

    try:
        with httpx.Client(timeout=4.0) as client:
            resp = client.post(url, json=reading_payload, headers=headers)
            if resp.status_code in [200, 201]:
                logger.debug(f"[CLOUD SYNC] Successfully synced reading {reading_payload.get('device_id')} to Render (HTTP {resp.status_code})")
            elif resp.status_code == 429:
                logger.warning("[CLOUD SYNC] Render/Cloudflare rate limit (HTTP 429) - cloud forwarder backing off.")
            else:
                logger.warning(f"[CLOUD SYNC] Render responded {resp.status_code}: {resp.text[:120]}")
    except Exception as e:
        logger.debug(f"[CLOUD SYNC] Render mirror deferred: {e}")
