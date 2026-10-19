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
  const [connected, setConnected] = useState(false);
  const accept = (next: SignalSummary) => {
    const timestamp = next.generated_at_mono_s || 0;
    if (timestamp < newest.current) return;
    newest.current = timestamp;
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
  return <div>
    {!isNative && address && <p className="text-xs text-slate-500 mb-2">
      {connected ? 'Live target updates connected' : 'Live connection reconnecting; using polling updates'}
    </p>}
    <LocatingGauge signal={live || signal} audioEnabled={audioEnabled} onToggleAudio={onToggleAudio} />
  </div>;
};
