import test from 'node:test';
import assert from 'node:assert/strict';
import { ProtocolClient } from '../src/protocol/client.js';
import { encodeFrame } from '../src/protocol/codec.js';
import { CODE, KIND } from '../src/protocol/limits.js';
import { ConsoleSession } from '../src/console/session.js';
import { checksFromSession } from '../src/console/observe.js';

function session() {
  const clock = { now: () => 100000 };
  const box = new ConsoleSession({ clock });
  const client = new ProtocolClient({ onData() {} }, { clock, onEvent: (frame) => box.takeEvent(frame) });
  box.client = client;
  box.bootId = client.bootId = 'presence-refresh';
  client.sessionId = 7;
  client.sessionLive = true;
  client.sessionDeadline = 200000;
  box.layers.protocol = 'online';
  box.layers.port = 'open';
  return box;
}

function feed(box, body, seq) {
  const encoded = encodeFrame({
    kind: KIND.event,
    sessionId: 7,
    requestId: 0,
    wireSeq: seq,
    code: CODE.TELEMETRY,
    payloadText: JSON.stringify(body),
  });
  assert.equal(encoded.ok, true);
  box.client.ingest(encoded.wire);
}

function body(seq, sent, presenceMs, targetMs, present) {
  return {
    source_seq: seq,
    sent_ms: sent,
    origin: 'hardware',
    presence: { value: present, quality: 'valid', sample_ms: presenceMs },
    targets_quality: 'valid',
    targets_ms: targetMs,
    targets: [{
      id: 't0', local_cm: [12, 34], room_cm: [12, 34],
      position_quality: 'valid', position_ms: targetMs, boundary: 'inside', speed_cm_s: null,
    }],
  };
}

test('a repeated legal presence value stays fresh only when its own sample time moves', () => {
  const box = session();
  feed(box, body(1, 100000, 1000, 99900, true), 1);
  box.syncDataLayers();
  const stale = box.observationView();
  assert.equal(stale.presence, 'stale');
  assert.equal(stale.targets, 'points');
  assert.equal(box.layers.radar, 'partial');
  assert.notEqual(checksFromSession(box).find((item) => item.id === 'presence').state, 'absent');

  feed(box, body(2, 100000, 99800, 99900, true), 2);
  box.syncDataLayers();
  const fresh = box.observationView();
  assert.equal(fresh.presence, 'present');
  assert.equal(fresh.targets, 'points');
  assert.equal(checksFromSession(box).find((item) => item.id === 'radar').state, 'pass');

  feed(box, body(3, 120000, 99800, 119900, true), 3);
  box.syncDataLayers();
  const aged = box.observationView();
  assert.equal(aged.presence, 'stale');
  assert.equal(aged.targets, 'points');
  assert.equal(box.layers.radar, 'partial');
  assert.notEqual(aged.presence, 'absent');
});

test('a legal nobody sample is explicit and an unknown sample is not nobody', () => {
  const box = session();
  feed(box, {
    source_seq: 4, sent_ms: 100000, origin: 'hardware',
    presence: { value: false, quality: 'valid', sample_ms: 99900 },
    targets_quality: 'valid', targets_ms: 99900, targets: [],
  }, 4);
  box.syncDataLayers();
  assert.equal(box.observationView().presence, 'absent');

  feed(box, {
    source_seq: 5, sent_ms: 100000, origin: 'hardware',
    presence: { value: null, quality: 'unknown', sample_ms: null },
    targets_quality: 'valid', targets_ms: 99900,
    targets: [{ id: 't0', local_cm: [1, 2], room_cm: [1, 2], position_quality: 'valid', position_ms: 99900, boundary: 'inside', speed_cm_s: null }],
  }, 5);
  box.syncDataLayers();
  const unknown = box.observationView();
  assert.equal(unknown.presence, 'unknown');
  assert.notEqual(unknown.presence, 'absent');
  assert.equal(unknown.targets, 'points');
});
