import json
import threading

import pytest

from src.domain.shared_capture import follow_capture, journal_path


@pytest.mark.parametrize('initial', [b'{"old":1}\n', b'{"old":'])
def test_follow_only_new_complete_packets(tmp_path, initial):
    journal = tmp_path / 'packets.jsonl'
    journal.write_bytes(initial)
    status = dict(is_scanning=True, capture_source='sdr', current_session_id='same',
                  capture_health={'output': str(tmp_path)})
    ready, stop, delivered = threading.Event(), threading.Event(), threading.Event()
    packets, errors = [], []

    def read_status():
        ready.set()
        return status

    def on_packet(packet):
        packets.append(packet)
        delivered.set()

    def run():
        try:
            follow_capture(status, tmp_path, 5, stop, on_packet, lambda _: None,
                           status_reader=read_status)
        except Exception as exc:
            errors.append(exc)

    worker = threading.Thread(target=run)
    worker.start()
    try:
        assert ready.wait(2)
        with journal.open('ab', buffering=0) as stream:
            if not initial.endswith(b'\n'):
                stream.write(b'1}\n')
            stream.write(b'{"new":')
            assert not delivered.wait(.15)
            stream.write(b'2}\n')
        assert delivered.wait(2)
        assert packets == [{'new': 2}]
    finally:
        stop.set()
        worker.join(2)
    assert not worker.is_alive()
    assert not errors
    assert status['is_scanning'] is True


def test_reject_journal_outside_capture_root(tmp_path):
    with pytest.raises(RuntimeError, match='outside'):
        journal_path({'capture_health': {'output': str(tmp_path.parent)}}, tmp_path)
