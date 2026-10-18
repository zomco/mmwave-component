import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { applyTransform, project1D, rotationMatrix } from '../src/protocol/transform.js';

const header = readFileSync(new URL('../../components/r60abd1/r60abd1_transform.h', import.meta.url), 'utf8');
const vectors = JSON.parse(readFileSync(new URL('../../docs/protocol/fixtures/coordinate-vectors.json', import.meta.url), 'utf8'));

test('firmware header in this repository uses the documented matrix', () => {
  assert.match(header, /R = Rz\(yaw\)/);
  assert.match(header, /room_z = cal\.radar_z - wz/);
  assert.match(header, /R\.m\[0\]\[1\] = sγ \* cα/);
  const yaw90 = rotationMatrix(90, 0, 0);
  assert.ok(Math.abs(yaw90[0][1] - 1) < 1e-9);
  assert.ok(Math.abs(yaw90[1][1]) < 1e-9);
});

test('shared vectors include pitch, roll, negative coordinates and 1D +Y projection', () => {
  for (const item of vectors.cases.filter((entry) => !entry.projection)) {
    const got = applyTransform(...item.local_cm, item.calibration);
    assert.ok(Math.abs(got.roomX - item.room_cm[0]) < vectors.tolerance_cm, item.id);
    assert.ok(Math.abs(got.roomY - item.room_cm[1]) < vectors.tolerance_cm, item.id);
    assert.ok(Math.abs(got.roomZ - item.room_cm[2]) < vectors.tolerance_cm, item.id);
  }
  const projected = project1D(150, { radar_x: 5, radar_y: -5, radar_z: 100, yaw: 90, pitch: 0, roll: 0, polygon: [] });
  assert.ok(Math.abs(projected.roomX - 155) < 1e-6);
  assert.ok(Math.abs(projected.roomY + 5) < 1e-6);
  const square = [{ x: 0, y: 0 }, { x: 100, y: 0 }, { x: 100, y: 100 }, { x: 0, y: 100 }];
  const cal = { radar_x: 0, radar_y: 0, radar_z: 0, yaw: 0, pitch: 0, roll: 0, polygon: square };
  assert.equal(applyTransform(50, 0, 0, cal).inBoundary, true);
  assert.equal(applyTransform(0, 0, 0, cal).inBoundary, true);
  assert.equal(applyTransform(150, 10, 0, cal).inBoundary, false);
  assert.equal(applyTransform(50, 50, 0, cal).inBoundary, true);
});
