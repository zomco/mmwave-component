import { readdirSync, readFileSync, statSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = fileURLToPath(new URL('.', import.meta.url));
const packageRoot = join(here, '../node_modules/esp-web-tools');
const patches = JSON.parse(readFileSync(join(here, 'installer-download-guard-patches.json'), 'utf8'));

export const EMPTY_FIRMWARE_MESSAGE =
  'the response was empty. Check a download blocker, then retry. Nothing was written.';
export const NO_BYTES_MESSAGE =
  'no firmware bytes were received. Check a download blocker, then retry. Nothing was written.';

function targets(spec) {
  if (!spec.includes('*')) return [join(packageRoot, spec)];
  const slash = spec.lastIndexOf('/');
  const dir = join(packageRoot, spec.slice(0, slash));
  const prefix = spec.slice(slash + 1, spec.indexOf('*'));
  const suffix = spec.slice(spec.lastIndexOf('*') + 1);
  const names = readdirSync(dir).filter((name) => name.startsWith(prefix) && name.endsWith(suffix));
  if (names.length !== 1) throw new Error('expected one match for ' + spec + ', found ' + names.join(','));
  return [join(dir, names[0])];
}

export function applyInstallerDownloadGuard() {
  const changed = [];
  const seen = new Set();
  for (const patch of patches) {
    for (const path of targets(patch.file)) {
      seen.add(path);
      let text = readFileSync(path, 'utf8');
      if (text.includes(patch.to)) continue;
      const at = text.indexOf(patch.from);
      if (at < 0) throw new Error('anchor missing in ' + path + ' for ' + patch.id);
      if (text.indexOf(patch.from, at + patch.from.length) >= 0) {
        throw new Error('anchor not unique in ' + path + ' for ' + patch.id);
      }
      text = text.slice(0, at) + patch.to + text.slice(at + patch.from.length);
      writeFileSync(path, text);
      changed.push(patch.id);
    }
  }
  for (const path of seen) {
    const text = readFileSync(path, 'utf8');
    const mark = Math.max(text.indexOf(EMPTY_FIRMWARE_MESSAGE), text.indexOf(NO_BYTES_MESSAGE));
    if (text.indexOf(EMPTY_FIRMWARE_MESSAGE) < 0 || text.indexOf(NO_BYTES_MESSAGE) < 0) {
      throw new Error('guard text missing in ' + path);
    }
    if (text.indexOf('eraseFlash', mark) < 0 || text.indexOf('writeFlash', mark) < 0) {
      throw new Error('guard is not before erase/write in ' + path);
    }
    if (text.includes('readAsArrayBuffer')) throw new Error('old firmware reader still present in ' + path);
  }
  const leftovers = [];
  const visit = (dir) => {
    for (const name of readdirSync(dir)) {
      const path = join(dir, name);
      if (statSync(path).isDirectory()) visit(path);
      else if (name.endsWith('.js') || name.endsWith('.ts')) {
        if (readFileSync(path, 'utf8').includes('readAsArrayBuffer')) leftovers.push(path);
      }
    }
  };
  visit(packageRoot);
  if (leftovers.length) throw new Error('unpatched firmware reader: ' + leftovers.join(', '));
  return changed;
}

export function assertBundleGuarded(outDir) {
  const hits = [];
  const visit = (dir) => {
    for (const name of readdirSync(dir)) {
      const path = join(dir, name);
      if (statSync(path).isDirectory()) visit(path);
      else if (name.endsWith('.js') && readFileSync(path, 'utf8').includes(EMPTY_FIRMWARE_MESSAGE)) hits.push(path);
    }
  };
  visit(outDir);
  if (hits.length === 0) throw new Error('built page is missing the empty-firmware guard: ' + outDir);
  return hits;
}

const invoked = process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;
if (invoked) {
  const changed = applyInstallerDownloadGuard();
  console.log(changed.length ? 'patched ' + changed.join(', ') : 'installer download guard already present');
}
