import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createClock } from '../src/protocol/clock.js';
import { CODE, ERROR } from '../src/protocol/limits.js';
import { link, observation } from '../src/protocol/simulator.js';
import { encodeFrame } from '../src/protocol/codec.js';
import { KIND } from '../src/protocol/limits.js';
import { encodeUtf8 } from '../src/protocol/utf8.js';
import { validate } from '../src/protocol/schema.js';

const schema = JSON.parse(readFileSync(new URL('../../docs/protocol/schema/mwcp-v1.schema.json', import.meta.url), 'utf8'));
const nonce = '0123456789abcdef0123456789abcdef';

async function open(profile = 'r60', chunk = 0) {
  const clock = createClock(1000);
  const { client, device } = link(clock, { profile }, chunk);
  const hello = await client.hello({ client: { name: 'mmwave-web-console', version: '0.1.0' }, nonce });
  assert.equal(hello.json.ok, true);
  assert.equal(hello.json.result.origin, undefined);
  assert.equal(hello.json.result.identity.firmware_version, 'simulation');
  return { clock, client, device, hello };
}

test('handshake, ping, chunked frames and simulation mark', async () => {
  const { client, device } = await open('r60', 1);
  const ping = await client.ping();
  assert.equal(ping.json.result.uptime_ms > 0, true);
  await client.subscribe([{ id: 'telemetry', max_rate_hz: 5 }]);
  device.emitTelemetry(observation('async'));
  assert.equal(client.events.at(-1).json.origin, 'simulation');
  assert.notEqual(client.events.at(-1).json.presence.sample_ms, client.events.at(-1).json.targets_ms);
  assert.equal(validate(schema.$defs.telemetry, client.events.at(-1).json, schema).ok, true);
});

test('duplicate id, reuse, eviction and old session are not re-executed', async () => {
  const { client, device, clock } = await open();
  const first = await client.request(CODE.PING, {});
  const before = device.executeCount;
  const again = await client.request(CODE.PING, {}, { requestId: first.requestId });
  assert.equal(again.json.result.uptime_ms, first.json.result.uptime_ms);
  assert.equal(device.executeCount, before);
  const reused = await client.request(CODE.PING, { extra: false }, { requestId: first.requestId });
  assert.equal(reused.json.error.code, ERROR.ID_REUSE);
  const ids = [];
  for (let n = 0; n < 5; n++) ids.push((await client.ping()).requestId);
  const expired = await client.request(CODE.PING, {}, { requestId: ids[0] });
  assert.equal(expired.json.error.code, ERROR.REQUEST_EXPIRED);
  const oldSession = client.sessionId;
  clock.advance(1000);
  await client.hello({ client: { name: 'mmwave-web-console', version: '0.1.0' }, nonce: 'abcdef0123456789abcdef0123456789' });
  assert.notEqual(client.sessionId, oldSession);
  const late = encodeFrame({ kind: KIND.response, sessionId: oldSession, requestId: 2, code: CODE.PING, wireSeq: 1, payload: encodeUtf8('{"ok":true,"result":{"uptime_ms":1}}') });
  client.ingest(late.wire);
  assert.equal(client.ignored > 0, true);
  clock.advance(15000);
  const writes = device.writeCount;
  const stale = client.ping();
  clock.advance(1000);
  await assert.rejects(stale);
  assert.equal(device.writeCount, writes);
});

test('config conflict, dropped commit and status query do not replay', async () => {
  const { client, device, clock } = await open();
  const opId = 'd8592ab1-394a-4b1e-89ae-3de15b250015';
  device.bumpExternal('install.x_cm', 10);
  const conflict = await client.request(CODE.CONFIG_COMMIT, { base_revision: '1', op_id: opId, changes: { 'install.x_cm': 20 } });
  assert.equal(conflict.json.error.code, ERROR.REVISION_CONFLICT);
  assert.equal(device.writeCount, 0);
  device.faults.dropResponses = 1;
  const revision = device.revision;
  const changes = { 'install.x_cm': 30 };
  const pending = client.commit(changes, { baseRevision: revision, opId });
  clock.advance(2000);
  const unknown = await pending;
  assert.equal(unknown.unknown, true);
  assert.equal(device.writeCount, 1);
  const status = await client.commitStatus(opId);
  assert.equal(status.json.result.found, true);
  assert.equal(device.writeCount, 1);
  const replay = await client.request(CODE.CONFIG_COMMIT, { base_revision: revision, op_id: opId, changes });
  assert.equal(replay.json.ok, true);
  assert.equal(device.writeCount, 1);
});

test('pagination conflict, rate limit, priority and semantic observations', async () => {
  const { client, device, clock } = await open();
  clock.advance(1000);
  const page = await client.request(CODE.CAPABILITIES_LIST, { cursor: null });
  assert.equal(page.json.result.items.length, 2);
  device.capRevision = 'changed';
  const conflict = await client.request(CODE.CAPABILITIES_LIST, { cursor: page.json.result.next_cursor });
  assert.equal(conflict.json.error.code, ERROR.REVISION_CONFLICT);
  const foreign = await client.request(CODE.CAPABILITIES_LIST, { cursor: `999:${page.json.result.next_cursor}` });
  assert.equal(foreign.json.error.code, ERROR.INVALID_ARGUMENT);
  await client.subscribe([{ id: 'logs', max_rate_hz: 0 }], 8000);
  device.budgetBps = 1;
  device.enqueue(CODE.LOG, { sample_ms: 1, level: 'info', source: 'sim', message: 'kept', dropped_before: 0 });
  const before = device.sentOrder.length;
  await client.ping();
  assert.equal(device.sentOrder[before], 0);
  assert.equal(device.sentEventBytes, 0);
  for (let n = 0; n < 10; n++) await client.ping();
  const limited = await client.ping();
  assert.equal(limited.json.error.code, ERROR.RATE_LIMITED);
  clock.advance(5000);
  assert.equal(client.qualityOf({ value: 1, quality: 'valid', sample_ms: 1000 }, { sentMs: 1100, receivedAt: clock.now() - 5000, now: clock.now(), staleAfterMs: 2000, sessionLive: true }), 'stale');
  for (const kind of ['empty', 'unknown', 'zero', '1d', 'multi']) {
    const sample = observation(kind);
    assert.equal(sample.origin, 'simulation');
    assert.equal(validate(schema.$defs.telemetry, sample, schema).ok, true, kind);
  }
  assert.notDeepEqual(observation('empty').targets, observation('unknown').targets);
  assert.deepEqual(observation('zero').targets[0].local_cm, [0, 0]);
});
