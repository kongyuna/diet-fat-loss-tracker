#!/usr/bin/env python3
"""Deterministic short-term energy-equivalent and monthly calibration helper."""

import argparse
import csv
import json
import re
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from statistics import mean


MODEL_VERSION = "forbes-hall-v1"
FAT_DENSITY = 9400.0
FFM_DENSITY = 1800.0
FORBES_CONSTANT = 10.4
BODY_FAT_SEE = 4.1
TDEE_WEIGHT_SLOPE = 23.9
EXPECTED_HEADERS = [
    "日期", "餐次", "食物", "估算份量", "热量下限", "热量上限", "采用热量",
    "蛋白质下限", "蛋白质上限", "采用蛋白质", "碳水下限", "碳水上限",
    "采用碳水", "可信度", "运动项目", "运动时长分钟", "运动强度",
    "是否额外运动", "备注",
]


def number(value):
    if value is None or str(value).strip() == "":
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", str(value))
    return float(match.group(0)) if match else None


def section(text, heading):
    match = re.search(
        rf"^[ \t]*##[ \t]+{re.escape(heading)}[ \t]*$([\s\S]*?)(?=^[ \t]*##[ \t]+|\Z)",
        text,
        flags=re.MULTILINE,
    )
    return match.group(1) if match else ""


def bullet_value(block, label):
    match = re.search(
        rf"^[ \t]*-[ \t]*{re.escape(label)}[ \t]*[：:][ \t]*([^\r\n]*)$",
        block,
        re.MULTILINE,
    )
    return match.group(1).strip() if match else ""


def read_rows(path):
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != EXPECTED_HEADERS:
            raise ValueError("CSV 表头与 V2/V3/V4 约定不一致")
        rows = []
        for line_number, row in enumerate(reader, start=2):
            if None in row:
                raise ValueError(f"CSV 第 {line_number} 行列数错误")
            rows.append(row)
    return rows


def parse_table(block):
    lines = [line.strip() for line in block.splitlines() if line.strip().startswith("|")]
    if not lines:
        return []
    headers = [cell.strip() for cell in lines[0].strip("|").split("|")]
    records = []
    for line in lines[1:]:
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if all(re.fullmatch(r":?-+:?", cell) for cell in cells):
            continue
        if len(cells) == len(headers):
            records.append(dict(zip(headers, cells)))
    return records


def parse_profile(path):
    text = path.read_text(encoding="utf-8")
    basics = section(text, "基础资料")
    current = section(text, "当前目标")
    monthly = parse_table(section(text, "月度记录"))
    records = []
    for row in monthly:
        month = row.get("月份", "")
        weigh_date = row.get("称重日期", "")
        weight = number(row.get("体重"))
        if not re.fullmatch(r"\d{4}-\d{2}", month) or weight is None:
            continue
        records.append({"month": month, "date": weigh_date, "weight": weight})
    records.sort(key=lambda item: item["month"])
    return {
        "formula_sex": bullet_value(basics, "用于公式的性别"),
        "age": number(bullet_value(basics, "年龄")),
        "height_cm": number(bullet_value(basics, "身高")),
        "weight": number(bullet_value(current, "当前体重")),
        "maintenance": number(bullet_value(current, "估算维持热量")),
        "calibration": number(bullet_value(current, "维持热量校准修正")) or 0.0,
        "model": bullet_value(current, "体重预测模型") or MODEL_VERSION,
        "monthly": records,
    }


def body_fat_percent(weight, height_cm, age, formula_sex):
    if not all(value is not None for value in (weight, height_cm, age)):
        raise ValueError("缺少体重、身高或年龄")
    sex = str(formula_sex).strip().lower()
    if sex in ("男", "男性", "male", "m", "1"):
        sex_code = 1
    elif sex in ("女", "女性", "female", "f", "0"):
        sex_code = 0
    else:
        raise ValueError("用于公式的性别无法识别")
    bmi = weight / ((height_cm / 100.0) ** 2)
    estimate = 1.20 * bmi + 0.23 * age - 10.8 * sex_code - 5.4
    return max(5.0, min(60.0, estimate))


def energy_equivalent(energy_balance_kcal, weight, height_cm, age, formula_sex, bf_percent=None):
    """Return one-day tissue-energy equivalent; not a scale-weight prediction."""
    bf = body_fat_percent(weight, height_cm, age, formula_sex) if bf_percent is None else bf_percent
    bf = max(5.0, min(60.0, bf))
    fat_mass = max(1.0, weight * bf / 100.0)
    c_energy = FORBES_CONSTANT * FFM_DENSITY / FAT_DENSITY
    p_energy = c_energy / (c_energy + fat_mass)
    kg_per_kcal = (1.0 - p_energy) / FAT_DENSITY + p_energy / FFM_DENSITY
    kcal_per_kg = 1.0 / kg_per_kcal
    return {
        "kg": energy_balance_kcal * kg_per_kcal,
        "kcal_per_kg": kcal_per_kg,
        "estimated_body_fat_percent": bf,
    }


def extra_exercise_allowance(rows, day_text):
    minutes = 0.0
    for row in rows:
        if row["日期"] != day_text or row["是否额外运动"].strip().lower() not in ("是", "yes", "y", "1"):
            continue
        minutes += number(row["运动时长分钟"]) or 0.0
    if minutes < 30:
        return 0
    if minutes <= 60:
        return 100
    if minutes <= 90:
        return 200
    return 300


def food_totals(rows, day_text):
    food_rows = [row for row in rows if row["日期"] == day_text and row["食物"].strip()]
    if not food_rows:
        return None, "当天没有饮食记录"
    fields = ("热量下限", "热量上限", "采用热量")
    totals = {}
    for field in fields:
        values = [number(row[field]) for row in food_rows]
        if any(value is None for value in values):
            return None, f"当天存在缺失的{field}"
        totals[field] = sum(values)
    return totals, ""


def daily_forecast(profile, rows, day_text):
    required = (profile["maintenance"], profile["weight"], profile["height_cm"], profile["age"])
    if profile["maintenance"] is None:
        return {"status": "insufficient", "reason": "减脂档案缺少估算维持热量"}
    if any(value is None for value in required[1:]) or not profile["formula_sex"]:
        return {"status": "insufficient", "reason": "减脂档案缺少体重、身高、年龄或公式性别"}
    totals, reason = food_totals(rows, day_text)
    if totals is None:
        return {"status": "insufficient", "reason": reason}
    extra = extra_exercise_allowance(rows, day_text)
    adjusted_maintenance = profile["maintenance"] + profile["calibration"] + extra
    balances = {
        "low": totals["热量下限"] - adjusted_maintenance,
        "point": totals["采用热量"] - adjusted_maintenance,
        "high": totals["热量上限"] - adjusted_maintenance,
    }
    bf = body_fat_percent(profile["weight"], profile["height_cm"], profile["age"], profile["formula_sex"])
    candidates = []
    for balance in (balances["low"], balances["high"]):
        for bf_value in (bf - BODY_FAT_SEE, bf + BODY_FAT_SEE):
            candidates.append(energy_equivalent(
                balance, profile["weight"], profile["height_cm"], profile["age"],
                profile["formula_sex"], bf_percent=bf_value,
            )["kg"])
    point = energy_equivalent(
        balances["point"], profile["weight"], profile["height_cm"], profile["age"], profile["formula_sex"]
    )
    if point["kg"] < -0.0005:
        direction = "理论减重"
    elif point["kg"] > 0.0005:
        direction = "理论增重"
    else:
        direction = "接近平衡"
    return {
        "status": "ok",
        "date": day_text,
        "condition": "若今天此后不再进食",
        "model": MODEL_VERSION,
        "intake_kcal": {
            "low": round(totals["热量下限"]),
            "point": round(totals["采用热量"]),
            "high": round(totals["热量上限"]),
        },
        "effective_maintenance_kcal": round(adjusted_maintenance),
        "extra_exercise_kcal": extra,
        "energy_balance_kcal": {key: round(value) for key, value in balances.items()},
        "weight_change_kg": {
            "low": round(min(candidates), 3),
            "point": round(point["kg"], 3),
            "high": round(max(candidates), 3),
        },
        "direction": direction,
        "confidence": "低",
        "disclaimer": "理论单日组织能量等价，不等于明早秤重；水分、糖原、盐分和胃内容物可造成更大波动。",
    }


def is_complete_day(day_rows):
    meals = {row["餐次"].strip() for row in day_rows if row["食物"].strip() and number(row["采用热量"]) is not None}
    return all(any(required in meal for meal in meals) for required in ("早餐", "午餐", "晚餐"))


def simulate_change(days, average_intake, average_extra, profile, starting_weight):
    weight = starting_weight
    baseline_weight = starting_weight
    base_maintenance = profile["maintenance"] + profile["calibration"]
    for _ in range(days):
        adaptive_maintenance = base_maintenance + TDEE_WEIGHT_SLOPE * (weight - baseline_weight)
        energy_balance = average_intake - adaptive_maintenance - average_extra
        weight += energy_equivalent(
            energy_balance, weight, profile["height_cm"], profile["age"], profile["formula_sex"]
        )["kg"]
    return weight - starting_weight


def monthly_evaluation(profile, rows, month_text):
    records = [item for item in profile["monthly"] if item["month"] <= month_text]
    if len(records) < 2 or records[-1]["month"] != month_text:
        return {"status": "insufficient", "reason": "缺少当前月及上一期月度体重"}
    previous, current = records[-2], records[-1]
    try:
        start = date.fromisoformat(previous["date"])
        end = date.fromisoformat(current["date"])
    except (TypeError, ValueError):
        return {"status": "insufficient", "reason": "相邻月度体重缺少准确称重日期"}
    interval_days = (end - start).days
    if interval_days <= 0:
        return {"status": "insufficient", "reason": "称重日期顺序无效"}
    if profile["maintenance"] is None:
        return {"status": "insufficient", "reason": "减脂档案缺少估算维持热量"}
    by_day = defaultdict(list)
    for row in rows:
        try:
            row_date = date.fromisoformat(row["日期"])
        except ValueError:
            continue
        if start <= row_date < end:
            by_day[row["日期"]].append(row)
    complete = []
    for offset in range(interval_days):
        day_text = (start + timedelta(days=offset)).isoformat()
        day_rows = by_day.get(day_text, [])
        if is_complete_day(day_rows):
            intake = sum(number(row["采用热量"]) for row in day_rows if row["食物"].strip())
            complete.append((day_text, intake, extra_exercise_allowance(rows, day_text)))
    complete_days = len(complete)
    coverage = complete_days / interval_days
    if not complete:
        return {"status": "insufficient", "reason": "相邻称重期间没有完整饮食记录日"}
    average_intake = mean(item[1] for item in complete)
    average_extra = mean(item[2] for item in complete)
    predicted = simulate_change(interval_days, average_intake, average_extra, profile, previous["weight"])
    actual = current["weight"] - previous["weight"]
    error = predicted - actual
    density = energy_equivalent(
        -500, previous["weight"], profile["height_cm"], profile["age"], profile["formula_sex"]
    )["kcal_per_kg"]
    raw_adjustment = error * density / interval_days
    enough = complete_days >= 20 and coverage >= 0.70
    recommended = max(-100, min(100, round(raw_adjustment * 0.25))) if enough else 0
    reason = "覆盖达标，采用25%平滑并限制单月±100千卡/日" if enough else "完整记录覆盖不足20天或70%，只比较不校准"
    return {
        "status": "ok",
        "model": MODEL_VERSION,
        "period": {"start": start.isoformat(), "end": end.isoformat(), "days": interval_days},
        "complete_days": complete_days,
        "coverage": round(coverage, 3),
        "average_intake_kcal": round(average_intake),
        "predicted_change_kg": round(predicted, 2),
        "actual_change_kg": round(actual, 2),
        "prediction_error_kg": round(error, 2),
        "calibration": {
            "applied": enough,
            "recommended_adjustment_kcal": recommended,
            "recommended_total_correction_kcal": round(profile["calibration"] + recommended),
            "reason": reason,
        },
        "notes": [
            "缺失日以完整记录日的平均摄入外推，仅在覆盖达标时用于校准。",
            "实测误差可能来自水分、盐和碳水、称重条件、漏记及维持热量估算。",
        ],
    }


def parse_args():
    project_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="输出单日条件性体重变化或月度预测校准 JSON。")
    parser.add_argument("mode", choices=("daily", "month"))
    parser.add_argument("value", help="daily 用 YYYY-MM-DD；month 用 YYYY-MM")
    parser.add_argument("--csv", dest="csv_path", type=Path, default=project_root / "饮食记录.csv")
    parser.add_argument("--profile", type=Path, default=project_root / "减脂档案.md")
    return parser.parse_args()


def main():
    args = parse_args()
    try:
        profile = parse_profile(args.profile)
        rows = read_rows(args.csv_path)
        if args.mode == "daily":
            date.fromisoformat(args.value)
            result = daily_forecast(profile, rows, args.value)
        else:
            if not re.fullmatch(r"\d{4}-\d{2}", args.value):
                raise ValueError("月份格式应为 YYYY-MM")
            result = monthly_evaluation(profile, rows, args.value)
    except (OSError, ValueError) as exc:
        result = {"status": "error", "reason": str(exc)}
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
