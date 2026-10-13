import test from 'node:test';
import assert from 'node:assert/strict';
import { demoFrame, STILL_PROGRESS } from '../src/feature-demo.js';
import { copy } from '../src/content.js';

test('alignment demonstrates before and after, with a useful still frame', () => {
  assert.equal(demoFrame(0).alignment.state, 'before');
  assert.notEqual(demoFrame(0).alignment.angle, 0);
  const still = demoFrame(STILL_PROGRESS);
  assert.equal(still.alignment.state, 'after');
  assert.equal(Math.abs(still.alignment.angle), 0);
  assert.equal(still.alignment.offset, 0);
  assert.equal(still.boundary.inside, true);
});

test('presence and occupancy labels match the drawn target position', () => {
  let seenOutside = false;
  let seenInside = false;
  let seenGap = false;
  for (let i = 0; i <= 1000; i++) {
    const { boundary, zones } = demoFrame(i / 1000);
    assert.equal(boundary.inside, boundary.y >= 114);
    assert.equal(zones.sofa, zones.x >= 44 && zones.x <= 152);
    assert.equal(zones.desk, zones.x >= 180 && zones.x <= 292);
    assert.equal(zones.sofa && zones.desk, false);
    seenInside ||= boundary.inside;
    seenOutside ||= !boundary.inside;
    seenGap ||= !zones.sofa && !zones.desk;
  }
  assert.ok(seenInside && seenOutside && seenGap);
});

test('demo loops without a position jump and clamps invalid input', () => {
  assert.deepEqual(demoFrame(0), demoFrame(1));
  assert.deepEqual(demoFrame(-1), demoFrame(0));
  assert.deepEqual(demoFrame(2), demoFrame(1));
  assert.deepEqual(demoFrame(NaN), demoFrame(STILL_PROGRESS));
});

test('both languages include feature descriptions, motion controls and model caveats', () => {
  for (const t of Object.values(copy)) {
    assert.equal(t.compareRows, undefined);
    assert.ok(t.features.play && t.features.pause && t.features.progress && t.features.note);
    for (const key of ['alignment', 'boundary', 'zones']) {
      assert.ok(t.features[key].title && t.features[key].body && t.features[key].description);
    }
  }
});
