import json
import subprocess
import sys
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "target_planner.py"


class TargetPlannerTests(unittest.TestCase):
    def run_cli(self, *extra):
        result = subprocess.run([
            sys.executable, str(SCRIPT),
            "--sex", "男", "--age", "30", "--height-cm", "175",
            "--current-weight", "85", "--target-weight", "75",
            "--activity", "轻活动", "--as-of", "2026-08-16",
            *extra,
        ], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_outputs_four_formulas_and_adopts_schofield(self):
        result = self.run_cli()

        self.assertEqual(result["status"], "ok")
        self.assertEqual(set(result["rmr_kcal"]), {
            "schofield", "mifflin_st_jeor", "liu", "xue1",
        })
        self.assertEqual(result["adopted_rmr"]["formula"], "schofield")
        self.assertEqual(result["choices"], ["采用推荐值", "更保守一些", "修改目标体重或日期"])
        self.assertGreater(result["formula_spread_percent"], 10)
        self.assertEqual(result["confidence"], "低")

    def test_aggressive_deadline_requires_adjustment(self):
        result = self.run_cli("--target-date", "2026-09-01")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["feasibility"], "需要调整目标体重或日期")
        self.assertTrue(any("期限" in reason for reason in result["reasons"]))

    def test_underweight_goal_is_rejected(self):
        result = subprocess.run([
            sys.executable, str(SCRIPT),
            "--sex", "女", "--age", "30", "--height-cm", "170",
            "--current-weight", "60", "--target-weight", "45",
            "--activity", "久坐", "--as-of", "2026-08-16",
        ], text=True, capture_output=True)
        payload = json.loads(result.stdout)

        self.assertEqual(result.returncode, 0)
        self.assertEqual(payload["status"], "error")
        self.assertIn("BMI低于18.5", payload["reason"])

    def test_skill_has_native_choice_fallback_and_progressive_visibility(self):
        skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        profile = (SKILL_DIR / "references" / "profile-and-targets.md").read_text(encoding="utf-8")

        self.assertIn("原生选择组件", skill)
        self.assertIn("一次性列出全部必要问题", skill)
        self.assertIn("普通记录只输出第 1、2、3、6 节", skill)
        self.assertIn("一个批量问题", profile)


if __name__ == "__main__":
    unittest.main()
