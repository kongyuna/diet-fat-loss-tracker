import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "food_lookup.py"
DATA = SKILL_DIR / "assets" / "food-data" / "tw_food_macros.csv"
SOURCE = SKILL_DIR / "assets" / "food-data" / "SOURCE.md"


class FoodLookupTests(unittest.TestCase):
    def lookup(self, food, limit=None):
        command = [sys.executable, str(SCRIPT), "lookup", food, "--data", str(DATA)]
        if limit is not None:
            command.extend(["--limit", str(limit)])
        result = subprocess.run(command, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_bundled_data_is_small_and_license_traceable(self):
        source = SOURCE.read_text(encoding="utf-8")
        digest = hashlib.sha256(DATA.read_bytes()).hexdigest()

        self.assertLess(DATA.stat().st_size, 100 * 1024 * 1024)
        self.assertEqual(digest, "b5a0e3530cd71d82bdcaaafe7ff06d390230644d67af9f9fcb2c0ea8c3da2101")
        self.assertIn(digest, source)
        self.assertIn("政府资料开放授权条款第 1 版", source)
        self.assertIn("不等同于中国大陆", source)

    def test_simplified_exact_query_returns_macros(self):
        result = self.lookup("白饭")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["matches"][0]["food_name"], "白飯")
        self.assertEqual(result["matches"][0]["fat_g"], "0.3")
        self.assertEqual(result["source_region"], "台湾地区")

    def test_ambiguous_query_does_not_silently_choose(self):
        result = self.lookup("鸡胸肉")

        self.assertEqual(result["status"], "ambiguous")
        self.assertGreaterEqual(len(result["matches"]), 2)

    def test_result_limit_cannot_turn_ambiguous_query_into_unique_match(self):
        result = self.lookup("鸡胸肉", limit=1)

        self.assertEqual(result["status"], "ambiguous")
        self.assertEqual(len(result["matches"]), 1)


if __name__ == "__main__":
    unittest.main()
