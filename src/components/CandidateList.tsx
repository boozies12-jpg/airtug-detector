import React from 'react';
import { BleDeviceItem } from '../types';
import { Pin, CheckCircle2 } from 'lucide-react';

interface CandidateListProps {
  candidates: BleDeviceItem[];
  selectedAddress: string | null;
  onSelectCandidate: (address: string) => void;
  onTogglePin: (address: string, e: React.MouseEvent) => void;
}

export const CandidateList: React.FC<CandidateListProps> = ({
  candidates,
  selectedAddress,
  onSelectCandidate,
  onTogglePin
}) => {
  const protocolMatches = candidates.filter(
    (c) => c.classification.candidate_group === "protocol_match"
  );
  const possibleTrackers = candidates.filter(
    (c) => c.classification.candidate_group === "possible_tracker"
  );

  const renderItem = (item: BleDeviceItem) => {
    const isSelected = item.address === selectedAddress;
    const rssi = item.signal.current_rssi;

    return (
      <div
        key={item.address}
        onClick={() => onSelectCandidate(item.address)}
        className={`p-3.5 sm:p-4 rounded-xl border transition-all cursor-pointer flex items-center justify-between gap-3 ${
          isSelected
            ? "border-blue-500 bg-blue-50/60 shadow-sm"
            : "border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50/50"
        }`}
      >
        <div className="flex items-start gap-2.5 sm:gap-3 min-w-0 flex-1">
          <button
            onClick={(e) => onTogglePin(item.address, e)}
            className={`p-1.5 rounded-lg transition-colors shrink-0 mt-0.5 ${
              item.is_pinned
                ? "text-blue-600 bg-blue-100"
                : "text-slate-300 hover:text-slate-500 hover:bg-slate-100"
            }`}
          >
            <Pin size={18} />
          </button>

          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1.5 sm:gap-2 flex-wrap">
              <span className="font-bold text-slate-800 text-sm truncate">
                {item.classification.brand || item.classification.protocol_family || "Unknown Network"}
              </span>
              {item.classification.model && (
                <span className="text-[11px] font-semibold px-2 py-0.5 rounded bg-blue-100 text-blue-700 shrink-0">
                  {item.classification.model}
                </span>
              )}
              {item.is_found && (
                <span className="flex items-center gap-1 text-[11px] font-bold px-2 py-0.5 rounded bg-emerald-100 text-emerald-700 shrink-0">
                  <CheckCircle2 size={12} /> Found
                </span>
              )}
            </div>

            <div className="text-xs text-slate-500 font-mono mt-0.5 truncate">
              {item.address}
              {item.local_name && (
                <span className="ml-2 font-sans font-medium text-slate-600">
                  "{item.local_name}"
                </span>
              )}
            </div>

            <div className="text-xs text-slate-400 mt-1 truncate">
              {item.classification.status_text}
            </div>
          </div>
        </div>

        <div className="text-right flex flex-col items-end shrink-0 pl-1">
          <span className="text-lg font-black text-slate-700 whitespace-nowrap">
            {rssi !== null ? `${rssi}` : "--"}{" "}
            <span className="text-xs font-semibold text-slate-400">dBm</span>
          </span>
          <span className="text-[11px] text-slate-400 font-medium whitespace-nowrap">
            {item.signal.current_age_s}s ago
          </span>
        </div>
      </div>
    );
  };

  return (
    <div className="flex flex-col gap-6">
      {/* Group 1: Protocol Matches */}
      <div>
        <div className="flex items-center justify-between mb-2 px-1">
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500">
            Protocol Matches ({protocolMatches.length})
          </h3>
          <span className="text-[11px] text-slate-400 font-medium">
            Confirmed finding network format
          </span>
        </div>
        {protocolMatches.length === 0 ? (
          <div className="p-4 bg-white rounded-xl border border-dashed border-slate-200 text-center text-xs text-slate-400">
            No confirmed protocol matches observed yet.
          </div>
        ) : (
          <div className="flex flex-col gap-2">{protocolMatches.map(renderItem)}</div>
        )}
      </div>

      {/* Group 2: Possible Trackers */}
      <div>
        <div className="flex items-center justify-between mb-2 px-1">
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500">
            Possible Trackers ({possibleTrackers.length})
          </h3>
          <span className="text-[11px] text-slate-400 font-medium">
            Provisional & experimental signatures
          </span>
        </div>
        {possibleTrackers.length === 0 ? (
          <div className="p-4 bg-white rounded-xl border border-dashed border-slate-200 text-center text-xs text-slate-400">
            No possible/experimental tracker signatures observed yet.
          </div>
        ) : (
          <div className="flex flex-col gap-2">{possibleTrackers.map(renderItem)}</div>
        )}
      </div>
    </div>
  );
};
