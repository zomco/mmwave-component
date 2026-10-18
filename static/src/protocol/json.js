import { JSON_MAX_DEPTH, JSON_MAX_ITEMS, JSON_MAX_KEYS } from './limits.js';

const WS = new Set([0x20, 0x09, 0x0a, 0x0d]);

export function checkJson(bytes, limits = {}) {
  const src = bytes instanceof Uint8Array ? bytes : Uint8Array.from(bytes);
  if (src.length >= 3 && src[0] === 0xef && src[1] === 0xbb && src[2] === 0xbf) {
    return fail('bom');
  }
  const parser = new Parser(src, {
    maxDepth: limits.maxDepth ?? JSON_MAX_DEPTH,
    maxKeys: limits.maxKeys ?? JSON_MAX_KEYS,
    maxItems: limits.maxItems ?? JSON_MAX_ITEMS,
    maxStringBytes: limits.maxStringBytes ?? 4096,
  });
  const value = parser.parseValue(1);
  if (!value.ok) return value;
  parser.skipWs();
  if (parser.i !== src.length) return fail('trailing');
  if (value.value === null || typeof value.value !== 'object' || Array.isArray(value.value)) {
    return fail('root');
  }
  return { ok: true, value: value.value };
}

function fail(error, index) {
  return { ok: false, error, index };
}

export function classifyNumber(literal) {
  let i = 0;
  if (literal[i] === '-') i++;
  const intBegin = i;
  while (i < literal.length && literal[i] >= '0' && literal[i] <= '9') i++;
  const intEnd = i;
  let frac = '';
  if (literal[i] === '.') {
    i++;
    const fracBegin = i;
    while (i < literal.length && literal[i] >= '0' && literal[i] <= '9') i++;
    frac = literal.slice(fracBegin, i);
  }
  let exp = 0;
  let expSign = 1;
  if (literal[i] === 'e' || literal[i] === 'E') {
    i++;
    if (literal[i] === '+') i++;
    else if (literal[i] === '-') {
      expSign = -1;
      i++;
    }
    while (i < literal.length && literal[i] >= '0' && literal[i] <= '9') {
      exp = exp * 10 + (literal.charCodeAt(i) - 48);
      i++;
    }
    exp *= expSign;
  }
  const digits = literal.slice(intBegin, intEnd) + frac;
  const right = frac.length - exp;
  if (right <= 0) {
    const integer = integerDigits(digits, -right);
    if (!integer.ok) return integer;
    return { ok: true, value: Number(literal) };
  }
  if (right < digits.length && digits.slice(digits.length - right).split('').every((ch) => ch === '0')) {
    const integer = integerDigits(digits.slice(0, digits.length - right), 0);
    if (!integer.ok) return integer;
    return { ok: true, value: Number(literal) };
  }
  if (right >= digits.length && digits.split('').every((ch) => ch === '0')) return { ok: true, value: 0 };
  const value = Number(literal);
  if (!Number.isFinite(value)) return { ok: false, error: 'number' };
  return { ok: true, value };
}

function integerDigits(digits, extraZeros) {
  const trimmed = digits.replace(/^0+(?=\d)/, '');
  if (trimmed === '0') return { ok: true };
  const width = trimmed.length + extraZeros;
  if (width > 16) return { ok: false, error: 'unsafe_integer' };
  if (width < 16) return { ok: true };
  const full = `${trimmed}${'0'.repeat(extraZeros)}`;
  if (full > '9007199254740991') return { ok: false, error: 'unsafe_integer' };
  return { ok: true };
}

class Parser {
  constructor(src, limits) {
    this.src = src;
    this.i = 0;
    this.limits = limits;
  }

  skipWs() {
    while (this.i < this.src.length && WS.has(this.src[this.i])) this.i++;
  }

  parseValue(depth) {
    this.skipWs();
    if (depth > this.limits.maxDepth) return fail('depth', this.i);
    if (this.i >= this.src.length) return fail('truncated', this.i);
    const b = this.src[this.i];
    if (b === 0x7b) return this.parseObject(depth);
    if (b === 0x5b) return this.parseArray(depth);
    if (b === 0x22) return this.parseString();
    if (b === 0x74) return this.parseLiteral('true', true);
    if (b === 0x66) return this.parseLiteral('false', false);
    if (b === 0x6e) return this.parseLiteral('null', null);
    if (b === 0x2d || (b >= 0x30 && b <= 0x39)) return this.parseNumber();
    return fail('syntax', this.i);
  }

  parseLiteral(text, value) {
    for (let n = 0; n < text.length; n++) {
      if (this.src[this.i + n] !== text.charCodeAt(n)) return fail('syntax', this.i);
    }
    this.i += text.length;
    return { ok: true, value };
  }

  parseNumber() {
    const start = this.i;
    if (this.src[this.i] === 0x2d) this.i++;
    if (this.i >= this.src.length || this.src[this.i] < 0x30 || this.src[this.i] > 0x39) return fail('number', start);
    if (this.src[this.i] === 0x30) this.i++;
    else while (this.i < this.src.length && this.src[this.i] >= 0x30 && this.src[this.i] <= 0x39) this.i++;
    let fraction = false;
    if (this.i < this.src.length && this.src[this.i] === 0x2e) {
      fraction = true;
      this.i++;
      const mark = this.i;
      while (this.i < this.src.length && this.src[this.i] >= 0x30 && this.src[this.i] <= 0x39) this.i++;
      if (this.i === mark) return fail('number', start);
    }
    if (this.i < this.src.length && (this.src[this.i] === 0x65 || this.src[this.i] === 0x45)) {
      fraction = true;
      this.i++;
      if (this.i >= this.src.length) return fail('truncated', start);
      if (this.src[this.i] === 0x2b || this.src[this.i] === 0x2d) {
        this.i++;
        if (this.i >= this.src.length) return fail('truncated', start);
      }
      const mark = this.i;
      while (this.i < this.src.length && this.src[this.i] >= 0x30 && this.src[this.i] <= 0x39) this.i++;
      if (this.i === mark) return fail(this.i >= this.src.length ? 'truncated' : 'number', start);
    }
    const literal = ascii(this.src, start, this.i);
    const classified = classifyNumber(literal);
    if (!classified.ok) return fail(classified.error, start);
    return { ok: true, value: classified.value };
  }

  parseString() {
    if (this.src[this.i] !== 0x22) return fail('string', this.i);
    this.i++;
    const start = this.i;
    let bytes = 0;
    let out = '';
    while (this.i < this.src.length) {
      const b = this.src[this.i];
      if (b === 0x22) {
        this.i++;
        if (bytes > this.limits.maxStringBytes) return fail('string_limit', start);
        return { ok: true, value: out };
      }
      if (b === 0x5c) {
        const esc = this.src[this.i + 1];
        if (esc === undefined) return fail('string', this.i);
        const simple = { 0x22: '"', 0x5c: '\\', 0x2f: '/', 0x62: '\b', 0x66: '\f', 0x6e: '\n', 0x72: '\r', 0x74: '\t' };
        if (simple[esc] !== undefined) {
          out += simple[esc];
          bytes += esc === 0x22 || esc === 0x5c || esc === 0x2f ? 1 : 1;
          this.i += 2;
          continue;
        }
        if (esc !== 0x75) return fail('string', this.i);
        const hex = ascii(this.src, this.i + 2, this.i + 6);
        if (!/^[0-9a-fA-F]{4}$/.test(hex)) return fail('string', this.i);
        const unit = Number.parseInt(hex, 16);
        this.i += 6;
        if (unit >= 0xd800 && unit <= 0xdbff) {
          if (this.src[this.i] !== 0x5c || this.src[this.i + 1] !== 0x75) return fail('surrogate', this.i);
          const hex2 = ascii(this.src, this.i + 2, this.i + 6);
          if (!/^[0-9a-fA-F]{4}$/.test(hex2)) return fail('surrogate', this.i);
          const low = Number.parseInt(hex2, 16);
          if (low < 0xdc00 || low > 0xdfff) return fail('surrogate', this.i);
          const cp = 0x10000 + ((unit - 0xd800) << 10) + (low - 0xdc00);
          out += String.fromCodePoint(cp);
          bytes += 4;
          this.i += 6;
          continue;
        }
        if (unit >= 0xdc00 && unit <= 0xdfff) return fail('surrogate', this.i);
        out += String.fromCharCode(unit);
        bytes += unit < 0x80 ? 1 : unit < 0x800 ? 2 : 3;
        continue;
      }
      if (b < 0x20) return fail('string', this.i);
      const seq = utf8Sequence(this.src, this.i);
      if (!seq) return fail('utf8', this.i);
      out += utf8Slice(this.src, this.i, seq);
      bytes += seq;
      this.i += seq;
    }
    return fail('string', start);
  }

  parseObject(depth) {
    this.i++;
    const obj = {};
    let count = 0;
    this.skipWs();
    if (this.src[this.i] === 0x7d) {
      this.i++;
      return { ok: true, value: obj };
    }
    while (this.i < this.src.length) {
      if (count >= this.limits.maxKeys) return fail('keys', this.i);
      this.skipWs();
      const key = this.parseString();
      if (!key.ok) return key;
      if (Object.prototype.hasOwnProperty.call(obj, key.value)) return fail('duplicate_key', this.i);
      this.skipWs();
      if (this.src[this.i] !== 0x3a) return fail('syntax', this.i);
      this.i++;
      const value = this.parseValue(depth + 1);
      if (!value.ok) return value;
      Object.defineProperty(obj, key.value, { value: value.value, enumerable: true, writable: true, configurable: true });
      count++;
      this.skipWs();
      if (this.src[this.i] === 0x7d) {
        this.i++;
        return { ok: true, value: obj };
      }
      if (this.src[this.i] !== 0x2c) return fail('syntax', this.i);
      this.i++;
    }
    return fail('truncated', this.i);
  }

  parseArray(depth) {
    this.i++;
    const arr = [];
    this.skipWs();
    if (this.src[this.i] === 0x5d) {
      this.i++;
      return { ok: true, value: arr };
    }
    while (this.i < this.src.length) {
      if (arr.length >= this.limits.maxItems) return fail('items', this.i);
      const value = this.parseValue(depth + 1);
      if (!value.ok) return value;
      arr.push(value.value);
      this.skipWs();
      if (this.src[this.i] === 0x5d) {
        this.i++;
        return { ok: true, value: arr };
      }
      if (this.src[this.i] !== 0x2c) return fail('syntax', this.i);
      this.i++;
    }
    return fail('truncated', this.i);
  }
}

function ascii(src, start, end) {
  let text = '';
  for (let i = start; i < end && i < src.length; i++) text += String.fromCharCode(src[i]);
  return text;
}

function utf8Slice(src, i, len) {
  return new TextDecoder('utf-8', { fatal: true }).decode(src.subarray(i, i + len));
}

function utf8Sequence(src, i) {
  const b = src[i];
  if (b <= 0x7f) return 1;
  if (b >= 0xc2 && b <= 0xdf && (src[i + 1] & 0xc0) === 0x80) return 2;
  if ((b & 0xf0) === 0xe0) {
    const c1 = src[i + 1];
    const c2 = src[i + 2];
    if ((c1 & 0xc0) !== 0x80 || (c2 & 0xc0) !== 0x80) return 0;
    if (b === 0xe0 && c1 < 0xa0) return 0;
    if (b === 0xed && c1 >= 0xa0) return 0;
    return 3;
  }
  if (b >= 0xf0 && b <= 0xf4) {
    const c1 = src[i + 1];
    if ((c1 & 0xc0) !== 0x80 || (src[i + 2] & 0xc0) !== 0x80 || (src[i + 3] & 0xc0) !== 0x80) return 0;
    if (b === 0xf0 && c1 < 0x90) return 0;
    if (b === 0xf4 && c1 >= 0x90) return 0;
    return 4;
  }
  return 0;
}
