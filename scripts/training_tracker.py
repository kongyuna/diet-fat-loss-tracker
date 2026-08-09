#!/usr/bin/env python3
"""Deterministic training logging, recovery guidance, planning, and anatomy maps."""

import argparse
import csv
import hashlib
import html
import json
import re
import tempfile
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from pathlib import Path


MODEL_VERSION = "training-recovery-v1"
MUSCLES = ("胸", "背", "肩", "肱二头", "肱三头", "核心", "臀", "股四头", "腘绳肌", "小腿")
MUSCLE_TEMPLATE = Path(__file__).resolve().parents[1] / "assets" / "muscle-map-anatomical.svg"
MUSCLE_KEYS = {
    "胸": "CHEST", "背": "BACK", "肩": "SHOULDER", "肱二头": "BICEPS",
    "肱三头": "TRICEPS", "核心": "CORE", "臀": "GLUTES", "股四头": "QUADS",
    "腘绳肌": "HAMSTRINGS", "小腿": "CALVES",
}
TRAINING_HEADERS = [
    "日期", "开始时间", "训练ID", "训练类型", "整节时长分钟", "动作", "组数", "次数", "重量kg",
    "时长分钟", "RIR", "RPE", "训练感受", "主要部位", "次要部位", "恢复反馈",
    "恢复反馈时间", "疼痛信号", "是否额外运动", "备注",
]
DIET_HEADERS = [
    "日期", "餐次", "食物", "估算份量", "热量下限", "热量上限", "采用热量",
    "蛋白质下限", "蛋白质上限", "采用蛋白质", "碳水下限", "碳水上限",
    "采用碳水", "可信度", "运动项目", "运动时长分钟", "运动强度",
    "是否额外运动", "备注",
]
FEELINGS = ("偏轻", "刚好", "偏重", "疼痛或异常")
FEEDBACK_VALUES = ("正常", "轻微疲劳", "明显影响动作", "疼痛")


EXERCISES = {
    "深蹲": (("股四头", "臀"), ("腘绳肌", "核心")),
    "徒手深蹲": (("股四头", "臀"), ("腘绳肌", "核心")),
    "杠铃深蹲": (("股四头", "臀"), ("腘绳肌", "核心")),
    "高脚杯深蹲": (("股四头", "臀"), ("腘绳肌", "核心")),
    "箭步蹲": (("股四头", "臀"), ("腘绳肌", "核心")),
    "保加利亚分腿蹲": (("股四头", "臀"), ("腘绳肌", "核心")),
    "腿举": (("股四头", "臀"), ("腘绳肌",)),
    "硬拉": (("臀", "腘绳肌", "背"), ("核心",)),
    "罗马尼亚硬拉": (("腘绳肌", "臀"), ("背", "核心")),
    "臀桥": (("臀",), ("腘绳肌", "核心")),
    "卧推": (("胸",), ("肩", "肱三头")),
    "哑铃卧推": (("胸",), ("肩", "肱三头")),
    "俯卧撑": (("胸",), ("肩", "肱三头", "核心")),
    "肩推": (("肩",), ("肱三头", "核心")),
    "哑铃肩推": (("肩",), ("肱三头", "核心")),
    "俯身推举": (("肩",), ("肱三头", "核心")),
    "侧平举": (("肩",), ()),
    "划船": (("背",), ("肱二头", "肩")),
    "哑铃划船": (("背",), ("肱二头", "肩")),
    "俯卧W抬臂": (("背", "肩"), ("核心",)),
    "坐姿划船": (("背",), ("肱二头", "肩")),
    "高位下拉": (("背",), ("肱二头",)),
    "引体向上": (("背",), ("肱二头", "核心")),
    "弯举": (("肱二头",), ()),
    "哑铃弯举": (("肱二头",), ()),
    "下压": (("肱三头",), ()),
    "臂屈伸": (("肱三头",), ("胸", "肩")),
    "平板支撑": (("核心",), ("肩", "臀")),
    "卷腹": (("核心",), ()),
    "提踵": (("小腿",), ()),
    "快走": (("股四头", "臀", "小腿"), ("腘绳肌",)),
    "跑步": (("股四头", "臀", "小腿"), ("腘绳肌", "核心")),
    "骑行": (("股四头", "臀"), ("小腿", "腘绳肌")),
    "动感单车": (("股四头", "臀"), ("小腿", "腘绳肌")),
    "椭圆机": (("股四头", "臀"), ("小腿", "腘绳肌")),
    "游泳": (("背", "肩"), ("胸", "核心", "肱三头")),
}


HOME_A = [
    ("徒手深蹲", "2～3", "8～15", "2～4"),
    ("俯卧撑", "2～3", "6～15", "2～4"),
    ("哑铃划船", "2～3", "8～15", "2～4"),
    ("臀桥", "2～3", "10～15", "2～4"),
    ("平板支撑", "2～3", "20～45秒", "2～4"),
    ("快走", "1", "10～20分钟", "—"),
]
HOME_B = [
    ("箭步蹲", "2～3", "每侧6～12", "2～4"),
    ("哑铃肩推", "2～3", "8～15", "2～4"),
    ("高位下拉", "2～3", "8～15", "2～4"),
    ("罗马尼亚硬拉", "2～3", "8～12", "2～4"),
    ("卷腹", "2～3", "10～20", "2～4"),
    ("快走", "1", "10～20分钟", "—"),
]
BODYWEIGHT_A = [
    ("徒手深蹲", "2～3", "8～15", "2～4"),
    ("俯卧撑", "2～3", "6～15", "2～4"),
    ("俯卧W抬臂", "2～3", "8～15", "2～4"),
    ("臀桥", "2～3", "10～15", "2～4"),
    ("平板支撑", "2～3", "20～45秒", "2～4"),
    ("快走", "1", "10～20分钟", "—"),
]
BODYWEIGHT_B = [
    ("箭步蹲", "2～3", "每侧6～12", "2～4"),
    ("俯身推举", "2～3", "6～12", "2～4"),
    ("俯卧W抬臂", "2～3", "8～15", "2～4"),
    ("臀桥", "2～3", "10～15", "2～4"),
    ("卷腹", "2～3", "10～20", "2～4"),
    ("快走", "1", "10～20分钟", "—"),
]
GYM_A = [
    ("杠铃深蹲", "2～3", "6～12", "2～4"),
    ("卧推", "2～3", "6～12", "2～4"),
    ("坐姿划船", "2～3", "8～12", "2～4"),
    ("罗马尼亚硬拉", "2～3", "6～12", "2～4"),
    ("平板支撑", "2～3", "20～45秒", "2～4"),
    ("快走", "1", "10～20分钟", "—"),
]
GYM_B = [
    ("腿举", "2～3", "8～15", "2～4"),
    ("肩推", "2～3", "6～12", "2～4"),
    ("高位下拉", "2～3", "8～12", "2～4"),
    ("臀桥", "2～3", "8～15", "2～4"),
    ("卷腹", "2～3", "10～20", "2～4"),
    ("骑行", "1", "10～20分钟", "—"),
]


def json_output(value):
    print(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def number(value):
    if value is None or str(value).strip() == "":
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", str(value))
    return float(match.group(0)) if match else None


def numeric_values(value):
    return [float(item) for item in re.findall(r"\d+(?:\.\d+)?", str(value or ""))]


def numeric_range(value):
    values = numeric_values(value)
    if not values:
        return None, None
    return min(values), max(values)


def split_muscles(value):
    return tuple(item for item in re.split(r"[,，、;/；\s]+", str(value).strip()) if item)


def validate_muscles(values):
    unknown = sorted(set(values) - set(MUSCLES))
    if unknown:
        raise ValueError(f"未知部位：{','.join(unknown)}")


def read_csv(path, headers, allow_missing=False):
    if not path.exists():
        if allow_missing:
            return []
        raise ValueError(f"文件不存在：{path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != headers:
            raise ValueError(f"{path.name}表头不符合约定")
        rows = []
        for line_number, row in enumerate(reader, start=2):
            if None in row:
                raise ValueError(f"{path.name}第{line_number}行列数错误")
            rows.append(row)
        return rows


def write_csv(path, headers, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def profile_section(text, heading):
    match = re.search(
        rf"^[ \t]*##[ \t]+{re.escape(heading)}[ \t]*$([\s\S]*?)(?=^[ \t]*##[ \t]+|\Z)",
        text,
        flags=re.MULTILINE,
    )
    return match.group(1) if match else ""


def profile_value(block, label):
    match = re.search(rf"^[ \t]*-[ \t]*{re.escape(label)}[ \t]*[：:][ \t]*([^\r\n]*)$", block, re.MULTILINE)
    return match.group(1).strip() if match else ""


def configure_profile(path, values):
    text = path.read_text(encoding="utf-8")
    lines = ["## 训练配置"] + [f"- {label}：{values[label]}" for label in (
        "主要目标", "训练经验", "器械条件", "单次可用时长", "可训练频率", "伤病与限制", "不喜欢动作",
    )]
    replacement = "\n".join(lines) + "\n"
    pattern = re.compile(r"^[ \t]*##[ \t]+训练配置[ \t]*$[\s\S]*?(?=^[ \t]*##[ \t]+|\Z)", re.MULTILINE)
    if pattern.search(text):
        updated = pattern.sub(replacement + "\n", text).rstrip() + "\n"
    else:
        marker = re.search(r"^[ \t]*##[ \t]+月度记录[ \t]*$", text, re.MULTILINE)
        if marker:
            updated = text[:marker.start()].rstrip() + "\n\n" + replacement + "\n" + text[marker.start():]
        else:
            updated = text.rstrip() + "\n\n" + replacement
    path.write_text(updated, encoding="utf-8")
    check = profile_section(path.read_text(encoding="utf-8"), "训练配置")
    for label, value in values.items():
        if profile_value(check, label) != value:
            raise ValueError(f"训练配置回读失败：{label}")
    return {"status": "ok", "profile": str(path), "training_config": values}


def parse_exercises(raw):
    try:
        values = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"动作 JSON 无法解析：{exc.msg}") from exc
    if not isinstance(values, list) or not values:
        raise ValueError("动作 JSON 必须是非空数组")
    parsed = []
    for value in values:
        if not isinstance(value, dict) or not str(value.get("name", "")).strip():
            raise ValueError("每个动作必须包含 name")
        item = dict(value)
        item["name"] = str(item["name"]).strip()
        mapped = EXERCISES.get(item["name"])
        primary = split_muscles(item.get("primary", ""))
        secondary = split_muscles(item.get("secondary", ""))
        if mapped and not primary:
            primary = mapped[0]
        if mapped and not secondary:
            secondary = mapped[1]
        if not primary:
            raise ValueError(f"未知动作“{item['name']}”；请明确 primary/secondary 部位后再记录")
        validate_muscles(primary + secondary)
        item["primary"] = primary
        item["secondary"] = secondary
        parsed.append(item)
    return parsed


def session_identifier(day_text, start_time, session_type, exercises):
    payload = json.dumps({
        "date": day_text,
        "time": start_time,
        "type": session_type,
        "exercises": exercises,
    }, ensure_ascii=False, sort_keys=True, default=list)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:10]
    return f"{day_text.replace('-', '')}-{digest}"


def intensity_label(rpe):
    value = number(rpe)
    if value is None:
        return "未记录"
    if value <= 4:
        return "低"
    if value <= 7:
        return "中"
    return "高"


def diet_summary_row(day_text, session_id, session_type, exercises, duration, rpe, extra, feeling):
    names = "、".join(dict.fromkeys(item["name"] for item in exercises))
    note = f"[training:{session_id}] {session_type}；感受：{feeling}；详细记录见训练账本"
    return {
        "日期": day_text,
        "运动项目": names,
        "运动时长分钟": str(duration),
        "运动强度": intensity_label(rpe),
        "是否额外运动": extra,
        "备注": note,
    }


def record_session(args):
    date.fromisoformat(args.date)
    if args.feeling not in FEELINGS:
        raise ValueError(f"训练感受应为：{'/'.join(FEELINGS)}")
    exercises = parse_exercises(args.exercises)
    session_id = args.session_id or session_identifier(args.date, args.start_time, args.type, exercises)
    training_rows = read_csv(args.training_csv, TRAINING_HEADERS, allow_missing=True)
    existing = [row for row in training_rows if row["训练ID"] == session_id]
    created = False
    expected_actions = [(
        item["name"], str(item.get("sets", "")), str(item.get("reps", "")),
        str(item.get("weight_kg", "")), str(item.get("minutes", "")),
        str(item.get("rir", "")), str(item.get("rpe", args.rpe or "")),
        "、".join(item["primary"]), "、".join(item["secondary"]), str(item.get("notes", "")),
    ) for item in exercises]
    if existing:
        actual_actions = [(
            row["动作"], row["组数"], row["次数"], row["重量kg"], row["时长分钟"],
            row["RIR"], row["RPE"], row["主要部位"], row["次要部位"], row["备注"],
        ) for row in existing]
        if (
            actual_actions != expected_actions
            or any(
                row["日期"] != args.date
                or row["开始时间"] != args.start_time
                or row["训练类型"] != args.type
                or row["整节时长分钟"] != str(args.duration)
                or row["训练感受"] != args.feeling
                or row["疼痛信号"] != args.pain
                or row["是否额外运动"] != args.extra
                for row in existing
            )
        ):
            raise ValueError("相同训练ID已存在但训练内容不同；拒绝覆盖或重复同步")
    if not existing:
        for item in exercises:
            training_rows.append({
                "日期": args.date,
                "开始时间": args.start_time,
                "训练ID": session_id,
                "训练类型": args.type,
                "整节时长分钟": str(args.duration),
                "动作": item["name"],
                "组数": str(item.get("sets", "")),
                "次数": str(item.get("reps", "")),
                "重量kg": str(item.get("weight_kg", "")),
                "时长分钟": str(item.get("minutes", "")),
                "RIR": str(item.get("rir", "")),
                "RPE": str(item.get("rpe", args.rpe or "")),
                "训练感受": args.feeling,
                "主要部位": "、".join(item["primary"]),
                "次要部位": "、".join(item["secondary"]),
                "恢复反馈": "",
                "恢复反馈时间": "",
                "疼痛信号": args.pain,
                "是否额外运动": args.extra,
                "备注": str(item.get("notes", "")),
            })
        write_csv(args.training_csv, TRAINING_HEADERS, training_rows)
        verified = read_csv(args.training_csv, TRAINING_HEADERS)
        if len([row for row in verified if row["训练ID"] == session_id]) != len(exercises):
            raise ValueError("训练账本写入后回读不一致")
        created = True

    try:
        diet_rows = read_csv(args.diet_csv, DIET_HEADERS, allow_missing=True)
        tag = f"[training:{session_id}]"
        synced = any(tag in row["备注"] for row in diet_rows)
        if not synced:
            diet_rows.append(diet_summary_row(
                args.date, session_id, args.type, exercises, args.duration, args.rpe, args.extra, args.feeling,
            ))
            write_csv(args.diet_csv, DIET_HEADERS, diet_rows)
            verified_diet = read_csv(args.diet_csv, DIET_HEADERS)
            if sum(tag in row["备注"] for row in verified_diet) != 1:
                raise ValueError("饮食账本摘要写入后回读不一致")
    except (OSError, ValueError) as exc:
        return {
            "status": "partial",
            "session_id": session_id,
            "training_written": True,
            "diet_summary_written": False,
            "reason": str(exc),
            "retry": "使用相同训练ID重试；训练明细不会重复，只补饮食摘要。",
        }
    return {
        "status": "ok",
        "session_id": session_id,
        "training_written": True,
        "diet_summary_written": True,
        "created": created,
        "idempotent": not created,
    }


def session_groups(rows):
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["训练ID"]].append(row)
    return grouped


def parse_started(row):
    day = date.fromisoformat(row["日期"])
    try:
        clock = time.fromisoformat(row["开始时间"] or "12:00")
    except ValueError:
        clock = time(12, 0)
    return datetime.combine(day, clock)


def feedback_for_session(session_rows):
    for row in session_rows:
        if row["恢复反馈"].strip():
            try:
                value = json.loads(row["恢复反馈"])
                return value if isinstance(value, dict) else {}
            except json.JSONDecodeError:
                return {}
    return {}


def add_feedback(args):
    values = json.loads(args.feedback)
    if not isinstance(values, dict) or not values:
        raise ValueError("恢复反馈必须是非空 JSON 对象")
    for muscle, value in values.items():
        if muscle != "整体" and muscle not in MUSCLES:
            raise ValueError(f"未知反馈部位：{muscle}")
        if value not in FEEDBACK_VALUES:
            raise ValueError(f"恢复反馈应为：{'/'.join(FEEDBACK_VALUES)}")
    rows = read_csv(args.training_csv, TRAINING_HEADERS)
    indexes = [index for index, row in enumerate(rows) if row["训练ID"] == args.session_id]
    if not indexes:
        raise ValueError("没有找到训练ID")
    rows[indexes[0]]["恢复反馈"] = json.dumps(values, ensure_ascii=False, separators=(",", ":"))
    rows[indexes[0]]["恢复反馈时间"] = args.at
    write_csv(args.training_csv, TRAINING_HEADERS, rows)
    verified = read_csv(args.training_csv, TRAINING_HEADERS)
    stored = next(row for row in verified if row["训练ID"] == args.session_id)["恢复反馈"]
    if json.loads(stored) != values:
        raise ValueError("恢复反馈写入后回读不一致")
    return {"status": "ok", "session_id": args.session_id, "feedback": values}


def exercise_stimulus(row):
    primary = split_muscles(row["主要部位"])
    secondary = split_muscles(row["次要部位"])
    sets = number(row["组数"])
    minutes = number(row["时长分钟"])
    if sets is not None and sets > 0:
        base = sets
    elif minutes is not None and minutes > 0:
        base = max(0.5, minutes / 30.0)
    else:
        base = 1.0
    modifier = 1.0
    rir = number(row["RIR"])
    rpe = number(row["RPE"])
    if rir is not None:
        if rir <= 1:
            modifier *= 1.2
        elif rir >= 4:
            modifier *= 0.8
    elif rpe is not None:
        if rpe >= 9:
            modifier *= 1.2
        elif rpe <= 5:
            modifier *= 0.8
    values = defaultdict(float)
    for muscle in primary:
        values[muscle] += base * modifier
    for muscle in secondary:
        values[muscle] += base * modifier * 0.5
    return values


def window_hours(score, feeling):
    if score < 2:
        low, high = 24, 36
    elif score < 5:
        low, high = 36, 60
    elif score < 8:
        low, high = 48, 72
    else:
        low, high = 72, 96
    if feeling == "偏重":
        high += 12
    return low, high


def recovery_feedback_value(feedback, muscle, session_muscles):
    if muscle in feedback:
        return feedback[muscle]
    if "整体" in feedback and muscle in session_muscles:
        return feedback["整体"]
    return ""


def calibration_adjustment(rows, muscle, as_of):
    values = []
    for session_rows in session_groups(rows).values():
        if parse_started(session_rows[0]) > as_of:
            continue
        feedback = feedback_for_session(session_rows)
        session_muscles = set()
        for row in session_rows:
            session_muscles.update(split_muscles(row["主要部位"]))
            session_muscles.update(split_muscles(row["次要部位"]))
        value = recovery_feedback_value(feedback, muscle, session_muscles)
        if value:
            values.append(value)
    if len(values) < 3:
        return 0, "低"
    recent = values[-3:]
    if all(value == "正常" for value in recent):
        return -6, "中"
    if sum(value == "明显影响动作" for value in recent) >= 2:
        return 12, "中"
    return 0, "中"


def recovery_status(rows, as_of):
    events = []
    for session_id, session_rows in session_groups(rows).items():
        started = parse_started(session_rows[0])
        if started > as_of:
            continue
        scores = defaultdict(float)
        session_muscles = set()
        for row in session_rows:
            for muscle, score in exercise_stimulus(row).items():
                scores[muscle] += score
                session_muscles.add(muscle)
        events.append((started, session_id, session_rows, scores, session_muscles))
    events.sort(key=lambda item: item[0])
    latest = {}
    previous_high = {}
    for started, session_id, session_rows, scores, session_muscles in events:
        feeling = session_rows[0]["训练感受"]
        feedback = feedback_for_session(session_rows)
        pain_flag = any(row["疼痛信号"].strip() not in ("", "无", "否") for row in session_rows)
        for muscle, score in scores.items():
            low, high = window_hours(score, feeling)
            adjustment, confidence = calibration_adjustment(rows, muscle, as_of)
            low = max(12, low + adjustment)
            high = max(low + 12, high + adjustment)
            overlap = previous_high.get(muscle)
            if overlap and overlap > started:
                high += 12
            low_at = started + timedelta(hours=low)
            high_at = started + timedelta(hours=high)
            previous_high[muscle] = max(overlap or high_at, high_at)
            feedback_value = recovery_feedback_value(feedback, muscle, session_muscles)
            if pain_flag or feeling == "疼痛或异常" or feedback_value == "疼痛":
                state = "疼痛警示"
            elif feedback_value == "明显影响动作":
                state = "建议休息或改练"
            elif as_of >= high_at:
                state = "可正常训练"
            elif as_of >= low_at:
                state = "建议降量或先热身复查"
            else:
                state = "建议恢复或改练"
            latest[muscle] = {
                "muscle": muscle,
                "last_trained_at": started.isoformat(timespec="minutes"),
                "next_heavy_review_earliest": low_at.isoformat(timespec="minutes"),
                "next_heavy_review_latest": high_at.isoformat(timespec="minutes"),
                "state": state,
                "confidence": confidence,
                "feedback": feedback_value or "未反馈",
                "score_band": "轻" if score < 2 else "中" if score < 5 else "高" if score < 8 else "很高",
            }
    return {
        "status": "ok",
        "as_of": as_of.isoformat(timespec="minutes"),
        "model": MODEL_VERSION,
        "muscles": [latest[muscle] for muscle in MUSCLES if muscle in latest],
        "disclaimer": "这是下一次重训复查窗口和行动分档，不是肌肉恢复百分比或医学测量。",
    }


def period_scores(rows, start_day, end_day):
    scores = defaultdict(float)
    for row in rows:
        row_day = date.fromisoformat(row["日期"])
        if start_day <= row_day <= end_day:
            for muscle, score in exercise_stimulus(row).items():
                scores[muscle] += score
    return scores


def color_for_score(score):
    if score <= 0:
        return "#e8edf2"
    if score < 3:
        return "#a8d4f2"
    if score < 7:
        return "#3f98d7"
    return "#075fa8"


def level_for_score(score):
    if score <= 0:
        return "无"
    if score < 3:
        return "轻"
    if score < 7:
        return "中"
    return "高"


def anatomy_svg(scores, start_day, end_day):
    if not MUSCLE_TEMPLATE.exists():
        raise ValueError(f"人体图模板不存在：{MUSCLE_TEMPLATE}")
    svg = MUSCLE_TEMPLATE.read_text(encoding="utf-8")
    replacements = {
        "TITLE": "训练部位概览",
        "PERIOD": f"{start_day.isoformat()} 至 {end_day.isoformat()}",
    }
    for muscle, key in MUSCLE_KEYS.items():
        score = scores.get(muscle, 0)
        replacements[f"COLOR_{key}"] = color_for_score(score)
        replacements[f"SCORE_{key}"] = f"{score:.1f}"
        replacements[f"LEVEL_{key}"] = level_for_score(score)
    for key, value in replacements.items():
        svg = svg.replace("{{" + key + "}}", html.escape(value))
    unresolved = re.findall(r"{{[A-Z_]+}}", svg)
    if unresolved:
        raise ValueError(f"人体图模板存在未替换字段：{','.join(sorted(set(unresolved)))}")
    return svg


def anatomy_html(svg):
    return f'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>训练部位概览</title>
<style>
:root {{ color-scheme: light; --ink:#17212b; --muted:#687887; --paper:#f4f1ea; }}
* {{ box-sizing:border-box; }}
html,body {{ margin:0; min-height:100%; background:var(--paper); }}
body {{ padding:24px; font-family:"Songti SC","Noto Serif CJK SC","STSong",serif; color:var(--ink); }}
main {{ width:min(1180px,100%); margin:0 auto; }}
.report {{ overflow:hidden; background:#fff; border:1px solid #dce3e8; border-radius:24px; box-shadow:0 20px 60px rgba(35,51,65,.12); }}
.map {{ display:block; width:100%; height:auto; }}
.note {{ display:flex; justify-content:space-between; gap:24px; padding:15px 28px 20px; color:var(--muted); font:13px/1.6 "PingFang SC","Noto Sans CJK SC",sans-serif; border-top:1px solid #edf1f3; }}
.note a {{ color:#075fa8; text-decoration:none; border-bottom:1px solid #a8d4f2; }}
@media (max-width:720px) {{ body {{ padding:8px; }} .report {{ border-radius:14px; }} .note {{ display:block; padding:12px 16px 16px; }} }}
@media print {{ body {{ padding:0; background:#fff; }} .report {{ border:0; box-shadow:none; }} }}
</style>
</head>
<body>
<main>
  <article class="report" aria-label="训练部位概览">
    {svg}
    <footer class="note">
      <span>解剖方向与主要表面肌群位置参考 NIH/NCI SEER 与 OpenStax；本图为训练记录示意，不用于医学诊断。</span>
      <span><a href="https://training.seer.cancer.gov/anatomy/body/terminology.html">解剖方向</a> · <a href="https://openstax.org/books/anatomy-and-physiology-2e/pages/11-2-naming-skeletal-muscles">肌群概览</a></span>
    </footer>
  </article>
</main>
</body>
</html>'''


def render_anatomy(rows, start_day, end_day, output=None):
    scores = period_scores(rows, start_day, end_day)
    svg = anatomy_svg(scores, start_day, end_day)
    is_temporary = output is None
    if output is None:
        output = Path(tempfile.gettempdir()) / "diet-fat-loss-tracker" / "training-muscle-map.html"
    suffix = output.suffix.lower()
    if suffix not in (".html", ".svg"):
        raise ValueError("部位图输出仅支持 .html 或 .svg")
    content = anatomy_html(svg) if suffix == ".html" else svg
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")
    if output.read_text(encoding="utf-8") != content:
        raise ValueError("部位图写入后回读不一致")
    return {
        "status": "ok",
        "output": str(output),
        "format": suffix.removeprefix("."),
        "temporary": is_temporary,
        "storage": "系统临时目录；默认覆盖同名文件，不写入健康项目文件夹" if is_temporary else "用户指定路径",
        "scores": {muscle: round(scores.get(muscle, 0), 2) for muscle in MUSCLES},
    }


def training_config(profile_path):
    text = profile_path.read_text(encoding="utf-8")
    block = profile_section(text, "训练配置")
    if not block:
        raise ValueError("减脂档案缺少训练配置；请先运行 configure")
    return {label: profile_value(block, label) for label in (
        "主要目标", "训练经验", "器械条件", "单次可用时长", "可训练频率", "伤病与限制", "不喜欢动作",
    )}


def planned_session(rows, profile_path, available_minutes, as_of):
    config = training_config(profile_path)
    limits = config["伤病与限制"].strip()
    if limits not in ("", "无", "否", "没有"):
        return {
            "status": "needs_review",
            "reason": f"档案记录了伤病或动作限制：{limits}；本次不自动生成训练处方。",
            "schedule_rule": "先确认相关动作是否经专业评估可做，再继续滚动队列。",
        }
    strength_sessions = []
    cutoff = as_of.date() - timedelta(days=28)
    for session_id, session_rows in session_groups(rows).items():
        session_day = date.fromisoformat(session_rows[0]["日期"])
        if cutoff <= session_day <= as_of.date() and session_rows[0]["训练类型"] in ("力量", "混合"):
            strength_sessions.append((parse_started(session_rows[0]), session_id))
    pattern = "A" if len(strength_sessions) % 2 == 0 else "B"
    equipment = config["器械条件"]
    gym = any(word in equipment for word in ("健身房", "杠铃", "器械齐全"))
    bodyweight = any(word in equipment for word in ("无器械", "徒手"))
    if gym:
        template = GYM_A if pattern == "A" else GYM_B
    elif bodyweight:
        template = BODYWEIGHT_A if pattern == "A" else BODYWEIGHT_B
    else:
        template = HOME_A if pattern == "A" else HOME_B
    limit = 4 if available_minutes <= 30 else 5 if available_minutes <= 60 else 6
    status = recovery_status(rows, as_of)
    state_by_muscle = {item["muscle"]: item["state"] for item in status["muscles"]}
    selected = []
    skipped = []
    dislikes = set(split_muscles(config["不喜欢动作"]))
    goal = config["主要目标"]
    if "心肺" in goal and available_minutes <= 30:
        limit = 3
    for name, sets, reps, rir in template:
        primary = EXERCISES[name][0]
        blocked = [muscle for muscle in primary if state_by_muscle.get(muscle) in ("建议恢复或改练", "建议休息或改练", "疼痛警示")]
        if name in dislikes or blocked:
            skipped.append({"exercise": name, "reason": "不喜欢动作" if name in dislikes else f"相关部位未到重训窗口：{'、'.join(blocked)}"})
            continue
        is_cardio = name in ("快走", "跑步", "骑行", "动感单车", "椭圆机", "游泳")
        if is_cardio and "心肺" in goal:
            sets, reps, rir = "1", "20～40分钟", "RPE 4～6"
        elif not is_cardio and "力量" in goal:
            sets, reps, rir = "3～4", "4～8", "2～3"
        elif not is_cardio and "增肌" in goal:
            sets, reps, rir = "3～4", "6～15", "1～3"
        selected.append({"exercise": name, "sets": sets, "reps": reps, "target_rir": rir, "primary": list(primary)})
        if len(selected) >= limit:
            break
    if "心肺" in goal and not any(item["exercise"] in ("快走", "跑步", "骑行", "动感单车", "椭圆机", "游泳") for item in selected):
        cardio_name = "骑行" if gym else "快走"
        if len(selected) >= limit:
            selected[-1] = {"exercise": cardio_name, "sets": "1", "reps": "20～40分钟", "target_rir": "RPE 4～6", "primary": list(EXERCISES[cardio_name][0])}
        else:
            selected.append({"exercise": cardio_name, "sets": "1", "reps": "20～40分钟", "target_rir": "RPE 4～6", "primary": list(EXERCISES[cardio_name][0])})
    if len(selected) < 3:
        return {
            "status": "recovery_day",
            "date": as_of.date().isoformat(),
            "recommendation": "20～40 分钟低强度步行或休息；不强行安排力量训练。",
            "skipped": skipped,
            "schedule_rule": "滚动队列；不绑定固定星期或每周次数。",
        }
    return {
        "status": "ok",
        "date": as_of.date().isoformat(),
        "session": pattern,
        "goal": config["主要目标"],
        "available_minutes": available_minutes,
        "exercises": selected,
        "skipped": skipped,
        "schedule_rule": "滚动 A/B 队列；按实际可用时间继续下一节，不绑定固定星期或每周次数。",
        "nutrition_rule": "常规训练不重复增加摄入额度；只有明确超出常规的额外有氧才进入现有保守弹性规则。",
    }


def evaluate_session(rows, session_id, raw_plan):
    try:
        plan = json.loads(raw_plan)
    except json.JSONDecodeError as exc:
        raise ValueError(f"计划 JSON 无法解析：{exc.msg}") from exc
    if isinstance(plan, dict):
        plan = plan.get("exercises")
    if not isinstance(plan, list) or not plan:
        raise ValueError("计划 JSON 必须是动作数组或包含 exercises 的对象")
    actual_rows = [row for row in rows if row["训练ID"] == session_id]
    if not actual_rows:
        raise ValueError("没有找到训练ID")
    actual_by_name = {row["动作"]: row for row in actual_rows}
    pain = any(row["疼痛信号"].strip() not in ("", "无", "否") or row["训练感受"] == "疼痛或异常" for row in actual_rows)
    results = []
    achieved_count = 0
    for item in plan:
        name = str(item.get("exercise") or item.get("name") or "").strip()
        if not name:
            raise ValueError("计划动作缺少 exercise/name")
        actual = actual_by_name.get(name)
        if actual is None:
            results.append({"exercise": name, "result": "未完成", "adjustment": "下次先完成计划下限，不加量。"})
            continue
        planned_sets_low, _ = numeric_range(item.get("sets"))
        planned_reps_low, planned_reps_high = numeric_range(item.get("reps"))
        planned_rir_low, planned_rir_high = numeric_range(item.get("target_rir"))
        duration_based = "分钟" in str(item.get("reps", "")) or name in (
            "快走", "跑步", "骑行", "动感单车", "椭圆机", "游泳",
        )
        actual_sets = number(actual["组数"])
        actual_measure = actual["时长分钟"] if duration_based else actual["次数"]
        actual_reps_values = numeric_values(actual_measure)
        actual_reps_low = min(actual_reps_values) if actual_reps_values else None
        actual_reps_high = max(actual_reps_values) if actual_reps_values else None
        effort_is_rpe = "RPE" in str(item.get("target_rir", "")).upper()
        actual_rir = number(actual["RPE"] if effort_is_rpe else actual["RIR"])
        too_hard = (
            (not duration_based and planned_sets_low is not None and (actual_sets is None or actual_sets < planned_sets_low))
            or (planned_reps_low is not None and (actual_reps_low is None or actual_reps_low < planned_reps_low))
            or (planned_rir_low is not None and actual_rir is not None and actual_rir < planned_rir_low)
        )
        too_easy = (
            not too_hard
            and planned_reps_high is not None
            and actual_reps_high is not None
            and actual_reps_high > planned_reps_high
            and planned_rir_high is not None
            and actual_rir is not None
            and actual_rir >= planned_rir_high
        )
        if too_hard:
            result = "偏重或未达下限"
            adjustment = "下次只减少重量、组数或动作难度之一。"
        elif too_easy:
            result = "偏轻"
            adjustment = "下次只增加少量次数或重量之一。"
            achieved_count += 1
        else:
            result = "达标"
            adjustment = "下次保持；连续达标后再小幅渐进。"
            achieved_count += 1
        results.append({
            "exercise": name,
            "result": result,
            "actual_sets": actual["组数"] or ("不适用" if duration_based else "未知"),
            "actual_reps_or_minutes": actual_measure or "未知",
            "actual_rir_or_rpe": (actual["RPE"] if effort_is_rpe else actual["RIR"]) or "未知",
            "adjustment": adjustment,
        })
    completion = achieved_count / len(plan)
    if pain:
        overall = "疼痛或异常：停止渐进建议"
        next_action = "停止相关动作；必要时寻求专业评估。"
    elif completion >= 0.8:
        overall = "达到本次主要目标"
        next_action = "按各动作结果只调整一个变量；不要同时加重量和组数。"
    else:
        overall = "未达到本次主要目标"
        next_action = "下次优先完成计划下限，不补偿性加量。"
    return {
        "status": "ok",
        "session_id": session_id,
        "overall": overall,
        "planned_exercises": len(plan),
        "achieved_exercises": achieved_count,
        "completion_band": "至少80%" if completion >= 0.8 else "低于80%",
        "exercises": results,
        "next_action": next_action,
    }


def parse_datetime(value):
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("时间格式应为 YYYY-MM-DDTHH:MM") from exc


def default_paths():
    root = Path(__file__).resolve().parents[2]
    return root / "训练记录.csv", root / "饮食记录.csv", root / "减脂档案.md"


def parse_args():
    training_default, diet_default, profile_default = default_paths()
    parser = argparse.ArgumentParser(description="记录训练、同步饮食摘要、判断达标与恢复、生成滚动计划和解剖部位图。")
    subparsers = parser.add_subparsers(dest="command", required=True)

    configure = subparsers.add_parser("configure", help="创建或更新减脂档案中的训练配置。")
    configure.add_argument("--profile", type=Path, default=profile_default)
    configure.add_argument("--goal", required=True)
    configure.add_argument("--experience", required=True)
    configure.add_argument("--equipment", required=True)
    configure.add_argument("--minutes", required=True)
    configure.add_argument("--frequency", required=True)
    configure.add_argument("--limits", default="无")
    configure.add_argument("--dislikes", default="无")

    record = subparsers.add_parser("record", help="记录一节训练并幂等同步饮食摘要。")
    record.add_argument("--training-csv", type=Path, default=training_default)
    record.add_argument("--diet-csv", type=Path, default=diet_default)
    record.add_argument("--date", required=True)
    record.add_argument("--start-time", default="12:00")
    record.add_argument("--session-id")
    record.add_argument("--type", choices=("力量", "有氧", "混合"), required=True)
    record.add_argument("--duration", type=int, required=True)
    record.add_argument("--rpe", default="")
    record.add_argument("--feeling", choices=FEELINGS, required=True)
    record.add_argument("--extra", choices=("是", "否"), default="否")
    record.add_argument("--pain", default="无")
    record.add_argument("--exercises", required=True, help="JSON 动作数组。")

    feedback = subparsers.add_parser("feedback", help="按训练ID写入恢复反馈。")
    feedback.add_argument("--training-csv", type=Path, default=training_default)
    feedback.add_argument("--session-id", required=True)
    feedback.add_argument("--feedback", required=True, help='如 {"整体":"正常","股四头":"轻微疲劳"}')
    feedback.add_argument("--at", required=True, help="YYYY-MM-DDTHH:MM")

    status = subparsers.add_parser("status", help="输出各部位下一次重训复查窗口。")
    status.add_argument("--training-csv", type=Path, default=training_default)
    status.add_argument("--as-of", required=True, help="YYYY-MM-DDTHH:MM")

    render = subparsers.add_parser("render", help="生成确定性解剖训练部位图；默认输出临时 HTML。")
    render.add_argument("--training-csv", type=Path, default=training_default)
    render.add_argument("--start", required=True, help="YYYY-MM-DD")
    render.add_argument("--end", required=True, help="YYYY-MM-DD")
    render.add_argument("--output", type=Path, help="可选永久路径，仅支持 .html 或 .svg；省略则覆盖系统临时 HTML。")

    plan = subparsers.add_parser("plan", help="根据可用时间和恢复状态选择滚动队列下一节。")
    plan.add_argument("--training-csv", type=Path, default=training_default)
    plan.add_argument("--profile", type=Path, default=profile_default)
    plan.add_argument("--available-minutes", type=int, required=True)
    plan.add_argument("--as-of", required=True, help="YYYY-MM-DDTHH:MM")

    evaluate = subparsers.add_parser("evaluate", help="把已记录训练与原计划做确定性达标比较。")
    evaluate.add_argument("--training-csv", type=Path, default=training_default)
    evaluate.add_argument("--session-id", required=True)
    evaluate.add_argument("--plan", required=True, help="plan 命令输出或 exercises 数组 JSON。")
    return parser.parse_args()


def main():
    args = parse_args()
    try:
        if args.command == "configure":
            values = {
                "主要目标": args.goal,
                "训练经验": args.experience,
                "器械条件": args.equipment,
                "单次可用时长": args.minutes,
                "可训练频率": args.frequency,
                "伤病与限制": args.limits,
                "不喜欢动作": args.dislikes,
            }
            result = configure_profile(args.profile, values)
        elif args.command == "record":
            result = record_session(args)
        elif args.command == "feedback":
            parse_datetime(args.at)
            result = add_feedback(args)
        elif args.command == "status":
            rows = read_csv(args.training_csv, TRAINING_HEADERS, allow_missing=True)
            result = recovery_status(rows, parse_datetime(args.as_of))
        elif args.command == "render":
            rows = read_csv(args.training_csv, TRAINING_HEADERS, allow_missing=True)
            start_day, end_day = date.fromisoformat(args.start), date.fromisoformat(args.end)
            if end_day < start_day:
                raise ValueError("结束日期不能早于开始日期")
            result = render_anatomy(rows, start_day, end_day, args.output)
        elif args.command == "plan":
            rows = read_csv(args.training_csv, TRAINING_HEADERS, allow_missing=True)
            result = planned_session(rows, args.profile, args.available_minutes, parse_datetime(args.as_of))
        else:
            rows = read_csv(args.training_csv, TRAINING_HEADERS)
            result = evaluate_session(rows, args.session_id, args.plan)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result = {"status": "error", "reason": str(exc)}
    json_output(result)


if __name__ == "__main__":
    main()
