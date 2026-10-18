import test from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createServer } from 'node:http';
import { mkdtempSync, readdirSync, readFileSync } from 'node:fs';
import { readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { extname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { findBrowser, killProcessTree, launchBrowser } from '../browser-harness.js';
import { connectCdp, waitForText } from '../cdp-client.js';

const root = fileURLToPath(new URL('../..', import.meta.url));

test('browser bundle instantiates ProtocolClient without Node APIs', async () => {
  const executable = findBrowser();
  assert.ok(executable, 'set MWCP_CHROME or install Chrome/Chromium');
  const outDir = mkdtempSync(join(tmpdir(), 'mwcp-browser-'));
  await runBounded(process.execPath, [fileURLToPath(new URL('../../node_modules/vite/bin/vite.js', import.meta.url)), 'build', '--config', 'vite.protocol.config.js'], {
    cwd: root,
    env: { ...process.env, MWCP_BROWSER_OUT: outDir },
    timeoutMs: 20000,
  });
  const bundleName = readdirSync(join(outDir, 'assets')).find((name) => name.endsWith('.js'));
  const bundle = readFileSync(join(outDir, 'assets', bundleName), 'utf8');
  assert.equal(bundle.includes('readFileSync'), false);
  assert.equal(bundle.includes('node:fs'), false);
  assert.equal(bundle.includes('node:crypto'), false);
  const server = await serve(outDir);
  const debugPort = await freePort();
  const profile = mkdtempSync(join(tmpdir(), 'mwcp-chrome-'));
  let browser = null;
  let socket = null;
  try {
    browser = await launchBrowser({
      executable,
      timeoutMs: 5000,
      args: [
        '--headless=new',
        '--disable-gpu',
        '--no-first-run',
        '--disable-extensions',
        `--user-data-dir=${profile}`,
        `--remote-debugging-port=${debugPort}`,
        '--remote-allow-origins=*',
        `http://127.0.0.1:${server.port}/protocol-browser.html`,
      ],
    });
    const page = await waitPage(debugPort, 5000);
    socket = connectCdp(page.webSocketDebuggerUrl, { openTimeoutMs: 3000, commandTimeoutMs: 1000 });
    await socket.send('Runtime.enable');
    const text = await waitForText(socket, { timeoutMs: 5000, commandTimeoutMs: 1000 });
    assert.match(text, /"ok":true/);
    assert.match(text, /"simulation":true/);
    assert.doesNotMatch(text, /readFileSync/);
  } finally {
    socket?.close();
    if (browser) await browser.close();
    await server.close();
    assert.equal(launchBrowser.active(), 0);
  }
});

function runBounded(command, args, { cwd, env, timeoutMs }) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { cwd, env, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
    let stdout = '';
    let stderr = '';
    const timer = setTimeout(() => {
      killProcessTree(child).finally(() => reject(new Error(`command timeout ${timeoutMs}`)));
    }, timeoutMs);
    child.stdout.on('data', (chunk) => { stdout += chunk; });
    child.stderr.on('data', (chunk) => { stderr += chunk; });
    child.once('error', (error) => {
      clearTimeout(timer);
      reject(error);
    });
    child.once('exit', (code) => {
      clearTimeout(timer);
      if (code === 0) resolve(stdout);
      else reject(new Error(`${command} failed ${code}\n${stderr}\n${stdout}`));
    });
  });
}

function serve(dir) {
  const types = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json' };
  const sockets = new Set();
  const server = createServer(async (request, response) => {
    const url = new URL(request.url, 'http://127.0.0.1');
    const path = join(dir, decodeURIComponent(url.pathname === '/' ? '/protocol-browser.html' : url.pathname));
    try {
      const body = await readFile(path);
      response.writeHead(200, { 'content-type': types[extname(path)] || 'application/octet-stream' });
      response.end(body);
    } catch {
      response.writeHead(404);
      response.end('missing');
    }
  });
  server.on('connection', (socket) => {
    sockets.add(socket);
    socket.on('close', () => sockets.delete(socket));
  });
  return new Promise((resolve) => {
    server.listen(0, '127.0.0.1', () => resolve({
      port: server.address().port,
      close() {
        for (const socket of sockets) socket.destroy();
        return new Promise((done) => {
          const timer = setTimeout(done, 500);
          server.close(() => {
            clearTimeout(timer);
            done();
          });
        });
      },
    }));
  });
}

function freePort() {
  return new Promise((resolve, reject) => {
    const probe = createServer();
    probe.once('error', reject);
    probe.listen(0, '127.0.0.1', () => {
      const { port } = probe.address();
      probe.close(() => resolve(port));
    });
  });
}

async function waitPage(port, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  let last = 'none';
  while (Date.now() < deadline) {
    try {
      const list = await fetchJson(`http://127.0.0.1:${port}/json/list`, 1000);
      const page = list.find((item) => item.type === 'page' && item.webSocketDebuggerUrl);
      if (page) return page;
      last = 'no page';
    } catch (error) {
      last = String(error);
    }
    await delay(50);
  }
  throw new Error(`browser debug timeout ${last}`);
}

function fetchJson(url, timeoutMs) {
  return fetch(url, { signal: AbortSignal.timeout(timeoutMs) }).then((response) => {
    if (!response.ok) throw new Error(`${response.status}`);
    return response.json();
  });
}

test('invalid browser path fails quickly and does not stay running', async () => {
  const started = Date.now();
  await assert.rejects(launchBrowser({ executable: 'mwcp-missing-browser', timeoutMs: 2000 }), /browser/);
  assert.ok(Date.now() - started < 3000);
  assert.equal(launchBrowser.active(), 0);
});

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
