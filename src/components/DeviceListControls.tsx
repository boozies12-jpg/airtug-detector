import { useEffect, useState } from 'react';
import type { BleDeviceItem } from '../types';
import { matchesFilter, sortDevices, nextAddresses, type SortKey, type ListFilter } from '../utils/deviceOrder';

export function useDeviceOrder(items: BleDeviceItem[], session: string | null, elapsed: number) {
  const [order, setOrder] = useState<{session: string | null; addresses: string[]; manual: boolean}>({session, addresses: [], manual: false});
  const [filter, setFilter] = useState<ListFilter>({query: '', minSignal: '', maxAge: ''});
  const [allowed, setAllowed] = useState<Set<string> | null>(null);
  const [key, setKey] = useState<SortKey>('signal');
  const same = order.session === session;
  const automatic = elapsed < 60 && !(same && order.manual);
  useEffect(() => {
    setOrder(old => {
      const reset = old.session !== session;
      const addresses = nextAddresses(reset ? [] : old.addresses, items, key, elapsed, reset ? false : old.manual);
      return {session, addresses, manual: reset ? false : old.manual};
    });
  }, [items, session, automatic, key, elapsed]);
  useEffect(() => { setAllowed(null); }, [session]);
  const addresses = same ? order.addresses : [];
  const ranks = new Map(addresses.map((address, index) => [address, index]));
  const ordered = [...items].sort((a, b) => (ranks.get(a.address) ?? Infinity) - (ranks.get(b.address) ?? Infinity));
  return {items: ordered.filter(item => !allowed || allowed.has(item.address)), automatic, key, setKey, filter, setFilter,
    apply: () => {
      setOrder({session, addresses: sortDevices(items, key).map(x => x.address), manual: true});
      // Filtering is a snapshot too: fluctuating strength/age will not remove rows.
      setAllowed(new Set(items.filter(item => matchesFilter(item, filter)).map(item => item.address)));
    },
    clear: () => { setFilter({query: '', minSignal: '', maxAge: ''}); setAllowed(null); },
  };
}

export function DeviceListControls({view, unit}: {view: ReturnType<typeof useDeviceOrder>; unit: string}) {
  const [open, setOpen] = useState(false);
  return <div className="mb-3 rounded-xl border border-slate-200 bg-white p-3 text-xs">
    <div className="flex items-center justify-between gap-2">
      <span className="text-slate-500">{view.automatic ? 'Auto-order: first 60 seconds' : 'Order locked · readings stay live'}</span>
      <button className="font-bold text-blue-700" onClick={() => setOpen(!open)}>Sort &amp; filter</button>
    </div>
    {open && <div className="mt-3 flex flex-wrap gap-2 items-end">
      <label>Sort by<select aria-label="Sort by" className="block border rounded p-1" value={view.key} onChange={e => view.setKey(e.target.value as SortKey)}>
        <option value="signal">Strongest signal</option><option value="name">Device name</option><option value="recent">Last seen</option>
      </select></label>
      <label>Name / address / company<input className="block border rounded p-1" value={view.filter.query} onChange={e => view.setFilter({...view.filter, query: e.target.value})}/></label>
      <label>Minimum {unit}<input type="number" className="block border rounded p-1 w-24" value={view.filter.minSignal} onChange={e => view.setFilter({...view.filter, minSignal: e.target.value})}/></label>
      <label>Seen within (s)<input type="number" min="0" className="block border rounded p-1 w-24" value={view.filter.maxAge} onChange={e => view.setFilter({...view.filter, maxAge: e.target.value})}/></label>
      <button className="bg-blue-600 text-white rounded px-3 py-2" onClick={view.apply}>Apply &amp; lock</button>
      <button className="border rounded px-3 py-2" onClick={view.clear}>Clear filters</button>
      <p className="w-full text-slate-500">Pinned devices lead on the next sort. Filters use a snapshot; apply again to refresh. New devices append when unfiltered.</p>
    </div>}
  </div>;
}
