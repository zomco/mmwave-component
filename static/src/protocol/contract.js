import schema from '../../../docs/protocol/schema/mwcp-v1.schema.json' with { type: 'json' };
import { ERROR } from './limits.js';
import { validate } from './schema.js';
import { encodeUtf8 } from './utf8.js';

export function loadSchema() {
  return schema;
}

export function validateRequest(code, body) {
  const command = schema['x-commands'][String(code)];
  if (!command?.request) return { ok: false, code: ERROR.UNSUPPORTED, message: 'Unsupported' };
  const result = validate(command.request, body, schema);
  if (!result.ok) {
    const unknown = result.errors.some((item) => item.code === 'additionalProperties');
    return { ok: false, code: unknown ? ERROR.UNKNOWN_FIELD : ERROR.INVALID_ARGUMENT, message: 'Invalid request', details: { errors: result.errors.slice(0, 16) } };
  }
  if (code === 0x0052) {
    const wifi = wifiPasswordIssue(body);
    if (wifi) return wifi;
  }
  return { ok: true };
}

export function validateResponse(code, body) {
  if (!body || typeof body !== 'object' || Array.isArray(body) || !Object.prototype.hasOwnProperty.call(body, 'ok')) return false;
  if (body.ok === true) {
    const command = schema['x-commands'][String(code)];
    if (!command?.result || !Object.prototype.hasOwnProperty.call(body, 'result')) return false;
    return validate(command.result, body.result, schema).ok;
  }
  if (body.ok === false) return validate(schema.$defs.errorEnvelope, body, schema).ok;
  return false;
}

export function validateEvent(code, body) {
  const command = schema['x-commands'][String(code)];
  if (!command?.event) return false;
  return validate(command.event, body, schema).ok;
}

export function wifiPasswordIssue(body) {
  const password = body?.password ?? '';
  const bytes = encodeUtf8(password).length;
  if (body?.auth === 'open') {
    return bytes === 0 ? null : { ok: false, code: ERROR.INVALID_ARGUMENT, message: 'Open network has no password' };
  }
  if (body?.auth === 'wpa2_psk') {
    if (/^[0-9a-fA-F]{64}$/.test(password) || (bytes >= 8 && bytes <= 63)) return null;
    return { ok: false, code: ERROR.INVALID_ARGUMENT, message: 'Bad passphrase' };
  }
  return { ok: false, code: ERROR.UNSUPPORTED, message: 'Unsupported auth' };
}

export function telemetryIssue(body) {
  const presence = body?.presence;
  if (presence && ['unknown', 'unsupported', 'invalid'].includes(presence.quality) && presence.value !== null) return 'quality_value';
  if (Array.isArray(body?.targets) && body.targets.length) {
    const kinds = new Set(body.targets.map((item) => (Object.prototype.hasOwnProperty.call(item, 'range_cm') ? '1d' : '2d')));
    if (kinds.size > 1) return 'mixed_representation';
  }
  return null;
}

export function nextRevision(current) {
  if (typeof current !== 'string' || !/^[0-9]+$/.test(current)) throw new Error('bad revision');
  return (BigInt(current) + 1n).toString();
}

export function isSideEffect(code) {
  return code === 0x0022 || code === 0x0041 || code === 0x0051 || code === 0x0052;
}
