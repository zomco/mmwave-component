import test from 'node:test';
import assert from 'node:assert/strict';
import { createClock, createRealClock } from '../src/protocol/clock.js';
import { ProtocolClient } from '../src/protocol/client.js';
import { loadSchema, nextRevision, validateRequest, wifiPasswordIssue } from '../src/protocol/contract.js';
import { CODE, ERROR, KIND } from '../src/protocol/limits.js';
import { checkJson, classifyNumber } from '../src/protocol/json.js';
import { encodeFrame } from '../src/protocol/codec.js';
import { encodeUtf8 } from '../src/protocol/utf8.js';
import { link, observation } from '../src/protocol/simulator.js';
import { validate } from '../src/protocol/schema.js';

const schema = loadSchema();
const nonce = '0123456789abcdef0123456789abcdef';

async function open() {
  const clock = createClock(1000);
  const linked = link(clock, { profile: 'r60' });
  await linked.client.hello({ client: { name: 'mmwave-web-console', version: '0.1.0' }, nonce });
  return { ...linked, clock };
}

test('real clock times out and leaves no pending request', async () => {
  const client = new ProtocolClient({ write() {}, onData() {} }, { rpcTimeout: 50 });
  assert.equal(client.clock.kind, 'real');
  await assert.rejects(client.ping(), /timeout/);
  assert.equal(client.pending, null);
  await assert.rejects(client.ping(), /timeout/);
});

test('fake clock is explicit and write rejection does not stick', async () => {
  const clock = createClock(0);
  let fail = true;
  const client = new ProtocolClient({
    write() {
      if (fail) return Promise.reject(new Error('write failed'));
    },
    onData() {},
  }, { clock, rpcTimeout: 50 });
  await assert.rejects(client.ping(), /write failed/);
  assert.equal(client.pending, null);
  fail = false;
  const pending = client.ping();
  clock.advance(50);
  await assert.rejects(pending, /timeout/);
  client.disconnect();
  assert.equal(client.pending, null);
});

test('late response and request frame cannot complete the next RPC', async () => {
  const { client, device, clock } = await open();
  device.faults.dropResponses = 1;
  const missed = client.ping();
  clock.advance(1000);
  await assert.rejects(missed, /timeout/);
  const late = encodeFrame({ kind: KIND.response, sessionId: client.sessionId, requestId: 2, code: CODE.PING, wireSeq: 1, payload: encodeUtf8('{"ok":true,"result":{"uptime_ms":1}}') });
  client.ingest(late.wire);
  device.faults.dropResponses = 1;
  const next = client.ping();
  const requestFrame = encodeFrame({ kind: KIND.request, sessionId: client.sessionId, requestId: client.pending.requestId, code: CODE.PING, wireSeq: 1, payload: encodeUtf8('{}') });
  client.ingest(requestFrame.wire);
  assert.equal(client.pending !== null, true);
  clock.advance(1000);
  await assert.rejects(next, /timeout/);
});

test('invalid commit and ping do not change device state', async () => {
  const { client, device } = await open();
  const before = device.writeCount;
  const revision = device.revision;
  const missing = await client.request(CODE.CONFIG_COMMIT, { base_revision: revision, changes: { 'install.x_cm': 3 } });
  assert.equal(missing.json.ok, false);
  assert.equal(device.writeCount, before);
  assert.equal(device.revision, revision);
  const extra = await client.request(CODE.PING, { extra: true });
  assert.equal(extra.json.error.code, ERROR.UNKNOWN_FIELD);
  assert.equal(device.executeCount, 0);
});

test('duplicate escaped keys and unsafe exponent integers are rejected', () => {
  assert.equal(checkJson(encodeUtf8('{"a":1,"\\u0061":2}')).error, 'duplicate_key');
  assert.equal(classifyNumber('9007199254740993e0').error, 'unsafe_integer');
  assert.equal(classifyNumber('1.5').ok, true);
  assert.equal(classifyNumber('1.5e1').ok, true);
});

test('freshness uses device sent_ms and local receive time', async () => {
  const clock = createClock(10_000_000);
  const client = new ProtocolClient({ write() {}, onData() {} }, { clock });
  const field = { value: true, quality: 'valid', sample_ms: 3_600_000 };
  const fresh = client.qualityOf(field, { sentMs: 3_600_100, receivedAt: 10_000_000, now: 10_000_050, staleAfterMs: 6000, sessionLive: true, bootId: 'a', activeBootId: 'a' });
  assert.equal(fresh, 'valid');
  const delayed = client.qualityOf(field, { sentMs: 3_600_100, receivedAt: 9_990_000, now: 10_000_000, staleAfterMs: 6000, sessionLive: true });
  assert.equal(delayed, 'stale');
  const restarted = client.qualityOf(field, { sentMs: 100, receivedAt: 100, now: 100, staleAfterMs: 6000, sessionLive: true, bootId: 'old', activeBootId: 'new' });
  assert.equal(restarted, 'stale');
  const background = client.qualityOf(field, { sentMs: 3_600_100, receivedAt: 10_000_000, now: 10_000_000, staleAfterMs: 6000, sessionLive: false });
  assert.equal(background, 'stale');
});

test('telemetry budget, session close and uint64 revision are enforced', async () => {
  const { client, device, clock } = await open();
  await client.subscribe([{ id: 'telemetry', max_rate_hz: 1 }], 1000);
  for (let n = 0; n < 100; n++) device.emitTelemetry(observation('zero'));
  assert.equal(device.sentTelemetry, 1);
  const heldTelemetry = device.heldEvents.filter((item) => item.code === CODE.TELEMETRY).length;
  assert.equal(device.stats.telemetryCoalesced + heldTelemetry, 99);
  assert.ok(device.sentEventBytes <= 1000);
  assert.ok(client.events.length <= 32);
  const closed = await client.request(CODE.SESSION_CLOSE, {});
  assert.equal(closed.json.result.closed, true);
  const after = client.ping();
  clock.advance(1000);
  await assert.rejects(after);
  device.emitTelemetry(observation('zero'));
  assert.equal(device.sentTelemetry, 1);
  const again = await client.hello({ client: { name: 'mmwave-web-console', version: '0.1.0' }, nonce });
  assert.notEqual(again.sessionId, closed.sessionId);
  const quiet = await open();
  await quiet.client.subscribe([{ id: 'telemetry', max_rate_hz: 5 }], 8000);
  quiet.device.emitTelemetry(observation('zero'));
  const sentBefore = quiet.device.sentTelemetry;
  quiet.clock.advance(15000);
  quiet.device.emitTelemetry(observation('zero'));
  assert.equal(quiet.device.sentTelemetry, sentBefore);
  assert.equal(quiet.device.session, null);
  device.revision = '9007199254740992';
  device.bumpExternal('install.x_cm', 4);
  assert.equal(device.revision, '9007199254740993');
  assert.equal(nextRevision('9007199254740992'), '9007199254740993');
});

test('schema rejects bad presence, proto keys and open responses stay compatible', () => {
  const presence = { value: 'yes', quality: 'valid', sample_ms: 1 };
  assert.equal(validate(schema.$defs.presenceSample, presence, schema).ok, false);
  const unknown = { value: true, quality: 'unknown', sample_ms: null };
  assert.equal(validate(schema.$defs.presenceSample, unknown, schema).ok, false);
  const proto = {};
  Object.defineProperty(proto, '__proto__', { value: { admin: true }, enumerable: true });
  assert.equal(validate(schema.$defs.empty, proto, schema).ok, false);
  const ping = validateRequest(CODE.PING, { extra: 1 });
  assert.equal(ping.ok, false);
  const open = validate(schema.$defs.pingResult, { uptime_ms: 1, future: true }, schema);
  assert.equal(open.ok, true);
  assert.equal(validate(schema.$defs.scanItem, { ssid: 'Lab', rssi_dbm: -40, auth: 'unknown', hidden: false }, schema).ok, true);
  assert.equal(validate(schema.$defs.wifiProvisionRequest, { op_id: 'd8592ab1-394a-4b1e-89ae-3de15b250015', ssid: 'Home', auth: 'unknown', password: '' }, schema).ok, false);
  assert.equal(wifiPasswordIssue({ auth: 'open', password: 'x' }).ok, false);
  assert.equal(validate(schema.$defs.wifiProvisionRequest, { op_id: 'd8592ab1-394a-4b1e-89ae-3de15b250015', ssid: 'Home', auth: 'open', password: 'x' }, schema).ok, false);
  for (const code of Object.keys(schema['x-commands'])) {
    const command = schema['x-commands'][code];
    assert.equal(Boolean(command.request || command.event), true, command.name);
    if (command.result) assert.equal(schema.$defs[command.result.$ref.split('/').pop()]['x-open-object'], true, command.name);
  }
});
