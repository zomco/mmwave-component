import test from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { existsSync, mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir, platform } from 'node:os';
import { delimiter, dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { ProtocolClient } from '../src/protocol/client.js';
import { validateResponse } from '../src/protocol/contract.js';
import { createClock } from '../src/protocol/clock.js';
import { CODE } from '../src/protocol/limits.js';
import { parseBaselineMeter } from '../src/g0/baseline-meter.js';

const root = fileURLToPath(new URL('../..', import.meta.url));
const hostDir = fileURLToPath(new URL('../../docs/reviews/web-console/g0/components/mmwave_host', import.meta.url));
const protocolDir = fileURLToPath(new URL('../../protocol/cpp', import.meta.url));

export function which(name, options = {}) {
  const plat = options.platform || platform();
  const env = options.env || process.env;
  const finder = plat === 'win32' ? 'where.exe' : 'which';
  const run = spawnSync(finder, [name], { encoding: 'utf8', timeout: 5000, windowsHide: true, env });
  if (run.error || run.status !== 0) return null;
  const exists = options.existsSync || existsSync;
  return run.stdout.split(/\r?\n/).map((line) => line.trim()).find((line) => line && exists(line)) || null;
}

export function resolveCompiler(configured, options = {}) {
  const plat = options.platform || platform();
  const exists = options.existsSync || existsSync;
  const findInPath = options.which || ((cmd) => which(cmd, options));

  if (configured !== undefined && configured !== null && configured !== '') {
    const candidate = String(configured).trim();
    if (!candidate) {
      throw new Error('Explicit MWCP_GPP compiler configuration is empty.');
    }
    // 1. Direct path check (absolute or relative)
    if (exists(candidate)) {
      return candidate;
    }
    // If it clearly contains directory separators, it was a specified path that does not exist
    if (candidate.includes('/') || candidate.includes('\\')) {
      throw new Error(`MWCP_GPP compiler path not found: ${candidate}`);
    }
    // 2. Command name in PATH
    const inPath = findInPath(candidate);
    if (inPath) {
      return inPath;
    }
    if (plat === 'win32' && !candidate.toLowerCase().endsWith('.exe')) {
      const inPathExe = findInPath(`${candidate}.exe`);
      if (inPathExe) {
        return inPathExe;
      }
    }
    throw new Error(`MWCP_GPP compiler '${candidate}' not found in PATH or filesystem. Explicit compiler configuration is invalid.`);
  }

  // Auto-discovery via PATH
  const candidates = plat === 'win32' ? ['g++.exe', 'c++.exe', 'g++', 'c++'] : ['g++', 'c++'];
  for (const name of candidates) {
    const found = findInPath(name);
    if (found) return found;
  }
  throw new Error('C++ compiler required. Install g++ and set MWCP_GPP. This test does not skip.');
}

export function findCompiler() {
  return resolveCompiler(process.env.MWCP_GPP);
}

function compileEmitter() {
  const compiler = findCompiler();
  const dir = mkdtempSync(join(tmpdir(), 'mwcp-g0-hello-'));
  const exe = join(dir, platform() === 'win32' ? 'emit.exe' : 'emit');
  const built = spawnSync(compiler, [
    '-std=c++14', '-fno-exceptions', '-fno-rtti', '-Wall', '-Wextra', '-Werror',
    '-static-libgcc', '-static-libstdc++',
    `-I${hostDir}`, `-I${protocolDir}`,
    '-o', exe,
    join(protocolDir, 'g0_hello_emit.cpp'),
    join(protocolDir, 'mwcp_codec.cpp'),
    join(protocolDir, 'mwcp_json.cpp'),
  ], { encoding: 'utf8', timeout: 20000, windowsHide: true });
  if (built.error || built.status !== 0) {
    rmSync(dir, { recursive: true, force: true });
    throw new Error(`compile failed status=${built.status} signal=${built.signal} ${built.stderr || built.stdout || built.error}`);
  }
  return {
    exe,
    cleanup() { rmSync(dir, { recursive: true, force: true }); },
    emit(args) {
      const run = spawnSync(exe, args, {
        encoding: 'utf8',
        timeout: 5000,
        windowsHide: true,
        env: { ...process.env, PATH: `${dirname(compiler)}${delimiter}${process.env.PATH || ''}` },
      });
      if (run.error || run.status !== 0) {
        throw new Error(`emit failed status=${run.status} signal=${run.signal} ${run.stderr || run.stdout || run.error}`);
      }
      return run.stdout.trim().split(/\r?\n/);
    },
  };
}

test('firmware HELLO boot_id is hex32 and completes a ProtocolClient handshake', async () => {
  const built = compileEmitter();
  const emit = (args) => built.emit(args);
  try {
  const zero = emit(['boot', '000000000000', '0', '0', '0']);
  assert.equal(zero[0], '00000000000000000000000000000000');
  const same = emit(['boot', '000000000000', '0', '0', '0']);
  const reboot = emit(['boot', '000000000000', '1', '0', '0']);
  assert.equal(same[0], zero[0]);
  assert.notEqual(reboot[0], zero[0]);
  assert.equal(reboot[0].length, 32);

  const clock = createClock(0);
  let request = null;
  const client = new ProtocolClient({
    async write(bytes) { request = bytes; },
    onData() {},
  }, { clock, helloTimeout: 3000 });
  const nonce = '0123456789abcdef0123456789abcdef';
  const pending = client.hello({ client: { name: 'mmwave-web-console', version: '0.1.0' }, nonce });
  await new Promise((resolve) => setTimeout(resolve, 0));
  const lines = emit(['respond', '00ff00000000', '1', '2', '3', '0', Buffer.from(request).toString('hex')]);
  const boot = lines[0];
  const session = lines[1];
  client.ingest(Buffer.from(lines[2], 'hex'));
  const frame = await pending;
  assert.equal(validateResponse(CODE.HELLO, frame.json), true);
  assert.equal(frame.json.result.boot_id, boot);
  assert.equal(client.bootId, boot);
  assert.equal(boot.length, 32);
  assert.equal(client.sessionId, Number(session));
  const broken = structuredClone(frame.json);
  broken.result.boot_id = boot.slice(0, 24);
  assert.equal(validateResponse(CODE.HELLO, broken), false);

  const ping = client.ping();
  await new Promise((resolve) => setTimeout(resolve, 0));
  client.ingest(Buffer.from(emit(['ping', String(client.sessionId + 1), '2', '1'])[0], 'hex'));
  client.poll();
  assert.equal(client.inflight(), true);
  client.ingest(Buffer.from(emit(['ping', String(client.sessionId), '2', '1'])[0], 'hex'));
  const pong = await ping;
  assert.equal(validateResponse(CODE.PING, pong.json), true);

  const status = emit(['status']);
  const body = JSON.parse(status[0]);
  assert.equal(validateResponse(CODE.STATUS_GET, body), true);
  assert.ok(body.result.unmeasured.includes('config_storage'));
  assert.notEqual(body.result.config_storage, 'healthy');
  assert.equal(body.result.counters.rx_crc_errors, 1);
  assert.equal(body.result.rx_errors.cobs, 4);
  const evidence = JSON.parse(readFileSync(new URL('../../docs/reviews/web-console/g0/stack-unit.json', import.meta.url), 'utf8'));
  assert.equal(evidence.sizeof_stack_type, 1);
  assert.equal(evidence.high_water_unit, 'bytes');
  assert.equal(body.result.stack_high_water_unit, 'bytes');
  assert.equal(body.result.stack_type_bytes, evidence.sizeof_stack_type);
  assert.equal(body.result.stack_high_water_bytes, 600);
  assert.notEqual(body.result.stack_high_water_bytes, 600 * 4);
  assert.equal(body.result.stack_word_bytes, undefined);
  const meter = parseBaselineMeter(status[1]);
  assert.equal(meter.stack_high_water_bytes, 600);
  assert.notEqual(meter.stack_high_water_bytes, 2400);
  assert.equal(meter.last_radar_frame_ms, 9);
  assert.ok(meter.unmeasured.includes('usb_tx'));
  } finally {
    built.cleanup();
  }
});

test('compiler resolution regression matrix: env, command name, spaces, invalid configs, and discovery', () => {
  // 1. Unset env var, PATH discoverable
  const foundDefault = resolveCompiler(undefined, {
    which: (name) => (name.startsWith('g++') ? '/mock/bin/g++' : null),
  });
  assert.equal(foundDefault, '/mock/bin/g++');

  // 2. MWCP_GPP=g++, PATH discoverable (as used by GitHub Actions CI)
  const foundGpp = resolveCompiler('g++', {
    existsSync: () => false,
    which: (name) => (name === 'g++' ? '/usr/bin/g++' : null),
  });
  assert.equal(foundGpp, '/usr/bin/g++');

  // 3. Valid absolute path with spaces
  const pathWithSpaces = 'C:\\Program Files\\LLVM MinGW\\bin\\g++.exe';
  const foundSpaced = resolveCompiler(pathWithSpaces, {
    existsSync: (path) => path === pathWithSpaces,
  });
  assert.equal(foundSpaced, pathWithSpaces);

  // 4. Invalid path (contains separators and does not exist) -> must fail loudly
  assert.throws(
    () => resolveCompiler('/nonexistent/path/to/g++', { existsSync: () => false }),
    /MWCP_GPP compiler path not found/
  );

  // 5. Invalid command name (not in PATH) -> must fail loudly without silently switching
  assert.throws(
    () => resolveCompiler('bad_compiler_name_xyz', { existsSync: () => false, which: () => null }),
    /bad_compiler_name_xyz.*not found in PATH/
  );

  // 6. Explicitly empty configuration -> must fail loudly
  assert.throws(
    () => resolveCompiler('   ', {}),
    /Explicit MWCP_GPP compiler configuration is empty/
  );

  // 7. Compiler unavailable (no env var and not in PATH) -> must not skip
  assert.throws(
    () => resolveCompiler(undefined, { which: () => null }),
    /C\+\+ compiler required.*This test does not skip/
  );
});

