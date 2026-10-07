import React from 'react';
import { SignalSummary } from '../types';
import { ArrowUp, ArrowDown, Minus, Volume2, VolumeX, Activity } from 'lucide-react';

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
  const isStale = signal.freshness !== "Recent observation";

  // Sparkline coordinates setup
  // X: -30s to 0s -> 55 to 525 (width 470)
  // Y: -100 dBm to -30 dBm -> 104 to 12 (height 92)
  const getX = (t: number) => {
    const clampedT = Math.max(-30, Math.min(0, t));
    return 55 + ((clampedT - (-30)) / 30) * 470;
  };

  const getY = (r: number) => {
    const clampedR = Math.max(-100, Math.min(-30, r));
    const norm = (clampedR - (-100)) / 70; // 0.0 at -100, 1.0 at -30
    return 104 - norm * 92;
  };

  const rawHistory = signal.recent_history || [];
  const points = rawHistory
    .filter((p) => p.t_rel_s >= -30.0)
    .sort((a, b) => a.t_rel_s - b.t_rel_s);

  let pathData = '';
  let areaData = '';
  if (points.length >= 2) {
    pathData = points
      .map((p, idx) => `${idx === 0 ? 'M' : 'L'} ${getX(p.t_rel_s).toFixed(1)} ${getY(p.rssi).toFixed(1)}`)
      .join(' ');
    const firstX = getX(points[0].t_rel_s).toFixed(1);
    const lastX = getX(points[points.length - 1].t_rel_s).toFixed(1);
    areaData = `${pathData} L ${lastX} 104 L ${firstX} 104 Z`;
  }

  return (
    <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6 flex flex-col gap-5">
      {/* Top Header: Gauge Name, Freshness, Audio Toggle */}
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

      {/* Main Signal Readout & Stationary Summary */}
      <div className="flex flex-col md:flex-row items-center justify-between gap-6 py-1">
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

        {/* 20-Second Stationary Summary & Directional Trend */}
        <div className="flex flex-wrap items-center gap-6 bg-slate-50 px-4 py-3 rounded-xl border border-slate-100 w-full md:w-auto">
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
            <div className="text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-1">
              Directional Trend (20s)
            </div>
            <div>
              {signal.trend_20s === "Stronger" && (
                <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800 border border-emerald-300">
                  <ArrowUp size={14} className="stroke-[3]" />
                  <span>+{signal.trend_diff_db} dB (User is closing in)</span>
                </span>
              )}
              {signal.trend_20s === "Weaker" && (
                <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-rose-100 text-rose-800 border border-rose-300">
                  <ArrowDown size={14} className="stroke-[3]" />
                  <span>{signal.trend_diff_db} dB (User is moving away)</span>
                </span>
              )}
              {signal.trend_20s === "Stable" && (
                <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-slate-100 text-slate-700 border border-slate-300">
                  <Minus size={14} className="stroke-[3]" />
                  <span>Stable Distance</span>
                </span>
              )}
              {signal.trend_20s === "Insufficient Data" && (
                <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-slate-100 text-slate-500 border border-slate-200">
                  <span>Insufficient Data</span>
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Progress Bar Gauge */}
      <div className="w-full bg-slate-100 h-3 rounded-full overflow-hidden p-0.5 border border-slate-200">
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

      {/* STEP C: Responsive SVG Area Sparkline for Target RSSI History */}
      <div className="bg-slate-50/80 rounded-xl border border-slate-200/80 p-3 pt-2">
        <div className="flex items-center justify-between mb-1 px-1">
          <div className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-slate-500">
            <Activity size={14} className="text-blue-600" />
            <span>Target RSSI History (-30s to 0s)</span>
          </div>
          <span className="text-[11px] text-slate-400 font-mono">
            Scale: -100 to -30 dBm
          </span>
        </div>

        <div className="w-full h-32 overflow-hidden">
          <svg
            viewBox="0 0 540 130"
            className="w-full h-full select-none"
            preserveAspectRatio="none"
          >
            <defs>
              <linearGradient id="sparklineGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#2563eb" stopOpacity="0.32" />
                <stop offset="60%" stopColor="#3b82f6" stopOpacity="0.12" />
                <stop offset="100%" stopColor="#3b82f6" stopOpacity="0.0" />
              </linearGradient>
            </defs>

            {/* Grid Reference Lines */}
            {/* -50 dBm (Close) -> Y=38.3 */}
            <line x1="55" y1="38.3" x2="525" y2="38.3" stroke="#cbd5e1" strokeDasharray="3 3" />
            <text x="50" y="41.5" textAnchor="end" fill="#64748b" fontSize="9.5" fontWeight="600">
              -50 (Close)
            </text>

            {/* -70 dBm (Medium) -> Y=64.6 */}
            <line x1="55" y1="64.6" x2="525" y2="64.6" stroke="#e2e8f0" strokeDasharray="3 3" />
            <text x="50" y="67.5" textAnchor="end" fill="#94a3b8" fontSize="9.5" fontWeight="500">
              -70 (Med)
            </text>

            {/* -90 dBm (Weak) -> Y=90.9 */}
            <line x1="55" y1="90.9" x2="525" y2="90.9" stroke="#e2e8f0" strokeDasharray="3 3" />
            <text x="50" y="93.5" textAnchor="end" fill="#94a3b8" fontSize="9.5" fontWeight="500">
              -90 (Weak)
            </text>

            {/* Bottom Base Line (Y=104) */}
            <line x1="55" y1="104" x2="525" y2="104" stroke="#e2e8f0" strokeWidth="1" />

            {/* Data Area & Line */}
            {points.length >= 2 ? (
              <>
                <path d={areaData} fill="url(#sparklineGrad)" />
                <path
                  d={pathData}
                  fill="none"
                  stroke="#2563eb"
                  strokeWidth="2.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                {/* Latest point indicator */}
                {(() => {
                  const last = points[points.length - 1];
                  const lx = getX(last.t_rel_s);
                  const ly = getY(last.rssi);
                  return (
                    <g>
                      <circle cx={lx} cy={ly} r="6" fill="#3b82f6" opacity="0.25" />
                      <circle cx={lx} cy={ly} r="3.5" fill="#1d4ed8" />
                    </g>
                  );
                })()}
              </>
            ) : (
              /* Fallback if fewer than 2 points are available */
              <g>
                <line x1="55" y1="64.6" x2="525" y2="64.6" stroke="#cbd5e1" strokeDasharray="4 4" />
                <text x="290" y="68" textAnchor="middle" fill="#94a3b8" fontSize="11" fontWeight="500">
                  Awaiting history...
                </text>
              </g>
            )}

            {/* Time Axis Labels */}
            <text x="55" y="122" textAnchor="start" fill="#94a3b8" fontSize="9.5" fontWeight="500">
              -30s
            </text>
            <text x="211" y="122" textAnchor="middle" fill="#94a3b8" fontSize="9.5" fontWeight="500">
              -20s
            </text>
            <text x="368" y="122" textAnchor="middle" fill="#94a3b8" fontSize="9.5" fontWeight="500">
              -10s
            </text>
            <text x="525" y="122" textAnchor="end" fill="#64748b" fontSize="9.5" fontWeight="700">
              0s (Now)
            </text>
          </svg>
        </div>
      </div>
    </div>
  );
};
