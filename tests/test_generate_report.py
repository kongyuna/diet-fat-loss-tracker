import csv
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "generate_report.py"
HEADERS = [
    "日期", "餐次", "食物", "估算份量", "热量下限", "热量上限", "采用热量",
    "蛋白质下限", "蛋白质上限", "采用蛋白质", "碳水下限", "碳水上限",
    "采用碳水", "脂肪下限", "脂肪上限", "采用脂肪", "可信度", "运动项目", "运动时长分钟", "运动强度",
    "是否额外运动", "备注",
]


class GenerateReportTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.csv_path = self.root / "饮食记录.csv"
        self.profile_path = self.root / "减脂档案.md"
        self.output_dir = self.root / "报告"

        rows = []
        for index, day in enumerate(range(3, 8)):
            rows.append({
                "日期": f"2026-08-{day:02d}",
                "餐次": "午餐",
                "食物": "测试餐",
                "估算份量": "1份",
                "热量下限": "1800",
                "热量上限": "2200",
                "采用热量": str(1980 + index * 20),
                "蛋白质下限": "90",
                "蛋白质上限": "130",
                "采用蛋白质": str(96 + index * 4),
                "碳水下限": "200" if day != 5 else "",
                "碳水上限": "280" if day != 5 else "",
                "采用碳水": str(230 + index * 5) if day != 5 else "",
                "可信度": "中",
                "备注": "测试数据",
            })
        rows.append({
            "日期": "2026-08-06",
            "运动项目": "快走",
            "运动时长分钟": "45",
            "运动强度": "中",
            "是否额外运动": "是",
            "备注": "测试运动",
        })

        with self.csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=HEADERS)
            writer.writeheader()
            writer.writerows(rows)

        self.profile_path.write_text(textwrap.dedent("""
            # 减脂档案

            ## 基础资料
            - 用于公式的性别：男
            - 年龄：30
            - 身高：180
            - 目标体重：80kg

            ## 当前目标
            - 生效月份：2026-08
            - 当前体重：90kg
            - 热量：1900~2100千卡
            - 蛋白质：90~130克
            - 碳水：200~280克

            ## 月度记录
            | 月份 | 体重 | 最近两周趋势 | 活动变化 | 热量目标 | 蛋白质目标 | 碳水目标 | 调整原因 |
            | 2026-07 | 100 | 无 | 无 | 2000 | 90~130 | 200~280 | 初始记录 |
            | 2026-08 | 90 | 下降 | 无 | 2000 | 90~130 | 200~280 | 月初更新 |
        """).strip() + "\n", encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    def run_report(self, period, date):
        result = subprocess.run([
            sys.executable,
            str(SCRIPT),
            period,
            "--date", date,
            "--csv", str(self.csv_path),
            "--profile", str(self.profile_path),
            "--output-dir", str(self.output_dir),
        ], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        output_path = Path(result.stdout.strip().splitlines()[-1])
        self.assertTrue(output_path.is_file(), result.stdout)
        return output_path, output_path.read_text(encoding="utf-8")

    def test_week_report_has_fixed_offline_mobile_contract(self):
        path, html = self.run_report("week", "2026-08-09")

        self.assertEqual(path.name, "2026-W32.html")
        for marker in ("2026年第32周", "减重进度", "每日热量", "每日蛋白质", "数据说明"):
            self.assertIn(marker, html)
        self.assertIn('name="viewport"', html)
        tablet_css = html.split('@media (max-width:760px)', 1)[1].split('@media (max-width:430px)', 1)[0]
        self.assertIn('.progress-card { grid-template-columns:1fr; text-align:center;', tablet_css)
        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)

    def test_month_report_has_month_contract(self):
        path, html = self.run_report("month", "2026-08-31")

        self.assertEqual(path.name, "2026-08.html")
        for marker in ("2026年8月", "周均趋势", "每日达标热力图", "预测 vs 实测", "校准状态"):
            self.assertIn(marker, html)
        self.assertIn("diet-fat-loss-tracker V4", html)

    def test_progress_and_missing_carbs_are_explicit(self):
        _, html = self.run_report("week", "2026-08-09")

        self.assertIn("50%", html)
        self.assertIn("碳水可计算 4 / 5 天", html)
        self.assertNotIn("碳水可计算 5 / 5 天", html)

    def test_rerun_overwrites_the_same_period_file(self):
        first_path, _ = self.run_report("week", "2026-08-09")
        second_path, _ = self.run_report("week", "2026-08-09")

        self.assertEqual(first_path, second_path)
        self.assertEqual([path.name for path in self.output_dir.glob("*.html")], ["2026-W32.html"])

    def test_fat_columns_do_not_expand_report_targets_or_charts(self):
        _, html = self.run_report("week", "2026-08-09")

        self.assertNotIn("每日脂肪", html)
        self.assertNotIn("脂肪目标", html)


if __name__ == "__main__":
    unittest.main()
