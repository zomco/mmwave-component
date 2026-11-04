import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { SerialCoordinator } from '../src/console/serial-coordinator.js';
import { serialControls } from '../src/console/serial-ui.js';

const idleSession = { layers: { port: 'closed', protocol: 'offline', radar: 'unknown', data: 'none', config: 'idle' } };

function tick() {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

function fakePort() {
  return {
    readable: null,
    writable: null,
    openCalls: 0,
    closeCalls: 0,
    failClose: false,
    holdClose: null,
    listeners: {},
    addEventListener(type, fn) { this.listeners[type] = fn; },
    removeEventListener(type) { delete this.listeners[type]; },
    async open() {
      this.openCalls += 1;
      this.readable = {};
      this.writable = {};
    },
    async close() {
      this.closeCalls += 1;
      if (this.failClose) {
        const error = new Error('close failed');
        error.name = 'NetworkError';
        throw error;
      }
      if (this.holdClose) await this.holdClose;
      this.readable = null;
      this.writable = null;
    },
  };
}

function fakeSerial(port) {
  return {
    requestCount: 0,
    mode: 'ok',
    async requestPort() {
      this.requestCount += 1;
      if (this.gate) await this.gate;
      if (this.mode === 'cancel') {
        const error = new Error('cancelled');
        error.name = 'NotFoundError';
        throw error;
      }
      return port;
    },
  };
}

test('one port scenario covers cancel, delayed release, failed close and retry', async () => {
  const port = fakePort();
  const serial = fakeSerial(port);
  const coordinator = new SerialCoordinator({ serial, isSecureContext: true });
  const buttons = () => serialControls(coordinator.snapshot(), idleSession);

  serial.mode = 'cancel';
  const cancelResult = await coordinator.connect({ isSecureContext: true });
  assert.equal(cancelResult.reason, 'chooser_cancelled');
  assert.equal(cancelResult.ok, false);
  assert.equal(serial.requestCount, 1);
  assert.equal(port.openCalls, 0);
  assert.equal(port.closeCalls, 0);
  assert.equal(buttons().phase, 'idle');
  assert.equal(buttons().flashDisabled, false);
  assert.equal(coordinator.snapshot().connecting, false);
  serial.mode = 'ok';

  let releaseRequest;
  serial.gate = new Promise((resolve) => { releaseRequest = resolve; });
  const opening = coordinator.connect({ isSecureContext: true });
  await tick();
  assert.equal(coordinator.snapshot().connecting, true);
  assert.equal(buttons().phase, 'connecting');
  assert.equal(buttons().flashDisabled, true);
  assert.equal(buttons().connectDisabled, true);
  const overlapped = await coordinator.connect({ isSecureContext: true });
  assert.equal(overlapped.reason, 'port_busy');
  assert.equal(serial.requestCount, 2);
  releaseRequest();
  serial.gate = null;
  const opened = await opening;
  assert.equal(opened.ok, true);
  assert.equal(port.openCalls, 1);
  assert.equal(buttons().phase, 'console');
  assert.equal(buttons().showDisconnect, true);
  assert.equal(buttons().flashDisabled, true);

  let releaseClose;
  port.holdClose = new Promise((resolve) => { releaseClose = resolve; });
  const closing = coordinator.disconnect({ stop: async () => {} });
  await tick();
  assert.equal(coordinator.snapshot().busy, true);
  assert.equal(buttons().phase, 'closing');
  assert.equal(buttons().flashDisabled, true);
  assert.equal(buttons().connectDisabled, true);
  const duringClose = await coordinator.connect({ isSecureContext: true });
  assert.equal(duringClose.reason, 'port_busy');
  assert.equal(serial.requestCount, 2);
  assert.equal(port.closeCalls, 1);
  releaseClose();
  port.holdClose = null;
  const closed = await closing;
  assert.equal(closed.ok, true);
  assert.equal(coordinator.snapshot().owner, 'none');
  assert.equal(buttons().phase, 'idle');
  assert.equal(buttons().flashDisabled, false);

  const again = await coordinator.connect({ isSecureContext: true });
  assert.equal(again.ok, true);
  assert.equal(serial.requestCount, 3);
  assert.equal(port.openCalls, 2);
  port.failClose = true;
  const failed = await coordinator.disconnect({ stop: async () => {} });
  assert.equal(failed.ok, false);
  assert.equal(failed.closeError, 'NetworkError');
  assert.equal(coordinator.snapshot().owner, 'console');
  assert.equal(coordinator.snapshot().closeError, 'NetworkError');
  assert.equal(port.readable == null, false);
  assert.equal(buttons().phase, 'close_failed');
  assert.equal(buttons().flashDisabled, true);
  assert.equal(buttons().showDisconnect, true);
  assert.equal(port.closeCalls, 2);
  port.failClose = false;
  const retried = await coordinator.disconnect({ stop: async () => {} });
  assert.equal(retried.ok, true);
  assert.equal(port.closeCalls, 3);
  assert.equal(coordinator.snapshot().owner, 'none');
  assert.equal(coordinator.snapshot().closeError, null);
  assert.equal(buttons().phase, 'idle');

  coordinator.noteInstallerHolding();
  const closedEvent = coordinator.noteInstallerClosedEvent();
  assert.equal(closedEvent.released, false);
  assert.equal(coordinator.snapshot().owner, 'installer');
  const blocked = await coordinator.connect({ isSecureContext: true });
  assert.equal(blocked.reason, 'installer_holds_port');
  assert.equal(serial.requestCount, 3);
  assert.equal(port.openCalls, 2);
  assert.equal(buttons().phase, 'installer');
  assert.equal(buttons().connectDisabled, true);
  assert.equal(buttons().flashDisabled, true);
  const dismissed = coordinator.noteInstallerDismissed();
  assert.equal(dismissed.released, false);
  assert.equal(dismissed.reason, 'close_not_confirmed');
  assert.equal(buttons().phase, 'installer_unconfirmed');
  assert.equal(buttons().connectDisabled, false);
  assert.equal(buttons().flashDisabled, false);
  assert.equal(port.openCalls, 2);
});

test('production app wires port phase and does not inject a simulator', () => {
  const app = readFileSync(new URL('../src/App.jsx', import.meta.url), 'utf8');
  const main = readFileSync(new URL('../src/main.jsx', import.meta.url), 'utf8');
  const vite = readFileSync(new URL('../vite.config.js', import.meta.url), 'utf8');
  assert.equal(app.includes('serialControls(serialSnap, consoleSnap)'), true);
  assert.equal(app.includes('portHeld={controls.flashDisabled}'), true);
  assert.equal(app.includes('portPhase={controls.phase}'), true);
  assert.equal(app.includes("querySelector('ewt-install-dialog')"), true);
  assert.equal(app.includes('SimulatedDevice') || app.includes('__mwcp') || app.includes('navigator.serial ='), false);
  assert.equal(main.includes('SimulatedDevice') || main.includes('__mwcp') || main.includes('node:crypto'), false);
  assert.equal(vite.includes('node:crypto') || vite.includes('SimulatedDevice'), false);
});
