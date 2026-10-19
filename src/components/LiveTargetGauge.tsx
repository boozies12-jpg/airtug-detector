import React, { useEffect, useRef, useState } from 'react';
import { SignalSummary } from '../types';
import { LocatingGauge } from './LocatingGauge';
import { audioFeedback } from '../utils/audio';

export const LiveTargetGauge: React.FC<{
  address: string | null;
  isNative: boolean;
  signal: SignalSummary | null;
  audioEnabled: boolean;
  onToggleAudio: () => void;
}> = ({ address, isNative, signal, audioEnabled, onToggleAudio }) => {
  const [live, setLive] = useState<SignalSummary | null>(null);
  const newest = useRef(0);
  const receivedAt = useRef(performance.now());
  const [clock, setClock] = useState(performance.now());
  useEffect(() => {
    const timer = setInterval(() => setClock(performance.now()), 250);
    return () => clearInterval(timer);
  }, []);
  const [connected, setConnected] = useState(false);
  const accept = (next: SignalSummary) => {
    const timestamp = next.generated_at_mono_s || 0;
    if (timestamp < newest.current) return;
    newest.current = timestamp;
    receivedAt.current = performance.now();
    setLive(next);
  };
  useEffect(() => { if (signal) accept(signal); }, [signal]);
  useEffect(() => {
    if (isNative || !address) return;
    let disposed = false;
    let socket: WebSocket | null = null;
    let retry: ReturnType<typeof setTimeout> | undefined;
    const connect = () => {
      socket = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws`);
      socket.onopen = () => { if (!disposed) setConnected(true); };
      socket.onmessage = event => {
        if (disposed) return;
        try {
          const message = JSON.parse(event.data);
          if (message.event === 'device_updated' && message.data.address === address) {
            const next = message.data.signal as SignalSummary;
            if ((next.generated_at_mono_s || 0) < newest.current) return;
            accept(next);
            audioFeedback.playCueForRssi(next.current_rssi, next.signal_unit);
          }
        } catch { /* Ignore malformed messages; polling remains available. */ }
      };
      socket.onerror = () => socket?.close();
      socket.onclose = () => {
        if (!disposed) {
          setConnected(false);
          retry = setTimeout(connect, 1000);
        }
      };
    };
    connect();
    return () => { disposed = true; clearTimeout(retry); socket?.close(); };
  }, [address, isNative]);
  const latest = live || signal;
  const age = latest ? latest.current_age_s + Math.max(0, clock - receivedAt.current) / 1000 : 0;
  const displayed: SignalSummary | null = latest ? {
    ...latest,
    current_age_s: Math.round(age * 10) / 10,
    freshness: age <= 3 ? 'Recent observation' : age <= 30 ? 'Waiting for next observation'
      : age <= 60 ? 'No recent signal' : 'Signal Lost',
  } : null;
  return <div>
    {!isNative && address && <p className="text-xs text-slate-500 mb-2">
      {connected ? 'Live target updates connected' : 'Live connection reconnecting; using polling updates'}
    </p>}
    <LocatingGauge signal={displayed} audioEnabled={audioEnabled} onToggleAudio={onToggleAudio} />
  </div>;
};
