import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "progress_bar.py"


def load_module():
    spec = importlib.util.spec_from_file_location("progress_bar", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ProgressBarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def render(self, current, target=2000):
        return self.module.render_item({
            "label": "热量", "current": current, "target": target, "unit": "kcal",
        })

    def test_below_goal_keeps_visible_full_capacity(self):
        result = self.render(400)

        self.assertEqual(result["display_percent"], "20%")
        self.assertEqual(result["bar"], "█" * 8 + "░" * 32)
        self.assertEqual(len(result["bar"]), 40)
        self.assertIn("400 / 2000 kcal", result["text"])

    def test_goal_fills_exactly_forty_cells(self):
        result = self.render(2000)

        self.assertEqual(result["bar"], "█" * 40)
        self.assertEqual(result["empty_cells"], 0)
        self.assertEqual(result["overflow_cells"], 0)

    def test_below_100_percent_always_keeps_a_remaining_cell(self):
        result = self.render(1980)

        self.assertEqual(result["display_percent"], "99%")
        self.assertEqual(result["bar"], "█" * 39 + "░")

    def test_over_goal_appends_distinct_cells_at_same_scale(self):
        result = self.render(2600)

        self.assertEqual(result["display_percent"], "130%")
        self.assertEqual(result["bar"], "█" * 40 + "▣" * 12)
        self.assertEqual(result["overflow_cells"], 12)

    def test_any_over_goal_has_a_visible_overflow_cell(self):
        result = self.render(2020)

        self.assertEqual(result["display_percent"], "101%")
        self.assertEqual(result["bar"], "█" * 40 + "▣")

    def test_above_150_percent_caps_visual_overflow(self):
        result = self.render(3400)

        self.assertEqual(result["display_percent"], ">150%")
        self.assertEqual(result["bar"], "█" * 40 + "▣" * 20)
        self.assertEqual(len(result["bar"]), 60)

    def test_cli_returns_one_exact_combined_text(self):
        items = [
            {"label": "热量", "current": 400, "target": 2000, "unit": "kcal"},
            {"label": "蛋白质", "current": 120, "target": 100, "unit": "g"},
        ]
        result = subprocess.run([
            sys.executable, str(SCRIPT), "--items-json", json.dumps(items, ensure_ascii=False),
        ], text=True, capture_output=True)
        payload = json.loads(result.stdout)

        self.assertEqual(result.returncode, 0)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["text"], "\n".join(item["text"] for item in payload["items"]))
        self.assertIn("░", payload["items"][0]["bar"])
        self.assertIn("▣", payload["items"][1]["bar"])


if __name__ == "__main__":
    unittest.main()
