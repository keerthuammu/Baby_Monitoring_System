import React, { useState, useEffect, useCallback, useRef } from 'react';
import Header from './components/Header';
import AlertBanner from './components/AlertBanner';
import MetricCards from './components/MetricCards';
import SoundChart from './components/SoundChart';
import EventsTable from './components/EventsTable';
import ReadingsTable from './components/ReadingsTable';
import { fetchStats, fetchReadingsHistory, fetchEvents, acknowledgeEvent, fetchDevices, fetchAudioClassificationStatus, API_BASE_URL } from './services/api';
import { AlertCircle, ShieldCheck, HeartHandshake, Laptop } from 'lucide-react';

export default function App() {
  const [stats, setStats] = useState(null);
  const [readings, setReadings] = useState([]);
  const [events, setEvents] = useState([]);
  const [devices, setDevices] = useState([]);
  const [audioStatus, setAudioStatus] = useState(null);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [isLoading, setIsLoading] = useState(false);
  const [isAcknowledging, setIsAcknowledging] = useState(false);
  const [error, setError] = useState(null);
  const [lastSyncTime, setLastSyncTime] = useState(null);
  const isPollingRef = useRef(false);
  const tickCountRef = useRef(0);

  // High-performance polling for real-time dashboard responsiveness (1-second tick)
  const loadData = useCallback(async (isManual = false) => {
    if (isPollingRef.current && !isManual) return;
    isPollingRef.current = true;
    if (isManual) setIsLoading(true);

    try {
      tickCountRef.current += 1;
      const shouldFetchMetadata = isManual || (tickCountRef.current % 5 === 1);

      // Fast critical telemetry (readings, events, live audio status) on every tick
      const fastPromises = [
        fetchReadingsHistory(30),
        fetchEvents(20),
        fetchAudioClassificationStatus().catch(() => null)
      ];

      // Metadata (devices, global stats) fetched periodically every 5 ticks to reduce network overhead
      const metaPromises = shouldFetchMetadata
        ? [fetchStats().catch(() => null), fetchDevices().catch(() => null)]
        : [Promise.resolve(null), Promise.resolve(null)];

      const [readingsData, eventsData, audioStatusData, statsData, devicesData] = await Promise.all([
        ...fastPromises,
        ...metaPromises
      ]);

      if (readingsData) setReadings(readingsData);
      if (eventsData) setEvents(eventsData);
      if (audioStatusData) setAudioStatus(audioStatusData);
      if (statsData) setStats(statsData);
      if (devicesData) setDevices(devicesData);

      setLastSyncTime(new Date());
      setError(null);
    } catch (err) {
      console.error('Polling error:', err);
      setError(`Unable to communicate with backend (${API_BASE_URL}). Ensure FastAPI server is running.`);
    } finally {
      isPollingRef.current = false;
      if (isManual) setIsLoading(false);
    }
  }, []);

  // Polling timer: 1000ms (1.0s) for ultra-responsive live display
  useEffect(() => {
    loadData();
    if (!autoRefresh) return;

    const intervalId = setInterval(() => {
      loadData();
    }, 1000);

    return () => clearInterval(intervalId);
  }, [autoRefresh, loadData]);

  // Acknowledge alert handler
  const handleAcknowledge = async (eventId) => {
    setIsAcknowledging(true);
    try {
      await acknowledgeEvent(eventId);
      // Optimistic state update
      setEvents(prev => prev.map(e => e.id === eventId ? { ...e, acknowledged: true } : e));
      if (stats) {
        setStats(prev => ({
          ...prev,
          unacknowledged_events: Math.max(0, prev.unacknowledged_events - 1)
        }));
      }
    } catch (err) {
      console.error('Error acknowledging event:', err);
    } finally {
      setIsAcknowledging(false);
    }
  };

  const latestReading = readings.length > 0 ? readings[0] : null;
  // Hardware freshness guard: device is actively streaming if a packet arrived within the last 10 seconds
  const isReadingFresh = latestReading?.recorded_at 
    ? (Date.now() - new Date(latestReading.recorded_at).getTime() < 10000)
    : false;
  const isOnline = Boolean(stats?.device_status === 'ONLINE' && isReadingFresh);

  // Single Authoritative Live State Agreement:
  // Is live audio currently classified as baby crying?
  const isLiveCrying = Boolean(
    isOnline &&
    audioStatus?.is_fresh && 
    (audioStatus?.code === 'BABY_CRYING_DETECTED' || audioStatus?.classification === 'BABY CRYING DETECTED')
  );

  // Active Alert Banner:
  // Strictly agrees with current authoritative live status.
  // A historical unacknowledged event is only displayed if it is actively ongoing or concluded within the freshness window (< 10 seconds).
  // If the baby has stopped crying and current audio is NOT BABY CRYING, UNCERTAIN, or AUDIO UNAVAILABLE,
  // the top alert banner does NOT display an outdated crying incident.
  const unacknowledgedEvent = events.find(e => !e.acknowledged && (e.classification === 'POSSIBLE_CRYING' || e.classification === 'BABY_CRYING_DETECTED'));
  const eventTime = unacknowledgedEvent?.end_time || unacknowledgedEvent?.start_time;
  const isEventRecent = eventTime ? (Date.now() - new Date(eventTime).getTime() < 10000) : false;

  const activeAlert = isLiveCrying
    ? (unacknowledgedEvent || {
        id: audioStatus?.event_id || 1,
        classification: 'BABY_CRYING_DETECTED',
        confidence: audioStatus?.confidence || 0.92,
        start_time: audioStatus?.timestamp || new Date().toISOString(),
        duration_seconds: audioStatus?.seconds_since_update || 2.0,
        device_id: 'esp32-nursery-01',
        acknowledged: false
      })
    : (unacknowledgedEvent && isEventRecent ? unacknowledgedEvent : null);

  return (
    <div className="min-h-screen bg-slate-950 flex flex-col text-slate-100">
      
      {/* Top Navigation & Status */}
      <Header
        isOnline={isOnline}
        lastSyncTime={lastSyncTime}
        autoRefresh={autoRefresh}
        setAutoRefresh={setAutoRefresh}
        onManualRefresh={() => loadData(true)}
        isLoading={isLoading}
      />

      {/* Backend connection error warning */}
      {error && (
        <div className="mx-4 lg:mx-8 mt-4 p-4 rounded-xl bg-rose-950/80 border border-rose-500/40 text-rose-300 text-xs flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
            <span>{error}</span>
          </div>
          <button 
            onClick={() => loadData(true)}
            className="underline hover:text-white font-medium"
          >
            Retry Connection
          </button>
        </div>
      )}

      {/* Prominent Emergency / Sound Alert Banner */}
      <AlertBanner
        activeAlert={activeAlert}
        onAcknowledge={handleAcknowledge}
        isAcknowledging={isAcknowledging}
      />

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl mx-auto w-full px-4 lg:px-8 py-6 space-y-6">
        
        {/* Metric Cards Row */}
        <MetricCards
          latestReading={latestReading}
          stats={stats}
          isOnline={isOnline}
          latestEvent={events.length > 0 ? events[0] : null}
          audioStatus={audioStatus}
        />


        {/* Real-time Telemetry Line Chart */}
        <SoundChart readings={readings} isOnline={isOnline} />

        {/* Dual Grid for Event Log & Packet Stream */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <EventsTable
            events={events}
            onAcknowledge={handleAcknowledge}
            isAcknowledging={isAcknowledging}
          />
          <ReadingsTable readings={readings} events={events} isOnline={isOnline} />
        </div>

      </main>

      {/* College Project Disclaimer & Architecture Footer */}
      <footer className="border-t border-slate-800/80 bg-slate-900/60 py-6 px-4 lg:px-8 mt-8">
        <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4 text-xs text-slate-500">
          <div className="flex items-center gap-2">
            <HeartHandshake className="w-4 h-4 text-indigo-400" />
            <span>
              <strong>Smart Baby Monitoring System</strong> • MCA Final Major Project
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-4">
            <span className="flex items-center gap-1.5">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
              Privacy-First (No Camera / Local Wi-Fi)
            </span>
            <span>•</span>
            <span className="flex items-center gap-1.5">
              <Laptop className="w-3.5 h-3.5 text-indigo-400" />
              FastAPI + PostgreSQL + React
            </span>
          </div>
        </div>
        <div className="max-w-7xl mx-auto mt-3 text-center md:text-left text-[11px] text-slate-600">
          Disclaimer: This system is an IoT academic prototype for caregiver assistance. It does not replace human parental supervision and is not a medical diagnostic device.
        </div>
      </footer>

    </div>
  );
}
