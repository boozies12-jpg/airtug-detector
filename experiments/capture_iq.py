"""Receive-only bounded IQ recording for repeatable offline comparisons."""
import argparse
import hashlib
import json
from pathlib import Path
import queue
import sys
import threading
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.domain.sdr_rx import load_pluto
from src.domain.shared_capture import app_status, active_sdr


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=float, default=10)
    parser.add_argument('--name', required=True)
    args = parser.parse_args()
    if active_sdr(app_status()):
        raise RuntimeError('The app is using Pluto; stop its SDR scan before recording IQ.')
    folder = ROOT / 'data/decoder-comparison' / args.name
    folder.mkdir(parents=True, exist_ok=False)
    sdr = load_pluto('ip:192.168.2.1', ROOT / 'vendor/libiio-0.26/Windows-VS-2022-x64')
    sdr._ctx.set_timeout(3000)
    sdr.sample_rate = 4000000
    sdr.rx_rf_bandwidth = 2000000
    sdr.rx_lo = 2402000000
    sdr.gain_control_mode_chan0 = 'manual'
    sdr.rx_hardwaregain_chan0 = 40
    sdr.rx_buffer_size = 65536
    rate = int(sdr.sample_rate)
    count = int(np.ceil(args.seconds * rate / 65536))
    pending = queue.Queue(maxsize=64)
    stats = dict(rate=rate, channel=37, lo=int(sdr.rx_lo), gain=float(sdr.rx_hardwaregain_chan0),
                 format='little-endian complex64; normalized by 2048', received_samples=0,
                 saved_samples=0, host_dropped_samples=0, queue_high_water=0, errors=[],
                 source_continuity='UNVERIFIED: no hardware sample counter', block_samples=65536)
    digest = hashlib.sha256()

    def writer():
        try:
            with (folder / 'iq.cf32').open('wb') as output:
                while True:
                    item = pending.get()
                    if item is None:
                        return
                    raw = item.astype('<c8', copy=False).tobytes()
                    output.write(raw)
                    digest.update(raw)
                    stats['saved_samples'] += len(item)
        except Exception as exc:
            stats['errors'].append(repr(exc))

    thread = threading.Thread(target=writer, daemon=True)
    began = time.perf_counter()
    thread.start()
    try:
        for _ in range(count):
            if not thread.is_alive():
                raise RuntimeError('IQ writer failed')
            samples = sdr.rx().astype(np.complex64) / np.float32(2048)
            stats['received_samples'] += len(samples)
            try:
                pending.put_nowait(samples)
                stats['queue_high_water'] = max(stats['queue_high_water'], pending.qsize())
            except queue.Full:
                stats['host_dropped_samples'] += len(samples)
                raise RuntimeError('Recording invalid: host queue overflow')
    except Exception as exc:
        stats['errors'].append(repr(exc))
    finally:
        sdr.rx_destroy_buffer()
        if thread.is_alive():
            pending.put(None, timeout=10)
        thread.join(30)
        stats['writer_stopped'] = not thread.is_alive()
        stats['wall_seconds'] = time.perf_counter() - began
        stats['duration_seconds'] = stats['saved_samples'] / rate
        stats['sha256'] = digest.hexdigest()
        (folder / 'capture.json').write_text(json.dumps(stats, indent=2))
        print(json.dumps(stats, indent=2))
    if stats['errors'] or not stats['writer_stopped']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
