import numpy as np
import pytest
from scipy.ndimage import gaussian_filter1d

from src.domain.ble_filter import FilteredDecoder
from src.domain.sdr_rx import Decoder, crc24, whiten


def waveform(noise=.001, corrupt=False):
    payload = bytes.fromhex('665544332211020106050954657374')
    pdu = bytes([0x42, len(payload)]) + payload
    crc = bytearray(crc24(pdu))
    if corrupt:
        crc[0] ^= 1
    prefix = np.unpackbits(np.frombuffer(bytes.fromhex('aad6be898e'), np.uint8), bitorder='little')
    bits = np.unpackbits(np.frombuffer(pdu + crc, np.uint8), bitorder='little')
    air = np.concatenate((prefix, whiten(bits, 37)))
    shaped = gaussian_filter1d(np.repeat(air.astype(np.float32) * 2 - 1, 4), 1.06)
    phase = np.cumsum(2 * np.pi * (250000 * shaped + 35000) / 4000000)
    x = np.concatenate((np.zeros(173), .15 * np.exp(1j * phase), np.zeros(1800)))
    rng = np.random.default_rng(7)
    x += noise * (rng.normal(size=len(x)) + 1j * rng.normal(size=len(x)))
    return x.astype(np.complex64), pdu.hex()


@pytest.mark.parametrize('block_size', [257, 65536])
def test_filter_preserves_raw_power_and_packet_across_boundaries(block_size):
    x, pdu = waveform()
    decoder = FilteredDecoder()
    packets = []
    for start in range(0, len(x), block_size):
        packets += decoder.feed(x[start:start + block_size], start)
    assert len(packets) == 1
    packet = packets[0]
    assert packet['pdu_hex'] == pdu
    first = packet['sample_index_host']
    length = (32 + (len(bytes.fromhex(pdu)) + 3) * 8) * 4
    expected = 10 * np.log10(np.mean(np.abs(x[first:first + length]) ** 2))
    assert packet['power_dbfs'] == pytest.approx(expected, abs=1e-5)
    # Doubling IQ amplitude changes relative power by 6.0206 dB without changing the payload.
    scaled = FilteredDecoder().feed(x * 2, 0)[0]
    assert scaled['pdu_hex'] == pdu
    assert scaled['power_dbfs'] - packet['power_dbfs'] == pytest.approx(6.0206, abs=.001)


def test_filter_improves_noisy_packet_reception():
    x, pdu = waveform(noise=.03)
    assert not Decoder().feed(x, 0)
    packets = FilteredDecoder().feed(x, 0)
    assert len(packets) == 1 and packets[0]['pdu_hex'] == pdu


def test_filter_rejects_bad_crc_and_does_not_bridge_known_loss():
    x, _ = waveform(corrupt=True)
    assert not FilteredDecoder().feed(x, 0)
    x, _ = waveform()
    decoder = FilteredDecoder()
    assert not decoder.feed(x[:400], 0)
    assert not decoder.feed(x[450:], 450)
