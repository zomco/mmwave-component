import { createServer } from 'node:http';
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { extname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { findBrowser, launchBrowser } from '../../../../static/test/browser-harness.js';
import { connectCdp } from '../../../../static/test/cdp-client.js';

const evidence = fileURLToPath(new URL('.', import.meta.url));
const dist = fileURLToPath(new URL('../../../../static/dist/', import.meta.url));
const types = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.svg': 'image/svg+xml', '.png': 'image/png', '.webp': 'image/webp', '.woff2': 'font/woff2' };

const server = createServer(async (request, response) => {
  const url = new URL(request.url, 'http://127.0.0.1');
  const relative = decodeURIComponent(url.pathname === '/' ? '/index.html' : url.pathname).replace(/^\//, '');
  try {
    const body = await readFile(join(dist, relative));
    response.writeHead(200, { 'content-type': types[extname(relative)] || 'application/octet-stream' });
    response.end(body);
  } catch {
    response.writeHead(404);
    response.end('not found');
  }
});
await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
const pagePort = server.address().port;
const debugPort = await freePort();
const executable = findBrowser();
if (!executable) throw new Error('browser not found');
const profile = mkdtempSync(join(tmpdir(), 'mwcp-console-'));
const browser = await launchBrowser({
  executable,
  timeoutMs: 8000,
  args: ['--headless=new', '--disable-gpu', '--no-first-run', '--disable-extensions', '--user-data-dir=' + profile, '--remote-debugging-port=' + debugPort, '--remote-allow-origins=*', '--window-size=1280,900', 'http://127.0.0.1:' + pagePort + '/#console'],
});
const page = await waitPage(debugPort, pagePort, 8000);
console.log('page', page.url);
const cdp = connectCdp(page.webSocketDebuggerUrl, { openTimeoutMs: 4000, commandTimeoutMs: 8000 });
const report = { browser: executable, securePage: 'http://127.0.0.1:' + pagePort + '/#console', shots: [] };
try {
  await cdp.send('Page.enable');
  await cdp.send('Runtime.enable');
  await cdp.send('Page.navigate', { url: 'http://127.0.0.1:' + pagePort + '/#console' });
  await waitFor(cdp, "location.href.includes('127.0.0.1') && !!document.querySelector('#console')");
  await shot(cdp, report, 'zh-light-1280', { language: 'zh', theme: 'light', width: 1280, height: 900, tab: 'quick' });
  await shot(cdp, report, 'zh-dark-1280', { language: 'zh', theme: 'dark', width: 1280, height: 900, tab: 'quick' });
  await shot(cdp, report, 'en-light-1280', { language: 'en', theme: 'light', width: 1280, height: 900, tab: 'quick' });
  await shot(cdp, report, 'zh-light-390', { language: 'zh', theme: 'light', width: 390, height: 844, tab: 'quick', mobile: true });
  await shot(cdp, report, 'zh-light-config', { language: 'zh', theme: 'light', width: 1280, height: 900, tab: 'config' });
  await shot(cdp, report, 'zh-light-diag', { language: 'zh', theme: 'light', width: 1280, height: 900, tab: 'diag' });
  await prepare(cdp, { language: 'zh', theme: 'light', width: 1280, height: 900, tab: 'live' });
  await evalValue(cdp, "document.documentElement.style.zoom='200%'; true");
  const zoomed = await evalValue(cdp, "({ zoom: getComputedStyle(document.documentElement).zoom, console: !!document.querySelector('#console'), overflow: document.documentElement.scrollWidth > 0 })");
  report.zoom200 = zoomed;
  await saveShot(cdp, 'zh-light-zoom200');
  report.shots.push('zh-light-zoom200.png');
  await evalValue(cdp, "document.documentElement.style.zoom=''; document.querySelector('#console button')?.focus(); true");
  report.focus = await evalValue(cdp, "({ tag: document.activeElement && document.activeElement.tagName, text: (document.activeElement && document.activeElement.innerText || '').slice(0, 40) })");
  writeFileSync(join(evidence, 'dom-check.json'), JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report, null, 2));
} finally {
  cdp.close?.();
  await browser.close();
  await new Promise((resolve) => server.close(resolve));
}

async function shot(cdp, report, name, options) {
  const dom = await prepare(cdp, options);
  await saveShot(cdp, name);
  report.shots.push(name + '.png');
  report[name] = dom;
}

async function prepare(cdp, options) {
  await cdp.send('Emulation.setDeviceMetricsOverride', { width: options.width, height: options.height, deviceScaleFactor: 1, mobile: options.mobile === true });
  const desiredLang = options.language === 'zh' ? 'zh-CN' : 'en';
  const state = await evalValue(cdp, "({ href: location.href, lang: document.documentElement.lang, dark: document.documentElement.classList.contains('dark'), title: document.title, text: (document.body && document.body.innerText || '').slice(0, 180) })");
  console.log('state', JSON.stringify(state));
  await evalValue(cdp, "localStorage.setItem('mmwave-language'," + JSON.stringify(options.language) + "); localStorage.setItem('mmwave-theme'," + JSON.stringify(options.theme) + "); true");
  if (!state || state.lang !== desiredLang || state.dark !== (options.theme === 'dark')) {
    try { await evalValue(cdp, "location.hash='#console'; location.reload(); true"); } catch { /* context is replaced by the reload */ }
    await waitUntil(cdp);
  }
  await evalValue(cdp, "location.hash='#console'; true");
  await waitFor(cdp, "document.querySelector('#console h2') && document.querySelector('#console h2').textContent.length > 0");
  await evalValue(cdp, "(() => { const tabs=[...document.querySelectorAll('#console [role=tab]')]; const index={quick:0,live:1,config:2,diag:3}[" + JSON.stringify(options.tab) + "]; if (tabs[index]) tabs[index].click(); const root=document.querySelector('#console'); const header=document.querySelector('header'); const top=root.getBoundingClientRect().top + window.scrollY - ((header && header.offsetHeight) || 0) - 12; window.scrollTo(0, Math.max(0, top)); return true; })()");
  await new Promise((resolve) => setTimeout(resolve, 300));
  return evalValue(cdp, "(() => { const root=document.querySelector('#console'); const text=root.innerText; return { title: root.querySelector('h2')?.textContent, tabs: [...root.querySelectorAll('[role=tab]')].map(el => ({ text: el.textContent.trim(), selected: el.getAttribute('aria-selected') })), connectDisabled: root.querySelector('button')?.disabled ?? null, connectText: root.querySelector('button')?.innerText, serial: 'serial' in navigator, secure: window.isSecureContext, mentionsSimulation: /模拟|simulation/i.test(text), nav: !!document.querySelector('a[href=\"#console\"]'), headerWrap: document.querySelector('header .flex-wrap') != null, width: window.innerWidth, themeDark: document.documentElement.classList.contains('dark'), lang: document.documentElement.lang }; })()");
}

async function saveShot(cdp, name) {
  const image = await cdp.send('Page.captureScreenshot', { format: 'png' }, 15000);
  writeFileSync(join(evidence, name + '.png'), Buffer.from(image.data, 'base64'));
}

async function evalValue(cdp, expression) {
  const result = await cdp.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }, 8000);
  if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails).slice(0, 500));
  return result.result?.value;
}

async function waitUntil(cdp) {
  const start = Date.now();
  while (Date.now() - start < 8000) {
    try {
      const ready = await evalValue(cdp, "document.readyState === 'complete' && !!document.querySelector('#console')");
      if (ready) return;
    } catch { /* page is still navigating */ }
    await new Promise((resolve) => setTimeout(resolve, 150));
  }
  throw new Error('reload timeout');
}

async function waitFor(cdp, expression) {
  const start = Date.now();
  while (Date.now() - start < 8000) {
    const value = await evalValue(cdp, expression);
    if (value) return value;
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error('dom timeout');
}

function freePort() {
  return new Promise((resolve) => {
    const probe = createServer();
    probe.listen(0, '127.0.0.1', () => {
      const port = probe.address().port;
      probe.close(() => resolve(port));
    });
  });
}

async function waitPage(port, pagePort, timeoutMs) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const response = await fetch('http://127.0.0.1:' + port + '/json/list');
      const pages = await response.json();
      const found = pages.find((item) => item.type === 'page' && String(item.url).includes(':' + pagePort)) || pages.find((item) => item.type === 'page' && item.webSocketDebuggerUrl);
      if (!pages.some((item) => String(item.url).includes(':' + pagePort))) { await new Promise((resolve) => setTimeout(resolve, 100)); continue; }
      if (found) return found;
    } catch { /* debugger not up */ }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error('page timeout');
}
