import test from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir, platform } from 'node:os';
import { delimiter, dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { decodeWire } from '../src/protocol/codec.js';
import { telemetryIssue, validateEvent, validateResponse } from '../src/protocol/contract.js';
import { CODE } from '../src/protocol/limits.js';

const root = fileURLToPath(new URL('../..', import.meta.url));

function compiler() {
  if (process.env.MWCP_GPP) return process.env.MWCP_GPP;
  const finder = platform() === 'win32' ? 'where.exe' : 'which';
  const names = platform() === 'win32' ? ['g++.exe', 'g++'] : ['g++'];
  for (const name of names) {
    const run = spawnSync(finder, [name], { encoding: 'utf8', timeout: 5000, windowsHide: true });
    const found = (run.stdout || '').split(/\r?\n/).map((line) => line.trim()).find(Boolean);
    if (run.status === 0 && found) return found;
  }
  throw new Error('C++ compiler required. Set MWCP_GPP. This test does not skip.');
}

const PATCH = join(root, 'patches/esphome-2026.9.1-wifi-scan-ownership.patch');
const GATE_HEADER = 'wifi_scan_ownership.h';

function extractGateHeader(dir) {
  const lines = readFileSync(PATCH, 'utf8').split(/\r?\n/);
  const start = lines.indexOf(`+++ b/esphome/components/wifi/${GATE_HEADER}`);
  assert.notEqual(start, -1, 'the patch must add the scan ownership header');
  const body = [];
  for (let i = start + 1; i < lines.length && !lines[i].startsWith('diff --git'); i++) {
    if (lines[i].startsWith('+')) body.push(lines[i].slice(1));
  }
  assert.ok(body.length > 0, 'the scan ownership header hunk must not be empty');
  writeFileSync(join(dir, GATE_HEADER), `${body.join('\n')}\n`);
}

test('production link output decodes as a schema-valid HELLO response', () => {
  const gpp = compiler();
  const dir = mkdtempSync(join(tmpdir(), 'mwcp-r-'));
  const exe = join(dir, platform() === 'win32' ? 'r.exe' : 'r');
  try {
    extractGateHeader(dir);
    const built = spawnSync(gpp, [
      '-std=c++14', '-fno-exceptions', '-fno-rtti', '-Wall', '-Wextra', '-Werror',
      '-static-libgcc', '-static-libstdc++',
      `-I${join(root, 'components/mmwave_host')}`,
      `-I${join(root, 'protocol/cpp')}`,
      '-o', exe,
      join(root, 'protocol/cpp/mwcp_r_test.cpp'),
      join(root, 'components/mmwave_host/mwcp_service.cpp'),
      join(root, 'protocol/cpp/mwcp_codec.cpp'),
      join(root, 'protocol/cpp/mwcp_json.cpp'),
    ], { encoding: 'utf8', timeout: 30000, windowsHide: true });
    assert.equal(built.status, 0, built.stderr || built.stdout);
    const run = spawnSync(exe, [], {
      encoding: 'utf8',
      timeout: 5000,
      windowsHide: true,
      env: { ...process.env, PATH: `${dirname(gpp)}${delimiter}${process.env.PATH || ''}` },
    });
    assert.equal(run.status, 0, run.stderr || run.stdout);
    assert.match(run.stdout, /mwcp r test passed/);
    const hex = run.stdout.split(/\r?\n/).find((line) => line.startsWith('FRAME '))?.slice(6);
    assert.ok(hex && !/^0+$/.test(hex), 'captured wire is not all zeros');
    const frame = decodeWire(Buffer.from(hex, 'hex'));
    assert.equal(frame.code, CODE.HELLO);
    assert.equal(validateResponse(CODE.HELLO, frame.json), true);
    assert.equal(frame.json.result.boot_id.length, 32);
    const af = join(dir, platform() === 'win32' ? 'af.exe' : 'af');
    const afBuilt = spawnSync(gpp, [
      '-std=c++14', '-fno-exceptions', '-fno-rtti', '-Wall', '-Wextra', '-Werror',
      '-static-libgcc', '-static-libstdc++',
      `-I${join(root, 'components/mmwave_host')}`,
      `-I${join(root, 'protocol/cpp')}`,
      '-o', af,
      join(root, 'protocol/cpp/mwcp_af_test.cpp'),
      join(root, 'components/mmwave_host/mwcp_service.cpp'),
      join(root, 'protocol/cpp/mwcp_codec.cpp'),
      join(root, 'protocol/cpp/mwcp_json.cpp'),
    ], { encoding: 'utf8', timeout: 30000, windowsHide: true });
    assert.equal(afBuilt.status, 0, afBuilt.stderr || afBuilt.stdout);
    const afRun = spawnSync(af, [], {
      encoding: 'utf8',
      timeout: 5000,
      windowsHide: true,
      env: { ...process.env, PATH: `${dirname(gpp)}${delimiter}${process.env.PATH || ''}` },
    });
    assert.equal(afRun.status, 0, afRun.stderr || afRun.stdout);
    assert.match(afRun.stdout, /mwcp af test passed/);
    const closeExe = join(dir, platform() === 'win32' ? 'close.exe' : 'close');
    const closeBuilt = spawnSync(gpp, [
      '-std=c++14', '-fno-exceptions', '-fno-rtti', '-Wall', '-Wextra', '-Werror',
      '-static-libgcc', '-static-libstdc++',
      `-I${join(root, 'components/mmwave_host')}`,
      `-I${join(root, 'protocol/cpp')}`,
      '-o', closeExe,
      join(root, 'protocol/cpp/mwcp_close_test.cpp'),
      join(root, 'components/mmwave_host/mwcp_service.cpp'),
      join(root, 'components/mmwave_host/mwcp_wifi_adapter.cpp'),
      join(root, 'protocol/cpp/mwcp_codec.cpp'),
      join(root, 'protocol/cpp/mwcp_json.cpp'),
    ], { encoding: 'utf8', timeout: 30000, windowsHide: true });
    assert.equal(closeBuilt.status, 0, closeBuilt.stderr || closeBuilt.stdout);
    const closeRun = spawnSync(closeExe, [], {
      encoding: 'utf8',
      timeout: 10000,
      windowsHide: true,
      env: { ...process.env, PATH: `${dirname(gpp)}${delimiter}${process.env.PATH || ''}` },
    });
    assert.equal(closeRun.status, 0, closeRun.stderr || closeRun.stdout);
    assert.match(closeRun.stdout, /mwcp close test passed/);
    const wires = closeRun.stdout.split(/\r?\n/).filter((line) => line.startsWith('WIRE '));
    assert.ok(wires.length >= 4, 'production wire samples missing');
    for (const line of wires) {
      const parts = line.split(' ');
      const frame = decodeWire(Buffer.from(parts[2], 'hex'));
      if (parts[1] === 'event') {
        assert.equal(frame.kind, 3);
        assert.equal(validateEvent(frame.code, frame.json), true, JSON.stringify(frame.json));
        if (frame.code === CODE.TELEMETRY) assert.equal(telemetryIssue(frame.json), null);
      } else {
        assert.equal(frame.kind, 2);
        assert.equal(validateResponse(frame.code, frame.json), true, JSON.stringify(frame.json));
      }
    }
    const scanExe = join(dir, platform() === 'win32' ? 'scan.exe' : 'scan');
    const scanBuilt = spawnSync(gpp, [
      '-std=c++14', '-fno-exceptions', '-fno-rtti', '-Wall', '-Wextra', '-Werror',
      '-static-libgcc', '-static-libstdc++',
      `-I${join(root, 'components/mmwave_host')}`,
      `-I${join(root, 'protocol/cpp')}`,
      `-I${dir}`,
      '-o', scanExe,
      join(root, 'protocol/cpp/mwcp_scan_test.cpp'),
      join(root, 'components/mmwave_host/mwcp_service.cpp'),
      join(root, 'components/mmwave_host/mwcp_wifi_adapter.cpp'),
      join(root, 'protocol/cpp/mwcp_codec.cpp'),
      join(root, 'protocol/cpp/mwcp_json.cpp'),
    ], { encoding: 'utf8', timeout: 30000, windowsHide: true });
    assert.equal(scanBuilt.status, 0, scanBuilt.stderr || scanBuilt.stdout);
    const scanRun = spawnSync(scanExe, [], {
      encoding: 'utf8',
      timeout: 10000,
      windowsHide: true,
      env: { ...process.env, PATH: `${dirname(gpp)}${delimiter}${process.env.PATH || ''}` },
    });
    assert.equal(scanRun.status, 0, scanRun.stderr || scanRun.stdout);
    assert.match(scanRun.stdout, /mwcp scan test passed/);
    const gateExe = join(dir, platform() === 'win32' ? 'gate.exe' : 'gate');
    const gateBuilt = spawnSync(gpp, [
      '-std=c++14', '-fno-exceptions', '-fno-rtti', '-Wall', '-Wextra', '-Werror',
      '-static-libgcc', '-static-libstdc++',
      `-I${dir}`,
      '-o', gateExe,
      join(root, 'protocol/cpp/mwcp_scan_gate_test.cpp'),
    ], { encoding: 'utf8', timeout: 30000, windowsHide: true });
    assert.equal(gateBuilt.status, 0, gateBuilt.stderr || gateBuilt.stdout);
    const gateRun = spawnSync(gateExe, [], {
      encoding: 'utf8',
      timeout: 5000,
      windowsHide: true,
      env: { ...process.env, PATH: `${dirname(gpp)}${delimiter}${process.env.PATH || ''}` },
    });
    assert.equal(gateRun.status, 0, gateRun.stderr || gateRun.stdout);
    assert.match(gateRun.stdout, /mwcp scan gate test passed/);
    const lifecycleExe = join(dir, platform() === 'win32' ? 'lifecycle.exe' : 'lifecycle');
    const lifecycleBuilt = spawnSync(gpp, [
      '-std=c++14', '-fno-exceptions', '-fno-rtti', '-Wall', '-Wextra', '-Werror',
      '-static-libgcc', '-static-libstdc++',
      `-I${join(root, 'components/mmwave_host')}`,
      `-I${join(root, 'protocol/cpp')}`,
      `-I${dir}`,
      '-o', lifecycleExe,
      join(root, 'protocol/cpp/mwcp_scan_lifecycle_test.cpp'),
      join(root, 'components/mmwave_host/mwcp_wifi_adapter.cpp'),
    ], { encoding: 'utf8', timeout: 30000, windowsHide: true });
    assert.equal(lifecycleBuilt.status, 0, lifecycleBuilt.stderr || lifecycleBuilt.stdout);
    const lifecycleRun = spawnSync(lifecycleExe, [], {
      encoding: 'utf8',
      timeout: 5000,
      windowsHide: true,
      env: { ...process.env, PATH: `${dirname(gpp)}${delimiter}${process.env.PATH || ''}` },
    });
    assert.equal(lifecycleRun.status, 0, lifecycleRun.stderr || lifecycleRun.stdout);
    assert.match(lifecycleRun.stdout, /mwcp scan lifecycle test passed/);
    const jobExe = join(dir, platform() === 'win32' ? 'job.exe' : 'job');
    const jobBuilt = spawnSync(gpp, [
      '-std=c++14', '-fno-exceptions', '-fno-rtti', '-Wall', '-Wextra', '-Werror',
      '-static-libgcc', '-static-libstdc++',
      `-I${join(root, 'components/mmwave_host')}`,
      `-I${join(root, 'protocol/cpp')}`,
      '-o', jobExe,
      join(root, 'protocol/cpp/mwcp_job_test.cpp'),
      join(root, 'components/mmwave_host/mwcp_service.cpp'),
      join(root, 'components/mmwave_host/mwcp_wifi_adapter.cpp'),
      join(root, 'protocol/cpp/mwcp_codec.cpp'),
      join(root, 'protocol/cpp/mwcp_json.cpp'),
    ], { encoding: 'utf8', timeout: 30000, windowsHide: true });
    assert.equal(jobBuilt.status, 0, jobBuilt.stderr || jobBuilt.stdout);
    const jobRun = spawnSync(jobExe, [], {
      encoding: 'utf8',
      timeout: 10000,
      windowsHide: true,
      env: { ...process.env, PATH: `${dirname(gpp)}${delimiter}${process.env.PATH || ''}` },
    });
    assert.equal(jobRun.status, 0, jobRun.stderr || jobRun.stdout);
    assert.match(jobRun.stdout, /mwcp job test passed/);
    const pairs = jobRun.stdout.split(/\r?\n/).filter((line) => line.startsWith('JOBPAIR '));
    assert.ok(pairs.length >= 4, 'JOB_CHANGED/JOB_GET wire pairs missing');
    for (const line of pairs) {
      const [, eventHex, responseHex] = line.split(' ');
      const event = decodeWire(Buffer.from(eventHex, 'hex'));
      const response = decodeWire(Buffer.from(responseHex, 'hex'));
      assert.equal(event.kind, 3);
      assert.equal(event.code, CODE.JOB_CHANGED);
      assert.equal(validateEvent(CODE.JOB_CHANGED, event.json), true, JSON.stringify(event.json));
      assert.equal(response.kind, 2);
      assert.equal(response.code, CODE.JOB_GET);
      assert.equal(validateResponse(CODE.JOB_GET, response.json), true, JSON.stringify(response.json));
      const job = response.json.result;
      for (const key of ['job_id', 'op_id', 'action_id', 'state', 'stage', 'progress', 'started_ms', 'finished_ms', 'result', 'error']) {
        assert.deepEqual(event.json[key], job[key], `JOB_CHANGED/JOB_GET differ at ${key}`);
      }
    }
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});
