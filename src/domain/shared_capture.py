"""Follow a running app's raw packet journal without opening the SDR again."""
import json
from pathlib import Path
import time
import urllib.request


def app_status():
    try:
        with urllib.request.urlopen('http://127.0.0.1:41732/api/status', timeout=2) as response:
            return json.load(response)
    except (OSError, ValueError):
        return None


def active_sdr(status):
    return bool(status and status.get('is_scanning') and status.get('capture_source') == 'sdr')


def journal_path(status, capture_root):
    output = (status.get('capture_health') or {}).get('output')
    if not output:
        return None
    folder = Path(output).resolve()
    if not folder.is_relative_to(Path(capture_root).resolve()):
        raise RuntimeError('The app reported a capture folder outside the SDR capture directory.')
    return folder / 'packets.jsonl'


def follow_capture(initial_status, capture_root, seconds, stop, on_packet, on_health,
                   status_reader=app_status):
    session = initial_status.get('current_session_id')
    began = time.monotonic()
    status = initial_status
    path = journal_path(status, capture_root)
    while path is None or not path.exists():
        if stop.wait(.2):
            return
        status = status_reader()
        if not active_sdr(status) or status.get('current_session_id') != session:
            raise RuntimeError('The app SDR scan ended before its packet journal became available.')
        path = journal_path(status, capture_root)
        if time.monotonic() - began > min(30, seconds):
            raise RuntimeError('The app is scanning but has not published a capture journal yet.')

    # Join at EOF: do not replay the earlier part of the app's scan as live RF.
    with path.open('rb') as stream:
        stream.seek(0, 2)
        position = stream.tell()
        if position:
            stream.seek(-1, 2)
            skip_partial = stream.read(1) != b'\n'
        else:
            skip_partial = False
        partial = b''
        checked = 0.
        ending = None
        while not stop.is_set() and time.monotonic() - began < seconds:
            chunk = stream.read(65536)
            if chunk:
                lines = (partial + chunk).split(b'\n')
                partial = lines.pop()
                for line in lines:
                    if skip_partial:
                        skip_partial = False
                        continue
                    if line.strip():
                        packet = json.loads(line)
                        on_packet(packet)
            now = time.monotonic()
            if now - checked >= 1:
                status = status_reader()
                if status is None:
                    raise RuntimeError('Lost contact with BLE Tracker Search; shared capture stopped.')
                if status.get('current_session_id') != session or not active_sdr(status):
                    if ending is None:
                        ending = now
                elif journal_path(status, capture_root) != path:
                    ending = ending or now
                on_health(status.get('capture_health') or {})
                checked = now
            # Let the app flush its final journal blocks, but never attach to a new session.
            if ending is not None and now - ending >= 2 and not chunk:
                return
            if not chunk:
                stop.wait(.05)
