import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { spawn } from 'node:child_process';
import { createServer } from 'node:http';
import { mkdtempSync } from 'node:fs';
import { readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { extname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { findBrowser, launchBrowser } from '../browser-harness.js';
import { connectCdp, waitForText } from '../cdp-client.js';

const root = fileURLToPath(new URL('../..', import.meta.url));
const manifestPath = '/firmware/v1.0.0-beta.1/r60abd1-ESP32-C3/manifest.json';
const manifestBody = JSON.stringify({
  name: 'QA fixture, not a firmware image',
  version: 'v1.0.0-beta.1',
  builds: [{ chipFamily: 'ESP32-C3', parts: [{ path: 'firmware.factory.bin', offset: 0 }] }],
});
const goodHash = createHash('sha256').update(manifestBody).digest('hex');
const badHash = '0'.repeat(64);

function releaseIndex(hash) {
  return JSON.stringify({
    schemaVersion: 1,
    releases: [{
      id: 'v1.0.0-beta.1',
      version: 'v1.0.0-beta.1',
      channel: 'beta',
      sourceCommit: 'a'.repeat(40),
      publishedAt: '2026-11-04T00:00:00.000Z',
      firmware: [{
        radarId: 'r60abd1',
        chipFamily: 'ESP32-C3',
        boardIds: ['esp32-c3-supermini'],
        manifest: manifestPath.slice(1),
        manifestSha256: hash,
      }],
    }],
  });
}

let built;
function buildOnce() {
  if (!built) {
    const outDir = mkdtempSync(join(tmpdir(), 'mwcp-flash-'));
    built = runBounded(process.execPath, [fileURLToPath(new URL('../../node_modules/vite/bin/vite.js', import.meta.url)), 'build', '--config', 'vite.app.config.js'], {
      cwd: root,
      env: Object.assign({}, process.env, { MWCP_APP_OUT: outDir }),
      timeoutMs: 40000,
    }).then(() => outDir);
  }
  return built;
}

test('a checked Beta manifest can flash only while the port is free', async () => {
  const executable = findBrowser();
  assert.ok(executable, 'set MWCP_CHROME or install Chrome/Chromium');
  const outDir = await buildOnce();
  const server = await serve(outDir, { releases: releaseIndex(goodHash), manifest: manifestBody });
  const session = await openPage(executable, server.port);
  const socket = session.socket;
  try {
    await socket.send('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
    await socket.send('Emulation.setFocusEmulationEnabled', { enabled: true });
    await waitForText(socket, { timeoutMs: 8000, commandTimeoutMs: 1000, match: '模拟页面。不是系统串口授权框' });
    await waitForText(socket, { timeoutMs: 8000, commandTimeoutMs: 1000, match: '选择雷达' });
    await socket.send('Input.dispatchMouseEvent', { type: 'mousePressed', x: 30, y: 30, button: 'left', clickCount: 1 });
    await socket.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: 30, y: 30, button: 'left', clickCount: 1 });
    const beforeTab = await evaluate(socket, 'document.activeElement ? document.activeElement.tagName : "none"');
    await socket.send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Tab', code: 'Tab', windowsVirtualKeyCode: 9, nativeVirtualKeyCode: 9 });
    await socket.send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Tab', code: 'Tab', windowsVirtualKeyCode: 9, nativeVirtualKeyCode: 9 });
    const afterTab = await evaluate(socket, 'document.activeElement ? document.activeElement.tagName : "none"');
    assert.notEqual(afterTab, beforeTab, 'Tab did not move focus');
    assert.match(afterTab, /^(A|BUTTON|INPUT|SELECT)$/);
    const narrowConnect = await controlBox(socket, '连接设备');
    assert.ok(narrowConnect.w > 0 && narrowConnect.h > 0 && narrowConnect.display !== 'none', JSON.stringify(narrowConnect));

    await socket.send('Emulation.setDeviceMetricsOverride', { width: 1280, height: 900, deviceScaleFactor: 1, mobile: false });
    await click(socket, 'R60ABD1');
    await click(socket, '继续');
    await click(socket, 'ESP32-C3 Super Mini');
    const checked = await evaluate(socket, '(() => { const box = document.querySelector("#diy input[type=checkbox]"); box.click(); return box.checked; })()');
    assert.equal(checked, true);
    await click(socket, '继续');
    await waitForText(socket, { timeoutMs: 4000, commandTimeoutMs: 1000, match: '烧录固件' });
    const ready = await waitInstall(socket, (state) => state.custom && state.disabled === false && state.manifest.indexOf(manifestPath) >= 0, 8000);
    assert.equal(ready.disabled, false);
    assert.equal(ready.manifest, 'http://127.0.0.1:' + server.port + manifestPath);
    const guide = await evaluate(socket, '(() => { const link = Array.from(document.querySelectorAll("a")).find((item) => item.textContent.trim() === "USB 调试使用说明"); return link ? link.getAttribute("href") : ""; })()');
    assert.equal(guide, 'https://github.com/zomco/mmwave-component/blob/main/docs/WEB_CONSOLE_CN.md');
    assert.doesNotMatch(await text(socket), /烧录成功/);

    await evaluate(socket, '(() => { window.__mwcp.serial.beforeGrant = () => new Promise((resolve) => { window.__mwcp.releaseGrant = resolve; }); })()');
    await clickExact(socket, '连接设备');
    const connecting = await waitInstall(socket, (state) => !state.custom && state.disabled === true, 4000);
    assert.equal(connecting.disabled, true);
    assert.match(await text(socket), /USB 调试正在连接、占用或释放这个端口/);
    await evaluate(socket, '(() => { window.__mwcp.serial.beforeGrant = null; window.__mwcp.releaseGrant(); })()');
    const online = await waitForText(socket, { timeoutMs: 8000, commandTimeoutMs: 1000, match: 'r60abd1' });
    assert.match(online, /R60ABD1/);
    const held = await waitInstall(socket, (state) => !state.custom && state.disabled === true, 4000);
    assert.equal(held.manifest, '');
    const rejected = await evaluate(socket, 'window.__mwcp.port.open().then(() => "opened", (error) => error && error.name)');
    assert.equal(rejected, 'InvalidStateError');
    assert.equal(await evaluate(socket, 'window.__mwcp.port.openCalls'), 1);

    await socket.send('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
    await clickExact(socket, '配置');
    await setField(socket, 'X (', '31');
    await waitEnabled(socket, '保存到设备');
    const saveBox = await controlBox(socket, '保存到设备');
    const disconnectBox = await controlBox(socket, '断开');
    assert.equal(saveBox.disabled, false);
    assert.ok(saveBox.w > 0 && saveBox.h > 0 && saveBox.display !== 'none', JSON.stringify(saveBox));
    assert.equal(disconnectBox.disabled, false);
    assert.ok(disconnectBox.w > 0 && disconnectBox.h > 0, JSON.stringify(disconnectBox));
    await clickExact(socket, '保存到设备');
    await waitForText(socket, { timeoutMs: 8000, commandTimeoutMs: 1000, match: '已保存并读回' });

    await evaluate(socket, 'window.__mwcp.port.closeDelay = 700');
    await clickExact(socket, '断开');
    await waitForText(socket, { timeoutMs: 3000, commandTimeoutMs: 1000, match: '正在释放端口' });
    const releasing = await installState(socket);
    assert.equal(releasing.custom, false);
    assert.equal(releasing.disabled, true);
    await waitConsole(socket, '连接设备');
    const restored = await waitInstall(socket, (state) => state.custom && state.disabled === false && state.manifest.indexOf(manifestPath) >= 0, 5000);
    assert.equal(restored.manifest, 'http://127.0.0.1:' + server.port + manifestPath);
    assert.match(await text(socket), /模拟页面/);
    assert.equal(await evaluate(socket, 'window.__mwcp.simulation'), true);
  } finally {
    session.socket.close();
    await session.browser.close();
    await server.close();
  }
});

test('a bad manifest checksum keeps flashing disabled', async () => {
  const executable = findBrowser();
  assert.ok(executable, 'set MWCP_CHROME or install Chrome/Chromium');
  const outDir = await buildOnce();
  const server = await serve(outDir, { releases: releaseIndex(badHash), manifest: manifestBody });
  const session = await openPage(executable, server.port);
  const socket = session.socket;
  try {
    await waitForText(socket, { timeoutMs: 8000, commandTimeoutMs: 1000, match: '选择雷达' });
    await click(socket, 'R60ABD1');
    await click(socket, '继续');
    await click(socket, 'ESP32-C3 Super Mini');
    await evaluate(socket, '(() => { document.querySelector("#diy input[type=checkbox]").click(); })()');
    await click(socket, '继续');
    await waitForText(socket, { timeoutMs: 8000, commandTimeoutMs: 1000, match: '固件清单不可用、版本不匹配或校验失败' });
    const blocked = await waitInstall(socket, (state) => !state.custom && state.disabled === true, 4000);
    assert.equal(blocked.custom, false);
    assert.equal(blocked.disabled, true);
    assert.equal(blocked.manifest, '');
    assert.doesNotMatch(await text(socket), /烧录成功/);
    assert.match(await text(socket), /模拟页面/);
  } finally {
    session.socket.close();
    await session.browser.close();
    await server.close();
  }
});

async function openPage(executable, port) {
  const debugPort = await freePort();
  const profile = mkdtempSync(join(tmpdir(), 'mwcp-flash-chrome-'));
  const browser = await launchBrowser({
    executable,
    timeoutMs: 5000,
    args: [
      '--headless=new',
      '--disable-gpu',
      '--no-first-run',
      '--disable-extensions',
      '--user-data-dir=' + profile,
      '--remote-debugging-port=' + debugPort,
      '--remote-allow-origins=*',
      'http://127.0.0.1:' + port + '/app-browser.html',
    ],
  });
  const page = await waitPage(debugPort, 5000);
  const socket = connectCdp(page.webSocketDebuggerUrl, { openTimeoutMs: 3000, commandTimeoutMs: 1000 });
  await socket.send('Runtime.enable');
  return { browser, socket };
}

function installState(cdp) {
  return evaluate(cdp, '(() => { const custom = document.querySelector("esp-web-install-button"); const button = Array.from(document.querySelectorAll("button")).find((item) => item.textContent.indexOf("连接设备并烧录") >= 0); return { manifest: custom ? String(custom.manifest || custom.getAttribute("manifest") || "") : "", custom: !!custom, disabled: button ? button.disabled : "missing" }; })()');
}

async function waitInstall(cdp, predicate, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  let last = null;
  while (Date.now() < deadline) {
    last = await installState(cdp);
    if (predicate(last)) return last;
    await new Promise((resolve) => setTimeout(resolve, 40));
  }
  throw new Error('install state ' + JSON.stringify(last));
}

async function controlBox(cdp, label) {
  return evaluate(cdp, '(() => { const label = ' + JSON.stringify(label) + '; const button = Array.from(document.querySelectorAll("button")).find((item) => item.textContent.trim() === label); if (!button) return { missing: true }; button.scrollIntoView({ block: "center" }); const rect = button.getBoundingClientRect(); const style = getComputedStyle(button); return { w: rect.width, h: rect.height, display: style.display, visibility: style.visibility, disabled: button.disabled }; })()');
}

async function waitEnabled(cdp, label) {
  const deadline = Date.now() + 5000;
  let last = '';
  while (Date.now() < deadline) {
    last = await evaluate(cdp, '(() => { const label = ' + JSON.stringify(label) + '; const button = Array.from(document.querySelectorAll("button")).find((item) => item.textContent.trim() === label); if (!button) return "missing"; return button.disabled ? "disabled" : "enabled"; })()');
    if (last === 'enabled') return;
    await new Promise((resolve) => setTimeout(resolve, 30));
  }
  throw new Error('button stayed disabled ' + label + ' ' + last);
}

async function waitConsole(cdp, label) {
  const deadline = Date.now() + 8000;
  let last = '';
  while (Date.now() < deadline) {
    last = await evaluate(cdp, '(() => { const label = ' + JSON.stringify(label) + '; const button = Array.from(document.querySelectorAll("#console button")).find((item) => item.textContent.trim() === label); if (!button) return "missing"; return button.disabled ? "disabled" : "ready"; })()');
    if (last === 'ready') return;
    await new Promise((resolve) => setTimeout(resolve, 30));
  }
  throw new Error('console button not ready ' + label + ' ' + last);
}

async function click(cdp, label) {
  const result = await evaluate(cdp, '(() => { const label = ' + JSON.stringify(label) + '; const button = Array.from(document.querySelectorAll("button")).find((item) => item.textContent.indexOf(label) >= 0); if (!button) return "missing"; if (button.disabled) return "disabled"; button.click(); return "clicked"; })()');
  assert.equal(result, 'clicked', label);
}

async function clickExact(cdp, label) {
  const result = await evaluate(cdp, '(() => { const label = ' + JSON.stringify(label) + '; const button = Array.from(document.querySelectorAll("button")).find((item) => item.textContent.trim() === label); if (!button) return "missing"; if (button.disabled) return "disabled"; button.click(); return "clicked"; })()');
  assert.equal(result, 'clicked', label);
}

async function setField(cdp, label, value) {
  const result = await evaluate(cdp, '(() => { const label = ' + JSON.stringify(label) + '; const value = ' + JSON.stringify(value) + '; const field = Array.from(document.querySelectorAll("#console label")).find((item) => item.textContent.trim().indexOf(label) === 0); if (!field) return "missing"; const input = field.querySelector("input"); if (!input || input.disabled) return input ? "disabled" : "missing-input"; const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set; setter.call(input, value); input.dispatchEvent(new Event("input", { bubbles: true })); return input.value; })()');
  assert.equal(result, value, label);
}

function text(cdp) {
  return evaluate(cdp, 'document.body ? document.body.innerText : ""');
}

async function evaluate(cdp, expression) {
  const result = await cdp.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }, 4000);
  if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
  return result.result ? result.result.value : undefined;
}

function runBounded(command, args, options) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { cwd: options.cwd, env: options.env, windowsHide: true });
    let stdout = '';
    let stderr = '';
    const timer = setTimeout(() => {
      child.kill();
      reject(new Error('timeout'));
    }, options.timeoutMs);
    child.stdout.on('data', (chunk) => { stdout += chunk; });
    child.stderr.on('data', (chunk) => { stderr += chunk; });
    child.once('error', (error) => { clearTimeout(timer); reject(error); });
    child.once('exit', (code) => {
      clearTimeout(timer);
      if (code === 0) resolve(stdout);
      else reject(new Error(command + ' failed ' + code + String.fromCharCode(10) + stderr + String.fromCharCode(10) + stdout));
    });
  });
}

function serve(dir, overlay) {
  const types = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.svg': 'image/svg+xml' };
  const sockets = new Set();
  const server = createServer(async (request, response) => {
    const url = new URL(request.url, 'http://127.0.0.1');
    if (url.pathname === '/releases.json') {
      response.writeHead(200, { 'content-type': 'application/json', 'cache-control': 'no-store' });
      response.end(overlay.releases);
      return;
    }
    if (url.pathname === manifestPath) {
      response.writeHead(200, { 'content-type': 'application/json', 'cache-control': 'no-store' });
      response.end(overlay.manifest);
      return;
    }
    if (url.pathname.endsWith('.bin')) {
      response.writeHead(404, { 'content-type': 'text/plain' });
      response.end('QA fixture: no flashable binary');
      return;
    }
    const path = join(dir, decodeURIComponent(url.pathname === '/' ? '/app-browser.html' : url.pathname));
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
          server.close(() => { clearTimeout(timer); done(); });
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
      const port = probe.address().port;
      probe.close(() => resolve(port));
    });
  });
}

async function waitPage(port, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  let last = 'none';
  while (Date.now() < deadline) {
    try {
      const list = await fetch('http://127.0.0.1:' + port + '/json/list', { signal: AbortSignal.timeout(1000) }).then((response) => {
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
  throw new Error('browser debug timeout ' + last);
}
