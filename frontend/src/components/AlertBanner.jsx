import React from 'react';
import { AlertTriangle, CheckCircle2, Volume2, Clock } from 'lucide-react';

export default function AlertBanner({ activeAlert, onAcknowledge, isAcknowledging }) {
  if (!activeAlert) return null;

  const isCrying = activeAlert.classification === 'POSSIBLE_CRYING';
  const bannerBg = isCrying 
    ? 'bg-rose-950/80 border-rose-500/50 shadow-rose-950/50' 
    : 'bg-amber-950/80 border-amber-500/50 shadow-amber-950/50';

  const iconColor = isCrying ? 'text-rose-400' : 'text-amber-400';
  const buttonColor = isCrying 
    ? 'bg-rose-600 hover:bg-rose-500 text-white' 
    : 'bg-amber-600 hover:bg-amber-500 text-white';

  return (
    <div className={`mx-4 lg:mx-8 mt-4 rounded-xl border p-4 shadow-xl backdrop-blur-md transition-all animate-bounce-subtle ${bannerBg}`}>
      <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        
        <div className="flex items-start gap-3.5">
          <div className={`p-2.5 rounded-lg bg-black/30 border border-white/10 shrink-0 ${iconColor}`}>
            <AlertTriangle className="w-6 h-6 animate-pulse" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold tracking-wider uppercase px-2 py-0.5 rounded bg-black/40 border border-white/10 text-white">
                {activeAlert.classification.replace(/_/g, ' ')}
              </span>
              <span className="text-xs text-slate-300">
                Confidence: {(activeAlert.confidence * 100).toFixed(0)}%
              </span>
            </div>
            <h3 className="text-base font-semibold text-white mt-1">
              {isCrying 
                ? 'Possible baby crying detected in nursery!' 
                : 'Elevated acoustic energy sustained above normal baseline!'}
            </h3>
            <p className="text-xs text-slate-300 mt-0.5 flex items-center gap-3">
              <span className="flex items-center gap-1">
                <Clock className="w-3.5 h-3.5" />
                Duration: {activeAlert.duration_seconds.toFixed(1)}s
              </span>
              <span>•</span>
              <span>Source: {activeAlert.device_id}</span>
              <span>•</span>
              <span>Started: {new Date(activeAlert.start_time).toLocaleTimeString()}</span>
            </p>
          </div>
        </div>

        {/* Action Button */}
        <div className="w-full md:w-auto flex items-center justify-end">
          <button
            onClick={() => onAcknowledge(activeAlert.id)}
            disabled={isAcknowledging}
            className={`w-full md:w-auto px-4 py-2 rounded-lg text-xs font-semibold tracking-wide flex items-center justify-center gap-2 transition shadow-md disabled:opacity-50 ${buttonColor}`}
          >
            <CheckCircle2 className="w-4 h-4" />
            {isAcknowledging ? 'Acknowledging...' : 'Acknowledge Alert'}
          </button>
        </div>
      </div>
    </div>
  );
}
