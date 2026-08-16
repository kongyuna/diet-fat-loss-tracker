#!/usr/bin/env python3
"""Deterministic calorie-target planner with Chinese-adult formula comparison."""

import argparse
import json
from datetime import date, timedelta

from weight_forecast import energy_equivalent


ACTIVITY_FACTORS = {
    "久坐": 1.20,
    "轻活动": 1.35,
    "中活动": 1.50,
    "高活动": 1.70,
}
CALORIE_FLOORS = {"male": 1500, "female": 1200}


def normalize_sex(value):
    text = str(value).strip().lower()
    if text in ("男", "男性", "male", "m", "1"):
        return "male"
    if text in ("女", "女性", "female", "f", "0"):
        return "female"
    raise ValueError("用于公式的性别应为男或女")


def round_to_50(value):
    return int(round(value / 50.0) * 50)


def rmr_estimates(sex, age, height_cm, weight_kg):
    male = sex == "male"
    mifflin = 10 * weight_kg + 6.25 * height_cm - 5 * age + (5 if male else -161)

    if age < 30:
        schofield = (15.057 * weight_kg + 692.2) if male else (14.818 * weight_kg + 486.6)
    elif age < 60:
        schofield = (11.472 * weight_kg + 873.1) if male else (8.126 * weight_kg + 845.6)
    else:
        schofield = (11.711 * weight_kg + 587.7) if male else (9.082 * weight_kg + 658.5)

    liu = 13.88 * weight_kg + 4.16 * height_cm - 3.43 * age - (0 if male else 112.4)
    xue1 = 13.9 * weight_kg + (247 if male else 0) - 5.39 * age + 855
    return {
        "schofield": round(schofield),
        "mifflin_st_jeor": round(mifflin),
        "liu": round(liu),
        "xue1": round(xue1),
    }


def validate_inputs(age, height_cm, current_weight, target_weight):
    if age < 18:
        raise ValueError("仅支持18岁以上普通成年人")
    if not 120 <= height_cm <= 230:
        raise ValueError("身高超出一般成人支持范围")
    if not 30 <= current_weight <= 350 or not 30 <= target_weight <= 350:
        raise ValueError("体重超出一般成人支持范围")
    if target_weight >= current_weight:
        raise ValueError("当前规划器只处理减脂目标，目标体重应低于当前体重")
    target_bmi = target_weight / ((height_cm / 100.0) ** 2)
    if target_bmi < 18.5:
        raise ValueError("目标体重对应BMI低于18.5，不自动建立减脂目标")


def plan_target(
    sex_value,
    age,
    height_cm,
    current_weight,
    target_weight,
    activity,
    target_date=None,
    as_of=None,
):
    sex = normalize_sex(sex_value)
    validate_inputs(age, height_cm, current_weight, target_weight)
    if activity not in ACTIVITY_FACTORS:
        raise ValueError("活动水平应为久坐、轻活动、中活动或高活动")

    today = as_of or date.today()
    if isinstance(today, str):
        today = date.fromisoformat(today)
    deadline = date.fromisoformat(target_date) if isinstance(target_date, str) else target_date
    if deadline is not None and deadline <= today:
        raise ValueError("目标日期必须晚于测算日期")

    estimates = rmr_estimates(sex, age, height_cm, current_weight)
    values = list(estimates.values())
    spread = (max(values) - min(values)) / estimates["schofield"]
    factor = ACTIVITY_FACTORS[activity]
    maintenance_point = estimates["schofield"] * factor
    maintenance_low = min(values) * factor
    maintenance_high = max(values) * factor
    floor = CALORIE_FLOORS[sex]

    standard_calories = max(floor, round_to_50(maintenance_point * 0.85))
    conservative_calories = max(floor, round_to_50(maintenance_point * 0.90))
    fast_calories = max(floor, round_to_50(maintenance_point * 0.80))

    def weekly_change(calories):
        daily_balance = calories - maintenance_point
        change = energy_equivalent(
            daily_balance,
            current_weight,
            height_cm,
            age,
            "男" if sex == "male" else "女",
        )["kg"]
        return abs(change * 7)

    weekly_standard = weekly_change(standard_calories)
    weekly_fast = weekly_change(fast_calories)
    gap = current_weight - target_weight
    estimated_weeks = gap / weekly_standard if weekly_standard > 0 else None
    estimated_date = today + timedelta(days=round(estimated_weeks * 7)) if estimated_weeks else None

    feasibility = "可采用推荐值"
    required_weekly = None
    reasons = []
    if deadline is not None:
        weeks = (deadline - today).days / 7
        required_weekly = gap / weeks
        upper_pace = min(1.0, current_weight * 0.01)
        if required_weekly > upper_pace or required_weekly > weekly_fast * 1.10:
            feasibility = "需要调整目标体重或日期"
            reasons.append("目标期限要求的下降速度超过当前自动规划边界")
    if fast_calories == floor and maintenance_point * 0.80 < floor:
        reasons.append("20%缺口会触及现役热量下限")
    if spread > 0.10:
        reasons.append("四种静息代谢公式差异超过10%，初始值不确定性较高")
    if age >= 60:
        reasons.append("60岁以上个体差异较大，不自动给激进期限")

    confidence = "低" if spread > 0.10 or age >= 60 else "中"
    return {
        "status": "ok",
        "as_of": today.isoformat(),
        "population": "18岁以上、无需疾病营养管理的普通成年人",
        "rmr_kcal": estimates,
        "adopted_rmr": {
            "formula": "schofield",
            "kcal": estimates["schofield"],
            "reason": "中国大陆成人研究中既有公式表现相对最好；仍保留其他公式作为不确定性边界",
        },
        "formula_spread_percent": round(spread * 100, 1),
        "activity": {"level": activity, "factor": factor},
        "maintenance_kcal": {
            "low": round_to_50(maintenance_low),
            "point": round_to_50(maintenance_point),
            "high": round_to_50(maintenance_high),
        },
        "recommended_calories_kcal": standard_calories,
        "alternatives_kcal": {
            "more_conservative": conservative_calories,
            "faster_boundary": fast_calories,
        },
        "estimated_weekly_change_kg": round(weekly_standard, 2),
        "estimated_target_date": estimated_date.isoformat() if estimated_date else None,
        "requested_target_date": deadline.isoformat() if deadline else None,
        "required_weekly_change_kg": round(required_weekly, 2) if required_weekly is not None else None,
        "feasibility": feasibility,
        "confidence": confidence,
        "reasons": reasons,
        "choices": ["采用推荐值", "更保守一些", "修改目标体重或日期"],
        "calibration": "这是初始估算；优先用连续14天记录观察，达到月度覆盖门槛后再校准维持热量。",
    }


def parse_args():
    parser = argparse.ArgumentParser(description="比较多种静息代谢公式并输出减脂热量目标JSON。")
    parser.add_argument("--sex", required=True, help="男或女")
    parser.add_argument("--age", required=True, type=int)
    parser.add_argument("--height-cm", required=True, type=float)
    parser.add_argument("--current-weight", required=True, type=float)
    parser.add_argument("--target-weight", required=True, type=float)
    parser.add_argument("--activity", required=True, choices=tuple(ACTIVITY_FACTORS))
    parser.add_argument("--target-date")
    parser.add_argument("--as-of")
    return parser.parse_args()


def main():
    args = parse_args()
    try:
        result = plan_target(
            args.sex,
            args.age,
            args.height_cm,
            args.current_weight,
            args.target_weight,
            args.activity,
            target_date=args.target_date,
            as_of=args.as_of,
        )
    except (ValueError, OverflowError) as exc:
        result = {"status": "error", "reason": str(exc)}
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
