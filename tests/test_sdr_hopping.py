import json
import time
from types import SimpleNamespace
import numpy as np
import pytest
from src.domain import sdr_rx

@pytest.mark.parametrize('hop', [False, True])
def test_radio_hopping_tags_buffers_resets_decoder_and_counts_settling(tmp_path, monkeypatch, hop):
    clock = [0.0]
    events = []
    class Radio:
        _ctx = SimpleNamespace(set_timeout=lambda n: None, attrs={})
        _rxbuf = None
        rx_lo = sdr_rx.FREQUENCIES[37]
        def rx_destroy_buffer(self): events.append(('destroy', self.rx_lo))
        def rx(self):
            time.sleep(.005)  # Let the consumer process each synthetic buffer.
            clock[0] += 1
            channel = next(k for k, v in sdr_rx.FREQUENCIES.items() if v == self.rx_lo)
            return np.full(64, channel * 2048, dtype=np.complex64)
    radio = Radio()
    class Decoder:
        def __init__(self, rate, channel):
            self.channel = channel
            self.crc_fail = 1
            events.append(('decoder', channel))
        def feed(self, samples, start):
            assert np.all(samples.real == self.channel), 'IQ was labelled with the wrong channel'
            return [{'channel': self.channel, 'sample_index_host': start}]
    monkeypatch.setattr(sdr_rx, 'load_pluto', lambda *args: radio)
    monkeypatch.setattr(sdr_rx, 'Decoder', Decoder)
    monkeypatch.setattr(sdr_rx, 'time', SimpleNamespace(perf_counter=lambda: clock[0], strftime=time.strftime, time_ns=time.time_ns))
    sdr_rx.main(['--no-prefilter', '--seconds', '36', '--output', str(tmp_path)] + (['--hop'] if hop else []))
    directory = next(tmp_path.iterdir())
    health = json.loads((directory / 'health.json').read_text())
    packets = [json.loads(s) for s in (directory / 'packets.jsonl').read_text().splitlines()]
    assert health['host_dropped_samples'] == 0
    assert health['stream_test_passed']
    if hop:
        assert [e['channel'] for e in health['hop_history']] == [38, 39, 37]
        assert [c for k, c in events if k == 'decoder'] == [37, 38, 39, 37]
        assert health['settling_discarded_samples'] == 3 * 64
        assert health['crc_failed_candidates'] == 4
        assert set(p['channel'] for p in packets) == {37, 38, 39}
        times = [0] + [e['elapsed_seconds'] for e in health['hop_history']]
        assert all(b-a >= 10 for a,b in zip(times,times[1:]))
    else:
        assert health['channel_switches'] == 0
        assert health['settling_discarded_samples'] == 0
        assert set(p['channel'] for p in packets) == {37}

@pytest.mark.asyncio
async def test_hop_mode_reaches_backend(tmp_path, monkeypatch):
    from test_sdr import make_orchestrator
    seen = []
    class Backend:
        def __init__(self, *args): pass
        async def start(self, uri, scan_mode='fixed37'): seen.append((uri, scan_mode))
        async def stop(self): pass
    monkeypatch.setattr('src.domain.acquisition.SdrBackend', Backend)
    o = make_orchestrator(tmp_path)
    await o.start_scan(source='sdr', sdr_scan_mode='hop')
    await o.stop_scan()
    assert seen == [('ip:192.168.2.1', 'hop')]
    with pytest.raises(ValueError, match='scan mode'):
        await o.start_scan(source='sdr', sdr_scan_mode='invalid')
