import React from 'react';
import { Database, Radio } from 'lucide-react';

export default function ReadingsTable({ readings, events }) {
  const displayedReadings = (readings || []).slice(0, 15);
  const cryingEvents = (events || []).filter(e => e.classification === 'POSSIBLE_CRYING');

  return (
    <div className="glass-panel rounded-2xl p-5 transition-all">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-xl bg-violet-500/10 text-violet-400 border border-violet-500/20">
            <Radio className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-base font-bold text-white tracking-tight">Recent Telemetry Stream</h3>
            <p className="text-xs text-slate-400">Raw acoustic packets received from ESP32 IoT node</p>
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
                <th className="py-2 px-3">Sound Level</th>
                <th className="py-2 px-3">Classification</th>
                <th className="py-2 px-3">RMS Energy</th>
                <th className="py-2 px-3">Peak Amplitude</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 text-slate-300">
              {displayedReadings.map((r) => {
                // Check if this packet falls within an active/recent crying event
                const readingTime = new Date(r.recorded_at).getTime();
                const isCryingEvent = cryingEvents.some(e => {
                  const start = new Date(e.start_time).getTime() - 2500;
                  const end = (e.end_time ? new Date(e.end_time).getTime() : start) + (e.duration_seconds ? e.duration_seconds * 1000 : 4000) + 3000;
                  return readingTime >= start && readingTime <= end;
                });

                const isEdgeCry = r.classification === 'POSSIBLE_CRYING' || (r.pitch_hz >= 300 && r.pitch_hz <= 680);
                const isCrying = isEdgeCry || (isCryingEvent && r.sound_level >= 55.0);
                const isHigh = r.sound_level >= 65.0;
                const isModerate = r.sound_level >= 45.0 && r.sound_level < 65.0;

                let classLabel = "Quiet / Ambient";
                let classStyle = "bg-emerald-500/15 text-emerald-400 border-emerald-500/30";

                if (isCrying) {
                  classLabel = "Baby Crying";
                  classStyle = "bg-rose-500/20 text-rose-400 border-rose-500/40 font-bold animate-pulse";
                } else if (isHigh) {
                  classLabel = "High Sound";
                  classStyle = "bg-amber-500/15 text-amber-400 border-amber-500/30";
                } else if (isModerate) {
                  classLabel = "Moderate Sound";
                  classStyle = "bg-sky-500/15 text-sky-400 border-sky-500/30";
                }

                return (
                  <tr key={r.id} className="hover:bg-slate-800/30 transition">
                    <td className="py-2.5 px-3 text-slate-500">#{r.id}</td>
                    <td className="py-2.5 px-3">
                      {new Date(r.recorded_at).toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                    </td>
                    <td className="py-2.5 px-3">
                      <span className={`font-semibold ${isHigh ? 'text-amber-400' : 'text-emerald-400'}`}>
                        {r.sound_level.toFixed(1)} dB
                      </span>
                    </td>
                    <td className="py-2.5 px-3 font-sans">
                      <span className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-semibold border ${classStyle}`}>
                        {classLabel}
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
