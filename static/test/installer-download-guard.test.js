import test from 'node:test';
import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';
import { applyInstallerDownloadGuard, EMPTY_FIRMWARE_MESSAGE, NO_BYTES_MESSAGE } from '../script/apply-installer-download-guard.mjs';

const require = createRequire(import.meta.url);
const root = fileURLToPath(new URL('..', import.meta.url));
const changed = applyInstallerDownloadGuard();
assert.deepEqual(applyInstallerDownloadGuard(), []);
const { deflate, Inflate } = require('pako');
const flashSource = readFileSync(root + '/node_modules/esp-web-tools/dist/flash.js', 'utf8');
const webFile = readdirSync(root + '/node_modules/esp-web-tools/dist/web').find((name) => name.startsWith('install-dialog-'));
const webSource = readFileSync(root + '/node_modules/esp-web-tools/dist/web/' + webFile, 'utf8');
const loaderSource = readFileSync(root + '/node_modules/esptool-js/lib/esploader.js', 'utf8');
const candidateDir = root + '/../docs/reviews/web-console/mwcp-firmware-20261105/firmware/v0.0.0-local.20261105/r60abd1-ESP32-C3';
const manifest = JSON.parse(readFileSync(candidateDir + '/manifest.json', 'utf8'));
const candidate = readFileSync(candidateDir + '/r60abd1.factory.bin');

function guardPrecedesWrite(text) {
  const at = text.indexOf(EMPTY_FIRMWARE_MESSAGE);
  assert.ok(at > 0);
  assert.ok(text.indexOf('eraseFlash', at) > at);
  assert.ok(text.indexOf('writeFlash', at) > at);
  assert.equal(text.includes('readAsArrayBuffer'), false);
}

test('the page bundle and the flash module both stop before erase', () => {
  guardPrecedesWrite(flashSource);
  guardPrecedesWrite(webSource);
  guardPrecedesWrite(readFileSync(root + '/node_modules/esp-web-tools/src/flash.ts', 'utf8'));
  const entry = readFileSync(root + '/src/main.jsx', 'utf8');
  const browserEntry = readFileSync(root + '/app-browser-entry.jsx', 'utf8');
  assert.match(entry, /esp-web-tools\/dist\/web\/install-button\.js/);
  assert.match(browserEntry, /esp-web-tools\/dist\/web\/install-button\.js/);
  assert.ok(Array.isArray(changed));
});

test('the bundled download expression rejects empty and unreadable bodies', async () => {
  const start = webSource.indexOf('if(!i.ok)throw new Error(');
  const end = webSource.indexOf('return r', start);
  const snippet = webSource.slice(start, end + 'return r'.length);
  assert.ok(snippet.length < 900);
  assert.ok(snippet.includes(EMPTY_FIRMWARE_MESSAGE));
  const run = new Function('i', 'e', 'return (async () => { ' + snippet + ' })()');
  const part = { path: 'r60abd1.factory.bin' };
  await assert.rejects(
    run({ ok: true, status: 200, arrayBuffer: async () => new ArrayBuffer(0) }, part),
    (err) => err.message.includes(EMPTY_FIRMWARE_MESSAGE)
  );
  const body = new Uint8Array([1, 2, 3, 4]).buffer;
  const saved = await run({ ok: true, status: 200, arrayBuffer: async () => body }, part);
  assert.equal(saved.byteLength, 4);
  await assert.rejects(
    run({ ok: false, status: 404, arrayBuffer: async () => body }, part),
    (err) => err.message.includes('404')
  );
  await assert.rejects(
    run({ ok: true, status: 200, arrayBuffer: async () => { throw new Error('body aborted'); } }, part),
    (err) => err.message.includes('body aborted')
  );
});

const writeStart = loaderSource.indexOf('    async writeFlash(options) {');
const writeEnd = loaderSource.indexOf('\n    /**', writeStart);
assert.ok(writeStart > 0 && writeEnd > writeStart);
const WriteImpl = vm.runInNewContext('(class {\n' + loaderSource.slice(writeStart, writeEnd) + '\n})', {
  deflate,
  Inflate,
  Uint8Array,
  Date,
  Math,
  String,
  ESPError: Error,
  padTo: (data, alignment) => {
    const out = new Uint8Array(Math.ceil(data.length / alignment) * alignment).fill(255);
    out.set(data);
    return out;
  },
});
const writeFlash = WriteImpl.prototype.writeFlash;

async function runFlash(options) {
  const events = [];
  const io = { disconnects: 0, erases: 0, writes: 0, fetches: 0 };
  class IOTransport {
    async setRTS() {}
    async disconnect() { io.disconnects += 1; }
  }
  class Loader {
    constructor() {
      this.chip = { CHIP_NAME: 'ESP32-C3' };
      this.IS_STUB = false;
      this.FLASH_WRITE_SIZE = 0x4000;
      this.ERASE_WRITE_TIMEOUT_PER_MB = 40000;
    }
    async main() {}
    async flashId() {}
    async after() {}
    debug() {}
    info() {}
    timeoutPerMb() { return 3000; }
    async eraseFlash() { io.erases += 1; }
    async _updateImageFlashParams(data) { return data; }
    async flashDeflBegin() { return 1; }
    async flashDeflBlock() { io.writes += 1; }
  }
  Loader.prototype.writeFlash = writeFlash;
  const context = vm.createContext({
    URL,
    Uint8Array,
    window: {},
    location: { toString() { return 'http://127.0.0.1/'; } },
    console: { log() {}, error() {} },
    fetch: async () => {
      io.fetches += 1;
      if (options.readError) {
        return { ok: true, status: 200, arrayBuffer: async () => { throw new Error(options.readError); } };
      }
      return new Response(options.bytes, { status: options.status });
    },
  });
  const imports = new vm.SyntheticModule(['Transport', 'ESPLoader', 'sleep'], function () {
    this.setExport('Transport', IOTransport);
    this.setExport('ESPLoader', Loader);
    this.setExport('sleep', async () => {});
  }, { context });
  const flashModule = new vm.SourceTextModule(flashSource, { context, identifier: 'flash.js' });
  await flashModule.link(async () => imports);
  await flashModule.evaluate();
  const useManifest = options.parts
    ? { name: manifest.name, version: manifest.version, builds: [{ chipFamily: 'ESP32-C3', parts: options.parts }] }
    : manifest;
  await flashModule.namespace.flash(
    (event) => events.push(event),
    { getInfo: () => ({ usbVendorId: 0x303a, usbProductId: 0x1001 }) },
    'http://127.0.0.1/manifest.json',
    useManifest,
    options.eraseFirst === true
  );
  return { events, io, last: events.at(-1) };
}

function assertNotWritten(result) {
  assert.equal(result.last.state, 'error');
  assert.equal(result.io.erases, 0);
  assert.equal(result.io.writes, 0);
  assert.equal(result.io.disconnects, 1);
  assert.equal(result.events.some((event) => event.state === 'finished'), false);
}

test('an empty HTTP 200 fails before erase, including when erase was requested', async () => {
  const kept = await runFlash({ bytes: new Uint8Array(), status: 200, eraseFirst: false });
  assertNotWritten(kept);
  assert.equal(kept.io.fetches, 1);
  assert.ok(kept.last.message.includes(EMPTY_FIRMWARE_MESSAGE));
  const eraseRequested = await runFlash({ bytes: new Uint8Array(), status: 200, eraseFirst: true });
  assertNotWritten(eraseRequested);
  assert.equal(eraseRequested.io.fetches, 1);
  const noParts = await runFlash({ bytes: new Uint8Array(), status: 200, eraseFirst: true, parts: [] });
  assertNotWritten(noParts);
  assert.equal(noParts.io.fetches, 0);
  assert.ok(noParts.last.message.includes(NO_BYTES_MESSAGE));
});

test('the real candidate is written once, with its byte count, and without a second download', async () => {
  const result = await runFlash({ bytes: candidate, status: 200, eraseFirst: false });
  assert.equal(result.last.state, 'finished');
  assert.equal(result.io.erases, 0);
  assert.ok(result.io.writes > 0);
  assert.equal(result.io.fetches, 1);
  assert.equal(result.io.disconnects, 1);
  const complete = result.events.find((event) => event.message === 'Writing complete');
  assert.equal(complete.details.bytesTotal, candidate.length);
  assert.equal(complete.details.bytesWritten, candidate.length);
  assert.equal(complete.details.percentage, 100);
});

test('download and body-read failures release the port, then one explicit retry completes', async () => {
  const missing = await runFlash({ bytes: new Uint8Array(), status: 404, eraseFirst: true });
  assertNotWritten(missing);
  assert.ok(missing.last.message.includes('404'));
  const unread = await runFlash({ bytes: candidate, status: 200, eraseFirst: true, readError: 'body aborted' });
  assertNotWritten(unread);
  assert.ok(unread.last.message.includes('body aborted'));
  const retry = await runFlash({ bytes: candidate, status: 200, eraseFirst: false });
  assert.equal(retry.last.state, 'finished');
  assert.equal(retry.io.writes > 0, true);
  const complete = retry.events.find((event) => event.message === 'Writing complete');
  assert.equal(complete.details.bytesWritten, candidate.length);
});

console.log(JSON.stringify({ patched: changed, simulated: 'serial transport and network only; writeFlash is the installed esptool-js method' }));
