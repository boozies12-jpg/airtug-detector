"""Board-only Wi-Fi switching with an independent systemd recovery timer.

Passwords go only to NetworkManager; state and API responses never contain them.
Every boot still defaults to the field AP. A client switch must be confirmed
from a reachable browser before its recovery timer is cancelled.
"""
import asyncio
import json
import os
from pathlib import Path
import socket
import time
import uuid


class WifiControl:
    def __init__(self, interface, state_path, recovery_seconds=180):
        self.interface = interface
        self.state_path = Path(state_path)
        self.recovery_seconds = recovery_seconds
        self.lock = asyncio.Lock()
        self.hotspot = 'ble-poc-hotspot'

    async def run(self, *args):
        process = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            out, _ = await asyncio.wait_for(process.communicate(), timeout=20)
        except BaseException:
            process.kill()
            await process.wait()
            raise
        if process.returncode:
            # Do not echo command lines or NM errors: they can contain secrets.
            raise RuntimeError('Network operation failed; the field network recovery remains scheduled.')
        return out.decode('utf-8', errors='replace').strip()

    def read_state(self):
        try:
            return json.loads(self.state_path.read_text(encoding='utf-8'))
        except FileNotFoundError:
            return {}

    def save_state(self, state):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix('.tmp')
        temporary.write_text(json.dumps(state), encoding='utf-8')
        os.replace(temporary, self.state_path)

    async def active(self):
        profile = await self.run('nmcli', '-g', 'GENERAL.CON-UUID', 'device', 'show', self.interface)
        if not profile or profile == '--':
            return {'mode': 'disconnected', 'ssid': '', 'profile': ''}
        values = await self.run('nmcli', '--escape', 'no', '-g',
                                '802-11-wireless.mode,802-11-wireless.ssid',
                                'connection', 'show', profile)
        mode, _, ssid = values.partition('\n')
        return {'mode': 'hotspot' if mode == 'ap' else 'client', 'ssid': ssid, 'profile': profile}

    async def status(self):
        active = await self.active()
        state = self.read_state()
        pending = state if state.get('deadline', 0) > time.time() and not state.get('confirmed') else None
        addresses = await self.run('nmcli', '-g', 'IP4.ADDRESS', 'device', 'show', self.interface)
        return {'enabled': True, 'mode': active['mode'], 'ssid': active['ssid'],
                'addresses': [a.split('/')[0] for a in addresses.splitlines() if a],
                'hostname_url': f'http://{socket.gethostname()}.local:41732',
                'field_url': 'http://192.168.50.1:41732',
                'pending': {'ssid': pending['ssid'], 'deadline': pending['deadline']} if pending else None}

    async def schedule(self, unit, seconds, profile):
        await self.run('systemd-run', '--user', '--quiet', f'--unit={unit}',
                       f'--on-active={seconds}s', '--timer-property=AccuracySec=1s',
                       '/usr/bin/nmcli', '--wait', '35', 'connection', 'up', profile)

    async def stop_unit(self, unit):
        loaded = await self.run('systemctl', '--user', 'show', '--property=LoadState', '--value', unit)
        if loaded == 'loaded':
            await self.run('systemctl', '--user', 'stop', unit)

    async def connect(self, ssid='', password='', saved=False):
        if not saved:
            if not 1 <= len(ssid.encode('utf-8')) <= 32 or any(ord(c) < 32 for c in ssid):
                raise ValueError('Network name must contain 1–32 UTF-8 bytes without control characters.')
            if password and not (8 <= len(password) <= 63 or
                                 (len(password) == 64 and all(c in '0123456789abcdefABCDEF' for c in password))):
                raise ValueError('Use an 8–63 character Wi-Fi password, or leave empty for an open network.')
        async with self.lock:
            previous = self.read_state()
            if previous.get('deadline', 0) > time.time() and not previous.get('confirmed'):
                raise ValueError('A network change is already waiting for confirmation.')
            action = uuid.uuid4().hex
            profile = 'ble-poc-workshop' if saved else f'ble-poc-client-{action}'
            if saved:
                ssid = await self.run('nmcli', '--escape', 'no', '-g', '802-11-wireless.ssid',
                                      'connection', 'show', profile)
            else:
                args = ['nmcli', 'connection', 'add', 'type', 'wifi', 'ifname', self.interface,
                        'con-name', profile, 'ssid', ssid, 'connection.autoconnect', 'no',
                        'ipv4.method', 'auto', 'ipv6.method', 'auto']
                if password:
                    args += ['wifi-sec.key-mgmt', 'wpa-psk', 'wifi-sec.psk', password]
                await self.run(*args)
            # Resolve the exact generated/saved profile before scheduling any disconnect.
            profile_uuid = await self.run('nmcli', '-g', 'connection.uuid', 'connection', 'show', profile)
            recovery = f'ble-wifi-recover-{action}'
            activation = f'ble-wifi-switch-{action}'
            # Recovery is installed FIRST and survives the API process or browser exiting.
            await self.schedule(recovery, self.recovery_seconds, self.hotspot)
            state = {'ssid': ssid, 'profile': profile_uuid, 'recovery': recovery,
                     'activation': activation, 'deadline': time.time() + self.recovery_seconds,
                     'confirmed': False}
            self.save_state(state)
            await self.schedule(activation, 5, profile_uuid)
            return {'accepted': True, 'ssid': ssid, 'recovery_seconds': self.recovery_seconds,
                    'hostname_url': f'http://{socket.gethostname()}.local:41732'}

    async def confirm(self):
        async with self.lock:
            state = self.read_state()
            if not state or state.get('confirmed') or state.get('deadline', 0) - time.time() < 5:
                raise ValueError('No active network change to confirm; reconnect through BLE-POC.')
            active = await self.active()
            if active['mode'] != 'client' or active['profile'] != state['profile']:
                raise ValueError('Connect the phone to the new Wi-Fi before confirming.')
            await self.run('systemctl', '--user', 'stop', state['recovery'] + '.timer')
            state['confirmed'] = True
            self.save_state(state)
            return {'confirmed': True}

    async def field(self):
        async with self.lock:
            state = self.read_state()
            if state.get('activation') and state.get('deadline', 0) > time.time() and not state.get('confirmed'):
                # Stop both the timer and an already-started activation before returning to AP.
                await self.stop_unit(state['activation'] + '.timer')
                await self.stop_unit(state['activation'] + '.service')
                await self.stop_unit(state['recovery'] + '.timer')
            await self.schedule('ble-wifi-field-' + uuid.uuid4().hex, 5, self.hotspot)
            self.save_state({})
            return {'accepted': True, 'field_url': 'http://192.168.50.1:41732'}
