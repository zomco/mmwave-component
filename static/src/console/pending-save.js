/**
 * A timed-out CONFIG_COMMIT may already have been applied.
 * Keep the original op_id, base_revision and changes. Never mint a new
 * op to "retry", and never let a different device clear this record.
 */

export const SAVE = {
  idle: 'idle',
  editing: 'editing',
  validating: 'validating',
  committing: 'committing',
  reading: 'reading',
  recovering: 'recovering',
  persisted: 'persisted',
  conflict: 'conflict',
  unknown: 'unknown',
  failed: 'failed',
};

const FLOW_LOCKED = new Set([SAVE.unknown, SAVE.committing, SAVE.validating, SAVE.reading, SAVE.recovering]);

const SECRET = /pass(word|phrase)|token|secret|authorization/i;

export function newOpId(randomBytes) {
  const bytes = (randomBytes || defaultRandom)(16);
  const hex = [...bytes].map((b) => b.toString(16).padStart(2, '0')).join('');
  return hex.slice(0, 8) + '-' + hex.slice(8, 12) + '-' + hex.slice(12, 16) + '-' + hex.slice(16, 20) + '-' + hex.slice(20);
}

function defaultRandom(size) {
  const bytes = new Uint8Array(size);
  if (globalThis.crypto && globalThis.crypto.getRandomValues) globalThis.crypto.getRandomValues(bytes);
  else for (let i = 0; i < size; i += 1) bytes[i] = Math.floor(Math.random() * 256);
  return bytes;
}

export function deviceKey(identity) {
  if (!identity) return null;
  if (identity.device_id) return 'dev:' + identity.device_id;
  if (identity.boot_id) return 'boot:' + identity.boot_id;
  return null;
}

export function createSaveState() {
  return {
    phase: SAVE.idle,
    deviceKey: null,
    sessionId: null,
    baseRevision: null,
    opId: null,
    changes: null,
    message: null,
    readback: null,
    found: null,
  };
}

export function saveFlowLocked(state) {
  return Boolean(state && FLOW_LOCKED.has(state.phase));
}

export function beginEdit(state) {
  if (saveFlowLocked(state)) return state;
  return { ...state, phase: SAVE.editing, message: null, readback: null };
}

export function rememberDevice(state, identity, sessionId) {
  const key = deviceKey(identity);
  if (state.phase === SAVE.unknown && state.deviceKey && key && state.deviceKey !== key) return state;
  if (state.deviceKey && key && state.deviceKey !== key && state.phase !== SAVE.unknown) {
    return { ...createSaveState(), deviceKey: key, sessionId };
  }
  return { ...state, deviceKey: key, sessionId: sessionId != null ? sessionId : state.sessionId };
}

/** Prepare one commit. Refuses to replace an unresolved pending write. */
export function armCommit(state, input) {
  if (state.phase === SAVE.unknown || state.phase === SAVE.committing) {
    return { ok: false, reason: 'pending_blocks_new_save', state };
  }
  if (!input || !input.opId || !input.baseRevision || !input.changes || typeof input.changes !== 'object') {
    return { ok: false, reason: 'incomplete_commit', state };
  }
  return {
    ok: true,
    state: {
      ...state,
      phase: SAVE.committing,
      baseRevision: input.baseRevision,
      opId: input.opId,
      changes: input.changes,
      sessionId: input.sessionId != null ? input.sessionId : state.sessionId,
      message: null,
      readback: null,
      found: null,
    },
  };
}

export function noteValidationFailure(state, message) {
  if (state.phase === SAVE.unknown || state.phase === SAVE.committing || state.phase === SAVE.reading || state.phase === SAVE.recovering) return state;
  return { ...state, phase: SAVE.failed, message: message || 'validation_failed' };
}

/**
 * Interpret a CONFIG_COMMIT response that already passed ProtocolClient checks.
 * unknown:true is the client's timeout signal — the write may have landed.
 */
export function applyCommitResult(state, frame) {
  if (state.phase !== SAVE.committing) return state;
  if (!frame || frame.unknown) {
    return { ...state, phase: SAVE.unknown, message: 'save_result_unconfirmed', found: null };
  }
  const body = frame.json;
  if (!body || body.ok !== true) {
    const code = body && body.error ? body.error.code : null;
    if (code === 'REVISION_CONFLICT') {
      return { ...state, phase: SAVE.conflict, message: 'revision_conflict' };
    }
    return { ...state, phase: SAVE.failed, message: code || 'commit_failed', opId: null };
  }
  const result = body.result || {};
  if (result.op_id !== state.opId) return state;
  if (result.revision == null || result.persisted !== true) {
    return { ...state, phase: SAVE.unknown, message: 'save_result_unconfirmed' };
  }
  return {
    ...state,
    phase: SAVE.persisted,
    baseRevision: String(result.revision),
    message: 'persisted',
    found: true,
  };
}

/**
 * COMMIT_STATUS may confirm the original op. found:false is NOT "not executed".
 * A mismatched session, code or body must not clear the pending record.
 */
export function applyStatusResult(state, frame, options) {
  const sessionId = options ? options.sessionId : undefined;
  if (state.phase !== SAVE.unknown && state.phase !== SAVE.committing && state.phase !== SAVE.recovering) {
    return { accepted: false, state, reason: 'not_pending' };
  }
  if (!frame || frame.unknown) return { accepted: false, state, reason: 'no_frame' };
  if (frame.kind != null && frame.kind !== 2) return { accepted: false, state, reason: 'wrong_kind' };
  if (frame.code != null && frame.code !== 0x0023) return { accepted: false, state, reason: 'wrong_code' };
  if (sessionId != null && frame.sessionId != null && frame.sessionId !== sessionId) {
    return { accepted: false, state, reason: 'wrong_session' };
  }
  const body = frame.json;
  if (!body || typeof body !== 'object' || body.ok !== true || !body.result) {
    return { accepted: false, state, reason: 'invalid_body' };
  }
  const result = body.result;
  if (options && options.deviceKey && state.deviceKey && options.deviceKey !== state.deviceKey) {
    return { accepted: false, state, reason: 'wrong_device' };
  }
  if (result.op_id != null && result.op_id !== state.opId) return { accepted: false, state, reason: 'wrong_op' };
  if (result.found === false) {
    return {
      accepted: false,
      state: { ...state, phase: SAVE.unknown, found: false, message: 'status_not_found_still_unknown' },
      reason: 'found_false',
    };
  }
  if (result.found !== true) return { accepted: false, state, reason: 'found_missing' };
  if (result.revision != null) {
    return {
      accepted: true,
      state: {
        ...state,
        phase: SAVE.persisted,
        baseRevision: String(result.revision),
        message: 'confirmed_by_status',
        found: true,
      },
    };
  }
  return { accepted: false, state: { ...state, phase: SAVE.unknown, found: true, message: 'status_incomplete' }, reason: 'incomplete_status' };
}

/** Explicit abandon does not claim the original write never ran. */
export function abandonTracking(state) {
  if (state.phase !== SAVE.unknown) return { ok: false, state, reason: 'not_unknown' };
  return {
    ok: true,
    state: {
      ...state,
      phase: SAVE.failed,
      message: 'tracking_abandoned_write_may_have_executed',
      abandoned: {
        opId: state.opId,
        baseRevision: state.baseRevision,
        deviceKey: state.deviceKey,
        changes: state.changes,
      },
    },
  };
}

export function markUnknown(state, message) {
  if (!state.opId) return state;
  return { ...state, phase: SAVE.unknown, message: message || 'save_result_unconfirmed', found: state.found };
}

export function pendingSummary(state) {
  if (state.phase !== SAVE.unknown && state.phase !== SAVE.committing) return null;
  return {
    phase: state.phase,
    opId: state.opId,
    baseRevision: state.baseRevision,
    deviceKey: state.deviceKey,
    sessionId: state.sessionId,
    changes: redact(state.changes),
    message: state.message,
    note: 'In-memory only. Closing the browser drops this record. The device may already have applied the write.',
  };
}

export function redact(value) {
  if (typeof value === 'string') return value.replace(/(pass(?:word|phrase)|token|secret|authorization)\s*[:=]\s*\S+/ig, '$1=[redacted]');
  if (Array.isArray(value)) return value.map(redact);
  if (!value || typeof value !== 'object') return value;
  const out = {};
  for (const [key, item] of Object.entries(value)) out[key] = SECRET.test(key) ? '[redacted]' : redact(item);
  return out;
}
