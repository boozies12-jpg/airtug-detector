"""Refresh offline vendor registries; does not send observed device addresses."""
import csv
import hashlib
import io
import json
from pathlib import Path
import urllib.request
import urllib.error
import gzip
from bleak.backends._manufacturers import MANUFACTURERS

ROOT = Path(__file__).resolve().parents[1] / 'catalog'
url = 'https://standards-oui.ieee.org/oui/oui.csv'
try:
    raw = urllib.request.urlopen(url, timeout=60).read()
    rows = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
    oui = {row['Assignment']: row['Organization Name'] for row in rows if row['Registry'] == 'MA-L'}
except urllib.error.HTTPError:
    url = 'https://www.wireshark.org/download/automated/data/manuf.gz'
    raw = urllib.request.urlopen(url, timeout=60).read()
    text = gzip.decompress(raw).decode('utf-8')
    oui = {}
    for line in text.splitlines():
        parts = line.split(None, 2)
        if len(parts) == 3 and len(parts[0]) == 8 and parts[0].count(':') == 2:
            oui[parts[0].replace(':', '').upper()] = parts[2].split('#')[0].strip()
(ROOT / 'oui_ma_l.json').write_text(json.dumps(oui, ensure_ascii=True, sort_keys=True, indent=2), encoding='utf-8')
(ROOT / 'company_identifiers.json').write_text(json.dumps({f'{k:04x}': v for k, v in MANUFACTURERS.items()},
    ensure_ascii=True, sort_keys=True, indent=2), encoding='utf-8')
(ROOT / 'registry_sources.json').write_text(json.dumps({'reviewed': '2026-10-12',
    'oui': {'url': url, 'sha256': hashlib.sha256(raw).hexdigest(), 'entries': len(oui), 'scope': 'MA-L only; public addresses only'},
    'company_ids': {'source': 'Bleak installed manufacturer registry, derived from Bluetooth SIG assigned numbers',
                    'url': 'https://www.bluetooth.com/specifications/assigned-numbers/', 'entries': len(MANUFACTURERS)},
    'note': 'Company IDs identify advertised namespaces; OUI names identify registrants, not proven device brands.'}, indent=2), encoding='utf-8')
print(f'Saved {len(oui)} MA-L registrants and {len(MANUFACTURERS)} company identifiers.')
