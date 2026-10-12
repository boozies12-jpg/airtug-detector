"""Known-truth BLE advertisements modulated by GNU Radio; never transmitted."""
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from gnuradio import gr, blocks, digital

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.domain.sdr_rx import crc24, whiten


def main():
    # Every case has 120 distinct packets, random burst spacing, and an 8-bit preamble.
    rng = np.random.default_rng(20261011)
    bits, envelopes, pdus = [], [], []
    for i in range(120):
        gap = int(rng.integers(300, 800))
        bits.extend([0] * gap)
        envelopes.extend([0.] * gap)
        payload = bytes.fromhex('665544332211020106') + bytes([5, 0xff]) + i.to_bytes(4, 'little')
        pdu = bytes([0x42, len(payload)]) + payload
        air = np.concatenate((np.unpackbits(np.frombuffer(bytes.fromhex('aad6be898e'), np.uint8), bitorder='little'),
                              whiten(np.unpackbits(np.frombuffer(pdu + crc24(pdu), np.uint8), bitorder='little'), 37)))
        bits.extend(air)
        envelopes.extend([1.] * len(air))
        pdus.append(pdu.hex())
    bits.extend([0] * 800)
    envelopes.extend([0.] * 800)
    tb = gr.top_block()
    source = blocks.vector_source_b([int(b) for b in bits], False)
    mod = digital.gfsk_mod(samples_per_symbol=4, sensitivity=np.pi / 8, bt=.5, do_unpack=False)
    sink = blocks.vector_sink_c()
    tb.connect(source, mod, sink)
    tb.run()
    base = np.array(sink.data(), dtype=np.complex64)
    # GNU Radio's interpolation FIR delay: gaussian(16) convolved with rect(4), 19 taps => 9 samples.
    envelope = np.repeat(envelopes, 4)
    envelope = np.concatenate((np.zeros(9), envelope))[:len(base)]
    base *= .15 * envelope
    cases = [('clean', 30, 0, 0), ('cfo35k', 20, 35000, 0), ('cfo100k', 20, 100000, 0),
             ('cfo150k', 20, 150000, 0), ('snr10', 10, 35000, 0), ('snr5', 5, 35000, 0),
             ('snr0', 0, 35000, 0), ('clock150ppm', 20, 35000, 150),
             ('clock500ppm', 20, 35000, 500)]
    for name, snr, cfo, ppm in cases:
        # Fractional sample offset and rate mismatch, identical for all tested decoders.
        index = np.arange(len(base), dtype=np.float64) * (1 + ppm / 1e6) + .37
        x = np.interp(index, np.arange(len(base)), base.real) + 1j * np.interp(index, np.arange(len(base)), base.imag)
        x *= np.exp(2j * np.pi * cfo * np.arange(len(x)) / 4000000)
        noise_sigma = .15 / np.sqrt(2 * 10 ** (snr / 10))
        x += noise_sigma * (rng.normal(size=len(x)) + 1j * rng.normal(size=len(x)))
        raw = x.astype('<c8').tobytes()
        folder = ROOT / 'data/decoder-comparison' / ('synthetic-' + name)
        folder.mkdir(parents=True, exist_ok=False)
        (folder / 'iq.cf32').write_bytes(raw)
        (folder / 'capture.json').write_text(json.dumps(dict(rate=4000000, channel=37, sha256=hashlib.sha256(raw).hexdigest(),
             source='GNU Radio gfsk_mod; BT=0.5; modulation index=0.5', snr_db=snr, cfo_hz=cfo,
             clock_ppm=ppm, fractional_offset=.37, seed=20261011, source_continuity='synthetic known truth'), indent=2))
        (folder / 'truth.json').write_text(json.dumps({'pdus': pdus}, indent=2))
        print(name, len(x), flush=True)


if __name__ == '__main__':
    main()
