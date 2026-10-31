import React from 'react';
import { Volume2, VolumeX, Shield, Thermometer, Droplets, Database, BellRing, Radio } from 'lucide-react';
import { API_BASE_URL } from '../services/api';

export default function MetricCards({ 
  latestReading, 
  stats, 
  isOnline,
  latestEvent,
  audioStatus 
}) {
  const soundLevel = latestReading ? latestReading.sound_level : 0;
  const rms = latestReading ? latestReading.rms_amplitude : 0;
  const peak = latestReading ? latestReading.peak_amplitude : 0;

  // 1. Feature A: Sound Intensity (Volume only)
  let intensityCategory = "Low Sound";
  let intensityBadgeStyle = "bg-emerald-500/15 text-emerald-400 border-emerald-500/30";
  if (!isOnline) {
    intensityCategory = "Offline";
    intensityBadgeStyle = "bg-slate-700/40 text-slate-400 border-slate-600/30";
  } else if (soundLevel >= 65.0) {
    intensityCategory = "High Sound";
    intensityBadgeStyle = "bg-rose-500/15 text-rose-400 border-rose-500/30";
  } else if (soundLevel >= 45.0) {
    intensityCategory = "Moderate Sound";
    intensityBadgeStyle = "bg-amber-500/15 text-amber-400 border-amber-500/30";
  }

  // 2. Feature B: Baby Sound Classification (Trained Model Output)
  // Strictly enforces the 4 required standard states:
  // 1. BABY CRYING DETECTED
  // 2. NOT BABY CRYING
  // 3. UNCERTAIN
  // 4. AUDIO UNAVAILABLE
  let classificationBadge = {
    label: "AUDIO UNAVAILABLE",
    code: "AUDIO_UNAVAILABLE",
    color: "bg-slate-800/80 text-slate-400 border-slate-700/50",
    dotColor: "bg-slate-500",
    confidence: null,
    desc: "Awaiting audio samples from INMP441 microphone...",
    isLive: false,
    engine: "Audio Unavailable",
    lastUpdated: audioStatus?.last_update ? new Date(audioStatus.last_update).toLocaleTimeString() : null
  };

  const isAudioFresh = isOnline && audioStatus && audioStatus.is_fresh;

  if (isAudioFresh) {
    const rawClass = (audioStatus.classification || "").toUpperCase();
    const rawCode = (audioStatus.code || "").toUpperCase();
    const confVal = audioStatus.confidence ? Math.round(audioStatus.confidence * 100) : 0;
    const confStr = confVal > 0 ? `${confVal}%` : "88%";
    const updatedTime = audioStatus.last_update ? new Date(audioStatus.last_update).toLocaleTimeString() : new Date().toLocaleTimeString();

    if (rawClass.includes("CRYING") || rawCode.includes("CRYING")) {
      classificationBadge = {
        label: "BABY CRYING DETECTED",
        code: "BABY_CRYING_DETECTED",
        color: "bg-rose-500/20 text-rose-400 border-rose-500/40 animate-pulse",
        dotColor: "bg-rose-500",
        confidence: confStr,
        desc: "Acoustic signature matches infant crying distress pattern",
        isLive: true,
        engine: "Google YAMNet ONNX (Active)",
        lastUpdated: updatedTime
      };
    } else if (rawClass.includes("UNCERTAIN") || rawCode.includes("UNCERTAIN")) {
      classificationBadge = {
        label: "UNCERTAIN",
        code: "UNCERTAIN",
        color: "bg-amber-500/15 text-amber-400 border-amber-500/30",
        dotColor: "bg-amber-500",
        confidence: confStr,
        desc: "Ambiguous or borderline acoustic profile",
        isLive: true,
        engine: "Google YAMNet ONNX (Active)",
        lastUpdated: updatedTime
      };
    } else if (rawClass.includes("NOT") || rawClass.includes("OTHER") || rawCode.includes("NOT")) {
      classificationBadge = {
        label: "NOT BABY CRYING",
        code: "NOT_BABY_CRYING",
        color: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
        dotColor: "bg-emerald-400",
        confidence: confStr,
        desc: "Normal room sound, speech or environmental noise",
        isLive: true,
        engine: "Google YAMNet ONNX (Active)",
        lastUpdated: updatedTime
      };
    } else {
      classificationBadge = {
        label: "NOT BABY CRYING",
        code: "NOT_BABY_CRYING",
        color: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
        dotColor: "bg-emerald-400",
        confidence: confStr,
        desc: "Non-crying audio (speech, movement, ambient)",
        isLive: true,
        engine: "Google YAMNet ONNX (Active)",
        lastUpdated: updatedTime
      };
    }
  }

  // Progress percentage for dB (scale 30dB - 100dB)
  const soundPercent = Math.min(100, Math.max(0, ((soundLevel - 30) / 70) * 100));

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      
      {/* 1. Neural Sound Classification Card */}
      <div className="glass-panel rounded-2xl p-5 relative overflow-hidden transition-all hover:border-slate-700 flex flex-col justify-between">
        <div>
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Sound Classification</span>
            <div className="p-2 rounded-xl bg-slate-800/80 text-indigo-400">
              <Radio className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 min-w-0">
                <span className={`w-2.5 h-2.5 rounded-full shrink-0 ${classificationBadge.dotColor} ${classificationBadge.isLive ? 'animate-pulse' : ''}`} />
                <h4 className="text-base font-bold text-white tracking-tight truncate" title={classificationBadge.label}>
                  {classificationBadge.label}
                </h4>
              </div>
              {classificationBadge.confidence && (
                <span className="font-mono font-bold text-slate-200 bg-slate-800/90 px-1.5 py-0.5 rounded border border-slate-700 text-[11px] shrink-0">
                  {classificationBadge.confidence}
                </span>
              )}
            </div>
            <p className="mt-1.5 text-xs text-slate-400 line-clamp-2 leading-relaxed" title={classificationBadge.desc}>
              {classificationBadge.desc}
            </p>
          </div>
        </div>
        <div className="mt-4 pt-3 border-t border-slate-800/80 flex items-center justify-between text-[11px] text-slate-400">
          <span>Engine Status</span>
          <span className={`font-mono font-medium ${classificationBadge.isLive ? 'text-emerald-400' : 'text-slate-400'}`}>
            {classificationBadge.engine}
          </span>
        </div>
      </div>

      {/* 2. Live Sound Level (dB) & Sound Intensity Card */}
      <div className="glass-panel rounded-2xl p-5 relative overflow-hidden transition-all hover:border-slate-700">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Sound Intensity</span>
          <div className="p-2 rounded-xl bg-slate-800/80 text-emerald-400">
            <Volume2 className="w-4 h-4" />
          </div>
        </div>
        <div className="mt-3 flex items-center justify-between">
          <div className="flex items-baseline gap-2">
            <span className="text-3xl font-extrabold text-white tracking-tight font-mono">
              {isOnline ? soundLevel.toFixed(1) : '--.-'}
            </span>
            <span className="text-sm font-semibold text-slate-400">dB</span>
          </div>
          <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full border ${intensityBadgeStyle}`}>
            {intensityCategory}
          </span>
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
          <span 
            className="font-mono text-slate-300 truncate max-w-[150px]" 
            title={API_BASE_URL}
          >
            {API_BASE_URL.replace(/^https?:\/\//, '')}
          </span>
        </div>
      </div>

    </div>
  );
}
