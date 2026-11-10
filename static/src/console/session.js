import { ProtocolClient } from '../protocol/client.js';
import { createRealClock } from '../protocol/clock.js';
import { CODE } from '../protocol/limits.js';
import { validateConfigChanges } from '../protocol/contract.js';
import { assessObservation, summarizeLayers } from './observe.js';
import {
  SAVE, abandonTracking, applyCommitResult, applyStatusResult, armCommit,
  beginEdit, createSaveState, deviceKey, markUnknown, newOpId, pendingSummary, rememberDevice, redact, saveFlowLocked,
} from './pending-save.js';

const HELLO_WAIT_MS = 8000;
const RECORD_MAX = 240;
const LOG_MAX = 80;

export function supportReport(serial, isSecureContext) {
  if (!isSecureContext) return { ok: false, reason: 'insecure_context' };
  if (!serial || typeof serial.requestPort !== 'function') return { ok: false, reason: 'no_web_serial' };
  return { ok: true, reason: null };
}

function nonce() {
  const bytes = new Uint8Array(16);
  if (globalThis.crypto && globalThis.crypto.getRandomValues) globalThis.crypto.getRandomValues(bytes);
  else for (let i = 0; i < bytes.length; i += 1) bytes[i] = Math.floor(Math.random() * 256);
  return [...bytes].map((b) => b.toString(16).padStart(2, '0')).join('');
}

function emptyLayers() {
  return { port: 'closed', protocol: 'offline', radar: 'unknown', data: 'none', config: SAVE.idle };
}

export class ConsoleSession {
  constructor(options = {}) {
    this.clientFactory = options.clientFactory || ((transport, extras) => new ProtocolClient(transport, extras));
    this.clock = options.clock || createRealClock();
    this.flow = null;
    this.flowSeq = 0;
    this.helloTimeout = options.helloTimeout ?? HELLO_WAIT_MS;
    this.rpcTimeout = options.rpcTimeout ?? 1000;
    this.client = null;
    this.transport = null;
    this.detach = null;
    this.mode = 'hardware';
    this.layers = emptyLayers();
    this.identity = null;
    this.bootId = null;
    this.sessionId = 0;
    this.capabilities = [];
    this.capRevision = null;
    this.configItems = [];
    this.configRevision = null;
    this.draft = null;
    this.edited = Object.create(null);
    this.incomingConfig = null;
    this.fieldErrors = {};
    this.save = createSaveState();
    this.telemetry = null;
    this.telemetryAt = null;
    this.observations = [];
    this.logs = [];
    this.status = null;
    this.wifi = null;
    this.actions = [];
    this.jobs = [];
    this.lastError = null;
    this.connectedAt = null;
    this.generation = 0;
    this.onChange = options.onChange || (() => {});
  }

  now() { return this.clock.now(); }

  beginFlow(kind) {
    if (this.flow) return { ok: false, reason: 'operation_busy' };
    if (kind !== 'recover' && this.save.phase === SAVE.unknown) return { ok: false, reason: 'pending_save' };
    if (this.save.phase === SAVE.committing || this.save.phase === SAVE.validating || this.save.phase === SAVE.reading || this.save.phase === SAVE.recovering) {
      return { ok: false, reason: 'operation_busy' };
    }
    const id = ++this.flowSeq;
    this.flow = { id, kind, generation: this.generation };
    return { ok: true, id };
  }

  ownsFlow(id) {
    return Boolean(this.flow && this.flow.id === id && this.flow.generation === this.generation);
  }

  endFlow(id) {
    if (this.flow && this.flow.id === id) this.flow = null;
  }

  async wait(ms) {
    const wait = Math.max(0, Number(ms) || 0);
    if (this.clock && typeof this.clock.advance === 'function') {
      this.clock.advance(wait);
      return;
    }
    await new Promise((resolve) => {
      if (this.clock && this.clock.setTimeout) this.clock.setTimeout(resolve, wait);
      else setTimeout(resolve, wait);
    });
  }

  async pace() {
    const now = this.now();
    this.rpcAt = (this.rpcAt || []).filter((at) => now - at < 1000);
    if (this.rpcAt.length < 8) {
      this.rpcAt.push(now);
      return;
    }
    await this.wait(1000 - (now - this.rpcAt[0]) + 1);
    const after = this.now();
    this.rpcAt = (this.rpcAt || []).filter((at) => after - at < 1000);
    this.rpcAt.push(after);
  }

  async call(run, retry = true) {
    let last;
    for (let attempt = 0; attempt < (retry ? 4 : 1); attempt += 1) {
      await this.pace();
      last = await run();
      const code = last && last.json && last.json.ok === false && last.json.error ? last.json.error.code : null;
      if (code !== 'RATE_LIMITED' || !retry) return last;
      const details = last.json.error.details || {};
      await this.wait(details.retry_after_ms || 1000);
    }
    return last;
  }

  snapshot() {
    return {
      mode: this.mode,
      layers: { ...this.layers, config: this.save.phase },
      identity: this.identity,
      bootId: this.bootId,
      sessionId: this.sessionId,
      sessionLive: Boolean(this.client && this.client.sessionLive),
      capabilities: this.capabilities,
      capRevision: this.capRevision,
      configItems: this.configItems,
      configRevision: this.configRevision,
      draft: this.draft,
      incomingConfig: this.incomingConfig,
      fieldErrors: this.fieldErrors,
      save: this.save,
      pending: pendingSummary(this.save),
      telemetry: this.telemetry,
      telemetryAt: this.telemetryAt,
      observations: this.observations.slice(),
      logs: this.logs.slice(),
      status: this.status,
      wifi: this.wifi ? redact(this.wifi) : null,
      actions: this.actions,
      jobs: this.jobs,
      lastError: this.lastError,
      connectedAt: this.connectedAt,
      generation: this.generation,
      simulation: this.mode !== 'hardware',
    };
  }

  emit() { this.onChange(this.snapshot()); }

  feature(id) { return this.capabilities.find((item) => item.id === id) || null; }

  supports(id) {
    const item = this.feature(id);
    return Boolean(item && item.supported !== false);
  }

  async attach(transport, options = {}) {
    const mode = options.mode || 'hardware';
    const detach = options.detach || null;
    await this.stop();
    this.generation += 1;
    const generation = this.generation;
    this.mode = mode;
    this.transport = transport;
    this.detach = detach;
    this.layers = { port: 'open', protocol: 'handshake', radar: 'unknown', data: 'none', config: this.save.phase };
    this.identity = null;
    this.lastError = null;
    this.telemetry = null;
    this.observations = [];
    this.logs = [];
    this.wifi = null;
    this.status = null;
    this.jobs = [];
    this.client = this.clientFactory(transport, {
      clock: this.clock,
      helloTimeout: this.helloTimeout,
      rpcTimeout: this.rpcTimeout,
      onEvent: (frame) => {
        if (generation !== this.generation) return;
        this.takeEvent(frame);
      },
    });
    if (transport.start) transport.start();
    this.emit();
    try {
      const hello = await this.client.hello({ client: { name: 'mmwave-web-console', version: '0.3.0' }, nonce: nonce(), minorMax: 0 });
      if (generation !== this.generation) return { ok: false, reason: 'stale_generation' };
      if (!hello.json || hello.json.ok !== true) {
        const code = hello.json && hello.json.error ? hello.json.error.code : 'handshake_failed';
        this.layers.protocol = code === 'VERSION_UNSUPPORTED' ? 'incompatible' : 'failed';
        this.lastError = { scope: 'hello', code };
        this.emit();
        return { ok: false, reason: code };
      }
      const result = hello.json.result;
      this.sessionId = this.client.sessionId;
      this.bootId = result.boot_id;
      this.identity = Object.assign({}, result.identity || {}, {
        boot_id: result.boot_id,
        protocol: result.protocol,
        configured_model_note: 'configured_model is a firmware setting, not a detected radar',
      });
      this.layers.protocol = 'online';
      this.layers.radar = 'waiting_first_frame';
      this.connectedAt = this.now();
      this.save = rememberDevice(this.save, Object.assign({}, this.identity, { boot_id: this.bootId }), this.sessionId);
      await this.loadCapabilities();
      const config = await this.readConfig(null);
      if (!config.ok && config.reason !== 'pending_save') throw new Error(config.reason || 'config_read_failed');
      const subscribed = await this.subscribe();
      if (!subscribed) throw new Error('subscribe_failed');
      try { await this.refreshStatus(); } catch { /* status is not required to view identity */ }
      this.client.startHeartbeat();
      this.emit();
      return { ok: true, identity: this.identity, simulation: this.mode !== 'hardware' };
    } catch (error) {
      if (generation !== this.generation) return { ok: false, reason: 'stale_generation' };
      const message = error && error.message ? error.message : 'handshake_failed';
      this.layers.protocol = message === 'timeout' ? 'no_response' : 'failed';
      this.lastError = { scope: 'hello', code: message, hint: message === 'timeout' ? 'no_protocol_response' : 'handshake_failed' };
      this.emit();
      return { ok: false, reason: message };
    }
  }

  async loadCapabilities() {
    const page = await this.readPages(CODE.CAPABILITIES_LIST);
    this.capabilities = page.items;
    this.capRevision = page.revision;
    this.actions = [];
    try {
      const actions = await this.readPages(CODE.ACTIONS_LIST);
      this.actions = actions.items;
    } catch (error) {
      this.actions = [];
    }
  }

  async readPages(code) {
    const items = [];
    let cursor = null;
    let revision = null;
    let guard = 0;
    do {
      const frame = await this.call(() => this.client.request(code, { cursor }));
      if (!frame.json || frame.json.ok !== true) {
        const codeName = frame.json && frame.json.error ? frame.json.error.code : 'page_failed';
        throw new Error(codeName);
      }
      const result = frame.json.result;
      if (revision != null && result.revision != null && result.revision !== revision) throw new Error('revision_changed_mid_page');
      revision = result.revision != null ? result.revision : revision;
      for (const item of result.items || []) items.push(item);
      cursor = result.next_cursor || null;
      guard += 1;
    } while (cursor && guard < 64);
    return { items, revision };
  }

  async readConfig(cursor = null, options = {}) {
    if (this.save.phase === SAVE.unknown) return { ok: false, reason: 'pending_save' };
    const locked = this.flow || saveFlowLocked(this.save);
    if (locked && !options.allowDuringFlow) return { ok: false, reason: 'operation_busy' };
    const generation = this.generation;
    const items = [];
    let revision = null;
    let next = cursor;
    let guard = 0;
    do {
      const frame = await this.call(() => this.client.readConfig(next));
      if (!this.readStillCurrent(generation, options.flowId)) return { ok: false, reason: 'stale_generation' };
      if (!frame.json || frame.json.ok !== true) return { ok: false, reason: 'config_read_failed' };
      const result = frame.json.result;
      if (revision != null && result.revision !== revision) return { ok: false, reason: 'revision_changed_mid_page' };
      revision = result.revision;
      for (const item of result.items || []) items.push(item);
      next = result.next_cursor || null;
      guard += 1;
    } while (next && guard < 64);
    if (!this.readStillCurrent(generation, options.flowId)) return { ok: false, reason: 'stale_generation' };
    if (options.preserveSave) {
      this.configItems = items;
      this.configRevision = revision;
      this.emit();
      return { ok: true, revision, items };
    }
    return this.applyConfigSnapshot(items, revision);
  }

  async subscribe() {
    const streams = [
      { id: 'telemetry', max_rate_hz: 5 },
      { id: 'status', max_rate_hz: 1 },
      { id: 'config', max_rate_hz: 1 },
      { id: 'logs', max_rate_hz: 2 },
    ];
    const frame = await this.call(() => this.client.subscribe(streams, 8000));
    return Boolean(frame.json && frame.json.ok);
  }

  takeEvent(frame) {
    if (!this.client || !this.client.sessionLive || frame.sessionId !== this.client.sessionId) return;
    if (frame.code === CODE.TELEMETRY) {
      const body = frame.json;
      this.telemetry = body;
      this.telemetryAt = frame.receivedAt != null ? frame.receivedAt : this.now();
      this.syncDataLayers();
      this.observations.push({
        source_seq: body.source_seq,
        sent_ms: body.sent_ms,
        receivedAt: this.telemetryAt,
        origin: body.origin,
        presence: body.presence,
        targets: body.targets,
      });
      if (this.observations.length > RECORD_MAX) this.observations.splice(0, this.observations.length - RECORD_MAX);
    } else if (frame.code === CODE.LOG) {
      this.logs.push(redact(frame.json));
      if (this.logs.length > LOG_MAX) this.logs.splice(0, this.logs.length - LOG_MAX);
    } else if (frame.code === CODE.STATUS_CHANGED) {
      this.status = Object.assign({}, this.status || {}, redact(frame.json));
    } else if (frame.code === CODE.CONFIG_CHANGED) {
      const payload = frame.json || {};
      const ownWrite = payload.op_id && payload.op_id === this.save.opId;
      const ownEcho = payload.origin === 'web' && (this.save.phase === SAVE.persisted || saveFlowLocked(this.save));
      if (!ownWrite && !ownEcho && !saveFlowLocked(this.save) && !this.flow) {
        this.save = Object.assign({}, this.save, { phase: SAVE.conflict, message: 'revision_conflict' });
      }
    } else if (frame.code === CODE.JOB_CHANGED) {
      this.jobs = mergeJob(this.jobs, frame.json);
    }
    this.emit();
  }

  observationView(now) {
    const at = now == null ? this.now() : now;
    const live = Boolean(this.client && this.client.sessionLive && this.layers.protocol === 'online');
    const context = {
      sessionLive: live,
      protocol: this.layers.protocol,
      bootId: this.bootId,
      activeBootId: this.client ? this.client.bootId : null,
      sentMs: this.telemetry ? this.telemetry.sent_ms : null,
      receivedAt: this.telemetryAt,
      staleAfterMs: 8000,
      now: at,
    };
    const qualityOf = live ? (field, next) => this.client.qualityOf(field, next) : () => 'stale';
    return assessObservation(this.telemetry, context, qualityOf);
  }

  presenceView(now) {
    const view = this.observationView(now);
    return { state: view.presence, historical: view.historical === true };
  }

  touchClock() {
    const before = this.freshnessStamp();
    if (this.client) this.client.poll(this.now());
    if (this.client && this.layers.protocol === 'online' && (!this.client.sessionLive || this.client.sessionExpired(this.now()))) {
      this.layers.protocol = 'session_expired';
    }
    this.syncDataLayers();
    if (before !== this.freshnessStamp()) this.emit();
    return this.observationView();
  }

  freshnessStamp() {
    const view = this.observationView();
    return [this.layers.protocol, this.layers.radar, this.layers.data, view.presence, view.targets, view.vitals, view.live].join('|');
  }

  syncDataLayers() {
    if (!this.telemetry) return;
    if (this.layers.protocol !== 'online') {
      if (this.layers.radar === 'healthy' || this.layers.radar === 'partial') this.layers.radar = 'stale';
      if (this.layers.data === 'valid' || this.layers.data === 'partial') this.layers.data = 'stale';
      return;
    }
    const summary = summarizeLayers(this.observationView());
    this.layers.radar = summary.radar;
    this.layers.data = summary.data;
  }

  async rehandshake() {
    if (this.save.phase === SAVE.committing || this.save.phase === SAVE.validating || this.save.phase === SAVE.reading || this.flow) {
      return { ok: false, reason: 'operation_busy', state: this.save };
    }
    if (!this.transport) return { ok: false, reason: 'no_port' };
    const transport = this.transport;
    const mode = this.mode;
    const detach = this.detach;
    this.transport = null;
    this.detach = null;
    if (this.client) {
      try { this.client.disconnect(); } catch { /* already closed */ }
      this.client = null;
    }
    return this.attach(transport, { mode, detach });
  }

  editDraft(key, value) {
    if (this.save.phase === SAVE.conflict) return { ok: false, reason: 'revision_conflict', state: this.save };
    if (this.save.phase === SAVE.unknown || this.flow || saveFlowLocked(this.save)) {
      return { ok: false, reason: this.save.phase === SAVE.unknown ? 'pending_blocks_edit' : 'operation_busy' };
    }
    this.draft = Object.assign({}, this.draft || {}, { [key]: value });
    this.fieldErrors = Object.assign({}, this.fieldErrors, { [key]: undefined });
    const base = this.configItems.find((item) => item.key === key);
    const same = JSON.stringify(value) === JSON.stringify(base ? base.value : undefined);
    if (same) delete this.edited[key];
    else this.edited[key] = true;
    if (!this.hasEdits()) {
      this.save = Object.assign({}, this.save, {
        phase: SAVE.idle,
        message: null,
        readback: null,
        opId: null,
        changes: null,
        baseRevision: this.configRevision,
      });
    } else {
      this.save = beginEdit(this.save);
    }
    this.emit();
    return { ok: true };
  }

  discardDraft() {
    if (this.save.phase === SAVE.unknown) return { ok: false, reason: 'pending_save', state: this.save };
    if (this.save.phase === SAVE.conflict) return { ok: false, reason: 'revision_conflict', state: this.save };
    if (this.flow || saveFlowLocked(this.save)) return { ok: false, reason: 'operation_busy', state: this.save };
    this.draft = Object.fromEntries(this.configItems.map((item) => [item.key, clone(item.value)]));
    this.edited = Object.create(null);
    this.incomingConfig = null;
    this.fieldErrors = {};
    this.save = Object.assign(createSaveState(), {
      phase: SAVE.idle,
      deviceKey: this.save.deviceKey,
      sessionId: this.sessionId,
      baseRevision: this.configRevision,
    });
    this.emit();
    return { ok: true, state: this.save };
  }

  localChanges() {
    const draft = this.draft || {};
    const changes = {};
    for (const key of Object.keys(this.edited)) {
      if (Object.prototype.hasOwnProperty.call(draft, key)) changes[key] = clone(draft[key]);
    }
    return changes;
  }

  async validateDraft(options = {}) {
    const nested = options.flowId != null && this.ownsFlow(options.flowId);
    let id = nested ? options.flowId : null;
    if (!nested) {
      if (this.save.phase === SAVE.unknown) return { ok: false, reason: 'pending_save', state: this.save };
      const flow = this.beginFlow('validate');
      if (!flow.ok) return { ok: false, reason: flow.reason === 'pending_save' ? 'pending_save' : 'operation_busy', state: this.save };
      id = flow.id;
      this.save = Object.assign({}, this.save, { phase: SAVE.validating, message: null });
      this.emit();
    }
    const generation = this.generation;
    const baseRevision = options.baseRevision != null ? options.baseRevision : this.configRevision;
    try {
      const changes = clone(this.localChanges());
      const local = validateConfigChanges(changes, this.capabilities);
      if (!this.ownsFlow(id)) return { ok: false, reason: 'stale_generation', state: this.save };
      if (!local.ok) {
        const field = local.details && local.details.field;
        this.fieldErrors = field ? { [field]: local.message } : { _form: local.message };
        this.save = Object.assign({}, this.save, { phase: SAVE.failed, message: local.message });
        if (!nested) this.endFlow(id);
        this.emit();
        return { ok: false, reason: local.message, field, source: 'local', state: this.save };
      }
      this.fieldErrors = {};
      const frame = await this.call(() => this.client.request(CODE.CONFIG_VALIDATE, { base_revision: baseRevision, changes }));
      if (!this.ownsFlow(id) || this.generation !== generation) return { ok: false, reason: 'stale_generation', state: this.save };
      if (!frame.json || frame.json.ok !== true) {
        const code = frame.json && frame.json.error ? frame.json.error.code : 'validate_failed';
        if (code === 'REVISION_CONFLICT') {
          this.save = Object.assign({}, this.save, { phase: SAVE.conflict, message: 'revision_conflict', baseRevision: this.configRevision });
        } else {
          const field = frame.json && frame.json.error && frame.json.error.details ? frame.json.error.details.field : null;
          this.fieldErrors = field ? { [field]: code } : { _form: code };
          this.save = Object.assign({}, this.save, { phase: SAVE.failed, message: code });
        }
        if (!nested) this.endFlow(id);
        this.emit();
        return { ok: false, reason: code, source: 'device', state: this.save };
      }
      if (!nested) {
        this.save = Object.assign({}, this.save, { phase: SAVE.editing, message: 'validated' });
        this.endFlow(id);
        this.emit();
      }
      return { ok: true, changes, restart_required: frame.json.result.restart_required === true, state: this.save };
    } catch (error) {
      if (this.ownsFlow(id) && this.save.phase === SAVE.validating) {
        this.save = Object.assign({}, this.save, { phase: SAVE.failed, message: error && error.message ? error.message : 'validate_failed' });
        this.emit();
      }
      if (!nested) this.endFlow(id);
      return { ok: false, reason: error && error.message ? error.message : 'validate_failed', state: this.save };
    }
  }

  async commitDraft() {
    if (this.save.phase === SAVE.unknown) return { ok: false, reason: 'pending_blocks_new_save', state: this.save };
    if (this.save.phase === SAVE.conflict) return { ok: false, reason: 'revision_conflict', state: this.save };
    if (this.save.message === 'persisted_readback_failed') return { ok: false, reason: 'readback_required', state: this.save };
    const flow = this.beginFlow('commit');
    if (!flow.ok) return { ok: false, reason: flow.reason === 'pending_save' ? 'pending_blocks_new_save' : 'operation_busy', state: this.save };
    const id = flow.id;
    const generation = this.generation;
    const baseRevision = this.configRevision;
    const sessionId = this.client ? this.client.sessionId : this.sessionId;
    const key = deviceKey(this.identity);
    this.save = Object.assign({}, this.save, { phase: SAVE.validating, message: null, readback: null });
    this.emit();
    try {
      const validated = await this.validateDraft({ flowId: id, baseRevision });
      if (!this.ownsFlow(id)) return { ok: false, reason: 'stale_generation', state: this.save };
      if (!validated.ok) {
        this.endFlow(id);
        return validated;
      }
      if (!this.client || !this.client.sessionLive || this.generation !== generation || this.configRevision !== baseRevision) {
        this.save = Object.assign({}, this.save, { phase: SAVE.conflict, message: 'revision_changed', opId: null, changes: null });
        this.endFlow(id);
        this.emit();
        return { ok: false, reason: 'revision_changed', state: this.save };
      }
      const changes = clone(validated.changes);
      const opId = newOpId();
      const armed = armCommit(this.save, { baseRevision, changes, opId, sessionId });
      if (!armed.ok) {
        this.endFlow(id);
        return armed;
      }
      this.save = Object.assign({}, armed.state, { deviceKey: key || armed.state.deviceKey, sessionId });
      this.emit();
      let frame;
      try {
        frame = await this.client.commit(changes, { baseRevision, opId });
      } catch (error) {
        if (this.ownsFlow(id) && this.save.phase === SAVE.committing && this.save.opId === opId) {
          this.save = markUnknown(this.save, 'commit_failed');
          this.emit();
        }
        this.endFlow(id);
        return { ok: false, reason: error && error.message ? error.message : 'commit_failed', state: this.save };
      }
      if (!this.ownsFlow(id) || this.save.phase !== SAVE.committing || this.save.opId !== opId) {
        this.endFlow(id);
        return { ok: false, reason: this.save.phase === SAVE.unknown ? 'unknown' : 'stale_generation', state: this.save };
      }
      this.save = applyCommitResult(this.save, frame);
      if (this.save.phase === SAVE.unknown) {
        this.endFlow(id);
        this.emit();
        return { ok: false, reason: 'unknown', state: this.save };
      }
      if (this.save.phase === SAVE.conflict || this.save.phase === SAVE.failed) {
        this.endFlow(id);
        this.emit();
        return { ok: false, reason: this.save.message, state: this.save };
      }
      if (this.save.phase !== SAVE.persisted) {
        if (this.save.phase === SAVE.committing && this.save.opId === opId) this.save = markUnknown(this.save, 'save_result_unconfirmed');
        this.endFlow(id);
        this.emit();
        return { ok: false, reason: 'unknown', state: this.save };
      }
      const read = await this.confirmReadback({ flowId: id, generation, changes, ackRevision: this.save.baseRevision, messageOk: 'persisted_and_read_back' });
      this.endFlow(id);
      return read;
    } catch (error) {
      if (this.ownsFlow(id) && this.save.phase === SAVE.committing && this.save.opId) {
        this.save = markUnknown(this.save, 'commit_failed');
        this.emit();
      }
      this.endFlow(id);
      return { ok: false, reason: error && error.message ? error.message : 'commit_failed', state: this.save };
    }
  }

  async confirmReadback({ flowId, generation, changes, ackRevision, messageOk }) {
    if (!this.ownsFlow(flowId) || this.generation !== generation) {
      return { ok: false, reason: 'stale_generation', state: this.save };
    }
    this.save = Object.assign({}, this.save, { phase: SAVE.reading, message: 'persisted', readPurpose: 'readback' });
    this.emit();
    let read;
    try {
      read = await this.readConfig(null, { allowDuringFlow: true, preserveSave: true, flowId });
    } catch (error) {
      read = { ok: false, reason: error && error.message ? error.message : 'config_read_failed' };
    }
    if (!this.ownsFlow(flowId) || this.generation !== generation) {
      return { ok: false, reason: 'stale_generation', state: this.save };
    }
    const finish = (message, ok) => {
      this.draft = Object.fromEntries(this.configItems.map((item) => [item.key, clone(item.value)]));
      this.edited = Object.create(null);
      this.incomingConfig = null;
      this.save = Object.assign({}, this.save, {
        phase: SAVE.persisted,
        message,
        readback: ok ? this.configRevision : null,
        opId: null,
        changes: null,
        readPurpose: null,
      });
      this.emit();
      return { ok, reason: message, state: this.save };
    };
    if (!read.ok) {
      this.edited = Object.create(null);
      this.save = Object.assign({}, this.save, {
        phase: SAVE.persisted,
        message: 'persisted_readback_failed',
        readback: null,
        opId: null,
        changes: null,
        readPurpose: null,
      });
      this.emit();
      return { ok: false, reason: 'persisted_readback_failed', state: this.save };
    }
    const sameRevision = String(this.configRevision) === String(ackRevision);
    if (!sameRevision || !valuesMatch(this.configItems, changes)) return finish('readback_diverged', false);
    return finish(messageOk, true);
  }

  async recoverPending() {
    if (this.save.phase !== SAVE.unknown || !this.save.opId) return { ok: false, reason: 'not_pending' };
    if (!this.client || !this.client.sessionLive) return { ok: false, reason: 'not_online', state: this.save };
    const liveKey = deviceKey(this.identity);
    if (this.save.deviceKey && liveKey && this.save.deviceKey !== liveKey) return { ok: false, reason: 'wrong_device', state: this.save };
    if (this.flow) return { ok: false, reason: 'operation_busy', state: this.save };
    const flow = this.beginFlow('recover');
    if (!flow.ok) return { ok: false, reason: 'operation_busy', state: this.save };
    const id = flow.id;
    const generation = this.generation;
    const changes = clone(this.save.changes);
    const opId = this.save.opId;
    let frame;
    try {
      frame = await this.call(() => this.client.commitStatus(opId));
    } catch (error) {
      this.endFlow(id);
      return { ok: false, reason: error && error.message ? error.message : 'status_failed', state: this.save };
    }
    if (!this.ownsFlow(id) || this.generation !== generation || this.save.opId !== opId || !this.client) {
      this.endFlow(id);
      return { ok: false, reason: 'stale_generation', state: this.save };
    }
    const applied = applyStatusResult(this.save, frame, { sessionId: this.client.sessionId, deviceKey: liveKey });
    this.save = applied.state;
    if (!applied.accepted) {
      this.endFlow(id);
      this.emit();
      return { ok: false, reason: applied.reason || this.save.message, state: this.save };
    }
    const read = await this.confirmReadback({
      flowId: id,
      generation,
      changes,
      ackRevision: this.save.baseRevision,
      messageOk: 'confirmed_by_status',
    });
    this.endFlow(id);
    return { ok: read.ok === true, reason: read.ok ? 'confirmed_by_status' : read.reason, state: this.save };
  }

  abandonPending() {
    const result = abandonTracking(this.save);
    this.save = result.state;
    this.emit();
    return result;
  }

  async reloadFromDevice() {
    if (this.save.phase === SAVE.unknown) return { ok: false, reason: 'pending_save', state: this.save };
    if (this.flow || saveFlowLocked(this.save)) return { ok: false, reason: 'operation_busy', state: this.save };
    const flow = this.beginFlow('reload');
    if (!flow.ok) return { ok: false, reason: 'operation_busy', state: this.save };
    const generation = this.generation;
    this.save = Object.assign({}, this.save, {
      phase: SAVE.reading,
      message: null,
      opId: null,
      changes: null,
      readback: null,
      readPurpose: 'load',
    });
    this.fieldErrors = {};
    this.emit();
    try {
      const read = await this.readConfig(null, { allowDuringFlow: true, preserveSave: true, flowId: flow.id });
      if (!this.ownsFlow(flow.id) || this.generation !== generation) return { ok: false, reason: 'stale_generation', state: this.save };
      if (read.ok) {
        this.draft = Object.fromEntries(this.configItems.map((item) => [item.key, clone(item.value)]));
        this.edited = Object.create(null);
        this.incomingConfig = null;
        this.save = Object.assign({}, this.save, {
          phase: SAVE.idle,
          baseRevision: this.configRevision,
          message: null,
          opId: null,
          changes: null,
          readback: null,
          readPurpose: null,
        });
      } else if (this.save.phase === SAVE.reading && this.save.readPurpose === 'load') {
        this.save = Object.assign({}, this.save, {
          phase: this.hasEdits() ? SAVE.conflict : SAVE.failed,
          message: this.hasEdits() ? 'revision_conflict' : (read.reason || 'config_read_failed'),
          readPurpose: null,
        });
      }
      this.emit();
      return read.ok ? read : { ok: false, reason: read.reason, state: this.save };
    } catch (error) {
      if (this.ownsFlow(flow.id) && this.save.phase === SAVE.reading && this.save.readPurpose === 'load') {
        this.save = Object.assign({}, this.save, { phase: SAVE.failed, message: 'config_read_failed', readPurpose: null });
        this.emit();
      }
      return { ok: false, reason: error && error.message ? error.message : 'config_read_failed', state: this.save };
    } finally {
      this.endFlow(flow.id);
    }
  }

  async refreshStatus() {
    const frame = await this.call(() => this.client.request(CODE.STATUS_GET, {}));
    if (frame.json && frame.json.ok) {
      this.status = redact(frame.json.result);
      this.syncDataLayers();
    }
    this.emit();
    return this.status;
  }

  async refreshWifi() {
    try {
      const frame = await this.call(() => this.client.request(CODE.WIFI_STATUS, {}));
      if (frame.json && frame.json.ok) this.wifi = redact(frame.json.result);
      else this.wifi = { state: 'unsupported' };
    } catch (error) {
      this.wifi = { state: 'unsupported' };
    }
    this.emit();
    return this.wifi;
  }

  async provisionWifi(input) {
    if (this.save.phase === SAVE.unknown) return { ok: false, reason: 'pending_save' };
    const opId = newOpId();
    const frame = await this.call(() => this.client.request(CODE.WIFI_PROVISION, {
      op_id: opId,
      ssid: input.ssid,
      auth: input.auth || 'wpa2_psk',
      password: input.password,
    }, { timeoutMs: 2000, retry: false }), false);
    if (!frame.json || frame.json.ok !== true) {
      return { ok: false, reason: frame.json && frame.json.error ? frame.json.error.code : 'provision_failed' };
    }
    const jobId = frame.json.result.job_id;
    this.jobs = mergeJob(this.jobs, { job_id: jobId, op_id: opId, action_id: 'wifi.provision', state: 'queued', verified: false });
    this.emit();
    return { ok: true, job_id: jobId, op_id: opId };
  }

  async pollJob(jobId) {
    const frame = await this.call(() => this.client.request(CODE.JOB_GET, { job_id: jobId }));
    if (!frame.json || frame.json.ok !== true) return { ok: false, reason: 'job_get_failed' };
    const job = frame.json.result;
    if (!job || job.found === false || !job.job_id) {
      const unknown = { job_id: jobId, state: 'unknown', action_id: 'job', op_id: null, verified: false };
      this.jobs = mergeJob(this.jobs, unknown);
      this.emit();
      return { ok: true, job: unknown };
    }
    const verified = job.state === 'succeeded';
    this.jobs = mergeJob(this.jobs, Object.assign({}, job, { verified }));
    this.emit();
    return { ok: true, job: Object.assign({}, job, { verified }) };
  }

  async refreshAfterResume() {
    if (!this.client) return { ok: false, reason: 'not_attached' };
    this.client.poll(this.now());
    if (!this.client.sessionLive || this.client.sessionExpired(this.now())) {
      this.layers.protocol = 'session_expired';
      this.emit();
      return { ok: false, reason: 'session_expired', rehello: true };
    }
    try {
      await this.client.ping();
      this.layers.protocol = 'online';
      this.emit();
      return { ok: true };
    } catch (error) {
      this.layers.protocol = 'session_expired';
      this.emit();
      return { ok: false, reason: error && error.message ? error.message : 'ping_failed', rehello: true };
    }
  }

  diagnosticExport(options = {}) {
    const includeNetwork = options.includeNetwork === true;
    const wifi = this.wifi ? Object.assign({}, this.wifi) : null;
    if (!includeNetwork && wifi) {
      wifi.ssid = wifi.ssid ? '[hidden]' : wifi.ssid;
      wifi.ip = wifi.ip ? '[hidden]' : wifi.ip;
    }
    const identity = this.identity ? {
      configured_model: this.identity.configured_model,
      dimension: this.identity.dimension,
      firmware_version: this.identity.firmware_version,
      protocol: this.identity.protocol,
    } : null;
    return redact({
      exported_at: new Date().toISOString(),
      mode: this.mode,
      simulation: this.mode !== 'hardware',
      identity,
      layers: this.snapshot().layers,
      config_revision: this.configRevision,
      cap_revision: this.capRevision,
      status: this.status,
      wifi,
      log_count: this.logs.length,
      logs: this.logs.slice(-40).map((entry) => ({
        level: entry.level,
        source: entry.source,
        message: String(entry.message || '').slice(0, 240),
        sample_ms: entry.sample_ms,
      })),
      pending: pendingSummary(this.save),
      observation_count: this.observations.length,
    });
  }

  async stop() {
    const client = this.client;
    this.client = null;
    this.flow = null;
    this.settleStoppedSave();
    if (client) {
      try {
        if (client.sessionLive && !client.inflight()) await this.call(() => client.request(CODE.SESSION_CLOSE, {}), false);
      } catch (error) { /* link may already be gone */ }
      client.disconnect();
    }
    if (this.transport && this.transport.close) {
      try { await this.transport.close(); } catch (error) { /* already closed */ }
    }
    if (this.detach) {
      try { this.detach(); } catch (error) { /* ignore */ }
    }
    this.transport = null;
    this.detach = null;
    this.layers = Object.assign({}, this.layers, {
      port: 'closed',
      protocol: 'offline',
      radar: this.telemetry ? 'stale' : 'unknown',
      data: this.telemetry ? 'stale' : 'none',
    });
    this.emit();
  }

  settleStoppedSave() {
    if (this.save.phase === SAVE.committing) this.save = markUnknown(this.save, 'disconnected_during_commit');
    else if (this.save.phase === SAVE.reading && this.save.readPurpose === 'readback') {
      this.edited = Object.create(null);
      this.save = Object.assign({}, this.save, {
        phase: SAVE.persisted,
        message: 'persisted_readback_failed',
        opId: null,
        changes: null,
        readback: null,
        readPurpose: null,
      });
    } else if (this.save.phase === SAVE.reading) {
      this.save = Object.assign({}, this.save, {
        phase: this.hasEdits() ? SAVE.conflict : SAVE.failed,
        message: this.hasEdits() ? 'revision_conflict' : 'read_disconnected',
        opId: null,
        changes: null,
        readback: null,
        readPurpose: null,
      });
    } else if (this.save.phase === SAVE.recovering) {
      this.save = Object.assign({}, this.save, { phase: SAVE.unknown });
    } else if (this.save.phase === SAVE.validating) {
      this.save = Object.assign({}, this.save, { phase: SAVE.failed, message: 'disconnected', opId: null, changes: null });
    }
  }

  hasEdits() {
    return Object.keys(this.edited || {}).length > 0;
  }

  readStillCurrent(generation, flowId) {
    if (this.generation !== generation) return false;
    if (flowId != null && !this.ownsFlow(flowId)) return false;
    return true;
  }

  baselineChanged(items, revision) {
    if (String(revision) !== String(this.configRevision)) return true;
    if (items.length !== this.configItems.length) return true;
    const current = new Map(this.configItems.map((item) => [item.key, item.value]));
    for (const item of items) {
      if (!current.has(item.key)) return true;
      if (JSON.stringify(current.get(item.key)) !== JSON.stringify(item.value)) return true;
    }
    return false;
  }

  applyConfigSnapshot(items, revision) {
    if (this.hasEdits() && this.baselineChanged(items, revision)) {
      this.incomingConfig = {
        revision,
        items: items.map((item) => ({ key: item.key, value: clone(item.value) })),
      };
      this.save = Object.assign({}, this.save, { phase: SAVE.conflict, message: 'revision_conflict' });
      this.emit();
      return { ok: true, conflict: true, revision: this.configRevision, items: this.configItems };
    }
    if (this.hasEdits()) {
      if (this.save.phase === SAVE.conflict) this.save = Object.assign({}, this.save, { phase: SAVE.editing, message: null });
      this.incomingConfig = null;
      this.emit();
      return { ok: true, revision: this.configRevision, items: this.configItems };
    }
    this.configItems = items;
    this.configRevision = revision;
    this.draft = Object.fromEntries(items.map((item) => [item.key, clone(item.value)]));
    this.edited = Object.create(null);
    this.incomingConfig = null;
    this.fieldErrors = {};
    this.save = Object.assign({}, this.save, {
      phase: SAVE.idle,
      baseRevision: revision,
      message: null,
      opId: null,
      changes: null,
      readback: null,
      readPurpose: null,
    });
    this.emit();
    return { ok: true, revision, items };
  }
}

function mergeJob(jobs, next) {
  if (!next || !next.job_id) return jobs;
  const index = jobs.findIndex((item) => item.job_id === next.job_id);
  const copy = jobs.slice();
  if (index >= 0) copy[index] = Object.assign({}, copy[index], next);
  else copy.push(next);
  return copy.slice(-12);
}

function clone(value) {
  if (value == null || typeof value !== 'object') return value;
  return JSON.parse(JSON.stringify(value));
}

function valuesMatch(items, changes) {
  if (!changes || typeof changes !== 'object') return false;
  for (const [key, value] of Object.entries(changes)) {
    const item = (items || []).find((entry) => entry.key === key);
    if (!item || JSON.stringify(item.value) !== JSON.stringify(value)) return false;
  }
  return true;
}

export { SAVE };
