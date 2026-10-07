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
        # Map: address -> list of raw observations [(mono_s, rssi)]
        self._raw_rssi_history: Dict[str, List[Tuple[float, int]]] = {}
        # Map: address -> list of bucketed groups [(bucket_mono_s, median_rssi)]
        self._bucketed_groups: Dict[str, List[Tuple[float, float]]] = {}

    def clear(self):
        self._raw_rssi_history.clear()
        self._bucketed_groups.clear()

    def add_observation(self, address: str, rssi: Optional[int], mono_s: float):
        if rssi is None:
            return
        if address not in self._raw_rssi_history:
            self._raw_rssi_history[address] = []
            self._bucketed_groups[address] = []

        self._raw_rssi_history[address].append((mono_s, rssi))
        self._rebucket(address)

    def _rebucket(self, address: str):
        """Aggregate raw RSSI points into fixed 250ms buckets."""
        raw = self._raw_rssi_history[address]
        if not raw:
            return

        buckets: Dict[int, List[int]] = {}
        for t, r in raw:
            b_idx = int(t / self.bucket_duration_s)
            buckets.setdefault(b_idx, []).append(r)

        groups: List[Tuple[float, float]] = []
        for b_idx in sorted(buckets.keys()):
            mid_t = (b_idx + 0.5) * self.bucket_duration_s
            med_rssi = statistics.median(buckets[b_idx])
            groups.append((mid_t, med_rssi))

        self._bucketed_groups[address] = groups

    def get_summary(self, address: str, current_mono_s: float) -> SignalSummary:
        groups = self._bucketed_groups.get(address, [])
        if not groups:
            return SignalSummary(
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
            for g in groups if g[0] >= graph_cutoff
        ]

        return SignalSummary(
            current_rssi=int(round(latest_rssi)),
            current_age_s=round(age_s, 2),
            freshness=freshness,
            summary_20s_median=round(w20_median, 1) if w20_median is not None else None,
            summary_20s_count=w20_count,
            summary_20s_coverage_s=round(w20_coverage, 2),
            trend_20s=trend,
            trend_diff_db=trend_diff,
            recent_history=recent_hist
        )
