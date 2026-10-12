"""Offline A/B: existing receiver vs GNU Radio GFSK demodulation on identical IQ.

Uses the SAME BLE framing/dewhitening/CRC rules to isolate the PHY comparison.
GNU Radio's generic continuous GFSK demodulator is not a complete BLE receiver.
Run in an environment with GNU Radio, NumPy, and SciPy (the installed WSL Ubuntu).
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import platform
import sys
import time

import numpy as np
from gnuradio import gr, blocks, digital, filter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.domain.sdr_rx import AA, Decoder, crc24, whiten
from src.domain.ble_filter import FilteredDecoder


def parse_bits(path, channel=37):
    """Streaming BLE framing, preserving incomplete packets across chunks."""
    source = np.memmap(path, dtype=np.uint8, mode='r')
    tail = np.empty(0, np.uint8)
    pattern = AA.astype(np.int16) * 2 - 1
    last = -1000
    packets = []
    for start in range(0, len(source), 65536):
        bits = np.concatenate((tail, source[start:start + 65536]))
        base = start - len(tail)
        tail = bits[-400:].copy()
        if len(bits) < 32:
            continue
        scores = np.correlate(bits.astype(np.int16) * 2 - 1, pattern, 'valid')
        for pos in np.flatnonzero(scores >= 28):
            absolute = base + int(pos)
            if absolute <= last + 8 or pos + 48 > len(bits):
                continue
            plain = whiten(bits[pos + 32:pos + 32 + 42 * 8], channel)
            header = np.packbits(plain[:16], bitorder='little').tobytes()
            kind, length = header[0] & 15, header[1] & 63
            if kind > 6 or not 6 <= length <= 37:
                continue
            count = 2 + length + 3
            if len(plain) < count * 8:
                continue
            raw = np.packbits(plain[:count * 8], bitorder='little').tobytes()
            if crc24(raw[:-3]) == raw[-3:]:
                packets.append(dict(bit_index=absolute, pdu_hex=raw[:-3].hex(), crc_hex=raw[-3:].hex()))
                last = absolute
    return packets


def decode_numpy(path, cutoff=None, production=False):
    source = np.memmap(path, dtype='<c8', mode='r')
    decoder = FilteredDecoder() if production else Decoder()
    packets = []
    if cutoff:
        from scipy.signal import lfilter
        taps = np.array(filter.firdes.low_pass(1., 4000000., cutoff, 200000.), dtype=np.float32)
        state = np.zeros(len(taps) - 1, dtype=np.complex64)
    for start in range(0, len(source), 65536):
        samples = source[start:start + 65536]
        if cutoff:
            samples, state = lfilter(taps, [1.], samples, zi=state)
        packets.extend(decoder.feed(samples, start))
    return packets


def decode_gnu(path, output, gain_mu=.175, cutoff=None):
    tb = gr.top_block('BLE offline comparison')
    source = blocks.file_source(gr.sizeof_gr_complex, str(path), False)
    demod = digital.gfsk_demod(samples_per_symbol=4, sensitivity=np.pi / 8,
                               gain_mu=gain_mu, omega_relative_limit=.005)
    sink = blocks.file_sink(gr.sizeof_char, str(output), False)
    if cutoff:
        taps = filter.firdes.low_pass(1., 4000000., cutoff, 200000.)
        lowpass = filter.fir_filter_ccf(1, taps)
        tb.connect(source, lowpass, demod, sink)
    else:
        tb.connect(source, demod, sink)
    began = time.perf_counter()
    tb.run()
    sink.close()
    demod_seconds = time.perf_counter() - began
    packets = parse_bits(output)
    return packets, demod_seconds


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    parser.add_argument('--sweep', action='store_true')
    parser.add_argument('--repeat', type=int, default=1)
    parser.add_argument('--only', help='Run only this configuration; overlap is then relative to itself')
    args = parser.parse_args()
    folder = args.folder.resolve()
    path = folder / 'iq.cf32'
    metadata = json.loads((folder / 'capture.json').read_text())
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    assert digest.hexdigest() == metadata['sha256'], 'IQ hash mismatch'
    if metadata.get('host_dropped_samples') or metadata.get('errors'):
        raise RuntimeError('Cannot compare a recording with known loss or capture errors')
    if metadata['rate'] != 4000000 or metadata['channel'] != 37:
        raise ValueError('This experiment currently fixes 4 MSPS / channel 37')
    duration = path.stat().st_size / 8 / metadata['rate']
    configs = [('gnu_default', .175, None), ('gnu_filtered', .175, 650000.)]
    if args.sweep:
        configs += [(f'gnu_mu{mu}_bw{bw}', mu, bw) for mu in (.03, .08, .3)
                    for bw in (None, 650000.)]
    report = dict(gnuradio=gr.version(), python=sys.version, platform=platform.platform(),
                  iq_sha256=digest.hexdigest(), duration_seconds=duration,
                  note='Offline WSL throughput including file IO and framing, not live Windows throughput. '
                       'Shared BLE parser; GNU Radio generic GFSK continuous-stream receiver. '
                       'Payload multiset overlap does not establish exact RF-event matches.', results={})
    baseline = None
    for name, mu, cutoff in [('numpy_existing', None, None), ('numpy_filtered', None, 650000.),
                             ('numpy_production', None, None)] + configs:
        if args.only and name != args.only:
            continue
        trials = []
        trial_counts = []
        for _ in range(args.repeat):
            began = time.perf_counter()
            if name.startswith('numpy_'):
                packets = decode_numpy(path, cutoff, production=name == 'numpy_production')
                demod_seconds = None
            else:
                packets, demod_seconds = decode_gnu(path, folder / (name + '.bits'), mu, cutoff)
            elapsed = time.perf_counter() - began
            trials.append(elapsed)
            trial_counts.append(len(packets))
        counts = Counter(p['pdu_hex'] for p in packets)
        if baseline is None:
            baseline = counts
        row = dict(valid_packets=len(packets), unique_pdus=len(counts), seconds=trials,
                   trial_packet_counts=trial_counts,
                   realtime_factor=duration / float(np.median(trials)),
                   common_payload_occurrences=sum((counts & baseline).values()),
                   extra_payload_occurrences=sum((counts - baseline).values()),
                   missing_payload_occurrences=sum((baseline - counts).values()),
                   gain_mu=mu, cutoff_hz=cutoff, last_demod_seconds=demod_seconds)
        truth_path = folder / 'truth.json'
        if truth_path.exists():
            truth = Counter(json.loads(truth_path.read_text())['pdus'])
            row.update(expected=sum(truth.values()), correct=sum((counts & truth).values()),
                       unexpected=sum((counts - truth).values()))
        report['results'][name] = row
        (folder / (name + '.packets.json')).write_text(json.dumps(packets))
        report_name = 'comparison.json' if not args.only else ('comparison-' + args.only + '.json')
        (folder / report_name).write_text(json.dumps(report, indent=2))
        print(name, json.dumps(row), flush=True)


if __name__ == '__main__':
    main()
