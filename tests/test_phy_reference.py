import unittest
import numpy as np
from scipy.ndimage import gaussian_filter1d
from src.domain.sdr_rx import Decoder, crc24, whiten


def waveform(channel=37, rate=4000000, corrupt=False):
    # Nonconnectable advertising: AdvA plus Flags and local name.
    payload = bytes.fromhex('665544332211020106050954657374')
    pdu = bytes([0x42, len(payload)]) + payload
    crc = bytearray(crc24(pdu))
    if corrupt:
        crc[0] ^= 1
    bits = np.unpackbits(np.frombuffer(pdu + crc, dtype=np.uint8), bitorder='little')
    prefix = np.unpackbits(np.frombuffer(bytes.fromhex('aad6be898e'), dtype=np.uint8), bitorder='little')
    air = np.concatenate((prefix, whiten(bits, channel)))
    sps = rate // 1000000
    symbols = np.repeat(air.astype(np.float32) * 2 - 1, sps)
    shaped = gaussian_filter1d(symbols, .265 * sps)
    phase = np.cumsum(2 * np.pi * (250000 * shaped + 35000) / rate)
    rng = np.random.default_rng(7)
    x = np.concatenate((np.zeros(173), .15 * np.exp(1j * phase), np.zeros(1800)))
    x += .001 * (rng.normal(size=len(x)) + 1j * rng.normal(size=len(x)))
    return x.astype(np.complex64), pdu


class DecodeTests(unittest.TestCase):
    def test_crc_reference(self):
        # CRC-24/BLE catalogue check vector, serialized little endian.
        self.assertEqual(crc24(b'123456789').hex(), '565ac2')

    def test_gfsk_noise_cfo_and_block_boundaries(self):
        for rate in (2000000, 3000000, 4000000):
            for channel in (37, 38, 39):
                x, pdu = waveform(channel, rate)
                decoder = Decoder(rate, channel)
                result = []
                for start in range(0, len(x), 257):
                    result += decoder.feed(x[start:start + 257], start)
                self.assertEqual(len(result), 1, (rate, channel))
                self.assertEqual(result[0]['pdu_hex'], pdu.hex())
                self.assertEqual(result[0]['address'], '11:22:33:44:55:66')

    def test_crc_rejects_corruption(self):
        x, _ = waveform(corrupt=True)
        self.assertEqual(Decoder().feed(x, 0), [])

    def test_does_not_stitch_across_known_loss(self):
        x, _ = waveform()
        decoder = Decoder()
        self.assertEqual(decoder.feed(x[:400], 0), [])
        self.assertEqual(decoder.feed(x[450:], 450), [])


if __name__ == '__main__':
    unittest.main()
