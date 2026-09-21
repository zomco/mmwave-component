"""Occupancy engine: exclusive assignment, leave hysteresis, still-speed lock."""

from __future__ import annotations

import math
import shutil
import subprocess
import tempfile
import unittest
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Area:
    vertices: list[tuple[float, float]] = field(default_factory=list)

    def ready(self) -> bool:
        return len(self.vertices) >= 3

    def centroid(self) -> tuple[float, float]:
        n = len(self.vertices)
        return (sum(p[0] for p in self.vertices) / n, sum(p[1] for p in self.vertices) / n)


@dataclass
class Sample:
    active: bool
    in_boundary: bool
    x: float
    y: float
    speed: float


def point_in(px: float, py: float, area: Area) -> bool:
    inside = False
    pts = area.vertices
    j = len(pts) - 1
    for i, (xi, yi) in enumerate(pts):
        xj, yj = pts[j]
        dy = yj - yi
        if (yi > py) != (yj > py) and dy != 0 and px < (xj - xi) * (py - yi) / dy + xi:
            inside = not inside
        j = i
    return inside


def dist_seg(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    vx, vy = bx - ax, by - ay
    wx, wy = px - ax, py - ay
    c1 = vx * wx + vy * wy
    if c1 <= 0:
        return math.hypot(px - ax, py - ay)
    c2 = vx * vx + vy * vy
    if c2 <= c1:
        return math.hypot(px - bx, py - by)
    t = c1 / c2
    return math.hypot(px - (ax + t * vx), py - (ay + t * vy))


def dist_outside(px: float, py: float, area: Area) -> float:
    if point_in(px, py, area):
        return 0.0
    best = 1e9
    n = len(area.vertices)
    for i, (ax, ay) in enumerate(area.vertices):
        bx, by = area.vertices[(i + 1) % n]
        best = min(best, dist_seg(px, py, ax, ay, bx, by))
    return best


class Occupancy:
    def __init__(self) -> None:
        self.areas = [Area(), Area(), Area()]
        self.occupied = [False, False, False]
        self.assign = [-1, -1, -1, -1]
        self.hyst = 50.0
        self.still = 15.0
        self.confirm_ms = 400
        self.clear_ms = 2000
        self.pass_speed = 80.0
        self.split = 150.0
        self.wait_on = [False, False, False]
        self.wait_off = [False, False, False]
        self.on_since = [0, 0, 0]
        self.off_since = [0, 0, 0]

    def add(self, i: int, x: float, y: float) -> None:
        self.areas[i].vertices.append((x, y))

    def update(self, samples: list[Sample], now_ms: int = 0) -> None:
        nxt = [False, False, False]
        spd = [1e9, 1e9, 1e9]
        for t, sample in enumerate(samples[:4]):
            if not sample.active or not sample.in_boundary:
                self.assign[t] = -1
                continue
            cur = self.assign[t]
            still = self.still > 0 and abs(sample.speed) < self.still
            if 0 <= cur < 3 and self.areas[cur].ready():
                if still or dist_outside(sample.x, sample.y, self.areas[cur]) <= self.hyst:
                    nxt[cur] = True
                    spd[cur] = min(spd[cur], abs(sample.speed))
                    continue
            best, best_d = -1, 1e9
            for a, area in enumerate(self.areas):
                if not area.ready() or not point_in(sample.x, sample.y, area):
                    continue
                cx, cy = area.centroid()
                d = math.hypot(sample.x - cx, sample.y - cy)
                if d < best_d:
                    best, best_d = a, d
            self.assign[t] = best
            if best >= 0:
                nxt[best] = True
                spd[best] = min(spd[best], abs(sample.speed))
        for t in range(len(samples), 4):
            self.assign[t] = -1
        self._apply(nxt, spd, now_ms)

    def update_bands(self, active: bool, in_boundary: bool, range_cm: float, speed: float, now_ms: int = 0) -> None:
        nxt = [False, False, False]
        spd = [1e9, 1e9, 1e9]
        if active and in_boundary:
            a = 1 if self.split > 0 and range_cm > self.split else 0
            nxt[a] = True
            spd[a] = abs(speed)
        self._apply(nxt, spd, now_ms)

    def _apply(self, nxt: list[bool], spd: list[float], now_ms: int) -> None:
        for a in range(3):
            want = nxt[a]
            if want and not self.occupied[a] and self.pass_speed > 0 and spd[a] >= self.pass_speed:
                want = False
            if want:
                self.wait_off[a] = False
                if self.occupied[a] or self.confirm_ms == 0:
                    self.occupied[a] = True
                    self.wait_on[a] = False
                    continue
                if not self.wait_on[a]:
                    self.wait_on[a] = True
                    self.on_since[a] = now_ms
                if now_ms - self.on_since[a] >= self.confirm_ms:
                    self.occupied[a] = True
                    self.wait_on[a] = False
            else:
                self.wait_on[a] = False
                if not self.occupied[a] or self.clear_ms == 0:
                    self.occupied[a] = False
                    self.wait_off[a] = False
                    continue
                if not self.wait_off[a]:
                    self.wait_off[a] = True
                    self.off_since[a] = now_ms
                if now_ms - self.off_since[a] >= self.clear_ms:
                    self.occupied[a] = False
                    self.wait_off[a] = False


def instant(occ: Occupancy) -> Occupancy:
    occ.confirm_ms = 0
    occ.clear_ms = 0
    return occ


def rect(occ: Occupancy, i: int, x0: float, y0: float, x1: float, y1: float) -> None:
    occ.add(i, x0, y0)
    occ.add(i, x1, y0)
    occ.add(i, x1, y1)
    occ.add(i, x0, y1)


class OccupancyTest(unittest.TestCase):
    def test_inside_occupies_nearest_centroid(self):
        occ = instant(Occupancy())
        rect(occ, 0, 0, 0, 200, 200)
        rect(occ, 1, 150, 0, 350, 200)
        occ.update([Sample(True, True, 40, 100, 40)])
        self.assertEqual(occ.occupied, [True, False, False])
        occ.update([Sample(True, True, 300, 100, 40)])
        self.assertEqual(occ.occupied, [False, True, False])

    def test_overlap_stays_with_last_area_inside_hysteresis(self):
        occ = instant(Occupancy())
        rect(occ, 0, 0, 0, 200, 200)
        rect(occ, 1, 150, 0, 350, 200)
        occ.update([Sample(True, True, 40, 100, 40)])
        occ.update([Sample(True, True, 180, 100, 40)])
        self.assertEqual(occ.occupied, [True, False, False])

    def test_still_lock_keeps_assignment_outside_polygon(self):
        occ = instant(Occupancy())
        rect(occ, 0, 0, 0, 200, 200)
        occ.update([Sample(True, True, 100, 100, 40)])
        occ.update([Sample(True, True, 400, 400, 5)])
        self.assertEqual(occ.occupied, [True, False, False])
        occ.update([Sample(True, True, 400, 400, 40)])
        self.assertEqual(occ.occupied, [False, False, False])

    def test_inactive_or_out_of_room_clears(self):
        occ = instant(Occupancy())
        rect(occ, 0, 0, 0, 200, 200)
        occ.update([Sample(True, True, 100, 100, 40)])
        occ.update([Sample(False, True, 100, 100, 40)])
        self.assertEqual(occ.occupied, [False, False, False])
        occ.update([Sample(True, True, 100, 100, 40)])
        occ.update([Sample(True, False, 100, 100, 40)])
        self.assertEqual(occ.occupied, [False, False, False])

    def test_confirm_and_clear_use_elapsed_time(self):
        occ = Occupancy()
        rect(occ, 0, 0, 0, 200, 200)
        inside = Sample(True, True, 100, 100, 40)
        occ.update([inside], 1000)
        self.assertEqual(occ.occupied, [False, False, False])
        occ.update([inside], 1399)
        self.assertEqual(occ.occupied, [False, False, False])
        occ.update([inside], 1400)
        self.assertEqual(occ.occupied, [True, False, False])
        gone = Sample(False, True, 100, 100, 40)
        occ.update([gone], 1500)
        self.assertEqual(occ.occupied, [True, False, False])
        occ.update([gone], 3499)
        self.assertEqual(occ.occupied, [True, False, False])
        occ.update([gone], 3500)
        self.assertEqual(occ.occupied, [False, False, False])

    def test_pass_speed_skips_confirm(self):
        occ = instant(Occupancy())
        rect(occ, 0, 0, 0, 200, 200)
        occ.update([Sample(True, True, 100, 100, 120)])
        self.assertEqual(occ.occupied, [False, False, False])
        occ.update([Sample(True, True, 100, 100, 40)])
        self.assertEqual(occ.occupied, [True, False, False])

    def test_bands_near_and_far(self):
        occ = instant(Occupancy())
        occ.update_bands(True, True, 80, 0)
        self.assertEqual(occ.occupied, [True, False, False])
        occ.update_bands(True, True, 200, 0)
        self.assertEqual(occ.occupied, [False, True, False])

    @unittest.skipUnless(shutil.which("g++"), "g++ required for native regression")
    def test_cpp_engine(self):
        with tempfile.TemporaryDirectory() as directory:
            exe = str(Path(directory) / "area-occupancy-test")
            subprocess.run(
                ["g++", "-std=c++17", "-I", str(ROOT), str(ROOT / "tests/area_occupancy_test.cpp"), "-o", exe],
                check=True,
            )
            subprocess.run([exe], check=True)


if __name__ == "__main__":
    unittest.main()
