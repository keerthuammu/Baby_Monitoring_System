import React, { useState } from 'react';
import { AlertTriangle, CheckCircle, Clock, ShieldAlert } from 'lucide-react';

export default function EventsTable({ events, onAcknowledge, isAcknowledging }) {
  const [filterUnack, setFilterUnack] = useState(false);

  const displayedEvents = filterUnack 
    ? (events || []).filter(e => !e.acknowledged) 
    : (events || []);

  return (
    <div className="glass-panel rounded-2xl p-5 transition-all">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 mb-4">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-xl bg-amber-500/10 text-amber-400 border border-amber-500/20">
            <ShieldAlert className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-base font-bold text-white tracking-tight">Acoustic Event History</h3>
            <p className="text-xs text-slate-400">Recorded crying episodes & elevated sound activity</p>
          </div>
        </div>

        {/* Filter controls */}
        <div className="flex items-center gap-1.5 bg-slate-900 p-1 rounded-xl border border-slate-800 text-xs">
          <button
            onClick={() => setFilterUnack(false)}
            className={`px-3 py-1 rounded-lg font-medium transition ${
              !filterUnack ? 'bg-indigo-600 text-white shadow-sm' : 'text-slate-400 hover:text-white'
            }`}
          >
            All Events ({events ? events.length : 0})
          </button>
          <button
            onClick={() => setFilterUnack(true)}
            className={`px-3 py-1 rounded-lg font-medium transition ${
              filterUnack ? 'bg-indigo-600 text-white shadow-sm' : 'text-slate-400 hover:text-white'
            }`}
          >
            Active / Unack
          </button>
        </div>
      </div>

      {displayedEvents.length === 0 ? (
        <div className="py-12 text-center text-slate-500 border border-dashed border-slate-800 rounded-xl">
          <CheckCircle className="w-8 h-8 mx-auto mb-2 opacity-30 text-emerald-500" />
          <p className="text-sm font-medium">No {filterUnack ? 'unacknowledged ' : ''}events recorded</p>
          <p className="text-xs text-slate-600 mt-0.5">The nursery sound level is calm and within normal thresholds</p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-slate-800 text-slate-400 uppercase text-[10px] tracking-wider font-semibold">
                <th className="py-2.5 px-3">Classification</th>
                <th className="py-2.5 px-3">Start Time</th>
                <th className="py-2.5 px-3">Duration</th>
                <th className="py-2.5 px-3">Confidence</th>
                <th className="py-2.5 px-3">Status</th>
                <th className="py-2.5 px-3 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 font-mono">
              {displayedEvents.map((evt) => {
                const isCrying = evt.classification === 'POSSIBLE_CRYING';
                return (
                  <tr key={evt.id} className="hover:bg-slate-800/30 transition">
                    <td className="py-3 px-3">
                      <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-[11px] font-sans font-semibold border ${
                        isCrying 
                          ? 'bg-rose-500/10 text-rose-400 border-rose-500/20' 
                          : 'bg-amber-500/10 text-amber-400 border-amber-500/20'
                      }`}>
                        <AlertTriangle className="w-3 h-3" />
                        {evt.classification.replace(/_/g, ' ')}
                      </span>
                    </td>
                    <td className="py-3 px-3 text-slate-300">
                      {new Date(evt.start_time).toLocaleTimeString()}
                    </td>
                    <td className="py-3 px-3 text-slate-300">
                      {evt.duration_seconds.toFixed(1)}s
                    </td>
                    <td className="py-3 px-3 text-slate-300">
                      {(evt.confidence * 100).toFixed(0)}%
                    </td>
                    <td className="py-3 px-3 font-sans">
                      {evt.acknowledged ? (
                        <span className="inline-flex items-center gap-1 text-[11px] text-emerald-400 font-medium">
                          <CheckCircle className="w-3 h-3" /> Acknowledged
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-[11px] text-amber-400 font-medium animate-pulse">
                          <Clock className="w-3 h-3" /> Pending
                        </span>
                      )}
                    </td>
                    <td className="py-3 px-3 text-right font-sans">
                      {!evt.acknowledged && (
                        <button
                          onClick={() => onAcknowledge(evt.id)}
                          disabled={isAcknowledging}
                          className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 text-[11px] font-medium transition hover:border-slate-600 disabled:opacity-50"
                        >
                          Dismiss
                        </button>
                      )}
                    </td>
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
