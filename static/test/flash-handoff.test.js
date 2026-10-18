import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { auditInstallerSources, claimReleasedPort, portIsClosed } from '../src/protocol/flash-handoff.js';

const root = new URL('../node_modules/esp-web-tools/src/', import.meta.url);
const connect = readFileSync(new URL('connect.ts', root), 'utf8');
const dialog = readFileSync(new URL('install-dialog.ts', root), 'utf8');

test('esp-web-tools 10.4.0 closed event is not port release', () => {
  const audit = auditInstallerSources(connect, dialog);
  assert.equal(audit.closedCallsPortClose, true);
  assert.equal(audit.closedAwaitsPortClose, false);
  assert.equal(audit.dialogReopensAfterFinish, true);
  assert.equal(audit.dialogInitializesImprovAfterFinish, true);
  assert.equal(audit.manifestCanDisableImprovWait, true);
});

test('console claims a port only after its own open resolves', async () => {
  const held = { readable: {}, writable: {} };
  assert.equal(portIsClosed(held), false);
  assert.equal((await claimReleasedPort(held, async () => {})).reason, 'installer_still_owns_port');
  const released = { readable: null, writable: null };
  const failed = await claimReleasedPort(released, async () => {
    throw Object.assign(new Error('busy'), { name: 'NetworkError' });
  });
  assert.equal(failed.ok, false);
  assert.equal(failed.reason, 'open_failed');
  const opened = { readable: null, writable: null };
  const ok = await claimReleasedPort(opened, async (port) => {
    port.readable = {};
    port.writable = {};
  });
  assert.equal(ok.ok, true);
  assert.equal(ok.owner, 'console');
});
