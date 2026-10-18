import { createRealClock } from '../protocol/clock.js';
import { CODE } from '../protocol/limits.js';

const MAX_UI = 200;
const DEFAULT_SAMPLES = 64;
const DEFAULT_SEGMENTS = 120;
const DEFAULT_ERRORS = 32;
const DEFAULT_EVENTS = 32;

export function createDiagController(options) {
  const hello = options.hello;
  const createClient = options.createClient;
  const timer = options.clock || createRealClock();
  const maxSamples = options.maxSamples ?? DEFAULT_SAMPLES;
  const maxSegments = options.maxSegments ?? DEFAULT_SEGMENTS;
  const maxCoverageSegments = options.maxCoverageSegments ?? DEFAULT_SEGMENTS;
  const maxErrors = options.maxErrors ?? DEFAULT_ERRORS;
  const maxEvents = options.maxEvents ?? DEFAULT_EVENTS;
  const captureIntervalMs = options.captureIntervalMs ?? 1000;
  const ioWaitMs = options.ioWaitMs ?? options.writeWaitMs ?? 1000;
  let generation = 0;
  let phase = 'idle';
  let lastError = '';
  let guidance = '';
  let port = null;
  let client = null;
  let reader = null;
  let writer = null;
  let readTask = null;
  let writeTail = Promise.resolve();
  let connectTask = null;
  let outstanding = null;
  let closing = null;
  let capture = null;
  const unreleasedPorts = new Set();
  const portEpochs = new WeakMap();
  const closedPortEpochs = new WeakMap();
  const portCloseStates = new Map(); // port -> { epoch, promise, status: 'closing'|'error', error: null }
  const records = [];
  const listeners = new Set();
  if (options.onState) listeners.add(options.onState);

  function hasHeldResources() {
    return Boolean(port || reader || writer || unreleasedPorts.size > 0 || portCloseStates.size > 0);
  }

  function handlePortClosed(p, epoch) {
    unreleasedPorts.delete(p);
    if (port === p && (epoch == null || portEpochs.get(p) === epoch)) {
      port = null;
      reader = null;
      writer = null;
    }
    checkResourcesAndClearGuidance();
  }

  function requestClosePort(p) {
    if (!p) return Promise.resolve({ done: true });
    let epoch = portEpochs.get(p);
    if (epoch == null) {
      epoch = 1;
      portEpochs.set(p, epoch);
    }
    if (closedPortEpochs.get(p) === epoch) {
      return Promise.resolve({ done: true });
    }
    const existing = portCloseStates.get(p);
    if (existing) {
      if (existing.epoch === epoch && existing.status === 'closing') {
        return existing.promise;
      }
      // If previous status === 'error' or belonging to earlier epoch, allow starting a new close task below
    }

    const record = {
      epoch,
      status: 'closing',
      port: p,
      error: null,
      promise: null,
    };

    const task = (async () => {
      try {
        await p.close();
        closedPortEpochs.set(p, epoch);
        portCloseStates.delete(p);
        handlePortClosed(p, epoch);
        return { done: true };
      } catch (err) {
        record.status = 'error';
        record.error = err;
        throw err;
      }
    })();

    record.promise = task;
    portCloseStates.set(p, record);
    return task;
  }

  function checkResourcesAndClearGuidance() {
    if (!hasHeldResources() && !closing && !connectTask && !outstanding) {
      guidance = '';
      if (phase === 'closing') {
        setPhase('closed');
      }
    }
  }

  function emit() {
    for (const fn of listeners) {
      try { fn(phase, lastError); } catch { /* listener */ }
    }
  }

  function log(kind, detail) {
    records.push({ at: timer.now(), kind, detail });
    if (records.length > MAX_UI) records.shift();
  }

  function setPhase(next, detail) {
    phase = next;
    if (detail) lastError = detail;
    log(next, detail || '');
    emit();
  }

  function hold(detail) {
    guidance = 'resources held; retry disconnect before connecting again';
    lastError = `${detail}; ${guidance}`;
    setPhase('error', lastError);
  }

  function delay(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  function waitBound(promise, ms) {
    if (!promise) return Promise.resolve({ done: true });
    let timerId;
    const timeout = new Promise((resolve) => {
      timerId = setTimeout(() => resolve({ timedOut: true }), ms);
    });
    return Promise.race([
      Promise.resolve(promise).then((value) => ({ done: true, value }), (error) => ({ done: true, error })),
      timeout,
    ]).finally(() => clearTimeout(timerId));
  }

  function watch(promise) {
    if (!promise) return;
    promise.then(() => {}, () => {});
  }

  function endCapture(reason) {
    const run = capture;
    if (!run || run.stopped) return run;
    run.stopped = true;
    run.stop_reason = reason;
    if (reason !== 'stop') {
      run.healthy = false;
    }
    if (run.timer != null) timer.clearTimeout(run.timer);
    run.timer = null;
    pushEvent(run, { kind: 'stop', at_ms: timer.now(), detail: reason });
    return run;
  }

  function pushEvent(run, event) {
    if (!run.first_event_ms) run.first_event_ms = event.at_ms;
    run.last_event_ms = event.at_ms;
    run.event_total++;
    if (run.events.length >= maxEvents) {
      run.dropped_events++;
      run.truncated = true;
      run.events.shift();
    }
    run.events.push(event);
  }

  function pushError(run, error) {
    const at = timer.now();
    if (!run.first_error_ms) run.first_error_ms = at;
    run.last_error_ms = at;
    run.error_total++;
    run.healthy = false;
    if (run.errors.length >= maxErrors) {
      run.dropped_errors++;
      run.truncated = true;
      run.errors.shift();
    }
    run.errors.push({ at_ms: at, message: String(error) });
  }

  function gapCount(samples) {
    let gaps = 0;
    for (let i = 1; i < samples.length; i++) {
      const delta = samples[i].seq - samples[i - 1].seq;
      if (delta > 1) gaps += delta - 1;
    }
    return gaps;
  }

  function flushSegment(run) {
    if (!run.samples.length) return;
    const isSummaryOnly = run.segments.length >= maxSegments;
    const segment = {
      run_id: run.id,
      index: run.segment_total,
      seq_first: run.samples[0].seq,
      seq_last: run.samples[run.samples.length - 1].seq,
      at_first: run.samples[0].at_ms,
      at_last: run.samples[run.samples.length - 1].at_ms,
      count: run.samples.length,
      gaps: gapCount(run.samples),
      samples: isSummaryOnly ? [] : run.samples.slice(),
      summary_only: isSummaryOnly,
    };
    run.segment_total++;
    if (segment.summary_only) {
      run.truncated = true;
      if (run.coverage.length >= maxCoverageSegments) {
        const dropped = run.coverage.shift();
        run.dropped_segments++;
        run.dropped_samples += dropped.count;
      }
      run.coverage.push(segment);
    } else {
      run.segments.push(segment);
    }
    run.samples = [];
  }

  function recordSample(run, sample) {
    run.samples.push(sample);
    run.sample_total++;
    run.last_ms = sample.at_ms;
    if (run.samples.length >= maxSamples) flushSegment(run);
  }

  function beginSample(run) {
    if (!run || run.stopped) return Promise.resolve();
    if (run.sampling) {
      run.gaps++;
      run.healthy = false;
      return Promise.resolve();
    }
    run.sampling = true;
    run.sample_attempts++;
    const bound = {
      run,
      client: client,
      bootId: client?.bootId ?? null,
      sessionId: client?.sessionId ?? null,
      generation,
    };
    const task = (async () => {
      try {
        if (!bound.client || bound.client.inflight()) {
          run.gaps++;
          run.healthy = false;
          run.responses_error++;
          pushError(run, 'client unavailable or inflight collision');
          return;
        }
        const started = timer.now();
        const frame = await bound.client.request(CODE.STATUS_GET, {});
        const isOk = Boolean(frame?.json?.ok);
        if (isOk) {
          run.responses_ok++;
          recordSample(run, {
            kind: 'sample',
            seq: run.next_seq++,
            at_ms: timer.now(),
            rtt_ms: timer.now() - started,
            boot_id: bound.bootId,
            session_id: bound.sessionId,
            generation: bound.generation,
            status: frame?.json?.result ?? null,
            ok: true,
          });
        } else {
          run.responses_error++;
          run.healthy = false;
          const errDetail = frame?.json?.error?.message || frame?.json?.error?.code || 'rpc ok:false';
          pushError(run, `STATUS_GET ok:false - ${errDetail}`);
          recordSample(run, {
            kind: 'error_response',
            seq: run.next_seq++,
            at_ms: timer.now(),
            rtt_ms: timer.now() - started,
            boot_id: bound.bootId,
            session_id: bound.sessionId,
            generation: bound.generation,
            error: frame?.json?.error ?? null,
            ok: false,
          });
        }
      } catch (error) {
        run.responses_error++;
        pushError(run, error);
        recordSample(run, {
          kind: 'error',
          seq: run.next_seq++,
          at_ms: timer.now(),
          generation: bound.generation,
          message: String(error),
          ok: false,
        });
      } finally {
        run.sampling = false;
      }
    })();
    run.inflight.add(task);
    watch(task.finally(() => run.inflight.delete(task)));
    return task;
  }

  function armCapture(run) {
    if (!run || run.stopped) return;
    run.timer = timer.setTimeout(() => {
      if (!run || run.stopped || capture !== run) return;
      run.timer = null;
      watch(beginSample(run).finally(() => armCapture(run)));
    }, run.interval_ms);
  }

  async function releaseIo() {
    const tail = writeTail;
    writeTail = Promise.resolve();
    const wrote = await waitBound(tail, ioWaitMs);
    if (wrote.timedOut) return { timedOut: true, label: 'write' };
    const activeReader = reader;
    if (activeReader) {
      const cancelled = await waitBound(activeReader.cancel(), ioWaitMs);
      if (cancelled.timedOut) return { timedOut: true, label: 'cancel' };
    }
    if (readTask) {
      const read = await waitBound(readTask, ioWaitMs);
      if (read.timedOut) return { timedOut: true, label: 'read' };
      readTask = null;
    }
    if (activeReader) {
      try { activeReader.releaseLock(); } catch { /* released */ }
      if (reader === activeReader) reader = null;
    }
    const activeWriter = writer;
    writer = null;
    if (activeWriter) {
      try { activeWriter.releaseLock(); } catch { /* released */ }
    }
    if (wrote.error && String(wrote.error).includes('timeout')) return { error: wrote.error, label: 'write' };
    return { done: true };
  }

  function adoptLate(task) {
    if (!task) return;
    const prev = outstanding;
    const tracked = (async () => {
      if (prev) {
        try { await prev; } catch { /* ignore previous error */ }
      }
      try {
        await task;
      } catch {
        /* late errors handled */
      }
    })();
    outstanding = tracked;
    watch(tracked.finally(() => {
      if (outstanding === tracked) {
        outstanding = null;
      }
      checkResourcesAndClearGuidance();
    }));
  }

  return {
    state() { return phase; },
    lastError() { return lastError; },
    guidance() { return guidance; },
    records() { return records.slice(); },
    subscribe(fn) {
      listeners.add(fn);
      return () => listeners.delete(fn);
    },
    capture() { return capture; },
    async sampleOnce() {
      if (!capture || capture.stopped) return;
      return beginSample(capture);
    },
    async connect(serial) {
      if (hasHeldResources() || closing || connectTask || outstanding || phase === 'selecting' || phase === 'opening' || phase === 'handshaking' || phase === 'closing') {
        throw new Error(guidance || 'busy');
      }
      const token = ++generation;
      const task = (async () => {
        setPhase('selecting');
        let selected;
        try {
          selected = await serial.requestPort();
        } catch (error) {
          if (token !== generation) return;
          lastError = String(error);
          setPhase('idle', 'select cancelled');
          throw error;
        }
        if (token !== generation) return;
        if (selected.readable || selected.writable) {
          lastError = 'streams before open';
          setPhase('error', lastError);
          throw new Error(lastError);
        }
        setPhase('opening');
        const nextEpoch = (portEpochs.get(selected) || 0) + 1;
        portEpochs.set(selected, nextEpoch);
        try {
          await selected.open({ baudRate: 115200 });
        } catch (error) {
          if (token !== generation) return;
          lastError = String(error);
          setPhase('error', 'open failed');
          throw error;
        }
        if (token !== generation) {
          const closed = await waitBound(requestClosePort(selected), ioWaitMs);
          if (closed.timedOut || closed.error) {
            unreleasedPorts.add(selected);
            hold(closed.error || 'late close timed out');
          }
          return;
        }
        port = selected;
        if (!selected.readable || !selected.writable) {
          lastError = 'streams missing';
          setPhase('error', lastError);
          throw new Error(lastError);
        }
        const transport = {
          async write(bytes) {
            if (token !== generation || port !== selected) throw new Error('stale write');
            const run = writeTail.then(async () => {
              if (token !== generation || port !== selected) throw new Error('stale write');
              const active = selected.writable.getWriter();
              writer = active;
              try {
                await active.write(bytes);
              } finally {
                try { active.releaseLock(); } catch { /* released */ }
                if (writer === active) writer = null;
              }
            });
            writeTail = run.then(() => {}, () => {});
            return run;
          },
          onData() {},
        };
        client = createClient(transport);
        reader = selected.readable.getReader();
        readTask = (async () => {
          try {
            for (;;) {
              const next = await reader.read();
              if (token !== generation) break;
              if (next.done) {
                failRead('eof');
                break;
              }
              client?.ingest(next.value);
            }
          } catch (error) {
            if (token === generation) failRead(String(error));
          }
        })();
        watch(readTask);
        setPhase('handshaking');
        const frame = await client.hello(hello);
        if (token !== generation) return;
        if (!frame?.json?.ok) throw new Error('handshake');
        client.startHeartbeat();
        setPhase('online');
        return frame;
      })();
      connectTask = task;
      try {
        return await task;
      } catch (error) {
        if (token !== generation) throw error;
        endCapture('handshake');
        hold(error);
        watch(releaseIo());
        throw error;
      } finally {
        if (connectTask === task) connectTask = null;
        checkResourcesAndClearGuidance();
      }
    },
    async disconnect() {
      if (closing) return closing;
      generation += 1;
      const gen = generation;
      setPhase('closing', 'disconnect');
      endCapture('disconnect');
      client?.stopHeartbeat?.();
      try { client?.disconnect?.(); } catch { /* already stopped */ }
      const task = (async () => {
        if (outstanding) {
          const lateWait = await waitBound(outstanding, ioWaitMs);
          if (lateWait.timedOut) {
            hold('late cleanup still pending');
            throw new Error(lastError);
          }
        }
        const connectWait = await waitBound(connectTask, ioWaitMs);
        if (connectWait.timedOut) {
          adoptLate(connectTask);
          hold('connect still pending');
          throw new Error(lastError);
        }
        const released = await releaseIo();
        if (released.timedOut || released.error) {
          hold(released.error || `${released.label} timeout`);
          throw new Error(lastError);
        }
        if (unreleasedPorts.size > 0) {
          for (const p of [...unreleasedPorts]) {
            const cl = await waitBound(requestClosePort(p), ioWaitMs);
            if (!cl.timedOut && !cl.error) {
              unreleasedPorts.delete(p);
            }
          }
          if (unreleasedPorts.size > 0) {
            hold('late close timed out');
            throw new Error(lastError);
          }
        }
        if (!port) {
          guidance = '';
          if (generation === gen) setPhase('closed');
          return;
        }
        const currentPort = port;
        const closed = await waitBound(requestClosePort(currentPort), ioWaitMs);
        if (closed.timedOut || closed.error) {
          unreleasedPorts.add(currentPort);
          hold(closed.error || 'close timeout');
          throw new Error(lastError);
        }
        if (port === currentPort) {
          port = null;
        }
        reader = null;
        writer = null;
        guidance = '';
        if (generation === gen) setPhase('closed');
      })();
      closing = task;
      watch(task.finally(() => {
        if (closing === task) closing = null;
        checkResourcesAndClearGuidance();
      }));
      return task;
    },
    startCapture() {
      if (phase !== 'online' || !client) throw new Error('offline');
      if (capture && !capture.stopped) throw new Error('capturing');
      const runId = `${Math.floor(timer.now()).toString(16)}-${generation}`;
      capture = {
        id: runId,
        run_id: runId,
        generation,
        interval_ms: captureIntervalMs,
        started_ms: timer.now(),
        last_ms: timer.now(),
        start: { kind: 'start', at_ms: timer.now(), run_id: runId, boot_id: client.bootId, session_id: client.sessionId },
        samples: [],
        segments: [],
        coverage: [],
        events: [],
        errors: [],
        inflight: new Set(),
        gaps: 0,
        dropped_events: 0,
        dropped_errors: 0,
        dropped_segments: 0,
        dropped_samples: 0,
        event_total: 0,
        error_total: 0,
        sample_attempts: 0,
        responses_ok: 0,
        responses_error: 0,
        sample_total: 0,
        segment_total: 0,
        truncated: false,
        stopped: false,
        stop_reason: null,
        healthy: true,
        sampling: false,
        next_seq: 1,
        export_index: 0,
        timer: null,
      };
      client.stopHeartbeat();
      armCapture(capture);
      setPhase('online', 'capture');
      return capture.run_id;
    },
    async stopCapture() {
      const run = endCapture('stop');
      if (!run) return;
      await waitBound(Promise.all([...run.inflight]), ioWaitMs);
      if (phase === 'online' && client) client.startHeartbeat();
      return run;
    },
    exportEvidence() {
      if (!capture) return JSON.stringify({ error: 'no-run', healthy: false });

      const stored = capture.segments.concat(capture.coverage);
      const pendingSamples = capture.samples.slice();
      const hasPending = pendingSamples.length > 0;

      const pendingSegment = hasPending ? {
        run_id: capture.id,
        index: capture.segment_total,
        seq_first: pendingSamples[0].seq,
        seq_last: pendingSamples[pendingSamples.length - 1].seq,
        at_first: pendingSamples[0].at_ms,
        at_last: pendingSamples[pendingSamples.length - 1].at_ms,
        count: pendingSamples.length,
        gaps: gapCount(pendingSamples),
        samples: pendingSamples,
        summary_only: false,
        is_pending_tail: true,
        uncommitted_snapshot: true,
      } : null;

      const snapshotSegments = pendingSegment ? stored.concat([pendingSegment]) : stored.slice();
      const rawSamples = capture.segments.flatMap((segment) => segment.samples).concat(pendingSamples);
      const rawSampleCount = rawSamples.length;
      const summaryOnlyCount = capture.coverage.reduce((sum, s) => sum + s.count, 0);
      const storedCount = rawSampleCount + summaryOnlyCount;

      const missingSequences = [];
      const duplicateSequences = [];
      for (let i = 0; i < snapshotSegments.length - 1; i++) {
        const cur = snapshotSegments[i];
        const next = snapshotSegments[i + 1];
        if (next.seq_first > cur.seq_last + 1) {
          missingSequences.push({
            expected_from: cur.seq_last + 1,
            expected_to: next.seq_first - 1,
            count: next.seq_first - cur.seq_last - 1,
          });
        } else if (next.seq_first <= cur.seq_last) {
          duplicateSequences.push({
            seq_start: next.seq_first,
            seq_end: cur.seq_last,
            count: cur.seq_last - next.seq_first + 1,
          });
        }
      }

      const seqs = snapshotSegments.flatMap((segment) => [segment.seq_first, segment.seq_last]).filter((value) => value != null);
      const seqFirst = seqs.length ? Math.min(...seqs) : null;
      const seqLast = seqs.length ? Math.max(...seqs) : null;
      const expectedSpan = seqFirst == null ? 0 : seqLast - seqFirst + 1;
      const missingCount = Math.max(0, expectedSpan - storedCount);
      const totalGaps = capture.gaps + snapshotSegments.reduce((sum, segment) => sum + segment.gaps, 0);

      const rawEvidenceComplete = rawSampleCount === capture.sample_attempts &&
                                  capture.sample_attempts > 0 &&
                                  capture.dropped_samples === 0 &&
                                  summaryOnlyCount === 0 &&
                                  missingCount === 0;

      const summaryCoverageComplete = missingCount === 0 &&
                                      capture.dropped_segments === 0 &&
                                      capture.dropped_samples === 0 &&
                                      expectedSpan > 0;

      const connectionOk = phase === 'online' || (capture.stopped && capture.stop_reason === 'stop');
      const captureOk = capture.healthy && capture.error_total === 0 && totalGaps === 0 && capture.responses_error === 0;
      const stoppedCleanly = capture.stopped ? capture.stop_reason === 'stop' : true;

      capture.export_index += 1;
      return JSON.stringify({
        run_id: capture.run_id,
        export_index: capture.export_index,
        started_ms: capture.started_ms,
        last_ms: capture.last_ms,
        interval_ms: capture.interval_ms,
        start: capture.start,
        segments: snapshotSegments,
        samples: rawSamples,
        pending_samples: pendingSamples,
        has_pending_tail: hasPending,
        sample_attempts: capture.sample_attempts,
        responses_ok: capture.responses_ok,
        responses_error: capture.responses_error,
        raw_samples_retained: rawSampleCount,
        summary_only_samples: summaryOnlyCount,
        dropped_samples: capture.dropped_samples,
        dropped_segments: capture.dropped_segments,
        dropped_events: capture.dropped_events,
        dropped_errors: capture.dropped_errors,
        error_total: capture.error_total,
        event_total: capture.event_total,
        sample_count: storedCount,
        seq_first: seqFirst,
        seq_last: seqLast,
        missing: missingCount,
        gaps: totalGaps,
        missing_sequences: missingSequences,
        duplicate_sequences: duplicateSequences,
        reconstruction_valid: missingSequences.length === 0 && duplicateSequences.length === 0,
        truncated: capture.truncated,
        errors: capture.errors,
        events: capture.events,
        identity: { boot_id: capture.start.boot_id, session_id: capture.start.session_id, generation: capture.generation },
        connection: phase,
        health_assessment: {
          connection_ok: connectionOk,
          no_capture_failures: captureOk,
          raw_evidence_complete: rawEvidenceComplete,
          summary_coverage_complete: summaryCoverageComplete,
          stopped_cleanly: capture.stopped ? capture.stop_reason === 'stop' : null,
          software_healthy: connectionOk && captureOk && rawEvidenceComplete && stoppedCleanly,
          hardware_g0_verified: false,
        },
        raw_evidence_complete: rawEvidenceComplete,
        summary_coverage_complete: summaryCoverageComplete,
        healthy: connectionOk && captureOk && rawEvidenceComplete && stoppedCleanly,
        rtt_clock: 'local_monotonic',
        duration_note: 'software capture only; not a two-hour hardware run',
      });
    },
  };

  function failRead(detail) {
    endCapture(detail);
    hold(detail);
    watch((async () => {
      const released = await releaseIo();
      if (released.timedOut || released.error) {
        hold(released.error || `${released.label} timeout`);
        return;
      }
      if (!port) return;
      const targetPort = port;
      const closed = await waitBound(requestClosePort(targetPort), ioWaitMs);
      if (closed.timedOut || closed.error) {
        unreleasedPorts.add(targetPort);
        hold(closed.error || 'close timeout');
      } else {
        if (port === targetPort) port = null;
      }
    })());
  }
}
