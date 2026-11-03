import { encodeFrame, FrameParser } from './codec.js';
import { createRealClock } from './clock.js';
import { isSideEffect, validateEvent, validateResponse } from './contract.js';
import { CODE, ERROR, KIND } from './limits.js';
import { encodeUtf8 } from './utf8.js';

const MAX_EVENTS = 32;

export class ProtocolClient {
  constructor(transport, options = {}) {
    this.transport = transport;
    this.clock = options.clock || createRealClock();
    this.helloTimeout = options.helloTimeout ?? 3000;
    this.rpcTimeout = options.rpcTimeout ?? 1000;
    this.sessionId = 0;
    this.nextId = 1;
    this.bootId = null;
    this.wireSeq = 1;
    this.pending = null;
    this.events = [];
    this.eventsDropped = 0;
    this.ignored = 0;
    this.rejected = 0;
    this.lastResponseAt = null;
    this.livenessTimer = null;
    this.sessionLive = false;
    this.generation = 0;
    this.sessionDeadline = null;
    this.parser = new FrameParser();
    this.onEvent = options.onEvent || (() => {});
    this.heartbeat = null;
    transport.onData((bytes) => this.ingest(bytes));
  }

  ingest(bytes) {
    const parsed = this.parser.push(bytes, this.clock.now());
    for (const frame of parsed.frames) this.handleFrame(frame);
  }

  handleFrame(frame) {
    const now = this.clock.now();
    if (this.sessionLive && this.sessionExpired(now)) this.expireLocal();
    if (frame.kind === KIND.event) {
      if (!this.sessionLive || frame.sessionId !== this.sessionId) {
        this.ignored++;
        return;
      }
      if (!validateEvent(frame.code, frame.json)) {
        this.rejected++;
        return;
      }
      frame.receivedAt = this.clock.now();
      if (this.events.length >= MAX_EVENTS) {
        this.events.shift();
        this.eventsDropped++;
      }
      this.events.push(frame);
      this.onEvent(frame);
      return;
    }
    if (frame.kind !== KIND.response || !this.pending) {
      this.ignored++;
      return;
    }
    if (frame.sessionId !== this.pending.expectSession && this.pending.expectSession !== 0) {
      this.ignored++;
      return;
    }
    if (frame.requestId !== this.pending.requestId || frame.code !== this.pending.code) {
      this.ignored++;
      return;
    }
    if (!validateResponse(frame.code, frame.json)) {
      this.rejected++;
      return;
    }
    if (this.pending.code === CODE.HELLO && frame.json.ok && frame.json.result?.nonce !== this.pending.nonce) {
      this.ignored++;
      return;
    }
    if (now >= this.pending.deadline) {
      const slot = this.pending;
      this.finishPending();
      slot.reject(new Error('timeout'));
      return;
    }
    const pending = this.pending;
    this.finishPending(null, frame);
    if (!this.sessionLive && frame.code !== CODE.HELLO) {
      this.ignored++;
      pending.resolve(frame);
      return;
    }
    if (frame.code === CODE.HELLO && frame.json.ok) {
      this.sessionId = frame.sessionId;
      this.bootId = frame.json.result.boot_id;
      this.nextId = 2;
      this.sessionLive = true;
      this.noteResponse();
    } else if (frame.code === CODE.SESSION_CLOSE && frame.json.ok) {
      this.dropSession();
    } else if (frame.json.ok && frame.kind === KIND.response) {
      this.noteResponse();
    }
    pending.resolve(frame);
  }

  noteResponse() {
    const now = this.clock.now();
    this.lastResponseAt = now;
    this.sessionDeadline = now + 15000;
    this.armLiveness();
  }

  sessionExpired(now = this.clock.now()) {
    return this.sessionDeadline != null && now >= this.sessionDeadline;
  }

  armLiveness() {
    this.clearLiveness();
    const generation = this.generation;
    const deadline = this.sessionDeadline ?? this.clock.now() + 15000;
    let id = null;
    id = this.clock.setTimeout(() => {
      if (generation !== this.generation || this.livenessTimer !== id) return;
      this.livenessTimer = null;
      this.expireLocal();
    }, Math.max(0, deadline - this.clock.now()));
    this.livenessTimer = id;
  }

  clearLiveness() {
    if (this.livenessTimer != null) this.clock.clearTimeout(this.livenessTimer);
    this.livenessTimer = null;
  }

  endSession() {
    this.generation += 1;
    this.sessionLive = false;
    this.sessionId = 0;
    this.sessionDeadline = null;
    this.stopHeartbeat();
    this.clearLiveness();
  }

  dropSession() {
    this.endSession();
  }

  expireLocal() {
    const slot = this.pending;
    this.endSession();
    if (this.pending === slot) this.finishPending();
    slot?.reject?.(new Error('session_expired'));
  }

  poll(now = this.clock.now()) {
    if (this.sessionLive && this.sessionExpired(now)) this.expireLocal();
    if (this.pending && now >= this.pending.deadline) {
      const slot = this.pending;
      this.finishPending();
      slot.reject(new Error('timeout'));
    }
  }

  async hello(input) {
    if (this.pending) throw new Error('rpc_inflight');
    this.endSession();
    this.nextId = 1;
    const nonce = input.nonce;
    const body = {
      client: input.client,
      nonce,
      protocol: { major: 1, minor_max: input.minorMax ?? 0 },
      max_payload: 4096,
    };
    return this.request(CODE.HELLO, body, { timeoutMs: this.helloTimeout, sessionId: 0, requestId: 1, nonce, retry: true });
  }

  async request(code, body, options = {}) {
    if (code !== CODE.HELLO && this.sessionExpired()) this.expireLocal();
    if (!this.sessionLive && code !== CODE.HELLO && this.lastResponseAt != null) {
      throw new Error('session_expired');
    }
    if (this.pending) throw new Error('rpc_inflight');
    const requestId = options.requestId ?? this.nextId++;
    const payload = encodeUtf8(JSON.stringify(body));
    const timeoutMs = options.timeoutMs ?? this.rpcTimeout;
    const retry = Boolean(options.retry) && !isSideEffect(code);
    return new Promise((resolve, reject) => {
      let settled = false;
      const settle = (error, frame) => {
        if (settled) return;
        settled = true;
        this.finishPending();
        if (error) reject(error);
        else resolve(frame);
      };
      const arm = (ms) => this.clock.setTimeout(() => onTimeout(), ms);
      const slot = {};
      const onTimeout = () => {
        if (settled || this.pending !== slot) return;
        const remaining = slot.deadline - this.clock.now();
        if (remaining > 0) {
          slot.timer = arm(Math.max(1, remaining));
          return;
        }
        if (retry && !slot.retried) {
          slot.retried = true;
          slot.deadline = this.clock.now() + timeoutMs;
          this.clock.clearTimeout(slot.timer);
          slot.timer = arm(timeoutMs);
          send().catch((error) => settle(error));
          return;
        }
        settle(new Error('timeout'));
      };
      const send = async () => {
        const encoded = encodeFrame({
          kind: KIND.request,
          sessionId: options.sessionId ?? this.sessionId,
          requestId,
          code,
          wireSeq: this.wireSeq++,
          payload,
        });
        if (!encoded.ok) throw new Error(encoded.error);
        await this.transport.write(encoded.wire);
      };
      slot.requestId = requestId;
      slot.code = code;
      slot.nonce = options.nonce;
      slot.expectSession = options.sessionId ?? this.sessionId;
      slot.resolve = (frame) => settle(null, frame);
      slot.reject = (error) => settle(error);
      slot.timer = arm(timeoutMs);
      slot.deadline = this.clock.now() + timeoutMs;
      slot.retried = false;
      slot.generation = this.generation;
      this.pending = slot;
      send().catch((error) => settle(error));
    });
  }

  finishPending() {
    if (this.pending?.timer != null) this.clock.clearTimeout(this.pending.timer);
    this.pending = null;
  }

  disconnect() {
    const pending = this.pending;
    this.dropSession();
    this.finishPending();
    pending?.reject?.(new Error('disconnected'));
  }

  async ping() {
    return this.request(CODE.PING, {});
  }

  async readConfig(cursor = null) {
    return this.request(CODE.CONFIG_READ, { cursor });
  }

  async commit(changes, { baseRevision, opId }) {
    try {
      return await this.request(CODE.CONFIG_COMMIT, { base_revision: baseRevision, op_id: opId, changes }, { timeoutMs: 2000, retry: false });
    } catch (error) {
      if (error.message === 'timeout') return { unknown: true, opId };
      throw error;
    }
  }

  async commitStatus(opId) {
    return this.request(CODE.COMMIT_STATUS, { op_id: opId });
  }

  async subscribe(streams, eventBudgetBps = 8000) {
    return this.request(CODE.SUBSCRIBE, { streams, event_budget_bps: eventBudgetBps });
  }

  inflight() {
    return this.pending != null;
  }

  startHeartbeat() {
    this.stopHeartbeat();
    const generation = this.generation;
    let id = null;
    const beat = () => {
      if (generation !== this.generation || this.heartbeat !== id) return;
      this.heartbeat = null;
      if (!this.sessionLive || this.sessionExpired()) return;
      id = this.clock.setTimeout(beat, 5000);
      this.heartbeat = id;
      if (this.pending) return;
      this.ping().catch(() => {});
    };
    id = this.clock.setTimeout(beat, 5000);
    this.heartbeat = id;
  }

  stopHeartbeat() {
    if (this.heartbeat != null) this.clock.clearTimeout(this.heartbeat);
    this.heartbeat = null;
  }

  fieldAge(field, sentMs, receivedAt, now = this.clock.now()) {
    if (!field || field.sample_ms == null || sentMs == null || receivedAt == null) return null;
    if (field.sample_ms > sentMs) return null;
    return sentMs - field.sample_ms + Math.max(0, now - receivedAt);
  }

  qualityOf(field, context) {
    if (!context?.sessionLive || (context.bootId && context.activeBootId && context.bootId !== context.activeBootId)) return 'stale';
    if (!field) return 'unknown';
    if (field.quality === 'unknown' || field.quality === 'unsupported' || field.quality === 'invalid') return field.quality;
    const age = this.fieldAge(field, context.sentMs, context.receivedAt, context.now ?? this.clock.now());
    if (age == null) return 'unknown';
    if (age > context.staleAfterMs) return 'stale';
    return field.quality === 'stale' ? 'stale' : 'valid';
  }
}

export { ERROR };
