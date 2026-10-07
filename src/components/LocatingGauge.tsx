import React from 'react';
import { SignalSummary } from '../types';
import { ArrowUp, ArrowDown, Minus, Volume2, VolumeX } from 'lucide-react';

interface LocatingGaugeProps {
  signal: SignalSummary | null;
  audioEnabled: boolean;
  onToggleAudio: () => void;
}

export const LocatingGauge: React.FC<LocatingGaugeProps> = ({
  signal,
  audioEnabled,
  onToggleAudio
}) => {
  if (!signal) {
    return (
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6 text-center text-slate-400">
        No target selected for signal tracking.
      </div>
    );
  }

  const rssi = signal.current_rssi;
  // RSSI percentage (scale: -100 dBm = 0%, -30 dBm = 100%)
  const percentage = rssi !== null ? Math.max(0, Math.min(100, Math.round(((rssi - (-100)) / 70) * 100))) : 0;

  // Freshness styling
  const isFresh = signal.freshness === "Recent observation";
  const isStale = signal.freshness !== "Recent observation";

  return (
    <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6 flex flex-col gap-4">
      <div className="flex items-center justify-between border-b border-slate-100 pb-3">
        <div>
          <h2 className="text-sm font-semibold tracking-wide text-slate-500 uppercase">
            Live Locating Gauge (250ms)
          </h2>
          <div className="flex items-center gap-2 mt-0.5">
            <span
              className={`inline-block w-2.5 h-2.5 rounded-full ${
                signal.freshness === "Recent observation"
                  ? "bg-emerald-500 animate-pulse"
                  : signal.freshness === "Waiting for next observation"
                  ? "bg-amber-500"
                  : signal.freshness === "No recent signal"
                  ? "bg-orange-500"
                  : "bg-red-500"
              }`}
            />
            <span className="text-xs font-medium text-slate-600">
              {signal.freshness} ({signal.current_age_s}s ago)
            </span>
          </div>
        </div>

        <button
          onClick={onToggleAudio}
          className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-colors ${
            audioEnabled
              ? "bg-blue-600 text-white hover:bg-blue-700"
              : "bg-slate-100 text-slate-600 hover:bg-slate-200"
          }`}
        >
          {audioEnabled ? <Volume2 size={16} /> : <VolumeX size={16} />}
          <span>Audio Cue</span>
        </button>
      </div>

      {/* Main Signal Display */}
      <div className="flex flex-col md:flex-row items-center justify-between gap-6 py-2">
        <div className="flex items-baseline gap-2">
          <span
            className={`text-5xl font-black tracking-tight ${
              isStale ? "text-slate-400 opacity-60" : "text-blue-600"
            }`}
          >
            {rssi !== null ? `${rssi}` : "--"}
          </span>
          <span className="text-lg font-semibold text-slate-500">dBm</span>
          {isStale && (
            <span className="text-xs bg-slate-100 text-slate-500 font-semibold px-2 py-0.5 rounded ml-2">
              HISTORICAL
            </span>
          )}
        </div>

        {/* 20-Second Stationary Summary */}
        <div className="flex items-center gap-6 bg-slate-50 px-4 py-3 rounded-lg border border-slate-100 w-full md:w-auto">
          <div>
            <div className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">
              20s Window Summary
            </div>
            <div className="text-lg font-bold text-slate-800">
              {signal.summary_20s_median !== null ? `${signal.summary_20s_median} dBm` : "None"}
            </div>
            <div className="text-[11px] text-slate-500">
              {signal.summary_20s_count} groups, {signal.summary_20s_coverage_s}s span
            </div>
          </div>

          <div className="border-l border-slate-200 pl-4">
            <div className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">
              Trend (20s vs Prev)
            </div>
            <div className="flex items-center gap-1 mt-0.5">
              {signal.trend_20s === "Stronger" && (
                <span className="flex items-center gap-1 text-emerald-600 font-bold text-sm">
                  <ArrowUp size={16} /> Stronger (+{signal.trend_diff_db} dB)
                </span>
              )}
              {signal.trend_20s === "Weaker" && (
                <span className="flex items-center gap-1 text-rose-600 font-bold text-sm">
                  <ArrowDown size={16} /> Weaker ({signal.trend_diff_db} dB)
                </span>
              )}
              {signal.trend_20s === "Stable" && (
                <span className="flex items-center gap-1 text-slate-600 font-bold text-sm">
                  <Minus size={16} /> Stable
                </span>
              )}
              {signal.trend_20s === "Insufficient Data" && (
                <span className="text-xs text-slate-400 font-medium">Insufficient Data</span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Progress Bar Gauge */}
      <div className="w-full bg-slate-100 h-4 rounded-full overflow-hidden p-0.5 border border-slate-200">
        <div
          className={`h-full rounded-full transition-all duration-300 ${
            isStale
              ? "bg-slate-400 opacity-50"
              : percentage > 70
              ? "bg-emerald-500"
              : percentage > 40
              ? "bg-blue-500"
              : "bg-amber-500"
          }`}
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  );
};
