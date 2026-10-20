import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from src.domain.acquisition import AcquisitionOrchestrator
from src.domain.classifier import ClassifierEngine, RuleCatalog
from src.domain.session_manager import SessionManager
from src.domain.signal_processor import SignalProcessor
from src.domain.sdr_backend import parse_advertisement


def make_orchestrator(tmp_path):
    catalog = RuleCatalog(str(Path(__file__).resolve().parents[1] / 'rules'))
    catalog.load()
    return AcquisitionOrchestrator(ClassifierEngine(catalog), SignalProcessor(), SessionManager(str(tmp_path)))


def packet():
    return {'address': 'AA:BB:CC:DD:EE:FF', 'crc_ok': True, 'channel': 37, 'power_dbfs': -25.75,
            'ad': [{'type': 255, 'value': '4c001219' + '11' * 25}]}


def test_sdr_uses_existing_classifier_and_preserves_unit_and_raw(tmp_path):
    o = make_orchestrator(tmp_path)
    o.is_scanning = True
    o.source = 'sdr'
    o.signal_processor.signal_unit = 'dBFS'
    sid = o.session_manager.start_session('sdr', '1', 'a')
    o._handle_sdr_packet(packet())
    row = o.devices['AA:BB:CC:DD:EE:FF']
    assert row['classification'].is_candidate
    assert row['record'].signal_unit == 'dBFS'
    assert row['record'].rssi == -25.75
    assert row['record'].raw_sdr_metadata['crc_ok']
    o.session_manager.close_session()
    csv = o.session_manager.export_csv(sid)
    assert 'Signal Unit' in csv and 'dBFS' in csv and 'sdr' in csv


def test_reject_bad_crc_and_wrong_packet_type():
    assert parse_advertisement(dict(packet(), crc_ok=False)) is None
    assert parse_advertisement({'crc_ok': True}) is None


@pytest.mark.asyncio
async def test_switch_clears_old_signal_target_and_marks(tmp_path):
    o = make_orchestrator(tmp_path)
    o.selected_target_address = 'old'
    o.pinned_addresses = ['old']
    o.found_addresses = {'old': {}}
    o.signal_processor.add_observation('old', -10, 1)
    await o.start_scan(demo_mode=True)
    assert o.selected_target_address is None
    assert not o.pinned_addresses and not o.found_addresses
    assert o.signal_processor.signal_unit == 'dBm'
    assert o.signal_processor.get_summary('old', 2).current_rssi is None
    with pytest.raises(ValueError):
        await o.start_scan(source='sdr')
    await o.stop_scan()


@pytest.mark.asyncio
async def test_failed_sdr_start_closes_session(tmp_path, monkeypatch):
    class FailedBackend:
        def __init__(self, *args): pass
        async def start(self, uri, scan_mode='fixed37'): raise RuntimeError('No Pluto connected')
        async def stop(self): pass
    monkeypatch.setattr('src.domain.acquisition.SdrBackend', FailedBackend)
    o = make_orchestrator(tmp_path)
    with pytest.raises(RuntimeError, match='No Pluto'):
        await o.start_scan(source='sdr')
    assert not o.is_scanning
    assert o.session_manager.current_session_id is None
    assert o.last_error == 'No Pluto connected'
