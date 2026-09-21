#include <cassert>
#include <cmath>

#include "components/ld2450/area_occupancy.h"

using mmwave_area::Occupancy;
using mmwave_area::Sample;

static void rect(Occupancy &occ, uint8_t i, float x0, float y0, float x1, float y1) {
  occ.add_point(i, x0, y0);
  occ.add_point(i, x1, y0);
  occ.add_point(i, x1, y1);
  occ.add_point(i, x0, y1);
}

static void instant(Occupancy &occ) {
  occ.set_confirm_ms(0);
  occ.set_clear_ms(0);
}

int main() {
  Occupancy occ;
  instant(occ);
  rect(occ, 0, 0, 0, 200, 200);
  rect(occ, 1, 150, 0, 350, 200);

  Sample a{true, true, 40.f, 100.f, 40.f};
  occ.update(&a, 1);
  assert(occ.occupied(0) && !occ.occupied(1));

  Sample b{true, true, 180.f, 100.f, 40.f};
  occ.update(&b, 1);
  assert(occ.occupied(0) && !occ.occupied(1));

  Sample c{true, true, 300.f, 100.f, 40.f};
  occ.update(&c, 1);
  assert(!occ.occupied(0) && occ.occupied(1));

  Occupancy still;
  instant(still);
  rect(still, 0, 0, 0, 200, 200);
  Sample inside{true, true, 100.f, 100.f, 40.f};
  still.update(&inside, 1);
  Sample locked{true, true, 400.f, 400.f, 5.f};
  still.update(&locked, 1);
  assert(still.occupied(0));
  Sample moving{true, true, 400.f, 400.f, 40.f};
  still.update(&moving, 1);
  assert(!still.occupied(0));

  Sample gone{false, true, 100.f, 100.f, 40.f};
  still.update(&inside, 1);
  still.update(&gone, 1);
  assert(!still.occupied(0));

  Occupancy gated;
  rect(gated, 0, 0, 0, 200, 200);
  gated.update(&inside, 1, 1000);
  assert(!gated.occupied(0));
  gated.update(&inside, 1, 1399);
  assert(!gated.occupied(0));
  gated.update(&inside, 1, 1400);
  assert(gated.occupied(0));
  gated.update(&gone, 1, 1500);
  assert(gated.occupied(0));
  gated.update(&gone, 1, 3499);
  assert(gated.occupied(0));
  gated.update(&gone, 1, 3500);
  assert(!gated.occupied(0));

  Occupancy passing;
  instant(passing);
  rect(passing, 0, 0, 0, 200, 200);
  Sample fast{true, true, 100.f, 100.f, 120.f};
  passing.update(&fast, 1);
  assert(!passing.occupied(0));
  Sample slow{true, true, 100.f, 100.f, 40.f};
  passing.update(&slow, 1);
  assert(passing.occupied(0));

  Occupancy bands;
  instant(bands);
  bands.update_bands(true, true, 80.f, 0.f, 0);
  assert(bands.occupied(0) && !bands.occupied(1));
  bands.update_bands(true, true, 200.f, 0.f, 0);
  assert(!bands.occupied(0) && bands.occupied(1));
  return 0;
}
