import React from 'react';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
  CartesianGrid
} from 'recharts';
import { Activity, Info } from 'lucide-react';

export default function SoundChart({ readings }) {
  // Format readings chronological for the chart (oldest to newest)
  const chartData = [...(readings || [])]
    .reverse()
    .map((r, index) => {
      const timeStr = r.recorded_at ? new Date(r.recorded_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : `#${index}`;
      return {
        time: timeStr,
        soundLevel: Number(r.sound_level.toFixed(1)),
        rms: Number(r.rms_amplitude.toFixed(1)),
        peak: r.peak_amplitude,
      };
    });

  const CustomTooltip = ({ active, payload, label }) => {
    if (active && payload && payload.length) {
      const data = payload[0].payload;
      const isHigh = data.soundLevel >= 65;
      const isModerate = data.soundLevel >= 45 && data.soundLevel < 65;
      const classLabel = isHigh ? "High Sound Activity" : isModerate ? "Moderate Sound" : "Quiet / Ambient";
      const classColor = isHigh ? "text-rose-400" : isModerate ? "text-amber-400" : "text-emerald-400";

      return (
        <div className="bg-slate-900/95 border border-slate-700/80 rounded-xl p-3 shadow-xl backdrop-blur-md text-xs">
          <p className="font-semibold text-slate-300 mb-1.5 flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-indigo-500" />
            Time: {label}
          </p>
          <div className="space-y-1 font-mono">
            <p className="text-emerald-400 font-bold">
              Sound Level: {data.soundLevel} dB
            </p>
            <p className="font-sans">
              <span className="text-slate-400">Class: </span>
              <span className={`font-semibold ${classColor}`}>{classLabel}</span>
            </p>
            <p className="text-slate-400">
              RMS Energy: {data.rms}
            </p>
            <p className="text-slate-400">
              Peak Amplitude: {data.peak}
            </p>
          </div>
        </div>
      );
    }
    return null;
  };

  return (
    <div className="glass-panel rounded-2xl p-5 transition-all">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 mb-6">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-xl bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
            <Activity className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-base font-bold text-white tracking-tight">Sound Activity Telemetry</h3>
            <p className="text-xs text-slate-400">Continuous acoustic decibel tracking (INMP441 Microphone)</p>
          </div>
        </div>

        {/* Legend */}
        <div className="flex items-center gap-4 text-xs text-slate-400">
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-indigo-500" />
            <span>Sound Level (dB)</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-0.5 bg-rose-500 border border-dashed" />
            <span className="text-rose-400">Alert Threshold (65 dB)</span>
          </div>
        </div>
      </div>

      {chartData.length === 0 ? (
        <div className="h-64 flex flex-col items-center justify-center text-slate-500 border border-dashed border-slate-800 rounded-xl">
          <Activity className="w-8 h-8 mb-2 opacity-40 animate-pulse" />
          <p className="text-sm font-medium">No acoustic telemetry received yet</p>
          <p className="text-xs text-slate-600 mt-1">Start ESP32 or run the hardware simulator to stream data</p>
        </div>
      ) : (
        <div className="h-72 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
              <XAxis 
                dataKey="time" 
                stroke="#64748b" 
                fontSize={11} 
                tickLine={false}
                axisLine={{ stroke: '#334155' }}
              />
              <YAxis 
                domain={[25, 100]} 
                stroke="#64748b" 
                fontSize={11} 
                tickLine={false}
                axisLine={{ stroke: '#334155' }}
                unit="dB"
              />
              <Tooltip content={<CustomTooltip />} />
              <ReferenceLine 
                y={65} 
                stroke="#f43f5e" 
                strokeDasharray="4 4" 
                label={{ value: '65 dB Alert Line', fill: '#fb7185', fontSize: 10, position: 'insideTopRight' }} 
              />
              <Line
                type="monotone"
                dataKey="soundLevel"
                stroke="#6366f1"
                strokeWidth={2.5}
                dot={false}
                activeDot={{ r: 6, fill: '#818cf8', stroke: '#312e81', strokeWidth: 2 }}
                isAnimationActive={false} // Smooth real-time update without disruptive reset animations
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
