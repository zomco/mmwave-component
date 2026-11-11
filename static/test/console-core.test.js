import test from 'node:test';
import assert from 'node:assert/strict';
import { ProtocolClient } from '../src/protocol/client.js';
import { createClock } from '../src/protocol/clock.js';
import { encodeFrame } from '../src/protocol/codec.js';
import { CODE, KIND } from '../src/protocol/limits.js';
import { SimulatedDevice, observation } from '../src/protocol/simulator.js';
import { encodeUtf8 } from '../src/protocol/utf8.js';
import { ConsoleSession } from '../src/console/session.js';
import { SerialCoordinator, OWNERS } from '../src/console/serial-coordinator.js';
import { WebSerialTransport } from '../src/console/web-serial-transport.js';
import { checksFromSession, interpretObservation, pushWindow, targetRows } from '../src/console/observe.js';
import { redact } from '../src/console/pending-save.js';

function named(name) {
  const error = new Error(name);
  error.name = name;
  return error;
}

async function micro() {
  for (let i = 0; i < 40; i += 1) await Promise.resolve();
}

function harness(profile) {
  const clock = createClock(5000);
  let device = new SimulatedDevice({ profile: profile || 'r60', clock });
  const session = new ConsoleSession({ clock, helloTimeout: 8000, rpcTimeout: 1000 });
  const advance = clock.advance.bind(clock);
  clock.advance = (ms) => {
    advance(ms);
    device.poll(clock.now());
  };
  const transport = {
    write(bytes) { device.ingest(bytes); },
    onData() {},
    close() { device.expire(); },
    start() {},
  };
  session.clientFactory = (next, extras) => {
    const client = new ProtocolClient(next, extras);
    device.onWire((bytes) => client.ingest(bytes));
    return client;
  };
  return {
    clock,
    session,
    transport,
    get device() { return device; },
    swap(next) { device = next; },
  };
}

async function online(profile) {
  const box = harness(profile);
  const hello = await box.session.attach(box.transport, { mode: 'simulation' });
  assert.equal(hello.ok, true);
  assert.equal(hello.simulation, true);
  assert.equal(box.session.snapshot().simulation, true);
  return box;
}

function dropNextCommit(device) {
  const original = device.dispatch.bind(device);
  let once = true;
  device.dispatch = (frame, now) => {
    const produced = original(frame, now);
    if (once && frame.code === CODE.CONFIG_COMMIT) {
      once = false;
      device.faults.dropResponses += 1;
    }
    return produced;
  };
}

function swallowNextCommit(session, device) {
  const ingest = device.ingest.bind(device);
  let skip = false;
  device.ingest = (bytes, now) => {
    if (skip) { skip = false; return; }
    return ingest(bytes, now);
  };
  const validate = session.validateDraft.bind(session);
  let armed = true;
  session.validateDraft = async (options) => {
    const result = await validate(options);
    if (armed && result.ok) { armed = false; skip = true; }
    return result;
  };
}

test('C1 connect handshake reads identity and does not guess the radar', async () => {
  const box = await online();
  const snap = box.session.snapshot();
  assert.equal(snap.layers.protocol, 'online');
  assert.equal(snap.identity.configured_model, 'r60abd1');
  assert.equal(snap.identity.firmware_version, 'simulation');
  assert.match(snap.identity.configured_model_note, /not a detected radar/);
  assert.ok(snap.capabilities.length > 2);
  assert.equal(snap.configRevision, '1');
  assert.equal(snap.configItems.length, 8);
  assert.equal(snap.layers.radar, 'waiting_first_frame');
  assert.equal(snap.layers.data, 'none');
});

test('C1 no protocol response is a bounded failure, not a reset loop', async () => {
  const box = harness();
  box.session.helloTimeout = 200;
  let writes = 0;
  const write = box.transport.write;
  box.transport.write = (bytes) => { writes += 1; return write(bytes); };
  box.device.faults.disconnect = true;
  const pending = box.session.attach(box.transport, { mode: 'simulation' });
  await micro();
  box.clock.advance(200);
  await micro();
  box.clock.advance(200);
  const result = await pending;
  assert.equal(result.ok, false);
  assert.equal(result.reason, 'timeout');
  assert.equal(box.session.layers.protocol, 'no_response');
  assert.ok(writes <= 2);
});

test('C3 unknown, empty and zero stay distinct', async () => {
  const box = await online();
  const before = checksFromSession(box.session);
  assert.equal(before.find((item) => item.id === 'presence').state, 'not_run');
  assert.notEqual(before.every((item) => item.state === 'pass'), true);
  box.device.emitTelemetry(observation('unknown'));
  let view = box.session.presenceView();
  assert.equal(view.state, 'unknown');
  assert.equal(interpretObservation(box.session.telemetry).targets, 'unknown');
  box.device.emitTelemetry(observation('empty'));
  view = box.session.presenceView();
  assert.equal(view.state, 'absent');
  assert.equal(interpretObservation(box.session.telemetry).targets, 'empty');
  box.device.emitTelemetry(observation('zero'));
  view = box.session.presenceView();
  assert.equal(view.state, 'present');
  const rows = targetRows(box.session.telemetry, null);
  assert.equal(rows.length, 1);
  assert.deepEqual(rows[0].room, [0, 0]);
  const checks = checksFromSession(box.session);
  assert.equal(checks.find((item) => item.id === 'usb').state, 'pass');
  assert.equal(checks.find((item) => item.id === 'presence').state, 'present');
  assert.equal(box.session.snapshot().simulation, true);
});

test('C4 1D range and outside targets stay visible', async () => {
  const box = await online('range1d');
  assert.equal(box.session.identity.dimension, '1D');
  box.device.emitTelemetry(observation('1d'));
  const rows = targetRows(box.session.telemetry, null);
  assert.equal(rows[0].oneD, true);
  assert.equal(rows[0].rangeCm, 150);
  const outside = targetRows({ targets: [{ id: '9', room_cm: [10, 10], position_quality: 'valid', position_ms: 1, boundary: 'outside' }] }, null);
  assert.equal(outside.length, 1);
  assert.equal(outside[0].faded, true);
  const window = pushWindow([], { at: 0 }, 0);
  assert.equal(pushWindow(window, { at: 11 * 60 * 1000 }, 11 * 60 * 1000).length, 1);
});

test('C3 stale observation is not a fresh pass', async () => {
  const box = await online();
  box.device.emitTelemetry(observation('zero'));
  box.session.client.stopHeartbeat();
  box.clock.advance(9000);
  assert.equal(box.session.presenceView().state, 'stale');
});

test('C5 save validates, commits once and reads back', async () => {
  const box = await online();
  assert.equal(box.session.editDraft('install.z_cm', 1).ok, true);
  const invalid = await box.session.validateDraft();
  assert.equal(invalid.ok, false);
  assert.equal(box.device.writeCount, 0);
  assert.ok(box.session.fieldErrors['install.z_cm'] || box.session.fieldErrors._form);
  box.session.editDraft('install.z_cm', 220);
  box.session.editDraft('install.x_cm', 25);
  const saved = await box.session.commitDraft();
  assert.equal(saved.ok, true);
  assert.equal(box.session.save.phase, 'persisted');
  assert.equal(box.session.save.message, 'persisted_and_read_back');
  assert.equal(box.device.config['install.x_cm'], 25);
  assert.equal(box.device.writeCount, 1);
  const again = box.session.configItems.find((item) => item.key === 'install.x_cm');
  assert.equal(again.value, 25);
});

test('C5 revision conflict keeps the draft and does not write', async () => {
  const box = await online();
  box.session.editDraft('install.x_cm', 25);
  box.device.bumpExternal('install.y_cm', 15);
  assert.equal(box.session.save.phase, 'conflict');
  const saved = await box.session.commitDraft();
  assert.equal(saved.ok, false);
  assert.equal(box.session.save.phase, 'conflict');
  assert.equal(box.session.draft['install.x_cm'], 25);
  assert.equal(box.device.writeCount, 0);
  assert.equal(box.device.config['install.y_cm'], 15);
  const reloaded = await box.session.reloadFromDevice();
  assert.equal(reloaded.ok, true);
  assert.equal(box.session.draft['install.y_cm'], 15);
  box.session.editDraft('install.x_cm', 30);
  const savedAfter = await box.session.commitDraft();
  assert.equal(savedAfter.ok, true);
  assert.equal(box.device.config['install.x_cm'], 30);
  assert.equal(box.device.config['install.y_cm'], 15);
});

test('C6 dropped commit stays unknown until the original status is found', async () => {
  const box = await online();
  dropNextCommit(box.device);
  box.session.editDraft('install.x_cm', 40);
  const pending = box.session.commitDraft();
  await micro();
  box.clock.advance(2000);
  const lost = await pending;
  assert.equal(lost.ok, false);
  assert.equal(box.session.save.phase, 'unknown');
  assert.equal(box.device.writeCount, 1);
  assert.equal(box.device.config['install.x_cm'], 40);
  const blocked = await box.session.commitDraft();
  assert.equal(blocked.reason, 'pending_blocks_new_save');
  assert.equal(box.device.writeCount, 1);
  const recovered = await box.session.recoverPending();
  assert.equal(recovered.ok, true);
  assert.equal(box.session.save.phase, 'persisted');
  assert.equal(box.session.save.message, 'confirmed_by_status');
  box.session.editDraft('install.x_cm', 41);
  const next = await box.session.commitDraft();
  assert.equal(next.ok, true);
  assert.equal(box.device.writeCount, 2);
  assert.equal(box.device.config['install.x_cm'], 41);
});

test('C6 found false does not clear the pending save', async () => {
  const box = await online();
  swallowNextCommit(box.session, box.device);
  box.session.editDraft('install.x_cm', 40);
  const pending = box.session.commitDraft();
  await micro();
  box.clock.advance(2000);
  const lost = await pending;
  assert.equal(lost.ok, false);
  assert.equal(box.session.save.phase, 'unknown');
  assert.equal(box.device.writeCount, 0);
  const recovered = await box.session.recoverPending();
  assert.equal(recovered.ok, false);
  assert.equal(recovered.reason, 'found_false');
  assert.equal(box.session.save.phase, 'unknown');
  assert.equal(box.session.save.found, false);
  const blocked = await box.session.commitDraft();
  assert.equal(blocked.reason, 'pending_blocks_new_save');
  assert.equal(box.device.config['install.x_cm'], 0);
  const abandoned = box.session.abandonPending();
  assert.equal(abandoned.ok, true);
  assert.match(box.session.save.message, /may_have_executed/);
  box.session.editDraft('install.x_cm', 12);
  const saved = await box.session.commitDraft();
  assert.equal(saved.ok, true);
  assert.equal(box.device.config['install.x_cm'], 12);
});

test('C6 a bad status frame does not block the later matching frame', async () => {
  const box = await online();
  dropNextCommit(box.device);
  box.session.editDraft('install.x_cm', 40);
  const pending = box.session.commitDraft();
  await micro();
  box.clock.advance(2000);
  await pending;
  assert.equal(box.session.save.phase, 'unknown');
  let seen = null;
  const onFrame = box.device.onFrame.bind(box.device);
  box.device.onFrame = (frame, now) => { seen = frame; return onFrame(frame, now); };
  box.device.faults.delayMs = 300;
  const recovering = box.session.recoverPending();
  await micro();
  assert.ok(seen);
  const good = { found: true, revision: '999', current_revision: '999' };
  const wrongSession = encodeFrame({ kind: KIND.response, sessionId: box.session.client.sessionId + 9, requestId: seen.requestId, code: CODE.COMMIT_STATUS, wireSeq: 3, payload: encodeUtf8(JSON.stringify({ ok: true, result: good })) });
  const wrongCode = encodeFrame({ kind: KIND.response, sessionId: box.session.client.sessionId, requestId: seen.requestId, code: CODE.PING, wireSeq: 4, payload: encodeUtf8(JSON.stringify({ ok: true, result: { uptime_ms: 1 } })) });
  const wrongBody = encodeFrame({ kind: KIND.response, sessionId: box.session.client.sessionId, requestId: seen.requestId, code: CODE.COMMIT_STATUS, wireSeq: 5, payload: encodeUtf8(JSON.stringify({ ok: true, result: { found: true } })) });
  assert.equal(wrongSession.ok, true);
  box.device.inject(wrongSession.wire);
  box.device.inject(wrongCode.wire);
  box.device.inject(wrongBody.wire);
  assert.equal(box.session.save.phase, 'unknown');
  box.device.faults.delayMs = 0;
  box.clock.advance(300);
  const recovered = await recovering;
  assert.equal(recovered.ok, true);
  assert.notEqual(box.session.configRevision, '999');
  assert.equal(box.session.client.ignored > 0 || box.session.client.rejected > 0, true);
});

test('C6 another device cannot clear the pending save', async () => {
  const box = await online();
  swallowNextCommit(box.session, box.device);
  box.session.editDraft('install.x_cm', 40);
  const pending = box.session.commitDraft();
  await micro();
  box.clock.advance(2000);
  await pending;
  const opId = box.session.save.opId;
  await box.session.stop();
  const other = new SimulatedDevice({ profile: 'r60', clock: box.clock });
  const hello = other.helloResult.bind(other);
  other.helloResult = (nonce) => {
    const result = hello(nonce);
    result.identity = Object.assign({}, result.identity, { device_id: 'other-device' });
    return result;
  };
  box.swap(other);
  const attached = await box.session.attach(box.transport, { mode: 'simulation' });
  assert.equal(attached.ok, true);
  const recovered = await box.session.recoverPending();
  assert.equal(recovered.reason, 'wrong_device');
  assert.equal(box.session.save.phase, 'unknown');
  assert.equal(box.session.save.opId, opId);
});

test('C2 session expiry asks for a new handshake', async () => {
  const box = await online();
  box.session.client.stopHeartbeat();
  const left = box.session.client.sessionDeadline - box.clock.now() + 1;
  box.clock.advance(left);
  const resumed = await box.session.refreshAfterResume();
  assert.equal(resumed.rehello, true);
  assert.equal(box.session.layers.protocol, 'session_expired');
  box.device.faults.disconnect = false;
  const again = await box.session.attach(box.transport, { mode: 'simulation' });
  assert.equal(again.ok, true);
  assert.equal(box.session.configRevision != null, true);
});

test('C7 secrets stay out of the diagnostic export', async () => {
  const box = await online();
  const secret = 'super-secret-value';
  box.device.enqueue(CODE.LOG, { sample_ms: 10, level: 'info', source: 'wifi', message: 'password=' + secret + ' token=' + secret, dropped_before: 0 });
  const dumped = JSON.stringify(box.session.diagnosticExport());
  assert.equal(dumped.includes(secret), false);
  assert.match(dumped, /redacted/);
  const password = 'wifi-secret-value';
  await box.session.provisionWifi({ ssid: 'Lab', password });
  assert.equal(JSON.stringify(box.session.snapshot()).includes(password), false);
  assert.equal(JSON.stringify(redact({ password, note: 'token=' + password })).includes(password), false);
});


test('wifi status, accepted provisioning and unknown timeout stay distinct', async () => {
  const box = await online();
  const status = await box.session.refreshWifi();
  assert.equal(status.state, 'disconnected');
  assert.equal(status.current, true);
  const original = box.device.dispatch.bind(box.device);
  box.device.dispatch = (frame, now) => {
    if (frame.code === CODE.WIFI_STATUS) throw new Error('status timeout');
    return original(frame, now);
  };
  const failed = await box.session.refreshWifi();
  assert.equal(failed.state, 'unknown');
  assert.notEqual(failed.state, 'unsupported');
  box.device.dispatch = original;
  const password = 'lab-pass-1';
  const accepted = await box.session.provisionWifi({ ssid: 'Lab', password });
  assert.equal(accepted.accepted, true);
  assert.equal(accepted.connected, false);
  assert.equal(JSON.stringify(box.session.snapshot()).includes(password), false);
  const second = await box.session.provisionWifi({ ssid: 'Lab', password });
  assert.equal(second.reason, 'provision_busy');
  const job = [...box.device.activeJobs.values()][0];
  job.state = 'succeeded';
  box.device.wifi = { state: 'connected', ssid: 'Lab', ip: '192.168.1.50', rssi_dbm: -40, last_error: null };
  await new Promise((resolve) => setTimeout(resolve, 1200));
  assert.equal(box.session.wifiTask.phase, 'succeeded');
  assert.equal(box.session.wifi.state, 'connected');
  assert.equal(box.session.wifi.ip, '192.168.1.50');
  await box.session.stop();
  assert.equal(box.session.wifi.historical, true);
  assert.equal(box.session.wifi.current, false);
});

test('a lost provisioning response stays unknown and is not sent again', async () => {
  const box = await online();
  const original = box.device.dispatch.bind(box.device);
  let writes = 0;
  box.device.dispatch = (frame, now) => {
    if (frame.code === CODE.WIFI_PROVISION) {
      writes += 1;
      throw new Error('acceptance timeout');
    }
    return original(frame, now);
  };
  const lost = await box.session.provisionWifi({ ssid: 'Lab', password: 'lab-pass-1' });
  assert.equal(lost.unknown, true);
  assert.equal(box.session.wifiTask.phase, 'unknown');
  const again = await box.session.provisionWifi({ ssid: 'Lab', password: 'lab-pass-1' });
  assert.equal(again.reason, 'provision_busy');
  assert.equal(writes, 1);
  box.device.dispatch = original;
  const seen = await box.session.refreshWifi();
  assert.equal(seen.state, 'disconnected');
  assert.notEqual(box.session.wifiTask.phase, 'succeeded');
});

test('a dropped provision reply is recovered by its original op id', async () => {
  const box = await online();
  const original = box.device.dispatch.bind(box.device);
  let provisions = 0;
  let jobs = 0;
  box.device.dispatch = (frame, now) => {
    if (frame.code === CODE.WIFI_PROVISION) provisions += 1;
    if (frame.code === CODE.JOB_GET) jobs += 1;
    const reply = original(frame, now);
    if (frame.code === CODE.WIFI_PROVISION) box.device.faults.dropResponses += 1;
    return reply;
  };
  const pending = box.session.provisionWifi({ ssid: 'Lab', password: 'lab-pass-1' });
  await new Promise((resolve) => setTimeout(resolve, 20));
  box.clock.advance(2100);
  const lost = await pending;
  assert.equal(lost.unknown, true);
  assert.equal(box.session.wifiTask.jobId, null);
  const found = await box.session.queryWifiTask();
  assert.equal(found.found, true);
  assert.equal(provisions, 1);
  assert.equal(jobs >= 1, true);
  assert.equal(Boolean(box.session.wifiTask.jobId), true);
  assert.notEqual(box.session.wifiTask.phase, 'succeeded');
});

test('a busy status read does not turn provisioning into an unknown lock', async () => {
  const box = await online();
  box.device.faults.delayMs = 5000;
  const reading = box.session.refreshWifi();
  await new Promise((resolve) => setTimeout(resolve, 20));
  const raced = await box.session.provisionWifi({ ssid: 'Lab', password: 'lab-pass-1' });
  assert.equal(raced.reason, 'rpc_inflight');
  assert.equal(box.session.wifiTask, null);
  box.device.faults.delayMs = 0;
  box.clock.advance(5000);
  await reading;
  const accepted = await box.session.provisionWifi({ ssid: 'Lab', password: 'lab-pass-1' });
  assert.equal(accepted.accepted, true);
});

test('a rate-limited provision is not sent after the session changes', async () => {
  const box = await online();
  const original = box.device.dispatch.bind(box.device);
  let provisions = 0;
  box.device.dispatch = (frame, now) => {
    if (frame.code === CODE.WIFI_PROVISION) provisions += 1;
    return original(frame, now);
  };
  const raw = box.clock;
  box.session.clock = { now: () => raw.now(), setTimeout: (fn, ms) => raw.setTimeout(fn, ms), clearTimeout: (id) => raw.clearTimeout(id) };
  const now = raw.now();
  box.session.rpcAt = [now, now, now, now, now, now, now, now];
  const pending = box.session.provisionWifi({ ssid: 'Lab', password: 'lab-pass-1' });
  await new Promise((resolve) => setTimeout(resolve, 10));
  assert.equal(provisions, 0);
  box.session.rpcAt = [];
  box.session.clock = raw;
  assert.equal((await box.session.rehandshake()).ok, true);
  box.clock.advance(1100);
  const cancelled = await pending;
  assert.equal(cancelled.sent, false);
  assert.equal(cancelled.reason, 'session_changed');
  assert.equal(provisions, 0);
  assert.equal(box.session.wifiTask, null);
  const accepted = await box.session.provisionWifi({ ssid: 'Lab', password: 'lab-pass-1' });
  assert.equal(accepted.accepted, true);
  assert.equal(provisions, 1);
});
function port() {
  const listeners = new Map();
  let readable = { locked: false };
  let writable = { locked: false };
  return {
    get readable() { return readable; },
    get writable() { return writable; },
    opened: false,
    async open() { this.opened = true; readable = { locked: false }; writable = { locked: false }; },
    async close() { readable = null; writable = null; this.opened = false; },
    addEventListener(type, fn) { listeners.set(type, fn); },
    removeEventListener(type) { listeners.delete(type); },
    emit(type) { const fn = listeners.get(type); if (fn) fn(); },
  };
}

function locks() {
  let held = false;
  return {
    request(name, options, callback) {
      if (held) {
        if (options && options.ifAvailable) return Promise.resolve(callback(null));
        return new Promise(() => {});
      }
      held = true;
      const result = callback({ name });
      return Promise.resolve(result).finally(() => { held = false; });
    },
  };
}

test('C1 cancel and unsupported are not device faults', async () => {
  let requested = 0;
  const serial = {
    requestPort() { requested += 1; throw named('NotFoundError'); },
    getPorts() { throw new Error('must not list ports'); },
  };
  const coord = new SerialCoordinator({ serial, locks: locks() });
  const cancelled = await coord.connect({ isSecureContext: true });
  assert.equal(cancelled.reason, 'chooser_cancelled');
  assert.equal(coord.owner, OWNERS.none);
  assert.equal(requested, 1);
  const insecure = await coord.connect({ isSecureContext: false });
  assert.equal(insecure.reason, 'insecure_context');
  assert.equal(requested, 1);
  const missing = new SerialCoordinator({ serial: null });
  assert.equal(missing.support(true).reason, 'no_web_serial');
});

test('C2 console and installer cannot own the port together', async () => {
  const chosen = port();
  const serial = {
    requestPort() { return Promise.resolve(chosen); },
    getPorts() { throw new Error('must not list ports'); },
  };
  const coord = new SerialCoordinator({ serial, locks: locks() });
  let unplugged = 0;
  coord.onUnplug = () => { unplugged += 1; };
  const opened = await coord.connect();
  assert.equal(opened.ok, true);
  assert.equal(coord.owner, OWNERS.console);
  const second = await coord.connect();
  assert.equal(second.reason, 'port_busy');
  const closed = coord.noteInstallerClosedEvent();
  assert.equal(closed.released, false);
  assert.equal(coord.owner, OWNERS.console);
  const released = await coord.disconnect({ stop() { return Promise.resolve(); } });
  assert.equal(released.ok, true);
  assert.equal(coord.owner, OWNERS.none);
  coord.noteInstallerHolding();
  assert.equal(coord.owner, OWNERS.installer);
  const hint = coord.noteInstallerClosedEvent();
  assert.equal(hint.released, false);
  assert.equal(coord.owner, OWNERS.installer);
  const blocked = await coord.connect();
  assert.equal(blocked.ok, false);
  assert.equal(blocked.reason, 'installer_holds_port');
  assert.equal(coord.owner, OWNERS.installer);
  const dismissed = coord.noteInstallerDismissed();
  assert.equal(dismissed.released, false);
  assert.equal(coord.owner, OWNERS.none);
  const after = await coord.connect();
  assert.equal(after.ok, true);
  assert.equal(coord.owner, OWNERS.console);
  chosen.emit('disconnect');
  assert.equal(coord.owner, OWNERS.none);
  assert.equal(unplugged, 1);
  const reopened = await coord.connect();
  assert.equal(reopened.ok, true);
});

test('C2 transport uses one reader and close releases it', async () => {
  const chunks = [new Uint8Array([1, 2, 3])];
  let readers = 0;
  let released = 0;
  const seen = [];
  const current = {
    readable: {
      getReader() {
        readers += 1;
        return {
          read() {
            if (!chunks.length) return Promise.resolve({ done: true });
            return Promise.resolve({ value: chunks.shift(), done: false });
          },
          cancel() { chunks.length = 0; return Promise.resolve(); },
          releaseLock() { released += 1; },
        };
      },
    },
    writable: {
      getWriter() {
        return { write(bytes) { seen.push(bytes); return Promise.resolve(); }, releaseLock() {} };
      },
    },
  };
  const transport = new WebSerialTransport(current);
  const got = [];
  transport.onData((bytes) => got.push(bytes[0]));
  transport.start();
  transport.start();
  await micro();
  await transport.write(new Uint8Array([9]));
  await transport.close();
  assert.equal(readers, 1);
  assert.equal(got[0], 1);
  assert.equal(seen[0][0], 9);
  assert.equal(released, 1);
});

function wrongCommit(device, frame) {
  return device.make(frame, {
    ok: true,
    result: {
      op_id: 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',
      revision: '9',
      persisted: true,
      restart_required: false,
    },
  });
}

test('R1 a second config action cannot replace the in-flight save', async () => {
  for (const action of ['discard', 'reload', 'validate', 'save']) {
    const box = await online();
    dropNextCommit(box.device);
    box.session.editDraft('install.x_cm', 31);
    const pending = box.session.commitDraft();
    await micro();
    assert.equal(box.session.save.phase, 'committing', action);
    const opId = box.session.save.opId;
    const frozen = box.session.save.changes['install.x_cm'];
    let blocked;
    if (action === 'discard') blocked = box.session.discardDraft();
    else if (action === 'reload') blocked = await box.session.reloadFromDevice();
    else if (action === 'validate') blocked = await box.session.validateDraft();
    else blocked = await box.session.commitDraft();
    assert.equal(blocked.ok, false, action);
    assert.equal(blocked.reason, 'operation_busy', action);
    assert.equal(box.session.save.phase, 'committing', action);
    assert.equal(box.session.save.opId, opId, action);
    assert.equal(box.session.save.changes['install.x_cm'], frozen, action);
    box.clock.advance(2000);
    const lost = await pending;
    assert.equal(lost.ok, false, action);
    assert.equal(box.session.save.phase, 'unknown', action);
    assert.equal(box.session.save.opId, opId, action);
    assert.equal(box.device.writeCount, 1, action);
    const again = await box.session.commitDraft();
    assert.equal(again.reason, 'pending_blocks_new_save', action);
    assert.equal(box.device.writeCount, 1, action);
  }
});

test('R1 a late acknowledgement after disconnect does not confirm the save', async () => {
  const box = await online();
  const original = box.device.dispatch.bind(box.device);
  let legal = null;
  box.device.dispatch = (frame, now) => {
    const produced = original(frame, now);
    if (frame.code === CODE.CONFIG_COMMIT) {
      legal = produced.wire;
      box.device.faults.dropResponses += 1;
    }
    return produced;
  };
  box.session.editDraft('install.x_cm', 31);
  const pending = box.session.commitDraft();
  await micro();
  assert.equal(box.session.save.phase, 'committing');
  const opId = box.session.save.opId;
  await box.session.stop();
  assert.equal(box.session.save.phase, 'unknown');
  assert.equal(box.session.save.opId, opId);
  box.clock.advance(2000);
  const lost = await pending;
  assert.equal(lost.ok, false);
  assert.equal(box.session.save.phase, 'unknown');
  box.device.faults.disconnect = false;
  const again = await box.session.attach(box.transport, { mode: 'simulation' });
  assert.equal(again.ok, true);
  assert.ok(legal);
  box.device.inject(legal);
  await micro();
  assert.equal(box.session.save.phase, 'unknown');
  assert.equal(box.session.save.opId, opId);
  assert.notEqual(box.session.save.message, 'persisted_and_read_back');
  assert.equal(box.device.writeCount, 1);
  const blocked = await box.session.commitDraft();
  assert.equal(blocked.reason, 'pending_blocks_new_save');
  assert.equal(box.device.writeCount, 1);
});

test('R1 overlapping validate cannot start a second write', async () => {
  const box = await online();
  box.device.faults.delayMs = 500;
  box.session.editDraft('install.x_cm', 32);
  const first = box.session.commitDraft();
  await micro();
  assert.equal(box.session.save.phase, 'validating');
  const second = await box.session.commitDraft();
  assert.equal(second.reason, 'operation_busy');
  assert.equal(box.device.writeCount, 0);
  box.device.faults.delayMs = 0;
  box.clock.advance(500);
  const saved = await first;
  assert.equal(saved.ok, true);
  assert.equal(saved.state.message, 'persisted_and_read_back');
  assert.equal(box.device.writeCount, 1);
});

test('R2 a wrong operation id cannot confirm, and a later legal frame can', async () => {
  const wrongOnly = await online();
  const originalWrong = wrongOnly.device.dispatch.bind(wrongOnly.device);
  wrongOnly.device.dispatch = (frame, now) => {
    if (frame.code === CODE.CONFIG_COMMIT) return wrongCommit(wrongOnly.device, frame);
    return originalWrong(frame, now);
  };
  wrongOnly.session.editDraft('install.x_cm', 33);
  const pendingWrong = wrongOnly.session.commitDraft();
  await micro();
  wrongOnly.clock.advance(2000);
  const lost = await pendingWrong;
  assert.equal(lost.ok, false);
  assert.equal(wrongOnly.session.save.phase, 'unknown');
  assert.equal(wrongOnly.device.writeCount, 0);
  assert.equal(wrongOnly.device.config['install.x_cm'], 0);
  const blocked = await wrongOnly.session.commitDraft();
  assert.equal(blocked.reason, 'pending_blocks_new_save');
  assert.equal(wrongOnly.device.writeCount, 0);

  const wrongThenLegal = await online();
  const original = wrongThenLegal.device.dispatch.bind(wrongThenLegal.device);
  wrongThenLegal.device.dispatch = (frame, now) => {
    if (frame.code !== CODE.CONFIG_COMMIT) return original(frame, now);
    const correct = original(frame, now);
    wrongThenLegal.device.inject(wrongCommit(wrongThenLegal.device, frame).wire);
    return correct;
  };
  wrongThenLegal.session.editDraft('install.x_cm', 34);
  const saved = await wrongThenLegal.session.commitDraft();
  assert.equal(saved.ok, true);
  assert.equal(wrongThenLegal.session.save.message, 'persisted_and_read_back');
  assert.equal(wrongThenLegal.device.writeCount, 1);
  assert.equal(wrongThenLegal.device.config['install.x_cm'], 34);

  const legalThenWrong = await online();
  const originalLegal = legalThenWrong.device.dispatch.bind(legalThenWrong.device);
  legalThenWrong.device.dispatch = (frame, now) => {
    if (frame.code !== CODE.CONFIG_COMMIT) return originalLegal(frame, now);
    const correct = originalLegal(frame, now);
    const wrong = wrongCommit(legalThenWrong.device, frame);
    queueMicrotask(() => legalThenWrong.device.inject(wrong.wire));
    return correct;
  };
  legalThenWrong.session.editDraft('install.x_cm', 35);
  const confirmed = await legalThenWrong.session.commitDraft();
  await micro();
  assert.equal(confirmed.ok, true);
  assert.equal(legalThenWrong.session.save.message, 'persisted_and_read_back');
  assert.equal(legalThenWrong.device.writeCount, 1);
  assert.equal(legalThenWrong.device.config['install.x_cm'], 35);
});

test('R2 readback failure or a changed page is not a full success', async () => {
  const failed = await online();
  const originalFailed = failed.device.dispatch.bind(failed.device);
  let failRead = false;
  failed.device.dispatch = (frame, now) => {
    if (frame.code === CODE.CONFIG_COMMIT) failRead = true;
    if (failRead && frame.code === CODE.CONFIG_READ) {
      failRead = false;
      return failed.device.make(frame, { ok: false, error: { code: 'INTERNAL_ERROR', message: 'read failed' } });
    }
    return originalFailed(frame, now);
  };
  failed.session.editDraft('install.x_cm', 36);
  const unreadable = await failed.session.commitDraft();
  assert.equal(unreadable.ok, false);
  assert.equal(unreadable.reason, 'persisted_readback_failed');
  assert.notEqual(failed.session.save.message, 'persisted_and_read_back');
  assert.equal(failed.device.writeCount, 1);
  const blocked = await failed.session.commitDraft();
  assert.equal(blocked.reason, 'readback_required');
  assert.equal(failed.device.writeCount, 1);

  const paged = await online();
  const originalPaged = paged.device.dispatch.bind(paged.device);
  let pageReads = 0;
  paged.device.dispatch = (frame, now) => {
    if (frame.code !== CODE.CONFIG_READ) return originalPaged(frame, now);
    pageReads += 1;
    if (pageReads === 1) return originalPaged(frame, now);
    return paged.device.make(frame, { ok: true, result: { revision: '99', items: [], next_cursor: null } });
  };
  paged.session.editDraft('install.x_cm', 37);
  const changedPage = await paged.session.commitDraft();
  assert.equal(changedPage.ok, false);
  assert.notEqual(paged.session.save.message, 'persisted_and_read_back');
  assert.equal(paged.device.writeCount, 1);
  assert.equal(paged.session.configRevision === '99', false);

  const diverged = await online();
  const originalDiverged = diverged.device.dispatch.bind(diverged.device);
  let bumped = false;
  diverged.device.dispatch = (frame, now) => {
    if (!bumped && frame.code === CODE.CONFIG_READ) {
      bumped = true;
      diverged.device.bumpExternal('install.x_cm', 77);
    }
    return originalDiverged(frame, now);
  };
  diverged.session.editDraft('install.x_cm', 38);
  const conflicted = await diverged.session.commitDraft();
  assert.equal(conflicted.ok, false);
  assert.equal(conflicted.reason, 'readback_diverged');
  assert.equal(diverged.session.draft['install.x_cm'], 77);
  assert.equal(diverged.device.writeCount, 1);
  assert.notEqual(diverged.session.save.message, 'persisted_and_read_back');
});

test('R3 fresh, stale, disconnected and recovered observations stay distinct', async () => {
  const box = await online();
  const writes = box.device.writeCount;
  box.device.emitTelemetry(observation('empty'));
  assert.equal(box.session.observationView().presence, 'absent');
  assert.equal(box.session.observationView().targets, 'empty');
  box.device.emitTelemetry(observation('zero'));
  assert.equal(box.session.observationView().presence, 'present');
  assert.equal(box.session.observationView().targets, 'points');
  assert.equal(checksFromSession(box.session).find((item) => item.id === 'radar').state, 'pass');
  box.clock.advance(9001);
  box.session.touchClock();
  const stale = checksFromSession(box.session);
  assert.equal(stale.find((item) => item.id === 'presence').state, 'stale');
  assert.equal(stale.find((item) => item.id === 'radar').state, 'stale');
  assert.equal(box.session.layers.radar, 'stale');
  assert.equal(box.session.layers.data, 'stale');
  await box.session.stop();
  const gone = checksFromSession(box.session);
  assert.notEqual(gone.find((item) => item.id === 'usb').state, 'pass');
  assert.notEqual(gone.find((item) => item.id === 'presence').state, 'present');
  assert.notEqual(box.session.layers.radar, 'healthy');
  assert.notEqual(box.session.layers.data, 'valid');
  box.device.faults.disconnect = false;
  const restored = await box.session.attach(box.transport, { mode: 'simulation' });
  assert.equal(restored.ok, true);
  box.session.client.stopHeartbeat();
  const left = box.session.client.sessionDeadline - box.clock.now() + 1;
  box.clock.advance(left);
  box.session.touchClock();
  assert.equal(box.session.layers.protocol, 'session_expired');
  assert.notEqual(checksFromSession(box.session).find((item) => item.id === 'presence').state, 'present');
  box.device.faults.disconnect = false;
  const again = await box.session.rehandshake();
  assert.equal(again.ok, true);
  assert.equal(box.session.layers.protocol, 'online');
  box.device.emitTelemetry(observation('zero'));
  assert.equal(box.session.presenceView().state, 'present');
  assert.equal(checksFromSession(box.session).find((item) => item.id === 'radar').state, 'pass');
  assert.equal(box.device.writeCount, writes);
});

test('mixed field freshness stays partial and does not expire fresh targets', async () => {
  const box = await online();
  const now = box.clock.now();
  const sent = now + 20000;
  box.device.emitTelemetry({
    source_seq: 90,
    sent_ms: sent,
    origin: 'simulation',
    presence: { value: true, quality: 'valid', sample_ms: now },
    targets_quality: 'valid',
    targets_ms: sent,
    targets: [{ id: '0', local_cm: [12, 34], room_cm: [12, 34], position_quality: 'valid', position_ms: sent, boundary: 'inside', speed_cm_s: null }],
  });
  const view = box.session.observationView();
  assert.equal(view.presence, 'stale');
  assert.equal(view.targets, 'points');
  assert.equal(box.session.layers.radar, 'partial');
  assert.equal(box.session.layers.data, 'partial');
  assert.equal(checksFromSession(box.session).find((item) => item.id === 'radar').state, 'partial');
  assert.equal(checksFromSession(box.session).find((item) => item.id === 'presence').state, 'stale');
  const row = targetRows(box.session.telemetry, null)[0];
  assert.equal(row.quality, 'valid');
  assert.equal(row.sampleMs, sent);
  box.session.touchClock();
  assert.equal(box.session.layers.radar, 'partial');
  assert.equal(checksFromSession(box.session).find((item) => item.id === 'radar').state, 'partial');
  box.device.emitTelemetry({
    source_seq: 91,
    sent_ms: now,
    origin: 'simulation',
    presence: { value: null, quality: 'unknown', sample_ms: null },
    targets_quality: 'unknown',
    targets_ms: null,
    targets: null,
  });
  assert.notEqual(box.session.layers.data, 'valid');
  assert.notEqual(checksFromSession(box.session).find((item) => item.id === 'radar').state, 'pass');
});

function captureCommits(device) {
  const original = device.commit.bind(device);
  const seen = [];
  device.commit = (frame, body) => {
    seen.push(body.changes);
    return original(frame, body);
  };
  return seen;
}

test('R2-A a clean reconnect adopts the device and commits only the new edit', async () => {
  const box = await online();
  box.session.editDraft('install.x_cm', 31);
  assert.equal((await box.session.commitDraft()).ok, true);
  await box.session.stop();
  box.device.bumpExternal('install.y_cm', 88);
  assert.equal((await box.session.attach(box.transport, { mode: 'simulation' })).ok, true);
  assert.equal(box.session.draft['install.y_cm'], 88);
  assert.equal(box.session.configItems.find((item) => item.key === 'install.y_cm').value, 88);
  assert.notEqual(box.session.save.message, 'persisted_and_read_back');
  assert.equal(box.session.editDraft('install.x_cm', 32).ok, true);
  assert.deepEqual(box.session.localChanges(), { 'install.x_cm': 32 });
  const seen = captureCommits(box.device);
  const saved = await box.session.commitDraft();
  assert.equal(saved.ok, true);
  assert.deepEqual(seen, [{ 'install.x_cm': 32 }]);
  assert.equal(box.device.config['install.y_cm'], 88);
});

test('R2-A unsaved edits stay visible and an external change must be reloaded', async () => {
  const box = await online();
  box.session.editDraft('install.x_cm', 32);
  await box.session.stop();
  box.device.bumpExternal('install.y_cm', 88);
  const writes = box.device.writeCount;
  assert.equal((await box.session.attach(box.transport, { mode: 'simulation' })).ok, true);
  assert.equal(box.session.draft['install.x_cm'], 32);
  assert.equal(box.session.save.phase, 'conflict');
  assert.equal(box.session.incomingConfig.items.find((item) => item.key === 'install.y_cm').value, 88);
  assert.equal(box.session.editDraft('install.x_cm', 33).ok, false);
  const refused = await box.session.commitDraft();
  assert.equal(refused.reason, 'revision_conflict');
  assert.equal(box.device.writeCount, writes);
  assert.equal(box.device.config['install.y_cm'], 88);
  const reloaded = await box.session.reloadFromDevice();
  assert.equal(reloaded.ok, true);
  assert.equal(box.session.save.phase, 'idle');
  assert.equal(box.session.draft['install.y_cm'], 88);
  assert.notEqual(box.session.draft['install.x_cm'], 32);
  const seen = captureCommits(box.device);
  box.session.editDraft('install.x_cm', 32);
  assert.equal((await box.session.commitDraft()).ok, true);
  assert.deepEqual(seen, [{ 'install.x_cm': 32 }]);
  assert.equal(box.device.config['install.y_cm'], 88);
});

test('R2-A a clean save can be edited again after reconnect and rehandshake', async () => {
  const box = await online();
  box.session.editDraft('install.x_cm', 31);
  assert.equal((await box.session.commitDraft()).ok, true);
  await box.session.stop();
  assert.equal((await box.session.attach(box.transport, { mode: 'simulation' })).ok, true);
  box.session.editDraft('install.x_cm', 32);
  assert.equal((await box.session.commitDraft()).ok, true);
  assert.equal(box.device.config['install.x_cm'], 32);
  const again = await box.session.rehandshake();
  assert.equal(again.ok, true);
  box.session.editDraft('install.x_cm', 33);
  assert.equal((await box.session.commitDraft()).ok, true);
  assert.equal(box.device.config['install.x_cm'], 33);
  assert.equal(box.device.config['install.y_cm'], 0);
});

test('R2-A reconnect keeps an unknown pending save', async () => {
  const box = await online();
  dropNextCommit(box.device);
  box.session.editDraft('install.x_cm', 40);
  const pending = box.session.commitDraft();
  await micro();
  const opId = box.session.save.opId;
  const base = box.session.save.baseRevision;
  await box.session.stop();
  await pending;
  assert.equal(box.session.save.phase, 'unknown');
  box.device.bumpExternal('install.y_cm', 88);
  assert.equal((await box.session.attach(box.transport, { mode: 'simulation' })).ok, true);
  assert.equal(box.session.save.phase, 'unknown');
  assert.equal(box.session.save.opId, opId);
  assert.equal(box.session.save.baseRevision, base);
  assert.equal(box.session.save.changes['install.x_cm'], 40);
  assert.equal((await box.session.commitDraft()).reason, 'pending_blocks_new_save');
  assert.equal(box.device.config['install.y_cm'], 88);
  const recovered = await box.session.recoverPending();
  assert.equal(recovered.reason, 'readback_diverged');
  assert.equal(box.session.save.phase, 'persisted');
  assert.equal(box.device.config['install.x_cm'], 40);
  assert.equal(box.device.config['install.y_cm'], 88);
});

test('R2-B a plain reload disconnect or read error is not a save confirmation', async () => {
  const box = await online();
  const writes = box.device.writeCount;
  box.device.faults.delayMs = 60000;
  const reload = box.session.reloadFromDevice();
  await micro();
  assert.equal(box.session.save.phase, 'reading');
  assert.equal(box.session.save.readPurpose, 'load');
  await box.session.stop();
  const interrupted = await reload;
  assert.equal(interrupted.ok, false);
  assert.equal(box.session.save.phase, 'failed');
  assert.equal(box.session.save.message, 'read_disconnected');
  assert.equal(box.device.writeCount, writes);
  box.device.faults.delayMs = 0;
  assert.equal((await box.session.attach(box.transport, { mode: 'simulation' })).ok, true);
  const original = box.device.dispatch.bind(box.device);
  box.device.dispatch = (frame, now) => {
    if (frame.code === CODE.CONFIG_READ && box.session.save.readPurpose === 'load') {
      return box.device.make(frame, { ok: false, error: { code: 'INTERNAL_ERROR', message: 'read failed' } });
    }
    return original(frame, now);
  };
  const failed = await box.session.reloadFromDevice();
  assert.equal(failed.ok, false);
  assert.equal(box.session.save.message, 'config_read_failed');
  assert.notEqual(box.session.save.phase, 'persisted');
  box.device.dispatch = original;
  const retried = await box.session.reloadFromDevice();
  assert.equal(retried.ok, true);
  assert.equal(box.session.save.phase, 'idle');
  box.session.editDraft('install.x_cm', 21);
  assert.equal((await box.session.commitDraft()).ok, true);
});

test('R2-B confirmed read-back failure stays confirmed and a lost ack stays unknown', async () => {
  const box = await online();
  const original = box.device.dispatch.bind(box.device);
  box.device.dispatch = (frame, now) => {
    if (frame.code === CODE.CONFIG_READ && box.session.save.readPurpose === 'readback') box.device.faults.delayMs = 60000;
    return original(frame, now);
  };
  box.session.editDraft('install.x_cm', 31);
  const saving = box.session.commitDraft();
  for (let i = 0; i < 30 && box.session.save.phase !== 'reading'; i += 1) await micro();
  assert.equal(box.session.save.readPurpose, 'readback');
  await box.session.stop();
  const readback = await saving;
  assert.equal(readback.ok, false);
  assert.equal(box.session.save.phase, 'persisted');
  assert.equal(box.session.save.message, 'persisted_readback_failed');
  assert.equal(box.device.writeCount, 1);
  box.device.faults.delayMs = 0;
  box.device.dispatch = original;
  assert.equal((await box.session.attach(box.transport, { mode: 'simulation' })).ok, true);
  box.session.editDraft('install.x_cm', 32);
  assert.equal((await box.session.commitDraft()).ok, true);

  const lostBox = await online();
  dropNextCommit(lostBox.device);
  lostBox.session.editDraft('install.x_cm', 29);
  const pending = lostBox.session.commitDraft();
  await micro();
  assert.equal(lostBox.session.save.phase, 'committing');
  const opId = lostBox.session.save.opId;
  await lostBox.session.stop();
  const lost = await pending;
  assert.equal(lost.ok, false);
  assert.equal(lostBox.session.save.phase, 'unknown');
  assert.equal(lostBox.session.save.opId, opId);
  assert.notEqual(lostBox.session.save.message, 'persisted_readback_failed');
  assert.equal((await lostBox.session.attach(lostBox.transport, { mode: 'simulation' })).ok, true);
  assert.equal(lostBox.session.save.phase, 'unknown');
  assert.equal(lostBox.session.save.opId, opId);
  const recovered = await lostBox.session.recoverPending();
  assert.equal(recovered.ok, true);
  assert.equal(lostBox.session.save.message, 'confirmed_by_status');
});
