import statistics
from typing import List, Dict, Optional, Tuple, Any
from .models import SignalFreshness, TrendDirection, SignalSummary

class SignalProcessor:
    """
    Signal Processing engine adhering to Section 10 of Cursor Specification Rev 3:
      - 250ms monotonic-time bucketing for RSSI callbacks.
      - Median calculation per completed bucket.
      - Main locating gauge driven by latest 250ms completed group (with visible hold > 3s).
      - Secondary 20-second stationary summary (median of 250ms bucket medians, coverage and count).
      - 20s vs previous 20s historical trend calculation.
      - Freshness transitions: Recent (<=3s), Waiting (3s-30s), No recent (30s-60s), Lost (>60s).
    """

    def __init__(self, bucket_duration_s: float = 0.25):
        self.bucket_duration_s = bucket_duration_s
        self.signal_unit = 'dBm'
        self._buckets = {}
        self._medians = {}
        self._latest = {}

    def clear(self):
        self._buckets.clear()
        self._medians.clear()
        self._latest.clear()

    def add_observation(self, address: str, rssi: Optional[int], mono_s: float):
        if rssi is None:
            return
        buckets = self._buckets.setdefault(address, {})
        medians = self._medians.setdefault(address, {})
        index = int(mono_s / self.bucket_duration_s)
        latest = max(index, self._latest.get(address, index))
        cutoff = latest - int(125 / self.bucket_duration_s) - 1
        if index < cutoff:
            return
        if latest != self._latest.get(address):
            for old in list(buckets):
                if old < cutoff:
                    del buckets[old]
                    medians.pop(old, None)
            self._latest[address] = latest
        buckets.setdefault(index, []).append(rssi)
        medians.pop(index, None)

    def get_summary(self, address: str, current_mono_s: float, include_history: bool = True) -> SignalSummary:
        buckets = self._buckets.get(address, {})
        medians = self._medians.get(address, {})
        for index, values in buckets.items():
            if index not in medians:
                medians[index] = statistics.median(values)
        groups = [((index + 0.5) * self.bucket_duration_s, medians[index])
                  for index in sorted(buckets)]
        if not groups:
            return SignalSummary(
                signal_unit=self.signal_unit,
                current_rssi=None,
                current_age_s=999.0,
                freshness=SignalFreshness.LOST,
                summary_20s_median=None,
                summary_20s_count=0,
                summary_20s_coverage_s=0.0,
                trend_20s=TrendDirection.INSUFFICIENT_DATA,
                trend_diff_db=None,
                recent_history=[]
            )

        latest_t, latest_rssi = groups[-1]
        age_s = max(0.0, current_mono_s - latest_t)

        # Freshness state machine
        if age_s <= 3.0:
            freshness = SignalFreshness.RECENT
        elif age_s <= 30.0:
            freshness = SignalFreshness.WAITING
        elif age_s <= 60.0:
            freshness = SignalFreshness.NO_RECENT
        else:
            freshness = SignalFreshness.LOST

        # 20-second stationary summary
        w20_start = current_mono_s - 20.0
        w20_groups = [g for g in groups if g[0] >= w20_start]
        w20_count = len(w20_groups)
        w20_median = statistics.median([g[1] for g in w20_groups]) if w20_groups else None
        w20_coverage = (w20_groups[-1][0] - w20_groups[0][0]) if len(w20_groups) >= 2 else 0.0

        # Historical trend (last 20s vs preceding 20s)
        # Window 1: [now - 20, now]
        # Window 2: [now - 40, now - 20)
        w_prev_start = current_mono_s - 40.0
        w_prev_groups = [g for g in groups if w_prev_start <= g[0] < w20_start]

        trend = TrendDirection.INSUFFICIENT_DATA
        trend_diff = None

        def valid_window(g_list: List[Tuple[float, float]]) -> bool:
            if len(g_list) < 3:
                return False
            span = g_list[-1][0] - g_list[0][0]
            return span >= 10.0

        if valid_window(w20_groups) and valid_window(w_prev_groups):
            m_curr = statistics.median([g[1] for g in w20_groups])
            m_prev = statistics.median([g[1] for g in w_prev_groups])
            trend_diff = round(m_curr - m_prev, 1)
            if trend_diff >= 4.0:
                trend = TrendDirection.STRONGER
            elif trend_diff <= -4.0:
                trend = TrendDirection.WEAKER
            else:
                trend = TrendDirection.STABLE

        # Recent history for graphing (up to last 120s)
        graph_cutoff = current_mono_s - 120.0
        recent_hist = [
            {"t_rel_s": round(g[0] - current_mono_s, 2), "rssi": round(g[1], 1)}
            for g in groups if include_history and g[0] >= graph_cutoff
        ]

        return SignalSummary(
            signal_unit=self.signal_unit,
            current_rssi=round(latest_rssi, 1),
            current_age_s=round(age_s, 2),
            freshness=freshness,
            summary_20s_median=round(w20_median, 1) if w20_median is not None else None,
            summary_20s_count=w20_count,
            summary_20s_coverage_s=round(w20_coverage, 2),
            trend_20s=trend,
            trend_diff_db=trend_diff,
            recent_history=recent_hist
        )
