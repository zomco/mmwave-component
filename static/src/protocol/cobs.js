export function cobsEncode(data) {
  const src = data instanceof Uint8Array ? data : Uint8Array.from(data);
  const out = new Uint8Array(src.length + Math.floor(src.length / 254) + 1);
  let outLen = 1;
  let codeIndex = 0;
  let code = 1;
  for (let i = 0; i < src.length; i++) {
    const byte = src[i];
    if (byte === 0) {
      out[codeIndex] = code;
      codeIndex = outLen;
      out[outLen++] = 0;
      code = 1;
    } else {
      out[outLen++] = byte;
      code++;
      if (code === 0xff) {
        out[codeIndex] = code;
        codeIndex = outLen;
        out[outLen++] = 0;
        code = 1;
      }
    }
  }
  out[codeIndex] = code;
  return out.subarray(0, outLen);
}

export function cobsDecode(data) {
  const src = data instanceof Uint8Array ? data : Uint8Array.from(data);
  if (src.length === 0) return { ok: false, error: 'bad_cobs' };
  const out = new Uint8Array(src.length);
  let outLen = 0;
  let i = 0;
  while (i < src.length) {
    const code = src[i];
    if (code === 0) return { ok: false, error: 'bad_cobs' };
    i++;
    const end = i + code - 1;
    if (end > src.length) return { ok: false, error: 'bad_cobs' };
    for (; i < end; i++) {
      if (src[i] === 0) return { ok: false, error: 'bad_cobs' };
      out[outLen++] = src[i];
    }
    if (code !== 0xff) out[outLen++] = 0;
  }
  if (outLen === 0 || out[outLen - 1] !== 0) return { ok: false, error: 'bad_cobs' };
  return { ok: true, data: out.subarray(0, outLen - 1) };
}
