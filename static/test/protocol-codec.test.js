import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { cobsDecode, cobsEncode } from '../src/protocol/cobs.js';
import { crc32c, crc32cHex } from '../src/protocol/crc32c.js';
import { bytesToHex, decodeWire, encodeFrame, FrameParser, hexToBytes } from '../src/protocol/codec.js';
import { checkJson } from '../src/protocol/json.js';
import { MAX_COBS, MAX_DECODED, MAX_PAYLOAD, MAX_WIRE } from '../src/protocol/limits.js';
import { encodeUtf8, utf8ByteLength } from '../src/protocol/utf8.js';

const vectors = JSON.parse(readFileSync(new URL('../../protocol/fixtures/protocol-vectors.json', import.meta.url), 'utf8'));

test('CRC32C matches the Castagnoli check value', () => {
  assert.equal(crc32cHex(encodeUtf8(vectors.crc32c_check.ascii)), vectors.crc32c_check.hex);
  assert.equal(bytesToHex(Uint8Array.of(crc32c(encodeUtf8('123456789')) & 0xff, (crc32c(encodeUtf8('123456789')) >>> 8) & 0xff, (crc32c(encodeUtf8('123456789')) >>> 16) & 0xff, (crc32c(encodeUtf8('123456789')) >>> 24) & 0xff)), '839206e3');
});

test('golden frames encode and decode byte-for-byte', () => {
  for (const frame of vectors.frames) {
    const encoded = encodeFrame({
      kind: frame.kind,
      sessionId: frame.session_id,
      requestId: frame.request_id,
      code: frame.code,
      wireSeq: frame.wire_seq,
      payload: encodeUtf8(frame.payload_text),
    });
    assert.equal(encoded.ok, true, frame.id);
    assert.equal(encoded.payloadLength, frame.payload_utf8_length, frame.id);
    assert.equal(bytesToHex(encoded.decoded), frame.decoded_hex, frame.id);
    assert.equal(bytesToHex(encoded.wire), frame.wire_hex, frame.id);
    assert.equal(encoded.crc.toString(16).padStart(8, '0'), frame.crc32c_hex, frame.id);
    const decoded = decodeWire(hexToBytes(frame.wire_hex));
    assert.equal(decoded.ok, true, frame.id);
    assert.equal(new TextDecoder().decode(decoded.payload), frame.payload_text, frame.id);
  }
});

test('golden COBS cases and standard block sizes round-trip', () => {
  for (const item of vectors.cobs_cases) {
    const decoded = hexToBytes(item.decoded_hex);
    assert.equal(bytesToHex(cobsEncode(decoded)), item.encoded_hex, item.id);
    assert.deepEqual(cobsDecode(hexToBytes(item.encoded_hex)).data, decoded, item.id);
  }
  for (const size of [0, 1, 253, 254, 255, 508]) {
    const data = new Uint8Array(size);
    data.fill(0x11);
    const encoded = cobsEncode(data);
    const back = cobsDecode(encoded);
    assert.equal(back.ok, true, String(size));
    assert.deepEqual(back.data, data, String(size));
  }
  const all = new Uint8Array(256);
  for (let i = 0; i < 256; i++) all[i] = i;
  assert.deepEqual(cobsDecode(cobsEncode(all)).data, all);
  const zeros = new Uint8Array(8);
  assert.deepEqual(cobsDecode(cobsEncode(zeros)).data, zeros);
  const block = cobsEncode(new Uint8Array(254).fill(0x11));
  assert.equal(block[0], 0xff);
  assert.equal(block[block.length - 1], 0x01);
});

test('parser accepts every chunk boundary, sticky frames and recovers', () => {
  const wires = vectors.frames.map((frame) => hexToBytes(frame.wire_hex));
  const sticky = concat(wires);
  for (let cut = 1; cut < sticky.length; cut++) {
    const parser = new FrameParser();
    const first = parser.push(sticky.subarray(0, cut));
    const second = parser.push(sticky.subarray(cut));
    const frames = [...first.frames, ...second.frames];
    assert.equal(frames.length, wires.length, `cut ${cut}`);
    frames.forEach((frame, index) => assert.equal(frame.requestId, vectors.frames[index].request_id));
  }
  const parser = new FrameParser();
  const one = parser.push(sticky.subarray(0, 1), 0);
  parser.poll(1999);
  const rest = parser.push(sticky.subarray(1), 1000);
  assert.equal(one.frames.length + rest.frames.length, wires.length);
  const timed = new FrameParser();
  timed.push(sticky.subarray(0, 4), 0);
  const expired = timed.poll(2000);
  assert.equal(expired.errors[0].error, 'timeout');
  const recovered = timed.push(wires[0], 2001);
  assert.equal(recovered.frames.length, 1);
  assert.equal(recovered.frames[0].code, vectors.frames[0].code);
});

test('noise, bad CRC, oversize and illegal JSON do not yield a command', () => {
  const good = hexToBytes(vectors.frames[0].wire_hex);
  const parser = new FrameParser();
  const boot = encodeUtf8('ESP-ROM:esp32c3\r\n');
  const noisy = parser.push(concat([boot, Uint8Array.of(0, 0), good]));
  assert.equal(noisy.frames.length, 1);
  assert.equal(noisy.frames[0].json.ok, undefined);
  const decoded = hexToBytes(vectors.frames[0].decoded_hex);
  decoded[0] ^= 0x01;
  const broken = encodeBroken(decoded);
  const bad = new FrameParser().push(concat([broken, good]));
  assert.equal(bad.frames.length, 1);
  assert.ok(bad.errors.some((item) => item.error === 'bad_crc' || item.error === 'bad_magic' || item.error === 'bad_cobs'));
  const huge = new FrameParser();
  const flood = huge.push(new Uint8Array(MAX_COBS + 5).fill(0x11));
  assert.equal(flood.frames.length, 0);
  assert.equal(flood.stats.oversize, 1);
  const after = huge.push(concat([Uint8Array.of(0), good]));
  assert.equal(after.frames.length, 1);
  assert.equal(encodeFrame({ kind: 1, sessionId: 1, requestId: 2, code: 2, wireSeq: 1, payload: new Uint8Array(MAX_PAYLOAD + 1) }).error, 'payload_too_large');
  const maxPayload = new Uint8Array(MAX_PAYLOAD);
  maxPayload.set(encodeUtf8('{"k":"'));
  maxPayload.set(encodeUtf8('"}'), MAX_PAYLOAD - 2);
  maxPayload.fill(0x61, 6, MAX_PAYLOAD - 2);
  const maxFrame = encodeFrame({ kind: 1, sessionId: 1, requestId: 2, code: 2, wireSeq: 1, payload: maxPayload });
  assert.equal(maxFrame.ok, true);
  assert.equal(maxFrame.decoded.length, MAX_DECODED);
  assert.equal(maxFrame.wire.length <= MAX_WIRE, true);
  assert.equal(cobsEncode(maxFrame.decoded).length <= MAX_COBS, true);
});

test('strict JSON rejects duplicate keys, depth, unsafe numbers and bad UTF-8', () => {
  assert.equal(checkJson(encodeUtf8('{"ok":true}')).ok, true);
  assert.equal(checkJson(encodeUtf8('{"a":1,"a":2}')).error, 'duplicate_key');
  assert.equal(checkJson(Uint8Array.of(0xef, 0xbb, 0xbf, 0x7b, 0x7d)).error, 'bom');
  assert.equal(checkJson(encodeUtf8('[1]')).error, 'root');
  assert.equal(checkJson(encodeUtf8('{"n":NaN}')).ok, false);
  assert.equal(checkJson(encodeUtf8('{"n":9007199254740993}')).error, 'unsafe_integer');
  assert.equal(checkJson(encodeUtf8('{"n":1e999}')).ok, false);
  let deep = '{"v":1}';
  for (let i = 0; i < 8; i++) deep = `{"a":${deep}}`;
  assert.equal(checkJson(encodeUtf8(deep)).error, 'depth');
  assert.equal(utf8ByteLength('参数无效'), 12);
  const bad = new FrameParser().push(encodeFrame({
    kind: 1,
    sessionId: 1,
    requestId: 2,
    code: 2,
    wireSeq: 1,
    payload: Uint8Array.of(0x7b, 0x22, 0x61, 0x22, 0x3a, 0x22, 0xff, 0x22, 0x7d),
    checkJson: false,
  }).wire);
  assert.equal(bad.frames.length, 0);
  assert.equal(bad.errors[0].error, 'bad_utf8');
});

function concat(parts) {
  const len = parts.reduce((sum, part) => sum + part.length, 0);
  const out = new Uint8Array(len);
  let offset = 0;
  for (const part of parts) {
    out.set(part, offset);
    offset += part.length;
  }
  return out;
}

function encodeBroken(decoded) {
  const encoded = cobsEncode(decoded);
  const wire = new Uint8Array(encoded.length + 2);
  wire[0] = 0;
  wire.set(encoded, 1);
  wire[wire.length - 1] = 0;
  return wire;
}
