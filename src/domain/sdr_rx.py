"""Receive-only BLE 1M, fixed channel or sequential advertising channels. No TX calls."""
from functools import lru_cache
import argparse
import json
import os
from pathlib import Path
import queue
import threading
import time

import numpy as np
from .fir_native import NativePhase

try:
    _phase_accelerator = NativePhase()
except (OSError, AttributeError):
    _phase_accelerator = None

FREQUENCIES = {37: 2402000000, 38: 2426000000, 39: 2480000000}
AA = np.unpackbits(np.frombuffer(bytes.fromhex('d6be898e'), dtype=np.uint8), bitorder='little')


def positive_phase(values):
    """Equivalent to angle(values) > 0, without evaluating atan2 per sample."""
    if _phase_accelerator is not None and values.dtype == np.complex64 and values.ndim == 1:
        return _phase_accelerator.decide(values)
    imag, real = values.imag, values.real
    result = (imag > 0) | ((imag == 0) & np.signbit(real) & ~np.signbit(imag))
    unusual = ~np.isfinite(real) | ~np.isfinite(imag)
    if np.any(unusual):
        result[unusual] = np.angle(values[unusual]) > 0
    return result


def _crc_entry(value):
    for _ in range(8):
        value = (value >> 1) ^ (0xDA6000 if value & 1 else 0)
    return value


_CRC_TABLE = tuple(_crc_entry(value) for value in range(256))


def crc24(data):
    state = 0xAAAAAA  # reflected advertising CRCInit 0x555555
    for byte in data:
        state = (state >> 8) ^ _CRC_TABLE[(state ^ byte) & 255]
    return state.to_bytes(3, 'little')


@lru_cache(maxsize=128)
def _whitening_mask(channel, count):
    state = channel | 0x40
    mask = np.empty(count, dtype=np.uint8)
    for i in range(count):
        feedback = state & 1
        mask[i] = feedback
        state >>= 1
        if feedback:
            state ^= 0x44
    mask.flags.writeable = False
    return mask


def whiten(bits, channel):
    return np.bitwise_xor(np.asarray(bits, dtype=np.uint8),
                          _whitening_mask(channel, len(bits)))


def ad_fields(data):
    result = []
    while data:
        length = data[0]
        if not length:
            break
        if length + 1 > len(data):
            result.append({'malformed': data.hex()})
            break
        result.append({'type': data[1], 'value': data[2:1 + length].hex()})
        data = data[1 + length:]
    return result


class Decoder:
    def __init__(self, rate=4000000, channel=37, measure_power=True):
        if rate != 2250000 and (rate % 1000000 or rate < 2000000):
            raise ValueError('Use 2.25 or an integer 2 or more samples per BLE 1M symbol')
        self.sps = rate / 1000000 if rate == 2250000 else rate // 1000000
        self.channel = channel
        self.measure_power = measure_power
        self.tail = np.empty(0, np.complex64)
        self.end = 0
        self.last_packet = -100000
        self.candidates = 0
        self.crc_fail = 0
        from .fir_native import NativeAccessMatcher
        try:
            self.matcher = NativeAccessMatcher(AA)
        except (OSError, AttributeError):
            self.matcher = None

    def feed(self, samples, start):
        if start != self.end:
            self.tail = np.empty(0, np.complex64)  # never join across known loss
        x = np.concatenate((self.tail, samples))
        base = start - len(self.tail)
        self.end = start + len(samples)
        self.tail = x[-int(400 * self.sps + 8):].copy()
        if len(x) < 100 * self.sps:
            return []
        differential = x[1:] * np.conj(x[:-1])
        positive = positive_phase(differential)
        # All 32-term +/-1 sums are exact in float32; this uses faster SIMD kernels.
        pattern = AA.astype(np.float32) * 2 - 1
        hits = []
        if self.sps == 2.25:
            if self.matcher is not None and hasattr(self.matcher, 'fractional'):
                hits = self.matcher.find_fractional(positive)
            else:
                size = max(0, len(positive) - (31 * 9 // 4))
                errors = np.zeros(size, np.uint8)
                for bit in range(32):
                    offset = bit * 9 // 4
                    errors += positive[offset:offset + size] != AA[bit]
                hits = np.flatnonzero(errors <= 2).tolist()
        elif self.matcher is not None:
            hits = self.matcher.find(positive, self.sps)
        else:
            for phase in range(self.sps):
                signs = positive[phase::self.sps].astype(np.float32) * 2 - 1
                scores = np.correlate(signs, pattern, mode='valid')
                for pos in np.flatnonzero(scores >= 28):
                    hits.append(int(pos) * self.sps + phase)
        packets = []
        for position in sorted(hits):
            sample = int(position)
            absolute = base + sample
            if absolute <= self.last_packet + 8 * self.sps:
                continue
            # Evaluate phase only around access-address candidates, retaining
            # the original frequency-offset estimate and payload decisions.
            if self.sps == 2.25:
                indices = (position + np.arange(32 + 42 * 8) * self.sps).astype(np.intp)
                symbols = np.angle(differential[indices[indices < len(differential)]])
            else:
                symbols = np.angle(differential[sample:sample + (32 + 42 * 8) * self.sps:self.sps])
            if len(symbols) < 48:
                continue
            aa_symbols = symbols[:32]
            offset = (np.mean(aa_symbols[AA == 1]) + np.mean(aa_symbols[AA == 0])) / 2
            bits = (symbols[32:32 + 42 * 8] > offset).astype(np.uint8)
            plain = whiten(bits, self.channel)
            header = np.packbits(plain[:16], bitorder='little').tobytes()
            kind, length = header[0] & 15, header[1] & 63
            # Legacy primary-channel packets only. Extended advertising excluded.
            if kind > 6 or not 6 <= length <= 37:
                continue
            count = 2 + length + 3
            if len(plain) < count * 8:
                continue
            self.candidates += 1
            raw = np.packbits(plain[:count * 8], bitorder='little').tobytes()
            if crc24(raw[:-3]) != raw[-3:]:
                self.crc_fail += 1
                continue
            self.last_packet = absolute
            window = x[sample:sample + int((32 + count * 8) * self.sps)]
            power = float(np.mean(np.abs(window) ** 2)) if self.measure_power else 1.0
            packet = {'sample_index_host': absolute, 'channel': self.channel,
                      'phy': 'LE1M', 'pdu_type': kind, 'crc_ok': True,
                      'pdu_hex': raw[:-3].hex(), 'crc_hex': raw[-3:].hex(),
                      'power_dbfs': float(10 * np.log10(max(power, 1e-20))),
                      'power_reference': 'complex power / (2048 squared); uncalibrated',
                      'clipped_fraction': float(np.mean((np.abs(window.real) >= 2047/2048) |
                                                       (np.abs(window.imag) >= 2047/2048))) if self.measure_power else 0.0}
            if kind in (0, 2, 4, 6):
                packet['address'] = ':'.join(f'{b:02X}' for b in raw[2:8][::-1])
                packet['address_type'] = ('public' if not raw[0] & 0x40 else
                    {0: 'random_non_resolvable', 1: 'random_resolvable', 2: 'random_reserved', 3: 'random_static'}[raw[7] >> 6])
                packet['ad'] = ad_fields(raw[8:2 + length])
            packets.append(packet)
        return packets


def load_pluto(uri, dll_dir):
    # Keep directory handles alive for dependent Windows DLLs.
    global _dll_handles
    _dll_handles = []
    if os.name == 'nt' and dll_dir:
        dll_dir = Path(dll_dir).resolve()
        os.environ['PATH'] = str(dll_dir) + os.pathsep + os.environ['PATH']
        _dll_handles.append(os.add_dll_directory(str(dll_dir)))
    import adi
    return adi.Pluto(uri=uri)


def main(argv=None, on_packet=None, on_health=None, stop_event=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--uri', default='ip:192.168.2.1')
    p.add_argument('--dll-dir', default=str(Path(__file__).resolve().parents[2] / 'vendor/libiio-0.26/Windows-VS-2022-x64'))
    p.add_argument('--channel', type=int, choices=FREQUENCIES, default=37)
    p.add_argument('--hop', action='store_true', help='Cycle 37, 38, 39 with 10 seconds per channel')
    p.add_argument('--rate', type=int, choices=(2000000, 2250000, 3000000, 4000000), default=4000000)
    p.add_argument('--gain', type=int, default=40)
    p.add_argument('--seconds', type=float, default=30)
    p.add_argument('--buffer', type=int, default=65536)
    p.add_argument('--queue-blocks', type=int, choices=(16, 32, 64), default=16)
    p.add_argument('--output', default='runs')
    p.add_argument('--no-prefilter', action='store_true', help='Use the original unfiltered decoder for comparison')
    args = p.parse_args(argv)
    output = Path(args.output) / (time.strftime('%Y%m%d-%H%M%S') + f'-{time.time_ns() % 1000000:06d}')
    output.mkdir(parents=True, exist_ok=False)
    sdr = load_pluto(args.uri, args.dll_dir)
    sdr._ctx.set_timeout(3000)
    # One complex receive path: logical channel 0 (RX1), I and Q together.
    sdr.rx_enabled_channels = [0]
    sdr.sample_rate = args.rate
    sdr.rx_rf_bandwidth = 2000000
    channels = (37, 38, 39) if args.hop else (args.channel,)
    sdr.rx_lo = FREQUENCIES[channels[0]]
    sdr.gain_control_mode_chan0 = 'manual'
    sdr.rx_hardwaregain_chan0 = args.gain
    sdr.rx_buffer_size = args.buffer
    actual_rate = int(sdr.sample_rate)
    if actual_rate in (2000000, 2250000, 3000000, 4000000) and not args.no_prefilter:
        from src.domain.ble_filter import FilteredDecoder
        decoder_factory = lambda channel: FilteredDecoder(actual_rate, channel)
    else:
        decoder_factory = lambda channel: Decoder(actual_rate, channel)
    decoded_epoch = 0
    decoder = decoder_factory(channels[0])
    prior_crc_fail = 0
    q = queue.Queue(maxsize=args.queue_blocks)
    stop = stop_event if stop_event is not None else threading.Event()
    stats = {'scan_mode': 'hop' if args.hop else 'fixed37', 'current_channel': channels[0],
             'center_frequency_hz': FREQUENCIES[channels[0]], 'dwell_seconds': 10 if args.hop else None,
             'channel_switches': 0, 'retune_seconds': 0., 'settling_discarded_samples': 0,
             'channel_samples': {str(ch): 0 for ch in channels},
             'channel_packets': {str(ch): 0 for ch in channels},
             'hop_history': [],
             'queue_capacity': args.queue_blocks, 'sample_rate': actual_rate, 'rf_bandwidth': int(sdr.rx_rf_bandwidth), 'rx_channel_index': 0, 'rx_channel_label': 'RX1 (first receive path)',
             'received_samples': 0, 'host_dropped_samples': 0, 'queue_high_water': 0,
             'read_errors': [], 'packets_crc_ok': 0, 'processed_blocks': 0,
             'decode_seconds': 0., 'decode_max_seconds': 0.,
             'max_read_seconds': 0., 'max_queue_age_seconds': 0.,
             'source_continuity': 'UNVERIFIED: no source sample counter in IQ stream'}
    metadata = vars(args) | {'actual_rate': actual_rate, 'actual_lo': int(sdr.rx_lo),
                            'rx_enabled_channels': list(sdr.rx_enabled_channels),
                            'actual_gain': float(sdr.rx_hardwaregain_chan0),
                            'firmware': sdr._ctx.attrs.get('fw_version', 'unknown'),
                            'source': 'Pluto RX only', 'decoder': type(decoder).__name__,
                            'timestamp_note': 'host clock, not RF timestamp'}
    (output / 'config.json').write_text(json.dumps(metadata, indent=2))

    def capture():
        epoch = 0
        channel = channels[0]
        next_hop = time.perf_counter() + 10
        while not stop.is_set():
            try:
                if args.hop and time.perf_counter() >= next_hop:
                    retune_start = time.perf_counter()
                    # Only the capture thread touches the radio. Destroy the old
                    # buffer before tuning so old-channel IQ is never relabelled.
                    sdr.rx_destroy_buffer()
                    epoch += 1
                    channel = channels[epoch % len(channels)]
                    sdr.rx_lo = FREQUENCIES[channel]
                    # Discard a fresh buffer for LO/filter settling, then start
                    # the dwell clock. This gap is intentional, not a queue loss.
                    discarded = len(sdr.rx())
                    stats['received_samples'] += discarded
                    stats['settling_discarded_samples'] += discarded
                    now = time.perf_counter()
                    stats['retune_seconds'] += now - retune_start
                    stats['channel_switches'] = epoch
                    stats['current_channel'] = channel
                    stats['center_frequency_hz'] = FREQUENCIES[channel]
                    stats['hop_history'].append({'elapsed_seconds': now - began, 'channel': channel})
                    # Bound telemetry in an all-day scan.
                    stats['hop_history'] = stats['hop_history'][-120:]
                    next_hop = now + 10
                read_start = time.perf_counter()
                samples = sdr.rx().astype(np.complex64) / np.float32(2048)
                received_at = time.perf_counter()
                stats['max_read_seconds'] = max(stats['max_read_seconds'], received_at - read_start)
                start = stats['received_samples']
                stats['received_samples'] += len(samples)
                try:
                    q.put_nowait((start, samples, received_at, channel, epoch))
                    stats['queue_high_water'] = max(stats['queue_high_water'], q.qsize())
                except queue.Full:
                    stats['host_dropped_samples'] += len(samples)
            except Exception as exc:
                if not stop.is_set():
                    stats['read_errors'].append(repr(exc))
                stop.set()

    thread = threading.Thread(target=capture, daemon=True)
    began = time.perf_counter()
    thread.start()
    last_health = began
    try:
        with (output / 'packets.jsonl').open('w') as packets:
            while time.perf_counter() - began < args.seconds and not stop.is_set():
                try:
                    start, samples, received_at, channel, epoch = q.get(timeout=1)
                except queue.Empty:
                    continue
                t = time.perf_counter()
                stats['max_queue_age_seconds'] = max(stats['max_queue_age_seconds'], t - received_at)
                if epoch != decoded_epoch:
                    prior_crc_fail += decoder.crc_fail
                    decoder = decoder_factory(channel)
                    decoded_epoch = epoch
                decoded = decoder.feed(samples, start)
                stats['channel_samples'][str(channel)] += len(samples)
                stats['channel_packets'][str(channel)] += len(decoded)
                elapsed = time.perf_counter() - t
                stats['decode_seconds'] += elapsed
                stats['decode_max_seconds'] = max(stats['decode_max_seconds'], elapsed)
                stats['processed_blocks'] += 1
                for packet in decoded:
                    packets.write(json.dumps(packet) + '\n')
                    if on_packet:
                        on_packet(packet)
                stats['packets_crc_ok'] += len(decoded)
                if on_health and time.perf_counter() - last_health >= 1:
                    on_health(dict(stats, output=str(output)))
                    last_health = time.perf_counter()
    finally:
        stop.set()
        if getattr(sdr, '_rxbuf', None) is not None:
            sdr._rxbuf.cancel()
        thread.join(timeout=10)
        stats['capture_thread_stopped'] = not thread.is_alive()
        stats['queued_blocks_at_stop'] = q.qsize()
        stats['wall_seconds'] = time.perf_counter() - began
        stats['crc_failed_candidates'] = prior_crc_fail + decoder.crc_fail
        stats['block_duration_seconds'] = args.buffer / actual_rate
        stats['mean_decode_seconds'] = stats['decode_seconds'] / max(1, stats['processed_blocks'])
        stats['stream_test_passed'] = (not stats['read_errors'] and stats['processed_blocks'] > 1
                                      and not stats['host_dropped_samples']
                                      and stats['capture_thread_stopped'])
        if not thread.is_alive():
            sdr.rx_destroy_buffer()
        (output / 'health.json').write_text(json.dumps(stats, indent=2))
        if on_health:
            on_health(dict(stats, output=str(output)))
        else:
            print(json.dumps({'output': str(output), **stats}, indent=2))
    if not stats['stream_test_passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
