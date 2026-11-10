import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:net';
import { launchBrowser } from './browser-harness.js';

async function freePort() {
  const server = createServer();
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const port = server.address().port;
  await new Promise((resolve) => server.close(resolve));
  return port;
}

test('browser readiness waits for CDP rather than a running process', async () => {
  const port = await freePort();
  const script = `setTimeout(() => require('http').createServer((req,res) => {
    res.setHeader('content-type','application/json');
    res.end(JSON.stringify({webSocketDebuggerUrl:'ws://127.0.0.1:${port}/devtools/browser/test'}));
  }).listen(${port},'127.0.0.1'), 180);`;
  const browser = await launchBrowser({ executable: process.execPath,
    args: ['-e', script, '--', `--remote-debugging-port=${port}`], timeoutMs: 3000 });
  try {
    assert.equal((await fetch(`http://127.0.0.1:${port}/json/version`)).status, 200);
  } finally { await browser.close(); }
  assert.equal(launchBrowser.active(), 0);
});

test('browser crash after the old 30ms grace period reports its stderr', async () => {
  const port = await freePort();
  await assert.rejects(launchBrowser({ executable: process.execPath,
    args: ['-e', 'setTimeout(()=>{console.error("fixture launch failed");process.exit(7)},180)', '--', `--remote-debugging-port=${port}`],
    timeoutMs: 3000 }), /browser exited 7[\s\S]*fixture launch failed/);
  assert.equal(launchBrowser.active(), 0);
});

test('browser that never opens CDP is terminated at the startup deadline', async () => {
  const port = await freePort();
  await assert.rejects(launchBrowser({ executable: process.execPath,
    args: ['-e', 'console.error("fixture hung startup");setInterval(()=>{},1000)', '--', `--remote-debugging-port=${port}`],
    timeoutMs: 1000 }), /browser start timeout[\s\S]*fixture hung startup/);
  assert.equal(launchBrowser.active(), 0);
});
