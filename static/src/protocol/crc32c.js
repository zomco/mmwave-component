const POLY = 0x82f63b78;
const TABLE = new Uint32Array(256);
for (let n = 0; n < 256; n++) {
  let crc = n;
  for (let i = 0; i < 8; i++) crc = (crc >>> 1) ^ (POLY & -(crc & 1));
  TABLE[n] = crc >>> 0;
}

export function crc32c(data) {
  const src = data instanceof Uint8Array ? data : Uint8Array.from(data);
  let crc = 0xffffffff;
  for (let i = 0; i < src.length; i++) crc = TABLE[(crc ^ src[i]) & 0xff] ^ (crc >>> 8);
  return (crc ^ 0xffffffff) >>> 0;
}

export function crc32cHex(data) {
  return crc32c(data).toString(16).padStart(8, '0');
}
