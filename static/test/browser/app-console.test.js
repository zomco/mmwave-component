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

test('production app connects, saves, and keeps one port owner', async () => {
  const executable = findBrowser();
  assert.ok(executable, 'set MWCP_CHROME or install Chrome/Chromium');
  const outDir = mkdtempSync(join(tmpdir(), 'mwcp-app-'));
  await runBounded(process.execPath, [fileURLToPath(new URL('../../node_modules/vite/bin/vite.js', import.meta.url)), 'build', '--config', 'vite.app.config.js'], {
    cwd: root,
    env: { ...process.env, MWCP_APP_OUT: outDir },
    timeoutMs: 40000,
  });
  const server = await serve(outDir);
  const debugPort = await freePort();
  const profile = mkdtempSync(join(tmpdir(), 'mwcp-app-chrome-'));
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
        `http://127.0.0.1:${server.port}/app-browser.html`,
      ],
    });
    const page = await waitPage(debugPort, 5000);
    socket = connectCdp(page.webSocketDebuggerUrl, { openTimeoutMs: 3000, commandTimeoutMs: 1000 });
    await socket.send('Runtime.enable');
    await socket.send('Emulation.setDeviceMetricsOverride', {
      width: 390,
      height: 844,
      deviceScaleFactor: 1,
      mobile: true,
    });
    await waitForText(socket, { timeoutMs: 8000, commandTimeoutMs: 1000, match: '模拟页面。不是系统串口授权框' });
    await waitForText(socket, { timeoutMs: 8000, commandTimeoutMs: 1000, match: '选择雷达' });
    const focused = await evaluate(socket, `(() => {
      const button = document.querySelector('#diy button');
      if (!button) return 'missing';
      button.focus();
      return document.activeElement === button ? document.activeElement.tagName : 'unfocused';
    })()`);
    assert.equal(focused, 'BUTTON');
    await socket.send('Emulation.setDeviceMetricsOverride', {
      width: 1280,
      height: 900,
      deviceScaleFactor: 1,
      mobile: false,
    });
    await click(socket, 'R60ABD1');
    await click(socket, '继续');
    await click(socket, 'ESP32-C3 Super Mini');
    const checked = await evaluate(socket, `(() => {
      const box = document.querySelector('#diy input[type="checkbox"]');
      box.click();
      return box.checked;
    })()`);
    assert.equal(checked, true);
    await click(socket, '继续');
    await waitForText(socket, { timeoutMs: 3000, commandTimeoutMs: 1000, match: '烧录固件' });
    assert.doesNotMatch(await text(socket), /烧录成功/);

    await clickExact(socket, '连接设备');
    const connected = await waitForText(socket, { timeoutMs: 8000, commandTimeoutMs: 1000, match: 'r60abd1' });
    assert.match(connected, /R60ABD1/);
    assert.match(connected, /关闭安装窗口不等于端口已经释放/);
    const held = await flashState(socket);
    assert.equal(held.disabled, true);
    const sample = await evaluate(socket, `(() => {
      const now = Date.now();
      const body = window.__mwcp.observation('zero');
      body.presence.sample_ms = now;
      body.targets_ms = now;
      body.sent_ms = now;
      body.targets[0].position_ms = now;
      window.__mwcp.device.emitTelemetry(body);
      return 'sent';
    })()`);
    assert.equal(sample, 'sent');
    await waitForText(socket, { timeoutMs: 3000, commandTimeoutMs: 1000, match: '报告有人' });

    await clickExact(socket, '配置');
    await setField(socket, 'X (', '31');
    await waitForText(socket, { timeoutMs: 3000, commandTimeoutMs: 1000, match: 'install.x_cm' });
    const onlyX = await evaluate(socket, `[...document.querySelectorAll('#console li code')].map((item) => item.textContent).join(',')`);
    assert.equal(onlyX, 'install.x_cm');
    await click(socket, '在设备上验证');
    await waitEnabled(socket, '保存到设备');
    await click(socket, '保存到设备');
    await waitForText(socket, { timeoutMs: 5000, commandTimeoutMs: 1000, match: '已保存并读回' });
    const saved = await evaluate(socket, `(() => ({
      x: window.__mwcp.device.config['install.x_cm'],
      writes: window.__mwcp.device.writeCount,
    }))()`);
    assert.equal(saved.x, 31);
    assert.equal(saved.writes, 1);

    await evaluate(socket, 'window.__mwcp.port.closeDelay = 400');
    await clickExact(socket, '断开');
    await waitForText(socket, { timeoutMs: 3000, commandTimeoutMs: 1000, match: '正在释放端口' });
    await waitConsole(socket, '连接设备');
    await clickExact(socket, '快速验证');
    await waitForText(socket, { timeoutMs: 5000, commandTimeoutMs: 1000, match: '历史样本' });
    const released = await text(socket);
    assert.match(released, /已过期/);
    assert.doesNotMatch(released, /报告无人/);
    assert.doesNotMatch(released, /正在释放端口/);
    await evaluate(socket, 'window.__mwcp.port.closeDelay = 0');

    await evaluate(socket, `window.__mwcp.device.bumpExternal('install.y_cm', 88)`);
    await clickExact(socket, '连接设备');
    await waitForText(socket, { timeoutMs: 8000, commandTimeoutMs: 1000, match: 'r60abd1' });
    await clickExact(socket, '配置');
    let adopted = await readFields(socket);
    for (let i = 0; i < 30 && adopted.y !== '88'; i++) {
      await new Promise((r) => setTimeout(r, 100));
      adopted = await readFields(socket);
    }
    assert.equal(adopted.x, '31');
    assert.equal(adopted.y, '88');
    await setField(socket, 'X (', '32');
    const dirty = await evaluate(socket, `[...document.querySelectorAll('#console li code')].map((item) => item.textContent).join(',')`);
    assert.equal(dirty, 'install.x_cm');
    await clickExact(socket, '断开');
    await waitConsole(socket, '连接设备');
    await evaluate(socket, `window.__mwcp.device.bumpExternal('install.y_cm', 77)`);
    await clickExact(socket, '连接设备');
    await waitForText(socket, { timeoutMs: 8000, commandTimeoutMs: 1000, match: 'r60abd1' });
    await clickExact(socket, '配置');
    await waitForText(socket, { timeoutMs: 3000, commandTimeoutMs: 1000, match: '设备配置已被其他入口修改' });
    const kept = await readFields(socket);
    assert.equal(kept.x, '32');
    assert.equal(kept.y, '88');
    const saveDisabled = await evaluate(socket, `(() => {
      const button = [...document.querySelectorAll('button')].find((item) => item.textContent.trim() === '保存到设备');
      return button ? button.disabled : 'missing';
    })()`);
    assert.equal(saveDisabled, true);
    await click(socket, '重新读取设备');
    await waitForText(socket, { timeoutMs: 3000, commandTimeoutMs: 1000, match: '没有未保存的修改' });
    const reloaded = await readFields(socket);
    assert.equal(reloaded.x, '31');
    assert.equal(reloaded.y, '77');
    const afterReload = await text(socket);
    assert.doesNotMatch(afterReload, /设备配置已被其他入口修改/);
    await setField(socket, 'X (', '34');
    await click(socket, '在设备上验证');
    await waitEnabled(socket, '保存到设备');
    await click(socket, '保存到设备');
    await waitForText(socket, { timeoutMs: 5000, commandTimeoutMs: 1000, match: '已保存并读回' });
    const second = await evaluate(socket, `(() => ({
      x: window.__mwcp.device.config['install.x_cm'],
      y: window.__mwcp.device.config['install.y_cm'],
      writes: window.__mwcp.device.writeCount,
    }))()`);
    assert.equal(second.x, 34);
    assert.equal(second.y, 77);
    assert.equal(second.writes, 2);

    const closesBeforeFail = await evaluate(socket, 'window.__mwcp.port.closeCalls');
    await evaluate(socket, 'window.__mwcp.port.failClose = true');
    await clickExact(socket, '断开');
    await waitForText(socket, { timeoutMs: 3000, commandTimeoutMs: 1000, match: '端口关闭失败，仍然占用' });
    const failed = await flashState(socket);
    assert.equal(failed.disabled, true);
    assert.match(await text(socket), /仍然被 USB 调试占用/);
    const stillDisconnect = await evaluate(socket, `(() => {
      const connect = [...document.querySelectorAll('#console button')].find((item) => item.textContent.includes('连接设备'));
      const disconnect = [...document.querySelectorAll('#console button')].find((item) => item.textContent.includes('断开'));
      return { connect: connect ? connect.textContent : '', disconnect: disconnect ? disconnect.disabled : 'missing' };
    })()`);
    assert.equal(stillDisconnect.connect, '');
    assert.equal(stillDisconnect.disconnect, false);
    await evaluate(socket, 'window.__mwcp.port.failClose = false');
    await clickExact(socket, '断开');
    await waitConsole(socket, '连接设备');
    const closesAfter = await evaluate(socket, 'window.__mwcp.port.closeCalls');
    assert.equal(closesAfter, closesBeforeFail + 2);

    const opensBeforeDialog = await evaluate(socket, 'window.__mwcp.port.openCalls');
    const requests = await evaluate(socket, 'window.__mwcp.serial.requestCount');
    await evaluate(socket, `(() => {
      const dialog = document.createElement('ewt-install-dialog');
      document.body.appendChild(dialog);
      return dialog.tagName;
    })()`);
    await waitForText(socket, { timeoutMs: 3000, commandTimeoutMs: 1000, match: '安装窗口正占用 USB 口' });
    const blocked = await evaluate(socket, `(() => {
      const button = [...document.querySelectorAll('#console button')].find((item) => item.textContent.includes('连接设备'));
      return button ? button.disabled : 'missing';
    })()`);
    assert.equal(blocked, true);
    assert.equal(await evaluate(socket, 'window.__mwcp.serial.requestCount'), requests);
    await evaluate(socket, `document.querySelector('ewt-install-dialog').remove()`);
    await waitForText(socket, { timeoutMs: 3000, commandTimeoutMs: 1000, match: '安装窗口已关闭' });
    const manual = await evaluate(socket, `(() => {
      const button = [...document.querySelectorAll('#console button')].find((item) => item.textContent.includes('连接设备'));
      return button ? button.disabled : 'missing';
    })()`);
    assert.equal(manual, false);
    assert.equal(await evaluate(socket, 'window.__mwcp.port.openCalls'), opensBeforeDialog);

    const opens = await evaluate(socket, 'window.__mwcp.port.openCalls');
    await evaluate(socket, `window.__mwcp.serial.mode = 'cancel'`);
    await clickExact(socket, '连接设备');
    await waitForText(socket, { timeoutMs: 3000, commandTimeoutMs: 1000, match: '已取消选择端口' });
    assert.equal(await evaluate(socket, 'window.__mwcp.port.openCalls'), opens);
    assert.equal(await evaluate(socket, 'window.__mwcp.serial.requestCount'), requests + 1);
    assert.doesNotMatch(await text(socket), /烧录成功/);
    assert.equal(await evaluate(socket, 'window.__mwcp.simulation'), true);
  } finally {
    if (socket) socket.close();
    if (browser) await browser.close();
    await server.close();
  }
});

async function waitEnabled(cdp, label, timeoutMs = 5000) {
  const deadline = Date.now() + timeoutMs;
  let last = '';
  while (Date.now() < deadline) {
    last = await evaluate(cdp, `(() => {
      const button = [...document.querySelectorAll('button')].find((item) => item.textContent.trim() === ${JSON.stringify(label)});
      if (!button) return 'missing';
      return button.disabled ? 'disabled' : 'enabled';
    })()`);
    if (last === 'enabled') return;
    await new Promise((resolve) => setTimeout(resolve, 30));
  }
  throw new Error(`button stayed disabled ${label} ${last}`);
}

async function waitConsole(cdp, label, timeoutMs = 8000) {
  const deadline = Date.now() + timeoutMs;
  let last = '';
  while (Date.now() < deadline) {
    last = await evaluate(cdp, `(() => {
      const button = [...document.querySelectorAll('#console button')].find((item) => item.textContent.trim() === ${JSON.stringify(label)});
      if (!button) return 'missing';
      if (button.disabled) return 'disabled';
      return 'ready';
    })()`);
    if (last === 'ready') return;
    await new Promise((resolve) => setTimeout(resolve, 30));
  }
  throw new Error(`console button not ready ${label} ${last}`);
}

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

async function clickExact(cdp, label) {
  const result = await evaluate(cdp, `(() => {
    const button = [...document.querySelectorAll('button')].find((item) => item.textContent.trim() === ${JSON.stringify(label)});
    if (!button) return 'missing';
    if (button.disabled) return 'disabled';
    button.click();
    return 'clicked';
  })()`);
  assert.equal(result, 'clicked', label);
}

async function setField(cdp, label, value) {
  const result = await evaluate(cdp, `(() => {
    const field = [...document.querySelectorAll('#console label')].find((item) => item.textContent.trim().startsWith(${JSON.stringify(label)}));
    if (!field) return 'missing';
    const input = field.querySelector('input');
    if (!input || input.disabled) return input ? 'disabled' : 'missing-input';
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
    setter.call(input, ${JSON.stringify(value)});
    input.dispatchEvent(new Event('input', { bubbles: true }));
    return input.value;
  })()`);
  assert.equal(result, value, label);
}

function readFields(cdp) {
  return evaluate(cdp, `(() => {
    const value = (label) => {
      const field = [...document.querySelectorAll('#console label')].find((item) => item.textContent.trim().startsWith(label));
      return field && field.querySelector('input') ? field.querySelector('input').value : 'missing';
    };
    return { x: value('X ('), y: value('Y (') };
  })()`);
}

function flashState(cdp) {
  return evaluate(cdp, `(() => {
    const button = [...document.querySelectorAll('button')].find((item) => item.textContent.includes('连接设备并烧录'));
    return { disabled: button ? button.disabled : 'missing' };
  })()`);
}

function text(cdp) {
  return evaluate(cdp, 'document.body ? document.body.innerText : ""');
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
  const types = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.svg': 'image/svg+xml' };
  const sockets = new Set();
  const server = createServer(async (request, response) => {
    const url = new URL(request.url, 'http://127.0.0.1');
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
