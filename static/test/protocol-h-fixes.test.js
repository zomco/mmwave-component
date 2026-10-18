import test from 'node:test';
import assert from 'node:assert/strict';
import { createClock } from '../src/protocol/clock.js';
import { encodeFrame, FrameParser } from '../src/protocol/codec.js';
import { ProtocolClient } from '../src/protocol/client.js';
import { CODE, KIND } from '../src/protocol/limits.js';
import { encodeUtf8 } from '../src/protocol/utf8.js';
import { link, observation } from '../src/protocol/simulator.js';

const nonce = '0123456789abcdef0123456789abcdef';
const nonce2 = 'fedcba9876543210fedcba9876543210';
const clientInfo = { name: 'mmwave-web-console', version: '0.1.0' };

function answer(frame) {
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
          cap_revision: 'h',
        },
      }
    : { ok: true, result: { uptime_ms: 1 } };
  const encoded = encodeFrame({
    kind: KIND.response,
    sessionId: frame.code === CODE.HELLO ? 7 : frame.sessionId,
    requestId: frame.requestId,
    code: frame.code,
    wireSeq: 1,
    payload: encodeUtf8(JSON.stringify(payload)),
  });
  if (!encoded.ok) throw new Error(encoded.error);
  return encoded.wire;
}

function openHeld(clock, options = {}) {
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
  }, { clock, rpcTimeout: options.rpcTimeout ?? 1000, helloTimeout: options.helloTimeout ?? 3000 });
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

test('a suspended clock cannot accept a ping after the absolute deadline', async () => {
  const clock = createClock(0);
  const session = openHeld(clock);
  await session.client.hello({ client: clientInfo, nonce });
  clock.jump(14000);
  session.hold(true);
  const ping = session.client.ping();
  clock.jump(16000);
  session.deliver();
  await assert.rejects(ping, /session_expired|timeout/);
  assert.equal(session.client.sessionLive, false);
  assert.equal(session.client.lastResponseAt, 0);
  assert.equal(session.client.pending, null);
  assert.equal(session.client.livenessTimer, null);
  session.client.disconnect();
});

test('request deadline and session deadline are checked without timer order', async () => {
  const clock = createClock(0);
  const session = openHeld(clock);
  await session.client.hello({ client: clientInfo, nonce });
  clock.jump(1000);
  session.hold(true);
  const ping = session.client.ping();
  clock.jump(1000);
  session.deliver();
  await assert.rejects(ping, /timeout/);
  assert.equal(session.client.sessionLive, true);
  assert.equal(session.client.lastResponseAt, 0);
  clock.jump(12999);
  session.client.poll();
  assert.equal(session.client.sessionLive, true);
  clock.jump(1);
  session.client.poll();
  assert.equal(session.client.sessionLive, false);
  session.client.disconnect();
});

test('hello response after the handshake deadline does not complete', async () => {
  const clock = createClock(0);
  const session = openHeld(clock, { helloTimeout: 3000 });
  session.hold(true);
  const hello = session.client.hello({ client: clientInfo, nonce });
  clock.jump(2999);
  session.deliver();
  assert.equal((await hello).json.ok, true);
  session.client.disconnect();
  const next = openHeld(clock, { helloTimeout: 3000 });
  next.hold(true);
  const late = next.client.hello({ client: clientInfo, nonce: nonce2 });
  clock.jump(3000);
  next.deliver();
  await assert.rejects(late, /timeout/);
  assert.equal(next.client.sessionLive, false);
  assert.equal(next.client.pending, null);
});

test('timeout callback and late response cannot both complete a request', async () => {
  const clock = createClock(0);
  const session = openHeld(clock);
  await session.client.hello({ client: clientInfo, nonce });
  session.hold(true);
  const ping = session.client.ping();
  clock.advance(1000);
  await assert.rejects(ping, /timeout/);
  session.deliver();
  assert.equal(session.client.pending, null);
  assert.equal(session.client.sessionLive, true);
  session.client.disconnect();
});

test('old liveness callback does not clear the new timer handle', async () => {
  const clock = createClock(0);
  const session = openHeld(clock);
  await session.client.hello({ client: clientInfo, nonce });
  const stale = session.timers.map((item) => item.fn);
  clock.jump(1000);
  const again = session.client.hello({ client: clientInfo, nonce: nonce2 });
  const handle = session.client.livenessTimer;
  for (const fn of stale) fn();
  assert.equal(session.client.livenessTimer, handle);
  assert.equal((await again).json.result.nonce, nonce2);
  session.held.splice(0);
  session.deliver();
  assert.equal(session.client.sessionLive, true);
  session.client.disconnect();
  assert.equal(session.client.pending, null);
  assert.equal(session.client.heartbeat, null);
  assert.equal(session.client.livenessTimer, null);
});

test('telemetry does not renew a suspended session and heartbeats still keep it online', async () => {
  const clock = createClock(0);
  const linked = link(clock, { profile: 'r60' });
  await linked.client.hello({ client: clientInfo, nonce });
  await linked.client.subscribe([{ id: 'telemetry', max_rate_hz: 5 }], 8000);
  clock.jump(20000);
  linked.device.emitTelemetry(observation('zero'));
  linked.client.poll();
  assert.equal(linked.client.sessionLive, false);
  assert.equal(linked.client.lastResponseAt, 0);
  const liveClock = createClock(0);
  const live = link(liveClock, { profile: 'r60' });
  await live.client.hello({ client: clientInfo, nonce });
  live.client.startHeartbeat();
  liveClock.advance(20000);
  assert.equal(live.client.sessionLive, true);
  live.client.disconnect();
  assert.equal(live.client.pending, null);
  assert.equal(live.client.livenessTimer, null);
});
