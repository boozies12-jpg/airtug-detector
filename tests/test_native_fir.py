from pathlib import Path
import numpy as np
import pytest
from scipy.signal import lfilter
from src.domain.ble_filter import channel_taps
from src.domain.fir_native import NativeFir
from src.domain.fir_native import NativeAccessMatcher
from src.domain.sdr_rx import AA

pytestmark = pytest.mark.skipif(
    not (Path(__file__).resolve().parents[1] / 'src/domain/libble_fir.so').exists(),
    reason='Optional board FIR library is not built')


@pytest.mark.parametrize('size', [1, 17, 257, 65536])
def test_native_stream_matches_reference_with_reset(size):
    rng = np.random.default_rng(42)
    x = (rng.normal(size=10007) + 1j * rng.normal(size=10007)).astype(np.complex64)
    taps = channel_taps()
    fir = NativeFir(taps)
    for scale in [1, 0.13]:
        fir.reset()
        data = x * scale
        actual = np.concatenate([fir.feed(data[i:i+size]) for i in range(0, len(x), size)])
        expected = lfilter(taps, np.array([1.], np.float32), data)
        np.testing.assert_allclose(actual, expected, atol=5e-7, rtol=5e-6)
        assert fir.feed(np.empty(0, np.complex64)).size == 0


@pytest.mark.parametrize('sps', [2, 3, 4])
def test_native_access_matches_reference_at_thresholds_and_phases(sps):
    rng = np.random.default_rng(19)
    matcher = NativeAccessMatcher(AA)
    for size in [0, 7, 128, 4096]:
        bits = rng.integers(0, 2, size=size, dtype=np.uint8)
        if size == 4096:
            for phase in range(sps):
                for errors in range(4):
                    start = (phase * 200 + errors * 40) * sps + phase
                    word = AA.copy()
                    word[:errors] ^= 1
                    bits[start:start + 32*sps:sps] = word
        expected = []
        for phase in range(sps):
            decisions = bits[phase::sps].astype(np.int16) * 2 - 1
            if len(decisions) < 32:
                continue
            scores = np.correlate(decisions, AA.astype(np.int16)*2-1, mode='valid')
            expected += [int(p)*sps+phase for p in np.flatnonzero(scores >= 28)]
        assert sorted(matcher.find(bits, sps)) == sorted(expected)
