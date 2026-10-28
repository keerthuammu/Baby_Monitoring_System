import React from 'react';
import { Volume2, VolumeX, Shield, Thermometer, Droplets, Database, BellRing, Radio } from 'lucide-react';

export default function MetricCards({ 
  latestReading, 
  stats, 
  isOnline,
  latestEvent 
}) {
  const soundLevel = latestReading ? latestReading.sound_level : 0;
  const rms = latestReading ? latestReading.rms_amplitude : 0;
  const peak = latestReading ? latestReading.peak_amplitude : 0;

  // Determine sound category
  let statusBadge = {
    label: 'Offline',
    color: 'bg-slate-700/50 text-slate-400 border-slate-600/30',
    dotColor: 'bg-slate-500',
    desc: 'Waiting for ESP32 connection...'
  };

  if (isOnline) {
    if (latestEvent && !latestEvent.acknowledged && latestEvent.classification === 'POSSIBLE_CRYING') {
      statusBadge = {
        label: 'Possible Crying',
        color: 'bg-rose-500/15 text-rose-400 border-rose-500/30',
        dotColor: 'bg-rose-500',
        desc: 'Acoustic pattern matches crying signature'
      };
    } else if (soundLevel >= 65) {
      statusBadge = {
        label: 'High Sound Activity',
        color: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
        dotColor: 'bg-amber-500',
        desc: 'Elevated noise above 65 dB threshold'
      };
    } else if (soundLevel >= 45) {
      statusBadge = {
        label: 'Moderate Sound',
        color: 'bg-blue-500/15 text-blue-400 border-blue-500/30',
        dotColor: 'bg-blue-500',
        desc: 'Normal nursery sound activity'
      };
    } else {
      statusBadge = {
        label: 'Quiet Nursery',
        color: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
        dotColor: 'bg-emerald-500',
        desc: 'Calm ambient acoustic baseline'
      };
    }
  }

  // Progress percentage for dB (scale 30dB - 100dB)
  const soundPercent = Math.min(100, Math.max(0, ((soundLevel - 30) / 70) * 100));

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      
      {/* 1. Acoustic Classification Card */}
      <div className="glass-panel rounded-2xl p-5 relative overflow-hidden transition-all hover:border-slate-700">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Acoustic Status</span>
          <div className="p-2 rounded-xl bg-slate-800/80 text-indigo-400">
            <Radio className="w-4 h-4" />
          </div>
        </div>
        <div className="mt-3">
          <div className="flex items-center gap-2">
            <span className={`w-2.5 h-2.5 rounded-full ${statusBadge.dotColor} animate-pulse`} />
            <h4 className="text-lg font-bold text-white tracking-tight">{statusBadge.label}</h4>
          </div>
          <p className="text-xs text-slate-400 mt-1">{statusBadge.desc}</p>
        </div>
        <div className="mt-4 pt-3 border-t border-slate-800/80 flex items-center justify-between text-[11px] text-slate-400">
          <span>Classifier State</span>
          <span className="font-mono text-slate-300">ESP32 I²S Audio Pipeline</span>
        </div>
      </div>

      {/* 2. Live Sound Level (dB) Card */}
      <div className="glass-panel rounded-2xl p-5 relative overflow-hidden transition-all hover:border-slate-700">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Live Sound Level</span>
          <div className="p-2 rounded-xl bg-slate-800/80 text-emerald-400">
            <Volume2 className="w-4 h-4" />
          </div>
        </div>
        <div className="mt-3 flex items-baseline gap-2">
          <span className="text-3xl font-extrabold text-white tracking-tight font-mono">
            {isOnline ? soundLevel.toFixed(1) : '--.-'}
          </span>
          <span className="text-sm font-semibold text-slate-400">dB</span>
        </div>

        {/* Progress gauge bar */}
        <div className="mt-3 w-full bg-slate-800 rounded-full h-2 overflow-hidden">
          <div 
            className={`h-full rounded-full transition-all duration-500 ${
              soundLevel >= 65 ? 'bg-gradient-to-r from-amber-500 to-rose-500' : 'bg-gradient-to-r from-emerald-500 to-indigo-500'
            }`}
            style={{ width: `${isOnline ? soundPercent : 0}%` }}
          />
        </div>

        <div className="mt-3 pt-3 border-t border-slate-800/80 flex items-center justify-between text-[11px] text-slate-400 font-mono">
          <span>RMS: {isOnline ? rms.toFixed(1) : '0'}</span>
          <span>Peak: {isOnline ? peak : '0'}</span>
        </div>
      </div>

      {/* 3. Telemetry Persistence Card */}
      <div className="glass-panel rounded-2xl p-5 relative overflow-hidden transition-all hover:border-slate-700">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Telemetry & Events</span>
          <div className="p-2 rounded-xl bg-slate-800/80 text-violet-400">
            <Database className="w-4 h-4" />
          </div>
        </div>
        <div className="mt-3 grid grid-cols-2 gap-2">
          <div>
            <div className="text-2xl font-extrabold text-white font-mono">
              {stats ? stats.total_readings.toLocaleString() : 0}
            </div>
            <p className="text-[11px] text-slate-400 mt-0.5">Total Packets</p>
          </div>
          <div>
            <div className="text-2xl font-extrabold text-amber-400 font-mono">
              {stats ? stats.total_events : 0}
            </div>
            <p className="text-[11px] text-slate-400 mt-0.5">Detected Events</p>
          </div>
        </div>
        <div className="mt-4 pt-3 border-t border-slate-800/80 flex items-center justify-between text-[11px] text-slate-400">
          <span>Database</span>
          <span className="text-emerald-400 font-medium">PostgreSQL 18</span>
        </div>
      </div>

      {/* 4. Network & Node Health */}
      <div className="glass-panel rounded-2xl p-5 relative overflow-hidden transition-all hover:border-slate-700">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Node & Network</span>
          <div className="p-2 rounded-xl bg-slate-800/80 text-sky-400">
            <Radio className="w-4 h-4" />
          </div>
        </div>
        <div className="mt-3">
          <div className="flex items-center justify-between">
            <span className="text-xs text-slate-400">Device Node:</span>
            <span className="font-mono text-xs font-semibold text-slate-200">
              {latestReading ? latestReading.device_id : "esp32-nursery-01"}
            </span>
          </div>
          <div className="flex items-center justify-between mt-2">
            <span className="text-xs text-slate-400">Local Wi-Fi:</span>
            <span className="text-xs font-semibold text-emerald-400">802.11 b/g/n</span>
          </div>
        </div>
        <div className="mt-4 pt-3 border-t border-slate-800/80 flex items-center justify-between text-[11px] text-slate-400">
          <span>Target Host</span>
          <span className="font-mono text-slate-300">192.168.60.178:8000</span>
        </div>
      </div>

    </div>
  );
}
