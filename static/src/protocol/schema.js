const KEYWORDS = new Set([
  '$ref', '$defs', '$schema', '$id', '$comment', 'title', 'description', 'type', 'const', 'enum', 'properties',
  'required', 'additionalProperties', 'items', 'minItems', 'maxItems', 'minLength', 'maxLength', 'pattern',
  'minimum', 'maximum', 'exclusiveMinimum', 'exclusiveMaximum', 'minProperties', 'maxProperties', 'oneOf',
  'anyOf', 'allOf', 'if', 'then', 'else', 'x-maxUtf8Bytes', 'x-status', 'x-commands', 'x-open-object',
]);

const MAPS = new Set(['$defs', 'properties', 'x-commands', 'x-configSchemas']);

export function unsupportedKeywords(schema) {
  const found = [];
  visit(schema, '#', '', found);
  return found;
}

export function validate(schema, value, root = schema) {
  const errors = [];
  check(schema, value, root, '', errors);
  return { ok: errors.length === 0, errors };
}

function visit(node, path, parentKey, found) {
  if (!node || typeof node !== 'object') return;
  if (!Array.isArray(node) && !MAPS.has(parentKey)) {
    for (const key of Object.keys(node)) {
      if (!KEYWORDS.has(key) && !key.startsWith('x-')) found.push(`${path}/${key}`);
    }
  }
  if (Array.isArray(node)) {
    node.forEach((item, index) => visit(item, `${path}/${index}`, '', found));
    return;
  }
  for (const [key, child] of Object.entries(node)) {
    if (key === '$ref' || key === 'x-commands') continue;
    visit(child, `${path}/${key}`, key, found);
  }
}

function check(schema, value, root, path, errors) {
  if (!schema || typeof schema !== 'object') return;
  if (schema.$ref) {
    check(resolve(root, schema.$ref), value, root, path, errors);
    return;
  }
  if (schema.oneOf) {
    const matches = schema.oneOf.filter((item) => validate(item, value, root).ok);
    if (matches.length !== 1) errors.push({ path, code: 'oneOf' });
    return;
  }
  if (schema.allOf) for (const item of schema.allOf) check(item, value, root, path, errors);
  if (schema.if) {
    const matched = validate(schema.if, value, root).ok;
    if (matched && schema.then) check(schema.then, value, root, path, errors);
    if (!matched && schema.else) check(schema.else, value, root, path, errors);
  }
  if (schema.anyOf && !schema.anyOf.some((item) => validate(item, value, root).ok)) errors.push({ path, code: 'anyOf' });
  if (schema.type && !typeOk(schema.type, value)) errors.push({ path, code: 'type', expected: schema.type });
  if (Object.prototype.hasOwnProperty.call(schema, 'const') && !same(schema.const, value)) errors.push({ path, code: 'const' });
  if (schema.enum && !schema.enum.some((item) => same(item, value))) errors.push({ path, code: 'enum' });
  if (typeof value === 'number') {
    if (schema.minimum !== undefined && value < schema.minimum) errors.push({ path, code: 'minimum' });
    if (schema.maximum !== undefined && value > schema.maximum) errors.push({ path, code: 'maximum' });
    if (schema.exclusiveMinimum !== undefined && value <= schema.exclusiveMinimum) errors.push({ path, code: 'exclusiveMinimum' });
    if (schema.exclusiveMaximum !== undefined && value >= schema.exclusiveMaximum) errors.push({ path, code: 'exclusiveMaximum' });
  }
  if (typeof value === 'string') {
    if (schema.minLength !== undefined && [...value].length < schema.minLength) errors.push({ path, code: 'minLength' });
    if (schema.maxLength !== undefined && [...value].length > schema.maxLength) errors.push({ path, code: 'maxLength' });
    if (schema.pattern && !new RegExp(schema.pattern).test(value)) errors.push({ path, code: 'pattern' });
    if (schema['x-maxUtf8Bytes'] !== undefined && utf8Size(value) > schema['x-maxUtf8Bytes']) errors.push({ path, code: 'utf8' });
  }
  if (Array.isArray(value)) {
    if (schema.minItems !== undefined && value.length < schema.minItems) errors.push({ path, code: 'minItems' });
    if (schema.maxItems !== undefined && value.length > schema.maxItems) errors.push({ path, code: 'maxItems' });
    if (schema.items) value.forEach((item, index) => check(schema.items, item, root, `${path}/${index}`, errors));
  }
  if (isObject(value)) {
    const keys = Object.keys(value);
    if (schema.minProperties !== undefined && keys.length < schema.minProperties) errors.push({ path, code: 'minProperties' });
    if (schema.maxProperties !== undefined && keys.length > schema.maxProperties) errors.push({ path, code: 'maxProperties' });
    if (schema.required) {
      for (const key of schema.required) if (!hasOwn(value, key)) errors.push({ path: `${path}/${key}`, code: 'required' });
    }
    if (schema.properties || schema.additionalProperties !== undefined || schema['x-open-object'] === true) {
      for (const key of keys) {
        if (schema.properties && hasOwn(schema.properties, key)) check(schema.properties[key], value[key], root, `${path}/${key}`, errors);
        else if (schema['x-open-object'] === true) continue;
        else if (schema.additionalProperties === false) errors.push({ path: `${path}/${key}`, code: 'additionalProperties' });
        else if (isObject(schema.additionalProperties)) check(schema.additionalProperties, value[key], root, `${path}/${key}`, errors);
      }
    }
  }
}

function resolve(root, ref) {
  if (!ref.startsWith('#/')) throw new Error(`unsupported ref ${ref}`);
  let node = root;
  for (const part of ref.slice(2).split('/')) node = node[part];
  if (!node) throw new Error(`missing ref ${ref}`);
  return node;
}

function typeOk(type, value) {
  const types = Array.isArray(type) ? type : [type];
  return types.some((item) => {
    if (item === 'object') return isObject(value);
    if (item === 'array') return Array.isArray(value);
    if (item === 'null') return value === null;
    if (item === 'integer') return typeof value === 'number' && Number.isInteger(value);
    if (item === 'number') return typeof value === 'number' && Number.isFinite(value);
    return typeof value === item;
  });
}

function hasOwn(obj, key) {
  return Object.prototype.hasOwnProperty.call(obj, key);
}

function isObject(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function same(a, b) {
  return JSON.stringify(a) === JSON.stringify(b);
}

function utf8Size(text) {
  return new TextEncoder().encode(text).length;
}
