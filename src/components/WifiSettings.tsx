import { useEffect, useRef, useState } from 'react';
import { Wifi } from 'lucide-react';

type NetworkStatus = {
  enabled: boolean; mode?: string; ssid?: string; hostname_url?: string;
  addresses?: string[]; pending?: { ssid: string; deadline: number } | null;
};

export function WifiSettings() {
  const [network, setNetwork] = useState<NetworkStatus | null>(null);
  const [open, setOpen] = useState(false);
  const [ssid, setSsid] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [joinUrl, setJoinUrl] = useState('');
  const [offline, setOffline] = useState(false);

  const refreshing = useRef(false);
  const refresh = async () => {
    if (refreshing.current) return;
    refreshing.current = true;
    try {
      const response = await fetch('/api/network', { signal: AbortSignal.timeout(8000) });
      if (!response.ok) throw new Error();
      const value = await response.json();
      setNetwork(value); setOffline(false);
      if (value.pending) setOpen(true);
    } catch { setOffline(true); }
    finally { refreshing.current = false; }
  };
  useEffect(() => { refresh(); }, []);
  useEffect(() => {
    if (network?.enabled === false) return;
    const timer = setInterval(refresh, open || !network ? 5000 : 15000);
    return () => clearInterval(timer);
  }, [open, network?.enabled]);

  async function action(kind: 'connect' | 'field' | 'confirm', saved = false) {
    setBusy(true); setError(''); setMessage(''); setJoinUrl('');
    try {
      const response = await fetch(`/api/network/${kind}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(kind === 'connect' ? { ssid, password, saved_workshop: saved } : {}),
        signal: AbortSignal.timeout(30000)
      });
      const result = await response.json();
      if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Check the network name and password.');
      setPassword('');
      if (kind === 'connect') {
        setMessage(`The board will connect to ${result.ssid}. This page will disconnect. Open your phone Wi-Fi settings and join ${result.ssid}, then open the link below and select Confirm connection within 3 minutes. The field address (192.168.50.1) does not work on the new network. Without confirmation, BLE-POC returns automatically.`);
        setJoinUrl(result.hostname_url);
      } else if (kind === 'field') {
        setMessage('In a few seconds, join BLE-POC without a password. Choose to stay connected even if your phone reports no internet access.');
        setJoinUrl(result.field_url);
      } else {
        setMessage('Connection confirmed. The board will start in field mode on its next boot.');
        await refresh();
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unable to complete the operation.');
    } finally { setBusy(false); }
  }

  if (network?.enabled === false) return null;
  if (!network) return <section dir="ltr" className="rounded-xl border border-slate-200 bg-white p-4 text-sm">
    <h2 className="font-bold text-slate-800">Wi-Fi &amp; field mode</h2>
    <p role="status" className="mt-2 text-slate-600">{offline ? 'Network settings are temporarily unavailable. Retrying automatically.' : 'Loading network settings...'}</p>
    <button type="button" onClick={refresh} className="mt-2 rounded-lg border px-4 py-2 text-blue-700">Retry network settings</button>
  </section>;
  return <section dir="ltr" className="rounded-xl border border-slate-200 bg-white p-4 text-sm">
    <button type="button" onClick={() => setOpen(!open)} aria-expanded={open}
      className="flex w-full items-center gap-2 text-left font-bold text-slate-800">
      <Wifi size={18} /> Wi-Fi & field mode
      <span className="ml-auto text-xs font-normal">{network.mode === 'hotspot' ? 'Field hotspot' : network.ssid || 'Disconnected'}</span>
    </button>
    {open && <div className="mt-4 space-y-3">
      <p>The board starts in field mode on every boot. Your phone is the display; detection does not require internet access.</p>
      <p>Current network: {network.mode === 'hotspot' ? 'BLE-POC (open network)' : network.ssid || 'Disconnected'}.
        {network.addresses?.map(address => <a key={address} dir="ltr" className="mx-2 underline" href={`http://${address}:41732`}>{address}:41732</a>)}
      </p>
      {offline && <p role="status" className="text-amber-800">Board connection lost. After switching networks, join the selected Wi-Fi on your phone and open the new address. If you cannot reconnect, wait 3 minutes, rejoin BLE-POC, and open http://192.168.50.1:41732.</p>}
      {message && <div role="status" className="rounded-lg bg-blue-50 p-3 text-blue-900">{message}
        {joinUrl && <a dir="ltr" className="mt-2 block break-all underline" href={joinUrl}>{joinUrl}</a>}
      </div>}
      {error && <p role="alert" className="text-rose-700">{error}</p>}
      {network.pending && <div className="rounded-lg bg-amber-50 p-3">
        <p>Waiting for confirmation on {network.pending.ssid}. Without confirmation, the board returns to BLE-POC after 3 minutes.</p>
        <button type="button" disabled={busy || offline || network.mode !== 'client'} onClick={() => action('confirm')}
          className="mt-2 rounded-lg bg-blue-600 px-4 py-2 font-bold text-white disabled:opacity-50">Confirm connection on the new network</button>
      </div>}
      <div className="flex flex-wrap gap-2">
        <button type="button" disabled={busy || offline} onClick={() => action('field')}
          className="rounded-lg border border-blue-600 px-4 py-2 font-bold text-blue-700 disabled:opacity-50">Switch to field mode (BLE-POC)</button>
        <button type="button" disabled={busy || offline || !!network.pending} onClick={() => action('connect', true)}
          className="rounded-lg border border-slate-300 px-4 py-2 disabled:opacity-50">Connect to saved workshop Wi-Fi</button>
      </div>
      <form onSubmit={e => { e.preventDefault(); action('connect'); }} className="flex flex-col gap-3 border-t pt-3">
        <label>Other Wi-Fi network name (SSID)
          <input required value={ssid} onChange={e => setSsid(e.target.value)} autoComplete="off" dir="auto"
            className="mt-1 block w-full rounded-lg border border-slate-300 p-2" />
        </label>
        <label>Network password (leave empty for an open network)
          <input type="password" value={password} onChange={e => setPassword(e.target.value)} autoComplete="new-password"
            className="mt-1 block w-full rounded-lg border border-slate-300 p-2" />
        </label>
        <button disabled={busy || offline || !!network.pending} className="self-start rounded-lg bg-blue-600 px-4 py-2 font-bold text-white disabled:opacity-50">
          {busy ? 'Preparing switch...' : 'Connect to network'}
        </button>
        <p className="text-xs text-slate-500">Supports open and personal password-protected networks. If the hostname link does not open, wait for BLE-POC to return. Captive portals and enterprise authentication are not supported.</p>
      </form>
    </div>}
  </section>;
}
