import React, { useState, useEffect, useRef } from 'react';
import { LocatingGauge } from './components/LocatingGauge';
import { CandidateList } from './components/CandidateList';
import { CandidateDetail } from './components/CandidateDetail';
import { BleDeviceItem, AppStatus } from './types';
import { audioFeedback } from './utils/audio';
import {
  Play,
  Square,
  Search,
  Radio,
  FileDown,
  Layers,
  Sparkles,
  Clock,
  ShieldCheck
} from 'lucide-react';

export const App: React.FC = () => {
  const [status, setStatus] = useState<AppStatus | null>(null);
  const [candidates, setCandidates] = useState<BleDeviceItem[]>([]);
  const [otherDevices, setOtherDevices] = useState<BleDeviceItem[]>([]);
  const [activeTab, setActiveTab] = useState<'candidates' | 'others'>('candidates');
  const [audioEnabled, setAudioEnabled] = useState(false);
  const [sessionName, setSessionName] = useState('Search Area 1');
  const [scanElapsedS, setScanElapsedS] = useState(0);

  const socketRef = useRef<WebSocket | null>(null);

  // Poll API status & candidate lists periodically
  const refreshData = async () => {
    try {
      const [resStatus, resCand, resOthers] = await Promise.all([
        fetch('/api/status').then((r) => r.json()),
        fetch('/api/candidates').then((r) => r.json()),
        fetch('/api/other-devices').then((r) => r.json())
      ]);
      setStatus(resStatus);
      setCandidates(resCand);
      setOtherDevices(resOthers);
    } catch {
      // offline or loading
    }
  };

  useEffect(() => {
    refreshData();
    const interval = setInterval(refreshData, 1000);
    return () => clearInterval(interval);
  }, []);

  // WebSocket for real-time live events
  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;
    const ws = new WebSocket(wsUrl);
    socketRef.current = ws;

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.event === 'device_updated') {
          const dev = msg.data;
          // Trigger throttled audio feedback if candidate matches selected target
          if (dev.address === status?.selected_target_address) {
            audioFeedback.playCueForRssi(dev.signal.current_rssi);
          }
          // Incremental update candidate list
          setCandidates((prev) => {
            const idx = prev.findIndex((p) => p.address === dev.address);
            if (idx >= 0) {
              const updated = [...prev];
              updated[idx] = dev;
              return updated;
            } else if (dev.classification.is_candidate) {
              return [...prev, dev];
            }
            return prev;
          });
        }
      } catch {}
    };

    return () => {
      ws.close();
    };
  }, [status?.selected_target_address]);

  // Elapsed timer when scanning
  useEffect(() => {
    let t: any = null;
    if (status?.is_scanning) {
      t = setInterval(() => setScanElapsedS((prev) => prev + 1), 1000);
    } else {
      setScanElapsedS(0);
    }
    return () => clearInterval(t);
  }, [status?.is_scanning]);

  const handleStartScan = async (demo: boolean = false) => {
    await fetch('/api/scan/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_name: sessionName, demo_mode: demo })
    });
    refreshData();
  };

  const handleStopScan = async () => {
    await fetch('/api/scan/stop', { method: 'POST' });
    refreshData();
  };

  const handleSelectTarget = async (address: string) => {
    await fetch('/api/target/select', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ address })
    });
    refreshData();
  };

  const handleTogglePin = async (address: string, e: React.MouseEvent) => {
    e.stopPropagation();
    await fetch('/api/target/pin', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ address })
    });
    refreshData();
  };

  const handleMarkFound = async (address: string, isFound: boolean, notes?: string) => {
    await fetch('/api/target/found', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ address, is_found: isFound, notes })
    });
    refreshData();
  };

  const handleRecordCheckpoint = async (position_label: string, notes?: string) => {
    await fetch('/api/checkpoint', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ position_label, duration_s: 30.0, notes })
    });
    alert('Checkpoint recorded successfully!');
  };

  const handleExportCsv = () => {
    if (!status?.current_session_id) return;
    window.open(`/api/sessions/${status.current_session_id}/export/csv`, '_blank');
  };

  // Find currently selected device
  const selectedDevice =
    candidates.find((c) => c.address === status?.selected_target_address) ||
    otherDevices.find((o) => o.address === status?.selected_target_address) ||
    null;

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      {/* Top Navigation Bar */}
      <header className="bg-white border-b border-slate-200 px-6 py-4 flex flex-col md:flex-row items-center justify-between gap-4 sticky top-0 z-20 shadow-xs">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-blue-600 text-white flex items-center justify-center shadow-sm">
            <Radio size={22} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="font-black text-slate-800 text-lg tracking-tight">
                BLE Tracker Search
              </h1>
              <span className="text-[11px] font-bold px-2 py-0.5 rounded bg-slate-100 text-slate-600">
                Security Pilot
              </span>
            </div>
            <div className="text-xs text-slate-400 font-medium">
              Rules: v{status?.rule_catalog_version} ({status?.rule_count} active) • Hash:{" "}
              {status?.rule_catalog_hash || "..."}
            </div>
          </div>
        </div>

        {/* Scan Controls */}
        <div className="flex items-center gap-3 w-full md:w-auto">
          {!status?.is_scanning ? (
            <>
              <button
                onClick={() => handleStartScan(false)}
                className="flex-1 md:flex-initial px-5 py-2.5 rounded-xl font-bold text-xs bg-blue-600 hover:bg-blue-700 text-white flex items-center justify-center gap-2 shadow-sm transition-all"
              >
                <Play size={16} />
                <span>Start BLE Scan</span>
              </button>
              <button
                onClick={() => handleStartScan(true)}
                className="flex-1 md:flex-initial px-4 py-2.5 rounded-xl font-bold text-xs bg-purple-50 text-purple-700 hover:bg-purple-100 border border-purple-200 flex items-center justify-center gap-2 transition-all"
              >
                <Sparkles size={16} />
                <span>Run Demo Feed</span>
              </button>
            </>
          ) : (
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-2 bg-emerald-50 text-emerald-800 px-3 py-1.5 rounded-xl border border-emerald-200 text-xs font-semibold">
                <Clock size={16} className="text-emerald-600 animate-spin" />
                <span>
                  {scanElapsedS < 120
                    ? `Initial Observation: ${120 - scanElapsedS}s`
                    : "Observation complete — scanning continues"}
                </span>
              </div>
              <button
                onClick={handleStopScan}
                className="px-5 py-2.5 rounded-xl font-bold text-xs bg-rose-600 hover:bg-rose-700 text-white flex items-center gap-2 shadow-sm transition-all"
              >
                <Square size={16} />
                <span>Stop Scan</span>
              </button>
            </div>
          )}

          {status?.current_session_id && (
            <button
              onClick={handleExportCsv}
              className="p-2.5 rounded-xl border border-slate-200 text-slate-600 hover:bg-slate-100 transition-colors"
              title="Export Session CSV"
            >
              <FileDown size={18} />
            </button>
          )}
        </div>
      </header>

      {/* Main Content Layout */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-4 md:p-6 flex flex-col gap-6">
        {/* Locating Gauge for selected candidate */}
        <LocatingGauge
          signal={selectedDevice?.signal || null}
          audioEnabled={audioEnabled}
          onToggleAudio={() => {
            const next = !audioEnabled;
            setAudioEnabled(next);
            audioFeedback.enabled = next;
          }}
        />

        {/* Master-Detail Split Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Left Column: Device Tabs and Lists */}
          <div className="lg:col-span-7 flex flex-col gap-4">
            {/* Tabs */}
            <div className="flex items-center gap-2 border-b border-slate-200 pb-2">
              <button
                onClick={() => setActiveTab('candidates')}
                className={`px-4 py-2 rounded-xl text-xs font-bold flex items-center gap-2 transition-colors ${
                  activeTab === 'candidates'
                    ? 'bg-blue-600 text-white shadow-xs'
                    : 'text-slate-600 hover:bg-slate-100'
                }`}
              >
                <ShieldCheck size={16} />
                <span>Candidates ({candidates.length})</span>
              </button>

              <button
                onClick={() => setActiveTab('others')}
                className={`px-4 py-2 rounded-xl text-xs font-bold flex items-center gap-2 transition-colors ${
                  activeTab === 'others'
                    ? 'bg-blue-600 text-white shadow-xs'
                    : 'text-slate-600 hover:bg-slate-100'
                }`}
              >
                <Layers size={16} />
                <span>Other Devices ({otherDevices.length})</span>
              </button>
            </div>

            {/* List Body */}
            {activeTab === 'candidates' ? (
              <CandidateList
                candidates={candidates}
                selectedAddress={status?.selected_target_address || null}
                onSelectCandidate={handleSelectTarget}
                onTogglePin={handleTogglePin}
              />
            ) : (
              <div className="flex flex-col gap-2">
                {otherDevices.length === 0 ? (
                  <div className="p-8 bg-white rounded-xl border border-dashed border-slate-200 text-center text-xs text-slate-400">
                    No background devices observed.
                  </div>
                ) : (
                  otherDevices.map((item) => (
                    <div
                      key={item.address}
                      onClick={() => handleSelectTarget(item.address)}
                      className={`p-3.5 rounded-xl border bg-white flex items-center justify-between cursor-pointer transition-colors ${
                        item.address === status?.selected_target_address
                          ? 'border-blue-500 bg-blue-50/50'
                          : 'border-slate-200 hover:bg-slate-50'
                      }`}
                    >
                      <div>
                        <div className="text-xs font-bold text-slate-700">
                          {item.local_name || 'Unnamed Device'}
                        </div>
                        <div className="text-[11px] font-mono text-slate-400">
                          {item.address} • {item.classification.status_text}
                        </div>
                      </div>
                      <div className="text-xs font-black text-slate-600">
                        {item.signal.current_rssi ?? '--'} dBm
                      </div>
                    </div>
                  ))
                )}
              </div>
            )}
          </div>

          {/* Right Column: Candidate Detail & Evidence */}
          <div className="lg:col-span-5">
            <CandidateDetail
              device={selectedDevice}
              onMarkFound={handleMarkFound}
              onRecordCheckpoint={handleRecordCheckpoint}
            />
          </div>
        </div>
      </main>
    </div>
  );
};

export default App;
