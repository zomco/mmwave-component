import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { unsupportedKeywords, validate } from '../src/protocol/schema.js';
import { polygonIssues } from '../src/protocol/geometry.js';
import { observation } from '../src/protocol/simulator.js';
import { encodeUtf8 } from '../src/protocol/utf8.js';

const schema = JSON.parse(readFileSync(new URL('../../docs/protocol/schema/mwcp-v1.schema.json', import.meta.url), 'utf8'));
const fixture = JSON.parse(readFileSync(new URL('../../docs/protocol/fixtures/r60abd1-capabilities.json', import.meta.url), 'utf8'));

test('schema uses only implemented keywords and covers every command', () => {
  assert.deepEqual(unsupportedKeywords(schema), []);
  const codes = Object.keys(schema['x-commands']);
  assert.equal(codes.length, 24);
  for (const code of codes) {
    const command = schema['x-commands'][code];
    assert.equal(Boolean(command.request || command.event), true, command.name);
    if (command.request) assert.equal(validate(command.request, { not: 'a request' }, schema).ok, false, command.name);
  }
});

test('R60 fixture fields come from source and do not invent speed or 3D', () => {
  assert.equal(fixture.origin, 'simulation');
  assert.equal(fixture.evidence.hardware_measured, false);
  for (const item of fixture.capabilities) assert.equal(validate(schema.$defs.capability, item, schema).ok, true, item.id);
  assert.equal(fixture.capabilities.find((item) => item.id === 'speed.cm_s').supported, false);
  assert.equal(fixture.identity.dimension, '2D');
  assert.equal(fixture.unsupported.includes('inject_mock_data'), true);
  assert.equal(validate(schema.$defs.error, { code: 'AUTH_REQUIRED', message: 'no' }, schema).ok, false);
});

test('observations and polygon capacity stay inside the draft limits', () => {
  for (const kind of ['empty', 'unknown', 'zero', '1d', 'multi']) {
    const result = validate(schema.$defs.telemetry, observation(kind), schema);
    assert.equal(result.ok, true, `${kind} ${JSON.stringify(result.errors)}`);
  }
  assert.deepEqual(polygonIssues([[0, 0], [1, 0], [0, 1]]), []);
  assert.ok(polygonIssues([[0, 0], [1, 1], [0, 1], [1, 0]]).includes('self_intersection'));
  const points = Array.from({ length: 64 }, () => [-2000, -2000]);
  const body = JSON.stringify({ base_revision: '1', op_id: 'd8592ab1-394a-4b1e-89ae-3de15b250015', changes: { 'geometry.boundary_cm': points } });
  assert.ok(encodeUtf8(body).length < 4096);
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
