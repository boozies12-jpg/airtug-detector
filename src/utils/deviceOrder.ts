import type { BleDeviceItem } from '../types';

export type SortKey = 'signal' | 'name' | 'recent';
export interface ListFilter { query: string; minSignal: string; maxAge: string }

export function sortDevices(items: BleDeviceItem[], key: SortKey): BleDeviceItem[] {
  return [...items].sort((a, b) => {
    const pin = Number(b.is_pinned) - Number(a.is_pinned);
    if (pin) return pin;
    let result = 0;
    if (key === 'signal') result = (b.signal.current_rssi ?? -Infinity) - (a.signal.current_rssi ?? -Infinity);
    if (key === 'name') result = (a.local_name || a.classification.brand || '').localeCompare(b.local_name || b.classification.brand || '', 'en');
    if (key === 'recent') result = a.signal.current_age_s - b.signal.current_age_s;
    return (Number.isNaN(result) ? 0 : result) || a.address.localeCompare(b.address);
  });
}

// Previously seen addresses keep their slots; newly discovered devices append.
export function stableAddresses(previous: string[], items: BleDeviceItem[]): string[] {
  const known = new Set(previous);
  return [...previous, ...items.filter(item => !known.has(item.address)).map(item => item.address)];
}

export function nextAddresses(previous: string[], items: BleDeviceItem[], key: SortKey, elapsed: number, manual: boolean): string[] {
  return elapsed < 60 && !manual ? sortDevices(items, key).map(x => x.address) : stableAddresses(previous, items);
}

export function matchesFilter(item: BleDeviceItem, filter: ListFilter): boolean {
  const text = [item.address, item.local_name, item.classification.brand, item.classification.protocol_family,
    ...(item.classification.evidence?.company_names || [])].join(' ').toLowerCase();
  return text.includes(filter.query.trim().toLowerCase()) &&
    (filter.minSignal === '' || (item.signal.current_rssi !== null && item.signal.current_rssi >= Number(filter.minSignal))) &&
    (filter.maxAge === '' || item.signal.current_age_s <= Number(filter.maxAge));
}
