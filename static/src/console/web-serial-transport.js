/**
 * Byte transport expected by ProtocolClient:
 *   write(Uint8Array), onData(callback), close()
 * One reader at a time. close() cancels the reader and releases its lock.
 */

export class WebSerialTransport {
  constructor(port) {
    this.port = port;
    this.listener = null;
    this.reader = null;
    this.writer = null;
    this.reading = null;
    this.stopped = false;
  }

  onData(callback) {
    this.listener = callback;
  }

  start() {
    if (this.reading || this.stopped) return this.reading;
    this.reading = this.pump();
    return this.reading;
  }

  async pump() {
    const readable = this.port?.readable;
    if (!readable) return;
    let reader;
    try {
      reader = readable.getReader();
    } catch {
      return;
    }
    this.reader = reader;
    try {
      while (!this.stopped) {
        const { value, done } = await reader.read();
        if (done) break;
        if (value && this.listener) this.listener(value);
      }
    } catch {
      /* disconnect or cancel */
    } finally {
      try { reader.releaseLock(); } catch { /* already released */ }
      if (this.reader === reader) this.reader = null;
    }
  }

  async write(bytes) {
    if (this.stopped) throw new Error('transport_closed');
    const writable = this.port?.writable;
    if (!writable) throw new Error('transport_not_writable');
    const writer = this.writer || writable.getWriter();
    this.writer = writer;
    await writer.write(bytes);
  }

  async close() {
    this.stopped = true;
    try { await this.reader?.cancel(); } catch { /* already cancelled */ }
    try { await this.reading; } catch { /* pump ended */ }
    try {
      if (this.writer) {
        try { this.writer.releaseLock(); } catch { /* ignore */ }
        this.writer = null;
      }
    } catch { /* ignore */ }
    this.listener = null;
  }
}
