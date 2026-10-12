"""Receive-only SDR process. JSON stdout; STOP on stdin releases the receiver."""
import argparse
import json
import os
from pathlib import Path
import sys
import threading
from .sdr_rx import main as receive


def main():
    # Load numerical dependencies before a thread blocks on stdin. Some Windows
    # dependency initialization probes subprocess/platform state and stdin handles.
    from .ble_filter import FilteredDecoder  # noqa: F401
    parser = argparse.ArgumentParser()
    parser.add_argument('--uri', default='ip:192.168.2.1')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    dll = os.environ.get('PLUTO_DLL_DIR', str(root / 'vendor/libiio-0.26/Windows-VS-2022-x64'))
    stop = threading.Event()
    def control():
        for line in sys.stdin:
            if line.strip() == 'STOP':
                stop.set()
                break
    threading.Thread(target=control, daemon=True).start()
    def emit(kind, value):
        print(json.dumps({'event': kind, 'data': value}), flush=True)
    try:
        receive(['--uri', args.uri, '--dll-dir', dll, '--seconds', '86400',
                 '--output', str(root / 'data/sdr-captures')],
                on_packet=lambda value: emit('packet', value),
                on_health=lambda value: emit('health', value), stop_event=stop)
    except (Exception, SystemExit) as exc:
        emit('error', str(exc) or 'SDR capture failed')
        raise SystemExit(1)


if __name__ == '__main__':
    main()
