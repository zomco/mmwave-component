const encoder = new TextEncoder();
const decoder = new TextDecoder('utf-8', { fatal: true });

export function encodeUtf8(text) {
  return encoder.encode(text);
}

export function decodeUtf8(bytes) {
  try {
    return { ok: true, text: decoder.decode(bytes) };
  } catch {
    return { ok: false, error: 'bad_utf8' };
  }
}

export function utf8ByteLength(text) {
  return encoder.encode(text).length;
}

export function isStrictUtf8(bytes) {
  const src = bytes instanceof Uint8Array ? bytes : Uint8Array.from(bytes);
  let i = 0;
  while (i < src.length) {
    const b = src[i];
    let need = 0;
    if (b <= 0x7f) {
      i++;
      continue;
    } else if ((b & 0xe0) === 0xc0) {
      if (b < 0xc2) return false;
      need = 1;
    } else if ((b & 0xf0) === 0xe0) need = 2;
    else if ((b & 0xf8) === 0xf0) {
      if (b > 0xf4) return false;
      need = 3;
    } else return false;
    if (i + need >= src.length) return false;
    const c1 = src[i + 1];
    if ((c1 & 0xc0) !== 0x80) return false;
    if (need >= 2 && (src[i + 2] & 0xc0) !== 0x80) return false;
    if (need === 3 && (src[i + 3] & 0xc0) !== 0x80) return false;
    if (b === 0xe0 && c1 < 0xa0) return false;
    if (b === 0xed && c1 >= 0xa0) return false;
    if (b === 0xf0 && c1 < 0x90) return false;
    if (b === 0xf4 && c1 >= 0x90) return false;
    i += 1 + need;
  }
  return true;
}
