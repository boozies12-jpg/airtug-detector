import numpy as np
from src.domain.sdr_rx import positive_phase


def test_phase_sign_matches_atan2_for_quadrants_signed_zero_and_nonfinite():
    parts = [-np.inf, -1., -0., 0., 1., np.inf, np.nan]
    values = np.array([complex(r, i) for r in parts for i in parts], dtype=np.complex64)
    rng = np.random.default_rng(12)
    values = np.concatenate((values, (rng.normal(size=10000) + 1j*rng.normal(size=10000)).astype(np.complex64)))
    np.testing.assert_array_equal(positive_phase(values), np.angle(values) > 0)
