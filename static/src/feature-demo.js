// Illustrative geometry only, not the firmware's coordinate or occupancy logic.
export const DEMO_DURATION_MS = 12000;
export const STILL_PROGRESS = 0.62;

const smooth = (value) => {
  const t = Math.max(0, Math.min(1, value));
  return t * t * (3 - 2 * t);
};
const windowEase = (p, start, end) => smooth((p - start) / (end - start));

export function demoFrame(progress) {
  const p = Number.isFinite(progress) ? Math.max(0, Math.min(1, progress)) : STILL_PROGRESS;
  const aligned = windowEase(p, 0.12, 0.48) * (1 - windowEase(p, 0.85, 1));
  const travel = windowEase(p, 0.18, 0.48) * (1 - windowEase(p, 0.72, 0.96));
  const boundaryY = 74 + 90 * travel;
  const zoneX = 97 + 136 * travel;
  return {
    alignment: { angle: -24 * (1 - aligned), offset: 18 * (1 - aligned),
      state: aligned < 0.02 ? 'before' : aligned > 0.98 ? 'after' : 'during' },
    boundary: { x: 268, y: boundaryY, inside: boundaryY >= 114 },
    zones: { x: zoneX, y: 149, sofa: zoneX <= 152, desk: zoneX >= 180 },
  };
}
