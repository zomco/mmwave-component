import { pointInPolygon, project1D } from '../protocol/transform.js';

export const WINDOW_MS = 10 * 60 * 1000;
export const WINDOW_POINTS = 600;

export function fieldView(field, client, context) {
  if (!field) return { state: 'unknown', value: null, sample_ms: null };
  const quality = client.qualityOf(field, context);
  if (quality !== 'valid') return { state: quality, value: null, sample_ms: field.sample_ms ?? null };
  return { state: 'valid', value: field.value, sample_ms: field.sample_ms ?? null };
}

/** Empty targets are not presence=false. A zero coordinate is a real point, not absence. */
export function interpretObservation(body) {
  if (!body) return { presence: 'unknown', targets: 'none', note: 'no_observation' };
  const presence = body.presence;
  let presenceState = 'unknown';
  if (presence && presence.quality === 'valid' && presence.value === true) presenceState = 'present';
  else if (presence && presence.quality === 'valid' && presence.value === false) presenceState = 'absent';
  else if (presence && presence.quality) presenceState = presence.quality;
  const targets = body.targets;
  let targetState = 'unknown';
  if (targets == null || body.targets_quality === 'unknown' || body.targets_quality === 'unsupported') targetState = body.targets_quality || 'unknown';
  else if (Array.isArray(targets) && targets.length === 0) targetState = 'empty';
  else if (Array.isArray(targets)) targetState = 'points';
  return {
    presence: presenceState,
    targets: targetState,
    origin: body.origin || null,
    simulation: body.origin === 'simulation' || body.origin === 'replay',
  };
}

function metricFields(metrics, context, qualityOf, force) {
  if (!metrics || typeof metrics !== 'object') return [];
  return Object.entries(metrics).map(([key, field]) => {
    if (force) return { key, state: force, value: null };
    const state = qualityOf(field, context);
    return { key, state, value: state === 'valid' ? field.value : null };
  });
}

/**
 * One freshness judgement for presence, targets and vitals.
 * A live view requires the session to still be online. Stored samples then
 * become history, not a current green check. Coordinate 0 and an empty target
 * list stay distinct from absence.
 */
export function assessObservation(body, context, qualityOf) {
  const live = Boolean(context && context.sessionLive && context.protocol === 'online');
  if (!body) {
    return { presence: 'unknown', targets: 'unknown', vitals: 'none', vitalFields: [], live, historical: false };
  }
  if (!live) {
    return {
      presence: body.presence ? 'stale' : 'unknown',
      targets: body.targets != null || body.targets_quality ? 'stale' : 'unknown',
      vitals: body.metrics ? 'stale' : 'none',
      vitalFields: metricFields(body.metrics, context, qualityOf, 'stale'),
      live: false,
      historical: true,
    };
  }
  const judge = typeof qualityOf === 'function' ? qualityOf : () => 'unknown';
  let presence = 'unknown';
  if (body.presence) {
    const quality = judge(body.presence, context);
    if (quality !== 'valid') presence = quality;
    else if (body.presence.value === true) presence = 'present';
    else if (body.presence.value === false) presence = 'absent';
  }
  let targets = 'unknown';
  if (body.targets == null) targets = body.targets_quality || 'unknown';
  else {
    const listQuality = judge({
      quality: body.targets_quality || 'valid',
      sample_ms: body.targets_ms,
      value: body.targets,
    }, context);
    if (listQuality !== 'valid') targets = listQuality;
    else if (!Array.isArray(body.targets) || body.targets.length === 0) targets = 'empty';
    else {
      const qualities = body.targets.map((target) => judge({
        quality: target.position_quality || 'valid',
        sample_ms: target.position_ms,
        value: target.room_cm || target.local_cm || target.range_cm,
      }, context));
      if (qualities.some((item) => item === 'stale')) targets = 'stale';
      else if (qualities.some((item) => item !== 'valid')) targets = qualities.find((item) => item !== 'valid');
      else targets = 'points';
    }
  }
  const vitalFields = metricFields(body.metrics, context, judge, null);
  let vitals = 'none';
  if (vitalFields.length) {
    if (vitalFields.some((item) => item.state === 'stale')) vitals = 'stale';
    else if (vitalFields.some((item) => item.state === 'invalid')) vitals = 'invalid';
    else if (vitalFields.some((item) => item.state === 'valid')) vitals = 'valid';
    else vitals = vitalFields[0].state || 'unknown';
  }
  return { presence, targets, vitals, vitalFields, live: true, historical: false };
}

export function targetRows(body, boundary) {
  const targets = Array.isArray(body && body.targets) ? body.targets : [];
  return targets.map((target, index) => {
    const oneD = Object.prototype.hasOwnProperty.call(target, 'range_cm');
    let outside = target.boundary === 'outside';
    if (!oneD && boundary && Array.isArray(boundary) && boundary.length >= 3 && Array.isArray(target.room_cm)) {
      outside = pointInPolygon(target.room_cm[0], target.room_cm[1], boundary) === false;
    }
    return {
      key: String(target.id != null ? target.id : index),
      idStable: false,
      oneD,
      rangeCm: oneD ? target.range_cm : null,
      local: target.local_cm || null,
      room: target.room_cm || null,
      quality: target.position_quality || 'unknown',
      sampleMs: target.position_ms != null ? target.position_ms : null,
      boundary: outside ? 'outside' : (target.boundary || 'unknown'),
      faded: outside,
    };
  });
}

export function projectRange(rangeCm, install) {
  if (typeof rangeCm !== 'number' || !install) return null;
  return project1D(rangeCm, {
    x: Number(install['install.x_cm'] || 0),
    y: Number(install['install.y_cm'] || 0),
    z: Number(install['install.z_cm'] || 0),
    yaw: Number(install['install.yaw_deg'] || 0),
    pitch: Number(install['install.pitch_deg'] || 0),
    roll: Number(install['install.roll_deg'] || 0),
  });
}

export function pushWindow(window, point, now) {
  const next = window.concat([point]).filter((item) => now - item.at <= WINDOW_MS);
  if (next.length > WINDOW_POINTS) return next.slice(next.length - WINDOW_POINTS);
  return next;
}

export function checksFromSession(session) {
  const snap = session.snapshot();
  const view = typeof session.observationView === 'function'
    ? session.observationView()
    : assessObservation(snap.telemetry, { sessionLive: false, protocol: snap.layers.protocol }, () => 'stale');
  const usb = snap.layers.protocol === 'online' && snap.identity ? 'pass' : snap.layers.protocol === 'handshake' ? 'running' : 'not_run';
  let radar = 'not_run';
  if (!snap.telemetry) radar = snap.layers.radar === 'waiting_first_frame' ? 'waiting' : 'not_run';
  else if (!view.live || view.presence === 'stale' || view.targets === 'stale') radar = 'stale';
  else radar = 'pass';
  const presence = !snap.telemetry ? 'not_run' : view.presence;
  let config = 'not_run';
  if (snap.layers.protocol === 'online') config = snap.configRevision != null ? 'pass' : 'fail';
  else if (snap.configRevision != null) config = 'stale';
  return [
    { id: 'usb', state: usb, evidence: snap.identity ? snap.identity.configured_model : null },
    { id: 'radar', state: radar, evidence: snap.telemetry ? snap.telemetry.source_seq : null },
    { id: 'presence', state: presence, evidence: snap.telemetry ? snap.telemetry.presence : null },
    { id: 'config', state: config, evidence: snap.configRevision },
  ];
}

const SECRET = /pass(word|phrase)|token|secret/i;

export function safeText(value) {
  return String(value == null ? '' : value).replace(/[<>&]/g, (ch) => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;' }[ch]));
}

export function csvCell(value) {
  const text = value == null ? '' : String(value);
  const guarded = /^[=+\-@]/.test(text) ? "'" + text : text;
  return '"' + guarded.replace(/"/g, '""') + '"';
}

export function redactExport(value) {
  if (Array.isArray(value)) return value.map(redactExport);
  if (!value || typeof value !== 'object') return value;
  const out = {};
  for (const [key, item] of Object.entries(value)) out[key] = SECRET.test(key) ? '[redacted]' : redactExport(item);
  return out;
}
