"""Explicit hardware integration check; never runs as part of pytest."""
import asyncio
import json
import time
from pathlib import Path
from src.domain.acquisition import AcquisitionOrchestrator
from src.domain.classifier import ClassifierEngine, RuleCatalog
from src.domain.session_manager import SessionManager
from src.domain.signal_processor import SignalProcessor


async def main():
    root = Path(__file__).resolve().parent
    catalog = RuleCatalog(str(root / 'rules'))
    catalog.load()
    o = AcquisitionOrchestrator(ClassifierEngine(catalog), SignalProcessor(), SessionManager(str(root / 'data')))
    results = []
    for source in ('computer', 'sdr', 'computer'):
        try:
            began = time.monotonic()
            await o.start_scan(session_name='Live backend verification', source=source)
            await asyncio.sleep(10)
            result = {'source': source, 'addresses': len(o.devices),
                      'candidates': sum(d['classification'].is_candidate for d in o.devices.values()),
                      'unit': o.signal_processor.signal_unit, 'health': o.capture_health,
                      'error': o.last_error, 'elapsed_seconds': time.monotonic() - began}
            assert o.devices and not o.last_error, result
            results.append(result)
        finally:
            await o.stop_scan()
    (root / 'data/backend-check.json').write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
