/**
 * Single owner of a Web Serial port for this page.
 * The installer and the console never hold readable/writable together.
 * A "closed" UI event is not proof that port.close() finished.
 */

export const OWNERS = {
  none: 'none',
  console: 'console',
  installer: 'installer',
};

const LOCK_NAME = 'mmwave-usb-serial';

export class SerialCoordinator {
  constructor(options = {}) {
    this.serial = options.serial ?? null;
    this.locks = options.locks ?? null;
    this.channelFactory = options.channelFactory ?? null;
    this.claimReleasedPort = options.claimReleasedPort;
    this.owner = OWNERS.none;
    this.port = null;
    this.generation = 0;
    this.closing = null;
    this.lockRelease = null;
    this.channel = null;
    this.peerHint = null;
    this.onChange = options.onChange || (() => {});
    if (this.channelFactory) {
      try {
        this.channel = this.channelFactory('mmwave-usb-serial');
        this.channel.onmessage = (event) => {
          const data = event?.data;
          if (!data || data.source === this.generation) return;
          if (data.type === 'held' && this.owner === OWNERS.none) {
            this.peerHint = data.owner || 'peer';
            this.emit();
          }
          if (data.type === 'released') {
            this.peerHint = null;
            this.emit();
          }
        };
      } catch {
        this.channel = null;
      }
    }
  }

  support(isSecureContext = true) {
    if (!isSecureContext) return { ok: false, reason: 'insecure_context' };
    if (!this.serial || typeof this.serial.requestPort !== 'function') return { ok: false, reason: 'no_web_serial' };
    return { ok: true, reason: null };
  }

  snapshot() {
    return {
      owner: this.owner,
      generation: this.generation,
      busy: this.closing != null,
      peerHint: this.peerHint,
      portClosed: this.port ? this.port.readable == null && this.port.writable == null : true,
    };
  }

  emit() {
    this.onChange(this.snapshot());
  }

  announce(type) {
    try {
      this.channel?.postMessage({ type, owner: this.owner, source: this.generation });
    } catch {
      /* BroadcastChannel is a hint, not a lock. */
    }
  }

  async acquireLock() {
    if (!this.locks?.request) return;
    await new Promise((resolve, reject) => {
      let settled = false;
      const finish = (fn, value) => {
        if (settled) return;
        settled = true;
        fn(value);
      };
      const pending = this.locks.request(LOCK_NAME, { mode: 'exclusive', ifAvailable: true }, (lock) => {
        if (!lock) {
          finish(reject, Object.assign(new Error('lock_unavailable'), { code: 'lock_unavailable' }));
          return undefined;
        }
        return new Promise((release) => {
          this.lockRelease = () => {
            this.lockRelease = null;
            release();
          };
          finish(resolve);
        });
      });
      Promise.resolve(pending).catch((error) => finish(reject, error));
    });
  }

  releaseLock() {
    const release = this.lockRelease;
    this.lockRelease = null;
    try { release?.(); } catch { /* ignore */ }
  }

  /**
   * User gesture only. A cancelled chooser is not a device fault.
   * Already-authorized ports are never opened here.
   */
  async connect({ open, isSecureContext = true } = {}) {
    const support = this.support(isSecureContext);
    if (!support.ok) return { ok: false, reason: support.reason };
    if (this.owner === OWNERS.console || this.closing) return { ok: false, reason: 'port_busy', owner: this.owner };
    if (this.owner === OWNERS.installer) this.owner = OWNERS.none;
    let port;
    try {
      port = await this.serial.requestPort();
    } catch (error) {
      const name = error?.name || '';
      if (name === 'NotFoundError' || name === 'AbortError') return { ok: false, reason: 'chooser_cancelled' };
      return { ok: false, reason: 'request_failed', error: name || 'Error' };
    }
    if (!port) return { ok: false, reason: 'chooser_cancelled' };
    try {
      await this.acquireLock();
    } catch {
      return { ok: false, reason: 'peer_holds_port' };
    }
    const opener = open || ((selected) => selected.open({ baudRate: 115200, bufferSize: 16384, dataBits: 8, stopBits: 1, parity: 'none', flowControl: 'none' }));
    try {
      await opener(port);
    } catch (error) {
      this.releaseLock();
      const name = error?.name || 'Error';
      if (name === 'InvalidStateError' || name === 'NetworkError') return { ok: false, reason: 'port_busy', error: name };
      return { ok: false, reason: 'open_failed', error: name };
    }
    if (port.readable == null || port.writable == null) {
      this.releaseLock();
      return { ok: false, reason: 'open_did_not_acquire' };
    }
    this.port = port;
    this.owner = OWNERS.console;
    this.generation += 1;
    this.peerHint = null;
    const generation = this.generation;
    const onDisconnect = () => {
      if (this.generation !== generation || this.port !== port) return;
      this.forceDrop('unplugged');
    };
    try { port.addEventListener?.('disconnect', onDisconnect); } catch { /* optional */ }
    this.announce('held');
    this.emit();
    return { ok: true, owner: OWNERS.console, port, generation, detach: () => { try { port.removeEventListener?.('disconnect', onDisconnect); } catch { /* ignore */ } } };
  }

  /** Installer still owns the port until readable and writable are both gone. */
  noteInstallerHolding() {
    if (this.owner === OWNERS.console) return { ok: false, reason: 'console_holds_port' };
    this.owner = OWNERS.installer;
    this.emit();
    this.announce('held');
    return { ok: true, owner: OWNERS.installer };
  }

  noteInstallerClosedEvent() {
    return { ok: true, released: false, reason: 'closed_event_is_not_close' };
  }

  async claimAfterInstaller(port, open) {
    if (this.owner === OWNERS.console) return { ok: false, reason: 'console_holds_port' };
    const claim = this.claimReleasedPort;
    if (!claim) return { ok: false, reason: 'no_claim_helper' };
    const result = await claim(port, open);
    if (!result.ok) {
      this.owner = OWNERS.installer;
      this.emit();
      return result;
    }
    this.port = port;
    this.owner = OWNERS.console;
    this.generation += 1;
    this.emit();
    this.announce('held');
    return { ...result, generation: this.generation };
  }

  /** Cancel the reader, release its lock, then wait until close() settles. */
  async disconnect(session) {
    if (this.owner !== OWNERS.console && !this.port) {
      return { ok: true, reason: 'already_idle' };
    }
    if (this.closing) return this.closing;
    const generation = this.generation;
    this.closing = (async () => {
      let readCancelled = false;
      try {
        await session?.stop?.();
        readCancelled = true;
      } catch {
        readCancelled = false;
      }
      const port = this.port;
      let closeError = null;
      try {
        if (port && (port.readable || port.writable)) await port.close();
      } catch (error) {
        closeError = error?.name || 'close_failed';
      }
      const released = !port || (port.readable == null && port.writable == null);
      if (generation === this.generation) {
        this.port = released ? null : port;
        this.owner = released ? OWNERS.none : OWNERS.console;
        if (released) this.releaseLock();
      }
      this.announce('released');
      this.emit();
      return { ok: released, readCancelled, closeError, owner: this.owner };
    })();
    try {
      return await this.closing;
    } finally {
      this.closing = null;
    }
  }

  forceDrop(reason = 'dropped') {
    const port = this.port;
    this.port = null;
    this.owner = OWNERS.none;
    this.generation += 1;
    this.releaseLock();
    try { port?.readable?.cancel?.(); } catch { /* already gone */ }
    this.announce('released');
    this.emit();
    try { this.onUnplug?.(reason); } catch { /* session stop is best-effort */ }
    return { ok: true, reason, owner: OWNERS.none };
  }
}
