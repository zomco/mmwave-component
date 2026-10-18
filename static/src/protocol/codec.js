import { cobsDecode, cobsEncode } from './cobs.js';
import { crc32c } from './crc32c.js';
import { checkJson } from './json.js';
import { HALF_FRAME_MS, HEADER_LEN, KIND, MAGIC, MAJOR, MAX_COBS, MAX_DECODED, MAX_PAYLOAD, MAX_WIRE, MINOR } from './limits.js';
import { encodeUtf8, isStrictUtf8 } from './utf8.js';

export function encodeFrame(input) {
  const payload = input.payload instanceof Uint8Array ? input.payload : encodeUtf8(input.payloadText ?? '');
  if (payload.length > MAX_PAYLOAD) return { ok: false, error: 'payload_too_large' };
  if (input.flags && input.flags !== 0) return { ok: false, error: 'bad_flags' };
  if ((input.major ?? MAJOR) !== MAJOR || (input.minor ?? MINOR) !== MINOR) return { ok: false, error: 'bad_version' };
  if (input.checkJson !== false) {
    const json = checkJson(payload);
    if (!json.ok) return { ok: false, error: json.error };
  }
  const decoded = new Uint8Array(HEADER_LEN + payload.length + 4);
  decoded.set(MAGIC, 0);
  decoded[4] = MAJOR;
  decoded[5] = MINOR;
  decoded[6] = input.kind;
  decoded[7] = 0;
  writeU32(decoded, 8, input.sessionId >>> 0);
  writeU32(decoded, 12, input.requestId >>> 0);
  writeU16(decoded, 16, input.code);
  writeU16(decoded, 18, payload.length);
  writeU32(decoded, 20, input.wireSeq >>> 0);
  decoded.set(payload, HEADER_LEN);
  const crc = crc32c(decoded.subarray(0, HEADER_LEN + payload.length));
  writeU32(decoded, HEADER_LEN + payload.length, crc);
  const encoded = cobsEncode(decoded);
  if (encoded.length > MAX_COBS) return { ok: false, error: 'oversize' };
  const wire = new Uint8Array(encoded.length + 2);
  wire[0] = 0;
  wire.set(encoded, 1);
  wire[wire.length - 1] = 0;
  if (wire.length > MAX_WIRE) return { ok: false, error: 'oversize' };
  return { ok: true, decoded, wire, crc, payloadLength: payload.length };
}

export function decodeDecoded(decoded, { validateJson = true } = {}) {
  if (!(decoded instanceof Uint8Array)) decoded = Uint8Array.from(decoded);
  if (decoded.length < HEADER_LEN + 4 || decoded.length > MAX_DECODED) return { ok: false, error: 'bad_length' };
  if (decoded[0] !== MAGIC[0] || decoded[1] !== MAGIC[1] || decoded[2] !== MAGIC[2] || decoded[3] !== MAGIC[3]) {
    return { ok: false, error: 'bad_magic' };
  }
  if (decoded[4] !== MAJOR || decoded[5] !== MINOR) return { ok: false, error: 'bad_version' };
  const kind = decoded[6];
  if (kind !== KIND.request && kind !== KIND.response && kind !== KIND.event) return { ok: false, error: 'bad_kind' };
  if (decoded[7] !== 0) return { ok: false, error: 'bad_flags' };
  const payloadLength = readU16(decoded, 18);
  if (payloadLength > MAX_PAYLOAD) return { ok: false, error: 'payload_too_large' };
  if (decoded.length !== HEADER_LEN + payloadLength + 4) return { ok: false, error: 'bad_length' };
  const expected = crc32c(decoded.subarray(0, HEADER_LEN + payloadLength));
  const actual = readU32(decoded, HEADER_LEN + payloadLength);
  if (expected !== actual) return { ok: false, error: 'bad_crc' };
  const payload = decoded.subarray(HEADER_LEN, HEADER_LEN + payloadLength);
  if (!isStrictUtf8(payload)) return { ok: false, error: 'bad_utf8' };
  let json = null;
  if (validateJson) {
    json = checkJson(payload);
    if (!json.ok) return { ok: false, error: json.error, header: headerOf(decoded, payload) };
  }
  return { ok: true, ...headerOf(decoded, payload), json: json ? json.value : null };
}

export function decodeWire(wire, options) {
  const src = wire instanceof Uint8Array ? wire : Uint8Array.from(wire);
  if (src.length < 2 || src[0] !== 0 || src[src.length - 1] !== 0) return { ok: false, error: 'bad_framing' };
  const body = src.subarray(1, src.length - 1);
  if (body.length === 0 || body.length > MAX_COBS) return { ok: false, error: 'oversize' };
  const decoded = cobsDecode(body);
  if (!decoded.ok) return decoded;
  return decodeDecoded(decoded.data, options);
}

export class FrameParser {
  constructor() {
    this.buf = [];
    this.discarding = false;
    this.lastByteMs = null;
    this.stats = emptyStats();
  }

  push(bytes, nowMs = 0) {
    const frames = [];
    const errors = [];
    const src = bytes instanceof Uint8Array ? bytes : Uint8Array.from(bytes);
    for (let i = 0; i < src.length; i++) this._byte(src[i], nowMs, frames, errors);
    return { frames, errors, stats: this.stats };
  }

  poll(nowMs) {
    const errors = [];
    if (!this.discarding && this.buf.length > 0 && this.lastByteMs !== null && nowMs - this.lastByteMs >= HALF_FRAME_MS) {
      this.discarding = true;
      this.buf = [];
      this.stats.timeouts++;
      errors.push({ error: 'timeout' });
    }
    return { frames: [], errors, stats: this.stats };
  }

  _byte(byte, nowMs, frames, errors) {
    this.lastByteMs = nowMs;
    if (byte === 0) {
      if (this.discarding) {
        this.discarding = false;
        this.buf = [];
        return;
      }
      if (this.buf.length === 0) return;
      this._finish(frames, errors);
      return;
    }
    if (this.discarding) return;
    if (this.buf.length >= MAX_COBS) {
      this.discarding = true;
      this.buf = [];
      this.stats.oversize++;
      errors.push({ error: 'oversize' });
      return;
    }
    this.buf.push(byte);
  }

  _finish(frames, errors) {
    const encoded = Uint8Array.from(this.buf);
    this.buf = [];
    if (encoded.length > MAX_COBS) {
      this.stats.oversize++;
      errors.push({ error: 'oversize' });
      return;
    }
    const decoded = cobsDecode(encoded);
    if (!decoded.ok) {
      this.stats.badCobs++;
      errors.push({ error: 'bad_cobs' });
      return;
    }
    const frame = decodeDecoded(decoded.data);
    if (!frame.ok) {
      bump(this.stats, frame.error);
      errors.push({ error: frame.error, header: frame.header });
      return;
    }
    this.stats.frames++;
    frames.push(frame);
  }
}

function headerOf(decoded, payload) {
  return {
    major: decoded[4],
    minor: decoded[5],
    kind: decoded[6],
    flags: decoded[7],
    sessionId: readU32(decoded, 8),
    requestId: readU32(decoded, 12),
    code: readU16(decoded, 16),
    payloadLength: readU16(decoded, 18),
    wireSeq: readU32(decoded, 20),
    payload,
  };
}

function bump(stats, error) {
  if (error === 'bad_crc') stats.badCrc++;
  else if (error === 'bad_utf8') stats.badUtf8++;
  else if (error === 'oversize' || error === 'payload_too_large' || error === 'bad_length') stats.oversize++;
  else if (error === 'bad_cobs') stats.badCobs++;
  else if (String(error).startsWith('bad_') || error === 'duplicate_key' || error === 'depth' || error === 'number' || error === 'unsafe_integer' || error === 'root' || error === 'bom' || error === 'trailing' || error === 'surrogate' || error === 'keys' || error === 'items') stats.badJson++;
  else stats.badHeader++;
}

function emptyStats() {
  return { frames: 0, badCobs: 0, badCrc: 0, badHeader: 0, badUtf8: 0, badJson: 0, oversize: 0, timeouts: 0 };
}

function writeU16(buf, offset, value) {
  buf[offset] = value & 0xff;
  buf[offset + 1] = (value >>> 8) & 0xff;
}

function writeU32(buf, offset, value) {
  buf[offset] = value & 0xff;
  buf[offset + 1] = (value >>> 8) & 0xff;
  buf[offset + 2] = (value >>> 16) & 0xff;
  buf[offset + 3] = (value >>> 24) & 0xff;
}

function readU16(buf, offset) {
  return buf[offset] | (buf[offset + 1] << 8);
}

function readU32(buf, offset) {
  return (buf[offset] | (buf[offset + 1] << 8) | (buf[offset + 2] << 16) | (buf[offset + 3] << 24)) >>> 0;
}

export function hexToBytes(hex) {
  const clean = hex.replace(/\s+/g, '');
  if (clean.length % 2 !== 0) throw new Error('odd hex');
  const out = new Uint8Array(clean.length / 2);
  for (let i = 0; i < out.length; i++) out[i] = Number.parseInt(clean.slice(i * 2, i * 2 + 2), 16);
  return out;
}

export function bytesToHex(bytes) {
  let hex = '';
  for (let i = 0; i < bytes.length; i++) hex += bytes[i].toString(16).padStart(2, '0');
  return hex;
}
