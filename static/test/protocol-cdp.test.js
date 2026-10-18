import test from 'node:test';
import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import { connectCdp, waitForText } from './cdp-client.js';

function fakeSocket() {
  const listeners = { open: [], error: [], close: [], message: [] };
  return {
    addEventListener(type, fn) {
      listeners[type].push(fn);
    },
    dispatch(type, event = {}) {
      for (const fn of listeners[type]) fn(event);
    },
    send() {},
    close() {
      this.dispatch('close');
    },
  };
}

test('a connected CDP command that never replies times out', async () => {
  const socket = fakeSocket();
  const cdp = connectCdp('ws://invalid', { socket, openTimeoutMs: 10, commandTimeoutMs: 30 });
  socket.dispatch('open');
  const started = Date.now();
  await assert.rejects(cdp.send('Runtime.enable'), /cdp command timeout/);
  assert.ok(Date.now() - started < 200);
  assert.equal(cdp.pendingCount(), 0);
  cdp.close();
});

test('closing or erroring the CDP connection rejects the waiting command', async () => {
  const closed = fakeSocket();
  const closing = connectCdp('ws://invalid', { socket: closed, commandTimeoutMs: 1000 });
  closed.dispatch('open');
  const pending = closing.send('Runtime.enable');
  await Promise.resolve();
  closed.dispatch('close');
  await assert.rejects(pending, /cdp closed/);
  assert.equal(closing.pendingCount(), 0);

  const broken = fakeSocket();
  const failing = connectCdp('ws://invalid', { socket: broken, commandTimeoutMs: 1000 });
  broken.dispatch('open');
  const waiting = failing.send('Runtime.enable');
  await Promise.resolve();
  broken.dispatch('error');
  await assert.rejects(waiting, /cdp closed/);
  assert.equal(failing.pendingCount(), 0);
});

test('a CDP response clears its timer and a late response cannot complete the next command', async () => {
  const socket = fakeSocket();
  const cdp = connectCdp('ws://invalid', { socket, commandTimeoutMs: 40 });
  socket.dispatch('open');
  const first = cdp.send('Runtime.enable');
  await Promise.resolve();
  socket.dispatch('message', { data: JSON.stringify({ id: 1, result: { ok: true } }) });
  assert.deepEqual(await first, { ok: true });
  assert.equal(cdp.pendingCount(), 0);
  const second = cdp.send('Runtime.evaluate');
  await Promise.resolve();
  socket.dispatch('message', { data: JSON.stringify({ id: 1, result: { stale: true } }) });
  assert.equal(cdp.pendingCount(), 1);
  socket.dispatch('message', { data: JSON.stringify({ id: 2, result: { fresh: true } }) });
  assert.deepEqual(await second, { fresh: true });
  cdp.close();
});

test('a page that never reports completion fails within the deadline', async () => {
  const cdp = {
    async send() {
      return { result: { value: '' } };
    },
  };
  const started = Date.now();
  await assert.rejects(waitForText(cdp, { timeoutMs: 40, commandTimeoutMs: 10 }), /browser result missing/);
  assert.ok(Date.now() - started < 200);
});

test('unit test files do not launch a browser', () => {
  const pkg = JSON.parse(readFileSync(new URL('../package.json', import.meta.url), 'utf8'));
  assert.equal(pkg.scripts['test:unit'].includes('test/browser'), false);
  assert.equal(pkg.scripts['test:unit'].includes('test-skip-pattern'), false);
  assert.match(pkg.scripts['test:browser'], /test\/browser/);
  assert.match(pkg.scripts.test, /test\/\*\.test\.js/);
  assert.match(pkg.scripts.test, /test\/browser\/\*\.test\.js/);
  for (const name of readdirSync(new URL('.', import.meta.url))) {
    if (!name.endsWith('.test.js')) continue;
    const text = readFileSync(new URL(name, import.meta.url), 'utf8');
    assert.equal(/import\s*\{[^}]*\blaunchBrowser\b/.test(text), false, name);
  }
});
