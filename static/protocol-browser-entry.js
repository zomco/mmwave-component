import { encodeFrame, FrameParser } from './src/protocol/codec.js';
import { ProtocolClient } from './src/protocol/client.js';
import { CODE, KIND } from './src/protocol/limits.js';
import { encodeUtf8 } from './src/protocol/utf8.js';

const nonce = '0123456789abcdef0123456789abcdef';

export async function runProtocolBrowserCheck() {
  const parser = new FrameParser();
  let client = null;
  client = new ProtocolClient({
    write(bytes) {
      const parsed = parser.push(bytes, 0);
      for (const frame of parsed.frames) {
        const wire = answer(frame);
        if (wire) client.ingest(wire);
      }
    },
    onData() {},
  });
  const hello = await client.hello({
    client: { name: 'mmwave-web-console', version: '0.1.0' },
    nonce,
  });
  const ping = await client.ping();
  return {
    ok: Boolean(hello.json?.ok && ping.json?.ok),
    uptime: ping.json?.result?.uptime_ms ?? null,
    simulation: hello.json?.result?.identity?.firmware_version === 'simulation',
  };
}

function answer(frame) {
  if (frame.kind !== KIND.request) return null;
  if (frame.code === CODE.HELLO) {
    return respond(frame, 1, {
      ok: true,
      result: {
        nonce: frame.json.nonce,
        protocol: { major: 1, minor: 0 },
        boot_id: nonce,
        session_ttl_ms: 15000,
        limits: { max_payload: 4096, rpc_inflight: 1, max_targets: 1, event_budget_bps: 8000 },
        identity: {
          device_id: 'browser-loopback',
          configured_model: 'r60abd1',
          dimension: '2D',
          firmware_version: 'simulation',
        },
        cap_revision: 'browser',
      },
    });
  }
  if (frame.code === CODE.PING) return respond(frame, frame.sessionId, { ok: true, result: { uptime_ms: 1 } });
  return null;
}

function respond(frame, sessionId, payload) {
  const encoded = encodeFrame({
    kind: KIND.response,
    sessionId,
    requestId: frame.requestId,
    code: frame.code,
    wireSeq: frame.requestId,
    payload: encodeUtf8(JSON.stringify(payload)),
  });
  return encoded.ok ? encoded.wire : null;
}
