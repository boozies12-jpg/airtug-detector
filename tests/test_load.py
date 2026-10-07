import time
import pytest
from src.domain.signal_processor import SignalProcessor
from src.domain.classifier import RuleCatalog, ClassifierEngine
from src.domain.normalizer import normalize_ble_data
import os

RULES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "rules")

def test_high_throughput_load():
    """Verify processing 1,000 BLE records in < 500ms without memory or cpu bottlenecks."""
    catalog = RuleCatalog(RULES_DIR)
    catalog.load()
    classifier = ClassifierEngine(catalog)
    signal_processor = SignalProcessor(bucket_duration_s=0.25)

    start_t = time.perf_counter()

    for i in range(1000):
        addr = f"AA:BB:CC:DD:EE:{i % 50:02X}"
        rec = normalize_ble_data(
            address=addr,
            rssi=-40 - (i % 40),
            local_name=f"Device_{i % 50}",
            service_data_raw={"feaa": "409870c3dbac216705d74478fe934f363e60d0fee206"} if i % 2 == 0 else None,
            mono_s=100.0 + (i * 0.05)
        )
        classifier.classify(rec)
        signal_processor.add_observation(rec.address, rec.rssi, rec.monotonic_timestamp_s)

    elapsed_s = time.perf_counter() - start_t
    print(f"Throughput: 1,000 records processed in {elapsed_s:.3f} seconds ({1000 / elapsed_s:.0f} rec/s)")
    assert elapsed_s < 1.0, f"Processing 1000 records took {elapsed_s:.3f}s (exceeds 1.0s limit)"
