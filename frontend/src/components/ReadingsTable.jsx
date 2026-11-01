import React from 'react';
import { Database, Radio } from 'lucide-react';

export default function ReadingsTable({ readings, events, isOnline }) {
  const displayedReadings = (readings || []).slice(0, 15);
  const cryingEvents = (events || []).filter(e => (e.classification || '').toUpperCase().includes('CRYING'));

  return (
    <div className="glass-panel rounded-2xl p-5 transition-all">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2.5">
          <div className={`p-2 rounded-xl border ${isOnline ? 'bg-violet-500/10 text-violet-400 border-violet-500/20' : 'bg-slate-800/80 text-slate-500 border-slate-700/50'}`}>
            <Radio className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-base font-bold text-white tracking-tight">Recent Telemetry Stream</h3>
            <p className="text-xs text-slate-400">
              {isOnline ? "Raw acoustic packets received from ESP32 IoT node" : "Last recorded packets (Device Offline)"}
            </p>
          </div>
        </div>
        <span className="text-[11px] font-mono text-slate-500">
          Showing latest {displayedReadings.length} packets
        </span>
      </div>

      {displayedReadings.length === 0 ? (
        <div className="py-8 text-center text-slate-500 border border-dashed border-slate-800 rounded-xl">
          <p className="text-xs">No telemetry packets received yet</p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs font-mono">
            <thead>
              <tr className="border-b border-slate-800 text-slate-400 uppercase text-[10px] tracking-wider font-semibold font-sans">
                <th className="py-2 px-3">Packet ID</th>
                <th className="py-2 px-3">Recorded Time</th>
                <th className="py-2 px-3">Sound Intensity</th>
                <th className="py-2 px-3">Baby Classification</th>
                <th className="py-2 px-3">RMS Energy</th>
                <th className="py-2 px-3">Peak Amplitude</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 text-slate-300">
              {displayedReadings.map((r) => {
                const isEdgeCry = (r.classification || '').toUpperCase().includes('CRYING');

                // Feature A: Sound Intensity (Decoupled Volume Level)
                let intensityLabel = "Low Sound";
                let intensityStyle = "bg-emerald-500/15 text-emerald-400 border-emerald-500/30";
                if (r.sound_level >= 65.0) {
                  intensityLabel = "High Sound";
                  intensityStyle = "bg-rose-500/15 text-rose-400 border-rose-500/30";
                } else if (r.sound_level >= 45.0) {
                  intensityLabel = "Moderate Sound";
                  intensityStyle = "bg-amber-500/15 text-amber-400 border-amber-500/30";
                }

                // Feature B: Baby Sound Classification (Trained Model / Verified Event)
                let babyLabel = "Not Baby Crying";
                let babyStyle = "bg-emerald-500/15 text-emerald-400 border-emerald-500/30";
                if (isEdgeCry) {
                  babyLabel = "🚨 Baby Crying";
                  babyStyle = "bg-rose-500/20 text-rose-400 border-rose-500/40 font-bold animate-pulse";
                }

                return (
                  <tr key={r.id} className="hover:bg-slate-800/30 transition">
                    <td className="py-2.5 px-3 text-slate-500">#{r.id}</td>
                    <td className="py-2.5 px-3">
                      {new Date(r.recorded_at).toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                    </td>
                    <td className="py-2.5 px-3">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-white">
                          {r.sound_level.toFixed(1)} dB
                        </span>
                        <span className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-semibold border ${intensityStyle}`}>
                          {intensityLabel}
                        </span>
                      </div>
                    </td>
                    <td className="py-2.5 px-3 font-sans">
                      <span className={`inline-block px-2 py-0.5 rounded text-[10px] font-semibold border ${babyStyle}`}>
                        {babyLabel}
                      </span>
                    </td>
                    <td className="py-2.5 px-3 text-slate-400">{r.rms_amplitude.toFixed(1)}</td>
                    <td className="py-2.5 px-3 text-slate-400">{r.peak_amplitude}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
