import csv
import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "training_tracker.py"
SKILL = SKILL_DIR / "SKILL.md"
TRAINING_HEADERS = [
    "日期", "开始时间", "训练ID", "训练类型", "整节时长分钟", "动作", "组数", "次数", "重量kg",
    "时长分钟", "RIR", "RPE", "训练感受", "主要部位", "次要部位", "恢复反馈",
    "恢复反馈时间", "疼痛信号", "是否额外运动", "备注",
]
DIET_HEADERS = [
    "日期", "餐次", "食物", "估算份量", "热量下限", "热量上限", "采用热量",
    "蛋白质下限", "蛋白质上限", "采用蛋白质", "碳水下限", "碳水上限",
    "采用碳水", "脂肪下限", "脂肪上限", "采用脂肪", "可信度", "运动项目", "运动时长分钟", "运动强度",
    "是否额外运动", "备注",
]


class TrainingTrackerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.training_csv = self.root / "训练记录.csv"
        self.diet_csv = self.root / "饮食记录.csv"
        self.profile = self.root / "减脂档案.md"
        self.profile.write_text(textwrap.dedent("""
            # 减脂档案

            ## 基础资料
            - 用于公式的性别：男
            - 年龄：30
            - 身高：180

            ## 当前目标
            - 当前体重：90kg
            - 热量：2050千卡

            ## 月度记录
            | 月份 | 称重日期 | 体重 |
            |---|---|---:|
        """).strip() + "\n", encoding="utf-8")
        self.write_diet([])

    def tearDown(self):
        self.temp_dir.cleanup()

    def run_cli(self, *args):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), *map(str, args)],
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def write_diet(self, rows):
        with self.diet_csv.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=DIET_HEADERS)
            writer.writeheader()
            writer.writerows(rows)

    def read_rows(self, path):
        with path.open("r", encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))

    def configure(self, equipment="健身房"):
        return self.run_cli(
            "configure", "--profile", self.profile,
            "--goal", "减脂保肌", "--experience", "初级", "--equipment", equipment,
            "--minutes", "30～60分钟", "--frequency", "不固定，0～3次/周",
            "--limits", "无", "--dislikes", "无",
        )

    def record(self, day="2026-08-09", start="10:00", session_id="s-001", extra="否", feeling="刚好"):
        exercises = json.dumps([
            {"name": "深蹲", "sets": 3, "reps": "8", "weight_kg": 60, "rir": 2},
            {"name": "卧推", "sets": 3, "reps": "8", "weight_kg": 40, "rir": 2},
            {"name": "划船", "sets": 3, "reps": "10", "weight_kg": 35, "rir": 2},
        ], ensure_ascii=False)
        return self.run_cli(
            "record", "--training-csv", self.training_csv, "--diet-csv", self.diet_csv,
            "--date", day, "--start-time", start, "--session-id", session_id,
            "--type", "力量", "--duration", "50", "--rpe", "7", "--feeling", feeling,
            "--extra", extra, "--pain", "无", "--exercises", exercises,
        )

    def test_configure_adds_one_training_section_and_readback(self):
        first = self.configure()
        second = self.configure(equipment="居家哑铃")

        text = self.profile.read_text(encoding="utf-8")
        self.assertEqual(first["status"], "ok")
        self.assertEqual(second["training_config"]["器械条件"], "居家哑铃")
        self.assertEqual(text.count("## 训练配置"), 1)
        self.assertIn("- 可训练频率：不固定，0～3次/周", text)

    def test_record_writes_both_ledgers_and_retry_is_idempotent(self):
        first = self.record()
        second = self.record()

        training_rows = self.read_rows(self.training_csv)
        diet_rows = self.read_rows(self.diet_csv)
        self.assertEqual(first["status"], "ok")
        self.assertEqual(first["created"], True)
        self.assertEqual(second["idempotent"], True)
        self.assertEqual(len(training_rows), 3)
        self.assertEqual(len(diet_rows), 1)
        self.assertIn("[training:s-001]", diet_rows[0]["备注"])

    def test_same_session_id_with_different_content_is_rejected(self):
        self.record()
        exercises = json.dumps([{"name": "硬拉", "sets": 3, "reps": "5", "rir": 2}], ensure_ascii=False)
        result = self.run_cli(
            "record", "--training-csv", self.training_csv, "--diet-csv", self.diet_csv,
            "--date", "2026-08-09", "--session-id", "s-001", "--type", "力量",
            "--duration", "30", "--feeling", "刚好", "--exercises", exercises,
        )

        self.assertEqual(result["status"], "error")
        self.assertIn("相同训练ID", result["reason"])
        self.assertEqual(len(self.read_rows(self.training_csv)), 3)
        self.assertEqual(len(self.read_rows(self.diet_csv)), 1)

    def test_partial_diet_sync_recovers_with_same_session_id(self):
        self.diet_csv.write_text("错误表头\n", encoding="utf-8")
        partial = self.record(session_id="s-partial")
        self.write_diet([])
        recovered = self.record(session_id="s-partial")

        self.assertEqual(partial["status"], "partial")
        self.assertEqual(partial["training_written"], True)
        self.assertEqual(partial["diet_summary_written"], False)
        self.assertEqual(recovered["status"], "ok")
        self.assertEqual(recovered["idempotent"], True)
        self.assertEqual(len(self.read_rows(self.training_csv)), 3)
        self.assertEqual(len(self.read_rows(self.diet_csv)), 1)

    def test_regular_and_extra_training_keep_explicit_diet_flag(self):
        self.record(session_id="regular", extra="否")
        self.record(day="2026-08-10", session_id="extra", extra="是")

        rows = self.read_rows(self.diet_csv)
        self.assertEqual([row["是否额外运动"] for row in rows], ["否", "是"])

    def test_unknown_exercise_requires_explicit_mapping(self):
        exercises = json.dumps([{"name": "神秘动作", "sets": 3}], ensure_ascii=False)
        result = self.run_cli(
            "record", "--training-csv", self.training_csv, "--diet-csv", self.diet_csv,
            "--date", "2026-08-09", "--session-id", "unknown", "--type", "力量",
            "--duration", "30", "--feeling", "刚好", "--exercises", exercises,
        )

        self.assertEqual(result["status"], "error")
        self.assertIn("未知动作", result["reason"])
        self.assertFalse(self.training_csv.exists())

    def test_status_uses_review_window_not_recovery_percentage(self):
        self.record()
        result = self.run_cli(
            "status", "--training-csv", self.training_csv, "--as-of", "2026-08-10T10:00",
        )

        encoded = json.dumps(result, ensure_ascii=False)
        self.assertEqual(result["status"], "ok")
        self.assertIn("复查窗口", result["disclaimer"])
        self.assertNotIn("恢复百分比", encoded.replace(result["disclaimer"], ""))
        self.assertNotIn("recovery_percent", encoded)
        self.assertTrue(any(item["muscle"] == "股四头" for item in result["muscles"]))

    def test_training_before_window_extends_latest_upper_bound(self):
        self.record(day="2026-08-09", start="10:00", session_id="first")
        first = self.run_cli(
            "status", "--training-csv", self.training_csv, "--as-of", "2026-08-10T00:00",
        )
        self.record(day="2026-08-10", start="10:00", session_id="second")
        second = self.run_cli(
            "status", "--training-csv", self.training_csv, "--as-of", "2026-08-10T12:00",
        )

        first_quad = next(item for item in first["muscles"] if item["muscle"] == "股四头")
        second_quad = next(item for item in second["muscles"] if item["muscle"] == "股四头")
        self.assertGreater(second_quad["next_heavy_review_latest"], first_quad["next_heavy_review_latest"])

    def test_three_consistent_feedbacks_raise_confidence(self):
        for index, day in enumerate(("2026-08-01", "2026-08-04", "2026-08-07"), start=1):
            session_id = f"feedback-{index}"
            self.record(day=day, session_id=session_id)
            result = self.run_cli(
                "feedback", "--training-csv", self.training_csv, "--session-id", session_id,
                "--feedback", '{"整体":"正常"}', "--at", f"{day}T22:00",
            )
            self.assertEqual(result["status"], "ok")
        status = self.run_cli(
            "status", "--training-csv", self.training_csv, "--as-of", "2026-08-08T12:00",
        )

        quad = next(item for item in status["muscles"] if item["muscle"] == "股四头")
        self.assertEqual(quad["confidence"], "中")

    def test_render_is_deterministic_and_contains_ten_regions(self):
        self.record()
        first = self.root / "first.svg"
        second = self.root / "second.svg"
        result_one = self.run_cli(
            "render", "--training-csv", self.training_csv, "--start", "2026-08-09",
            "--end", "2026-08-09", "--output", first,
        )
        result_two = self.run_cli(
            "render", "--training-csv", self.training_csv, "--start", "2026-08-09",
            "--end", "2026-08-09", "--output", second,
        )

        self.assertEqual(result_one["status"], "ok")
        self.assertEqual(first.read_text(encoding="utf-8"), second.read_text(encoding="utf-8"))
        svg = first.read_text(encoding="utf-8")
        for muscle in ("胸", "背", "肩", "肱二头", "肱三头", "核心", "臀", "股四头", "腘绳肌", "小腿"):
            self.assertIn(f'id="{muscle}"', svg)
            self.assertIn(f'data-muscle="{muscle}"', svg)
        self.assertIn("正面 · 前侧", svg)
        self.assertIn("背面 · 后侧", svg)
        self.assertIn("不表示恢复百分比", svg)

    def test_render_defaults_to_dedicated_temporary_html(self):
        self.record()
        result = self.run_cli(
            "render", "--training-csv", self.training_csv, "--start", "2026-08-09",
            "--end", "2026-08-09",
        )
        repeated = self.run_cli(
            "render", "--training-csv", self.training_csv, "--start", "2026-08-09",
            "--end", "2026-08-09",
        )

        output = Path(result["output"])
        rendered_html = output.read_text(encoding="utf-8")
        self.assertEqual(result["format"], "html")
        self.assertEqual(result["temporary"], True)
        self.assertEqual(output.parent, Path(tempfile.gettempdir()) / "diet-fat-loss-tracker")
        self.assertEqual(repeated["output"], result["output"])
        self.assertEqual(len(list(output.parent.glob("training-muscle-map.*"))), 1)
        self.assertNotIn(str(SKILL_DIR.parent), str(output))
        self.assertIn("<!doctype html>", rendered_html)
        self.assertIn("ANTERIOR · FACING YOU", rendered_html)
        self.assertIn("POSTERIOR · BACK TO YOU", rendered_html)
        self.assertIn("training.seer.cancer.gov", rendered_html)

    def test_plan_uses_rolling_queue_for_any_available_time(self):
        self.configure()
        first_plan = self.run_cli(
            "plan", "--training-csv", self.training_csv, "--profile", self.profile,
            "--available-minutes", "25", "--as-of", "2026-08-09T09:00",
        )
        self.record(day="2026-08-09", session_id="plan-a")
        second_plan = self.run_cli(
            "plan", "--training-csv", self.training_csv, "--profile", self.profile,
            "--available-minutes", "70", "--as-of", "2026-08-12T09:00",
        )

        self.assertEqual(first_plan["session"], "A")
        self.assertLessEqual(len(first_plan["exercises"]), 4)
        self.assertEqual(second_plan["session"], "B")
        self.assertLessEqual(len(second_plan["exercises"]), 6)
        self.assertIn("不绑定固定星期", second_plan["schedule_rule"])

    def test_evaluate_compares_actual_session_to_plan(self):
        self.record()
        plan = json.dumps({"exercises": [
            {"exercise": "深蹲", "sets": "3", "reps": "6～10", "target_rir": "2～4"},
            {"exercise": "卧推", "sets": "3", "reps": "6～10", "target_rir": "2～4"},
            {"exercise": "划船", "sets": "3", "reps": "8～12", "target_rir": "2～4"},
        ]}, ensure_ascii=False)
        result = self.run_cli(
            "evaluate", "--training-csv", self.training_csv, "--session-id", "s-001", "--plan", plan,
        )

        self.assertEqual(result["overall"], "达到本次主要目标")
        self.assertEqual(result["completion_band"], "至少80%")
        self.assertTrue(all(item["result"] == "达标" for item in result["exercises"]))
        self.assertIn("只调整一个变量", result["next_action"])

    def test_evaluate_cardio_uses_minutes_and_rpe(self):
        exercises = json.dumps([{"name": "快走", "minutes": 30, "rpe": 5}], ensure_ascii=False)
        recorded = self.run_cli(
            "record", "--training-csv", self.training_csv, "--diet-csv", self.diet_csv,
            "--date", "2026-08-09", "--session-id", "cardio", "--type", "有氧",
            "--duration", "30", "--rpe", "5", "--feeling", "刚好", "--exercises", exercises,
        )
        plan = json.dumps({"exercises": [
            {"exercise": "快走", "sets": "1", "reps": "20～40分钟", "target_rir": "RPE 4～6"},
        ]}, ensure_ascii=False)
        result = self.run_cli(
            "evaluate", "--training-csv", self.training_csv, "--session-id", "cardio", "--plan", plan,
        )

        self.assertEqual(recorded["status"], "ok")
        self.assertEqual(result["overall"], "达到本次主要目标")
        self.assertEqual(result["exercises"][0]["result"], "达标")
        self.assertEqual(result["exercises"][0]["actual_reps_or_minutes"], "30")
        self.assertEqual(result["exercises"][0]["actual_rir_or_rpe"], "5")

    def test_no_equipment_plan_uses_no_dumbbell_or_machine(self):
        self.configure(equipment="无器械")
        plan = self.run_cli(
            "plan", "--training-csv", self.training_csv, "--profile", self.profile,
            "--available-minutes", "60", "--as-of", "2026-08-09T09:00",
        )

        names = [item["exercise"] for item in plan["exercises"]]
        self.assertNotIn("哑铃划船", names)
        self.assertNotIn("高位下拉", names)
        self.assertIn("俯卧W抬臂", names)

    def test_injury_limit_stops_automatic_plan(self):
        self.run_cli(
            "configure", "--profile", self.profile,
            "--goal", "减脂保肌", "--experience", "初级", "--equipment", "健身房",
            "--minutes", "45分钟", "--frequency", "不固定", "--limits", "右膝疼痛",
            "--dislikes", "无",
        )
        plan = self.run_cli(
            "plan", "--training-csv", self.training_csv, "--profile", self.profile,
            "--available-minutes", "45", "--as-of", "2026-08-09T09:00",
        )

        self.assertEqual(plan["status"], "needs_review")
        self.assertIn("右膝疼痛", plan["reason"])

    def test_skill_routes_training_only_when_needed(self):
        text = SKILL.read_text(encoding="utf-8")
        self.assertIn("普通餐食：只读取", text)
        self.assertIn("## 记录训练", text)
        self.assertIn("## 今天能训练", text)
        self.assertIn("## 初次与月度联合复核", text)
        self.assertIn("不假定固定星期或每周次数", text)
        self.assertIn("训练脚本同步饮食摘要", text)


if __name__ == "__main__":
    unittest.main()
