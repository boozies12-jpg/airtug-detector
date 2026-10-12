import test from 'node:test';
import assert from 'node:assert/strict';
import {sortDevices, stableAddresses, matchesFilter, nextAddresses} from '../src/utils/deviceOrder.ts';
const device = (address, rssi, age = 1, name = address) => ({address, local_name: name, is_pinned: false,
  classification: {evidence: {}}, signal: {current_rssi: rssi, current_age_s: age}});

test('locked order survives signal reversal and appends new devices', () => {
  const first = sortDevices([device('a', -60), device('b', -40)], 'signal').map(x => x.address);
  assert.deepEqual(first, ['b', 'a']);
  const changed = [device('a', -20), device('b', -90), device('c', -10)];
  assert.deepEqual(stableAddresses(first, changed), ['b', 'a', 'c']);
  assert.deepEqual(sortDevices(changed, 'signal').map(x => x.address), ['c', 'a', 'b']);
});
test('name, recency, null power and snapshot filters', () => {
  const devices = [device('b', null, 30, 'Bravo'), device('a', -40, 2, 'Alpha')];
  assert.equal(sortDevices(devices, 'name')[0].address, 'a');
  assert.equal(sortDevices(devices, 'recent')[0].address, 'a');
  assert.equal(sortDevices(devices, 'signal')[0].address, 'a');
  const accepted = new Set(devices.filter(x => matchesFilter(x, {query: 'alpha', minSignal: '-50', maxAge: '10'})).map(x => x.address));
  devices[1].signal.current_rssi = -100;
  assert(accepted.has('a'));
  assert(!matchesFilter(devices[0], {query: '', minSignal: '-50', maxAge: ''}));
});

test('first-minute ordering freezes at 60 seconds and explicit lock can freeze early', () => {
  const items = [device('a', -20), device('b', -80)];
  assert.deepEqual(nextAddresses(['b','a'], items, 'signal', 59, false), ['a','b']);
  assert.deepEqual(nextAddresses(['b','a'], items, 'signal', 60, false), ['b','a']);
  assert.deepEqual(nextAddresses(['b','a'], items, 'signal', 600, false), ['b','a']);
  assert.deepEqual(nextAddresses(['b','a'], items, 'signal', 10, true), ['b','a']);
});
