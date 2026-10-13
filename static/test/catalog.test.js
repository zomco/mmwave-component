import test from 'node:test';
import assert from 'node:assert/strict';
import { radars, boards, safeAssetPath, parseReleaseIndex, compatibleReleases, defaultRelease, verifyManifest } from '../src/catalog.js';
const make = (channel = 'alpha') => ({ id: `v1.0.0-${channel}.1`, version: `v1.0.0-${channel}.1`, channel, sourceCommit: 'a'.repeat(40), publishedAt: '2026-10-12T10:00:00Z', firmware: [{ radarId: 'r60abd1', chipFamily: 'ESP32-C3', boardIds: ['esp32-c3-supermini'], manifest: `firmware/v1.0.0-${channel}.1/r60abd1-ESP32-C3/manifest.json`, manifestSha256: 'b'.repeat(64) }] });
test('only Completed 1D/2D ESP32-C3 hardware is listed', () => { assert.ok(radars.length); assert.ok(radars.every((r) => r.status === 'Completed' && ['1D', '2D'].includes(r.dimension))); assert.ok(boards.every((b) => b.uart.tx === 21 && b.uart.rx === 20)); });
test('Alpha never selected implicitly', () => { assert.equal(defaultRelease([make()]), ''); assert.equal(defaultRelease([make(), make('beta')]), 'v1.0.0-beta.1'); });
test('incompatible or unaccepted hardware cannot get a release', () => { assert.equal(compatibleReleases([make()], radars[0], boards[0]).length, 1); assert.deepEqual(compatibleReleases([make()], { ...radars[0], status: 'Testing' }, boards[0]), []); assert.deepEqual(compatibleReleases([make()], radars[0], { ...boards[0], id: 'other' }), []); });
test('invalid, duplicate or traversing release data fails closed', () => { const r = make(); assert.equal(parseReleaseIndex({ schemaVersion: 1, releases: [r] }).length, 1); for (const data of [{}, [], { schemaVersion: 1, releases: [r, r] }, { schemaVersion: 1, releases: [{ ...r, channel: 'nightly' }] }, { schemaVersion: 1, releases: [{ ...r, firmware: [{ ...r.firmware[0], manifest: '../firmware.json' }] }] }]) assert.throws(() => parseReleaseIndex(data)); for (const path of ['../x', '/x', 'https://a/b', 'a/%2e%2e/b', 'a/./b']) assert.equal(safeAssetPath(path), false); });
test('manifest checksum, version and flash parts are verified', async (t) => {
  const r = { ...make(), firmware: make().firmware[0] };
  const manifest = { version: r.version, builds: [{ chipFamily: 'ESP32-C3', parts: [{ path: 'firmware.factory.bin', offset: 0 }] }] };
  const body = JSON.stringify(manifest);
  r.firmware.manifestSha256 = Buffer.from(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(body))).toString('hex');
  t.mock.method(globalThis, 'fetch', async () => new Response(body));
  assert.match(await verifyManifest(r, 'https://example.com/mmwave/'), /^https:\/\/example.com\/mmwave\/firmware\//);
  await assert.rejects(verifyManifest({ ...r, binaryVersion: 'wrong' }, 'https://example.com/'));
  await assert.rejects(verifyManifest({ ...r, firmware: { ...r.firmware, manifestSha256: '0'.repeat(64) } }, 'https://example.com/'));
});
