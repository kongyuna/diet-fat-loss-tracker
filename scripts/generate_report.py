#!/usr/bin/env python3
"""Generate deterministic offline weekly or monthly diet reports."""

import argparse
import calendar
import csv
import html
import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import mean

from weight_forecast import monthly_evaluation, parse_profile as parse_forecast_profile


EXPECTED_HEADERS = [
    "日期", "餐次", "食物", "估算份量", "热量下限", "热量上限", "采用热量",
    "蛋白质下限", "蛋白质上限", "采用蛋白质", "碳水下限", "碳水上限",
    "采用碳水", "脂肪下限", "脂肪上限", "采用脂肪", "可信度", "运动项目", "运动时长分钟", "运动强度",
    "是否额外运动", "备注",
]
METRICS = {
    "热量": ("采用热量", "千卡"),
    "蛋白质": ("采用蛋白质", "克"),
    "碳水": ("采用碳水", "克"),
}


def parse_args():
    project_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(
        description="从饮食记录 CSV 和减脂档案生成固定结构的离线 HTML 周报或月报。"
    )
    parser.add_argument("period", choices=("week", "month"))
    parser.add_argument("--date", default=date.today().isoformat(), help="统计截止日 YYYY-MM-DD")
    parser.add_argument("--csv", dest="csv_path", type=Path, default=project_root / "饮食记录.csv")
    parser.add_argument("--profile", type=Path, default=project_root / "减脂档案.md")
    parser.add_argument("--output-dir", type=Path, default=project_root / "报告")
    return parser.parse_args()


def number(value):
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def fmt(value, digits=0):
    if value is None:
        return "—"
    if digits == 0 or float(value).is_integer():
        return f"{value:.0f}"
    return f"{value:.{digits}f}"


def section(text, heading):
    match = re.search(
        rf"^##\s+{re.escape(heading)}\s*$([\s\S]*?)(?=^##\s+|\Z)",
        text,
        flags=re.MULTILINE,
    )
    return match.group(1) if match else ""


def bullet_value(block, label):
    match = re.search(rf"^-\s*{re.escape(label)}\s*[：:]\s*(.+?)\s*$", block, re.MULTILINE)
    return match.group(1).strip() if match else ""


def target_range(value):
    match = re.search(r"(-?\d+(?:\.\d+)?)\s*[~～]\s*(-?\d+(?:\.\d+)?)", value)
    if match:
        low, high = float(match.group(1)), float(match.group(2))
        return (min(low, high), max(low, high))
    single = number(re.search(r"-?\d+(?:\.\d+)?", value).group(0)) if re.search(r"-?\d+(?:\.\d+)?", value) else None
    return (single, single) if single is not None else (None, None)


def parse_profile(path):
    text = path.read_text(encoding="utf-8")
    basics = section(text, "基础资料")
    current = section(text, "当前目标")
    monthly = section(text, "月度记录")
    targets = {
        name: target_range(bullet_value(current, name))
        for name in METRICS
    }
    target_weight = number(bullet_value(basics, "目标体重").replace("kg", ""))
    weights = []
    table_lines = [line.strip() for line in monthly.splitlines() if line.strip().startswith("|")]
    headers = [cell.strip() for cell in table_lines[0].strip("|").split("|")] if table_lines else []
    for line in table_lines[1:]:
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) != len(headers) or all(re.fullmatch(r":?-+:?", cell) for cell in cells):
            continue
        row = dict(zip(headers, cells))
        month = row.get("月份", "")
        weight = number(re.sub(r"[^\d.\-]", "", row.get("体重", "")))
        if re.fullmatch(r"\d{4}-\d{2}", month) and weight is not None:
            weights.append((month, weight))
    weights.sort(key=lambda item: item[0])
    return {"targets": targets, "target_weight": target_weight, "weights": weights}


def read_rows(path):
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        try:
            headers = next(reader)
        except StopIteration:
            raise ValueError("CSV 为空")
        if headers != EXPECTED_HEADERS:
            raise ValueError("CSV 表头与 V2/V3 约定不一致")
        rows = []
        for line_number, values in enumerate(reader, start=2):
            if len(values) != len(headers):
                raise ValueError(
                    f"CSV 第 {line_number} 行有 {len(values)} 列，应为 {len(headers)} 列；请先修复列错位"
                )
            rows.append(dict(zip(headers, values)))
        return rows


def period_info(period, as_of):
    if period == "week":
        start = as_of - timedelta(days=as_of.weekday())
        calendar_end = start + timedelta(days=6)
        iso_year, iso_week, _ = as_of.isocalendar()
        filename = f"{iso_year}-W{iso_week:02d}.html"
        title = f"{iso_year}年第{iso_week}周"
        eyebrow = "WEEKLY PULSE"
    else:
        start = as_of.replace(day=1)
        calendar_end = as_of.replace(day=calendar.monthrange(as_of.year, as_of.month)[1])
        filename = f"{as_of.year}-{as_of.month:02d}.html"
        title = f"{as_of.year}年{as_of.month}月"
        eyebrow = "MONTHLY REVIEW"
    observed_end = min(as_of, calendar_end)
    return {
        "start": start,
        "calendar_end": calendar_end,
        "end": observed_end,
        "filename": filename,
        "title": title,
        "eyebrow": eyebrow,
    }


def dates_between(start, end):
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def aggregate(rows, days):
    allowed = {day.isoformat() for day in days}
    food_by_day = defaultdict(list)
    exercise_rows = []
    for row in rows:
        if row["日期"] not in allowed:
            continue
        if row["食物"].strip():
            food_by_day[row["日期"]].append(row)
        if row["运动项目"].strip():
            exercise_rows.append(row)

    daily = []
    for day in days:
        food_rows = food_by_day.get(day.isoformat(), [])
        entry = {"date": day, "recorded": bool(food_rows)}
        for metric, (field, _) in METRICS.items():
            values = [number(row[field]) for row in food_rows]
            entry[metric] = sum(values) if values and all(value is not None for value in values) else None
        daily.append(entry)

    exercise_minutes = sum(number(row["运动时长分钟"]) or 0 for row in exercise_rows)
    extra_exercise = sum(1 for row in exercise_rows if row["是否额外运动"].strip() in ("是", "yes", "Yes", "Y", "1"))
    return daily, {
        "sessions": len(exercise_rows),
        "minutes": exercise_minutes,
        "extra": extra_exercise,
    }


def in_target(value, band):
    low, high = band
    if value is None or low is None or high is None:
        return None
    return low <= value <= high


def metric_stats(daily, targets):
    stats = {}
    for metric in METRICS:
        values = [item[metric] for item in daily if item[metric] is not None]
        hits = [in_target(value, targets[metric]) for value in values]
        stats[metric] = {
            "values": values,
            "average": mean(values) if values else None,
            "calculable": len(values),
            "hits": sum(1 for hit in hits if hit is True),
        }
    return stats


def relevant_weights(weights, period_end):
    end_month = period_end.strftime("%Y-%m")
    eligible = [item for item in weights if item[0] <= end_month]
    if not eligible:
        return None, None, None
    initial = weights[0]
    latest = eligible[-1]
    previous = eligible[-2] if len(eligible) >= 2 else None
    return initial, latest, previous


def progress_data(profile, period_end):
    initial, latest, previous = relevant_weights(profile["weights"], period_end)
    target = profile["target_weight"]
    progress = None
    if initial and latest and target is not None and initial[1] != target:
        progress = (initial[1] - latest[1]) / (initial[1] - target) * 100
        progress = max(0, min(100, progress))
    return {
        "initial": initial,
        "latest": latest,
        "previous": previous,
        "target": target,
        "progress": progress,
    }


def target_text(band, unit):
    low, high = band
    if low is None:
        return "目标缺失"
    if low == high:
        return f"目标 {fmt(low)} {unit}"
    return f"目标 {fmt(low)}–{fmt(high)} {unit}"


def kpi_card(label, value, meta, accent="coral"):
    return f"""
        <article class="kpi {accent}">
          <p>{html.escape(label)}</p>
          <strong>{html.escape(value)}</strong>
          <span>{html.escape(meta)}</span>
        </article>"""


def bar_chart(title, items, band, unit):
    numeric = [value for _, value in items if value is not None]
    if not numeric:
        return f'<section class="panel"><h2>{html.escape(title)}</h2><p class="empty">该周期没有可计算数据。</p></section>'
    high_target = band[1] or 0
    scale = max(max(numeric), high_target) * 1.16 or 1
    low_position = max(0, min(100, (band[0] or 0) / scale * 100))
    high_position = max(low_position, min(100, (band[1] or band[0] or 0) / scale * 100))
    band_html = ""
    if band[0] is not None:
        band_html = (
            f'<div class="target-band" style="bottom:{low_position:.2f}%;height:{max(2, high_position-low_position):.2f}%">'
            '<span>目标区间</span></div>'
        )
    bars = []
    for label, value in items:
        if value is None:
            bars.append(f'<div class="bar-wrap"><div class="bar missing"></div><small>{html.escape(label)}</small></div>')
        else:
            height = max(3, value / scale * 100)
            bars.append(
                f'<div class="bar-wrap" title="{html.escape(label)} · {fmt(value, 1)} {html.escape(unit)}">'
                f'<div class="bar" style="height:{height:.2f}%"><span>{fmt(value)}</span></div>'
                f'<small>{html.escape(label)}</small></div>'
            )
    return f"""
      <section class="panel chart-panel">
        <div class="panel-head"><h2>{html.escape(title)}</h2><p>{html.escape(target_text(band, unit))}</p></div>
        <div class="chart"><div class="grid-lines"></div>{band_html}<div class="bars">{''.join(bars)}</div></div>
      </section>"""


def week_buckets(daily, metric):
    buckets = defaultdict(list)
    for item in daily:
        if item[metric] is not None:
            iso_year, iso_week, _ = item["date"].isocalendar()
            buckets[(iso_year, iso_week)].append(item[metric])
    return [(f"W{week:02d}", mean(values)) for (_, week), values in sorted(buckets.items())]


def heatmap(daily, targets):
    rows = []
    for metric in METRICS:
        cells = []
        for item in daily:
            value = item[metric]
            if value is None:
                status, title = "missing", "无数据"
            else:
                low, high = targets[metric]
                if low is None:
                    status, title = "missing", "目标缺失"
                elif value < low:
                    status, title = "low", f"{fmt(value)} · 偏低"
                elif value > high:
                    status, title = "high", f"{fmt(value)} · 偏高"
                else:
                    status, title = "hit", f"{fmt(value)} · 达标"
            cells.append(
                f'<span class="heat {status}" title="{item["date"].isoformat()} · {html.escape(title)}"></span>'
            )
        rows.append(f'<div class="heat-row"><b>{metric}</b><div class="heat-cells">{"".join(cells)}</div></div>')
    day_labels = "".join(f"<span>{item['date'].day}</span>" for item in daily)
    return f"""
      <section class="panel heatmap-panel">
        <div class="panel-head"><h2>每日达标热力图</h2><p>绿色达标，橙色偏离，灰色缺失</p></div>
        <div class="heat-row labels"><b>日期</b><div class="heat-cells">{day_labels}</div></div>
        {''.join(rows)}
      </section>"""


def conclusion(period, daily, stats):
    recorded = sum(1 for item in daily if item["recorded"])
    coverage = recorded / len(daily) if daily else 0
    insufficient = recorded < 5 if period == "week" else coverage < 0.60
    if insufficient:
        return "当前证据不足，先提高记录连续性。", "下个周期优先保证每天留下饮食记录。"
    protein = stats["蛋白质"]
    calorie = stats["热量"]
    protein_rate = protein["hits"] / protein["calculable"] if protein["calculable"] else 0
    calorie_rate = calorie["hits"] / calorie["calculable"] if calorie["calculable"] else 0
    if protein_rate < 0.60:
        return "记录已经足够判断，当前最明显的问题是蛋白质达标率偏低。", "下个周期优先在一餐增加一份明确的高蛋白食物。"
    if calorie_rate < 0.60:
        return "记录已经足够判断，当前最明显的问题是每日热量波动较大。", "下个周期优先让每日热量回到目标区间。"
    return "记录连续且主要指标总体稳定，当前执行节奏可继续。", "下个周期保持当前饮食结构和记录频率。"


def weight_panel(progress, period, report_month):
    initial = progress["initial"]
    latest = progress["latest"]
    target = progress["target"]
    percent = progress["progress"]
    degree = (percent or 0) * 3.6
    if initial and latest and target is not None:
        facts = (
            f'<span>初始 <b>{fmt(initial[1], 1)}kg</b></span>'
            f'<span>最新 <b>{fmt(latest[1], 1)}kg</b></span>'
            f'<span>目标 <b>{fmt(target, 1)}kg</b></span>'
        )
        freshness = f"最新体重记录于 {latest[0]}"
    else:
        facts = "<span>体重数据不足</span>"
        freshness = "无法计算减重进度"
    monthly_change = ""
    if period == "month":
        latest, previous = progress["latest"], progress["previous"]
        if latest and previous and latest[0] == report_month:
            delta = latest[1] - previous[1]
            monthly_change = f'<p class="monthly-change">本月体重变化 <strong>{delta:+.1f}kg</strong></p>'
        else:
            monthly_change = '<p class="monthly-change">本月体重变化 <strong>证据不足</strong></p>'
    return f"""
      <section class="progress-card">
        <div class="progress-ring" style="--degree:{degree:.1f}deg"><strong>{fmt(percent)}%</strong><span>目标进度</span></div>
        <div class="progress-copy"><p class="eyebrow">WEIGHT JOURNEY</p><h2>减重进度</h2><div class="weight-facts">{facts}</div><p>{html.escape(freshness)}</p>{monthly_change}</div>
      </section>"""


def calibration_panel(evaluation):
    if not evaluation or evaluation.get("status") != "ok":
        reason = evaluation.get("reason", "缺少相邻月度体重或完整饮食记录") if evaluation else "没有可用评估"
        return f"""
      <section class="panel comparison-panel">
        <div class="panel-head"><h2>预测 vs 实测</h2><p>月度模型复核</p></div>
        <div class="comparison-grid"><article><span>模型预测</span><strong>证据不足</strong></article><article><span>实际变化</span><strong>证据不足</strong></article><article><span>校准状态</span><strong>未校准</strong></article></div>
        <p class="comparison-note">{html.escape(reason)}</p>
      </section>"""
    calibration = evaluation["calibration"]
    adjustment = calibration["recommended_adjustment_kcal"]
    status = f"建议 {adjustment:+d} kcal/日" if calibration["applied"] else "未校准"
    return f"""
      <section class="panel comparison-panel">
        <div class="panel-head"><h2>预测 vs 实测</h2><p>{html.escape(evaluation['period']['start'])} — {html.escape(evaluation['period']['end'])}</p></div>
        <div class="comparison-grid">
          <article><span>模型预测</span><strong>{evaluation['predicted_change_kg']:+.2f} kg</strong></article>
          <article><span>实际变化</span><strong>{evaluation['actual_change_kg']:+.2f} kg</strong></article>
          <article><span>预测误差</span><strong>{evaluation['prediction_error_kg']:+.2f} kg</strong></article>
          <article><span>校准状态</span><strong>{html.escape(status)}</strong></article>
        </div>
        <p class="comparison-note">完整记录 {evaluation['complete_days']} 天 · 覆盖率 {evaluation['coverage'] * 100:.0f}% · {html.escape(calibration['reason'])}</p>
      </section>"""


def render_report(period, info, profile, daily, exercise, monthly_evaluation_result=None):
    stats = metric_stats(daily, profile["targets"])
    recorded = sum(1 for item in daily if item["recorded"])
    missing_dates = [f"{item['date'].month}/{item['date'].day}" for item in daily if not item["recorded"]]
    progress = progress_data(profile, info["end"])
    conclusion_text, action_text = conclusion(period, daily, stats)

    cards = [
        kpi_card("记录覆盖", f"{recorded} / {len(daily)} 天", "仅表示当天存在饮食记录", "ink"),
    ]
    accents = {"热量": "coral", "蛋白质": "teal", "碳水": "gold"}
    for metric, (_, unit) in METRICS.items():
        stat = stats[metric]
        cards.append(kpi_card(
            f"日均{metric}",
            f"{fmt(stat['average'])} {unit}" if stat["average"] is not None else "数据不足",
            f"达标 {stat['hits']} 天 · 可计算 {stat['calculable']} 天",
            accents[metric],
        ))

    if period == "week":
        chart_items = {
            metric: [(f"{item['date'].month}/{item['date'].day}", item[metric]) for item in daily]
            for metric in ("热量", "蛋白质")
        }
        charts = (
            bar_chart("每日热量", chart_items["热量"], profile["targets"]["热量"], "千卡")
            + bar_chart("每日蛋白质", chart_items["蛋白质"], profile["targets"]["蛋白质"], "克")
        )
        period_note = "自然周 · 截至统计日"
    else:
        charts = (
            '<div class="section-title"><p class="eyebrow">WEEKLY AVERAGES</p><h2>周均趋势</h2></div>'
            + bar_chart("周均热量", week_buckets(daily, "热量"), profile["targets"]["热量"], "千卡")
            + bar_chart("周均蛋白质", week_buckets(daily, "蛋白质"), profile["targets"]["蛋白质"], "克")
            + heatmap(daily, profile["targets"])
        )
        period_note = "自然月 · 截至统计日"

    comparison = calibration_panel(monthly_evaluation_result) if period == "month" else ""

    missing_text = "、".join(missing_dates) if missing_dates else "无"
    calculable_text = "；".join(
        f"{metric}可计算 {stats[metric]['calculable']} / {recorded} 天"
        for metric in METRICS
    )
    exercise_weekly = exercise["sessions"] / max(1, len(daily) / 7)
    report_month = info["start"].strftime("%Y-%m")

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(info['title'])} · 减脂进度报告</title>
  <style>
    :root {{ --paper:#f4efe5; --card:#fffdf8; --ink:#18332f; --muted:#6f7d76; --line:#d9d2c5; --coral:#ef6b52; --teal:#2f8f83; --gold:#d5a238; --shadow:0 18px 50px rgba(47,61,54,.10); }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; color:var(--ink); background:var(--paper); font-family:"Avenir Next","PingFang SC","Microsoft YaHei",sans-serif; }}
    body::before {{ content:""; position:fixed; inset:0; pointer-events:none; opacity:.28; background-image:radial-gradient(#b8a98e .55px,transparent .55px); background-size:7px 7px; }}
    main {{ position:relative; width:min(1160px,calc(100% - 32px)); margin:0 auto; padding:44px 0 72px; }}
    .hero {{ display:grid; grid-template-columns:1.6fr .8fr; gap:24px; align-items:end; margin-bottom:24px; }}
    h1,h2 {{ font-family:"Iowan Old Style","Songti SC","STSong",serif; margin:0; letter-spacing:-.025em; }}
    h1 {{ font-size:clamp(42px,7vw,82px); line-height:.98; max-width:760px; }}
    h2 {{ font-size:28px; }}
    p {{ margin:0; }}
    .eyebrow {{ color:var(--coral); font-size:12px; font-weight:800; letter-spacing:.18em; text-transform:uppercase; margin-bottom:10px; }}
    .date-range {{ color:var(--muted); margin-top:18px; font-size:15px; }}
    .stamp {{ border:1px solid var(--ink); border-radius:50%; aspect-ratio:1; display:grid; place-items:center; text-align:center; justify-self:end; width:min(190px,100%); transform:rotate(4deg); background:rgba(255,253,248,.45); }}
    .stamp b {{ display:block; font-family:"Iowan Old Style","Songti SC",serif; font-size:28px; }}
    .stamp span {{ font-size:12px; letter-spacing:.12em; }}
    .progress-card,.panel,.kpi,.summary,.data-note {{ background:var(--card); border:1px solid rgba(24,51,47,.10); box-shadow:var(--shadow); }}
    .progress-card {{ border-radius:28px; padding:28px; display:grid; grid-template-columns:180px 1fr; gap:30px; align-items:center; margin-bottom:18px; }}
    .progress-ring {{ width:164px; aspect-ratio:1; border-radius:50%; display:grid; place-content:center; text-align:center; background:radial-gradient(circle at center,var(--card) 57%,transparent 58%),conic-gradient(var(--coral) var(--degree),#e7dfd2 0); }}
    .progress-ring strong {{ font-family:"Iowan Old Style","Songti SC",serif; font-size:42px; line-height:1; }}
    .progress-ring span {{ color:var(--muted); font-size:12px; margin-top:7px; }}
    .weight-facts {{ display:flex; flex-wrap:wrap; gap:18px; margin:18px 0 12px; }}
    .weight-facts span,.progress-copy>p:last-child,.monthly-change {{ color:var(--muted); }}
    .weight-facts b,.monthly-change strong {{ color:var(--ink); }}
    .monthly-change {{ margin-top:10px; }}
    .kpi-grid {{ display:grid; grid-template-columns:repeat(4,1fr); gap:14px; margin:18px 0 34px; }}
    .kpi {{ border-radius:20px; padding:20px; border-top:4px solid var(--accent); }}
    .kpi.coral {{ --accent:var(--coral); }} .kpi.teal {{ --accent:var(--teal); }} .kpi.gold {{ --accent:var(--gold); }} .kpi.ink {{ --accent:var(--ink); }}
    .kpi p {{ color:var(--muted); font-size:13px; }} .kpi strong {{ display:block; font-size:27px; margin:9px 0 5px; }} .kpi span {{ color:var(--muted); font-size:12px; }}
    .section-title {{ margin:38px 0 16px; }}
    .panel {{ border-radius:24px; padding:24px; margin-bottom:18px; overflow:hidden; }}
    .panel-head {{ display:flex; justify-content:space-between; gap:18px; align-items:baseline; margin-bottom:20px; }} .panel-head p {{ color:var(--muted); font-size:13px; }}
    .chart {{ height:245px; position:relative; padding:24px 2px 0; }}
    .grid-lines {{ position:absolute; inset:24px 0 28px; background:repeating-linear-gradient(to bottom,transparent 0,transparent calc(25% - 1px),rgba(24,51,47,.08) 25%); }}
    .target-band {{ position:absolute; left:0; right:0; background:rgba(47,143,131,.11); border-top:1px dashed rgba(47,143,131,.55); border-bottom:1px dashed rgba(47,143,131,.55); }}
    .target-band span {{ position:absolute; right:6px; top:-19px; color:var(--teal); font-size:10px; }}
    .bars {{ position:absolute; inset:24px 8px 0; display:grid; grid-auto-flow:column; grid-auto-columns:minmax(12px,1fr); align-items:end; gap:7px; }}
    .bar-wrap {{ height:100%; display:flex; flex-direction:column; justify-content:flex-end; align-items:center; min-width:0; }}
    .bar {{ position:relative; width:min(34px,82%); min-height:3px; border-radius:8px 8px 2px 2px; background:linear-gradient(180deg,var(--coral),#d95442); }}
    .bar span {{ position:absolute; left:50%; top:-18px; transform:translateX(-50%); font-size:9px; color:var(--muted); white-space:nowrap; }}
    .bar.missing {{ height:3px; background:#c9c2b7; }} .bar-wrap small {{ height:24px; padding-top:7px; font-size:9px; color:var(--muted); white-space:nowrap; }}
    .heatmap-panel {{ overflow-x:auto; }} .heat-row {{ display:grid; grid-template-columns:58px minmax(540px,1fr); gap:10px; align-items:center; margin:8px 0; }}
    .heat-row b {{ font-size:12px; }} .heat-cells {{ display:grid; grid-auto-flow:column; grid-auto-columns:1fr; gap:3px; }}
    .heat {{ height:22px; border-radius:5px; background:#d5cec2; }} .heat.hit {{ background:var(--teal); }} .heat.low {{ background:#e7b657; }} .heat.high {{ background:var(--coral); }}
    .heat-row.labels span {{ color:var(--muted); font-size:8px; text-align:center; }}
    .summary {{ border-radius:28px; padding:30px; display:grid; grid-template-columns:1fr 1fr; gap:30px; margin-top:26px; }}
    .summary article:first-child {{ border-right:1px solid var(--line); padding-right:30px; }} .summary p:last-child {{ margin-top:10px; line-height:1.65; color:var(--muted); }}
    .exercise-line {{ display:flex; gap:22px; flex-wrap:wrap; margin-top:14px; }} .exercise-line b {{ font-size:24px; }}
    .data-note {{ border-radius:18px; margin-top:18px; padding:20px 24px; box-shadow:none; background:rgba(255,253,248,.55); }} .data-note h2 {{ font-size:20px; }} .data-note ul {{ margin:12px 0 0; padding-left:18px; color:var(--muted); line-height:1.7; font-size:13px; }}
    .comparison-grid {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; }} .comparison-grid article {{ padding:16px; border-radius:16px; background:#f4efe5; }} .comparison-grid span {{ display:block; color:var(--muted); font-size:12px; }} .comparison-grid strong {{ display:block; margin-top:8px; font-size:21px; }} .comparison-note {{ color:var(--muted); font-size:13px; margin-top:16px; line-height:1.6; }}
    .empty {{ color:var(--muted); padding:36px 0; }}
    footer {{ color:var(--muted); font-size:11px; margin-top:24px; text-align:right; }}
    @media (max-width:760px) {{ main {{ width:min(100% - 20px,680px); padding-top:24px; }} .hero {{ grid-template-columns:1fr auto; }} .stamp {{ width:100px; }} .stamp b {{ font-size:18px; }} .progress-card {{ grid-template-columns:1fr; text-align:center; gap:18px; padding:20px; }} .progress-ring {{ width:104px; margin:auto; }} .progress-ring strong {{ font-size:28px; }} .weight-facts {{ justify-content:center; }} .kpi-grid,.comparison-grid {{ grid-template-columns:1fr 1fr; }} .summary {{ grid-template-columns:1fr; }} .summary article:first-child {{ border-right:0; border-bottom:1px solid var(--line); padding:0 0 24px; }} .panel {{ padding:18px 14px; }} .panel-head {{ display:block; }} .panel-head p {{ margin-top:6px; }} }}
    @media (max-width:430px) {{ h1 {{ font-size:42px; }} .hero {{ grid-template-columns:1fr; }} .stamp {{ display:none; }} .progress-card {{ grid-template-columns:1fr; text-align:center; }} .progress-ring {{ margin:auto; }} .weight-facts {{ justify-content:center; }} .kpi-grid {{ grid-template-columns:1fr 1fr; gap:8px; }} .kpi {{ padding:15px 12px; }} .kpi strong {{ font-size:21px; }} }}
  </style>
</head>
<body>
  <main>
    <header class="hero">
      <div><p class="eyebrow">{info['eyebrow']}</p><h1>{html.escape(info['title'])}<br>减脂进度报告</h1><p class="date-range">{info['start'].strftime('%Y.%m.%d')} — {info['end'].strftime('%Y.%m.%d')} · {period_note}</p></div>
      <div class="stamp"><div><span>DATA SNAPSHOT</span><b>{recorded}/{len(daily)}</b><span>有记录天数</span></div></div>
    </header>
    {weight_panel(progress, period, report_month)}
    <section class="kpi-grid">{''.join(cards)}</section>
    {charts}
    {comparison}
    <section class="summary">
      <article><p class="eyebrow">ONE CLEAR SIGNAL</p><h2>本期判断</h2><p>{html.escape(conclusion_text)}</p></article>
      <article><p class="eyebrow">NEXT MOVE</p><h2>下一步</h2><p>{html.escape(action_text)}</p></article>
    </section>
    <section class="panel">
      <div class="panel-head"><h2>运动记录</h2><p>只统计 CSV 中主动记录的运动</p></div>
      <div class="exercise-line"><span><b>{exercise['sessions']}</b> 次</span><span><b>{fmt(exercise['minutes'])}</b> 分钟</span><span><b>{exercise['extra']}</b> 次额外有氧</span><span><b>{exercise_weekly:.1f}</b> 次/周</span></div>
    </section>
    <section class="data-note">
      <h2>数据说明</h2>
      <ul>
        <li>缺失日期：{html.escape(missing_text)}</li>
        <li>{html.escape(calculable_text)}</li>
        <li>有记录天数只表示当天存在饮食记录，不代表三餐完整。</li>
        <li>{html.escape('最新体重记录于 ' + progress['latest'][0] if progress['latest'] else '没有可用体重记录')}；未记录时不推断体重变化。</li>
        <li>食物图片、烹调油和酱汁仍可能带来估算误差。</li>
      </ul>
    </section>
    <footer>由 diet-fat-loss-tracker V4 离线生成 · {datetime.now().strftime('%Y-%m-%d %H:%M')}</footer>
  </main>
</body>
</html>
"""


def main():
    args = parse_args()
    try:
        as_of = date.fromisoformat(args.date)
    except ValueError as exc:
        raise SystemExit(f"日期格式错误：{exc}")
    try:
        rows = read_rows(args.csv_path)
        profile = parse_profile(args.profile)
        forecast_profile = parse_forecast_profile(args.profile)
        info = period_info(args.period, as_of)
        days = dates_between(info["start"], info["end"])
        daily, exercise = aggregate(rows, days)
        month_result = monthly_evaluation(forecast_profile, rows, info["start"].strftime("%Y-%m")) if args.period == "month" else None
        output = render_report(args.period, info, profile, daily, exercise, month_result)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        output_path = args.output_dir / info["filename"]
        output_path.write_text(output, encoding="utf-8")
        verified = output_path.read_text(encoding="utf-8")
        required = ('name="viewport"', "减重进度", "数据说明", info["title"])
        if any(marker not in verified for marker in required) or "http://" in verified or "https://" in verified:
            raise ValueError("生成文件回读校验失败")
    except (OSError, ValueError) as exc:
        raise SystemExit(f"生成失败：{exc}")
    print(output_path.resolve())


if __name__ == "__main__":
    main()
