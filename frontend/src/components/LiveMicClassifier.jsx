import React, { useState, useEffect, useRef } from 'react';
import { Mic, MicOff, Volume2, ShieldAlert, CheckCircle2, AlertCircle } from 'lucide-react';
import { classifyTestAudio } from '../services/api';

/**
 * First-harmonic peak picking autocorrelation pitch detector (80 Hz - 850 Hz).
 * Prevents sub-harmonic octave halving error (e.g., 450 Hz detected as 225 Hz).
 */
function detectPitch(buffer, sampleRate = 16000) {
  const minLag = Math.floor(sampleRate / 850); // ~18 samples (850 Hz)
  const maxLag = Math.floor(sampleRate / 80);  // ~200 samples (80 Hz)

  let energy = 0;
  for (let i = 0; i < buffer.length; i++) {
    energy += buffer[i] * buffer[i];
  }

  if (energy < 0.005) return { pitch: 0, periodicity: 0 };

  const normCorr = new Float32Array(maxLag + 1);
  for (let lag = minLag; lag <= maxLag; lag++) {
    let sum = 0;
    for (let i = 0; i < buffer.length - lag; i++) {
      sum += buffer[i] * buffer[i + lag];
    }
    normCorr[lag] = sum / energy;
  }

  // Find all local maxima in [minLag, maxLag]
  const peaks = [];
  for (let lag = minLag + 1; lag < maxLag; lag++) {
    if (normCorr[lag] > normCorr[lag - 1] && normCorr[lag] >= normCorr[lag + 1]) {
      peaks.push({ lag, val: normCorr[lag] });
    }
  }

  if (peaks.length === 0) return { pitch: 0, periodicity: 0 };

  let globalMax = 0;
  for (let i = 0; i < peaks.length; i++) {
    if (peaks[i].val > globalMax) globalMax = peaks[i].val;
  }

  if (globalMax < 0.22) return { pitch: 0, periodicity: globalMax };

  // First local maximum that reaches at least 70% of globalMax is the fundamental F0
  const threshold = Math.max(0.22, globalMax * 0.70);
  let fundamentalLag = peaks[0].lag;
  for (let i = 0; i < peaks.length; i++) {
    if (peaks[i].val >= threshold) {
      fundamentalLag = peaks[i].lag;
      break;
    }
  }

  const pitch = sampleRate / fundamentalLag;
  return { pitch, periodicity: globalMax };
}

/**
 * Encodes Float32Array PCM samples into a standard 16-bit Mono WAV Blob
 */
function encodeWavBlob(samples, sampleRate = 16000) {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);

  const writeString = (offset, str) => {
    for (let i = 0; i < str.length; i++) {
      view.setUint8(offset + i, str.charCodeAt(i));
    }
  };

  writeString(0, 'RIFF');
  view.setUint32(4, 36 + samples.length * 2, true);
  writeString(8, 'WAVE');
  writeString(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeString(36, 'data');
  view.setUint32(40, samples.length * 2, true);

  let offset = 44;
  for (let i = 0; i < samples.length; i++, offset += 2) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
  }

  return new Blob([view], { type: 'audio/wav' });
}

export default function LiveMicClassifier({ onTestComplete }) {
  const [isListening, setIsListening] = useState(false);
  const [micVolume, setMicVolume] = useState(0);
  const [soundClassification, setSoundClassification] = useState(null);
  const [errorMessage, setErrorMessage] = useState(null);

  const streamRef = useRef(null);
  const audioContextRef = useRef(null);
  const analyserRef = useRef(null);
  const animFrameRef = useRef(null);
  const isClassifyingRef = useRef(false);
  const audioBufferRef = useRef([]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stopListening();
    };
  }, []);

  const startListening = async () => {
    setErrorMessage(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: false,
          noiseSuppression: false,
          autoGainControl: false,
        }
      });
      streamRef.current = stream;

      const audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
      audioContextRef.current = audioCtx;

      const source = audioCtx.createMediaStreamSource(stream);
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 2048;
      analyserRef.current = analyser;

      const processor = audioCtx.createScriptProcessor(4096, 1, 1);

      audioBufferRef.current = [];

      processor.onaudioprocess = (e) => {
        const input = e.inputBuffer.getChannelData(0);
        audioBufferRef.current.push(new Float32Array(input));

        // When we have accumulated ~1.5s of audio (approx 24000 samples @ 16kHz)
        const totalSamples = audioBufferRef.current.reduce((acc, c) => acc + c.length, 0);
        if (totalSamples >= 24000 && !isClassifyingRef.current) {
          const chunkToProcess = audioBufferRef.current.slice();
          audioBufferRef.current = [];
          analyzeAudioChunk(chunkToProcess, audioCtx.sampleRate);
        }
      };

      source.connect(analyser);
      analyser.connect(processor);
      processor.connect(audioCtx.destination);

      setIsListening(true);
      monitorVolume();
    } catch (err) {
      setErrorMessage("Microphone access denied: " + err.message);
      setIsListening(false);
    }
  };

  const stopListening = () => {
    if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
      audioContextRef.current.close().catch(() => {});
      audioContextRef.current = null;
    }
    setIsListening(false);
    setMicVolume(0);
  };

  // Real-time visual audio meter
  const monitorVolume = () => {
    if (!analyserRef.current) return;
    const dataArray = new Uint8Array(analyserRef.current.frequencyBinCount);
    analyserRef.current.getByteFrequencyData(dataArray);

    let sum = 0;
    for (let i = 0; i < dataArray.length; i++) {
      sum += dataArray[i];
    }
    const avg = sum / dataArray.length;
    const volPercent = Math.min(100, Math.round((avg / 128) * 100));
    setMicVolume(volPercent);

    animFrameRef.current = requestAnimationFrame(monitorVolume);
  };

  // Analyze sound chunk
  const analyzeAudioChunk = async (chunks, sampleRate) => {
    isClassifyingRef.current = true;
    try {
      const totalLen = chunks.reduce((acc, c) => acc + c.length, 0);
      const merged = new Float32Array(totalLen);
      let offset = 0;
      for (const chunk of chunks) {
        merged.set(chunk, offset);
        offset += chunk.length;
      }

      // 1. Calculate sound level (RMS and dB)
      let sumSq = 0;
      for (let i = 0; i < merged.length; i++) {
        sumSq += merged[i] * merged[i];
      }
      const rms = Math.sqrt(sumSq / merged.length);
      const db = Math.round(20 * Math.log10(Math.max(rms, 1e-4) * 32768));

      // 2. Client-side pitch detection with calibrated bounds
      const { pitch, periodicity } = detectPitch(merged, sampleRate);
      const isInfantPitch = pitch >= 300 && pitch <= 720 && periodicity >= 0.22;

      let isBaby = false;
      let label = "NOT BABY SOUND";
      let details = "Normal Ambient Sound";
      let confidence = 85;

      if (db < 38) {
        label = "QUIET / AMBIENT";
        details = "Room is quiet";
        confidence = 95;
      } else if (isInfantPitch && db >= 40) {
        isBaby = true;
        label = "BABY SOUND DETECTED";
        details = `Infant crying pitch detected (${Math.round(pitch)} Hz)`;
        confidence = 92;
      } else {
        isBaby = false;
        label = "NOT BABY SOUND";
        details = pitch > 0 ? `Adult voice / noise (${Math.round(pitch)} Hz)` : "Room noise / not baby cry";
        confidence = 85;
      }

      // Update immediate UI classification
      setSoundClassification({
        isBaby,
        label,
        details,
        soundLevel: db,
        pitch: Math.round(pitch),
        confidence,
        timestamp: new Date().toLocaleTimeString(),
      });

      // 3. Send to Google YAMNet neural network on cloud backend in parallel
      try {
        const wavBlob = encodeWavBlob(merged, 16000);
        const serverResult = await classifyTestAudio(wavBlob);

        const serverIsBaby = serverResult?.classification === "POSSIBLE_CRYING";
        const topClass = serverResult?.top_classes?.[0]?.class_name || "";
        const finalIsBaby = serverIsBaby || isBaby;

        setSoundClassification({
          isBaby: finalIsBaby,
          label: finalIsBaby ? "BABY SOUND DETECTED" : (db < 38 ? "QUIET / AMBIENT" : "NOT BABY SOUND"),
          details: finalIsBaby
            ? (serverIsBaby ? `Google YAMNet: ${topClass || "Infant Cry"}` : `Infant crying pitch detected (${Math.round(pitch)} Hz)`)
            : `Classified as: ${topClass || "Non-baby sound"}`,
          soundLevel: db,
          pitch: Math.round(pitch),
          confidence: Math.round((serverResult?.confidence || (confidence / 100)) * 100),
          yamnetClass: topClass,
          timestamp: new Date().toLocaleTimeString(),
        });

        if (onTestComplete) onTestComplete();
      } catch (backendErr) {
        // Local pitch detection continues with zero interruption
        console.warn("Backend classification fallback:", backendErr);
      }
    } catch (err) {
      console.error("Audio processing error:", err);
    } finally {
      isClassifyingRef.current = false;
    }
  };

  return (
    <div className="glass-panel rounded-2xl p-5 border border-slate-800 transition-all">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        
        {/* Title & Info */}
        <div className="flex items-center gap-3">
          <div className={`p-2.5 rounded-xl border transition ${
            isListening 
              ? 'bg-rose-500/15 text-rose-400 border-rose-500/30 animate-pulse' 
              : 'bg-indigo-500/15 text-indigo-400 border-indigo-500/30'
          }`}>
            <Mic className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-base font-bold text-white tracking-tight flex items-center gap-2">
              Live Microphone Baby Sound Classifier
              {isListening && (
                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-500/20 text-rose-400 border border-rose-500/40 animate-pulse">
                  LISTENING LIVE
                </span>
              )}
            </h3>
            <p className="text-xs text-slate-400">
              Listens to your microphone and immediately identifies whether it is a Baby Sound or Not
            </p>
          </div>
        </div>

        {/* Start / Stop Toggle Button */}
        <button
          onClick={isListening ? stopListening : startListening}
          className={`flex items-center gap-2 px-5 py-2.5 rounded-xl text-xs font-bold transition shadow-lg ${
            isListening
              ? 'bg-rose-600 hover:bg-rose-500 text-white shadow-rose-950/50'
              : 'bg-indigo-600 hover:bg-indigo-500 text-white shadow-indigo-950/50'
          }`}
        >
          {isListening ? (
            <>
              <MicOff className="w-4 h-4" />
              <span>Stop Microphone</span>
            </>
          ) : (
            <>
              <Mic className="w-4 h-4" />
              <span>Start Microphone Monitoring</span>
            </>
          )}
        </button>
      </div>

      {/* Error Message */}
      {errorMessage && (
        <div className="mt-4 p-3 rounded-xl bg-rose-950/60 border border-rose-500/40 text-xs text-rose-300 flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0 text-rose-400" />
          <span>{errorMessage}</span>
        </div>
      )}

      {/* Live Audio Visualizer Bar */}
      {isListening && (
        <div className="mt-4 pt-4 border-t border-slate-800/80">
          <div className="flex items-center justify-between text-xs text-slate-400 mb-1.5 font-mono">
            <span className="flex items-center gap-1.5">
              <Volume2 className="w-3.5 h-3.5 text-indigo-400" />
              Microphone Sound Input
            </span>
            <span>{micVolume}%</span>
          </div>
          <div className="w-full bg-slate-900 h-2 rounded-full overflow-hidden border border-slate-800">
            <div
              className={`h-full transition-all duration-75 rounded-full ${
                micVolume > 60
                  ? 'bg-rose-500'
                  : micVolume > 30
                  ? 'bg-amber-500'
                  : 'bg-emerald-500'
              }`}
              style={{ width: `${Math.max(4, micVolume)}%` }}
            />
          </div>
        </div>
      )}

      {/* Classification Result Display */}
      {soundClassification && (
        <div className="mt-4 p-4 rounded-xl bg-slate-900/90 border border-slate-800 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div
              className={`p-3 rounded-xl border ${
                soundClassification.isBaby
                  ? 'bg-rose-500/20 text-rose-400 border-rose-500/40 animate-pulse'
                  : 'bg-sky-500/20 text-sky-400 border-sky-500/40'
              }`}
            >
              {soundClassification.isBaby ? (
                <ShieldAlert className="w-7 h-7" />
              ) : (
                <CheckCircle2 className="w-7 h-7" />
              )}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span
                  className={`text-sm font-black tracking-wide uppercase px-2.5 py-0.5 rounded-lg border ${
                    soundClassification.isBaby
                      ? 'bg-rose-500 text-white border-rose-400 animate-pulse'
                      : 'bg-slate-800 text-slate-300 border-slate-700'
                  }`}
                >
                  {soundClassification.isBaby ? '👶 BABY SOUND DETECTED' : '🔊 NOT BABY SOUND'}
                </span>
                <span className="text-xs text-slate-500 font-mono">
                  {soundClassification.timestamp}
                </span>
              </div>
              <p className="text-xs font-medium text-slate-300 mt-1">
                {soundClassification.details}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-4 text-xs font-mono text-slate-400 border-t sm:border-t-0 sm:border-l border-slate-800 pt-2 sm:pt-0 sm:pl-4">
            <div>
              <div className="text-[10px] text-slate-500 uppercase">Sound Level</div>
              <div className="text-sm font-bold text-white">{soundClassification.soundLevel} dB</div>
            </div>
            <div>
              <div className="text-[10px] text-slate-500 uppercase">Confidence</div>
              <div className="text-sm font-bold text-emerald-400">{soundClassification.confidence}%</div>
            </div>
            {soundClassification.pitch > 0 && (
              <div>
                <div className="text-[10px] text-slate-500 uppercase">Pitch</div>
                <div className="text-sm font-bold text-sky-400">{soundClassification.pitch} Hz</div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
