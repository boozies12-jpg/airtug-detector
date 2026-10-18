import json
import time
import pytest
from src.domain.wifi_control import WifiControl


class FakeWifi(WifiControl):
    def __init__(self, tmp_path):
        super().__init__('wlan0', tmp_path / 'wifi.json')
        self.calls = []
        self.current = {'mode': 'hotspot', 'ssid': 'BLE-POC', 'profile': 'field-uuid'}
        self.fail_timer = False

    async def run(self, *args):
        self.calls.append(args)
        if args[0] == 'systemd-run' and self.fail_timer:
            raise RuntimeError('timer unavailable')
        if 'connection.uuid' in args:
            return 'new-client-uuid'
        if '802-11-wireless.ssid' in args:
            return 'Saved Wi-Fi'
        if '--property=LoadState' in args:
            return 'loaded'
        return ''

    async def active(self):
        return self.current


@pytest.mark.asyncio
async def test_recovery_precedes_switch_and_password_is_not_persisted(tmp_path):
    wifi = FakeWifi(tmp_path)
    await wifi.connect('Office: $(echo nope)', 'private123')
    timers = [c for c in wifi.calls if c[0] == 'systemd-run']
    assert '--on-active=180s' in timers[0] and timers[0][-1] == 'ble-poc-hotspot'
    assert '--on-active=5s' in timers[1] and timers[1][-1] == 'new-client-uuid'
    assert 'private123' not in wifi.state_path.read_text()
    assert 'private123' not in json.dumps(await wifi.status())
    with pytest.raises(ValueError, match='already'):
        await wifi.connect('second', 'private123')


@pytest.mark.asyncio
async def test_confirm_requires_target_network_and_survives_api_restart(tmp_path):
    wifi = FakeWifi(tmp_path)
    await wifi.connect(saved=True)
    restarted = FakeWifi(tmp_path)
    with pytest.raises(ValueError, match='new Wi-Fi'):
        await restarted.confirm()
    restarted.current = {'mode': 'client', 'ssid': 'Saved Wi-Fi', 'profile': 'new-client-uuid'}
    await restarted.confirm()
    assert restarted.read_state()['confirmed']
    assert any(c[:3] == ('systemctl', '--user', 'stop') and c[-1].endswith('.timer') for c in restarted.calls)


@pytest.mark.asyncio
async def test_no_switch_when_recovery_cannot_be_scheduled(tmp_path):
    wifi = FakeWifi(tmp_path)
    wifi.fail_timer = True
    with pytest.raises(RuntimeError):
        await wifi.connect('network', '')
    assert not wifi.state_path.exists()
    assert not any('--on-active=5s' in c for c in wifi.calls)


@pytest.mark.asyncio
async def test_late_confirmation_does_not_cancel_recovery(tmp_path):
    wifi = FakeWifi(tmp_path)
    await wifi.connect(saved=True)
    state = wifi.read_state(); state['deadline'] = time.time() - 1; wifi.save_state(state)
    wifi.current = {'mode': 'client', 'ssid': 'Saved Wi-Fi', 'profile': 'new-client-uuid'}
    with pytest.raises(ValueError):
        await wifi.confirm()
    assert not any(c[:3] == ('systemctl', '--user', 'stop') for c in wifi.calls)


@pytest.mark.asyncio
async def test_field_switch_cancels_previous_timers(tmp_path):
    wifi = FakeWifi(tmp_path)
    await wifi.connect(saved=True)
    state = wifi.read_state()
    await wifi.field()
    assert ('systemctl', '--user', 'stop', state['recovery'] + '.timer') in wifi.calls
    assert ('systemctl', '--user', 'stop', state['activation'] + '.service') in wifi.calls
    assert wifi.read_state() == {}
    assert wifi.calls[-1][-1] == 'ble-poc-hotspot'


@pytest.mark.asyncio
@pytest.mark.parametrize('ssid,password', [('', ''), ('a'*33, ''), ('a\nb', ''), ('network', 'short')])
async def test_invalid_credentials_do_not_modify_network(tmp_path, ssid, password):
    wifi = FakeWifi(tmp_path)
    with pytest.raises(ValueError):
        await wifi.connect(ssid, password)
    assert wifi.calls == []
