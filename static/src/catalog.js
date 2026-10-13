import catalog from '../device-catalog.json' with { type: 'json' };
export const radars = catalog.radars.filter((r) => r.status === 'Completed' && ['1D', '2D'].includes(r.dimension) && r.chipFamily === 'ESP32-C3');
export const boards = catalog.boards.filter((b) => b.chipFamily === 'ESP32-C3' && b.uart.tx === 21 && b.uart.rx === 20);
export const textFor = (value, language) => value?.[language] ?? value?.en ?? '';
export function safeAssetPath(path) {
  return typeof path === 'string' && /^[a-zA-Z0-9_./-]+$/.test(path) && !path.startsWith('/') && !path.split('/').some((p) => p === '..' || p === '.' || p === '');
}
export function parseReleaseIndex(data) {
  if (data?.schemaVersion !== 1 || !Array.isArray(data.releases)) throw new Error('Invalid release index');
  const ids = new Set();
  return data.releases.map((r) => {
    if (!r || !['alpha', 'beta'].includes(r.channel) || typeof r.id !== 'string' || r.id !== r.version || ids.has(r.id)
      || !/^v?\d+\.\d+\.\d+-(alpha|beta)\.\d+$/.test(r.version) || !r.version.includes(`-${r.channel}.`)
      || !/^[a-f0-9]{40}$/.test(r.sourceCommit) || !Number.isFinite(Date.parse(r.publishedAt))
      || !Array.isArray(r.firmware) || !r.firmware.length) throw new Error('Invalid release metadata');
    ids.add(r.id);
    const targets = new Set();
    for (const f of r.firmware) {
      if (!f || !safeAssetPath(f.manifest) || !f.manifest.startsWith(`firmware/${r.version}/`)
        || !Array.isArray(f.boardIds) || !f.boardIds.length || f.chipFamily !== 'ESP32-C3'
        || typeof f.radarId !== 'string' || !/^[a-f0-9]{64}$/.test(f.manifestSha256)
        || targets.has(f.radarId)) throw new Error('Invalid firmware metadata');
      targets.add(f.radarId);
    }
    return r;
  }).sort((a, b) => Date.parse(b.publishedAt) - Date.parse(a.publishedAt) || b.version.localeCompare(a.version, undefined, { numeric: true }));
}
export function compatibleReleases(releases, radar, board) {
  if (!radar || !board || radar.status !== 'Completed' || radar.chipFamily !== board.chipFamily) return [];
  return releases.flatMap((r) => {
    const firmware = r.firmware.find((f) => f.radarId === radar.id && f.chipFamily === board.chipFamily && f.boardIds.includes(board.id));
    return firmware ? [{ ...r, firmware }] : [];
  });
}
export const defaultRelease = (releases) => releases.find((r) => r.channel === 'beta')?.id ?? '';
export async function verifyManifest(release, base, signal) {
  const url = new URL(release.firmware.manifest, base);
  const response = await fetch(url, { signal, cache: 'no-cache' });
  if (!response.ok) throw new Error('Manifest unavailable');
  const bytes = await response.arrayBuffer();
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  const hash = Array.from(new Uint8Array(digest), (v) => v.toString(16).padStart(2, '0')).join('');
  if (hash !== release.firmware.manifestSha256) throw new Error('Manifest checksum mismatch');
  const manifest = JSON.parse(new TextDecoder().decode(bytes));
  if (manifest.version !== (release.binaryVersion || release.version)) throw new Error('Firmware version mismatch');
  const build = manifest.builds?.find((b) => b.chipFamily === release.firmware.chipFamily);
  if (!build?.parts?.length || build.parts.some((p) => !safeAssetPath(p.path) || !Number.isInteger(p.offset) || p.offset < 0)) throw new Error('Invalid flash manifest');
  return url.href;
}
