"""Explicit receive-only app integration check; not part of automated unit tests."""
import json
from pathlib import Path
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
URL = 'http://127.0.0.1:41732'


def request(path, body=None):
    req = urllib.request.Request(URL + path, data=None if body is None else json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=50) as response:
        return json.load(response)


def main():
    if request('/api/status')['is_scanning']:
        raise RuntimeError('App already scanning; do not interrupt the user capture')
    request('/api/scan/start', {'source': 'sdr', 'session_name': 'Filtered decoder validation'})
    try:
        time.sleep(15)
        status = request('/api/status')
        devices = request('/api/candidates') + request('/api/other-devices')
        assert not status['scanner_error'], status
        assert devices and all(d['signal']['signal_unit'] == 'dBFS' for d in devices)
    finally:
        request('/api/scan/stop', {})
    folder = Path(status['capture_health']['output'])
    config = json.loads((folder / 'config.json').read_text())
    health = json.loads((folder / 'health.json').read_text())
    assert config['decoder'] == 'FilteredDecoder', config
    assert health['stream_test_passed'] and not health['host_dropped_samples'], health
    result = dict(devices=len(devices), config=config, health=health)
    (ROOT / 'data/decoder-comparison/live-validation.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
