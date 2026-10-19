import random
import statistics
from src.domain.signal_processor import SignalProcessor


def test_incremental_history_matches_batch_bucketing_and_prunes():
    rng = random.Random(42)
    processor = SignalProcessor()
    raw = []
    for n in range(16000):
        timestamp = 1000 + n * .01
        power = rng.uniform(-90, -20)
        processor.add_observation('a', power, timestamp)
        raw.append((timestamp, power))
        if n % 997 == 0:
            buckets = {}
            for t, value in raw:
                buckets.setdefault(int(t / .25), []).append(value)
            expected = [{'t_rel_s': round((index + .5) * .25 - timestamp, 2),
                         'rssi': round(statistics.median(values), 1)}
                        for index, values in sorted(buckets.items())
                        if (index + .5) * .25 >= timestamp - 120]
            full = processor.get_summary('a', timestamp)
            assert full.recent_history == expected
            compact = processor.get_summary('a', timestamp, include_history=False)
            assert compact.recent_history == []
            assert compact.model_dump(exclude={'recent_history'}) == full.model_dump(exclude={'recent_history'})
    assert len(processor._buckets['a']) <= 502
    processor.clear()
    assert processor.get_summary('a', 2000).current_rssi is None


def test_out_of_order_and_multiple_addresses():
    processor = SignalProcessor()
    for timestamp, value in [(10.1, -40), (10.05, -60), (9.9, -80)]:
        processor.add_observation('a', value, timestamp)
    processor.add_observation('b', -10, 10.1)
    assert processor.get_summary('a', 10.2).current_rssi == -50
    assert processor.get_summary('b', 10.2).current_rssi == -10
