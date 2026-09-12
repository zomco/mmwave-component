"""Regression checks for polygon-only positioning firmware.

Run with: python tests/test_polygon_only.py
"""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = ("ld2450", "ld2451", "ld2452", "ld2453", "ld2454", "r60abd1")

class PolygonOnlyTest(unittest.TestCase):
    def test_no_distance_controls_or_restored_values(self):
        for model in MODELS:
            with self.subTest(model=model):
                config = (ROOT / "tests/common" / (model + ".yaml")).read_text(encoding="utf-8")
                self.assertNotIn("g_distance_", config)
                self.assertNotIn("Zone Min Distance", config)
                self.assertNotIn("Zone Max Distance", config)
                self.assertIn("apply_polygon", config)

    def test_ranging_controls_preserved(self):
        for model in ("ld2410b", "ld2410c", "ld2412", "ld2420", "rd03e"):
            config = (ROOT / "tests/common" / (model + ".yaml")).read_text(encoding="utf-8")
            self.assertIn("Zone Min Distance", config)
            self.assertIn("Zone Max Distance", config)

    @unittest.skipUnless(shutil.which("g++"), "g++ required for native regression")
    def test_legacy_limits_do_not_override_polygon(self):
        with tempfile.TemporaryDirectory() as directory:
            exe = str(Path(directory) / "polygon-test")
            subprocess.run(["g++", "-std=c++17", "-I", str(ROOT),
                            str(ROOT / "tests/polygon_only_test.cpp"), "-o", exe], check=True)
            subprocess.run([exe], check=True)

if __name__ == "__main__":
    unittest.main()
