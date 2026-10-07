import React, { useState, useEffect, useRef } from 'react';
import { LocatingGauge } from './components/LocatingGauge';
import { CandidateList } from './components/CandidateList';
import { CandidateDetail } from './components/CandidateDetail';
import { BleDeviceItem, AppStatus } from './types';
import { audioFeedback } from './utils/audio';
import { mobileBleManager } from './mobile/mobileScanner';
import {
  Play,
  Square,
  Radio,
  FileDown,
  Layers,
  Sparkles,
  Clock,
  ShieldCheck,
  Pin,
  Smartphone
} from 'lucide-react';

export const App: React.FC = () => {
  const isNative = mobileBleManager.isNative();
  const [status, setStatus] = useState<AppStatus | null>(isNative ? mobileBleManager.getStatus() : null);
  const [candidates, setCandidates] = useState<BleDeviceItem[]>([]);
  const [otherDevices, setOtherDevices] = useState<BleDeviceItem[]>([]);
  const [activeTab, setActiveTab] = useState<'candidates' | 'others' | 'details'>('candidates');
  const [audioEnabled, setAudioEnabled] = useState(false);
  const [sessionName, setSessionName] = useState('Search Area 1');
  const [scanElapsedS, setScanElapsedS] = useState(0);

  const socketRef = useRef<WebSocket | null>(null);

  // Poll API status & candidate lists periodically (for desktop/web)
  const refreshData = async () => {
    if (isNative) return;
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
      // offline or mobile
    }
  };

  useEffect(() => {
    if (isNative) {
      mobileBleManager.onUpdate((cands, others, stat) => {
        setCandidates(cands);
        setOtherDevices(others);
        setStatus(stat);
        if (stat.selected_target_address) {
          const sel =
            cands.find((c) => c.address === stat.selected_target_address) ||
            others.find((o) => o.address === stat.selected_target_address);
          if (sel && sel.signal.current_rssi !== null) {
            audioFeedback.playCueForRssi(sel.signal.current_rssi);
          }
        }
      });
      setStatus(mobileBleManager.getStatus());
      return;
    }

    refreshData();
    const interval = setInterval(refreshData, 1000);
    return () => clearInterval(interval);
  }, [isNative]);

  // WebSocket for real-time live events (desktop/web)
  useEffect(() => {
    if (isNative) return;
    try {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = `${protocol}//${window.location.host}/ws`;
      const ws = new WebSocket(wsUrl);
      socketRef.current = ws;

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.event === 'device_updated') {
            const dev = msg.data;
            // Trigger throttled audio feedback if device matches selected target
            if (dev.address === status?.selected_target_address) {
              audioFeedback.playCueForRssi(dev.signal.current_rssi);
            }
            if (dev.classification.is_candidate) {
              setCandidates((prev) => {
                const idx = prev.findIndex((p) => p.address === dev.address);
                if (idx >= 0) {
                  const updated = [...prev];
                  updated[idx] = dev;
                  return updated;
                }
                return [...prev, dev];
              });
            } else {
              setOtherDevices((prev) => {
                const idx = prev.findIndex((p) => p.address === dev.address);
                if (idx >= 0) {
                  const updated = [...prev];
                  updated[idx] = dev;
                  return updated;
                }
                return [...prev, dev];
              });
            }
          }
        } catch {}
      };

      return () => {
        ws.close();
      };
    } catch {}
  }, [isNative, status?.selected_target_address]);

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
    if (isNative) {
      try {
        await mobileBleManager.startScan(demo);
      } catch (err: any) {
        alert("Bluetooth scan error: " + (err?.message || err));
      }
      return;
    }
    await fetch('/api/scan/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_name: sessionName, demo_mode: demo })
    });
    refreshData();
  };

  const handleStopScan = async () => {
    if (isNative) {
      await mobileBleManager.stopScan();
      return;
    }
    await fetch('/api/scan/stop', { method: 'POST' });
    refreshData();
  };

  const handleSelectTarget = async (address: string) => {
    if (isNative) {
      mobileBleManager.selectTarget(address);
      return;
    }
    await fetch('/api/target/select', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ address })
    });
    refreshData();
  };

  const handleTogglePin = async (address: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (isNative) {
      mobileBleManager.togglePin(address);
      return;
    }
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

  // Find currently selected device across candidates or other devices
  const selectedDevice =
    candidates.find((c) => c.address === status?.selected_target_address) ||
    otherDevices.find((o) => o.address === status?.selected_target_address) ||
    null;

  // Sort other devices: pinned devices first, then descending by RSSI
  const sortedOtherDevices = [...otherDevices].sort((a, b) => {
    if (a.is_pinned && !b.is_pinned) return -1;
    if (!a.is_pinned && b.is_pinned) return 1;
    return (b.signal.current_rssi ?? -999) - (a.signal.current_rssi ?? -999);
  });

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      {/* Top Navigation Bar */}
      <header className="bg-white border-b border-slate-200 px-4 py-3 sm:px-6 sm:py-4 flex flex-col md:flex-row items-center justify-between gap-3 sm:gap-4 sticky top-0 z-20 shadow-xs">
        <div className="flex items-center justify-between w-full md:w-auto gap-3">
          <div className="flex items-center gap-2.5 sm:gap-3">
            <div className="w-9 h-9 sm:w-10 sm:h-10 rounded-xl bg-blue-600 text-white flex items-center justify-center shadow-sm shrink-0">
              <Radio size={20} className="sm:w-[22px] sm:h-[22px]" />
            </div>
            <div>
              <div className="flex items-center gap-1.5 sm:gap-2">
                <h1 className="font-black text-slate-800 text-base sm:text-lg tracking-tight">
                  BLE Tracker Search
                </h1>
                <span className="text-[10px] sm:text-[11px] font-bold px-1.5 sm:px-2 py-0.5 rounded bg-blue-50 text-blue-700 border border-blue-200">
                  v2.0
                </span>
                <span className="text-[10px] sm:text-[11px] font-bold px-1.5 sm:px-2 py-0.5 rounded bg-slate-100 text-slate-600">
                  Security Pilot
                </span>
              </div>
              <div className="text-xs text-slate-400 font-medium hidden sm:block">
                Rules: v{status?.rule_catalog_version} ({status?.rule_count} active) • Hash:{" "}
                {status?.rule_catalog_hash || "..."}
              </div>
            </div>
          </div>
        </div>

        {/* Scan Controls */}
        <div className="flex items-center gap-2 sm:gap-3 w-full md:w-auto">
          {!status?.is_scanning ? (
            <>
              <button
                onClick={() => handleStartScan(false)}
                className="flex-1 md:flex-initial px-4 sm:px-5 py-2 sm:py-2.5 rounded-xl font-bold text-xs bg-blue-600 hover:bg-blue-700 text-white flex items-center justify-center gap-1.5 sm:gap-2 shadow-sm transition-all"
              >
                <Play size={15} />
                <span>Start BLE Scan</span>
              </button>
              <button
                onClick={() => handleStartScan(true)}
                className="flex-1 md:flex-initial px-3 sm:px-4 py-2 sm:py-2.5 rounded-xl font-bold text-xs bg-purple-50 text-purple-700 hover:bg-purple-100 border border-purple-200 flex items-center justify-center gap-1.5 sm:gap-2 transition-all"
              >
                <Sparkles size={15} />
                <span>Run Demo Feed</span>
              </button>
            </>
          ) : (
            <div className="flex items-center justify-between sm:justify-start gap-2 sm:gap-3 w-full md:w-auto">
              <div className="flex items-center gap-2 bg-emerald-50 text-emerald-800 px-2.5 sm:px-3 py-1.5 rounded-xl border border-emerald-200 text-xs font-semibold truncate flex-1 md:flex-initial">
                <Clock size={15} className="text-emerald-600 animate-spin shrink-0" />
                <span className="truncate">
                  {scanElapsedS < 120
                    ? `Initial Observation: ${120 - scanElapsedS}s`
                    : "Observation complete"}
                </span>
              </div>
              <button
                onClick={handleStopScan}
                className="px-4 sm:px-5 py-2 sm:py-2.5 rounded-xl font-bold text-xs bg-rose-600 hover:bg-rose-700 text-white flex items-center gap-1.5 sm:gap-2 shadow-sm transition-all shrink-0"
              >
                <Square size={15} />
                <span>Stop Scan</span>
              </button>
            </div>
          )}

          {status?.current_session_id && (
            <button
              onClick={handleExportCsv}
              className="p-2 sm:p-2.5 rounded-xl border border-slate-200 text-slate-600 hover:bg-slate-100 transition-colors shrink-0"
              title="Export Session CSV"
            >
              <FileDown size={18} />
            </button>
          )}
        </div>
      </header>

      {/* Main Content Layout */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-4 md:p-6 flex flex-col gap-6">
        {/* Locating Gauge for selected target (from Candidates or Other Devices) */}
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
            <div className="flex items-center gap-1.5 sm:gap-2 border-b border-slate-200 pb-2 overflow-x-auto">
              <button
                onClick={() => setActiveTab('candidates')}
                className={`px-3 sm:px-4 py-2 rounded-xl text-xs font-bold flex items-center gap-1.5 sm:gap-2 transition-colors shrink-0 ${
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
                className={`px-3 sm:px-4 py-2 rounded-xl text-xs font-bold flex items-center gap-1.5 sm:gap-2 transition-colors shrink-0 ${
                  activeTab === 'others'
                    ? 'bg-blue-600 text-white shadow-xs'
                    : 'text-slate-600 hover:bg-slate-100'
                }`}
              >
                <Layers size={16} />
                <span>Other Devices ({otherDevices.length})</span>
              </button>

              {/* Mobile-only Target Details Tab */}
              <button
                onClick={() => setActiveTab('details')}
                className={`lg:hidden px-3 sm:px-4 py-2 rounded-xl text-xs font-bold flex items-center gap-1.5 sm:gap-2 transition-colors shrink-0 ${
                  activeTab === 'details'
                    ? 'bg-blue-600 text-white shadow-xs'
                    : selectedDevice
                    ? 'text-blue-700 bg-blue-50 hover:bg-blue-100 border border-blue-200'
                    : 'text-slate-400 hover:bg-slate-100'
                }`}
              >
                <Radio size={16} className={selectedDevice ? "animate-pulse" : ""} />
                <span>Target Details</span>
              </button>
            </div>

            {/* List Body */}
            {activeTab === 'candidates' ? (
              <CandidateList
                candidates={candidates}
                selectedAddress={status?.selected_target_address || null}
                onSelectCandidate={(addr) => {
                  handleSelectTarget(addr);
                }}
                onTogglePin={handleTogglePin}
              />
            ) : activeTab === 'others' ? (
              /* STEP B: Upgraded Other Devices Tab with Real-Time Tracking, Liveness, and Pinning */
              <div className="flex flex-col gap-2.5">
                {sortedOtherDevices.length === 0 ? (
                  <div className="p-8 bg-white rounded-xl border border-dashed border-slate-200 text-center text-xs text-slate-400">
                    No background devices observed.
                  </div>
                ) : (
                  sortedOtherDevices.map((item) => {
                    const isSelected = item.address === status?.selected_target_address;
                    const rssi = item.signal.current_rssi;
                    const freshness = item.signal.freshness;
                    const dotColor =
                      freshness === "Recent observation"
                        ? "bg-emerald-500 animate-pulse"
                        : freshness === "Waiting for next observation"
                        ? "bg-amber-500"
                        : freshness === "No recent signal"
                        ? "bg-orange-500"
                        : "bg-slate-300";

                    return (
                      <div
                        key={item.address}
                        onClick={() => handleSelectTarget(item.address)}
                        className={`p-3.5 sm:p-4 rounded-xl border transition-all cursor-pointer flex flex-col sm:flex-row sm:items-center justify-between gap-3 ${
                          isSelected
                            ? "border-blue-500 bg-blue-50/70 ring-2 ring-blue-400 shadow-sm"
                            : "border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50/60"
                        }`}
                      >
                        {/* Device Info & Status Pulse */}
                        <div className="flex items-start gap-2.5 sm:gap-3 min-w-0 flex-1">
                          {/* Pin Toggle Button */}
                          <button
                            onClick={(e) => handleTogglePin(item.address, e)}
                            className={`p-1.5 rounded-lg transition-colors mt-0.5 shrink-0 ${
                              item.is_pinned
                                ? "text-blue-600 bg-blue-100"
                                : "text-slate-300 hover:text-slate-500 hover:bg-slate-100"
                            }`}
                            title={item.is_pinned ? "Unpin device" : "Pin to top"}
                          >
                            <Pin size={18} />
                          </button>

                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-1.5 sm:gap-2 flex-wrap">
                              {/* Visual Pulse / Status Indicator */}
                              <span
                                className={`inline-block w-2.5 h-2.5 rounded-full shrink-0 ${dotColor}`}
                                title={freshness}
                              />
                              <span className="font-bold text-slate-800 text-sm truncate">
                                {item.local_name || "Unnamed Device"}
                              </span>
                              {item.is_pinned && (
                                <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-blue-100 text-blue-700 shrink-0">
                                  PINNED
                                </span>
                              )}
                              {isSelected && (
                                <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-blue-600 text-white shrink-0">
                                  TRACKING
                                </span>
                              )}
                            </div>

                            <div className="text-xs text-slate-500 font-mono mt-0.5 flex flex-wrap items-center gap-x-2">
                              <span>{item.address}</span>
                              <span className="text-slate-300">•</span>
                              <span className="font-sans text-slate-400 truncate">{item.classification.status_text}</span>
                            </div>

                            {/* Liveness & Packet Activity */}
                            <div className="text-[11px] text-slate-400 mt-1 flex flex-wrap items-center gap-x-3">
                              <span>
                                Activity:{" "}
                                <strong className="text-slate-600 font-semibold">
                                  {item.signal.summary_20s_count} pkts / 20s
                                </strong>
                              </span>
                              <span className="text-slate-300">•</span>
                              <span>
                                Last seen:{" "}
                                <strong className="text-slate-600 font-semibold">
                                  {item.signal.current_age_s}s ago
                                </strong>
                              </span>
                            </div>
                          </div>
                        </div>

                        {/* RSSI & Dedicated Track Action Button */}
                        <div className="flex items-center justify-between sm:justify-end gap-3 pt-2 sm:pt-0 border-t sm:border-t-0 border-slate-100 shrink-0">
                          <div className="text-left sm:text-right">
                            <div className="text-lg font-black text-slate-800 tracking-tight whitespace-nowrap">
                              {rssi !== null ? `${rssi}` : "--"}{" "}
                              <span className="text-xs font-semibold text-slate-400">dBm</span>
                            </div>
                            <div className="text-[11px] text-slate-400 font-medium whitespace-nowrap">
                              {freshness}
                            </div>
                          </div>

                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handleSelectTarget(item.address);
                            }}
                            className={`px-3.5 py-2 rounded-xl text-xs font-bold flex items-center gap-1.5 transition-all shrink-0 ${
                              isSelected
                                ? "bg-blue-600 text-white shadow-xs"
                                : "bg-slate-100 hover:bg-blue-50 text-slate-700 hover:text-blue-700 border border-slate-200"
                            }`}
                          >
                            <Radio size={14} className={isSelected ? "animate-pulse" : ""} />
                            <span>{isSelected ? "Tracking" : "Track / עקוב"}</span>
                          </button>
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            ) : (
              <CandidateDetail
                device={selectedDevice}
                onMarkFound={handleMarkFound}
                onRecordCheckpoint={handleRecordCheckpoint}
              />
            )}
          </div>

          {/* Right Column: Candidate Detail & Evidence (Desktop only) */}
          <div className="lg:col-span-5 hidden lg:block">
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
