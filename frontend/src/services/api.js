/**
 * API Client for Smart Baby Monitoring System Backend
 */

let rawUrl = import.meta.env.VITE_API_URL;

const isHostedOnRender = typeof window !== 'undefined' && window.location && window.location.hostname.includes('onrender.com');

if (isHostedOnRender) {
  // Hosted on Render Cloud
  rawUrl = (rawUrl && rawUrl.includes('http')) ? rawUrl : 'https://baby-monitor-backend-8m8o.onrender.com';
} else {
  // Local development / local network
  if (!rawUrl || rawUrl.includes('onrender.com') || rawUrl.includes('localhost')) {
    if (typeof window !== 'undefined' && window.location && window.location.hostname && window.location.hostname !== 'localhost') {
      rawUrl = `http://${window.location.hostname}:8000`;
    } else {
      rawUrl = 'http://localhost:8000';
    }
  }
}

const formattedUrl = rawUrl.startsWith('http') ? rawUrl : `https://${rawUrl}`;
export const API_BASE_URL = formattedUrl.replace(/\/+$/, '');

export async function fetchStats() {
  const res = await fetch(`${API_BASE_URL}/api/stats`);
  if (!res.ok) throw new Error(`HTTP error ${res.status}`);
  return res.json();
}

export async function fetchLatestReading() {
  const res = await fetch(`${API_BASE_URL}/api/readings/latest`);
  if (!res.ok) throw new Error(`HTTP error ${res.status}`);
  return res.json();
}

export async function fetchReadingsHistory(limit = 40) {
  const res = await fetch(`${API_BASE_URL}/api/readings?limit=${limit}`);
  if (!res.ok) throw new Error(`HTTP error ${res.status}`);
  return res.json();
}

export async function fetchEvents(limit = 20, unackOnly = false) {
  const query = unackOnly ? `?unacknowledged_only=true&limit=${limit}` : `?limit=${limit}`;
  const res = await fetch(`${API_BASE_URL}/api/events${query}`);
  if (!res.ok) throw new Error(`HTTP error ${res.status}`);
  return res.json();
}

export async function acknowledgeEvent(eventId) {
  const res = await fetch(`${API_BASE_URL}/api/events/${eventId}/acknowledge`, {
    method: 'PATCH',
  });
  if (!res.ok) throw new Error(`HTTP error ${res.status}`);
  return res.json();
}

export async function fetchDevices() {
  const res = await fetch(`${API_BASE_URL}/api/devices`);
  if (!res.ok) throw new Error(`HTTP error ${res.status}`);
  return res.json();
}

export async function fetchHealth() {
  const res = await fetch(`${API_BASE_URL}/health`);
  if (!res.ok) throw new Error(`HTTP error ${res.status}`);
  return res.json();
}

export async function fetchAudioClassificationStatus() {
  const res = await fetch(`${API_BASE_URL}/api/audio/status`);
  if (!res.ok) throw new Error(`HTTP error ${res.status}`);
  return res.json();
}

export async function classifyTestAudio(wavBlob) {
  const formData = new FormData();
  formData.append('file', wavBlob, 'test_sample.wav');
  formData.append('device_id', 'dashboard-web-test');

  const res = await fetch(`${API_BASE_URL}/api/audio/test-classify`, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || `Classification error ${res.status}`);
  }
  return res.json();
}

