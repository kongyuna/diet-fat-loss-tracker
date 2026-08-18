#!/usr/bin/env python3
"""Render deterministic fixed-capacity progress bars for daily nutrition totals."""

import argparse
import json
import math
from decimal import Decimal, ROUND_HALF_UP


TOTAL_CELLS = 40
MAX_PERCENT = 150.0
FILLED = "█"
EMPTY = "░"
OVERFLOW = "▣"


def number(value, field):
    if isinstance(value, bool):
        raise ValueError(f"{field}必须是数字")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field}必须是数字") from exc
    if not math.isfinite(result):
        raise ValueError(f"{field}必须是有限数字")
    return result


def round_half_up(value):
    return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def format_number(value):
    return f"{value:g}"


def format_percent(value):
    rounded = round(value, 1)
    return f"{rounded:g}%"


def render_item(item):
    label = str(item.get("label", "")).strip()
    unit = str(item.get("unit", "")).strip()
    if not label:
        raise ValueError("label不能为空")
    current = number(item.get("current"), "current")
    target = number(item.get("target"), "target")
    if current < 0:
        raise ValueError("current不能小于0")
    if target <= 0:
        raise ValueError("target必须大于0")

    ratio = current / target
    percent = ratio * 100
    base_cells = min(TOTAL_CELLS, round_half_up(min(ratio, 1.0) * TOTAL_CELLS))
    if ratio < 1:
        base_cells = min(TOTAL_CELLS - 1, base_cells)
    empty_cells = TOTAL_CELLS - base_cells
    overflow_cells = 0
    if ratio > 1:
        overflow_ratio = min(ratio, MAX_PERCENT / 100) - 1
        overflow_cells = max(1, round_half_up(overflow_ratio * TOTAL_CELLS))

    bar = FILLED * base_cells + EMPTY * empty_cells + OVERFLOW * overflow_cells
    display_percent = f">{MAX_PERCENT:g}%" if percent > MAX_PERCENT else format_percent(percent)
    suffix = f" {unit}" if unit else ""
    header = (
        f"{label}  {format_number(current)} / {format_number(target)}{suffix}  "
        f"{display_percent}"
    )
    return {
        "label": label,
        "current": current,
        "target": target,
        "unit": unit,
        "percent": round(percent, 1),
        "display_percent": display_percent,
        "base_cells": base_cells,
        "empty_cells": empty_cells,
        "overflow_cells": overflow_cells,
        "bar": bar,
        "text": f"{header}\n{bar}",
    }


def render(items):
    if not isinstance(items, list) or not items:
        raise ValueError("items必须是非空数组")
    rendered = [render_item(item) for item in items]
    return {
        "status": "ok",
        "scale": {"full_cells": TOTAL_CELLS, "cell_percent": 2.5, "cap_percent": MAX_PERCENT},
        "items": rendered,
        "text": "\n".join(item["text"] for item in rendered),
    }


def parse_args():
    parser = argparse.ArgumentParser(description="生成固定40格的营养目标进度条JSON。")
    parser.add_argument(
        "--items-json",
        required=True,
        help='JSON数组，例如[{"label":"热量","current":400,"target":2000,"unit":"kcal"}]',
    )
    return parser.parse_args()


def main():
    args = parse_args()
    try:
        result = render(json.loads(args.items_json))
    except (json.JSONDecodeError, ValueError) as exc:
        result = {"status": "error", "reason": str(exc)}
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
