// Legacy radial limits must not suppress a polygon-contained target.
#include <cassert>
#include "components/ld2450/ld2450_transform.h"
#include "components/ld2451/ld2451_transform.h"
#include "components/ld2452/ld2452_transform.h"
#include "components/ld2453/ld2453_transform.h"
#include "components/ld2454/ld2454_transform.h"
#include "components/r60abd1/r60abd1_transform.h"

int main() {
  {
    using namespace esphome::ld2450;
    CalibrationParams c;
    c.distance_min = 900;
    c.distance_max = 1;
    c.polygon = {{-100, 100}, {100, 100}, {100, 300}, {-100, 300}};
    assert(apply(0, 200, build_rotation(0, 0, 0), c).in_boundary);
    c.polygon = {{500, 500}, {600, 500}, {600, 600}, {500, 600}};
    assert(!apply(0, 200, build_rotation(0, 0, 0), c).in_boundary);
    c.polygon.clear();
    assert(apply(0, 200, build_rotation(0, 0, 0), c).in_boundary);
  }
  {
    using namespace esphome::ld2451;
    CalibrationParams c;
    c.distance_min = 900;
    c.distance_max = 1;
    c.polygon = {{-100, 100}, {100, 100}, {100, 300}, {-100, 300}};
    assert(Transform3D::transform(0, 200, 0, c).in_boundary);
    c.polygon = {{500, 500}, {600, 500}, {600, 600}, {500, 600}};
    assert(!Transform3D::transform(0, 200, 0, c).in_boundary);
    c.polygon.clear();
    assert(Transform3D::transform(0, 200, 0, c).in_boundary);
  }
  {
    using namespace esphome::ld2452;
    CalibrationParams c;
    c.distance_min = 900;
    c.distance_max = 1;
    c.polygon = {{-100, 100}, {100, 100}, {100, 300}, {-100, 300}};
    assert(apply(0, 200, build_rotation(0, 0, 0), c).in_boundary);
    c.polygon = {{500, 500}, {600, 500}, {600, 600}, {500, 600}};
    assert(!apply(0, 200, build_rotation(0, 0, 0), c).in_boundary);
    c.polygon.clear();
    assert(apply(0, 200, build_rotation(0, 0, 0), c).in_boundary);
  }
  {
    using namespace esphome::ld2453;
    CalibrationParams c;
    c.distance_min = 900;
    c.distance_max = 1;
    c.polygon = {{-100, 100}, {100, 100}, {100, 300}, {-100, 300}};
    assert(Transform3D::transform(0, 200, 0, c).in_boundary);
    c.polygon = {{500, 500}, {600, 500}, {600, 600}, {500, 600}};
    assert(!Transform3D::transform(0, 200, 0, c).in_boundary);
    c.polygon.clear();
    assert(Transform3D::transform(0, 200, 0, c).in_boundary);
  }
  {
    using namespace esphome::ld2454;
    CalibrationParams c;
    c.distance_min = 900;
    c.distance_max = 1;
    c.polygon = {{-100, 100}, {100, 100}, {100, 300}, {-100, 300}};
    assert(apply(0, 200, build_rotation(0, 0, 0), c).in_boundary);
    c.polygon = {{500, 500}, {600, 500}, {600, 600}, {500, 600}};
    assert(!apply(0, 200, build_rotation(0, 0, 0), c).in_boundary);
    c.polygon.clear();
    assert(apply(0, 200, build_rotation(0, 0, 0), c).in_boundary);
  }
  {
    using namespace esphome::r60abd1;
    CalibrationParams c;
    c.distance_min = 900;
    c.distance_max = 1;
    c.polygon = {{-100, 100}, {100, 100}, {100, 300}, {-100, 300}};
    assert(apply(0, 200, 0, c).in_boundary);
    c.polygon = {{500, 500}, {600, 500}, {600, 600}, {500, 600}};
    assert(!apply(0, 200, 0, c).in_boundary);
    c.polygon.clear();
    assert(apply(0, 200, 0, c).in_boundary);
  }
}
