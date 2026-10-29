import React, { useState, useRef } from 'react';
import { Mic, Upload, Play, CheckCircle2, AlertTriangle, Sparkles, Volume2, Music, UserCheck, ShieldAlert, X } from 'lucide-react';
import { classifyTestAudio } from '../services/api';

/**
 * Encodes Float32Array PCM samples into a standard 16-bit Mono WAV Blob
 */
function encodeWavBlob(samples, sampleRate = 16000) {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);

  // Helper to write ASCII strings
  const writeString = (offset, str) => {
    for (let i = 0; i < str.length; i++) {
      view.setUint8(offset + i, str.charCodeAt(i));
    }
  };

  // RIFF chunk descriptor
  writeString(0, 'RIFF');
  view.setUint32(4, 36 + samples.length * 2, true);
  writeString(8, 'WAVE');

  // "fmt " sub-chunk
  writeString(12, 'fmt ');
  view.setUint32(16, 16, true);          // Subchunk1Size (16 for PCM)
  view.setUint16(20, 1, true);           // AudioFormat (1 for PCM)
  view.setUint16(22, 1, true);           // NumChannels (1 mono)
  view.setUint32(24, sampleRate, true);  // SampleRate
  view.setUint32(28, sampleRate * 2, true); // ByteRate (SampleRate * NumChannels * BitsPerSample/8)
  view.setUint16(32, 2, true);           // BlockAlign (NumChannels * BitsPerSample/8)
  view.setUint16(34, 16, true);          // BitsPerSample (16 bits)

  // "data" sub-chunk
  writeString(36, 'data');
  view.setUint32(40, samples.length * 2, true);

  // Write PCM audio samples
  let offset = 44;
  for (let i = 0; i < samples.length; i++, offset += 2) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
  }

  return new Blob([view], { type: 'audio/wav' });
}

export default function AudioClassifierTest({ onTestComplete }) {
  const [isRecording, setIsRecording] = useState(false);
  const [countdown, setCountdown] = useState(0);
  const [isProcessing, setIsProcessing] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [isOpen, setIsOpen] = useState(false);
  const fileInputRef = useRef(null);

  // 1. Microphone capture (2.0 seconds @ 16kHz)
  const handleRecordMic = async () => {
    setError(null);
    setIsRecording(true);
    setCountdown(2);

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
      const source = audioCtx.createMediaStreamSource(stream);
      const processor = audioCtx.createScriptProcessor(4096, 1, 1);

      const capturedSamples = [];
      processor.onaudioprocess = (e) => {
        const input = e.inputBuffer.getChannelData(0);
        capturedSamples.push(new Float32Array(input));
      };

      source.connect(processor);
      processor.connect(audioCtx.destination);

      let timeLeft = 2;
      const timer = setInterval(() => {
        timeLeft -= 1;
        setCountdown(timeLeft);
      }, 1000);

      // Stop after 2.0 seconds
      setTimeout(async () => {
        clearInterval(timer);
        source.disconnect();
        processor.disconnect();
        stream.getTracks().forEach(t => t.stop());
        await audioCtx.close();
        setIsRecording(false);
        setIsProcessing(true);

        try {
          // Flatten samples
          const totalLen = capturedSamples.reduce((sum, chunk) => sum + chunk.length, 0);
          const merged = new Float32Array(totalLen);
          let offset = 0;
          for (const chunk of capturedSamples) {
            merged.set(chunk, offset);
            offset += chunk.length;
          }

          const wavBlob = encodeWavBlob(merged, 16000);
          const data = await classifyTestAudio(wavBlob);
          setResult(data);
          if (onTestComplete) onTestComplete();
        } catch (err) {
          setError(err.message || 'Classification failed');
        } finally {
          setIsProcessing(false);
        }
      }, 2000);

    } catch (err) {
      setIsRecording(false);
      setError('Microphone access denied or unavailable: ' + err.message);
    }
  };

  // 2. Upload and test audio file
  const handleFileUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setError(null);
    setIsProcessing(true);

    try {
      const arrayBuffer = await file.arrayBuffer();
      const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      const decodedBuffer = await audioCtx.decodeAudioData(arrayBuffer);

      // Take first 3 seconds max, mono
      const sampleRate = decodedBuffer.sampleRate;
      const maxSamples = Math.min(decodedBuffer.length, sampleRate * 3);
      const monoSamples = new Float32Array(maxSamples);

      // Downmix to mono
      for (let ch = 0; ch < decodedBuffer.numberOfChannels; ch++) {
        const chData = decodedBuffer.getChannelData(ch);
        for (let i = 0; i < maxSamples; i++) {
          monoSamples[i] += chData[i] / decodedBuffer.numberOfChannels;
        }
      }
      await audioCtx.close();

      // Resample to 16000 Hz if needed
      let finalSamples = monoSamples;
      if (sampleRate !== 16000) {
        const targetLen = Math.floor(maxSamples * 16000 / sampleRate);
        finalSamples = new Float32Array(targetLen);
        for (let i = 0; i < targetLen; i++) {
          const origIdx = (i * sampleRate) / 16000;
          const idx0 = Math.floor(origIdx);
          const idx1 = Math.min(idx0 + 1, maxSamples - 1);
          const frac = origIdx - idx0;
          finalSamples[i] = monoSamples[idx0] * (1 - frac) + monoSamples[idx1] * frac;
        }
      }

      const wavBlob = encodeWavBlob(finalSamples, 16000);
      const data = await classifyTestAudio(wavBlob);
      setResult(data);
      if (onTestComplete) onTestComplete();
    } catch (err) {
      setError('File processing error: ' + (err.message || 'Unsupported audio format'));
    } finally {
      setIsProcessing(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  // 3. Synthetic Baby Cry Generator (1.5s, 480 Hz with vibrato)
  const handleTestSyntheticCry = async () => {
    setError(null);
    setIsProcessing(true);

    try {
      const sampleRate = 16000;
      const duration = 1.5;
      const totalSamples = Math.floor(sampleRate * duration);
      const samples = new Float32Array(totalSamples);

      let phase = 0;
      for (let i = 0; i < totalSamples; i++) {
        const t = i / sampleRate;
        const f0 = 480 + 35 * Math.sin(2 * Math.PI * 4.5 * t);
        phase += 2 * Math.PI * f0 / sampleRate;

        // Infant cry harmonic structure with high-pitch vibrato
        const s =
          0.70 * Math.sin(phase) +
          0.35 * Math.sin(2 * phase) +
          0.20 * Math.sin(3 * phase);

        // Amplitude envelope (wailing burst)
        const envelope = Math.sin(Math.PI * t / duration);
        samples[i] = s * envelope * 0.8;
      }

      const wavBlob = encodeWavBlob(samples, 16000);
      const data = await classifyTestAudio(wavBlob);
      setResult(data);
      if (onTestComplete) onTestComplete();
    } catch (err) {
      setError(err.message || 'Synthetic test failed');
    } finally {
      setIsProcessing(false);
    }
  };

  // 4. Synthetic Adult Speech Generator (1.5s, 130 Hz fundamental)
  const handleTestSyntheticSpeech = async () => {
    setError(null);
    setIsProcessing(true);

    try {
      const sampleRate = 16000;
      const duration = 1.5;
      const totalSamples = Math.floor(sampleRate * duration);
      const samples = new Float32Array(totalSamples);

      let phase = 0;
      for (let i = 0; i < totalSamples; i++) {
        const t = i / sampleRate;
        const f0 = 130; // Adult voice range (85-180 Hz)
        phase += 2 * Math.PI * f0 / sampleRate;

        const s =
          0.60 * Math.sin(phase) +
          0.30 * Math.sin(2 * phase) +
          0.15 * Math.sin(3 * phase);

        const envelope = Math.sin(Math.PI * t / duration);
        samples[i] = s * envelope * 0.7;
      }

      const wavBlob = encodeWavBlob(samples, 16000);
      const data = await classifyTestAudio(wavBlob);
      setResult(data);
      if (onTestComplete) onTestComplete();
    } catch (err) {
      setError(err.message || 'Speech test failed');
    } finally {
      setIsProcessing(false);
    }
  };

  const isBabyCry = result?.classification === 'POSSIBLE_CRYING';

  return (
    <div className="glass-panel rounded-2xl p-5 border border-slate-800 transition-all">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 mb-4">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-xl bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
            <Sparkles className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-base font-bold text-white tracking-tight flex items-center gap-2">
              Google YAMNet Audio Classifier Test Bench
              <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
                AudioSet 521 Classes
              </span>
            </h3>
            <p className="text-xs text-slate-400">
              Test neural sound differentiation live with your microphone, an audio file, or sound presets
            </p>
          </div>
        </div>

        <button
          onClick={() => setIsOpen(!isOpen)}
          className="text-xs font-semibold px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition"
        >
          {isOpen ? 'Hide Test Bench' : 'Open Test Bench'}
        </button>
      </div>

      {isOpen && (
        <div className="mt-4 pt-4 border-t border-slate-800/80 space-y-4">
          {/* Action Buttons Row */}
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-2.5">
            {/* Record Mic */}
            <button
              onClick={handleRecordMic}
              disabled={isRecording || isProcessing}
              className={`flex items-center justify-center gap-2 py-2.5 px-3 rounded-xl text-xs font-semibold border transition ${
                isRecording
                  ? 'bg-rose-500/20 text-rose-300 border-rose-500/50 animate-pulse'
                  : 'bg-indigo-600 hover:bg-indigo-500 text-white border-indigo-500'
              }`}
            >
              <Mic className="w-4 h-4" />
              {isRecording ? `Recording... (${countdown}s)` : '🎙️ Record Mic (2s)'}
            </button>

            {/* Upload File */}
            <label
              className={`flex items-center justify-center gap-2 py-2.5 px-3 rounded-xl text-xs font-semibold border cursor-pointer transition ${
                isProcessing
                  ? 'bg-slate-800 text-slate-500 border-slate-700 pointer-events-none'
                  : 'bg-slate-800 hover:bg-slate-700 text-slate-200 border-slate-700'
              }`}
            >
              <Upload className="w-4 h-4 text-violet-400" />
              <span>📁 Upload Audio (.wav, .mp3)</span>
              <input
                ref={fileInputRef}
                type="file"
                accept="audio/*"
                onChange={handleFileUpload}
                disabled={isProcessing || isRecording}
                className="hidden"
              />
            </label>

            {/* Test Baby Cry Preset */}
            <button
              onClick={handleTestSyntheticCry}
              disabled={isRecording || isProcessing}
              className="flex items-center justify-center gap-2 py-2.5 px-3 rounded-xl text-xs font-semibold bg-rose-500/10 hover:bg-rose-500/20 text-rose-300 border border-rose-500/30 transition"
            >
              <Volume2 className="w-4 h-4 text-rose-400" />
              <span>👶 Test Baby Cry Audio</span>
            </button>

            {/* Test Speech Preset */}
            <button
              onClick={handleTestSyntheticSpeech}
              disabled={isRecording || isProcessing}
              className="flex items-center justify-center gap-2 py-2.5 px-3 rounded-xl text-xs font-semibold bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 border border-amber-500/30 transition"
            >
              <UserCheck className="w-4 h-4 text-amber-400" />
              <span>🗣️ Test Speech (High Sound)</span>
            </button>
          </div>

          {/* Loading status */}
          {isProcessing && (
            <div className="p-4 rounded-xl bg-slate-900 border border-indigo-500/30 text-center text-xs text-indigo-300 animate-pulse">
              Running Google YAMNet ONNX neural inference on audio sample...
            </div>
          )}

          {/* Error Message */}
          {error && (
            <div className="p-3 rounded-xl bg-rose-950/60 border border-rose-500/40 text-xs text-rose-300 flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 shrink-0 text-rose-400" />
              <span>{error}</span>
            </div>
          )}

          {/* Classification Results Card */}
          {result && !isProcessing && (
            <div className="p-4 rounded-xl bg-slate-900/90 border border-slate-800 space-y-3">
              <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 border-b border-slate-800 pb-3">
                <div className="flex items-center gap-2.5">
                  <div
                    className={`p-2 rounded-xl border ${
                      isBabyCry
                        ? 'bg-rose-500/20 text-rose-400 border-rose-500/40'
                        : 'bg-amber-500/20 text-amber-400 border-amber-500/40'
                    }`}
                  >
                    {isBabyCry ? <ShieldAlert className="w-5 h-5 animate-pulse" /> : <Volume2 className="w-5 h-5" />}
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs uppercase tracking-wider text-slate-400 font-semibold font-sans">
                        AI Classification Output
                      </span>
                      <span
                        className={`px-2 py-0.5 rounded text-[11px] font-bold border ${
                          isBabyCry
                            ? 'bg-rose-500/20 text-rose-400 border-rose-500/40 animate-pulse'
                            : 'bg-amber-500/20 text-amber-400 border-amber-500/40'
                        }`}
                      >
                        {isBabyCry ? '👶 POSSIBLE BABY CRYING' : '🔊 OTHER SOUND ACTIVITY'}
                      </span>
                    </div>
                    <p className="text-sm font-bold text-white mt-0.5">
                      {isBabyCry
                        ? 'Infant vocalization patterns detected matching baby crying'
                        : 'Sound is elevated (e.g., speech/applause/ambient), successfully NOT classified as crying'}
                    </p>
                  </div>
                </div>

                <div className="text-right">
                  <div className="text-xs text-slate-400 font-mono">
                    Volume: <strong className="text-white">{result.sound_level_db} dB</strong>
                  </div>
                  <div className="text-xs text-slate-400 font-mono">
                    Confidence: <strong className="text-emerald-400">{Math.round((result.confidence || 0) * 100)}%</strong>
                  </div>
                </div>
              </div>

              {/* Top Google AudioSet Neural Predictions */}
              <div>
                <h4 className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-2 font-mono">
                  Google AudioSet Neural Probabilities (Top Classes)
                </h4>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {(result.top_classes || []).map((c, idx) => {
                    const scorePct = Math.round(c.score * 100);
                    const isCryClass = c.class_name.toLowerCase().includes('cry') || c.class_name.toLowerCase().includes('baby');
                    return (
                      <div
                        key={idx}
                        className={`p-2.5 rounded-lg border text-xs flex items-center justify-between font-mono ${
                          isCryClass
                            ? 'bg-rose-950/40 border-rose-500/40 text-rose-200'
                            : 'bg-slate-950/60 border-slate-800 text-slate-300'
                        }`}
                      >
                        <div className="flex items-center gap-2 truncate">
                          <span className="text-slate-500 text-[10px]">#{idx + 1}</span>
                          <span className={`font-sans truncate ${isCryClass ? 'font-bold text-rose-300' : ''}`}>
                            {c.class_name}
                          </span>
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          <div className="w-16 bg-slate-800 h-1.5 rounded-full overflow-hidden">
                            <div
                              className={`h-full rounded-full ${isCryClass ? 'bg-rose-500' : 'bg-indigo-500'}`}
                              style={{ width: `${Math.min(100, scorePct * 1.5)}%` }}
                            />
                          </div>
                          <span className="text-[11px] font-bold w-9 text-right">{scorePct}%</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
