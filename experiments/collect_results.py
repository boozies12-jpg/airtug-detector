"""Collect small, non-address-bearing comparison evidence for the repository."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/decoder-comparison'
result = {'date': '2026-10-11', 'decision': 'Keep existing BLE decoder with validated FIR frontend; no full GNU Radio migration.',
          'method': 'Same SHA256-verified IQ for every decoder, 4 MSPS, channel 37. Shared BLE framing/CRC. '
                    'Real B held out from timing-loop tuning. Generic GNU Radio gfsk_demod, not an optimized BLE burst receiver.',
          'limitations': ['No RF ground truth for real recordings.', 'Hardware sample continuity unverified.',
                         'Payload multiset overlaps are not exact RF-event matches.',
                         'WSL offline timings include IO and are not Windows live-performance measurements.',
                         'Synthetic PHY uses GNU Radio gfsk_mod, but shared CRC/whitening; not independent protocol validation.',
                         'GNU Radio GFSK baseline lacks the custom decoder AA-based frequency-offset correction.'],
          'real': {}, 'synthetic': {}}
for name in ('real-a', 'real-b'):
    folder = DATA / name
    report = json.loads((folder / 'comparison.json').read_text())
    production = json.loads((folder / 'comparison-numpy_production.json').read_text())
    report['results']['numpy_production'] = production['results']['numpy_production']
    result['real'][name] = {'capture': json.loads((folder / 'capture.json').read_text()), 'comparison': report}
for folder in sorted(DATA.glob('synthetic-*')):
    result['synthetic'][folder.name] = {
        'capture': json.loads((folder / 'capture.json').read_text()),
        'comparison': json.loads((folder / 'comparison.json').read_text())}
result['live'] = json.loads((DATA / 'live-validation.json').read_text())
(ROOT / 'docs/decoder-comparison-2026-10-11.json').write_text(json.dumps(result, indent=2))
print('Saved docs/decoder-comparison-2026-10-11.json')
