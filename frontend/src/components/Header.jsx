import React from 'react';
import { Activity, Wifi, WifiOff, RefreshCw, ShieldAlert, Cpu } from 'lucide-react';

export default function Header({ 
  isOnline, 
  lastSyncTime, 
  autoRefresh, 
  setAutoRefresh, 
  onManualRefresh, 
  isLoading 
}) {
  return (
    <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur-md sticky top-0 z-30 px-4 lg:px-8 py-3.5">
      <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        
        {/* Brand & Project Info */}
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-indigo-600 to-violet-500 flex items-center justify-center shadow-lg shadow-indigo-500/20">
            <Activity className="w-5 h-5 text-white animate-pulse" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-bold tracking-tight text-white">Smart Baby Monitor</h1>
              <span className="text-[10px] uppercase font-semibold px-2 py-0.5 rounded-full bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                IoT Prototype
              </span>
            </div>
            <p className="text-xs text-slate-400">
              MCA Project • ESP32 & INMP441 Acoustic Node
            </p>
          </div>
        </div>

        {/* Status & Control Actions */}
        <div className="flex flex-wrap items-center gap-3 w-full sm:w-auto justify-between sm:justify-end">
          
          {/* Connection Status Badge */}
          <div className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border text-xs font-medium transition-all ${
            isOnline 
              ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400' 
              : 'bg-rose-500/10 border-rose-500/20 text-rose-400'
          }`}>
            {isOnline ? (
              <>
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                </span>
                <Wifi className="w-3.5 h-3.5" />
                <span>ESP32 Node Online</span>
              </>
            ) : (
              <>
                <span className="inline-flex rounded-full h-2 w-2 bg-rose-500"></span>
                <WifiOff className="w-3.5 h-3.5" />
                <span>Device Offline</span>
              </>
            )}
          </div>

          {/* Auto Refresh Toggle */}
          <button
            onClick={() => setAutoRefresh(!autoRefresh)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors flex items-center gap-1.5 ${
              autoRefresh 
                ? 'bg-slate-800 border-slate-700 text-indigo-400 hover:bg-slate-700/80' 
                : 'bg-slate-900 border-slate-800 text-slate-500 hover:text-slate-300'
            }`}
            title="Toggle automatic telemetry polling"
          >
            <span className={`inline-block w-1.5 h-1.5 rounded-full ${autoRefresh ? 'bg-indigo-400' : 'bg-slate-600'}`} />
            {autoRefresh ? 'Live Polling (2.5s)' : 'Polling Paused'}
          </button>

          {/* Manual Refresh Button */}
          <button
            onClick={onManualRefresh}
            disabled={isLoading}
            className="p-2 rounded-lg bg-slate-800 border border-slate-700 text-slate-300 hover:text-white hover:bg-slate-700 transition disabled:opacity-50"
            title="Manual sync"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin text-indigo-400' : ''}`} />
          </button>

          {/* Last sync time */}
          {lastSyncTime && (
            <span className="text-[11px] text-slate-500 hidden md:inline">
              Updated {lastSyncTime.toLocaleTimeString()}
            </span>
          )}
        </div>
      </div>
    </header>
  );
}
