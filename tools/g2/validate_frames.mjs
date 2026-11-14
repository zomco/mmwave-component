// Compatibility entry for historical firmware evidence tooling.
// Set MMWAVE_FLASHER_ROOT to an explicit mmwave-flasher checkout.
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
const root = process.env.MMWAVE_FLASHER_ROOT;
if (!root) throw new Error('Set MMWAVE_FLASHER_ROOT to the mmwave-flasher checkout before G2 frame validation');
await import(pathToFileURL(resolve(root, 'tools/g2/validate_frames.mjs')).href);
