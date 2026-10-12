"""Live Pluto BLE -> PCAPNG -> Wireshark 4.x, and a persistent capture file.

Joins the app's running SDR capture when available; otherwise opens the receiver.
Stopping an attached viewer leaves the app's scan running.
"""
import argparse
import json
import os
from pathlib import Path
import queue
import re
import socket
import subprocess
import threading
import time

from src.domain.ble_pcapng import capture_header, packet_block
from src.domain.sdr_rx import main as receive
from src.domain.shared_capture import app_status, active_sdr, follow_capture

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--uri', default='ip:192.168.2.1')
    parser.add_argument('--seconds', type=float, default=86400)
    parser.add_argument('--no-wireshark', action='store_true', help='Save capture without launching a viewer')
    parser.add_argument('--tshark', action='store_true', help='Use TShark for automated live-stream verification')
    parser.add_argument('--wireshark', default=r'C:\Program Files\Wireshark\Wireshark.exe')
    args = parser.parse_args()
    status = app_status()
    shared = active_sdr(status)
    stamp = time.strftime('%Y%m%d-%H%M%S') + f'-{time.time_ns() % 1000000:06d}'
    folder = ROOT / 'data/wireshark-captures' / stamp
    folder.mkdir(parents=True)
    capture_path = folder / 'ble-channel37.pcapng'
    stop = threading.Event()
    pending = queue.Queue(maxsize=4096)
    stats = {'packets_saved': 0, 'viewer_packets_dropped': 0, 'viewer_error': None}
    stats['source_mode'] = 'shared_app_capture' if shared else 'direct_sdr'
    connection = None
    sender = None
    capture = None
    viewer_log = None
    print('PLUTO SDR BLE SNIFFER - channel 37 / 2402 MHz', flush=True)
    print('Sharing the app SDR scan; closing this viewer will not stop the app.' if shared
          else 'Opening the SDR directly. Stop other SDR applications first.', flush=True)
    print('Power is uncalibrated dBFS in each packet comment. No IQ recording.', flush=True)
    print(f'Capture file: {capture_path}', flush=True)
    try:
        capture = capture_path.open('wb')
        header = capture_header()
        capture.write(header)
        capture.flush()
        if not args.no_wireshark:
            executable = Path(args.wireshark).with_name('tshark.exe') if args.tshark else Path(args.wireshark)
            version = subprocess.check_output([str(executable), '--version'], text=True,
                                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            match = re.search(r'(?:Wireshark|TShark).*?\b(\d+)\.', version)
            if not match or int(match.group(1)) >= 5:
                raise RuntimeError('Live TCP input requires Wireshark 4.x. Use --no-wireshark to save a PCAPNG instead.')
            with socket.socket() as listener:
                listener.bind(('127.0.0.1', 0))
                listener.listen(1)
                listener.settimeout(45)
                port = listener.getsockname()[1]
                command = [str(executable), '-i', f'TCP@127.0.0.1:{port}']
                if args.tshark:
                    command += ['-l', '-T', 'fields', '-e', 'frame.number', '-e', 'btle.advertising_address', '-e', 'frame.comment']
                else:
                    command += ['-k', '-o', 'gui.window_title:Pluto SDR BLE channel 37']
                viewer_log = (folder / 'viewer.log').open('w', encoding='utf-8')
                # Dedicated English viewer profile; raw over-the-air names remain unchanged.
                profile = ROOT / 'data/wireshark-profile'
                profile.mkdir(parents=True, exist_ok=True)
                (profile / 'language').write_text('language: en\n', encoding='utf-8')
                viewer_env = dict(os.environ, WIRESHARK_CONFIG_DIR=str(profile))
                subprocess.Popen(command, stdout=viewer_log, stderr=viewer_log, env=viewer_env,
                                 creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                print('Waiting for Wireshark to connect...', flush=True)
                connection, _ = listener.accept()
            connection.settimeout(2)
            connection.sendall(header)

            def send_packets():
                try:
                    while True:
                        try:
                            data = pending.get(timeout=.25)
                        except queue.Empty:
                            if stop.is_set():
                                return
                            # Detect viewer stop even when no RF packets arrive.
                            import select
                            readable, _, _ = select.select([connection], [], [], 0)
                            if readable and connection.recv(1, socket.MSG_PEEK) == b'':
                                stop.set()
                                return
                            continue
                        connection.sendall(data)
                except OSError as exc:
                    stats['viewer_error'] = str(exc)
                    stop.set()
            sender = threading.Thread(target=send_packets, daemon=True)
            sender.start()

        def packet(value):
            data = packet_block(value)
            capture.write(data)
            stats['packets_saved'] += 1
            if connection:
                try:
                    pending.put_nowait(data)
                except queue.Full:
                    stats['viewer_packets_dropped'] += 1

        def health(value):
            capture.flush()
            stats['capture_health'] = value
            print(f"Packets: {stats['packets_saved']} | host samples dropped: {value.get('host_dropped_samples', 'unknown')} | "
                  f"viewer packets dropped: {stats['viewer_packets_dropped']} | read errors: {len(value.get('read_errors', []))}", flush=True)

        dll = os.environ.get('PLUTO_DLL_DIR', str(ROOT / 'vendor/libiio-0.26/Windows-VS-2022-x64'))
        print('Receiving. Press Ctrl+C here or Stop in Wireshark to finish.', flush=True)
        if shared:
            follow_capture(status, ROOT / 'data/sdr-captures', args.seconds, stop, packet, health)
        else:
            # The user may have started the app while Wireshark was opening.
            latest = app_status()
            if active_sdr(latest):
                stats['source_mode'] = 'shared_app_capture'
                follow_capture(latest, ROOT / 'data/sdr-captures', args.seconds, stop, packet, health)
            else:
                receive(['--uri', args.uri, '--seconds', str(args.seconds), '--dll-dir', dll,
                         '--output', str(folder / 'receiver')], on_packet=packet, on_health=health, stop_event=stop)
    except KeyboardInterrupt:
        print('\nStopping capture export...', flush=True)
    finally:
        stop.set()
        if sender:
            sender.join(timeout=3)
        if connection:
            connection.close()
        if capture:
            capture.close()
        if viewer_log:
            viewer_log.close()
        (folder / 'sniffer-health.json').write_text(json.dumps(stats, indent=2), encoding='utf-8')
        print(f'Saved {stats["packets_saved"]} packets: {capture_path}', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'Capture could not continue: {exc}', flush=True)
        raise SystemExit(1)
