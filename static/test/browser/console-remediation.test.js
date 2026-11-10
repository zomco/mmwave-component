import test from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createServer } from 'node:http';
import { mkdtempSync } from 'node:fs';
import { readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { extname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { findBrowser, killProcessTree, launchBrowser } from '../browser-harness.js';
import { connectCdp, waitForText } from '../cdp-client.js';

const root = fileURLToPath(new URL('../..', import.meta.url));

test('browser page clicks config and shows stale data on the simulated console', async () => {
  const executable = findBrowser();
  assert.ok(executable, 'set MWCP_CHROME or install Chrome/Chromium');
  const outDir = mkdtempSync(join(tmpdir(), 'mwcp-console-'));
  await runBounded(process.execPath, [fileURLToPath(new URL('../../node_modules/vite/bin/vite.js', import.meta.url)), 'build', '--config', 'vite.console.config.js'], {
    cwd: root,
    env: { ...process.env, MWCP_CONSOLE_OUT: outDir },
    timeoutMs: 20000,
  });
  const server = await serve(outDir);
  const debugPort = await freePort();
  const profile = mkdtempSync(join(tmpdir(), 'mwcp-console-chrome-'));
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
        `http://127.0.0.1:${server.port}/console-browser.html`,
      ],
    });
    const page = await waitPage(debugPort, 5000);
    socket = connectCdp(page.webSocketDebuggerUrl, { openTimeoutMs: 3000, commandTimeoutMs: 1000 });
    await socket.send('Runtime.enable');
    try {
      await waitForText(socket, { timeoutMs: 8000, commandTimeoutMs: 1000, match: '连接设备' });
    } catch (error) {
      const diag = await evaluate(socket, `(() => ({
        text: document.body ? document.body.innerText.slice(0, 400) : '',
        resources: performance.getEntriesByType('resource').map((item) => item.name),
      }))()`).catch((diagError) => String(diagError));
      throw new Error(String(error && error.message || error) + '\n' + JSON.stringify(diag));
    }
    await click(socket, '连接设备');
    const connected = await waitForText(socket, { timeoutMs: 5000, commandTimeoutMs: 1000, match: '模拟模式' });
    assert.match(connected, /r60abd1/);
    assert.doesNotMatch(connected, /烧录成功/);
    await click(socket, '配置');
    await waitForText(socket, { timeoutMs: 3000, commandTimeoutMs: 1000, match: '在设备上验证' });
    const edited = await evaluate(socket, `(() => new Promise((resolve) => {
      const deadline = Date.now() + 3000;
      const tick = () => {
        const input = document.querySelector('#console input.field');
        if (!input) {
          if (Date.now() > deadline) resolve('missing-input');
          else setTimeout(tick, 20);
          return;
        }
        const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        setter.call(input, '31');
        input.dispatchEvent(new Event('input', { bubbles: true }));
        resolve('edited');
      };
      tick();
    }))()`);
    assert.equal(edited, 'edited');
    await waitForText(socket, { timeoutMs: 3000, commandTimeoutMs: 1000, match: 'install.x_cm' });
    await click(socket, '在设备上验证');
    const validated = await evaluate(socket, `(() => new Promise((resolve) => {
      const deadline = Date.now() + 3000;
      const tick = () => {
        const message = window.__mwcp.session.save.message;
        if (message === 'validated') resolve('validated');
        else if (Date.now() > deadline) resolve(String(message));
        else setTimeout(tick, 20);
      };
      tick();
    }))()`);
    assert.equal(validated, 'validated');
    await click(socket, '保存到设备');
    const saved = await waitForText(socket, { timeoutMs: 5000, commandTimeoutMs: 1000, match: '已保存并读回' });
    assert.match(saved, /模拟模式/);
    assert.doesNotMatch(saved, /烧录成功/);
    await evaluate(socket, `window.__mwcp.device.emitTelemetry(window.__mwcp.observation('zero'))`);
    await click(socket, '快速验证');
    const freshQuick = await waitForText(socket, { timeoutMs: 3000, commandTimeoutMs: 1000, match: '报告有人' });
    assert.match(freshQuick, /报告有人/);
    await click(socket, '实时数据');
    const freshLive = await waitForText(socket, { timeoutMs: 3000, commandTimeoutMs: 1000, match: '报告有人' });
    assert.match(freshLive, /报告有人/);
    await evaluate(socket, `(() => {
      const now = window.__mwcp.clock.now(); const sent = now + 20000;
      window.__mwcp.device.emitTelemetry({
        source_seq: 90,
        sent_ms: sent,
        presence: { value: true, quality: 'valid', sample_ms: now },
        targets_quality: 'valid',
        targets_ms: sent,
        targets: [{ id: '0', local_cm: [12, 34], room_cm: [12, 34], position_quality: 'valid', position_ms: sent, boundary: 'inside', speed_cm_s: null }],
      });
      window.__mwcp.session.touchClock();
      return window.__mwcp.session.layers.radar;
    })()`);
    await click(socket, '快速验证');
    const mixedQuick = await waitForText(socket, { timeoutMs: 3000, commandTimeoutMs: 1000, match: '部分可用' });
    assert.match(mixedQuick, /已过期 · 有目标/);
    assert.match(mixedQuick, /目标坐标仍按自己的时间有效/);
    assert.doesNotMatch(mixedQuick, /报告有人/);
    await click(socket, '实时数据');
    const mixedLive = await waitForText(socket, { timeoutMs: 3000, commandTimeoutMs: 1000, match: '12, 34' });
    assert.match(mixedLive, /有效 · sample/);
    assert.match(mixedLive, /已过期/);
    await evaluate(socket, `(() => { window.__mwcp.clock.advance(9001); window.__mwcp.session.touchClock(); return window.__mwcp.session.observationView().presence; })()`);
    const staleLive = await waitForText(socket, { timeoutMs: 3000, commandTimeoutMs: 1000, match: '已过期' });
    assert.doesNotMatch(staleLive, /\bvalid\b/);
    await click(socket, '快速验证');
    const staleQuick = await waitForText(socket, { timeoutMs: 3000, commandTimeoutMs: 1000, match: '已过期' });
    assert.match(staleQuick, /已过期/);
    await evaluate(socket, `window.__mwcp.device.emitTelemetry(window.__mwcp.observation('zero'))`);
    const restored = await waitForText(socket, { timeoutMs: 3000, commandTimeoutMs: 1000, match: '报告有人' });
    assert.doesNotMatch(restored, /已过期/);
    await click(socket, '配置');
    await evaluate(socket, `window.__mwcp.device.faults.delayMs = 60000`);
    await click(socket, '重新读取设备');
    const reading = await evaluate(socket, `(() => new Promise((resolve) => {
      const deadline = Date.now() + 2000;
      const tick = () => {
        const phase = window.__mwcp.session.save.phase;
        if (phase === 'reading') resolve('reading');
        else if (Date.now() > deadline) resolve(String(phase));
        else setTimeout(tick, 20);
      };
      tick();
    }))()`);
    assert.equal(reading, 'reading');
    await click(socket, '断开');
    const interrupted = await waitForText(socket, { timeoutMs: 3000, commandTimeoutMs: 1000, match: '读取没有完成' });
    assert.doesNotMatch(interrupted, /保存已确认/);
    assert.equal(await evaluate(socket, `window.__mwcp.session.save.message`), 'read_disconnected');
    const kind = await evaluate(socket, `window.__mwcp.simulation === true && window.__mwcp.session.mode`);
    assert.equal(kind, 'simulation');
  } finally {
    socket?.close();
    if (browser) await browser.close();
    await server.close();
    assert.equal(launchBrowser.active(), 0);
  }
});

async function click(cdp, label) {
  const result = await evaluate(cdp, `(() => {
    const button = [...document.querySelectorAll('button')].find((item) => item.textContent.includes(${JSON.stringify(label)}));
    if (!button) return 'missing';
    if (button.disabled) return 'disabled';
    button.click();
    return 'clicked';
  })()`);
  assert.equal(result, 'clicked', label);
}

async function evaluate(cdp, expression) {
  const result = await cdp.send('Runtime.evaluate', {
    expression,
    returnByValue: true,
    awaitPromise: true,
  }, 4000);
  if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
  return result.result?.value;
}

function runBounded(command, args, { cwd, env, timeoutMs }) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { cwd, env, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
    let stdout = '';
    let stderr = '';
    const timer = setTimeout(() => {
      killProcessTree(child).finally(() => reject(new Error(`command timeout ${timeoutMs}\n${stderr}\n${stdout}`)));
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
    const path = join(dir, decodeURIComponent(url.pathname === '/' ? '/console-browser.html' : url.pathname));
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
      const list = await fetch(`http://127.0.0.1:${port}/json/list`, { signal: AbortSignal.timeout(1000) }).then((response) => {
        if (!response.ok) throw new Error(String(response.status));
        return response.json();
      });
      const page = list.find((item) => item.type === 'page' && item.webSocketDebuggerUrl);
      if (page) return page;
      last = 'no page';
    } catch (error) {
      last = String(error);
    }
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  throw new Error(`browser debug timeout ${last}`);
}
