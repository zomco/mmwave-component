import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createDiagController } from '../src/g0/diag.js';
import { bindDiagPage } from '../src/g0/diag-page.js';
import { ProtocolClient } from '../src/protocol/client.js';
import { SimulatedDevice } from '../src/protocol/simulator.js';
import { createClock } from '../src/protocol/clock.js';

const hello = {
  client: { name: 'mmwave-web-console', version: '0.1.0' },
  nonce: '0123456789abcdef0123456789abcdef',
};

function createPort({ hangCancel = false } = {}) {
  let opened = false;
  let controller = null;
  let onWrite = () => {};
  let releaseWrite = null;
  let holdWrites = false;
  const readable = new ReadableStream({
    start(control) { controller = control; },
    cancel() { if (hangCancel) return new Promise(() => {}); },
  });
  const writable = new WritableStream({
    write(chunk) {
      if (!holdWrites) return onWrite(chunk);
      return new Promise((resolve) => {
        releaseWrite = () => {
          holdWrites = false;
          Promise.resolve(onWrite(chunk)).then(resolve, resolve);
        };
      });
    },
  });
  return {
    get readable() { return opened ? readable : null; },
    get writable() { return opened ? writable : null; },
    async open() { opened = true; },
    async close() {
      if (readable.locked || writable.locked) throw new Error('locked');
      opened = false;
    },
    push(bytes) {
      controller.enqueue(bytes instanceof Uint8Array ? bytes : Uint8Array.from(bytes));
    },
    fail(error) { controller.error(error); },
    setWriter(fn) { onWrite = fn; },
    holdNextWrite() { holdWrites = true; },
    releaseHeldWrite() {
      holdWrites = false;
      releaseWrite?.();
    },
    isOpen() { return opened; },
  };
}

function createStrictPort({ hangCancel = false } = {}) {
  let state = 'closed'; // 'closed' | 'opening' | 'opened' | 'closing'
  let readableStream = null;
  let writableStream = null;
  let streamController = null;
  let onWrite = () => {};
  let closeCallCount = 0;
  let openCallCount = 0;
  let customCloseHandler = null;
  let customOpenHandler = null;

  function initStreams() {
    readableStream = new ReadableStream({
      start(ctrl) { streamController = ctrl; },
      cancel() { if (hangCancel) return new Promise(() => {}); },
    });
    writableStream = new WritableStream({
      write(chunk) { return onWrite(chunk); },
    });
  }

  return {
    get readable() { return state === 'opened' ? readableStream : null; },
    get writable() { return state === 'opened' ? writableStream : null; },
    get state() { return state; },
    get closeCount() { return closeCallCount; },
    get openCount() { return openCallCount; },
    isOpen() { return state === 'opened'; },
    isClosed() { return state === 'closed'; },
    isClosing() { return state === 'closing'; },
    setCloseHandler(fn) { customCloseHandler = fn; },
    setOpenHandler(fn) { customOpenHandler = fn; },
    async open(options) {
      openCallCount++;
      if (state !== 'closed') {
        const err = new Error(`InvalidStateError: Cannot open port in state '${state}'`);
        err.name = 'InvalidStateError';
        throw err;
      }
      state = 'opening';
      if (customOpenHandler) {
        try {
          await customOpenHandler(options);
        } catch (err) {
          state = 'closed';
          throw err;
        }
      }
      initStreams();
      state = 'opened';
    },
    async close() {
      closeCallCount++;
      if (readableStream?.locked || writableStream?.locked) {
        const err = new Error('InvalidStateError: Cannot close a port with locked streams');
        err.name = 'InvalidStateError';
        throw err;
      }
      if (state === 'closing') {
        const err = new Error('InvalidStateError: A close() operation is already in progress');
        err.name = 'InvalidStateError';
        throw err;
      }
      if (state === 'closed') {
        const err = new Error('InvalidStateError: Cannot close a port that is already closed');
        err.name = 'InvalidStateError';
        throw err;
      }
      if (state !== 'opened') {
        const err = new Error(`InvalidStateError: Cannot close port in state '${state}'`);
        err.name = 'InvalidStateError';
        throw err;
      }
      state = 'closing';
      if (customCloseHandler) {
        try {
          await customCloseHandler();
          state = 'closed';
        } catch (err) {
          state = 'opened'; // close failed, leaves port in opened state for retry
          throw err;
        }
      } else {
        state = 'closed';
      }
    },
    push(bytes) {
      streamController?.enqueue(bytes instanceof Uint8Array ? bytes : Uint8Array.from(bytes));
    },
    fail(error) { streamController?.error(error); },
    setWriter(fn) { onWrite = fn; },
  };
}

function pageDom() {
  const nodes = new Map();
  function node(sel) {
    if (!nodes.has(sel)) {
      const listeners = {};
      nodes.set(sel, {
        textContent: '',
        addEventListener(type, fn) { (listeners[type] ||= []).push(fn); },
        async click() { for (const fn of listeners.click || []) await fn(); },
      });
    }
    return nodes.get(sel);
  }
  return {
    querySelector: node,
    click: (sel) => node(sel).click(),
    text: (sel) => node(sel).textContent,
  };
}

function harness(port, clock = createClock(0)) {
  const device = new SimulatedDevice({ clock, profile: 'r60' });
  const seen = [];
  port.setWriter((chunk) => {
    const bytes = chunk instanceof Uint8Array ? chunk : Uint8Array.from(chunk);
    seen.push(bytes);
    device.ingest(bytes);
  });
  device.onWire((bytes) => port.push(bytes));
  const diag = createDiagController({
    hello,
    clock,
    writeWaitMs: 50,
    maxSamples: 3,
    captureIntervalMs: 1000,
    createClient(transport) { return new ProtocolClient(transport, { clock }); },
  });
  return { diag, device, seen, clock };
}

test('streams stay null until open and locks are independent', async () => {
  const port = createPort();
  assert.equal(port.readable, null);
  assert.equal(port.writable, null);
  await port.open();
  const reader = port.readable.getReader();
  await reader.cancel();
  assert.equal(port.readable.locked, true);
  await assert.rejects(port.close(), /locked/);
  reader.releaseLock();
  const writer = port.writable.getWriter();
  assert.equal(port.writable.locked, true);
  assert.equal(port.readable.locked, false);
  await assert.rejects(port.close(), /locked/);
  writer.releaseLock();
  await port.close();
});

test('page buttons connect through the controller transport and leave online after a fault', async () => {
  const html = readFileSync(new URL('../g0-diag.html', import.meta.url), 'utf8');
  assert.match(html, /id="connect"/);
  assert.match(html, /id="capture"/);
  assert.match(html, /id="export"/);
  assert.doesNotMatch(html, /readable\.pipeTo/);
  const clock = createClock(0);
  const port = createPort();
  const { seen } = harness(port, clock);
  const dom = pageDom();
  bindDiagPage(dom, { async requestPort() { return port; } }, hello, {
    clock,
    clientOptions: { clock },
    writeWaitMs: 50,
  });
  await dom.click('#connect');
  assert.equal(dom.text('#state'), 'online');
  assert.ok(seen.length > 0);
  port.fail(new Error('unplugged'));
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.notEqual(dom.text('#state'), 'online');
  assert.match(dom.text('#state'), /error/);
});

test('disconnect waits for close, retains the port on failure, and a late select does not open', async () => {
  const clock = createClock(0);
  const port = createPort();
  const { diag } = harness(port, clock);
  await diag.connect({ async requestPort() { return port; } });
  assert.equal(diag.state(), 'online');
  let failClose = true;
  const realClose = port.close.bind(port);
  port.close = async () => {
    if (failClose) throw new Error('locked');
    return realClose();
  };
  await assert.rejects(diag.disconnect(), /locked/);
  assert.equal(diag.state(), 'error');
  assert.equal(port.isOpen(), true);
  failClose = false;
  await diag.disconnect();
  assert.equal(diag.state(), 'closed');
  assert.equal(port.isOpen(), false);

  let opened = false;
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  const late = createPort();
  const realOpen = late.open.bind(late);
  late.open = async () => { opened = true; return realOpen(); };
  const session = createDiagController({
    hello,
    clock,
    createClient(transport) { return new ProtocolClient(transport, { clock }); },
  });
  const pending = session.connect({ requestPort: () => gate.then(() => late) });
  const closing = session.disconnect();
  release();
  await closing;
  await pending.catch(() => {});
  assert.equal(opened, false);
  assert.notEqual(session.state(), 'online');
});

test('open, handshake, read failure, backpressure and a second click stay bounded', async () => {
  const clock = createClock(0);
  let releaseOpen;
  const openGate = new Promise((resolve) => { releaseOpen = resolve; });
  const port = createPort();
  const { diag, seen } = harness(port, clock);
  const realOpen = port.open.bind(port);
  port.open = () => openGate.then(() => realOpen());
  const opening = diag.connect({ async requestPort() { return port; } });
  const closing = diag.disconnect();
  releaseOpen();
  await closing;
  await opening.catch(() => {});
  assert.notEqual(diag.state(), 'online');
  assert.equal(port.isOpen(), false);

  const live = createPort();
  const again = harness(live, clock);
  const first = again.diag.connect({ async requestPort() { return live; } });
  await assert.rejects(again.diag.connect({ async requestPort() { return live; } }), /busy/);
  await first;
  assert.equal(again.diag.state(), 'online');
  assert.ok(again.seen.length > 0);

  again.diag.startCapture();
  live.holdNextWrite();
  const sampling = again.diag.sampleOnce();
  await new Promise((resolve) => setTimeout(resolve, 0));
  let closed = false;
  const realClose = live.close.bind(live);
  live.close = async () => { closed = true; return realClose(); };
  await assert.rejects(again.diag.disconnect(), /timeout|held/);
  assert.equal(closed, false);
  assert.equal(again.diag.state(), 'error');
  assert.equal(live.isOpen(), true);
  live.releaseHeldWrite();
  await sampling.catch(() => {});
  await again.diag.disconnect();
  assert.equal(closed, true);
  assert.equal(again.diag.state(), 'closed');
  assert.ok(seen || true);
});

test('capture keeps the start record, measures local rtt, and does not collide with an in-flight rpc', async () => {
  const clock = createClock(0);
  const port = createPort();
  const { diag } = harness(port, clock);
  await diag.connect({ async requestPort() { return port; } });
  diag.startCapture();
  await diag.sampleOnce();
  await diag.sampleOnce();
  await diag.sampleOnce();
  await diag.sampleOnce();
  const body = JSON.parse(diag.exportEvidence());
  assert.equal(body.start.kind, 'start');
  assert.equal(body.rtt_clock, 'local_monotonic');
  assert.equal(body.samples[0].seq, 1);
  assert.equal(typeof body.samples[0].rtt_ms, 'number');
  assert.equal(body.samples.at(-1).seq, 4);
  assert.equal(body.missing, 0);
  assert.equal(body.samples[0].status.radar_link, 'healthy');
  const hung = createPort();
  const blocked = harness(hung, clock);
  await blocked.diag.connect({ async requestPort() { return hung; } });
  blocked.diag.startCapture();
  hung.holdNextWrite();
  const pending = blocked.diag.sampleOnce();
  await new Promise((resolve) => setTimeout(resolve, 0));
  await blocked.diag.sampleOnce();
  assert.ok(blocked.diag.capture().gaps > 0);
  hung.releaseHeldWrite();
  await pending.catch(() => {});
  await blocked.diag.disconnect().catch(() => {});
});

test('a hung write leaves error, keeps the port, and stops capture', async () => {
  const clock = createClock(0);
  const port = createPort();
  const { diag } = harness(port, clock);
  await diag.connect({ async requestPort() { return port; } });
  diag.startCapture();
  port.holdNextWrite();
  const sampling = diag.sampleOnce();
  await new Promise((resolve) => setTimeout(resolve, 0));
  await assert.rejects(diag.disconnect(), /timeout|held/);
  assert.equal(diag.state(), 'error');
  assert.notEqual(diag.state(), 'online');
  assert.notEqual(diag.state(), 'closed');
  assert.equal(diag.capture().stopped, true);
  assert.equal(port.isOpen(), true);
  assert.match(diag.guidance(), /retry disconnect/);
  await assert.rejects(diag.connect({ async requestPort() { return port; } }), /busy|held|retry/);
  port.releaseHeldWrite();
  await sampling.catch(() => {});
});

test('cancel and open that never finish stay bounded and isolate the next attempt', async () => {
  const clock = createClock(0);
  const port = createPort({ hangCancel: true });
  const { diag } = harness(port, clock);
  await diag.connect({ async requestPort() { return port; } });
  await assert.rejects(diag.disconnect(), /timeout|held/);
  assert.equal(diag.state(), 'error');
  assert.notEqual(diag.state(), 'closed');
  assert.equal(port.isOpen(), true);

  let releaseOpen;
  const openGate = new Promise((resolve) => { releaseOpen = resolve; });
  const slow = createPort();
  const realOpen = slow.open.bind(slow);
  slow.open = () => openGate.then(() => realOpen());
  const session = createDiagController({
    hello,
    clock,
    ioWaitMs: 20,
    createClient(transport) { return new ProtocolClient(transport, { clock }); },
  });
  const opening = session.connect({ async requestPort() { return slow; } });
  await new Promise((resolve) => setTimeout(resolve, 0));
  await assert.rejects(session.disconnect(), /pending|timeout|held/);
  assert.equal(session.state(), 'error');
  assert.notEqual(session.state(), 'closed');
  releaseOpen();
  await opening.catch(() => {});
  await new Promise((resolve) => setTimeout(resolve, 30));
  assert.equal(slow.isOpen(), false);
  assert.notEqual(session.state(), 'online');
});

test('capture runs do not accept late results and stay bounded', async () => {
  const clock = createClock(0);
  const port = createPort();
  const { diag } = harness(port, clock);
  await diag.connect({ async requestPort() { return port; } });
  diag.startCapture();
  port.holdNextWrite();
  const late = diag.sampleOnce();
  await new Promise((resolve) => setTimeout(resolve, 0));
  const runA = diag.capture();
  await diag.stopCapture();
  diag.startCapture();
  const runB = diag.capture();
  port.releaseHeldWrite();
  await late.catch(() => {});
  assert.notEqual(runA, runB);
  assert.equal(runB.samples.length, 0);
  assert.ok(runA.samples.length + runA.errors.length > 0);
  await diag.disconnect().catch(() => {});

  const failed = createPort();
  const other = harness(failed, clock);
  await other.diag.connect({ async requestPort() { return failed; } });
  other.diag.startCapture();
  failed.holdNextWrite();
  const failing = other.diag.sampleOnce();
  await new Promise((resolve) => setTimeout(resolve, 0));
  const first = other.diag.capture();
  await other.diag.stopCapture();
  other.diag.startCapture();
  const second = other.diag.capture();
  failed.releaseHeldWrite();
  await failing.catch(() => {});
  assert.equal(second.errors.length, 0);
  assert.equal(second.samples.length, 0);
  assert.ok(first.sample_total + first.error_total > 0);
  await other.diag.disconnect().catch(() => {});

  const noisy = createDiagController({
    hello,
    clock,
    maxErrors: 2,
    maxEvents: 2,
    maxSamples: 2,
    maxSegments: 1,
    createClient(transport) { return new ProtocolClient(transport, { clock }); },
  });
  const noisePort = createPort();
  const device = new SimulatedDevice({ clock, profile: 'r60' });
  noisePort.setWriter((chunk) => device.ingest(chunk));
  device.onWire((bytes) => noisePort.push(bytes));
  await noisy.connect({ async requestPort() { return noisePort; } });
  noisy.startCapture();
  noisePort.setWriter(() => { throw new Error('boom'); });
  for (let i = 0; i < 5; i++) await noisy.sampleOnce();
  const exported = JSON.parse(noisy.exportEvidence());
  assert.equal(exported.error_total, 5);
  assert.ok(exported.errors.length <= 2);
  assert.ok(exported.dropped_errors >= 3);
  assert.ok(exported.sample_count >= 5);
  assert.equal(exported.healthy, false);
  assert.equal(exported.truncated, true);
  await noisy.disconnect().catch(() => {});
});

test('U2 recovery: timed-out selection returns, guidance is cleared, and reconnect succeeds', async () => {
  const clock = createClock(0);
  let releaseSelect;
  const selectGate = new Promise((resolve) => { releaseSelect = resolve; });
  const port1 = createPort();
  const session = createDiagController({
    hello,
    clock,
    ioWaitMs: 20,
    createClient(transport) { return new ProtocolClient(transport, { clock }); },
  });

  // Step 1: requestPort is pending
  const pending = session.connect({ requestPort: () => selectGate.then(() => port1) });
  await new Promise((resolve) => setTimeout(resolve, 0));

  // Step 2: disconnect times out waiting for requestPort -> holds error
  await assert.rejects(session.disconnect(), /pending|timeout|held/);
  assert.equal(session.state(), 'error');
  assert.match(session.guidance(), /retry disconnect/);

  // Step 3: requestPort returns; token !== generation, so port1 is not opened
  releaseSelect();
  await pending.catch(() => {});
  assert.equal(port1.isOpen(), false);

  // Step 4: wait for old operation to finish, call disconnect again
  await session.disconnect();
  assert.equal(session.state(), 'closed');
  assert.equal(session.guidance(), '');

  // Step 5: reconnect with new port succeeds
  const port2 = createPort();
  const device2 = new SimulatedDevice({ clock, profile: 'r60' });
  port2.setWriter((chunk) => device2.ingest(chunk));
  device2.onWire((bytes) => port2.push(bytes));
  await session.connect({ async requestPort() { return port2; } });
  assert.equal(session.state(), 'online');
  assert.equal(port2.isOpen(), true);
  assert.equal(port1.isOpen(), false);
  await session.disconnect();
});

test('U2 recovery: timed-out open completes late and cleans up, then reconnect succeeds', async () => {
  const clock = createClock(0);
  let releaseOpen;
  const openGate = new Promise((resolve) => { releaseOpen = resolve; });
  const slowPort = createPort();
  const realOpen = slowPort.open.bind(slowPort);
  slowPort.open = () => openGate.then(() => realOpen());

  const session = createDiagController({
    hello,
    clock,
    ioWaitMs: 20,
    createClient(transport) { return new ProtocolClient(transport, { clock }); },
  });

  const opening = session.connect({ async requestPort() { return slowPort; } });
  await new Promise((resolve) => setTimeout(resolve, 0));

  await assert.rejects(session.disconnect(), /pending|timeout|held/);
  assert.equal(session.state(), 'error');

  // Slow open resolves late, cleans itself up
  releaseOpen();
  await opening.catch(() => {});
  await new Promise((resolve) => setTimeout(resolve, 30));
  assert.equal(slowPort.isOpen(), false);

  // Disconnect clears guidance
  await session.disconnect();
  assert.equal(session.guidance(), '');

  // Reconnect succeeds
  const livePort = createPort();
  const device = new SimulatedDevice({ clock, profile: 'r60' });
  livePort.setWriter((chunk) => device.ingest(chunk));
  device.onWire((bytes) => livePort.push(bytes));
  await session.connect({ async requestPort() { return livePort; } });
  assert.equal(session.state(), 'online');
  assert.equal(livePort.isOpen(), true);
  await session.disconnect();
});

test('U2 recovery: late failure, duplicate disconnect, and retry after close failure', async () => {
  const clock = createClock(0);
  let rejectSelect;
  const selectGate = new Promise((_, reject) => { rejectSelect = reject; });
  const session = createDiagController({
    hello,
    clock,
    ioWaitMs: 20,
    createClient(transport) { return new ProtocolClient(transport, { clock }); },
  });

  const pending = session.connect({ requestPort: () => selectGate });
  await new Promise((resolve) => setTimeout(resolve, 0));
  await assert.rejects(session.disconnect(), /pending|timeout|held/);
  rejectSelect(new Error('user cancelled dialog'));
  await pending.catch(() => {});
  await session.disconnect();
  assert.equal(session.guidance(), '');

  // Duplicate disconnect calls
  await session.disconnect();
  await session.disconnect();
  assert.equal(session.guidance(), '');

  // Close failure and retry
  const port = createPort();
  const device = new SimulatedDevice({ clock, profile: 'r60' });
  port.setWriter((chunk) => device.ingest(chunk));
  device.onWire((bytes) => port.push(bytes));
  await session.connect({ async requestPort() { return port; } });
  assert.equal(session.state(), 'online');

  let failClose = true;
  const origClose = port.close.bind(port);
  port.close = async () => {
    if (failClose) throw new Error('hardware close fault');
    return origClose();
  };

  await assert.rejects(session.disconnect(), /hardware close fault/);
  assert.equal(session.state(), 'error');
  assert.match(session.guidance(), /retry disconnect/);

  // Reconnect rejected while resources held
  await assert.rejects(session.connect({ async requestPort() { return port; } }), /retry disconnect/);

  // Retry disconnect succeeds
  failClose = false;
  await session.disconnect();
  assert.equal(session.state(), 'closed');
  assert.equal(session.guidance(), '');

  // Reconnect now succeeds
  const port2 = createPort();
  const device2 = new SimulatedDevice({ clock, profile: 'r60' });
  port2.setWriter((chunk) => device2.ingest(chunk));
  device2.onWire((bytes) => port2.push(bytes));
  await session.connect({ async requestPort() { return port2; } });
  assert.equal(session.state(), 'online');
  await session.disconnect();
});

test('U2 recovery: old cleanup callback does not close a later-connected device', async () => {
  const clock = createClock(0);
  let finishClose1;
  const closeGate = new Promise((resolve) => { finishClose1 = resolve; });
  const port1 = createPort();
  const origClose1 = port1.close.bind(port1);
  port1.close = () => closeGate.then(() => origClose1());

  const session = createDiagController({
    hello,
    clock,
    ioWaitMs: 20,
    createClient(transport) { return new ProtocolClient(transport, { clock }); },
  });

  const dev1 = new SimulatedDevice({ clock, profile: 'r60' });
  port1.setWriter((chunk) => dev1.ingest(chunk));
  dev1.onWire((bytes) => port1.push(bytes));
  await session.connect({ async requestPort() { return port1; } });

  // Disconnect times out because port1.close is blocked
  await assert.rejects(session.disconnect(), /timeout|held/);

  // Now port1.close finishes
  finishClose1();
  await new Promise((resolve) => setTimeout(resolve, 30));
  await session.disconnect();
  assert.equal(session.guidance(), '');

  // Connect port2
  const port2 = createPort();
  const dev2 = new SimulatedDevice({ clock, profile: 'r60' });
  port2.setWriter((chunk) => dev2.ingest(chunk));
  dev2.onWire((bytes) => port2.push(bytes));
  await session.connect({ async requestPort() { return port2; } });
  assert.equal(session.state(), 'online');
  assert.equal(port2.isOpen(), true);

  // Verify port2 stays open and connected
  await new Promise((resolve) => setTimeout(resolve, 40));
  assert.equal(session.state(), 'online');
  assert.equal(port2.isOpen(), true);
  await session.disconnect();
});

test('U2 recovery: reconnect is strictly rejected when resources are genuinely unreleased', async () => {
  const clock = createClock(0);
  let releaseOpen;
  const openGate = new Promise((resolve) => { releaseOpen = resolve; });
  const stubbornPort = createPort();
  const realOpen = stubbornPort.open.bind(stubbornPort);
  stubbornPort.open = () => openGate.then(() => realOpen());

  let closeShouldFail = true;
  stubbornPort.close = async () => {
    if (closeShouldFail) throw new Error('port locked in OS driver');
  };

  const session = createDiagController({
    hello,
    clock,
    ioWaitMs: 20,
    createClient(transport) { return new ProtocolClient(transport, { clock }); },
  });

  const opening = session.connect({ async requestPort() { return stubbornPort; } });
  await new Promise((resolve) => setTimeout(resolve, 0));

  // Disconnect times out while opening
  await assert.rejects(session.disconnect(), /pending|timeout|held/);
  assert.equal(session.state(), 'error');

  // Stubborn open resolves, but its close fails with 'port locked in OS driver'
  releaseOpen();
  await opening.catch(() => {});
  await new Promise((resolve) => setTimeout(resolve, 40));

  // Reconnect MUST be rejected because stubbornPort failed to close
  const freshPort = createPort();
  await assert.rejects(session.connect({ async requestPort() { return freshPort; } }), /retry disconnect/);

  // Now driver releases lock, retry disconnect cleans up unreleased port
  closeShouldFail = false;
  await session.disconnect();
  assert.equal(session.state(), 'closed');
  assert.equal(session.guidance(), '');

  // Now reconnect succeeds!
  const device = new SimulatedDevice({ clock, profile: 'r60' });
  freshPort.setWriter((c) => device.ingest(c));
  device.onWire((b) => freshPort.push(b));
  await session.connect({ async requestPort() { return freshPort; } });
  assert.equal(session.state(), 'online');
  assert.equal(freshPort.isOpen(), true);
  await session.disconnect();
});

test('U3: continuous sampling far exceeding capacity strictly bounds arrays and distinguishes observations from raw retention', async () => {
  const clock = createClock(0);
  const diag = createDiagController({
    hello,
    clock,
    maxSamples: 2,
    maxSegments: 1,
    maxCoverageSegments: 1,
    maxErrors: 2,
    maxEvents: 2,
    createClient(transport) { return new ProtocolClient(transport, { clock }); },
  });

  const port = createPort();
  const device = new SimulatedDevice({ clock, profile: 'r60' });
  port.setWriter((chunk) => device.ingest(chunk));
  device.onWire((bytes) => port.push(bytes));
  await diag.connect({ async requestPort() { return port; } });
  diag.startCapture();

  for (let i = 0; i < 20; i++) {
    await diag.sampleOnce();
  }

  // Check controller internal arrays
  const cap = diag.capture();
  assert.ok(cap.samples.length <= 2, `samples length ${cap.samples.length} <= 2`);
  assert.ok(cap.segments.length <= 1, `segments length ${cap.segments.length} <= 1`);
  assert.ok(cap.coverage.length <= 1, `coverage length ${cap.coverage.length} <= 1`);
  assert.ok(cap.events.length <= 2, `events length ${cap.events.length} <= 2`);
  assert.ok(cap.errors.length <= 2, `errors length ${cap.errors.length} <= 2`);

  // Export evidence
  const exported = JSON.parse(diag.exportEvidence());
  assert.equal(exported.sample_attempts, 20);
  assert.equal(exported.raw_samples_retained, 2);
  assert.equal(exported.samples.length, 2);
  assert.equal(exported.summary_only_samples, 2);
  assert.equal(exported.dropped_samples, 16);
  assert.ok(exported.dropped_segments >= 8);
  assert.equal(exported.raw_evidence_complete, false);
  assert.equal(exported.healthy, false);
  assert.equal(exported.truncated, true);

  // Multiple exports do not consume capacity or alter evidence semantics
  const exportAgain = JSON.parse(diag.exportEvidence());
  assert.equal(exportAgain.sample_attempts, 20);
  assert.equal(exportAgain.raw_samples_retained, 2);
  assert.equal(exportAgain.dropped_samples, 16);
  assert.equal(exportAgain.export_index, exported.export_index + 1);
  assert.equal(exportAgain.healthy, exported.healthy);

  await diag.disconnect();
});

test('U3: ok:false responses (BUSY/RADAR_UNAVAILABLE) record errors and cannot be marked healthy', async () => {
  const clock = createClock(0);
  let returnBusy = false;
  const mockClient = {
    bootId: '0123456789abcdef0123456789abcdef',
    sessionId: 1,
    inflight() { return false; },
    async hello() { return { json: { ok: true, result: { boot_id: this.bootId, session_id: 1 } } }; },
    async request() {
      if (returnBusy) {
        return {
          json: {
            ok: false,
            error: { code: 5, message: 'RADAR_UNAVAILABLE' },
          },
        };
      }
      return {
        json: {
          ok: true,
          result: { radar_link: 'healthy', counters: {} },
        },
      };
    },
    startHeartbeat() {},
    stopHeartbeat() {},
    disconnect() {},
  };

  const diag = createDiagController({
    hello,
    clock,
    createClient() { return mockClient; },
  });

  const port = createPort();
  await diag.connect({ async requestPort() { return port; } });
  diag.startCapture();

  // One successful sample
  await diag.sampleOnce();
  let body = JSON.parse(diag.exportEvidence());
  assert.equal(body.responses_ok, 1);
  assert.equal(body.responses_error, 0);
  assert.equal(body.healthy, true);

  // ok:false sample
  returnBusy = true;
  await diag.sampleOnce();
  body = JSON.parse(diag.exportEvidence());
  assert.equal(body.responses_ok, 1);
  assert.equal(body.responses_error, 1);
  assert.equal(body.error_total, 1);
  assert.equal(body.errors.length, 1);
  assert.match(body.errors[0].message, /RADAR_UNAVAILABLE/);
  assert.equal(body.healthy, false);
  assert.equal(body.health_assessment.no_capture_failures, false);

  await diag.disconnect();
});

test('U3: segment reassembly identifies missing sequences, duplicates, and clean ordering', async () => {
  const clock = createClock(0);
  const diag = createDiagController({
    hello,
    clock,
    createClient(transport) { return new ProtocolClient(transport, { clock }); },
  });
  const port = createPort();
  const dev = new SimulatedDevice({ clock, profile: 'r60' });
  port.setWriter((c) => dev.ingest(c));
  dev.onWire((b) => port.push(b));
  await diag.connect({ async requestPort() { return port; } });
  diag.startCapture();
  for (let i = 0; i < 4; i++) await diag.sampleOnce();
  const clean = JSON.parse(diag.exportEvidence());
  assert.equal(clean.reconstruction_valid, true);
  assert.equal(clean.missing_sequences.length, 0);
  assert.equal(clean.duplicate_sequences.length, 0);

  // Manual inspection of segment gaps and overlaps
  const segmentsWithGap = [
    { seq_first: 1, seq_last: 5, count: 5, samples: [] },
    { seq_first: 8, seq_last: 10, count: 3, samples: [] },
  ];
  const cap = diag.capture();
  cap.samples = [];
  cap.segments = segmentsWithGap;
  cap.coverage = [];
  const withGap = JSON.parse(diag.exportEvidence());
  assert.equal(withGap.reconstruction_valid, false);
  assert.equal(withGap.missing_sequences.length, 1);
  assert.equal(withGap.missing_sequences[0].expected_from, 6);
  assert.equal(withGap.missing_sequences[0].expected_to, 7);

  const segmentsWithDup = [
    { seq_first: 1, seq_last: 5, count: 5, samples: [] },
    { seq_first: 4, seq_last: 8, count: 5, samples: [] },
  ];
  cap.samples = [];
  cap.segments = segmentsWithDup;
  cap.coverage = [];
  const withDup = JSON.parse(diag.exportEvidence());
  assert.equal(withDup.reconstruction_valid, false);
  assert.equal(withDup.duplicate_sequences.length, 1);
  assert.equal(withDup.duplicate_sequences[0].seq_start, 4);
  assert.equal(withDup.duplicate_sequences[0].seq_end, 5);

  await diag.disconnect();
});

test('U3: normal stop vs fault stop conclusions conform to definition', async () => {
  const clock = createClock(0);
  const diag = createDiagController({
    hello,
    clock,
    createClient(transport) { return new ProtocolClient(transport, { clock }); },
  });
  const port = createPort();
  const dev = new SimulatedDevice({ clock, profile: 'r60' });
  port.setWriter((c) => dev.ingest(c));
  dev.onWire((b) => port.push(b));
  await diag.connect({ async requestPort() { return port; } });

  // Normal stop
  diag.startCapture();
  await diag.sampleOnce();
  await diag.sampleOnce();
  await diag.stopCapture();
  const cleanStop = JSON.parse(diag.exportEvidence());
  assert.equal(cleanStop.health_assessment.stopped_cleanly, true);
  assert.equal(cleanStop.health_assessment.software_healthy, true);
  assert.equal(cleanStop.health_assessment.hardware_g0_verified, false);
  assert.equal(cleanStop.healthy, true);

  // Fault stop via disconnect
  diag.startCapture();
  await diag.sampleOnce();
  await diag.disconnect();
  const faultStop = JSON.parse(diag.exportEvidence());
  assert.equal(faultStop.health_assessment.stopped_cleanly, false);
  assert.equal(faultStop.healthy, false);
});

test('U2 strict: normal connection, close times out then completes late -> can reconnect', async () => {
  const clock = createClock(0);
  let finishClose1;
  const closeGate = new Promise((resolve) => { finishClose1 = resolve; });

  const port1 = createStrictPort();
  port1.setCloseHandler(() => closeGate);

  const session = createDiagController({
    hello,
    clock,
    ioWaitMs: 20,
    createClient(transport) { return new ProtocolClient(transport, { clock }); },
  });

  const dev1 = new SimulatedDevice({ clock, profile: 'r60' });
  port1.setWriter((c) => dev1.ingest(c));
  dev1.onWire((b) => port1.push(b));
  await session.connect({ async requestPort() { return port1; } });
  assert.equal(session.state(), 'online');

  // Disconnect times out because port1 close is deferred
  await assert.rejects(session.disconnect(), /timeout|held/);
  assert.equal(session.state(), 'error');
  assert.match(session.guidance(), /resources held/);

  // While closing is pending in background, reconnect is rejected
  const port2 = createStrictPort();
  await assert.rejects(session.connect({ async requestPort() { return port2; } }), /resources held|busy/);

  // Now port1 close completes late in the background
  finishClose1();
  await new Promise((resolve) => setTimeout(resolve, 30));

  // Disconnect called again: should not throw InvalidStateError on already-closed port1
  await session.disconnect();
  assert.equal(session.guidance(), '');
  assert.equal(session.state(), 'closed');

  // Reconnection with port2 must succeed
  const dev2 = new SimulatedDevice({ clock, profile: 'r60' });
  port2.setWriter((c) => dev2.ingest(c));
  dev2.onWire((b) => port2.push(b));
  await session.connect({ async requestPort() { return port2; } });
  assert.equal(session.state(), 'online');
  assert.equal(port2.isOpen(), true);
  await session.disconnect();
});

test('U2 strict: open completes late, cleanup close times out then completes late -> can reconnect', async () => {
  const clock = createClock(0);
  let finishOpen1, finishClose1;
  const openGate = new Promise((resolve) => { finishOpen1 = resolve; });
  const closeGate = new Promise((resolve) => { finishClose1 = resolve; });

  const port1 = createStrictPort();
  port1.setOpenHandler(() => openGate);
  port1.setCloseHandler(() => closeGate);

  const session = createDiagController({
    hello,
    clock,
    ioWaitMs: 20,
    createClient(transport) { return new ProtocolClient(transport, { clock }); },
  });

  const connectPromise = session.connect({ async requestPort() { return port1; } });
  await new Promise((resolve) => setTimeout(resolve, 5));

  // Disconnect while opening
  await assert.rejects(session.disconnect(), /pending|timeout|held/);

  // Open finishes late
  finishOpen1();
  await connectPromise.catch(() => {});
  await new Promise((resolve) => setTimeout(resolve, 30));

  // port1 close was started as late cleanup, and timed out. Resources held.
  const port2 = createStrictPort();
  await assert.rejects(session.connect({ async requestPort() { return port2; } }), /resources held|busy/);

  // Now port1 close finishes late
  finishClose1();
  await new Promise((resolve) => setTimeout(resolve, 30));

  // Disconnect cleans up unreleased state
  await session.disconnect();
  assert.equal(session.guidance(), '');

  // Connect port2 now succeeds
  const dev2 = new SimulatedDevice({ clock, profile: 'r60' });
  port2.setWriter((c) => dev2.ingest(c));
  dev2.onWire((b) => port2.push(b));
  await session.connect({ async requestPort() { return port2; } });
  assert.equal(session.state(), 'online');
  await session.disconnect();
});

test('U2 strict: close late failure allows safe retry', async () => {
  const clock = createClock(0);
  let failClose = true;
  let finishClose1;
  let closeGate = new Promise((resolve, reject) => { finishClose1 = { resolve, reject }; });

  const port1 = createStrictPort();
  port1.setCloseHandler(() => {
    if (failClose) {
      return closeGate;
    }
    return Promise.resolve();
  });

  const session = createDiagController({
    hello,
    clock,
    ioWaitMs: 20,
    createClient(transport) { return new ProtocolClient(transport, { clock }); },
  });

  const dev1 = new SimulatedDevice({ clock, profile: 'r60' });
  port1.setWriter((c) => dev1.ingest(c));
  dev1.onWire((b) => port1.push(b));
  await session.connect({ async requestPort() { return port1; } });

  // Disconnect times out
  await assert.rejects(session.disconnect(), /timeout|held/);

  // Late close rejects with error
  finishClose1.reject(new Error('driver failure during close'));
  await new Promise((resolve) => setTimeout(resolve, 30));

  // Resources still held
  const port2 = createStrictPort();
  await assert.rejects(session.connect({ async requestPort() { return port2; } }), /resources held/);

  // Now driver issue resolved; retry disconnect succeeds
  failClose = false;
  await session.disconnect();
  assert.equal(session.guidance(), '');
  assert.equal(session.state(), 'closed');

  // Reconnect succeeds
  const dev2 = new SimulatedDevice({ clock, profile: 'r60' });
  port2.setWriter((c) => dev2.ingest(c));
  dev2.onWire((b) => port2.push(b));
  await session.connect({ async requestPort() { return port2; } });
  assert.equal(session.state(), 'online');
  await session.disconnect();
});

test('U2 strict: close permanently hanging continuously refuses reconnect, API wait is bounded', async () => {
  const clock = createClock(0);
  const hangingPort = createStrictPort();
  hangingPort.setCloseHandler(() => new Promise(() => {})); // never resolves

  const session = createDiagController({
    hello,
    clock,
    ioWaitMs: 25,
    createClient(transport) { return new ProtocolClient(transport, { clock }); },
  });

  const dev = new SimulatedDevice({ clock, profile: 'r60' });
  hangingPort.setWriter((c) => dev.ingest(c));
  dev.onWire((b) => hangingPort.push(b));
  await session.connect({ async requestPort() { return hangingPort; } });

  const start1 = Date.now();
  await assert.rejects(session.disconnect(), /timeout|held/);
  const elapsed1 = Date.now() - start1;
  assert.ok(elapsed1 < 500, `API wait must be bounded, took ${elapsed1}ms`);

  // Reconnect refused
  const freshPort = createStrictPort();
  await assert.rejects(session.connect({ async requestPort() { return freshPort; } }), /resources held/);

  // Second disconnect also bounded and continues to reject
  const start2 = Date.now();
  await assert.rejects(session.disconnect(), /timeout|held/);
  const elapsed2 = Date.now() - start2;
  assert.ok(elapsed2 < 500, `Second API wait must be bounded, took ${elapsed2}ms`);
  await assert.rejects(session.connect({ async requestPort() { return freshPort; } }), /resources held/);
});

test('U2 strict: duplicate disconnect does not start concurrent close on same port', async () => {
  const clock = createClock(0);
  let finishClose;
  const closeGate = new Promise((resolve) => { finishClose = resolve; });

  const port = createStrictPort();
  port.setCloseHandler(() => closeGate);

  const session = createDiagController({
    hello,
    clock,
    ioWaitMs: 50,
    createClient(transport) { return new ProtocolClient(transport, { clock }); },
  });

  const dev = new SimulatedDevice({ clock, profile: 'r60' });
  port.setWriter((c) => dev.ingest(c));
  dev.onWire((b) => port.push(b));
  await session.connect({ async requestPort() { return port; } });

  // Launch duplicate disconnects
  const d1 = session.disconnect();
  const d2 = session.disconnect();

  // Allow microtasks for releaseIo to complete and reach close
  await new Promise((r) => setTimeout(r, 10));

  // close() should only be called once on port
  assert.equal(port.closeCount, 1);

  // Complete the close
  finishClose();
  await Promise.all([d1, d2]);
  assert.equal(port.closeCount, 1);
  assert.equal(port.isClosed(), true);
  assert.equal(session.state(), 'closed');
});

test('U2 strict: old cleanup task does not affect newly connected port', async () => {
  const clock = createClock(0);
  let finishClose1;
  const closeGate = new Promise((resolve) => { finishClose1 = resolve; });

  const port1 = createStrictPort();
  port1.setCloseHandler(() => closeGate);

  const session = createDiagController({
    hello,
    clock,
    ioWaitMs: 20,
    createClient(transport) { return new ProtocolClient(transport, { clock }); },
  });

  const dev1 = new SimulatedDevice({ clock, profile: 'r60' });
  port1.setWriter((c) => dev1.ingest(c));
  dev1.onWire((b) => port1.push(b));
  await session.connect({ async requestPort() { return port1; } });

  await assert.rejects(session.disconnect(), /timeout|held/);

  // Finish port1 close
  finishClose1();
  await new Promise((resolve) => setTimeout(resolve, 30));
  await session.disconnect();

  // Connect port2
  const port2 = createStrictPort();
  const dev2 = new SimulatedDevice({ clock, profile: 'r60' });
  port2.setWriter((c) => dev2.ingest(c));
  dev2.onWire((b) => port2.push(b));
  await session.connect({ async requestPort() { return port2; } });
  assert.equal(session.state(), 'online');

  // Verify port2 stays open and its state is not reset by port1's background resolution
  await new Promise((resolve) => setTimeout(resolve, 30));
  assert.equal(session.state(), 'online');
  assert.equal(port2.isOpen(), true);
  await session.disconnect();
});

test('U3 regression: maxSamples=2, maxSegments=1, Path A vs Path B identical outcome', async () => {
  const clockA = createClock(0);
  const diagA = createDiagController({
    hello,
    clock: clockA,
    maxSamples: 2,
    maxSegments: 1,
    maxCoverageSegments: 1,
    createClient(transport) { return new ProtocolClient(transport, { clock: clockA }); },
  });
  const portA = createPort();
  const devA = new SimulatedDevice({ clock: clockA, profile: 'r60' });
  portA.setWriter((c) => devA.ingest(c));
  devA.onWire((b) => portA.push(b));
  await diagA.connect({ async requestPort() { return portA; } });
  diagA.startCapture();

  // Path A: sample -> sample -> export
  await diagA.sampleOnce();
  await diagA.sampleOnce();
  const expA = JSON.parse(diagA.exportEvidence());

  const clockB = createClock(0);
  const diagB = createDiagController({
    hello,
    clock: clockB,
    maxSamples: 2,
    maxSegments: 1,
    maxCoverageSegments: 1,
    createClient(transport) { return new ProtocolClient(transport, { clock: clockB }); },
  });
  const portB = createPort();
  const devB = new SimulatedDevice({ clock: clockB, profile: 'r60' });
  portB.setWriter((c) => devB.ingest(c));
  devB.onWire((b) => portB.push(b));
  await diagB.connect({ async requestPort() { return portB; } });
  diagB.startCapture();

  // Path B: sample -> export -> sample -> export
  await diagB.sampleOnce();
  const expB1 = JSON.parse(diagB.exportEvidence());
  assert.equal(expB1.raw_samples_retained, 1);
  assert.equal(expB1.summary_only_samples, 0);

  await diagB.sampleOnce();
  const expB2 = JSON.parse(diagB.exportEvidence());

  // Both paths must retain both raw samples and produce identical health and counts
  assert.equal(expA.raw_samples_retained, 2);
  assert.equal(expA.summary_only_samples, 0);
  assert.equal(expA.dropped_samples, 0);
  assert.equal(expA.healthy, true);

  assert.equal(expB2.raw_samples_retained, 2);
  assert.equal(expB2.summary_only_samples, 0);
  assert.equal(expB2.dropped_samples, 0);
  assert.equal(expB2.healthy, true);

  await diagA.disconnect();
  await diagB.disconnect();
});

test('U3 regression: sampling and export interleaved across segment and coverage boundaries', async () => {
  const clock = createClock(0);
  const diag = createDiagController({
    hello,
    clock,
    maxSamples: 2,
    maxSegments: 2,
    maxCoverageSegments: 2,
    createClient(transport) { return new ProtocolClient(transport, { clock }); },
  });
  const port = createPort();
  const dev = new SimulatedDevice({ clock, profile: 'r60' });
  port.setWriter((c) => dev.ingest(c));
  dev.onWire((b) => port.push(b));
  await diag.connect({ async requestPort() { return port; } });
  diag.startCapture();

  // Interleave 10 samples and exports
  for (let i = 0; i < 10; i++) {
    await diag.sampleOnce();
    const snap = JSON.parse(diag.exportEvidence());
    assert.equal(snap.sample_attempts, i + 1);
    const sumCount = snap.raw_samples_retained + snap.summary_only_samples + snap.dropped_samples;
    assert.equal(sumCount, i + 1, `sample count invariant preserved at step ${i}`);
  }

  const finalExp = JSON.parse(diag.exportEvidence());
  assert.equal(finalExp.sample_attempts, 10);
  assert.equal(finalExp.raw_samples_retained, 4); // maxSegments(2) * maxSamples(2)
  assert.equal(finalExp.summary_only_samples, 4); // maxCoverageSegments(2) * maxSamples(2)
  assert.equal(finalExp.dropped_samples, 2); // 10 - 4 - 4
  await diag.disconnect();
});

test('U3 regression: identical sequence with zero vs frequent export yields identical final evidence', async () => {
  // Run 1: Zero intermediate exports
  const clock1 = createClock(0);
  const diag1 = createDiagController({
    hello,
    clock: clock1,
    maxSamples: 3,
    maxSegments: 2,
    maxCoverageSegments: 2,
    createClient(transport) { return new ProtocolClient(transport, { clock: clock1 }); },
  });
  const port1 = createPort();
  const dev1 = new SimulatedDevice({ clock: clock1, profile: 'r60' });
  port1.setWriter((c) => dev1.ingest(c));
  dev1.onWire((b) => port1.push(b));
  await diag1.connect({ async requestPort() { return port1; } });
  diag1.startCapture();
  for (let i = 0; i < 7; i++) await diag1.sampleOnce();
  const final1 = JSON.parse(diag1.exportEvidence());
  await diag1.disconnect();

  // Run 2: Frequent exports (after every sample)
  const clock2 = createClock(0);
  const diag2 = createDiagController({
    hello,
    clock: clock2,
    maxSamples: 3,
    maxSegments: 2,
    maxCoverageSegments: 2,
    createClient(transport) { return new ProtocolClient(transport, { clock: clock2 }); },
  });
  const port2 = createPort();
  const dev2 = new SimulatedDevice({ clock: clock2, profile: 'r60' });
  port2.setWriter((c) => dev2.ingest(c));
  dev2.onWire((b) => port2.push(b));
  await diag2.connect({ async requestPort() { return port2; } });
  diag2.startCapture();
  for (let i = 0; i < 7; i++) {
    await diag2.sampleOnce();
    diag2.exportEvidence();
  }
  const final2 = JSON.parse(diag2.exportEvidence());
  await diag2.disconnect();

  // Compare final outcomes: must be identical in counts and retention
  assert.equal(final1.sample_attempts, final2.sample_attempts);
  assert.equal(final1.raw_samples_retained, final2.raw_samples_retained);
  assert.equal(final1.summary_only_samples, final2.summary_only_samples);
  assert.equal(final1.dropped_samples, final2.dropped_samples);
  assert.equal(final1.healthy, final2.healthy);
  assert.equal(final1.samples.length, final2.samples.length);
  assert.equal(final1.missing, final2.missing);
});

test('U3 regression: consecutive exports without new samples do not mutate state', async () => {
  const clock = createClock(0);
  const diag = createDiagController({
    hello,
    clock,
    maxSamples: 4,
    maxSegments: 2,
    createClient(transport) { return new ProtocolClient(transport, { clock }); },
  });
  const port = createPort();
  const dev = new SimulatedDevice({ clock, profile: 'r60' });
  port.setWriter((c) => dev.ingest(c));
  dev.onWire((b) => port.push(b));
  await diag.connect({ async requestPort() { return port; } });
  diag.startCapture();

  await diag.sampleOnce();
  await diag.sampleOnce();

  const cap = diag.capture();
  const initialSamplesLen = cap.samples.length;
  const initialSegmentsLen = cap.segments.length;
  const initialCoverageLen = cap.coverage.length;
  const initialDropped = cap.dropped_samples;

  // Export 5 times in a row
  for (let i = 1; i <= 5; i++) {
    const exp = JSON.parse(diag.exportEvidence());
    assert.equal(exp.export_index, i);
    assert.equal(cap.samples.length, initialSamplesLen, 'cap.samples length must not change');
    assert.equal(cap.segments.length, initialSegmentsLen, 'cap.segments length must not change');
    assert.equal(cap.coverage.length, initialCoverageLen, 'cap.coverage length must not change');
    assert.equal(cap.dropped_samples, initialDropped, 'cap.dropped_samples must not change');
  }

  await diag.disconnect();
});

test('U3 regression: export after stop, after error response, and after capacity exhaustion', async () => {
  const clock = createClock(0);
  let errorMode = false;
  const mockClient = {
    bootId: '0123456789abcdef0123456789abcdef',
    sessionId: 1,
    inflight() { return false; },
    async hello() { return { json: { ok: true, result: { boot_id: this.bootId, session_id: 1 } } }; },
    async request() {
      if (errorMode) {
        return { json: { ok: false, error: { code: 9, message: 'RADAR_BUSY' } } };
      }
      return { json: { ok: true, result: { status: 'normal' } } };
    },
    startHeartbeat() {},
    stopHeartbeat() {},
    disconnect() {},
  };

  const diag = createDiagController({
    hello,
    clock,
    maxSamples: 2,
    maxSegments: 1,
    maxCoverageSegments: 1,
    createClient() { return mockClient; },
  });
  const port = createPort();
  await diag.connect({ async requestPort() { return port; } });
  diag.startCapture();

  // 1 sample ok
  await diag.sampleOnce();

  // 1 sample error
  errorMode = true;
  await diag.sampleOnce();
  const errExp = JSON.parse(diag.exportEvidence());
  assert.equal(errExp.responses_error, 1);
  assert.equal(errExp.healthy, false);

  // Stop capture and export
  await diag.stopCapture();
  const stopExp = JSON.parse(diag.exportEvidence());
  assert.equal(stopExp.health_assessment.stopped_cleanly, true);
  // because responses_error > 0, healthy is false
  assert.equal(stopExp.healthy, false);

  await diag.disconnect();
});

test('U2 lifecycle: same port object reopened across 3 consecutive connect->handshake->disconnect rounds', async () => {
  const clock = createClock(0);
  const port = createStrictPort();
  const device = new SimulatedDevice({ clock, profile: 'r60' });
  port.setWriter((c) => device.ingest(c));
  device.onWire((b) => port.push(b));

  const session = createDiagController({
    hello,
    clock,
    createClient(transport) { return new ProtocolClient(transport, { clock }); },
  });

  // Round 1
  await session.connect({ async requestPort() { return port; } });
  assert.equal(session.state(), 'online');
  assert.equal(port.isOpen(), true);
  assert.equal(port.openCount, 1);
  assert.equal(port.closeCount, 0);

  await session.disconnect();
  assert.equal(session.state(), 'closed');
  assert.equal(port.isClosed(), true);
  assert.equal(port.openCount, 1);
  assert.equal(port.closeCount, 1);

  // Round 2 (same port object)
  await session.connect({ async requestPort() { return port; } });
  assert.equal(session.state(), 'online');
  assert.equal(port.isOpen(), true);
  assert.equal(port.openCount, 2);
  assert.equal(port.closeCount, 1);

  await session.disconnect();
  assert.equal(session.state(), 'closed');
  assert.equal(port.isClosed(), true, 'port must be closed after round 2 disconnect');
  assert.equal(port.openCount, 2);
  assert.equal(port.closeCount, 2, 'port.close() must be called in round 2');

  // Round 3 (same port object)
  await session.connect({ async requestPort() { return port; } });
  assert.equal(session.state(), 'online');
  assert.equal(port.isOpen(), true);
  assert.equal(port.openCount, 3);
  assert.equal(port.closeCount, 2);

  await session.disconnect();
  assert.equal(session.state(), 'closed');
  assert.equal(port.isClosed(), true, 'port must be closed after round 3 disconnect');
  assert.equal(port.openCount, 3);
  assert.equal(port.closeCount, 3, 'port.close() must be called in round 3');
});

test('U2 lifecycle: same port close timeout late success, then reopened and closed normally', async () => {
  const clock = createClock(0);
  const port = createStrictPort();
  const device = new SimulatedDevice({ clock, profile: 'r60' });
  port.setWriter((c) => device.ingest(c));
  device.onWire((b) => port.push(b));

  const session = createDiagController({
    hello,
    clock,
    ioWaitMs: 20,
    createClient(transport) { return new ProtocolClient(transport, { clock }); },
  });

  // Round 1: connect and close times out
  let finishClose1;
  const closeGate1 = new Promise((resolve) => { finishClose1 = resolve; });
  port.setCloseHandler(() => closeGate1);

  await session.connect({ async requestPort() { return port; } });
  assert.equal(session.state(), 'online');

  await assert.rejects(session.disconnect(), /timeout|held/);
  assert.equal(session.guidance(), 'resources held; retry disconnect before connecting again');

  // Finish late close
  finishClose1();
  await new Promise((r) => setTimeout(r, 30));
  await session.disconnect();
  assert.equal(session.guidance(), '');
  assert.equal(port.isClosed(), true);
  assert.equal(port.openCount, 1);
  assert.equal(port.closeCount, 1);

  // Round 2: reopen same port and close normally
  port.setCloseHandler(null);
  await session.connect({ async requestPort() { return port; } });
  assert.equal(session.state(), 'online');
  assert.equal(port.isOpen(), true);
  assert.equal(port.openCount, 2);

  await session.disconnect();
  assert.equal(session.state(), 'closed');
  assert.equal(port.isClosed(), true);
  assert.equal(port.openCount, 2);
  assert.equal(port.closeCount, 2);
});

test('U2 lifecycle: previously closed port, next round open times out then succeeds late -> must execute cleanup close', async () => {
  const clock = createClock(0);
  const port = createStrictPort();
  const device = new SimulatedDevice({ clock, profile: 'r60' });
  port.setWriter((c) => device.ingest(c));
  device.onWire((b) => port.push(b));

  const session = createDiagController({
    hello,
    clock,
    ioWaitMs: 20,
    createClient(transport) { return new ProtocolClient(transport, { clock }); },
  });

  // Round 1: clean open and close
  await session.connect({ async requestPort() { return port; } });
  await session.disconnect();
  assert.equal(port.isClosed(), true);
  assert.equal(port.openCount, 1);
  assert.equal(port.closeCount, 1);

  // Round 2: same port, open times out
  let finishOpen2;
  const openGate2 = new Promise((resolve) => { finishOpen2 = resolve; });
  port.setOpenHandler(() => openGate2);

  const connectPromise = session.connect({ async requestPort() { return port; } });
  await new Promise((r) => setTimeout(r, 5));

  // Disconnect while opening
  await assert.rejects(session.disconnect(), /pending|timeout|held/);

  // Open finishes late: controller must recognize new lifecycle and close it
  finishOpen2();
  await connectPromise.catch(() => {});
  await new Promise((r) => setTimeout(r, 40));

  // Disconnect to complete cleanup if needed
  await session.disconnect().catch(() => {});
  assert.equal(session.guidance(), '');
  assert.equal(port.isClosed(), true, 'port must be closed after late open cleanup in round 2');
  assert.equal(port.openCount, 2);
  assert.equal(port.closeCount, 2, 'cleanup close must be called for round 2');

  // Round 3: same port can connect again cleanly
  port.setOpenHandler(null);
  await session.connect({ async requestPort() { return port; } });
  assert.equal(session.state(), 'online');
  assert.equal(port.isOpen(), true);
  assert.equal(port.openCount, 3);
  await session.disconnect();
  assert.equal(port.isClosed(), true);
  assert.equal(port.closeCount, 3);
});

test('U2 lifecycle: duplicate disconnect does not increase close count in same lifecycle, even on reused port', async () => {
  const clock = createClock(0);
  const port = createStrictPort();
  const device = new SimulatedDevice({ clock, profile: 'r60' });
  port.setWriter((c) => device.ingest(c));
  device.onWire((b) => port.push(b));

  const session = createDiagController({
    hello,
    clock,
    ioWaitMs: 50,
    createClient(transport) { return new ProtocolClient(transport, { clock }); },
  });

  // Round 1
  await session.connect({ async requestPort() { return port; } });
  await session.disconnect();
  assert.equal(port.openCount, 1);
  assert.equal(port.closeCount, 1);

  // Round 2
  let finishClose2;
  const closeGate2 = new Promise((resolve) => { finishClose2 = resolve; });
  port.setCloseHandler(() => closeGate2);

  await session.connect({ async requestPort() { return port; } });
  assert.equal(port.openCount, 2);

  const d1 = session.disconnect();
  const d2 = session.disconnect();

  await new Promise((r) => setTimeout(r, 10));
  assert.equal(port.closeCount, 2, 'close should only be called once in round 2');

  finishClose2();
  await Promise.all([d1, d2]);
  assert.equal(port.closeCount, 2);
  assert.equal(port.isClosed(), true);
});

test('U2 lifecycle: old tasks do not affect subsequent lifecycle, and failures maintain safe blocking', async () => {
  const clock = createClock(0);
  const port = createStrictPort();
  const device = new SimulatedDevice({ clock, profile: 'r60' });
  port.setWriter((c) => device.ingest(c));
  device.onWire((b) => port.push(b));

  const session = createDiagController({
    hello,
    clock,
    ioWaitMs: 20,
    createClient(transport) { return new ProtocolClient(transport, { clock }); },
  });

  // Round 1: close fails
  let failClose = true;
  port.setCloseHandler(() => {
    if (failClose) throw new Error('OS driver lock error');
    return Promise.resolve();
  });

  await session.connect({ async requestPort() { return port; } });
  await assert.rejects(session.disconnect(), /OS driver lock error|close timeout|held/);

  // Reconnect same port while close failed must be rejected
  await assert.rejects(session.connect({ async requestPort() { return port; } }), /resources held/);

  // Fix error and retry disconnect
  failClose = false;
  await session.disconnect();
  assert.equal(session.guidance(), '');
  assert.equal(port.isClosed(), true);

  // Round 2: connect same port succeeds and is not affected by round 1
  await session.connect({ async requestPort() { return port; } });
  assert.equal(session.state(), 'online');
  assert.equal(port.isOpen(), true);
  assert.equal(port.openCount, 2);

  await session.disconnect();
  assert.equal(session.state(), 'closed');
  assert.equal(port.isClosed(), true);
});



