import schema from '../../../docs/protocol/schema/mwcp-v1.schema.json' with { type: 'json' };
import { polygonIssues } from './geometry.js';
import { ERROR } from './limits.js';
import { validate } from './schema.js';
import { encodeUtf8 } from './utf8.js';

const AREA_SLOT_KEYS = new Set(['slot', 'enabled', 'name', 'points_cm']);
const RANGE_WINDOW_KEYS = new Set(['min', 'max']);

export function loadSchema() {
  return schema;
}

export function validateRequest(code, body) {
  const command = schema['x-commands'][String(code)];
  if (!command?.request) return { ok: false, code: ERROR.UNSUPPORTED, message: 'Unsupported' };
  const result = validate(command.request, body, schema);
  if (!result.ok) {
    const unknown = result.errors.some((item) => item.code === 'additionalProperties');
    const outOfRange =
      !unknown &&
      (code === 0x0021 || code === 0x0022) &&
      result.errors.some(
        (item) =>
          (item.code === 'minimum' || item.code === 'maximum') &&
          (item.path.includes('geometry.boundary_cm') || item.path.includes('points_cm') || item.path.includes('range.window_cm')),
      );
    return {
      ok: false,
      code: unknown ? ERROR.UNKNOWN_FIELD : outOfRange ? ERROR.OUT_OF_RANGE : ERROR.INVALID_ARGUMENT,
      message: 'Invalid request',
      details: { errors: result.errors.slice(0, 16) },
    };
  }
  if (code === 0x0021 || code === 0x0022) {
    const cfgIssue = validateConfigChanges(body?.changes);
    if (!cfgIssue.ok) return cfgIssue;
  }
  if (code === 0x0041) {
    if (typeof body?.confirm === 'string' && body.confirm !== body.action_id) {
      return { ok: false, code: ERROR.INVALID_ARGUMENT, message: 'Confirmation must equal action_id', details: { field: 'confirm' } };
    }
  }
  if (code === 0x0052) {
    const wifi = wifiPasswordIssue(body);
    if (wifi) return wifi;
  }
  return { ok: true };
}

export function validateConfigChanges(changes, capabilities = null) {
  if (!changes || typeof changes !== 'object' || Array.isArray(changes)) {
    return { ok: false, code: ERROR.INVALID_ARGUMENT, message: 'Bad changes' };
  }
  const keys = Object.keys(changes);
  if (!keys.length || keys.length > 32) {
    return { ok: false, code: ERROR.INVALID_ARGUMENT, message: 'Bad changes' };
  }
  for (const key of keys) {
    if (key === '__proto__' || key === 'constructor' || key === 'prototype') {
      return { ok: false, code: ERROR.UNKNOWN_FIELD, message: 'Bad field', details: { field: key } };
    }
    const cap = capabilities ? capabilities.find((item) => item.kind === 'config' && item.id === key) : null;
    if (capabilities && (!cap || !cap.writable)) {
      return { ok: false, code: ERROR.UNSUPPORTED, message: 'Unsupported field', details: { field: key } };
    }
    const value = changes[key];
    if (cap) {
      if (cap.type === 'number') {
        if (typeof value !== 'number' || !Number.isFinite(value)) {
          return { ok: false, code: ERROR.INVALID_ARGUMENT, message: 'Bad number', details: { field: key } };
        }
        if (value < cap.minimum || value > cap.maximum) {
          return { ok: false, code: ERROR.OUT_OF_RANGE, message: 'Out of range', details: { field: key } };
        }
        if (typeof cap.step === 'number' && cap.step > 0) {
          const steps = (value - (cap.minimum ?? 0)) / cap.step;
          if (Math.abs(steps - Math.round(steps)) > 1e-6) {
            return { ok: false, code: ERROR.INVALID_ARGUMENT, message: 'Step mismatch', details: { field: key, step: cap.step } };
          }
        }
      }
      if (cap.type === 'boolean' && typeof value !== 'boolean') {
        return { ok: false, code: ERROR.INVALID_ARGUMENT, message: 'Bad boolean', details: { field: key } };
      }
    }
    const schemaId =
      cap?.schema_id ||
      (key === 'geometry.boundary_cm'
        ? 'polygon.xy.v1'
        : key === 'range.window_cm'
          ? 'range.window.v1'
          : key === 'areas.definitions'
            ? 'r60.areas.v1'
            : null);

    if (schemaId === 'range.window.v1') {
      if (!value || typeof value !== 'object' || Array.isArray(value)) {
        return { ok: false, code: ERROR.INVALID_ARGUMENT, message: 'Bad range window', details: { field: key } };
      }
      for (const k of Object.keys(value)) {
        if (!RANGE_WINDOW_KEYS.has(k)) {
          return { ok: false, code: ERROR.UNKNOWN_FIELD, message: 'Unknown field in range window', details: { field: `${key}.${k}` } };
        }
      }
      if (typeof value.min !== 'number' || !Number.isFinite(value.min) || typeof value.max !== 'number' || !Number.isFinite(value.max)) {
        return { ok: false, code: ERROR.INVALID_ARGUMENT, message: 'Bad range window bounds', details: { field: key } };
      }
      if (value.min < 0 || value.min > 600 || value.max < 0 || value.max > 600) {
        return { ok: false, code: ERROR.OUT_OF_RANGE, message: 'Range window out of range', details: { field: key } };
      }
      if (value.min > value.max) {
        return { ok: false, code: ERROR.INVALID_ARGUMENT, message: 'Range min exceeds max', details: { field: key } };
      }
    }

    if (schemaId === 'polygon.xy.v1' && value !== null) {
      const issues = polygonIssues(value, {
        minVertices: cap?.min_items ?? 3,
        maxVertices: cap?.max_items ?? 64,
        minCoord: -2000,
        maxCoord: 2000,
      });
      if (issues.includes('range')) {
        return { ok: false, code: ERROR.OUT_OF_RANGE, message: 'Polygon vertex out of range', details: { field: key, errors: issues.slice(0, 16) } };
      }
      if (issues.length) {
        return { ok: false, code: ERROR.INVALID_ARGUMENT, message: 'Bad polygon', details: { field: key, errors: issues.slice(0, 16) } };
      }
    }

    if (schemaId === 'r60.areas.v1') {
      const minItems = cap?.min_items ?? 0;
      const maxItems = cap?.max_items ?? 3;
      if (!Array.isArray(value) || value.length < minItems || value.length > maxItems) {
        return { ok: false, code: ERROR.INVALID_ARGUMENT, message: 'Bad areas.definitions array', details: { field: key } };
      }
      const seenSlots = new Set();
      for (const slot of value) {
        if (!slot || typeof slot !== 'object' || Array.isArray(slot)) {
          return { ok: false, code: ERROR.INVALID_ARGUMENT, message: 'Bad area slot object', details: { field: key } };
        }
        for (const k of Object.keys(slot)) {
          if (!AREA_SLOT_KEYS.has(k)) {
            return { ok: false, code: ERROR.UNKNOWN_FIELD, message: 'Unknown field in area slot', details: { field: `${key}.${k}` } };
          }
        }
        for (const reqKey of AREA_SLOT_KEYS) {
          if (!Object.prototype.hasOwnProperty.call(slot, reqKey)) {
            return { ok: false, code: ERROR.INVALID_ARGUMENT, message: 'Missing required area slot field', details: { field: `${key}.${reqKey}` } };
          }
        }
        if (!Number.isInteger(slot.slot) || slot.slot < 0 || slot.slot >= maxItems || seenSlots.has(slot.slot)) {
          return { ok: false, code: ERROR.INVALID_ARGUMENT, message: 'Bad or duplicate area slot index', details: { field: key } };
        }
        seenSlots.add(slot.slot);
        if (typeof slot.enabled !== 'boolean' || typeof slot.name !== 'string' || encodeUtf8(slot.name).length > 32) {
          return { ok: false, code: ERROR.INVALID_ARGUMENT, message: 'Bad area slot metadata', details: { field: key } };
        }
        if (!Array.isArray(slot.points_cm)) {
          return { ok: false, code: ERROR.INVALID_ARGUMENT, message: 'Area points_cm must be an array', details: { field: key } };
        }
        if (slot.enabled || slot.points_cm.length > 0) {
          const issues = polygonIssues(slot.points_cm, {
            minVertices: 3,
            maxVertices: 12,
            minCoord: -2000,
            maxCoord: 2000,
          });
          if (issues.includes('range')) {
            return { ok: false, code: ERROR.OUT_OF_RANGE, message: 'Area vertex out of range', details: { field: key, errors: issues.slice(0, 16) } };
          }
          if (issues.length) {
            return { ok: false, code: ERROR.INVALID_ARGUMENT, message: 'Bad area polygon', details: { field: key, errors: issues.slice(0, 16) } };
          }
        }
      }
    }
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

