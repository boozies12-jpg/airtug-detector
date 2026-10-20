import React, { useState, useEffect, useRef } from 'react';
import { LiveTargetGauge } from './components/LiveTargetGauge';
import { CandidateList } from './components/CandidateList';
import { DeviceListControls, useDeviceOrder } from './components/DeviceListControls';
import { TrackerResearchCatalog } from './components/IdentityEvidence';
import { CandidateDetail } from './components/CandidateDetail';
import { WifiSettings } from './components/WifiSettings';
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
  Pin
} from 'lucide-react';

export const App: React.FC = () => {
  const isNative = mobileBleManager.isNative();
  const [status, setStatus] = useState<AppStatus | null>(isNative ? mobileBleManager.getStatus() : null);
  const [candidates, setCandidates] = useState<BleDeviceItem[]>([]);
  const [otherDevices, setOtherDevices] = useState<BleDeviceItem[]>([]);
  const [activeTab, setActiveTab] = useState<'candidates' | 'others' | 'details'>('candidates');
  const [audioEnabled, setAudioEnabled] = useState(false);
  const [sessionName] = useState('Search Area 1');
  const [scanElapsedS, setScanElapsedS] = useState(0);
  const defaultCaptureSource = import.meta.env.VITE_DEFAULT_CAPTURE_SOURCE === 'sdr' ? 'sdr' : 'computer';
  const defaultSdrUri = import.meta.env.VITE_DEFAULT_SDR_URI || 'ip:192.168.2.1';
  const [captureSource, setCaptureSource] = useState<'computer' | 'sdr'>(() => {
    try { return (localStorage.getItem('ble.captureSource') || defaultCaptureSource) === 'sdr' ? 'sdr' : 'computer'; }
    catch { return defaultCaptureSource; }
  });
  const [sdrUri, setSdrUri] = useState(() => {
    try { return localStorage.getItem('ble.sdrUri') || defaultSdrUri; }
    catch { return defaultSdrUri; }
  });
  const [sdrScanMode, setSdrScanMode] = useState<'fixed37' | 'hop'>(() => {
    try { return localStorage.getItem('ble.sdrScanMode') === 'hop' ? 'hop' : 'fixed37'; }
    catch { return 'fixed37'; }
  });
  const [scanBusy, setScanBusy] = useState(false);
  const [scanError, setScanError] = useState('');

  const refreshing = useRef(false);

  useEffect(() => {
    if (isNative) return;
    try {
      localStorage.setItem('ble.captureSource', captureSource);
      localStorage.setItem('ble.sdrUri', sdrUri);
      localStorage.setItem('ble.sdrScanMode', sdrScanMode);
    } catch { /* Scanning also works when browser storage is unavailable. */ }
  }, [isNative, captureSource, sdrUri, sdrScanMode]);

  // Poll API status & candidate lists periodically (for desktop/web)
  const refreshData = async () => {
    if (isNative || refreshing.current) return;
    refreshing.current = true;
    try {
      const [resStatus, resCand, resOthers] = await Promise.all([
        fetch('/api/status', { signal: AbortSignal.timeout(5000) }).then((r) => r.json()),
        fetch('/api/candidates?compact=true', { signal: AbortSignal.timeout(5000) }).then((r) => r.json()),
        fetch('/api/other-devices?compact=true', { signal: AbortSignal.timeout(5000) }).then((r) => r.json())
      ]);
      setStatus(resStatus);
      if (resStatus.is_scanning && ['computer', 'sdr'].includes(resStatus.capture_source)) {
        setCaptureSource(resStatus.capture_source);
      }
      setCandidates(resCand);
      setOtherDevices(resOthers);
    } catch {
      // offline or mobile
    } finally { refreshing.current = false; }
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
    setScanBusy(true);
    setScanError('');
    setCandidates([]);
    setOtherDevices([]);
    try {
      const response = await fetch('/api/scan/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_name: sessionName, demo_mode: demo, source: captureSource, sdr_uri: sdrUri, sdr_scan_mode: sdrScanMode })
      });
      if (!response.ok) {
        const error = await response.json();
        throw new Error(typeof error.detail === 'string' ? error.detail : 'Receiver could not start');
      }
    } catch (error) {
      setScanError(String(error));
    } finally {
      setScanBusy(false);
      refreshData();
    }
  };

  const handleStopScan = async () => {
    if (isNative) {
      await mobileBleManager.stopScan();
      return;
    }
    setScanBusy(true);
    try {
      const response = await fetch('/api/scan/stop', { method: 'POST' });
      if (!response.ok) throw new Error('Could not stop receiver');
    } catch (error) {
      setScanError(String(error));
    } finally {
      setScanBusy(false);
      refreshData();
    }
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

  const elapsed = status?.scan_elapsed_s ?? scanElapsedS;
  const candidateView = useDeviceOrder(candidates, status?.current_session_id || null, elapsed);
  const otherView = useDeviceOrder(otherDevices, status?.current_session_id || null, elapsed);
  const sortedOtherDevices = otherView.items;

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
        <div className="flex flex-wrap items-center gap-2 sm:gap-3 w-full md:w-auto">
          {!isNative && <label className="text-xs font-semibold text-slate-600 flex flex-col gap-1">
            Scan source
            <select aria-label="Scan source" value={status?.is_scanning && status.capture_source !== 'demo' ? status.capture_source : captureSource}
              disabled={scanBusy || status?.is_scanning} onChange={e => setCaptureSource(e.target.value as 'computer' | 'sdr')}
              className="border border-slate-300 rounded-lg bg-white p-2 disabled:opacity-60">
              <option value="computer">Computer Bluetooth</option>
              <option value="sdr">Pluto SDR</option>
            </select>
          </label>}
          {!isNative && captureSource === 'sdr' && <label className="text-xs font-semibold text-slate-600 flex flex-col gap-1">
            Pluto connection
            <input aria-label="Pluto connection" value={sdrUri} onChange={e => setSdrUri(e.target.value)}
              disabled={scanBusy || status?.is_scanning} className="border border-slate-300 rounded-lg p-2 w-40" />
          </label>}
          {!isNative && captureSource === 'sdr' && <label className="text-xs font-semibold text-slate-600 flex flex-col gap-1">
            SDR scan mode
            <select aria-label="SDR scan mode" value={status?.is_scanning ? status.capture_health?.scan_mode || sdrScanMode : sdrScanMode}
              disabled={scanBusy || status?.is_scanning} onChange={e => setSdrScanMode(e.target.value as 'fixed37' | 'hop')}
              className="border border-slate-300 rounded-lg bg-white p-2 disabled:opacity-60">
              <option value="fixed37">Fixed channel 37 · 2402 MHz</option>
              <option value="hop">Hop 37 → 38 → 39 · 10 seconds each</option>
            </select>
          </label>}
          {!status?.is_scanning ? (
            <>
              <button
                onClick={() => handleStartScan(false)}
                disabled={scanBusy}
                className="flex-1 md:flex-initial px-4 sm:px-5 py-2 sm:py-2.5 rounded-xl font-bold text-xs bg-blue-600 hover:bg-blue-700 text-white flex items-center justify-center gap-1.5 sm:gap-2 shadow-sm transition-all"
              >
                <Play size={15} />
                <span>{scanBusy ? 'Starting…' : 'Start BLE Scan'}</span>
              </button>
              <button
                onClick={() => handleStartScan(true)}
                disabled={scanBusy}
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
                disabled={scanBusy}
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
        {!isNative && <WifiSettings />}
        {(scanError || status?.scanner_error) && <div role="alert" className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">
          {scanError || status?.scanner_error}
        </div>}
        {!isNative && (status?.capture_source === 'sdr' || captureSource === 'sdr') &&
          <div className="rounded-xl border border-blue-200 bg-blue-50 p-4 text-sm text-blue-900">
            <strong>Pluto SDR · {status?.is_scanning && status.capture_health?.scan_mode === 'hop' ? 'Hopping 37 → 38 → 39 (10 seconds each)' : !status?.is_scanning && sdrScanMode === 'hop' ? 'Hopping 37 → 38 → 39 (10 seconds each)' : 'Fixed channel 37 · 2402 MHz'}</strong>
            {status?.is_scanning && status.capture_health?.current_channel && <p>Receiving channel {status.capture_health.current_channel} · {(status.capture_health.center_frequency_hz || 0) / 1000000} MHz · Channel switches: {status.capture_health.channel_switches || 0}</p>}
            <p>Hopping listens to one channel at a time. A channel is revisited about every 30 seconds; fixed mode is better for continuous hot/cold tracking. Signal levels can differ between channels.</p>
            {status?.capture_health?.sample_rate && <p>Sampling: {status.capture_health.sample_rate / 1000000} MSPS / RF bandwidth: {(status.capture_health.rf_bandwidth || 0) / 1000000} MHz</p>}
            <p>Receiver input: {status?.capture_health?.rx_channel_label || 'RX1 (first receive path)'}. Antenna or cable connection is not detected by software.</p>
            <p>Relative power in dBFS, fixed gain 40 dB. Stop other SDR applications before scanning. Stop the scan to change receivers.</p>
            <p>Valid packets: {status?.capture_health?.packets_crc_ok ?? 0} · Host samples dropped: {status?.capture_health?.host_dropped_samples ?? 0} · Read errors: {status?.capture_health?.read_errors?.length ?? 0}</p>
            <p>Source sample continuity is not verified. Passive SDR reception may not receive device names available through active Bluetooth scanning.</p>
          </div>}
        {/* Locating Gauge for selected target (from Candidates or Other Devices) */}
        <LiveTargetGauge
          key={`${status?.current_session_id}:${status?.selected_target_address}`}
          address={status?.selected_target_address || null}
          isNative={isNative}
          signal={status?.selected_target_summary || selectedDevice?.signal || null}
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
            <TrackerResearchCatalog/>
            {activeTab !== 'details' && <DeviceListControls view={activeTab === 'others' ? otherView : candidateView} unit={status?.signal_unit || 'dBm'}/>}
            {activeTab === 'candidates' ? (
              <CandidateList
                candidates={candidateView.items}
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
                            title={item.is_pinned ? "Unpin device" : "Pin for next sort"}
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
                            <div className="text-[11px] text-slate-500 mt-1">{item.classification.evidence?.company_names?.join(', ') || 'No advertised company ID'}</div>
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
                              <span className="text-xs font-semibold text-slate-400">{item.signal.signal_unit || 'dBm'}</span>
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
                            <span>{isSelected ? "Tracking" : "Track"}</span>
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
