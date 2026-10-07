import pytest
from src.domain.signal_processor import SignalProcessor
from src.domain.models import SignalFreshness, TrendDirection

def test_signal_processor_monotonic_bucketing():
    sp = SignalProcessor(bucket_duration_s=0.25)
    addr = "C2:9F:5B:4C:F3:69"

    # Add 3 observations within the first 250ms bucket [0.0, 0.25)
    sp.add_observation(addr, -40, mono_s=0.05)
    sp.add_observation(addr, -30, mono_s=0.10)
    sp.add_observation(addr, -35, mono_s=0.20)

    # Median of [-40, -30, -35] is -35
    summary = sp.get_summary(addr, current_mono_s=0.25)
    assert summary.current_rssi == -35
    assert summary.freshness == SignalFreshness.RECENT

def test_signal_processor_freshness_state_machine():
    sp = SignalProcessor(bucket_duration_s=0.25)
    addr = "TEST:01"

    sp.add_observation(addr, -50, mono_s=10.0)

    # At t = 12.0 (age = 2s <= 3s) -> Recent
    s1 = sp.get_summary(addr, current_mono_s=12.0)
    assert s1.freshness == SignalFreshness.RECENT

    # At t = 25.0 (age = 15s > 3s and <= 30s) -> Waiting
    s2 = sp.get_summary(addr, current_mono_s=25.0)
    assert s2.freshness == SignalFreshness.WAITING

    # At t = 50.0 (age = 40s > 30s and <= 60s) -> No recent signal
    s3 = sp.get_summary(addr, current_mono_s=50.0)
    assert s3.freshness == SignalFreshness.NO_RECENT

    # At t = 80.0 (age = 70s > 60s) -> Lost
    s4 = sp.get_summary(addr, current_mono_s=80.0)
    assert s4.freshness == SignalFreshness.LOST

def test_signal_processor_trend_calculation():
    sp = SignalProcessor(bucket_duration_s=0.25)
    addr = "TEST:TREND"

    # Preceding 20s window [0, 20): RSSI around -70 dBm
    for t in [2.0, 8.0, 14.0, 18.0]:
        sp.add_observation(addr, -70, mono_s=t)

    # Current 20s window [20, 40): RSSI around -55 dBm (+15 dB stronger)
    for t in [22.0, 28.0, 34.0, 38.0]:
        sp.add_observation(addr, -55, mono_s=t)

    summary = sp.get_summary(addr, current_mono_s=40.0)
    assert summary.trend_20s == TrendDirection.STRONGER
    assert summary.trend_diff_db is not None
    assert summary.trend_diff_db >= 4.0
