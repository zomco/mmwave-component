import test from 'node:test';
import assert from 'node:assert/strict';
import { createClock } from '../src/protocol/clock.js';
import { encodeFrame, FrameParser } from '../src/protocol/codec.js';
import { ProtocolClient } from '../src/protocol/client.js';
import { CODE, KIND } from '../src/protocol/limits.js';
import { encodeUtf8 } from '../src/protocol/utf8.js';
import { SimulatedDevice } from '../src/protocol/simulator.js';

const nonce = '0123456789abcdef0123456789abcdef';
const nonce2 = 'fedcba9876543210fedcba9876543210';
const clientInfo = { name: 'mmwave-web-console', version: '0.1.0' };

function answer(frame, sessionId = frame.sessionId || 7) {
  const payload = frame.code === CODE.HELLO
    ? {
        ok: true,
        result: {
          nonce: frame.json.nonce,
          protocol: { major: 1, minor: 0 },
          boot_id: nonce,
          session_ttl_ms: 15000,
          limits: { max_payload: 4096, rpc_inflight: 1, max_targets: 1, event_budget_bps: 8000 },
          identity: { device_id: 'loop', configured_model: 'r60abd1', dimension: '2D', firmware_version: 'simulation' },
          cap_revision: 'g',
        },
      }
    : frame.code === CODE.PING
      ? { ok: true, result: { uptime_ms: 1 } }
      : { ok: true, result: { streams: frame.json.streams, event_budget_bps: frame.json.event_budget_bps } };
  const encoded = encodeFrame({
    kind: KIND.response,
    sessionId: frame.code === CODE.HELLO ? sessionId : frame.sessionId,
    requestId: frame.requestId,
    code: frame.code,
    wireSeq: 1,
    payload: encodeUtf8(JSON.stringify(payload)),
  });
  if (!encoded.ok) throw new Error(encoded.error);
  return encoded.wire;
}

function openClient(clock, { helloTimeout = 3000, rpcTimeout = 1000 } = {}) {
  const parser = new FrameParser();
  const held = [];
  let hold = false;
  let client = null;
  const timers = [];
  const setTimeout = clock.setTimeout.bind(clock);
  clock.setTimeout = (fn, ms) => {
    const id = setTimeout(fn, ms);
    timers.push({ id, fn });
    return id;
  };
  client = new ProtocolClient({
    write(bytes) {
      const parsed = parser.push(bytes, clock.now());
      for (const frame of parsed.frames) {
        if (hold) held.push(frame);
        else client.ingest(answer(frame));
      }
    },
    onData() {},
  }, { clock, helloTimeout, rpcTimeout });
  return {
    client,
    held,
    timers,
    hold(next) { hold = next; },
    deliver() {
      const frames = held.splice(0);
      for (const frame of frames) client.ingest(answer(frame));
    },
  };
}

test('rehandshake at 14.9s is not cancelled by the old liveness timer', async () => {
  const clock = createClock(0);
  const session = openClient(clock);
  await session.client.hello({ client: clientInfo, nonce });
  const oldTimer = session.timers.length;
  clock.advance(14900);
  session.hold(true);
  const again = session.client.hello({ client: clientInfo, nonce: nonce2 });
  clock.advance(100);
  session.deliver();
  const hello = await again;
  assert.equal(hello.json.ok, true);
  assert.equal(hello.json.result.nonce, nonce2);
  assert.equal(session.client.sessionLive, true);
  assert.equal(session.client.pending, null);
  assert.ok(session.timers.length >= oldTimer);
  session.client.disconnect();
  assert.equal(session.client.livenessTimer, null);
  assert.equal(session.client.heartbeat, null);
  assert.equal(session.client.pending, null);
});

test('a delayed old liveness callback cannot reject the new handshake', async () => {
  const clock = createClock(0);
  const session = openClient(clock);
  await session.client.hello({ client: clientInfo, nonce });
  const stale = session.timers.map((item) => item.fn);
  clock.advance(14900);
  session.hold(true);
  const again = session.client.hello({ client: clientInfo, nonce: nonce2 });
  for (const fn of stale) fn();
  session.deliver();
  const hello = await again;
  assert.equal(hello.json.result.nonce, nonce2);
  assert.equal(session.client.pending, null);
});

test('hello during an in-flight RPC does not damage the live session', async () => {
  const clock = createClock(0);
  const session = openClient(clock);
  await session.client.hello({ client: clientInfo, nonce });
  const sessionId = session.client.sessionId;
  session.hold(true);
  const ping = session.client.ping();
  const nextId = session.client.nextId;
  await assert.rejects(session.client.hello({ client: clientInfo, nonce: nonce2 }), /rpc_inflight/);
  assert.equal(session.client.sessionLive, true);
  assert.equal(session.client.sessionId, sessionId);
  assert.equal(session.client.nextId, nextId);
  assert.notEqual(session.client.nextId, 1);
  session.hold(false);
  session.deliver();
  assert.equal((await ping).json.ok, true);
  session.client.disconnect();
});

test('failed hello can be retried and an old heartbeat cannot complete it', async () => {
  const clock = createClock(0);
  const session = openClient(clock, { helloTimeout: 500 });
  await session.client.hello({ client: clientInfo, nonce });
  session.client.startHeartbeat();
  clock.advance(4900);
  session.hold(true);
  const failed = session.client.hello({ client: clientInfo, nonce: nonce2 });
  const beats = session.timers.map((item) => item.fn);
  clock.advance(1000);
  for (const fn of beats) fn();
  await assert.rejects(failed, /timeout/);
  assert.equal(session.client.sessionLive, false);
  assert.equal(session.client.pending, null);
  session.hold(false);
  session.held.splice(0);
  const recovered = await session.client.hello({ client: clientInfo, nonce: nonce2 });
  assert.equal(recovered.json.ok, true);
  session.client.disconnect();
  clock.advance(60000);
  assert.equal(session.client.pending, null);
  assert.equal(session.client.livenessTimer, null);
});

test('natural session expiry does not emit config or other events', async () => {
  const clock = createClock(0);
  const device = new SimulatedDevice({ clock, profile: 'r60' });
  const client = new ProtocolClient({
    write(bytes) { device.ingest(bytes); },
    onData() {},
  }, { clock });
  device.onWire((bytes) => client.ingest(bytes));
  await client.hello({ client: clientInfo, nonce });
  await client.subscribe([
    { id: 'config', max_rate_hz: 0 },
    { id: 'status', max_rate_hz: 0 },
    { id: 'jobs', max_rate_hz: 0 },
    { id: 'logs', max_rate_hz: 1 },
  ], 1000);
  device.enqueue(CODE.LOG, { sample_ms: 1, level: 'info', source: 'sim', message: 'first', dropped_before: 0 });
  device.enqueue(CODE.LOG, { sample_ms: 2, level: 'info', source: 'sim', message: 'held', dropped_before: 0 });
  assert.equal(device.heldEvents.length, 1);
  clock.advance(16000);
  assert.equal(device.session, null);
  assert.equal(device.heldEvents.length, 0);
  assert.equal(device.subscriptions.size, 0);
  const afterExpiry = device.sentEventBytes;
  assert.doesNotThrow(() => device.bumpExternal('install.x_cm', 2));
  device.enqueue(CODE.STATUS_CHANGED, { uptime_ms: 1 });
  device.enqueue(CODE.JOB_CHANGED, { id: 'job' });
  device.enqueue(CODE.LOG, { sample_ms: 2, level: 'info', source: 'sim', message: 'late', dropped_before: 0 });
  assert.equal(device.config['install.x_cm'], 2);
  assert.equal(device.sentEventBytes, afterExpiry);
  assert.equal(device.session, null);
});

test('a rate-held event is sent when the window opens and dropped after expiry', async () => {
  const clock = createClock(0);
  const device = new SimulatedDevice({ clock, profile: 'r60' });
  const client = new ProtocolClient({
    write(bytes) { device.ingest(bytes); },
    onData() {},
  }, { clock });
  device.onWire((bytes) => client.ingest(bytes));
  await client.hello({ client: clientInfo, nonce });
  await client.subscribe([{ id: 'telemetry', max_rate_hz: 1 }], 8000);
  device.emitTelemetry({ targets: [], sample_ms: 0, origin: 'simulation' });
  device.emitTelemetry({ targets: [], sample_ms: 1, origin: 'simulation' });
  const sent = device.sentTelemetry;
  assert.equal(sent, 1);
  assert.equal(device.heldEvents.length, 1);
  clock.advance(1000);
  assert.equal(device.sentTelemetry, sent + 1);
  assert.equal(device.session !== null, true);
  device.budgetBps = 1;
  device.enqueue(CODE.LOG, { sample_ms: 1, level: 'info', source: 'sim', message: 'wait', dropped_before: 0 });
  clock.advance(15000);
  assert.equal(device.heldEvents.length, 0);
  assert.equal(device.session, null);
});


