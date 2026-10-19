import numpy as np
from src.domain.sdr_rx import crc24, whiten


def reference_crc(data):
    state = 0xAAAAAA
    for byte in data:
        for bit in range(8):
            feedback = (state ^ (byte >> bit)) & 1
            state >>= 1
            if feedback:
                state ^= 0xDA6000
    return state.to_bytes(3, 'little')


def test_crc_table_matches_bitwise_reference():
    rng = np.random.default_rng(93)
    for length in range(260):
        data = rng.integers(0, 256, length, dtype=np.uint8).tobytes()
        assert crc24(data) == reference_crc(data)


def test_whitening_matches_reference_without_mutating_input_or_cache():
    rng = np.random.default_rng(94)
    for channel in range(40):
        for count in [0, 1, 16, 48, 312, 336]:
            bits = rng.integers(0, 2, count, dtype=np.uint8)
            before = bits.copy()
            expected = bits.copy()
            state = channel | 0x40
            for i in range(count):
                feedback = state & 1
                expected[i] ^= feedback
                state >>= 1
                if feedback:
                    state ^= 0x44
            actual = whiten(bits, channel)
            np.testing.assert_array_equal(actual, expected)
            np.testing.assert_array_equal(bits, before)
            actual[:] = 0
            np.testing.assert_array_equal(whiten(bits, channel), expected)
