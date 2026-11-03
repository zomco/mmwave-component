import test from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { createClock } from '../src/protocol/clock.js';
import { validateEvent, validateRequest, validateResponse } from '../src/protocol/contract.js';
import { encodeFrame, FrameParser } from '../src/protocol/codec.js';
import { CODE, ERROR, KIND, MAX_PAYLOAD } from '../src/protocol/limits.js';
import { unsupportedKeywords, validate } from '../src/protocol/schema.js';
import { polygonIssues } from '../src/protocol/geometry.js';
import { link, observation } from '../src/protocol/simulator.js';
import { encodeUtf8 } from '../src/protocol/utf8.js';

const schema = JSON.parse(readFileSync(new URL('../../docs/protocol/schema/mwcp-v1.schema.json', import.meta.url), 'utf8'));
const fixture = JSON.parse(readFileSync(new URL('../../docs/protocol/fixtures/r60abd1-capabilities.json', import.meta.url), 'utf8'));
const uuid = 'd8592ab1-394a-4b1e-89ae-3de15b250015';
const hex32 = '0123456789abcdef0123456789abcdef';

function makeValidConvexPolygon(vertexCount = 64, radiusCm = 1800) {
  const points = [];
  for (let i = 0; i < vertexCount; i++) {
    const angle = (2 * Math.PI * i) / vertexCount;
    const x = Math.round(radiusCm * Math.cos(angle));
    const y = Math.round(radiusCm * Math.sin(angle));
    points.push([x, y]);
  }
  return points;
}

test('schema uses only implemented keywords and validates positive/negative cases for all 24 commands and events', () => {
  assert.deepEqual(unsupportedKeywords(schema), []);
  const codes = Object.keys(schema['x-commands']);
  assert.equal(codes.length, 24);

  const validRequests = {
    [CODE.HELLO]: { client: { name: 'mmwave-web-console', version: '0.1.0' }, nonce: hex32, protocol: { major: 1, minor_max: 0 }, max_payload: 4096 },
    [CODE.PING]: {},
    [CODE.SESSION_CLOSE]: {},
    [CODE.DEVICE_INFO]: {},
    [CODE.CAPABILITIES_LIST]: { cursor: null },
    [CODE.STATUS_GET]: {},
    [CODE.CONFIG_READ]: { cursor: null },
    [CODE.CONFIG_VALIDATE]: { base_revision: '1', changes: { 'install.x_cm': 10 } },
    [CODE.CONFIG_COMMIT]: { base_revision: '1', op_id: uuid, changes: { 'install.x_cm': 10 } },
    [CODE.COMMIT_STATUS]: { op_id: uuid },
    [CODE.SUBSCRIBE]: { streams: [{ id: 'telemetry', max_rate_hz: 5 }], event_budget_bps: 4000 },
    [CODE.UNSUBSCRIBE]: { streams: ['telemetry'] },
    [CODE.ACTIONS_LIST]: { cursor: null },
    [CODE.ACTION_START]: { action_id: 'device.restart', op_id: uuid, params: {}, confirm: 'device.restart' },
    [CODE.JOB_GET]: { job_id: 'job-1' },
    [CODE.WIFI_STATUS]: {},
    [CODE.WIFI_SCAN]: { op_id: uuid },
    [CODE.WIFI_PROVISION]: { op_id: uuid, ssid: 'Lab-2.4G', auth: 'wpa2_psk', password: 'password123' },
    [CODE.WIFI_SCAN_RESULTS]: { job_id: 'job-1', cursor: null },
  };

  const validResults = {
    [CODE.HELLO]: {
      nonce: hex32,
      protocol: { major: 1, minor: 0 },
      boot_id: hex32,
      session_ttl_ms: 15000,
      limits: { max_payload: 4096, rpc_inflight: 1, max_targets: 1, event_budget_bps: 8000 },
      identity: { device_id: 'dev-1', configured_model: 'r60abd1', dimension: '2D', firmware_version: '0.1.0' },
      cap_revision: 'r60-v1',
    },
    [CODE.PING]: { uptime_ms: 1000 },
    [CODE.SESSION_CLOSE]: { closed: true },
    [CODE.DEVICE_INFO]: {
      device_id: 'dev-1',
      boot_id: hex32,
      configured_model: 'r60abd1',
      dimension: '2D',
      firmware_version: '0.1.0',
      git_sha: null,
      release_channel: 'development',
      build_profile: 'baseline',
      host_protocol: 'MWCP/1',
      radar_identity: null,
    },
    [CODE.CAPABILITIES_LIST]: { revision: 'r60-v1', items: [fixture.capabilities[0]], next_cursor: null },
    [CODE.STATUS_GET]: {
      uptime_ms: 1000,
      radar_link: 'healthy',
      last_radar_frame_ms: 950,
      config_revision: '1',
      config_storage: 'healthy',
      active_jobs: [],
      counters: {
        rx_frames: 1,
        rx_crc_errors: 0,
        rx_oversize: 0,
        invalid_requests: 0,
        radar_frames: 10,
        radar_errors: 0,
        telemetry_coalesced: 0,
        logs_dropped: 0,
        tx_overflow: 0,
      },
    },
    [CODE.CONFIG_READ]: { revision: '1', items: [{ key: 'install.x_cm', value: 0 }], next_cursor: null },
    [CODE.CONFIG_VALIDATE]: { valid: true, base_revision: '1', restart_required: false },
    [CODE.CONFIG_COMMIT]: { op_id: uuid, revision: '2', persisted: true, restart_required: false },
    [CODE.COMMIT_STATUS]: { found: true, revision: '2', current_revision: '2' },
    [CODE.SUBSCRIBE]: { streams: [{ id: 'telemetry', max_rate_hz: 5 }], event_budget_bps: 4000 },
    [CODE.UNSUBSCRIBE]: { removed: ['telemetry'] },
    [CODE.ACTIONS_LIST]: {
      revision: 'actions-1',
      items: [{ action_id: 'device.restart', verification: 'none', confirm: true, resource: 'restart', deadline_ms: 8000 }],
      next_cursor: null,
    },
    [CODE.ACTION_START]: { job_id: 'job-1' },
    [CODE.JOB_GET]: {
      job_id: 'job-1',
      op_id: uuid,
      action_id: 'radar.reset_module',
      state: 'running',
      stage: 'resetting',
      progress: null,
      started_ms: 100,
      finished_ms: null,
      result: null,
      error: null,
    },
    [CODE.WIFI_STATUS]: { state: 'disconnected', ssid: null, ip: null, rssi_dbm: null, last_error: null },
    [CODE.WIFI_SCAN]: { job_id: 'job-2' },
    [CODE.WIFI_PROVISION]: { job_id: 'job-3' },
    [CODE.WIFI_SCAN_RESULTS]: { items: [{ ssid: 'Lab-2.4G', rssi_dbm: -45, auth: 'wpa2_psk', hidden: false }], next_cursor: null, truncated: false },
  };

  const validEvents = {
    [CODE.TELEMETRY]: observation('zero'),
    [CODE.STATUS_CHANGED]: validResults[CODE.STATUS_GET],
    [CODE.CONFIG_CHANGED]: { revision: '2', changed_keys: ['install.x_cm'], origin: 'web', op_id: uuid },
    [CODE.JOB_CHANGED]: validResults[CODE.JOB_GET],
    [CODE.LOG]: { sample_ms: 100, level: 'info', source: 'host', message: 'ready', dropped_before: 0 },
  };

  for (const codeStr of codes) {
    const code = Number(codeStr);
    const command = schema['x-commands'][codeStr];
    assert.equal(Boolean(command.request || command.event), true, command.name);
    if (command.request) {
      assert.equal(validateRequest(code, validRequests[code]).ok, true, `${command.name} valid request`);
      assert.equal(validateRequest(code, { ...validRequests[code], unknown_request_field: 1 }).ok, false, `${command.name} rejects unknown request field`);
      assert.equal(validateResponse(code, { ok: true, result: validResults[code] }), true, `${command.name} valid response`);
      assert.equal(validateResponse(code, { ok: true, result: { ...validResults[code], future_minor_field: true } }), true, `${command.name} open response object`);
      assert.equal(validateResponse(code, { ok: true, result: { invalid_result_shape: true } }), false, `${command.name} rejects invalid result shape`);
      assert.equal(validateResponse(code, { ok: false, error: { code: ERROR.INVALID_ARGUMENT, message: 'bad input' } }), true, `${command.name} valid error envelope`);
      assert.equal(validateResponse(code, { ok: false, error: { code: 'NOT_AN_ERROR_CODE', message: 'bad' } }), false, `${command.name} rejects unknown error code`);
    } else if (command.event) {
      assert.equal(validateEvent(code, validEvents[code]), true, `${command.name} valid event`);
      assert.equal(validateEvent(code, { ...validEvents[code], future_minor_field: 1 }), true, `${command.name} open event object`);
      assert.equal(validateEvent(code, { invalid_event_shape: true }), false, `${command.name} rejects invalid event shape`);
    }
  }

  // Test x-maxUtf8Bytes with multibyte UTF-8 characters (11 Chinese chars = 33 UTF-8 bytes > 32 limit)
  const multibyteSsid = '雷达测试网络名称超长一';
  assert.equal(multibyteSsid.length, 11);
  assert.equal(encodeUtf8(multibyteSsid).length, 33);
  assert.equal(validateRequest(CODE.WIFI_PROVISION, { op_id: uuid, ssid: multibyteSsid, auth: 'open', password: '' }).ok, false);
});

test('R60 fixture fields come from source and do not invent speed or 3D', () => {
  assert.equal(fixture.origin, 'simulation');
  assert.equal(fixture.evidence.hardware_measured, false);
  for (const item of fixture.capabilities) assert.equal(validate(schema.$defs.capability, item, schema).ok, true, item.id);
  const posXy = fixture.capabilities.find((item) => item.id === 'position.xy');
  assert.equal(posXy.expected_interval_ms, 2000);
  assert.equal(posXy.stale_after_ms, 6000);
  const installZ = fixture.capabilities.find((item) => item.id === 'install.z_cm');
  assert.equal(installZ.minimum, 50);
  assert.equal(installZ.maximum, 600);
  assert.equal(fixture.capabilities.find((item) => item.id === 'speed.cm_s').supported, false);
  assert.equal(fixture.capabilities.find((item) => item.id === 'position.z'), undefined);
  assert.equal(fixture.identity.dimension, '2D');
  assert.equal(fixture.unsupported.includes('inject_mock_data'), true);
  assert.equal(validate(schema.$defs.error, { code: 'AUTH_REQUIRED', message: 'no' }, schema).ok, false);
});

test('observations, semantically valid 64-vertex R60 max config, and 4096/4097 byte boundaries pass contract checks', async () => {
  for (const kind of ['empty', 'unknown', 'zero', '1d', 'multi']) {
    const result = validate(schema.$defs.telemetry, observation(kind), schema);
    assert.equal(result.ok, true, `${kind} ${JSON.stringify(result.errors)}`);
  }
  assert.deepEqual(polygonIssues([[0, 0], [1, 0], [0, 1]]), []);
  assert.ok(polygonIssues([[0, 0], [1, 1], [0, 1], [1, 0]]).includes('self_intersection'));
  assert.ok(polygonIssues(Array.from({ length: 64 }, () => [-2000, -2000])).includes('duplicate'));

  const points = makeValidConvexPolygon(64, 1800);
  assert.equal(points.length, 64);
  assert.deepEqual(polygonIssues(points), []);
  assert.ok(polygonIssues([[0, 0], [10, 0], [20, 0]]).includes('zero_area'));

  const area12 = makeValidConvexPolygon(12, 800);
  const maxR60Changes = {
    'install.x_cm': -2000,
    'install.y_cm': 2000,
    'install.z_cm': 600,
    'install.yaw_deg': -180,
    'install.pitch_deg': -90,
    'install.roll_deg': 90,
    'geometry.boundary_cm': points,
    'areas.definitions': [
      { slot: 0, enabled: true, name: '区域一-最大字节长度A', points_cm: area12 },
      { slot: 1, enabled: true, name: '区域二-最大字节长度B', points_cm: area12 },
      { slot: 2, enabled: true, name: '区域三-最大字节长度C', points_cm: area12 },
    ],
  };
  const commitReq = { base_revision: '1', op_id: uuid, changes: maxR60Changes };
  assert.equal(validateRequest(CODE.CONFIG_COMMIT, commitReq).ok, true);
  const body = JSON.stringify(commitReq);
  assert.ok(encodeUtf8(body).length < MAX_PAYLOAD, `max R60 config bytes=${encodeUtf8(body).length}`);

  const clock = createClock(1000);
  const { client } = link(clock, { profile: 'r60' });
  await client.hello({ client: { name: 'mmwave-web-console', version: '0.1.0' }, nonce: hex32 });
  const committed = await client.request(CODE.CONFIG_COMMIT, commitReq);
  assert.equal(committed.json.ok, true);
  assert.equal(committed.json.result.persisted, true);

  const overZ = await client.request(CODE.CONFIG_VALIDATE, { base_revision: committed.json.result.revision, changes: { 'install.z_cm': 601 } });
  assert.equal(overZ.json.ok, false);
  assert.equal(overZ.json.error.code, 'OUT_OF_RANGE');

  // Exact 4096-byte and 4097-byte payload boundary checks (C-13)
  const prefix = '{"base_revision":"1","op_id":"d8592ab1-394a-4b1e-89ae-3de15b250015","changes":{"pad":"';
  const suffix = '"}}';
  const exact4096 = encodeUtf8(prefix + 'a'.repeat(MAX_PAYLOAD - prefix.length - suffix.length) + suffix);
  assert.equal(exact4096.length, MAX_PAYLOAD);
  const encoded4096 = encodeFrame({ kind: KIND.request, sessionId: 1, requestId: 9, code: CODE.CONFIG_COMMIT, wireSeq: 9, payload: exact4096 });
  assert.equal(encoded4096.ok, true);
  const parsed4096 = new FrameParser().push(encoded4096.wire);
  assert.equal(parsed4096.frames.length, 1);
  assert.equal(parsed4096.frames[0].payload.length, MAX_PAYLOAD);

  const over4097 = encodeUtf8(prefix + 'a'.repeat(MAX_PAYLOAD + 1 - prefix.length - suffix.length) + suffix);
  assert.equal(over4097.length, MAX_PAYLOAD + 1);
  const encoded4097 = encodeFrame({ kind: KIND.request, sessionId: 1, requestId: 10, code: CODE.CONFIG_COMMIT, wireSeq: 10, payload: over4097 });
  assert.equal(encoded4097.ok, false);
  assert.equal(encoded4097.error, 'payload_too_large');

  // Legacy 254-byte serialized boundary string limitation demonstration (DD-04)
  let legacy = '';
  let stored = 0;
  for (const point of points) {
    const next = legacy ? `${legacy};${point[0]},${point[1]}` : `${point[0]},${point[1]}`;
    if (encodeUtf8(next).length > 254) break;
    legacy = next;
    stored++;
  }
  assert.ok(stored < 64);
  assert.ok(stored >= 3);
});

test('async actions, job lifecycle, reboot recovery and Wi-Fi flows follow contract semantics (A-01..A-03, W-01..W-04)', async () => {
  const clock = createClock(1000);
  const { client, device } = link(clock, { profile: 'r60' });
  await client.hello({ client: { name: 'mmwave-web-console', version: '0.1.0' }, nonce: hex32 });
  await client.subscribe([{ id: 'jobs', max_rate_hz: 0 }, { id: 'config', max_rate_hz: 0 }], 8000);

  // A-01: destructive action without exact action_id confirm rejected; duplicate op_id idempotent; conflicting resource returns BUSY
  const actionsPage = await client.request(CODE.ACTIONS_LIST, { cursor: null });
  assert.equal(actionsPage.json.ok, true);
  assert.equal(actionsPage.json.result.items.length, 2);

  const unconfirmed = await client.request(CODE.ACTION_START, {
    action_id: 'radar.reset_module',
    op_id: '11111111-1111-4111-8111-111111111111',
    params: {},
    confirm: null,
  });
  assert.equal(unconfirmed.json.ok, false);
  assert.equal(unconfirmed.json.error.code, ERROR.INVALID_ARGUMENT);

  const resetOp = '22222222-2222-4222-8222-222222222222';
  const started = await client.request(CODE.ACTION_START, {
    action_id: 'radar.reset_module',
    op_id: resetOp,
    params: {},
    confirm: 'radar.reset_module',
  });
  assert.equal(started.json.ok, true);
  const jobId = started.json.result.job_id;

  const duplicate = await client.request(CODE.ACTION_START, {
    action_id: 'radar.reset_module',
    op_id: resetOp,
    params: {},
    confirm: 'radar.reset_module',
  });
  assert.equal(duplicate.json.ok, true);
  assert.equal(duplicate.json.result.job_id, jobId);

  const busy = await client.request(CODE.ACTION_START, {
    action_id: 'radar.reset_module',
    op_id: '33333333-3333-4333-8333-333333333333',
    params: {},
    confirm: 'radar.reset_module',
  });
  assert.equal(busy.json.ok, false);
  assert.equal(busy.json.error.code, ERROR.BUSY);

  // A-02: JOB_GET by job_id and op_id + state transitions via JOB_CHANGED
  device.advanceJob(jobId, 'running', { stage: 'resetting' });
  const runningJob = await client.request(CODE.JOB_GET, { op_id: resetOp });
  assert.equal(runningJob.json.ok, true);
  assert.equal(runningJob.json.result.state, 'running');
  device.advanceJob(jobId, 'succeeded', { stage: 'done' });
  const doneJob = await client.request(CODE.JOB_GET, { job_id: jobId });
  assert.equal(doneJob.json.result.state, 'succeeded');
  assert.deepEqual(doneJob.json.result.result, { verified: false, verification: 'none' });
  assert.ok(doneJob.json.result.finished_ms >= doneJob.json.result.started_ms);

  clock.advance(1000);

  // W-01..W-04: Wi-Fi status, scan, paginated RSSI-ordered scan results, provision & busy protection
  const wifi0 = await client.request(CODE.WIFI_STATUS, {});
  assert.equal(wifi0.json.result.state, 'disconnected');

  const scanOp = '44444444-4444-4444-8444-444444444444';
  const scanStart = await client.request(CODE.WIFI_SCAN, { op_id: scanOp });
  assert.equal(scanStart.json.ok, true);
  const scanJobId = scanStart.json.result.job_id;
  device.advanceJob(scanJobId, 'succeeded', { stage: 'done' });

  const scanPage1 = await client.request(CODE.WIFI_SCAN_RESULTS, { job_id: scanJobId, cursor: null });
  assert.equal(scanPage1.json.ok, true);
  assert.equal(scanPage1.json.result.items.length, 2);
  assert.ok(scanPage1.json.result.items[0].rssi_dbm >= scanPage1.json.result.items[1].rssi_dbm);
  assert.ok(scanPage1.json.result.next_cursor);
  const scanPage2 = await client.request(CODE.WIFI_SCAN_RESULTS, { job_id: scanJobId, cursor: scanPage1.json.result.next_cursor });
  assert.equal(scanPage2.json.ok, true);
  assert.equal(scanPage2.json.result.items.length, 1);
  assert.equal(scanPage2.json.result.next_cursor, null);

  const provOp = '55555555-5555-4555-8555-555555555555';
  const secretPass = 'superSecretPass99';
  const provStart = await client.request(CODE.WIFI_PROVISION, {
    op_id: provOp,
    ssid: 'Lab-2.4G',
    auth: 'wpa2_psk',
    password: secretPass,
  });
  assert.equal(provStart.json.ok, true);
  assert.equal(JSON.stringify(provStart.json).includes(secretPass), false);

  // W-03: WIFI_SCAN while provision is active returns BUSY
  const scanWhileBusy = await client.request(CODE.WIFI_SCAN, { op_id: '66666666-6666-4666-8666-666666666666' });
  assert.equal(scanWhileBusy.json.ok, false);
  assert.equal(scanWhileBusy.json.error.code, ERROR.BUSY);

  clock.advance(1000);

  device.advanceJob(provStart.json.result.job_id, 'succeeded', { stage: 'connected', result: { ip: '192.168.1.88' } });
  const wifiConnected = await client.request(CODE.WIFI_STATUS, {});
  assert.equal(wifiConnected.json.result.state, 'connected');
  assert.equal(wifiConnected.json.result.ssid, 'Lab-2.4G');
  assert.equal(wifiConnected.json.result.ip, '192.168.1.88');
  assert.equal(JSON.stringify(client.events).includes(secretPass), false);

  // A-03: device.restart (verification: 'none') never reports fake succeeded before reboot, and old job_id is 'unknown' after boot_id change
  const restartOp = '88888888-8888-4888-8888-888888888888';
  const restartStart = await client.request(CODE.ACTION_START, {
    action_id: 'device.restart',
    op_id: restartOp,
    params: {},
    confirm: 'device.restart',
  });
  assert.equal(restartStart.json.ok, true);
  const restartJobId = restartStart.json.result.job_id;
  assert.throws(() => device.advanceJob(restartJobId, 'succeeded'), /verification:none/);

  const oldBootId = device.bootId;
  device.reboot('abcdef0123456789abcdef0123456789');
  const rehello = await client.hello({ client: { name: 'mmwave-web-console', version: '0.1.0' }, nonce: hex32 });
  assert.notEqual(rehello.json.result.boot_id, oldBootId);
  const afterRebootJob = await client.request(CODE.JOB_GET, { job_id: restartJobId });
  assert.equal(afterRebootJob.json.result.state, 'unknown');
});

test('G1-R1 regression: R60 capabilities/config/actions match fixture and confirm requires exact action_id string', async () => {
  const clock = createClock(1000);
  const { client, device } = link(clock, { profile: 'r60' });
  await client.hello({ client: { name: 'mmwave-web-console', version: '0.1.0' }, nonce: hex32 });

  const areasFixtureCap = fixture.capabilities.find((item) => item.id === 'areas.definitions');
  assert.ok(areasFixtureCap);
  assert.equal(areasFixtureCap.type, 'array');
  assert.equal(areasFixtureCap.schema_id, 'r60.areas.v1');
  assert.equal(areasFixtureCap.min_items, 0);
  assert.equal(areasFixtureCap.max_items, 3);

  assert.deepEqual(
    device.capabilities.map((item) => item.id),
    fixture.capabilities.map((item) => item.id),
  );

  // Full paginated CAPABILITIES_LIST
  const capItems = [];
  let cursor = null;
  do {
    const p = client.request(CODE.CAPABILITIES_LIST, { cursor });
    if (client.inflight()) clock.advance(1000);
    const res = await p;
    assert.equal(res.json.ok, true);
    capItems.push(...res.json.result.items);
    cursor = res.json.result.next_cursor;
    clock.advance(200);
  } while (cursor);
  assert.equal(client.rejected, 0);
  assert.deepEqual(capItems, fixture.capabilities);

  // Full paginated CONFIG_READ
  const cfgItems = [];
  cursor = null;
  do {
    const res = await client.request(CODE.CONFIG_READ, { cursor });
    assert.equal(res.json.ok, true);
    cfgItems.push(...res.json.result.items);
    cursor = res.json.result.next_cursor;
    clock.advance(200);
  } while (cursor);
  const expectedConfigKeys = fixture.capabilities.filter((item) => item.kind === 'config').map((item) => item.id);
  assert.deepEqual(
    cfgItems.map((item) => item.key),
    expectedConfigKeys,
  );

  // Full paginated ACTIONS_LIST
  const actItems = [];
  cursor = null;
  do {
    const res = await client.request(CODE.ACTIONS_LIST, { cursor });
    assert.equal(res.json.ok, true);
    actItems.push(...res.json.result.items);
    cursor = res.json.result.next_cursor;
    clock.advance(200);
  } while (cursor);
  assert.deepEqual(actItems, fixture.actions);

  // confirm semantics: missing, null, false, true, wrong string all rejected; exact action_id accepted
  assert.equal(validateRequest(CODE.ACTION_START, { action_id: 'radar.reset_module', op_id: uuid, params: {} }).ok, false);
  assert.equal(validateRequest(CODE.ACTION_START, { action_id: 'radar.reset_module', op_id: uuid, params: {}, confirm: false }).ok, false);
  assert.equal(validateRequest(CODE.ACTION_START, { action_id: 'radar.reset_module', op_id: uuid, params: {}, confirm: true }).ok, false);
  assert.equal(validateRequest(CODE.ACTION_START, { action_id: 'radar.reset_module', op_id: uuid, params: {}, confirm: 'radar.reset_module' }).ok, true);

  for (const [idx, badConfirm] of [null, false, true, 'device.restart'].entries()) {
    clock.advance(200);
    const res = await client.request(CODE.ACTION_START, {
      action_id: 'radar.reset_module',
      op_id: `a0000000-0000-4000-8000-00000000000${idx}`,
      params: {},
      confirm: badConfirm,
    });
    assert.equal(res.json.ok, false, `confirm=${JSON.stringify(badConfirm)} must be rejected`);
    assert.equal(res.json.error.code, ERROR.INVALID_ARGUMENT);
  }
});

test('G1-R2 regression: active job is never evicted by completed jobs and preserves resource lock', async () => {
  const clock = createClock(1000);
  const { client, device } = link(clock, { profile: 'r60' });
  await client.hello({ client: { name: 'mmwave-web-console', version: '0.1.0' }, nonce: hex32 });

  const activeRadarOp = 'b0000000-0000-4000-8000-000000000001';
  const startedRadar = await client.request(CODE.ACTION_START, {
    action_id: 'radar.reset_module',
    op_id: activeRadarOp,
    params: {},
    confirm: 'radar.reset_module',
  });
  assert.equal(startedRadar.json.ok, true);
  const activeRadarJobId = startedRadar.json.result.job_id;
  device.advanceJob(activeRadarJobId, 'running', { stage: 'resetting' });

  // With 1 active radar job, 7 completed scans can be accepted (1 active + 7 completed = 8 slots reserved)
  for (let i = 0; i < 7; i++) {
    clock.advance(1000);
    const scanOp = `b1000000-0000-4000-8000-00000000000${i}`;
    const scanRes = await client.request(CODE.WIFI_SCAN, { op_id: scanOp });
    assert.equal(scanRes.json.ok, true);
    device.advanceJob(scanRes.json.result.job_id, 'succeeded', { stage: 'done' });
  }

  // Attempting an 8th scan while activeRadar is still running would exceed capacity (1 active + 7 completed + 1 new = 9 > 8)
  clock.advance(1000);
  const initialWifiState = device.wifi.state;
  const overflowScanRes = await client.request(CODE.WIFI_SCAN, { op_id: 'b1000000-0000-4000-8000-000000000007' });
  assert.equal(overflowScanRes.json.ok, false);
  assert.equal(overflowScanRes.json.error.code, ERROR.BUSY);
  assert.equal(device.wifi.state, initialWifiState, 'capacity rejection must not mutate wifi.state');

  clock.advance(1000);
  const statusWhileActive = await client.request(CODE.STATUS_GET, {});
  assert.equal(statusWhileActive.json.ok, true);
  assert.ok(statusWhileActive.json.result.active_jobs.includes(activeRadarJobId), 'active job must remain in STATUS_GET.active_jobs');

  const jobWhileActive = await client.request(CODE.JOB_GET, { job_id: activeRadarJobId });
  assert.equal(jobWhileActive.json.ok, true);
  assert.equal(jobWhileActive.json.result.state, 'running', 'active job must not become unknown');

  const conflictRadar = await client.request(CODE.ACTION_START, {
    action_id: 'radar.reset_module',
    op_id: 'b2000000-0000-4000-8000-000000000002',
    params: {},
    confirm: 'radar.reset_module',
  });
  assert.equal(conflictRadar.json.ok, false);
  assert.equal(conflictRadar.json.error.code, ERROR.BUSY);
  assert.equal(conflictRadar.json.error.details.active_job_id, activeRadarJobId);

  // Now advance activeRadar to succeeded -> total completed jobs reaches 8 (7 scans + 1 radar)
  const completedRadar = device.advanceJob(activeRadarJobId, 'succeeded', { stage: 'done' });
  assert.equal(completedRadar.state, 'succeeded');
  assert.deepEqual(completedRadar.result, { verified: false, verification: 'none' });

  // Radar task completed after 7 wifi scans must NOT be evicted
  const queryById = await client.request(CODE.JOB_GET, { job_id: activeRadarJobId });
  assert.equal(queryById.json.ok, true);
  assert.equal(queryById.json.result.state, 'succeeded', 'newly completed job must NOT be evicted');

  const queryByOp = await client.request(CODE.JOB_GET, { op_id: activeRadarOp });
  assert.equal(queryByOp.json.ok, true);
  assert.equal(queryByOp.json.result.job_id, activeRadarJobId);
  assert.equal(queryByOp.json.result.state, 'succeeded');

  // Idempotency: same op_id and same payload must return original job_id without re-execution even when capacity is full
  const duplicateStart = await client.request(CODE.ACTION_START, {
    action_id: 'radar.reset_module',
    op_id: activeRadarOp,
    params: {},
    confirm: 'radar.reset_module',
  });
  assert.equal(duplicateStart.json.ok, true);
  assert.equal(duplicateStart.json.result.job_id, activeRadarJobId);

  // Idempotency: same op_id with different payload must return OP_ID_REUSE even when capacity is full
  const conflictOpStart = await client.request(CODE.ACTION_START, {
    action_id: 'radar.reset_module',
    op_id: activeRadarOp,
    params: { altered: true },
    confirm: 'radar.reset_module',
  });
  assert.equal(conflictOpStart.json.ok, false);
  assert.equal(conflictOpStart.json.error.code, ERROR.OP_ID_REUSE);
});

test('G1-R2-A regression: completed jobs FIFO by completion order, 5-minute retention window, failed jobs and session reconnection', async () => {
  const clock = createClock(1000);
  const { client, device } = link(clock, { profile: 'r60' });
  await client.hello({ client: { name: 'mmwave-web-console', version: '0.1.0' }, nonce: hex32 });

  // Start job-A (finishes 2nd) and job-B (finishes 1st)
  const opA = 'a1000000-0000-4000-8000-000000000001';
  const opB = 'b1000000-0000-4000-8000-000000000002';
  const startA = await client.request(CODE.ACTION_START, {
    action_id: 'radar.reset_module',
    op_id: opA,
    params: {},
    confirm: 'radar.reset_module',
  });
  assert.equal(startA.json.ok, true);
  const jobA = startA.json.result.job_id;

  const startB = await client.request(CODE.WIFI_SCAN, { op_id: opB });
  assert.equal(startB.json.ok, true);
  const jobB = startB.json.result.job_id;

  // Complete jobB first, then jobA (after 5s delay so jobA retention outlasts jobB)
  clock.advance(1000);
  device.advanceJob(jobB, 'succeeded', { stage: 'done' });
  const jobBRecord = device.completedJobs.find((j) => j.job_id === jobB);
  const jobBFinishedMs = jobBRecord.finished_ms;

  clock.advance(5000);
  device.advanceJob(jobA, 'failed', { error: { code: 'RADAR_TIMEOUT', message: 'UART timeout' } });

  // Duplicate advanceJob call on already completed job must be a no-op and NOT duplicate slot
  const beforeLen = device.completedJobs.length;
  device.advanceJob(jobA, 'failed', { error: { code: 'RADAR_TIMEOUT', message: 'duplicate call' } });
  assert.equal(device.completedJobs.length, beforeLen, 'duplicate completion callback must not occupy additional slot');

  // Verify failed job retains its error and state
  const queryFailedA = await client.request(CODE.JOB_GET, { job_id: jobA });
  assert.equal(queryFailedA.json.result.state, 'failed');
  assert.equal(queryFailedA.json.result.error.code, 'RADAR_TIMEOUT');

  // Verify idempotency on failed job
  const retryFailedA = await client.request(CODE.ACTION_START, {
    action_id: 'radar.reset_module',
    op_id: opA,
    params: {},
    confirm: 'radar.reset_module',
  });
  assert.equal(retryFailedA.json.ok, true);
  assert.equal(retryFailedA.json.result.job_id, jobA);

  // New session (reconnect) within same boot retains idempotency and completed jobs
  const nonce2 = '00000000000000000000000000000002';
  await client.hello({ client: { name: 'mmwave-web-console', version: '0.1.0' }, nonce: nonce2 });
  const queryAAfterReconnect = await client.request(CODE.JOB_GET, { job_id: jobA });
  assert.equal(queryAAfterReconnect.json.result.state, 'failed');

  // Fill completed queue to capacity (8 items) with 6 more wifi scans (2 + 6 = 8)
  const allOps = [opB, opA];
  const allJobIds = [jobB, jobA];
  for (let i = 0; i < 6; i++) {
    clock.advance(1000);
    const op = `c1000000-0000-4000-8000-00000000000${i}`;
    const res = await client.request(CODE.WIFI_SCAN, { op_id: op });
    assert.equal(res.json.ok, true);
    allOps.push(op);
    allJobIds.push(res.json.result.job_id);
    device.advanceJob(res.json.result.job_id, 'succeeded', { stage: 'done' });
  }

  assert.equal(device.completedJobs.length, 8, 'completedJobs must have exactly 8 items');
  assert.equal(device.activeJobs.size, 0, 'activeJobs must be empty');

  // Full capacity verification: ALL 8 records must be queryable by job_id AND by op_id
  for (let i = 0; i < 8; i++) {
    clock.advance(1000);
    const qId = await client.request(CODE.JOB_GET, { job_id: allJobIds[i] });
    assert.equal(qId.json.ok, true, `job_id query ${allJobIds[i]}`);
    assert.notEqual(qId.json.result.state, 'unknown', `job_id query ${allJobIds[i]} must not be unknown`);

    const qOp = await client.request(CODE.JOB_GET, { op_id: allOps[i] });
    assert.equal(qOp.json.ok, true, `op_id query ${allOps[i]}`);
    assert.equal(qOp.json.result.job_id, allJobIds[i], `op_id query ${allOps[i]} must match job_id`);
  }

  // Under full capacity:
  // 1. Existing op_id with same payload still returns existing job_id without side-effects
  clock.advance(1000);
  const retrySameB = await client.request(CODE.WIFI_SCAN, { op_id: opB });
  assert.equal(retrySameB.json.ok, true);
  assert.equal(retrySameB.json.result.job_id, jobB);

  // 2. Existing op_id with different payload returns OP_ID_REUSE
  clock.advance(1000);
  const retryDiffB = await client.request(CODE.ACTION_START, {
    action_id: 'radar.reset_module',
    op_id: opB,
    params: {},
    confirm: 'radar.reset_module',
  });
  assert.equal(retryDiffB.json.ok, false);
  assert.equal(retryDiffB.json.error.code, ERROR.OP_ID_REUSE);

  // 3. New op_id on ACTION_START, WIFI_SCAN, and WIFI_PROVISION must be rejected with BUSY before any side-effects
  const preWifiState = device.wifi.state;
  const preWifiSsid = device.wifi.ssid;

  clock.advance(1000);
  const newActionReject = await client.request(CODE.ACTION_START, {
    action_id: 'radar.reset_module',
    op_id: 'e0000000-0000-4000-8000-000000000001',
    params: {},
    confirm: 'radar.reset_module',
  });
  assert.equal(newActionReject.json.ok, false);
  assert.equal(newActionReject.json.error.code, ERROR.BUSY);
  assert.equal(newActionReject.json.error.details?.reason, 'capacity');

  const newScanReject = await client.request(CODE.WIFI_SCAN, {
    op_id: 'e0000000-0000-4000-8000-000000000002',
  });
  assert.equal(newScanReject.json.ok, false);
  assert.equal(newScanReject.json.error.code, ERROR.BUSY);
  assert.equal(newScanReject.json.error.details?.reason, 'capacity');
  assert.equal(device.wifi.state, preWifiState, 'wifi.state must not mutate on capacity rejection');

  const newProvReject = await client.request(CODE.WIFI_PROVISION, {
    op_id: 'e0000000-0000-4000-8000-000000000003',
    ssid: 'TestNetwork',
    auth: 'wpa2_psk',
    password: 'password123',
  });
  assert.equal(newProvReject.json.ok, false);
  assert.equal(newProvReject.json.error.code, ERROR.BUSY);
  assert.equal(newProvReject.json.error.details?.reason, 'capacity');
  assert.equal(device.wifi.state, preWifiState, 'wifi.state must not mutate on provision rejection');
  assert.equal(device.wifi.ssid, preWifiSsid, 'wifi.ssid must not mutate on provision rejection');

  // Verify memory strictly bounded
  assert.equal(device.completedJobs.length, 8);
  assert.equal(device.activeJobs.size, 0);

  // 5-minute boundary: advance clock to exactly 299,999 ms from jobB completion
  const currentDeviceTime = device.uptime + clock.now();
  const targetDeviceTime299999 = jobBFinishedMs + 299999;
  clock.advance(targetDeviceTime299999 - currentDeviceTime);

  // Re-establish session to refresh session window
  const nonce3 = '00000000000000000000000000000003';
  await client.hello({ client: { name: 'mmwave-web-console', version: '0.1.0' }, nonce: nonce3 });

  // At 299,999 ms from jobB completion: jobB (the earliest completed job) is STILL protected
  const qJobB299k = await client.request(CODE.JOB_GET, { job_id: jobB });
  assert.equal(qJobB299k.json.ok, true);
  assert.notEqual(qJobB299k.json.result.state, 'unknown', 'jobB must remain protected at 299999ms');

  // Attempting new task at 299,999 ms is STILL rejected with BUSY
  const stillBusyRes = await client.request(CODE.WIFI_SCAN, { op_id: 'e0000000-0000-4000-8000-000000000004' });
  assert.equal(stillBusyRes.json.ok, false);
  assert.equal(stillBusyRes.json.error.code, ERROR.BUSY);

  // Advance 1001 ms -> past 300,000 ms from jobB completion (and past 1000ms RPC rate-limiting window)
  clock.advance(1001);

  // Now jobB is expired! Capacity freed: new job CAN be admitted!
  const admittedRes = await client.request(CODE.WIFI_SCAN, { op_id: 'e0000000-0000-4000-8000-000000000005' });
  assert.equal(admittedRes.json.ok, true, 'new job must be admitted once an expired job is reclaimed');
  const newJobId = admittedRes.json.result.job_id;
  device.advanceJob(newJobId, 'succeeded', { stage: 'done' });

  // Expired jobB is now unknown
  clock.advance(1000);
  const queryBExpired = await client.request(CODE.JOB_GET, { job_id: jobB });
  assert.equal(queryBExpired.json.result.state, 'unknown', 'jobB must be unknown after expiring beyond 300000ms');

  // jobA finished 5s later so it remains protected (within 300000ms)
  const queryAStillPresent = await client.request(CODE.JOB_GET, { job_id: jobA });
  assert.equal(queryAStillPresent.json.result.state, 'failed', 'jobA must remain present (within 300000ms)');

  const queryNewJob = await client.request(CODE.JOB_GET, { job_id: newJobId });
  assert.equal(queryNewJob.json.result.state, 'succeeded', 'new job must be present');
  assert.equal(device.completedJobs.length, 8, 'completedJobs size strictly bounded at 8');
});

// ---------------------------------------------------------------------------
// G1-R2-A exact retention boundary (independent acceptance cases fixed as tests)
//
// elapsed = device_now - finished_ms
//   elapsed <  300000 ms -> protected, still queryable, full capacity => BUSY
//   elapsed >= 300000 ms -> reclaimable, new task may be admitted
//
// The clock is fully controlled. Before each boundary the test keeps the
// session alive with PINGs (TTL 15000 ms) and ends with a silent step of more
// than 5000 ms, so the 10 RPC/s window is empty at the boundary instant and no
// RATE_LIMITED or session expiry can mask the result. Every assertion that is
// tied to the boundary runs at exactly that device time (asserted).
// ---------------------------------------------------------------------------
const RETENTION_MS = 300000;
const FILL_SPACING_MS = 5000;

function deviceNow(device, clock) {
  return device.uptime + clock.now();
}

function assertJobStoreBounded(device, where) {
  const total = device.completedJobs.length + device.activeJobs.size;
  assert.ok(total <= 8, `${where}: active + completed records must be <= 8 (got ${total})`);
  assert.ok(device.jobs.length <= 8, `${where}: device.jobs must be <= 8 (got ${device.jobs.length})`);
}

async function advanceDeviceTo(client, device, clock, target) {
  let remaining = target - deviceNow(device, clock);
  assert.ok(remaining > 10000, `advance target must be > 10000 ms ahead (got ${remaining})`);
  while (remaining > 10000) {
    clock.advance(FILL_SPACING_MS);
    remaining -= FILL_SPACING_MS;
    const pong = await client.request(CODE.PING, {});
    assert.equal(pong.json.ok, true, 'keepalive PING must succeed (no rate limit, no session expiry)');
  }
  // Final silent step lies in (5000, 10000] ms: RPC window empty, session alive.
  clock.advance(remaining);
  assert.equal(deviceNow(device, clock), target, 'device clock must land exactly on the boundary');
}

async function fillCompletedHistory(client, device, clock, prefix) {
  const records = [];
  for (let i = 0; i < 8; i++) {
    clock.advance(FILL_SPACING_MS);
    const opId = `${prefix}-0000-4000-8000-${String(i).padStart(12, '0')}`;
    const res = await client.request(CODE.WIFI_SCAN, { op_id: opId });
    assert.equal(res.json.ok, true, `fill scan #${i} must be admitted`);
    const jobId = res.json.result.job_id;
    device.advanceJob(jobId, 'succeeded', { stage: 'done' });
    const record = device.completedJobs.find((item) => item.job_id === jobId);
    assert.ok(record, `fill scan #${i} must be in completed history`);
    assert.equal(record.finished_ms, deviceNow(device, clock));
    records.push({ opId, jobId, finishedMs: record.finished_ms });
    assertJobStoreBounded(device, `fill #${i}`);
  }
  assert.equal(device.completedJobs.length, 8);
  assert.equal(device.activeJobs.size, 0);
  return records;
}

function assertCapacityBusy(res, where) {
  assert.equal(res.json.ok, false, `${where}: must be rejected`);
  assert.equal(res.json.error.code, ERROR.BUSY, `${where}: must be BUSY (not RATE_LIMITED or other)`);
  assert.equal(res.json.error.details?.reason, 'capacity', `${where}: BUSY reason must be capacity`);
}

for (const boundary of [299999, 300000, 300001]) {
  test(`G1-R2-A exact boundary: oldest completed record at elapsed ${boundary} ms with a controlled clock`, async () => {
    const clock = createClock(1000);
    const { client, device } = link(clock, { profile: 'r60' });
    await client.hello({ client: { name: 'mmwave-web-console', version: '0.1.0' }, nonce: hex32 });

    const prefix = `b0${boundary}`;
    const newOp = (n) => `${prefix}-0000-4000-8000-e0000000000${n}`;
    const records = await fillCompletedHistory(client, device, clock, prefix);
    const oldest = records[0];
    const others = records.slice(1);

    // Well inside the window at full capacity a new task is BUSY.
    clock.advance(FILL_SPACING_MS);
    assertCapacityBusy(await client.request(CODE.WIFI_SCAN, { op_id: newOp(1) }), 'early full capacity');
    assertJobStoreBounded(device, 'early full capacity');

    const target = oldest.finishedMs + boundary;
    await advanceDeviceTo(client, device, clock, target);
    assert.equal(deviceNow(device, clock) - oldest.finishedMs, boundary);
    for (const record of others) {
      assert.ok(deviceNow(device, clock) - record.finishedMs < RETENTION_MS, `${record.jobId} must still be inside the window`);
    }
    const wifiBefore = { state: device.wifi.state, ssid: device.wifi.ssid };

    if (boundary < RETENTION_MS) {
      // elapsed < 300000: protected
      const byId = await client.request(CODE.JOB_GET, { job_id: oldest.jobId });
      assert.equal(byId.json.ok, true);
      assert.equal(byId.json.result.job_id, oldest.jobId);
      assert.equal(byId.json.result.state, 'succeeded', 'oldest record must remain queryable by job_id');
      const byOp = await client.request(CODE.JOB_GET, { op_id: oldest.opId });
      assert.equal(byOp.json.ok, true);
      assert.equal(byOp.json.result.job_id, oldest.jobId, 'oldest record must remain queryable by op_id');

      const replay = await client.request(CODE.WIFI_SCAN, { op_id: oldest.opId });
      assert.equal(replay.json.ok, true);
      assert.equal(replay.json.result.job_id, oldest.jobId, 'same op_id replay must return the original job_id');

      assertCapacityBusy(await client.request(CODE.WIFI_SCAN, { op_id: newOp(2) }), `WIFI_SCAN at ${boundary}`);
      assertCapacityBusy(
        await client.request(CODE.ACTION_START, { action_id: 'radar.reset_module', op_id: newOp(3), params: {}, confirm: 'radar.reset_module' }),
        `ACTION_START at ${boundary}`,
      );
      assert.deepEqual({ state: device.wifi.state, ssid: device.wifi.ssid }, wifiBefore, 'rejection must not mutate Wi-Fi state');
      assert.equal(device.activeJobs.size, 0, 'rejection must not create an active job');
      assert.equal(device.completedJobs.length, 8);
      assert.ok(device.completedJobs.some((item) => item.job_id === oldest.jobId), 'oldest record must not be evicted');
      assertJobStoreBounded(device, `at ${boundary}`);
    } else {
      // elapsed >= 300000: reclaimable, new task admitted
      const admitted = await client.request(CODE.ACTION_START, {
        action_id: 'radar.reset_module',
        op_id: newOp(2),
        params: {},
        confirm: 'radar.reset_module',
      });
      assert.equal(admitted.json.ok, true, `new task must be admitted at elapsed ${boundary} ms`);
      const admittedJobId = admitted.json.result.job_id;
      assert.ok(!device.completedJobs.some((item) => item.job_id === oldest.jobId), 'oldest record must be reclaimed');
      assert.equal(device.completedJobs.length, 7);
      assert.equal(device.activeJobs.size, 1);
      assertJobStoreBounded(device, `admitted at ${boundary}`);

      // The admitted active job reserves the freed slot: capacity is full again.
      assertCapacityBusy(await client.request(CODE.WIFI_SCAN, { op_id: newOp(3) }), `reservation at ${boundary}`);
      assert.deepEqual({ state: device.wifi.state, ssid: device.wifi.ssid }, wifiBefore, 'rejection must not mutate Wi-Fi state');

      const byId = await client.request(CODE.JOB_GET, { job_id: oldest.jobId });
      assert.equal(byId.json.result.state, 'unknown', 'reclaimed record must be unknown by job_id');
      const byOp = await client.request(CODE.JOB_GET, { op_id: oldest.opId });
      assert.equal(byOp.json.result.state, 'unknown', 'reclaimed record must be unknown by op_id');

      device.advanceJob(admittedJobId, 'succeeded', { stage: 'done' });
      assert.equal(device.completedJobs.length, 8);
      assert.equal(device.activeJobs.size, 0);
      assertJobStoreBounded(device, `admitted job completed at ${boundary}`);
    }
    assert.equal(deviceNow(device, clock), target, 'all boundary assertions must run at the exact boundary instant');

    // Records that have not expired are unaffected. Query 4 records (8 RPCs)
    // per fresh 1000 ms window; others[0] finished 5000 ms after the oldest,
    // so they all stay inside the window for these 2000 ms.
    for (let i = 0; i < others.length; i += 4) {
      clock.advance(1000);
      for (const record of others.slice(i, i + 4)) {
        assert.ok(deviceNow(device, clock) - record.finishedMs < RETENTION_MS);
        const byId = await client.request(CODE.JOB_GET, { job_id: record.jobId });
        assert.equal(byId.json.ok, true);
        assert.equal(byId.json.result.state, 'succeeded', `${record.jobId} must be unaffected`);
        const byOp = await client.request(CODE.JOB_GET, { op_id: record.opId });
        assert.equal(byOp.json.ok, true);
        assert.equal(byOp.json.result.job_id, record.jobId, `${record.opId} must be unaffected`);
      }
      assertJobStoreBounded(device, `unexpired batch ${i}`);
    }
  });
}

test('G1-R2-B regression: reboot lifecycle, memory boundedness across 100 reboots, lock release, and boot_id uniqueness', async () => {
  const clock = createClock(1000);
  const { client, device } = link(clock, { profile: 'r60' });
  await client.hello({ client: { name: 'mmwave-web-console', version: '0.1.0' }, nonce: hex32 });

  // Normal session expire / disconnect does NOT cancel active tasks or discard jobs
  const opNormal = 'd1000000-0000-4000-8000-000000000001';
  const startNormal = await client.request(CODE.ACTION_START, {
    action_id: 'radar.reset_module',
    op_id: opNormal,
    params: {},
    confirm: 'radar.reset_module',
  });
  const normalJobId = startNormal.json.result.job_id;
  device.expire(); // Session expiration
  await client.hello({ client: { name: 'mmwave-web-console', version: '0.1.0' }, nonce: '00000000000000000000000000000003' });
  const checkNormalJob = await client.request(CODE.JOB_GET, { job_id: normalJobId });
  assert.equal(checkNormalJob.json.result.state, 'queued', 'session expiration must NOT cancel or clear accepted tasks');
  device.advanceJob(normalJobId, 'succeeded', { stage: 'done' });

  // Modify config to verify NVS persistence across reboot
  const baseRev = device.revision;
  const commitRes = await client.request(CODE.CONFIG_COMMIT, {
    base_revision: baseRev,
    op_id: 'd2000000-0000-4000-8000-000000000002',
    changes: { 'install.yaw_deg': 45.0 },
  });
  assert.equal(commitRes.json.ok, true);
  const persistedRevision = commitRes.json.result.revision;

  // Run 100 consecutive reboots:
  // - each reboot generates a distinct non-repeating boot_id
  // - volatile jobs and locks are cleared (cannot grow unbounded)
  // - NVS config and commit history are preserved
  // - old job_id and op_id queries return state: "unknown"
  const seenBootIds = new Set([device.bootId]);

  for (let i = 0; i < 100; i++) {
    clock.advance(500);
    // Start an active job that holds a lock
    const op = `d3000000-0000-4000-8000-${String(i).padStart(12, '0')}`;
    const startRes = await client.request(CODE.ACTION_START, {
      action_id: 'radar.reset_module',
      op_id: op,
      params: {},
      confirm: 'radar.reset_module',
    });
    assert.equal(startRes.json.ok, true);
    const activeJobId = startRes.json.result.job_id;

    // Simulate reboot without manual boot_id argument
    device.reboot();
    assert.ok(!seenBootIds.has(device.bootId), `reboot #${i} must generate a new unique boot_id`);
    seenBootIds.add(device.bootId);

    // Re-handshake on new boot
    const nonce = String(i + 10).padStart(32, '0');
    const helloRes = await client.hello({ client: { name: 'mmwave-web-console', version: '0.1.0' }, nonce });
    assert.equal(helloRes.json.result.boot_id, device.bootId);

    // Query old job from previous boot: MUST return unknown, never leak old result
    const oldJobQuery = await client.request(CODE.JOB_GET, { job_id: activeJobId });
    assert.equal(oldJobQuery.json.result.state, 'unknown', `job from previous boot must return unknown on reboot #${i}`);

    const oldOpQuery = await client.request(CODE.JOB_GET, { op_id: op });
    assert.equal(oldOpQuery.json.result.state, 'unknown', `op_id from previous boot must return unknown on reboot #${i}`);

    // Resource lock must be released immediately upon reboot: new radar action must NOT return BUSY
    const newOp = `d4000000-0000-4000-8000-${String(i).padStart(12, '0')}`;
    const newStartRes = await client.request(CODE.ACTION_START, {
      action_id: 'radar.reset_module',
      op_id: newOp,
      params: {},
      confirm: 'radar.reset_module',
    });
    assert.equal(newStartRes.json.ok, true, `resource lock must be released after reboot #${i}`);
    device.advanceJob(newStartRes.json.result.job_id, 'succeeded', { stage: 'done' });

    // Check memory boundedness: active + completed records must never exceed 8
    // (protected completed records + active reservations <= 8).
    const taskCount = device.jobs.length;
    assert.ok(taskCount <= 8, `device task memory must be bounded (got ${taskCount} after reboot #${i})`);
    assert.ok(device.completedJobs.length + device.activeJobs.size <= 8, `active + completed must be <= 8 after reboot #${i}`);
  }

  // Verify NVS config and commit persistence survived all 100 reboots
  assert.equal(device.config['install.yaw_deg'], 45.0, 'persisted config must survive 100 reboots');
  assert.equal(device.revision, persistedRevision, 'persisted revision must survive 100 reboots');
  const commitStatusRes = await client.request(CODE.COMMIT_STATUS, { op_id: 'd2000000-0000-4000-8000-000000000002' });
  assert.equal(commitStatusRes.json.ok, true);
  assert.equal(commitStatusRes.json.result.found, true, 'persisted commit op_id must survive 100 reboots');
});


test('G1-R3 regression: strict structured config validation across schema, CONFIG_VALIDATE, and CONFIG_COMMIT', async () => {
  const clock = createClock(1000);
  const { client, device } = link(clock, { profile: 'r60' });
  await client.hello({ client: { name: 'mmwave-web-console', version: '0.1.0' }, nonce: hex32 });

  const rev = device.revision;
  const badConfigs = [
    {
      name: 'non-integer slot 0.5',
      changes: { 'areas.definitions': [{ slot: 0.5, enabled: true, name: 'A', points_cm: [[0, 0], [100, 0], [0, 100]] }] },
      expectedCode: ERROR.INVALID_ARGUMENT,
    },
    {
      name: 'duplicate slot index',
      changes: {
        'areas.definitions': [
          { slot: 0, enabled: true, name: 'A', points_cm: [[0, 0], [100, 0], [0, 100]] },
          { slot: 0, enabled: false, name: 'B', points_cm: [] },
        ],
      },
      expectedCode: ERROR.INVALID_ARGUMENT,
    },
    {
      name: 'unknown field inside area slot',
      changes: { 'areas.definitions': [{ slot: 0, enabled: false, name: 'A', points_cm: [], extra_field: 1 }] },
      expectedCode: ERROR.UNKNOWN_FIELD,
    },
    {
      name: 'disabled slot with non-array points_cm',
      changes: { 'areas.definitions': [{ slot: 0, enabled: false, name: 'A', points_cm: 'bad' }] },
      expectedCode: ERROR.INVALID_ARGUMENT,
    },
    {
      name: 'disabled slot with 2 points',
      changes: { 'areas.definitions': [{ slot: 0, enabled: false, name: 'A', points_cm: [[0, 0], [10, 0]] }] },
      expectedCode: ERROR.INVALID_ARGUMENT,
    },
    {
      name: 'disabled slot with self-intersecting polygon',
      changes: { 'areas.definitions': [{ slot: 0, enabled: false, name: 'A', points_cm: [[0, 0], [100, 100], [0, 100], [100, 0]] }] },
      expectedCode: ERROR.INVALID_ARGUMENT,
    },
    {
      name: 'area slot exceeding 12 vertices',
      changes: { 'areas.definitions': [{ slot: 0, enabled: true, name: 'A', points_cm: makeValidConvexPolygon(13, 500) }] },
      expectedCode: ERROR.INVALID_ARGUMENT,
    },
    {
      name: 'boundary vertex out of [-2000, 2000] range',
      changes: { 'geometry.boundary_cm': [[0, 0], [2001, 0], [0, 100]] },
      expectedCode: ERROR.OUT_OF_RANGE,
    },
    {
      name: 'install.yaw_deg misaligned step 0.05',
      changes: { 'install.yaw_deg': 0.05 },
      expectedCode: ERROR.INVALID_ARGUMENT,
    },
    {
      name: 'unsupported legacy key area.slots',
      changes: { 'area.slots': [] },
      expectedCode: ERROR.UNSUPPORTED,
    },
  ];

  for (const [idx, item] of badConfigs.entries()) {
    clock.advance(200);
    const valRes = await client.request(CODE.CONFIG_VALIDATE, { base_revision: rev, changes: item.changes });
    assert.equal(valRes.json.ok, false, `CONFIG_VALIDATE must reject ${item.name}`);
    assert.equal(valRes.json.error.code, item.expectedCode, `CONFIG_VALIDATE code for ${item.name}`);
    const comRes = await client.request(CODE.CONFIG_COMMIT, {
      base_revision: rev,
      op_id: `c0000000-0000-4000-8000-00000000000${idx}`,
      changes: item.changes,
    });
    assert.equal(comRes.json.ok, false, `CONFIG_COMMIT must reject ${item.name}`);
    assert.equal(comRes.json.error.code, item.expectedCode, `CONFIG_COMMIT code for ${item.name}`);
  }

  // Positive cases: disabled slot with empty [] points_cm and disabled slot preserving valid 3..12 polygon
  clock.advance(1000);
  const validDisabledChanges = {
    'areas.definitions': [
      { slot: 0, enabled: false, name: 'EmptyDisabled', points_cm: [] },
      { slot: 1, enabled: false, name: 'PreservedPolygon', points_cm: [[0, 0], [100, 0], [0, 100]] },
      { slot: 2, enabled: true, name: 'ActiveZone', points_cm: makeValidConvexPolygon(12, 600) },
    ],
  };
  const validDisabledVal = await client.request(CODE.CONFIG_VALIDATE, { base_revision: rev, changes: validDisabledChanges });
  assert.equal(validDisabledVal.json.ok, true);
  const validDisabledCom = await client.request(CODE.CONFIG_COMMIT, {
    base_revision: rev,
    op_id: 'c1000000-0000-4000-8000-000000000001',
    changes: validDisabledChanges,
  });
  assert.equal(validDisabledCom.json.ok, true);

  // range.window.v1 unknown field and min > max on range1d profile
  const clock1d = createClock(1000);
  const { client: client1d, device: device1d } = link(clock1d, { profile: 'range1d' });
  await client1d.hello({ client: { name: 'mmwave-web-console', version: '0.1.0' }, nonce: hex32 });
  const rangeUnknown = await client1d.request(CODE.CONFIG_VALIDATE, {
    base_revision: device1d.revision,
    changes: { 'range.window_cm': { min: 0, max: 300, extra: 1 } },
  });
  assert.equal(rangeUnknown.json.ok, false);
  assert.equal(rangeUnknown.json.error.code, ERROR.UNKNOWN_FIELD);

  const rangeInverted = await client1d.request(CODE.CONFIG_VALIDATE, {
    base_revision: device1d.revision,
    changes: { 'range.window_cm': { min: 400, max: 100 } },
  });
  assert.equal(rangeInverted.json.ok, false);
  assert.equal(rangeInverted.json.error.code, ERROR.INVALID_ARGUMENT);
});

const repoRoot = new URL('../../', import.meta.url);
const repoPath = (rel) => fileURLToPath(new URL(rel, repoRoot));
const readRepo = (rel) => readFileSync(repoPath(rel), 'utf8');

function yamlUartPins(text) {
  const tx = /^\s*tx_pin:\s*(GPIO\d+)\s*$/m.exec(text);
  const rx = /^\s*rx_pin:\s*(GPIO\d+)\s*$/m.exec(text);
  const baud = /^uart:[\s\S]*?^\s*baud_rate:\s*(\d+)\s*$/m.exec(text);
  return { tx: tx?.[1], rx: rx?.[1], baud: baud ? Number(baud[1]) : undefined };
}

function markdownLinkTargets(text) {
  const targets = [];
  for (const match of text.matchAll(/\]\(([^)\s]+)\)/g)) {
    const raw = match[1];
    if (/^(https?:|mailto:|sidecar:|conversation:|#)/.test(raw)) continue;
    targets.push(decodeURIComponent(raw.split('#')[0]));
  }
  return targets;
}

test('G1-R4 regression: G0 evidence index matches host.yaml/baseline.yaml and is arithmetically self-consistent', () => {
  const index = JSON.parse(readRepo('docs/reviews/web-console/g0-evidence-index.json'));
  const hostPins = yamlUartPins(readRepo('docs/reviews/web-console/g0/host.yaml'));
  const basePins = yamlUartPins(readRepo('docs/reviews/web-console/g0/baseline.yaml'));
  assert.deepEqual(hostPins, { tx: 'GPIO21', rx: 'GPIO20', baud: 115200 });
  assert.deepEqual(basePins, hostPins);

  const uart = index.hardware_testbed.radar_uart;
  assert.ok(uart.includes(`TX=${hostPins.tx}`), uart);
  assert.ok(uart.includes(`RX=${hostPins.rx}`), uart);
  assert.ok(uart.includes(String(hostPins.baud)), uart);
  const host = index.firmware_artifacts.host;
  const base = index.firmware_artifacts.baseline;
  assert.equal(host.single_usb_owner_verified.radar_uart_tx_pin, hostPins.tx);
  assert.equal(host.single_usb_owner_verified.radar_uart_rx_pin, hostPins.rx);
  assert.equal(base.radar_uart_tx_pin, basePins.tx);
  assert.equal(base.radar_uart_rx_pin, basePins.rx);
  assert.ok(existsSync(repoPath(host.config)), host.config);
  assert.ok(existsSync(repoPath(base.config)), base.config);

  const m = index.gates['G0-05'].metrics;
  assert.equal(m.link_time_flash_host_bytes, host.link_time_flash_used_bytes);
  assert.equal(m.link_time_flash_baseline_bytes, base.link_time_flash_used_bytes);
  assert.equal(m.link_time_flash_delta_bytes, m.link_time_flash_host_bytes - m.link_time_flash_baseline_bytes);
  assert.equal(m.ota_bin_delta_bytes, host.firmware_ota_bin_bytes - base.firmware_ota_bin_bytes);
  assert.equal(m.factory_bin_delta_bytes, host.firmware_factory_bin_bytes - base.firmware_factory_bin_bytes);
  assert.ok(m.link_time_flash_delta_bytes <= m.flash_budget_max_bytes);
  assert.equal(m.link_time_ram_host_bytes, host.link_time_ram_used_bytes);
  assert.equal(m.link_time_ram_baseline_bytes, base.link_time_ram_used_bytes);
  assert.equal(m.link_time_ram_delta_bytes, m.link_time_ram_host_bytes - m.link_time_ram_baseline_bytes);
  assert.equal(m.dram0_bss_host_bytes, host.elf_sections_bytes['.dram0.bss']);
  assert.equal(m.dram0_bss_baseline_bytes, base.elf_sections_bytes['.dram0.bss']);
  assert.equal(m.dram0_bss_delta_bytes, m.dram0_bss_host_bytes - m.dram0_bss_baseline_bytes);
  assert.equal(m.runtime_heap_delta_bytes, m.free_heap_baseline_bytes - m.free_heap_host_initial_bytes);
  assert.ok(m.runtime_heap_delta_bytes <= m.runtime_ram_hard_limit_bytes);
  assert.ok(m.stack_high_water_host_2h_min_bytes >= m.stack_budget_min_bytes);
  assert.ok(m.max_loop_us_host_2h_peak <= m.loop_target_max_us);

  const g03 = index.gates['G0-03'];
  assert.equal(g03.metrics.free_heap_net_delta_bytes, g03.metrics.free_heap_last_bytes - g03.metrics.free_heap_first_bytes);
  assert.equal(g03.metrics.radar_frames_delta, g03.metrics.radar_frames_last - g03.metrics.radar_frames_first);
  assert.equal(g03.metrics.radar_targets_delta, g03.metrics.radar_targets_last - g03.metrics.radar_targets_first);
  assert.equal(g03.metrics.free_heap_min_bytes, m.free_heap_host_2h_min_bytes);
  assert.equal(g03.metrics.free_heap_max_bytes, m.free_heap_host_2h_max_bytes);
  assert.equal(g03.metrics.free_heap_last_bytes, m.free_heap_host_2h_steady_bytes);
  assert.equal(g03.metrics.max_loop_us_peak, m.max_loop_us_host_2h_peak);
  assert.equal(g03.raw_evidence_file.total_samples, g03.metrics.attempts);
  for (const loc of g03.raw_evidence_file.in_repo_summary_locations) {
    assert.ok(existsSync(repoPath(loc.split('#')[0])), loc);
  }
  assert.equal(JSON.stringify(index).includes('g0-03-endurance-2h-summary.json'), false);
});

test('G1-R5 regression: referenced paths exist and bilingual protocol READMEs mirror the R60 fixture', () => {
  for (const source of fixture.evidence.sources) assert.ok(existsSync(repoPath(source)), `fixture source ${source}`);

  const docs = [
    'docs/protocol/README.md',
    'docs/protocol/README_CN.md',
    'docs/protocol/design-differences.md',
    'docs/protocol/design-differences_CN.md',
    'docs/reviews/web-console/wp0-wp1-phase-report.md',
    'docs/reviews/web-console/wp0-wp1-phase-report_CN.md',
  ];
  for (const doc of docs) {
    const base = new URL(doc, repoRoot);
    for (const target of markdownLinkTargets(readRepo(doc))) {
      if (!target) continue;
      assert.ok(existsSync(fileURLToPath(new URL(target, base))), `${doc} -> ${target}`);
    }
  }

  const unsupportedJson = JSON.stringify(fixture.unsupported).replace(/,/g, ', ');
  for (const doc of ['docs/protocol/README.md', 'docs/protocol/README_CN.md']) {
    const text = readRepo(doc);
    assert.ok(text.includes(`\`${fixture.unsupported.length}\``), `${doc} unsupported count`);
    assert.ok(text.includes(unsupportedJson), `${doc} unsupported list`);
    for (const cap of fixture.capabilities.filter((item) => item.kind === 'config')) {
      assert.ok(text.includes(`\`${cap.id}\``), `${doc} mentions ${cap.id}`);
      if (cap.type === 'number') {
        assert.ok(text.includes(`\`${cap.minimum} .. ${cap.maximum}\`, step \`${cap.step}\``), `${doc} ${cap.id} range/step`);
      } else {
        assert.ok(text.includes(`\`schema_id: "${cap.schema_id}"\`, \`min_items: ${cap.min_items}\`, \`max_items: ${cap.max_items}\``), `${doc} ${cap.id} schema`);
      }
    }
    for (const action of fixture.actions) {
      assert.ok(text.includes(`\`${action.action_id}\`（\`confirm: ${action.confirm}\``) || text.includes(`\`${action.action_id}\` (\`confirm: ${action.confirm}\``), `${doc} ${action.action_id}`);
      assert.ok(text.includes(`\`resource: "${action.resource}"\`, \`deadline_ms: ${action.deadline_ms}\``), `${doc} ${action.action_id} deadline`);
    }
    assert.ok(text.includes('{slot, enabled, name, points_cm}'), `${doc} area slot shape`);
    assert.ok(text.includes('`range1d`'), `${doc} range1d profile`);
    for (const stale of ['area.slots', 'radar.reinitialize', 'wifi.clear', '{slot, enabled, points}']) {
      assert.equal(text.includes(stale), false, `${doc} must not mention ${stale}`);
    }
  }
});
