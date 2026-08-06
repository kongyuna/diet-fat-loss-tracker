import csv
import importlib.util
import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "weight_forecast.py"
SKILL = SKILL_DIR / "SKILL.md"
HEADERS = [
    "日期", "餐次", "食物", "估算份量", "热量下限", "热量上限", "采用热量",
    "蛋白质下限", "蛋白质上限", "采用蛋白质", "碳水下限", "碳水上限",
    "采用碳水", "可信度", "运动项目", "运动时长分钟", "运动强度",
    "是否额外运动", "备注",
]


def load_module():
    spec = importlib.util.spec_from_file_location("weight_forecast", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WeightForecastTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.csv_path = self.root / "饮食记录.csv"
        self.profile_path = self.root / "减脂档案.md"

    def tearDown(self):
        self.temp_dir.cleanup()

    def write_csv(self, rows):
        with self.csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=HEADERS)
            writer.writeheader()
            writer.writerows(rows)

    def write_profile(self, monthly_rows=None, maintenance="2300千卡/日"):
        monthly_rows = monthly_rows or [
            "| 2026-08 | 2026-08-01 | 90 | 暂无 | 无 | 2050 | 94~126 | 231~282 | — | — | — | 0 | 首次建档 |"
        ]
        self.profile_path.write_text(textwrap.dedent(f"""
            # 减脂档案

            ## 基础资料
            - 用于公式的性别：男
            - 年龄：30
            - 身高：180
            - 目标体重：75kg

            ## 当前目标
            - 生效月份：2026-08
            - 当前体重：90kg
            - 热量：2050千卡
            - 蛋白质：94~126克
            - 碳水：231~282克
            - 估算维持热量：{maintenance}
            - 体重预测模型：forbes-hall-v1
            - 维持热量校准修正：0千卡/日
            - 上次校准月份：无

            ## 月度记录
            | 月份 | 称重日期 | 体重 | 最近两周趋势 | 活动变化 | 热量目标 | 蛋白质目标 | 碳水目标 | 模型预测变化 | 实测变化 | 预测误差 | 维持热量校准 | 调整原因 |
            |---|---|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---|
            {chr(10).join(monthly_rows)}
        """).strip() + "\n", encoding="utf-8")

    def run_cli(self, mode, value):
        result = subprocess.run([
            sys.executable, str(SCRIPT), mode, value,
            "--csv", str(self.csv_path), "--profile", str(self.profile_path),
        ], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_same_deficit_predicts_less_mass_change_at_higher_fat_mass(self):
        module = load_module()
        leaner = module.energy_equivalent(-500, weight=75, height_cm=180, age=30, formula_sex="男")
        fatter = module.energy_equivalent(-500, weight=120, height_cm=180, age=30, formula_sex="男")

        self.assertLess(abs(fatter["kg"]), abs(leaner["kg"]))
        self.assertGreater(fatter["kcal_per_kg"], leaner["kcal_per_kg"])

    def test_daily_cli_includes_conditional_range_and_extra_exercise(self):
        self.write_profile()
        self.write_csv([
            {"日期": "2026-08-06", "餐次": "午餐", "食物": "测试餐", "估算份量": "1份",
             "热量下限": "1700", "热量上限": "1900", "采用热量": "1800", "可信度": "中"},
            {"日期": "2026-08-06", "运动项目": "快走", "运动时长分钟": "45",
             "运动强度": "中", "是否额外运动": "是", "备注": "超出常规"},
        ])

        result = self.run_cli("daily", "2026-08-06")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["condition"], "若今天此后不再进食")
        self.assertEqual(result["extra_exercise_kcal"], 100)
        self.assertLess(result["weight_change_kg"]["point"], 0)
        self.assertLessEqual(result["weight_change_kg"]["low"], result["weight_change_kg"]["point"])
        self.assertLessEqual(result["weight_change_kg"]["point"], result["weight_change_kg"]["high"])
        self.assertIn("不等于明早秤重", result["disclaimer"])

    def test_daily_cli_refuses_to_invent_without_maintenance(self):
        self.write_profile(maintenance="")
        self.write_csv([
            {"日期": "2026-08-06", "餐次": "午餐", "食物": "测试餐", "估算份量": "1份",
             "热量下限": "700", "热量上限": "900", "采用热量": "800", "可信度": "中"},
        ])

        result = self.run_cli("daily", "2026-08-06")

        self.assertEqual(result["status"], "insufficient")
        self.assertIn("维持热量", result["reason"])

    def test_monthly_low_coverage_compares_but_does_not_calibrate(self):
        self.write_profile(monthly_rows=[
            "| 2026-07 | 2026-07-01 | 100 | 无 | 无 | 2200 | 100~140 | 230~290 | — | — | — | 0 | 初始 |",
            "| 2026-08 | 2026-08-01 | 97 | 下降 | 无 | 2050 | 94~126 | 231~282 | — | — | — | 0 | 月初 |",
        ])
        rows = []
        for day in range(1, 11):
            for meal, calories in (("早餐", 500), ("午餐", 800), ("晚餐", 700)):
                rows.append({"日期": f"2026-07-{day:02d}", "餐次": meal, "食物": "测试餐",
                             "热量下限": str(calories - 50), "热量上限": str(calories + 50),
                             "采用热量": str(calories), "可信度": "中"})
        self.write_csv(rows)

        result = self.run_cli("month", "2026-08")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["calibration"]["applied"], False)
        self.assertIn("覆盖", result["calibration"]["reason"])

    def test_monthly_unknown_previous_weigh_date_stays_insufficient(self):
        self.write_profile(monthly_rows=[
            "| 2026-08 | 未知 | 100 | 无 | 无 | 2200 | 100~140 | 230~290 | — | — | — | 0 | 初始 |",
            "| 2026-09 | 2026-09-01 | 98 | 下降 | 无 | 2050 | 94~126 | 231~282 | — | — | — | 0 | 月初 |",
        ])
        self.write_csv([])

        result = self.run_cli("month", "2026-09")

        self.assertEqual(result["status"], "insufficient")
        self.assertIn("称重日期", result["reason"])

    def test_monthly_calibration_is_smoothed_and_capped(self):
        self.write_profile(monthly_rows=[
            "| 2026-07 | 2026-07-01 | 100 | 无 | 无 | 2200 | 100~140 | 230~290 | — | — | — | 0 | 初始 |",
            "| 2026-08 | 2026-08-01 | 96 | 下降 | 无 | 2050 | 94~126 | 231~282 | — | — | — | 0 | 月初 |",
        ])
        rows = []
        for day in range(1, 32):
            for meal, calories in (("早餐", 500), ("午餐", 800), ("晚餐", 700)):
                rows.append({"日期": f"2026-07-{day:02d}", "餐次": meal, "食物": "测试餐",
                             "热量下限": str(calories - 50), "热量上限": str(calories + 50),
                             "采用热量": str(calories), "可信度": "中"})
        self.write_csv(rows)

        result = self.run_cli("month", "2026-08")

        self.assertEqual(result["complete_days"], 31)
        self.assertEqual(result["calibration"]["applied"], True)
        self.assertEqual(result["calibration"]["recommended_adjustment_kcal"], 100)
        self.assertLess(result["predicted_change_kg"], 0)
        self.assertEqual(result["actual_change_kg"], -4.0)

    def test_skill_contains_flexible_v5_reply_contract(self):
        text = SKILL.read_text(encoding="utf-8")
        self.assertIn("先用一至两句给出结论", text)
        self.assertIn("本餐热量、蛋白质、碳水的估算区间和采用值", text)
        self.assertIn("今日三项累计、当前目标、完成比例或差额", text)
        self.assertIn("若今天此后不再进食", text)
        self.assertIn("自行选择最清晰且最简洁的展示方式", text)
        self.assertIn("不固定标题、表格、进度条或排版", text)
        self.assertNotIn("进度条固定 10 格", text)
        self.assertNotIn("██████████", text)
        self.assertNotIn("data-dynamic-ui-widget", text)


if __name__ == "__main__":
    unittest.main()
