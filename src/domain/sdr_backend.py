import asyncio
import json
from pathlib import Path
import subprocess
import sys
import uuid


def parse_advertisement(packet):
    """Extract AD structures without inventing scan responses or RF metadata."""
    if not packet.get('crc_ok') or not packet.get('address'):
        return None
    result = dict(address=packet['address'], name=None, manufacturer={}, services={}, uuids=[])
    for field in packet.get('ad', []):
        if 'type' not in field:
            continue
        kind, data = field['type'], bytes.fromhex(field['value'])
        if kind in (8, 9):
            result['name'] = data.decode('utf-8', errors='replace')
        elif kind == 255 and len(data) >= 2:
            result['manufacturer'][int.from_bytes(data[:2], 'little')] = data[2:]
        elif kind in (22, 32, 33):
            size = {22: 2, 32: 4, 33: 16}[kind]
            if len(data) >= size:
                key = str(uuid.UUID(bytes=data[:16][::-1])) if size == 16 else f'{int.from_bytes(data[:size], "little"):0{size*2}x}'
                result['services'][key] = data[size:]
        elif kind in (2, 3, 4, 5, 6, 7):
            size = 2 if kind < 4 else 4 if kind < 6 else 16
            for i in range(0, len(data) - size + 1, size):
                part = data[i:i+size]
                key = str(uuid.UUID(bytes=part[::-1])) if size == 16 else f'{int.from_bytes(part, "little"):0{size*2}x}'
                result['uuids'].append(key)
    return result


class SdrBackend:
    def __init__(self, packet_callback, health_callback, error_callback):
        self.packet_callback = packet_callback
        self.health_callback = health_callback
        self.error_callback = error_callback
        self.process = None
        self.reader = None
        self.ready = asyncio.Event()
        self.error = None
        self.stopping = False

    async def start(self, uri, scan_mode='fixed37'):
        self.process = await asyncio.create_subprocess_exec(
            sys.executable, '-u', '-m', 'src.domain.sdr_worker', '--uri', uri, '--scan-mode', scan_mode,
            cwd=Path(__file__).resolve().parents[2],
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.reader = asyncio.create_task(self._read())
        try:
            await asyncio.wait_for(self.ready.wait(), timeout=45)
            if self.error:
                raise RuntimeError(self.error)
        except BaseException:
            await self.stop()
            raise

    async def _read(self):
        try:
            async for line in self.process.stdout:
                try:
                    event = json.loads(line)
                except (ValueError, UnicodeError):
                    continue
                kind, value = event.get('event'), event.get('data')
                if kind == 'packet':
                    self.packet_callback(value)
                    self.ready.set()
                elif kind == 'health':
                    self.health_callback(value)
                    if value.get('read_errors'):
                        self.error = '; '.join(value['read_errors'])
                    self.ready.set()
                elif kind == 'error':
                    self.error = value
                    self.ready.set()
            code = await self.process.wait()
            if not self.stopping:
                self.error = self.error or f'SDR receiver exited ({code})'
        except Exception as exc:
            self.error = str(exc)
        finally:
            self.ready.set()
            if self.error and not self.stopping:
                self.error_callback(self.error)

    async def stop(self):
        self.stopping = True
        if self.process and self.process.returncode is None:
            try:
                self.process.stdin.write(b'STOP\n')
                await self.process.stdin.drain()
            except (BrokenPipeError, ConnectionResetError):
                pass
            try:
                await asyncio.wait_for(self.process.wait(), 8)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()
        if self.reader and self.reader is not asyncio.current_task():
            await self.reader
