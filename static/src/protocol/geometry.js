export function polygonIssues(points, options = {}) {
  if (points == null) return [];
  if (!Array.isArray(points)) return ['type'];
  const minVertices = options.minVertices ?? 3;
  const maxVertices = options.maxVertices ?? 64;
  const minCoord = options.minCoord ?? -2000;
  const maxCoord = options.maxCoord ?? 2000;
  if (points.length < minVertices || points.length > maxVertices) return ['count'];
  const issues = [];
  for (let i = 0; i < points.length; i++) {
    const point = points[i];
    if (!Array.isArray(point) || point.length !== 2 || !Number.isFinite(point[0]) || !Number.isFinite(point[1])) {
      issues.push('point');
      return issues;
    }
    if (point[0] < minCoord || point[0] > maxCoord || point[1] < minCoord || point[1] > maxCoord) {
      issues.push('range');
    }
    for (let j = 0; j < i; j++) {
      if (point[0] === points[j][0] && point[1] === points[j][1]) issues.push('duplicate');
    }
  }
  if (points.length >= 2) {
    const a = points[0];
    const b = points[points.length - 1];
    if (a[0] === b[0] && a[1] === b[1]) issues.push('closed');
  }
  if (Math.abs(signedArea(points)) === 0) issues.push('zero_area');
  if (selfIntersects(points)) issues.push('self_intersection');
  return issues;
}

function signedArea(points) {
  let sum = 0;
  for (let i = 0; i < points.length; i++) {
    const next = points[(i + 1) % points.length];
    sum += points[i][0] * next[1] - next[0] * points[i][1];
  }
  return sum / 2;
}

function selfIntersects(points) {
  const n = points.length;
  for (let i = 0; i < n; i++) {
    for (let j = i + 1; j < n; j++) {
      if (Math.abs(i - j) <= 1 || (i === 0 && j === n - 1)) continue;
      if (segmentsIntersect(points[i], points[(i + 1) % n], points[j], points[(j + 1) % n])) return true;
    }
  }
  return false;
}

function segmentsIntersect(a, b, c, d) {
  const o1 = orient(a, b, c);
  const o2 = orient(a, b, d);
  const o3 = orient(c, d, a);
  const o4 = orient(c, d, b);
  return o1 * o2 < 0 && o3 * o4 < 0;
}

function orient(a, b, c) {
  return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
}
