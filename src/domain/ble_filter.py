"""BLE channel FIR; equivalent design to GNU Radio firdes.low_pass.

4 MSPS, 650 kHz cutoff, 200 kHz transition, 49-tap Hamming window.
The decoder uses filtered IQ, but packet power is measured on the original IQ.
"""
import numpy as np
from scipy.signal import lfilter


def channel_taps():
    taps = np.sinc(2 * 650000 / 4000000 * (np.arange(49) - 24)) * np.hamming(49)
    return (taps / taps.sum()).astype(np.float32)


class FilteredDecoder:
    def __init__(self, rate=4000000, channel=37):
        from .sdr_rx import Decoder
        if rate != 4000000:
            raise ValueError('The validated FIR configuration requires 4 MSPS')
        self.decoder = Decoder(rate, channel)
        self.taps = channel_taps()
        self.delay = (len(self.taps) - 1) // 2
        self.state = np.zeros(len(self.taps) - 1, np.complex64)
        from .fir_native import NativeFir
        try:
            self.native = NativeFir(self.taps)
        except OSError:
            self.native = None
        self.raw_tail = np.empty(0, np.complex64)
        self.end = 0

    @property
    def crc_fail(self):
        return self.decoder.crc_fail

    def feed(self, samples, start):
        if start != self.end:
            self.state.fill(0)
            if self.native is not None:
                self.native.reset()
            self.raw_tail = np.empty(0, np.complex64)
        raw = np.concatenate((self.raw_tail, samples))
        base = start - len(self.raw_tail)
        self.end = start + len(samples)
        self.raw_tail = raw[-(400 * self.decoder.sps + 8 + self.delay):].copy()
        if self.native is not None:
            filtered = self.native.feed(samples)
        else:
            filtered, self.state = lfilter(self.taps, np.array([1.], np.float32), samples, zi=self.state)
        packets = self.decoder.feed(filtered, start)
        result = []
        for packet in packets:
            absolute = packet['sample_index_host'] - self.delay
            offset = absolute - base
            count = len(bytes.fromhex(packet['pdu_hex'] + packet['crc_hex']))
            length = (32 + count * 8) * self.decoder.sps
            if offset < 0 or offset + length > len(raw):
                # Never manufacture a power reading from an incomplete raw window.
                continue
            window = raw[offset:offset + length]
            packet.update(sample_index_host=absolute,
                          power_dbfs=float(10 * np.log10(max(float(np.mean(np.abs(window) ** 2)), 1e-20))),
                          clipped_fraction=float(np.mean((np.abs(window.real) >= 2047/2048) |
                                                         (np.abs(window.imag) >= 2047/2048))),
                          demod_frontend='49-tap Hamming FIR; cutoff 650 kHz; raw-IQ power',
                          filter_group_delay_samples=self.delay)
            result.append(packet)
        return result
