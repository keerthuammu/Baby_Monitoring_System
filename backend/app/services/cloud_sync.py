import os
import logging
import httpx
from typing import Dict, Any
from app.core.config import settings

logger = logging.getLogger("cloud_sync")

def forward_reading_to_cloud(reading_payload: Dict[str, Any]):
    """
    Non-blocking background forwarder.
    Mirror IoT acoustic reading to Render Cloud backend ONLY when running in local development mode.
    Guaranteed loop-protection: Never forwards when running on Render cloud itself.
    """
    # 1. Guard: Never forward if already running on Render or in production cloud
    if os.environ.get("RENDER") or os.environ.get("RENDER_SERVICE_ID") or os.environ.get("RENDER_INSTANCE_ID"):
        return

    # 2. Guard: Respect global toggle
    if not getattr(settings, "ENABLE_CLOUD_FORWARDING", True):
        return

    cloud_base = getattr(settings, "CLOUD_BACKEND_URL", "").rstrip("/")
    if not cloud_base or not cloud_base.startswith("http"):
        return

    # 3. Guard: Do not self-forward if local server URL matches cloud backend
    local_host = getattr(settings, "BACKEND_HOST", "localhost")
    if "localhost" not in cloud_base and "127.0.0.1" not in cloud_base and local_host in cloud_base:
        return

    url = f"{cloud_base}/api/readings"
    headers = {
        "X-API-Key": settings.API_KEY,
        "X-Forwarded-From-Local": "true",
        "Content-Type": "application/json",
        "User-Agent": "SmartBabyMonitor-LocalBridge/1.1"
    }

    try:
        with httpx.Client(timeout=4.0) as client:
            resp = client.post(url, json=reading_payload, headers=headers)
            if resp.status_code in [200, 201]:
                logger.debug(f"[CLOUD SYNC] Synced reading to Render (HTTP {resp.status_code})")
            elif resp.status_code == 429:
                logger.warning("[CLOUD SYNC] Cloud rate limit (HTTP 429) - backing off.")
            else:
                logger.warning(f"[CLOUD SYNC] Render responded {resp.status_code}: {resp.text[:120]}")
    except Exception as e:
        logger.debug(f"[CLOUD SYNC] Cloud mirror deferred: {e}")

