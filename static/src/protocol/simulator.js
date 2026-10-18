import { createHash } from 'node:crypto';
import { ProtocolClient } from './client.js';
import { nextRevision, telemetryIssue, validateRequest, wifiPasswordIssue } from './contract.js';
import { encodeFrame, FrameParser } from './codec.js';
import { CODE, ERROR, KIND } from './limits.js';
import { polygonIssues } from './geometry.js';
import { encodeUtf8 } from './utf8.js';

const PAGE = 2;

export class SimulatedDevice {
  constructor(options = {}) {
    this.profile = options.profile || 'r60';
    this.clock = options.clock;
    this.parser = new FrameParser();
    this.listeners = [];
    this.session = null;
    this.nextSession = 0x1000;
    this.cache = [];
    this.seenMax = 0;
    this.commits = [];
    this.revision = '1';
    this.config = defaultConfig(this.profile);
    this.writeCount = 0;
    this.executeCount = 0;
    this.subscriptions = new Set();
    this.streamLimits = new Map();
    this.budgetBps = 8000;
    this.windowStart = 0;
    this.windowBytes = 0;
    this.windowTelemetry = 0;
    this.heldTelemetry = null;
    this.heldEvents = [];
    this.sessionTimer = null;
    this.releaseTimer = null;
    this.sentTelemetry = 0;
    this.sentEventBytes = 0;
    this.jobs = [];
    this.logs = [];
    this.telemetry = null;
    this.queue = [];
    this.rpcTimes = [];
    this.tokens = 32;
    this.lastTokenMs = 0;
    this.faults = { dropResponses: 0, delayMs: 0, badFrames: 0, disconnect: false };
    this.stats = { invalid: 0, dropped: 0, logsDropped: 0, telemetryCoalesced: 0, txOverflow: 0 };
    this.sentOrder = [];
    this.bootId = 'fedcba9876543210fedcba9876543210';
    this.uptime = 1000;
    this.capRevision = 'r60-draft-source';
    this.capabilities = options.capabilities || defaultCapabilities(this.profile);
    this.externalChanges = 0;
  }

  onWire(listener) {
    this.listeners.push(listener);
  }

  ingest(bytes, now = this.clock ? this.clock.now() : 0) {
    if (this.faults.disconnect) return;
    const parsed = this.parser.push(bytes, now);
    for (const frame of parsed.frames) this.onFrame(frame, now);
  }

  inject(bytes) {
    this.emit(bytes);
  }

  disconnect() {
    this.faults.disconnect = true;
    this.expire();
  }

  bumpExternal(key, value) {
    this.config[key] = value;
    this.revision = nextRevision(this.revision);
    this.externalChanges++;
    this.offerEvent(CODE.CONFIG_CHANGED, { revision: this.revision, changed_keys: [key], origin: 'ha', op_id: null });
  }

  emitTelemetry(snapshot) {
    const now = this.clock ? this.clock.now() : 0;
    this.poll(now);
    const body = { ...snapshot, origin: 'simulation' };
    if (telemetryIssue(body)) {
      this.stats.invalid++;
      return this.sentTelemetry;
    }
    this.telemetry = body;
    this.offerEvent(CODE.TELEMETRY, body);
    return this.sentTelemetry;
  }

  now() {
    return this.clock ? this.clock.now() : 0;
  }

  sessionAlive(now = this.now()) {
    if (!this.session) return false;
    if (now - this.session.touched >= 15000) {
      this.expire();
      return false;
    }
    return true;
  }

  poll(now = this.now()) {
    if (!this.sessionAlive(now)) return;
    this.releaseEvents(now);
  }

  expire() {
    this.clearSessionTimer();
    this.clearReleaseTimer();
    this.session = null;
    this.subscriptions.clear();
    this.streamLimits.clear();
    this.heldTelemetry = null;
    this.heldEvents = [];
    this.queue = this.queue.filter((item) => item.priority === 0 && item.wire);
  }

  clearSessionTimer() {
    if (this.sessionTimer != null && this.clock?.clearTimeout) this.clock.clearTimeout(this.sessionTimer);
    this.sessionTimer = null;
  }

  clearReleaseTimer() {
    if (this.releaseTimer != null && this.clock?.clearTimeout) this.clock.clearTimeout(this.releaseTimer);
    this.releaseTimer = null;
  }

  armSessionTimer() {
    this.clearSessionTimer();
    if (!this.session || !this.clock?.setTimeout) return;
    const stamp = this.session.touched;
    this.sessionTimer = this.clock.setTimeout(() => {
      this.sessionTimer = null;
      if (!this.session || this.session.touched !== stamp) return;
      this.expire();
    }, 15000);
  }

  armReleaseTimer(now) {
    this.clearReleaseTimer();
    if (!this.heldEvents.length || !this.clock?.setTimeout || !this.session) return;
    const wait = Math.max(1, this.windowStart + 1000 - now);
    this.releaseTimer = this.clock.setTimeout(() => {
      this.releaseTimer = null;
      const at = this.now();
      if (!this.sessionAlive(at)) return;
      this.releaseEvents(at);
    }, wait);
  }

  onFrame(frame, now) {
    if (frame.kind !== KIND.request) return;
    this.refill(now);
    this.rpcTimes = this.rpcTimes.filter((at) => now - at < 1000);
    if (this.rpcTimes.length >= 10) {
      this.reply(frame, errorBody(ERROR.RATE_LIMITED, 'Rate limited', { retry_after_ms: 1000 }));
      return;
    }
    this.rpcTimes.push(now);
    if (frame.code === CODE.HELLO) return this.hello(frame);
    if (!this.session || frame.sessionId !== this.session.id) {
      this.stats.invalid++;
      return;
    }
    if (now - this.session.touched >= 15000) {
      this.expire();
      this.stats.invalid++;
      return;
    }
    this.session.touched = now;
    this.armSessionTimer();
    if (frame.requestId === 0 || frame.requestId > 0xfffffffe) {
      this.reply(frame, errorBody(ERROR.INVALID_ARGUMENT, 'Bad request id'));
      return;
    }
    const digest = sha(frame.payload);
    const cached = this.cache.find((item) => item.id === frame.requestId);
    if (cached) {
      if (cached.digest === digest && cached.code === frame.code) {
        this.emit(cached.wire);
        return;
      }
      this.reply(frame, errorBody(ERROR.ID_REUSE, 'Request id reuse'));
      return;
    }
    if (frame.requestId <= this.seenMax) {
      this.reply(frame, errorBody(ERROR.REQUEST_EXPIRED, 'Request expired'));
      return;
    }
    const verdict = validateRequest(frame.code, frame.json);
    if (!verdict.ok) {
      this.stats.invalid++;
      return this.reply(frame, errorBody(verdict.code, verdict.message, verdict.details));
    }
    const produced = this.dispatch(frame, now);
    if (!produced) return;
    this.seenMax = frame.requestId;
    this.remember(frame, digest, produced.wire);
    if (this.faults.dropResponses > 0) {
      this.faults.dropResponses--;
      this.stats.dropped++;
      return;
    }
    if (this.faults.delayMs > 0) {
      const delay = this.faults.delayMs;
      this.clock.setTimeout(() => this.emit(produced.wire), delay);
      return;
    }
    this.queue.push({ priority: 0, wire: produced.wire });
    this.flush();
  }

  hello(frame) {
    const body = frame.json;
    const verdict = validateRequest(CODE.HELLO, body);
    if (!verdict.ok) {
      const code = body?.protocol?.major !== 1 ? ERROR.VERSION_UNSUPPORTED : body?.max_payload < 4096 ? ERROR.LIMIT_UNSUPPORTED : verdict.code;
      this.reply(frame, errorBody(code, verdict.message), 0);
      return;
    }
    if (!body || body.protocol?.major !== 1 || body.max_payload < 4096) {
      this.reply(frame, errorBody(body?.max_payload < 4096 ? ERROR.LIMIT_UNSUPPORTED : ERROR.VERSION_UNSUPPORTED, 'Unsupported'), 0);
      return;
    }
    if (this.session && this.session.nonce === body.nonce) {
      this.reply(frame, ok(this.helloResult(body.nonce)), this.session.id);
      return;
    }
    this.session = { id: this.nextSession++, nonce: body.nonce, touched: this.clock ? this.clock.now() : 0 };
    this.armSessionTimer();
    this.cache = [];
    this.seenMax = 1;
    this.subscriptions.clear();
    this.streamLimits.clear();
    this.heldTelemetry = null;
    this.heldEvents = [];
    this.clearReleaseTimer();
    this.queue = this.queue.filter((item) => item.priority === 0 && item.wire);
    this.reply(frame, ok(this.helloResult(body.nonce)), this.session.id);
  }

  helloResult(nonce) {
    return {
      nonce,
      protocol: { major: 1, minor: 0 },
      boot_id: this.bootId,
      session_ttl_ms: 15000,
      limits: { max_payload: 4096, rpc_inflight: 1, max_targets: this.profile === 'multi' ? 3 : 1, event_budget_bps: 8000 },
      identity: {
        device_id: 'sim-local-device',
        configured_model: this.profile === 'range1d' ? 'range-sim' : 'r60abd1',
        dimension: this.profile === 'range1d' ? '1D' : '2D',
        firmware_version: 'simulation',
      },
      cap_revision: this.capRevision,
    };
  }

  dispatch(frame, now) {
    const body = frame.json || {};
    switch (frame.code) {
      case CODE.PING:
        this.executeCount++;
        return this.make(frame, ok({ uptime_ms: this.uptime + now }));
      case CODE.SESSION_CLOSE: {
        const sid = this.session.id;
        const made = this.make(frame, ok({ closed: true }), sid);
        this.expire();
        return made;
      }
      case CODE.DEVICE_INFO:
        return this.make(frame, ok({
          device_id: 'sim-local-device',
          boot_id: this.bootId,
          configured_model: this.profile === 'range1d' ? 'range-sim' : 'r60abd1',
          dimension: this.profile === 'range1d' ? '1D' : '2D',
          firmware_version: 'simulation',
          git_sha: null,
          release_channel: 'development',
          build_profile: 'simulation',
          host_protocol: 'MWCP/1',
          radar_identity: null,
        }));
      case CODE.CAPABILITIES_LIST:
        return this.page(frame, this.capabilities, this.capRevision, (items, next) => ({ revision: this.capRevision, items, next_cursor: next }));
      case CODE.CONFIG_READ:
        return this.page(frame, Object.entries(this.config).map(([key, value]) => ({ key, value })), this.revision, (items, next) => ({ revision: this.revision, items, next_cursor: next }));
      case CODE.CONFIG_VALIDATE:
        return this.make(frame, this.validate(body));
      case CODE.CONFIG_COMMIT:
        return this.make(frame, this.commit(frame, body));
      case CODE.COMMIT_STATUS:
        return this.make(frame, this.commitStatus(body.op_id));
      case CODE.SUBSCRIBE:
        this.budgetBps = Math.min(body.event_budget_bps, 8000);
        for (const stream of body.streams || []) {
          this.subscriptions.add(stream.id);
          this.streamLimits.set(stream.id, stream.max_rate_hz);
        }
        return this.make(frame, ok({ streams: body.streams, event_budget_bps: this.budgetBps }));
      case CODE.UNSUBSCRIBE: {
        const removed = [];
        for (const id of body.streams || []) {
          if (this.subscriptions.delete(id)) removed.push(id);
          this.streamLimits.delete(id);
        }
        if (!this.subscriptions.has('telemetry')) this.heldTelemetry = null;
        this.heldEvents = (this.heldEvents || []).filter((item) => this.subscriptions.has(item.stream));
        return this.make(frame, ok({ removed }));
      }
      case CODE.STATUS_GET:
        return this.make(frame, ok(this.status(now)));
      case CODE.ACTIONS_LIST:
        return this.page(frame, defaultActions(), 'actions-draft', (items, next) => ({ revision: 'actions-draft', items, next_cursor: next }));
      case CODE.JOB_GET:
        return this.make(frame, ok(this.job(body)));
      default:
        this.stats.invalid++;
        return this.make(frame, errorBody(ERROR.UNSUPPORTED, 'Unsupported'));
    }
  }

  page(frame, items, revision, shape) {
    const cursor = frame.json.cursor;
    const prefix = `${this.session.id}:`;
    if (cursor && !cursor.startsWith(prefix)) return this.make(frame, errorBody(ERROR.INVALID_ARGUMENT, 'Bad cursor'));
    const bodyCursor = cursor ? cursor.slice(prefix.length) : null;
    if (bodyCursor && !bodyCursor.endsWith(`:${revision}`)) return this.make(frame, errorBody(ERROR.REVISION_CONFLICT, 'Snapshot changed', { current_revision: revision }));
    const start = bodyCursor ? Number(bodyCursor.split(':')[0]) : 0;
    const slice = items.slice(start, start + PAGE);
    const next = start + PAGE < items.length ? `${this.session.id}:${start + PAGE}:${revision}` : null;
    return this.make(frame, ok(shape(slice, next)));
  }

  validate(body) {
    if (body.base_revision !== this.revision) return errorBody(ERROR.REVISION_CONFLICT, 'Configuration changed', { current_revision: this.revision });
    const issues = configIssues(body.changes || {}, this.capabilities);
    if (issues) return issues;
    return ok({ valid: true, base_revision: this.revision, restart_required: false });
  }

  commit(frame, body) {
    const digest = sha(frame.payload);
    const prior = this.commits.find((item) => item.opId === body.op_id);
    if (prior && prior.digest === digest) return ok(prior.result);
    if (prior) return errorBody(ERROR.OP_ID_REUSE, 'Op id reuse');
    if (this.tokens <= 0) return errorBody(ERROR.RATE_LIMITED, 'Write limited', { retry_after_ms: 1000 });
    const validated = this.validate(body);
    if (!validated.ok) return validated;
    this.tokens--;
    this.writeCount++;
    this.executeCount++;
    Object.assign(this.config, body.changes);
    this.revision = nextRevision(this.revision);
    const result = { op_id: body.op_id, revision: this.revision, persisted: true, restart_required: false };
    this.commits.push({ opId: body.op_id, digest, result });
    if (this.commits.length > 4) this.commits.shift();
    return ok(result);
  }

  commitStatus(opId) {
    const prior = this.commits.find((item) => item.opId === opId);
    return ok({ found: Boolean(prior), revision: prior ? prior.result.revision : null, current_revision: this.revision });
  }

  status(now) {
    return {
      uptime_ms: this.uptime + now,
      radar_link: 'healthy',
      last_radar_frame_ms: now,
      config_revision: this.revision,
      config_storage: 'healthy',
      active_jobs: [],
      counters: {
        rx_frames: this.stats.invalid,
        rx_crc_errors: 0,
        rx_oversize: 0,
        invalid_requests: this.stats.invalid,
        radar_frames: 1,
        radar_errors: 0,
        telemetry_coalesced: this.stats.telemetryCoalesced,
        logs_dropped: this.stats.logsDropped,
        tx_overflow: this.stats.txOverflow,
      },
    };
  }

  job(body) {
    return {
      job_id: body.job_id || 'missing',
      op_id: body.op_id || null,
      action_id: 'unknown',
      state: 'unknown',
      stage: null,
      progress: null,
      started_ms: null,
      finished_ms: null,
      result: null,
      error: null,
    };
  }

  remember(frame, digest, wire) {
    this.cache.push({ id: frame.requestId, code: frame.code, digest, wire });
    if (this.cache.length > 4) this.cache.shift();
  }

  make(frame, payload, sessionId = this.session.id) {
    const encoded = encodeFrame({
      kind: KIND.response,
      sessionId,
      requestId: frame.requestId,
      code: frame.code,
      wireSeq: frame.requestId,
      payload: encodeUtf8(JSON.stringify(payload)),
    });
    if (!encoded.ok) throw new Error(`encode ${encoded.error}`);
    return { wire: encoded.wire, payload };
  }

  reply(frame, payload, sessionId = this.session ? this.session.id : 0) {
    const made = this.make(frame, payload, sessionId);
    if (!made) return;
    this.queue.push({ priority: 0, wire: made.wire });
    this.flush();
  }

  enqueue(code, payload) {
    this.offerEvent(code, payload);
  }

  offerEvent(code, payload) {
    const stream = streamFor(code);
    const now = this.now();
    if (!stream || !this.sessionAlive(now) || !this.subscriptions.has(stream)) {
      this.stats.eventsSuppressed = (this.stats.eventsSuppressed || 0) + 1;
      return;
    }
    if (!this.heldEvents) this.heldEvents = [];
    const priority = code === CODE.LOG ? 3 : code === CODE.TELEMETRY ? 2 : 1;
    if (code === CODE.CONFIG_CHANGED || code === CODE.STATUS_CHANGED || code === CODE.TELEMETRY) {
      const index = this.heldEvents.findIndex((item) => item.code === code);
      if (index >= 0) {
        if (code === CODE.CONFIG_CHANGED) {
          const keys = new Set([...(this.heldEvents[index].payload.changed_keys || []), ...(payload.changed_keys || [])]);
          payload = { ...payload, changed_keys: [...keys] };
        }
        this.heldEvents[index] = { code, payload, stream, priority };
        if (code === CODE.TELEMETRY) this.stats.telemetryCoalesced++;
        else this.stats.eventsCoalesced = (this.stats.eventsCoalesced || 0) + 1;
        return;
      }
    }
    if (code === CODE.LOG && this.heldEvents.filter((item) => item.code === CODE.LOG).length >= 8) {
      this.stats.logsDropped++;
      this.heldEvents.splice(this.heldEvents.findIndex((item) => item.code === CODE.LOG), 1);
    }
    if (this.heldEvents.length >= 16) {
      this.stats.txOverflow++;
      return;
    }
    this.heldEvents.push({ code, payload, stream, priority });
    this.releaseEvents(now);
  }

  flush() {
    const rpc = this.queue.filter((item) => item.priority === 0 && item.wire);
    this.queue = this.queue.filter((item) => !(item.priority === 0 && item.wire));
    for (const item of rpc) {
      this.sentOrder.push(0);
      this.emit(item.wire);
    }
    this.releaseEvents(this.clock ? this.clock.now() : 0);
  }

  releaseEvents(now) {
    if (!this.sessionAlive(now)) return;
    if (now - this.windowStart >= 1000) {
      this.windowStart = now;
      this.windowBytes = 0;
      this.windowFrames = 0;
      this.streamFrames = {};
    }
    if (!this.heldEvents) this.heldEvents = [];
    this.heldEvents.sort((a, b) => a.priority - b.priority);
    const remain = [];
    for (const item of this.heldEvents) {
      if (!this.session || !this.subscriptions.has(item.stream)) {
        this.stats.eventsSuppressed = (this.stats.eventsSuppressed || 0) + 1;
        continue;
      }
      const hz = this.streamLimits.get(item.stream) ?? 0;
      const encoded = encodeFrame({
        kind: KIND.event,
        sessionId: this.session.id,
        requestId: 0,
        code: item.code,
        wireSeq: 1,
        payload: encodeUtf8(JSON.stringify(item.payload)),
      });
      if (!encoded.ok) continue;
      const tooBig = encoded.wire.length > this.budgetBps;
      const overBudget = this.windowBytes + encoded.wire.length > this.budgetBps;
      const overRate = hz > 0 && (this.streamFrames?.[item.stream] || 0) >= hz;
      if (tooBig) {
        this.stats.txOverflow++;
        continue;
      }
      if (overBudget || overRate) {
        remain.push(item);
        continue;
      }
      this.sentOrder.push(item.priority);
      this.emit(encoded.wire);
      this.windowBytes += encoded.wire.length;
      this.windowFrames = (this.windowFrames || 0) + 1;
      this.streamFrames = this.streamFrames || {};
      this.streamFrames[item.stream] = (this.streamFrames[item.stream] || 0) + 1;
      this.sentEventBytes += encoded.wire.length;
      if (item.code === CODE.TELEMETRY) this.sentTelemetry++;
    }
    this.heldEvents = remain;
    if (remain.length) this.armReleaseTimer(now);
    else this.clearReleaseTimer();
  }

  emit(bytes) {
    for (const listener of this.listeners) listener(bytes);
  }

  refill(now) {
    const elapsed = now - this.lastTokenMs;
    if (elapsed >= 1000) {
      this.tokens = Math.min(32, this.tokens + Math.floor(elapsed / 1000));
      this.lastTokenMs = now;
    }
  }
}

export function link(clock, deviceOptions = {}, chunk = 0) {
  const device = new SimulatedDevice({ ...deviceOptions, clock });
  if (clock?.advance) {
    const advance = clock.advance.bind(clock);
    clock.advance = (ms) => {
      advance(ms);
      device.poll(clock.now());
    };
  }
  let client = null;
  const transport = {
    write(bytes) {
      for (const part of split(bytes, chunk)) device.ingest(part);
    },
    onData() {},
    close() {
      device.disconnect();
    },
  };
  client = new ProtocolClient(transport, { clock });
  device.onWire((bytes) => {
    for (const part of split(bytes, chunk)) client.ingest(part);
  });
  return { client, device };
}

export function couple(client, device, { chunk = 0 } = {}) {
  device.onWire((bytes) => deliver(client, bytes, chunk));
  return {
    write(bytes) {
      deliverDevice(device, bytes, chunk);
    },
    onData() {},
    close() {
      device.disconnect();
    },
  };
}

function deliver(client, bytes, chunk) {
  for (const part of split(bytes, chunk)) client.ingest(part);
}

function deliverDevice(device, bytes, chunk) {
  for (const part of split(bytes, chunk)) device.ingest(part);
}

function streamFor(code) {
  if (code === CODE.TELEMETRY) return 'telemetry';
  if (code === CODE.STATUS_CHANGED) return 'status';
  if (code === CODE.CONFIG_CHANGED) return 'config';
  if (code === CODE.JOB_CHANGED) return 'jobs';
  if (code === CODE.LOG) return 'logs';
  return '';
}

function split(bytes, chunk) {
  if (!chunk) return [bytes];
  const parts = [];
  for (let i = 0; i < bytes.length; i += chunk) parts.push(bytes.subarray(i, i + chunk));
  return parts;
}

function ok(result) {
  return { ok: true, result };
}

function errorBody(code, message, details) {
  return { ok: false, error: { code, message, ...(details ? { details } : {}) } };
}

function sha(bytes) {
  return createHash('sha256').update(bytes).digest('hex');
}

function defaultConfig(profile) {
  if (profile === 'range1d') return { 'range.window_cm': { min: 0, max: 300 } };
  return {
    'install.x_cm': 0,
    'install.y_cm': 0,
    'install.z_cm': 220,
    'install.yaw_deg': 0,
    'install.pitch_deg': 0,
    'install.roll_deg': 0,
    'geometry.boundary_cm': null,
  };
}

function defaultCapabilities(profile) {
  if (profile === 'range1d') {
    return [
      { kind: 'feature', id: 'distance.cm', supported: true, expected_interval_ms: null, stale_after_ms: null },
      { kind: 'feature', id: 'position.xy', supported: false },
    ];
  }
  if (profile === 'unsupported') return [{ kind: 'feature', id: 'position.xy', supported: false }];
  return [
    { kind: 'feature', id: 'presence', supported: true, expected_interval_ms: null, stale_after_ms: null },
    { kind: 'feature', id: 'position.xy', supported: true, max_targets: profile === 'multi' ? 3 : 1, target_id_stable: false, expected_interval_ms: null, stale_after_ms: null },
    { kind: 'config', id: 'install.x_cm', type: 'number', unit: 'cm', minimum: -2000, maximum: 2000, step: 1, writable: true, domain: 'host', label_key: 'install.x', restart_required: false },
    { kind: 'config', id: 'geometry.boundary_cm', type: 'array', writable: true, domain: 'host', label_key: 'geometry.boundary', restart_required: false, schema_id: 'polygon.xy.v1', min_items: 3, max_items: 64 },
  ];
}

function defaultActions() {
  return [{ action_id: 'device.restart', verification: 'none', confirm: true, resource: 'restart', deadline_ms: 8000 }];
}

function configIssues(changes, capabilities) {
  const keys = Object.keys(changes);
  if (!keys.length || keys.length > 32) return errorBody(ERROR.INVALID_ARGUMENT, 'Bad changes');
  for (const key of keys) {
    if (key === '__proto__' || key === 'constructor' || key === 'prototype') return errorBody(ERROR.UNKNOWN_FIELD, 'Bad field', { field: key });
    const cap = capabilities.find((item) => item.kind === 'config' && item.id === key);
    if (!cap || !cap.writable) return errorBody(ERROR.UNSUPPORTED, 'Unsupported field');
    const value = changes[key];
    if (cap.type === 'number' && (typeof value !== 'number' || value < cap.minimum || value > cap.maximum)) {
      return errorBody(ERROR.OUT_OF_RANGE, 'Out of range', { field: key });
    }
    if (key === 'geometry.boundary_cm' && value != null) {
      const issues = polygonIssues(value);
      if (issues.length) return errorBody(ERROR.INVALID_ARGUMENT, 'Bad polygon', { errors: issues.slice(0, 16) });
    }
  }
  return null;
}

export function observation(kind) {
  if (kind === 'empty') {
    return { source_seq: 1, sent_ms: 10, origin: 'simulation', presence: { value: false, quality: 'valid', sample_ms: 10 }, targets_quality: 'valid', targets_ms: 10, targets: [] };
  }
  if (kind === 'unknown') {
    return { source_seq: 2, sent_ms: 20, origin: 'simulation', presence: { value: null, quality: 'unknown', sample_ms: null }, targets_quality: 'unknown', targets_ms: null, targets: null };
  }
  if (kind === 'zero') {
    return { source_seq: 3, sent_ms: 30, origin: 'simulation', presence: { value: true, quality: 'valid', sample_ms: 30 }, targets_quality: 'valid', targets_ms: 30, targets: [{ id: '0', local_cm: [0, 0], room_cm: [0, 0], position_quality: 'valid', position_ms: 30, boundary: 'inside', speed_cm_s: null }] };
  }
  if (kind === '1d') {
    return { source_seq: 4, sent_ms: 40, origin: 'simulation', presence: { value: true, quality: 'valid', sample_ms: 40 }, targets_quality: 'valid', targets_ms: 40, targets: [{ id: '0', range_cm: 150, position_quality: 'valid', position_ms: 40, boundary: 'not_applicable', speed_cm_s: null }] };
  }
  if (kind === 'multi') {
    return {
      source_seq: 5,
      sent_ms: 50,
      origin: 'simulation',
      presence: { value: true, quality: 'valid', sample_ms: 40 },
      targets_quality: 'valid',
      targets_ms: 50,
      targets: [0, 1, 2].map((id) => ({ id: String(id), local_cm: [id * 10, 100], room_cm: [id * 10, 100], position_quality: 'valid', position_ms: 50, boundary: 'inside', speed_cm_s: null })),
    };
  }
  return { source_seq: 6, sent_ms: 60, origin: 'simulation', presence: { value: true, quality: 'valid', sample_ms: 20 }, targets_quality: 'valid', targets_ms: 60, targets: [{ id: '0', local_cm: [30, 150], room_cm: [130, 150], position_quality: 'valid', position_ms: 60, boundary: 'inside', speed_cm_s: null }], metrics: { breath_rate: { value: null, quality: 'unknown', sample_ms: null } } };
}
