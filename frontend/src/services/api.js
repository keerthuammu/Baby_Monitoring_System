/**
 * API Client for Smart Baby Monitoring System Backend
 */

const rawUrl = import.meta.env.VITE_API_URL || 'https://baby-monitor-backend-8m8o.onrender.com';
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
