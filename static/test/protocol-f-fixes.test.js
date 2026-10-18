import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createClock } from '../src/protocol/clock.js';
import { ProtocolClient } from '../src/protocol/client.js';
import { loadSchema } from '../src/protocol/contract.js';
import { checkJson } from '../src/protocol/json.js';
import { CODE } from '../src/protocol/limits.js';
import { encodeUtf8 } from '../src/protocol/utf8.js';
import { SimulatedDevice } from '../src/protocol/simulator.js';
import { link, observation } from '../src/protocol/simulator.js';

const cases = JSON.parse(readFileSync(new URL('../../protocol/fixtures/json-cases.json', import.meta.url), 'utf8'));
const nonce = '0123456789abcdef0123456789abcdef';

test('shared JSON fixture has an expected result for every case', () => {
  assert.ok(cases.cases.length >= 20);
  for (const item of cases.cases) {
    const parsed = checkJson(encodeUtf8(item.text));
    if (item.expect === 'accept') {
      assert.equal(parsed.ok, true, item.id);
      const value = JSON.parse(item.text).n;
      if (typeof value === 'number') assert.equal(Number.isFinite(value), true, item.id);
    } else {
      assert.equal(parsed.error, item.expect, `${item.id} ${parsed.error}`);
      if (item.expect === 'number') assert.equal(Number.isFinite(JSON.parse(item.text).n), false, item.id);
    }
  }
  assert.deepEqual(loadSchema().title, JSON.parse(readFileSync(new URL('../../docs/protocol/schema/mwcp-v1.schema.json', import.meta.url), 'utf8')).title);
  const threshold = readFileSync(new URL('../../protocol/fixtures/double-overflow-threshold.txt', import.meta.url), 'utf8').trim();
  assert.equal(threshold, ((1n << 1024n) - (1n << 970n)).toString());
});

test('events share the wire budget and ignore missing subscriptions', async () => {
  const clock = createClock(0);
  const { client, device } = link(clock, { profile: 'r60' });
  await client.hello({ client: { name: 'mmwave-web-console', version: '0.1.0' }, nonce });
  device.bumpExternal('install.x_cm', 1);
  assert.equal(device.sentEventBytes, 0);
  assert.equal(device.config['install.x_cm'], 1);
  await client.subscribe([{ id: 'telemetry', max_rate_hz: 5 }], 1000);
  const before = device.sentEventBytes;
  for (let n = 0; n < 100; n++) device.bumpExternal('install.x_cm', n);
  assert.equal(device.sentEventBytes, before);
  device.expire();
  assert.doesNotThrow(() => device.bumpExternal('install.x_cm', 7));
  assert.equal(device.config['install.x_cm'], 7);
  assert.equal(device.session, null);
});

test('mixed events stay inside 1000 and 8000 byte windows', async () => {
  const clock = createClock(0);
  const { client, device } = link(clock, { profile: 'r60' });
  await client.hello({ client: { name: 'mmwave-web-console', version: '0.1.0' }, nonce });
  await client.subscribe([
    { id: 'telemetry', max_rate_hz: 20 },
    { id: 'config', max_rate_hz: 0 },
    { id: 'logs', max_rate_hz: 0 },
  ], 1000);
  device.sentEventBytes = 0;
  device.windowStart = 0;
  for (let n = 0; n < 40; n++) {
    device.emitTelemetry(observation('zero'));
    device.bumpExternal('install.x_cm', n);
    device.enqueue(CODE.LOG, { sample_ms: n, level: 'info', source: 'sim', message: `m${n}`, dropped_before: 0 });
  }
  assert.ok(device.sentEventBytes > 0 && device.sentEventBytes <= 1000, String(device.sentEventBytes));
  assert.ok(device.heldEvents.length > 0);
  const ping = await client.ping();
  assert.equal(ping.json.ok, true);
  clock.advance(1000);
  device.poll(clock.now());
  const second = device.sentEventBytes;
  for (let n = 0; n < 40; n++) device.emitTelemetry(observation('multi'));
  assert.ok(device.sentEventBytes - second <= 1000);
  device.budgetBps = 8000;
  device.windowStart = clock.now() - 1000;
  device.poll(clock.now());
  const wideStart = device.sentEventBytes;
  for (let n = 0; n < 30; n++) device.enqueue(CODE.LOG, { sample_ms: n, level: 'info', source: 'sim', message: 'x'.repeat(40), dropped_before: 0 });
  assert.ok(device.sentEventBytes - wideStart <= 8000);
  await client.request(CODE.UNSUBSCRIBE, { streams: ['logs', 'config', 'telemetry'] });
  const after = device.sentEventBytes;
  device.bumpExternal('install.y_cm', 2);
  device.emitTelemetry(observation('zero'));
  assert.equal(device.sentEventBytes, after);
  assert.ok(device.heldEvents.length <= 16);
  assert.ok(client.events.length <= 32);
});

test('client liveness does not treat a successful write as a device response', async () => {
  const clock = createClock(0);
  const device = new SimulatedDevice({ clock, profile: 'r60' });
  const client = new ProtocolClient({
    write(bytes) { device.ingest(bytes); },
    onData() {},
  }, { clock, rpcTimeout: 1000 });
  device.onWire((bytes) => client.ingest(bytes));
  await client.hello({ client: { name: 'mmwave-web-console', version: '0.1.0' }, nonce });
  assert.equal(client.clock.kind, 'manual');
  assert.equal(client.sessionLive, true);
  device.faults.dropResponses = 100;
  client.startHeartbeat();
  clock.advance(40000);
  assert.equal(client.sessionLive, false);
  assert.equal(client.heartbeat, null);
  assert.equal(client.livenessTimer, null);
  assert.equal(client.pending, null);
  const late = client.ping();
  clock.advance(1000);
  await assert.rejects(late);
});

test('successful pings keep the session and telemetry alone does not', async () => {
  const clock = createClock(0);
  const device = new SimulatedDevice({ clock, profile: 'r60' });
  const client = new ProtocolClient({
    write(bytes) { device.ingest(bytes); },
    onData() {},
  }, { clock, rpcTimeout: 1000 });
  device.onWire((bytes) => client.ingest(bytes));
  await client.hello({ client: { name: 'mmwave-web-console', version: '0.1.0' }, nonce });
  client.startHeartbeat();
  clock.advance(20000);
  assert.equal(client.sessionLive, true);
  client.stopHeartbeat();
  await client.subscribe([{ id: 'telemetry', max_rate_hz: 5 }], 8000);
  for (let n = 0; n < 5; n++) {
    clock.advance(4000);
    device.emitTelemetry(observation('zero'));
  }
  assert.equal(client.sessionLive, false);
  assert.equal(new ProtocolClient({ write() {}, onData() {} }).clock.kind, 'real');
});
