// Batch schema validation of G2 evidence JSONL using the real frozen-contract
// JS validators (static/src/protocol). One process validates the whole file:
//   node tools/g2/validate_frames.mjs evidence.jsonl
// Exits non-zero when any frame fails. Never prints payloads (they may carry
// device identifiers); only frame index, direction, code and the issue.
import { readFileSync } from 'node:fs';
import { validateResponse, validateEvent, validateRequest, telemetryIssue } from '../../static/src/protocol/contract.js';
import { CODE } from '../../static/src/protocol/limits.js';

const path = process.argv[2];
if (!path) {
  console.error('usage: node validate_frames.mjs <evidence.jsonl>');
  process.exit(2);
}
const codeByName = Object.fromEntries(Object.entries(CODE).map(([k, v]) => [v, k]));
let total = 0;
let checked = 0;
let failed = 0;
const failures = [];
for (const [index, line] of readFileSync(path, 'utf8').split('\n').entries()) {
  if (!line.trim()) continue;
  let rec;
  try {
    rec = JSON.parse(line);
  } catch {
    failures.push({ index: index + 1, issue: 'unparseable line' });
    failed += 1;
    continue;
  }
  if (rec.dir === 'note' || rec.payload === undefined || rec.payload === null) continue;
  total += 1;
  const isTx = rec.dir === 'tx';
  const kind = rec.kind;
  const code = rec.code;
  if (!Number.isInteger(code)) continue;
  try {
    if (isTx) {
      if (rec.expect_invalid) {
        // Deliberately malformed request (negative test): request validation
        // is skipped by design; the recorded response is still validated.
      } else if (code === CODE.WIFI_PROVISION) {
        // Secret values were replaced at capture time; only the field shape is
        // checked here so redaction length changes never fail this pass.
        const keys = Object.keys(rec.payload).sort().join(',');
        if (keys !== 'auth,op_id,password,ssid') {
          failures.push({ index: index + 1, dir: 'tx', code: 'WIFI_PROVISION', issue: `provision tx keys: ${keys}` });
          failed += 1;
        }
      } else {
        const okReq = validateRequest(code, rec.payload);
        if (okReq?.ok !== true) {
          failures.push({ index: index + 1, dir: 'tx', code: codeByName[code] ?? code, issue: JSON.stringify(okReq).slice(0, 200) });
          failed += 1;
        }
      }
    } else if (kind === 3) {
      const okEv = validateEvent(code, rec.payload);
      if (okEv !== true) {
        failures.push({ index: index + 1, dir: 'rx', event: codeByName[code] ?? code, issue: String(okEv) });
        failed += 1;
      } else if (code === CODE.TELEMETRY) {
        const issue = telemetryIssue(rec.payload);
        if (issue !== null && issue !== undefined && issue !== true) {
          failures.push({ index: index + 1, dir: 'rx', event: 'TELEMETRY', issue: `telemetryIssue: ${JSON.stringify(issue)}` });
          failed += 1;
        }
      }
    } else if (kind === 2) {
      const okResp = validateResponse(code, rec.payload);
      if (okResp !== true) {
        failures.push({ index: index + 1, dir: 'rx', code: codeByName[code] ?? code, issue: String(okResp) });
        failed += 1;
      }
    }
    checked += 1;
  } catch (error) {
    failures.push({ index: index + 1, dir: rec.dir, code, issue: `validator threw: ${error.message}` });
    failed += 1;
  }
}
console.log(JSON.stringify({ file: path, frames: total, schema_checked: checked, failed, failures: failures.slice(0, 50) }, null, 2));
process.exit(failed === 0 ? 0 : 1);
