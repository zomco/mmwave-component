const D = Math.PI / 180;

export function rotationMatrix(yawDeg, pitchDeg, rollDeg) {
  const y = yawDeg * D;
  const p = pitchDeg * D;
  const r = rollDeg * D;
  const sy = Math.sin(y);
  const cy = Math.cos(y);
  const sp = Math.sin(p);
  const cp = Math.cos(p);
  const sr = Math.sin(r);
  const cr = Math.cos(r);
  return [
    [cy * cr + sy * sp * sr, sy * cp, -cy * sr + sy * sp * cr],
    [-sy * cr + cy * sp * sr, cy * cp, sy * sr + cy * sp * cr],
    [cp * sr, -sp, cp * cr],
  ];
}

export function project1D(rangeCm, cal) {
  return applyTransform(0, rangeCm, 0, cal);
}

export function applyTransform(lx, ly, lz, cal) {
  const R = rotationMatrix(cal.yaw, cal.pitch, cal.roll);
  const wx = R[0][0] * lx + R[0][1] * ly + R[0][2] * lz;
  const wy = R[1][0] * lx + R[1][1] * ly + R[1][2] * lz;
  const wz = R[2][0] * lx + R[2][1] * ly + R[2][2] * lz;
  const roomX = cal.radar_x + wx;
  const roomY = cal.radar_y + wy;
  const roomZ = cal.radar_z - wz;
  return {
    roomX,
    roomY,
    roomZ,
    inBoundary: pointInPolygon(roomX, roomY, cal.polygon || []),
  };
}

export function pointInPolygon(px, py, polygon) {
  const n = polygon.length;
  if (n < 3) return true;
  let inside = false;
  for (let i = 0, j = n - 1; i < n; j = i++) {
    const xi = polygon[i].x;
    const yi = polygon[i].y;
    const xj = polygon[j].x;
    const yj = polygon[j].y;
    const cross = yi > py !== yj > py && px < ((xj - xi) * (py - yi)) / (yj - yi) + xi;
    if (cross) inside = !inside;
  }
  return inside;
}
