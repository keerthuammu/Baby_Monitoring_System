import pytest
from datetime import datetime, timezone
from app.core.config import settings

def test_root_endpoint(client):
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["project"] == "Smart Baby Monitoring System"
    assert data["status"] == "operational"

def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"

def test_submit_reading_unauthorized(client):
    # Missing API Key
    payload = {
        "device_id": "esp32-test-01",
        "sound_level": 55.4,
        "rms_amplitude": 120.5,
        "peak_amplitude": 350
    }
    response = client.post("/api/readings", json=payload)
    assert response.status_code == 401

def test_submit_reading_invalid_payload(client):
    # Invalid sound level (> 140 dB)
    headers = {"X-API-Key": settings.API_KEY}
    payload = {
        "device_id": "esp32-test-01",
        "sound_level": 999.0,
        "rms_amplitude": 120.5,
        "peak_amplitude": 350
    }
    response = client.post("/api/readings", json=payload, headers=headers)
    assert response.status_code == 422

def test_submit_reading_success(client):
    headers = {"X-API-Key": settings.API_KEY}
    payload = {
        "device_id": "esp32-test-01",
        "sound_level": 48.2,
        "rms_amplitude": 85.0,
        "peak_amplitude": 210
    }
    response = client.post("/api/readings", json=payload, headers=headers)
    assert response.status_code == 201
    data = response.json()
    assert data["device_id"] == "esp32-test-01"
    assert data["sound_level"] == 48.2
    assert "id" in data

def test_get_latest_reading(client):
    response = client.get("/api/readings/latest")
    assert response.status_code == 200
    data = response.json()
    assert data is not None
    assert data["device_id"] == "esp32-test-01"

def test_get_readings_history(client):
    response = client.get("/api/readings?limit=10")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1

def test_elevated_sound_creates_event(client):
    headers = {"X-API-Key": settings.API_KEY}
    # Sound level higher than threshold (65 dB)
    payload = {
        "device_id": "esp32-test-01",
        "sound_level": 74.5,
        "rms_amplitude": 650.0,
        "peak_amplitude": 1500
    }
    res = client.post("/api/readings", json=payload, headers=headers)
    assert res.status_code == 201

    # Check that an event was generated
    events_res = client.get("/api/events")
    assert events_res.status_code == 200
    events = events_res.json()
    assert len(events) >= 1
    assert events[0]["classification"] == "HIGH_SOUND_ACTIVITY"
    assert events[0]["acknowledged"] is False

def test_acknowledge_event(client):
    # Get the latest event
    events_res = client.get("/api/events")
    event_id = events_res.json()[0]["id"]

    # Acknowledge it
    ack_res = client.patch(f"/api/events/{event_id}/acknowledge")
    assert ack_res.status_code == 200
    assert ack_res.json()["acknowledged"] is True

def test_dashboard_stats(client):
    response = client.get("/api/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["total_readings"] >= 2
    assert data["total_events"] >= 1
    assert data["device_status"] in ["ONLINE", "OFFLINE"]

def test_list_devices(client):
    response = client.get("/api/devices")
    assert response.status_code == 200
    devices = response.json()
    assert len(devices) >= 1
    assert devices[0]["device_id"] == "esp32-test-01"
