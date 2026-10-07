import React, { useState } from 'react';
import { BleDeviceItem } from '../types';
import { CheckCircle2, Bookmark, Send, FileText } from 'lucide-react';

interface CandidateDetailProps {
  device: BleDeviceItem | null;
  onMarkFound: (address: string, isFound: boolean, notes?: string) => void;
  onRecordCheckpoint: (label: string, notes?: string) => void;
}

export const CandidateDetail: React.FC<CandidateDetailProps> = ({
  device,
  onMarkFound,
  onRecordCheckpoint
}) => {
  const [notes, setNotes] = useState('');
  const [positionLabel, setPositionLabel] = useState('Front Seat / Luggage Bag A');
  const [showCheckpointDialog, setShowCheckpointDialog] = useState(false);

  if (!device) {
    return (
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-8 text-center text-slate-400">
        Select a candidate from the list to view evidence details and record actions.
      </div>
    );
  }

  const { classification, signal } = device;

  return (
    <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6 flex flex-col gap-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-100 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-xl font-black text-slate-800">
              {classification.brand || classification.protocol_family || "Candidate Target"}
            </h2>
            {classification.model && (
              <span className="text-xs font-bold px-2.5 py-0.5 rounded-full bg-blue-100 text-blue-700">
                {classification.model}
              </span>
            )}
          </div>
          <div className="text-xs font-mono text-slate-500 mt-1">
            MAC: {device.address} {device.local_name ? `• "${device.local_name}"` : ""}
          </div>
        </div>

        {/* Found Action Button */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => onMarkFound(device.address, !device.is_found, notes)}
            className={`px-4 py-2 rounded-xl text-xs font-bold flex items-center gap-2 transition-colors ${
              device.is_found
                ? "bg-emerald-600 text-white hover:bg-emerald-700 shadow-sm"
                : "bg-slate-100 text-slate-700 hover:bg-slate-200"
            }`}
          >
            <CheckCircle2 size={16} />
            <span>{device.is_found ? "Marked as Found" : "Mark as Found"}</span>
          </button>

          <button
            onClick={() => setShowCheckpointDialog(!showCheckpointDialog)}
            className="px-4 py-2 rounded-xl text-xs font-bold flex items-center gap-2 bg-blue-50 text-blue-700 hover:bg-blue-100 transition-colors"
          >
            <Bookmark size={16} />
            <span>Checkpoint</span>
          </button>
        </div>
      </div>

      {/* Checkpoint Recording Panel */}
      {showCheckpointDialog && (
        <div className="p-4 bg-blue-50/70 border border-blue-200 rounded-xl flex flex-col gap-3">
          <div className="flex items-center gap-2 text-xs font-bold text-blue-900">
            <Bookmark size={16} />
            <span>Record Stationary Checkpoint Measurement</span>
          </div>
          <div className="text-xs text-blue-700">
            Records stationary signal median and coverage over 30 seconds for comparing inspection locations.
          </div>
          <div className="flex flex-col sm:flex-row gap-2">
            <input
              type="text"
              placeholder="Inspection Position Label (e.g. Left Rear Wheel)"
              value={positionLabel}
              onChange={(e) => setPositionLabel(e.target.value)}
              className="flex-1 bg-white border border-blue-200 rounded-lg px-3 py-1.5 text-xs text-slate-800"
            />
            <button
              onClick={() => {
                onRecordCheckpoint(positionLabel, notes);
                setShowCheckpointDialog(false);
              }}
              className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-1.5 rounded-lg text-xs font-bold flex items-center justify-center gap-1.5"
            >
              <Send size={14} />
              <span>Save Checkpoint</span>
            </button>
          </div>
        </div>
      )}

      {/* Structured Evidence Section */}
      <div>
        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-3 flex items-center gap-1.5">
          <FileText size={14} /> Structured Technical Evidence
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 bg-slate-50 p-4 rounded-xl border border-slate-100 text-xs">
          <div>
            <span className="text-slate-400 block font-medium">Protocol Family</span>
            <span className="font-bold text-slate-700">
              {classification.protocol_family || "None"}
            </span>
          </div>
          <div>
            <span className="text-slate-400 block font-medium">Brand Provenance</span>
            <span className="font-bold text-slate-700">
              {classification.brand_source || "None (generic format)"}
            </span>
          </div>
          <div>
            <span className="text-slate-400 block font-medium">Matched Rules</span>
            <span className="font-mono text-slate-700">
              {classification.matched_rule_ids.join(", ") || "None"}
            </span>
          </div>
          <div>
            <span className="text-slate-400 block font-medium">Candidate Group</span>
            <span className="font-bold text-slate-700 capitalize">
              {classification.candidate_group?.replace("_", " ") || "Non-candidate"}
            </span>
          </div>
          <div className="sm:col-span-2">
            <span className="text-slate-400 block font-medium">Raw Payload Keys</span>
            <div className="font-mono text-[11px] text-slate-600 truncate mt-0.5">
              Service Data: {JSON.stringify(classification.evidence?.service_data_keys || [])} |
              Mfg IDs: {JSON.stringify(classification.evidence?.mfg_keys || [])}
            </div>
          </div>
        </div>
      </div>

      {/* Operator Notes Field */}
      <div>
        <label className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-2 block">
          Operator Notes & Found Item Label
        </label>
        <textarea
          rows={2}
          placeholder="Add physical description, bag tag number, or inspection notes..."
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 text-xs text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>
    </div>
  );
};
