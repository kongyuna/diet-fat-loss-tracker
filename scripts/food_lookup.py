#!/usr/bin/env python3
"""Build and query a compact offline Chinese-language food macro reference."""

import argparse
import csv
import hashlib
import io
import json
import re
import urllib.request
import zipfile
from pathlib import Path


SOURCE_URL = "https://data.fda.gov.tw/opendata/exportDataList.do?InfoId=20&logType=2&method=ExportData"
DEFAULT_DATA = Path(__file__).resolve().parents[1] / "assets" / "food-data" / "tw_food_macros.csv"
WANTED = {
    "熱量": "energy_kcal",
    "粗蛋白": "protein_g",
    "粗脂肪": "fat_g",
    "總碳水化合物": "carb_g",
}
TRADITIONAL_TO_SIMPLIFIED = str.maketrans({
    "魚": "鱼", "雞": "鸡", "鴨": "鸭", "鵝": "鹅", "豬": "猪", "麵": "面",
    "飯": "饭", "粥": "粥", "餅": "饼", "餃": "饺", "燒": "烧", "烤": "烤",
    "滷": "卤", "醬": "酱", "湯": "汤", "乾": "干", "鮮": "鲜", "凍": "冻",
    "葉": "叶", "蘿": "萝", "蔔": "卜", "馬": "马", "龍": "龙", "鳳": "凤",
    "黃": "黄", "綠": "绿", "紅": "红", "黑": "黑", "白": "白", "薑": "姜",
    "蔥": "葱", "蒜": "蒜", "頭": "头", "條": "条", "塊": "块", "絲": "丝",
    "罐": "罐", "發": "发", "奶": "奶", "貝": "贝", "蝦": "虾", "蟹": "蟹",
    "鮭": "鲑", "鯖": "鲭", "鱈": "鳕", "鯛": "鲷", "鯉": "鲤", "鰻": "鳗",
})


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def normalize_text(value):
    text = str(value or "").translate(TRADITIONAL_TO_SIMPLIFIED).lower()
    return re.sub(r"[\s\-—_()（）\[\]【】,，、/]+", "", text)


def download_source():
    request = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "diet-fat-loss-tracker/2.1"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def source_rows(zip_bytes):
    archive = zipfile.ZipFile(io.BytesIO(zip_bytes))
    names = archive.namelist()
    if len(names) != 1 or not names[0].lower().endswith(".csv"):
        raise ValueError("开放数据压缩包结构不符合预期")
    handle = io.TextIOWrapper(archive.open(names[0]), encoding="utf-8-sig", newline="")
    return csv.DictReader(handle)


def normalize_rows(rows):
    foods = {}
    for row in rows:
        nutrient = row.get("分析項", "").strip()
        if nutrient not in WANTED:
            continue
        food_id = row.get("整合編號", "").strip()
        if not food_id:
            continue
        item = foods.setdefault(food_id, {
            "id": food_id,
            "food_name": row.get("樣品名稱", "").strip(),
            "aliases": row.get("俗名", "").strip(),
            "category": row.get("食品分類", "").strip(),
            "energy_kcal": "",
            "protein_g": "",
            "fat_g": "",
            "carb_g": "",
        })
        value = row.get("每100克含量", "").strip()
        if value:
            try:
                item[WANTED[nutrient]] = f"{float(value):g}"
            except ValueError:
                pass
    return [foods[key] for key in sorted(foods)]


def write_dataset(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ("id", "food_name", "aliases", "category", "energy_kcal", "protein_g", "fat_g", "carb_g")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def build_dataset(path):
    source = download_source()
    rows = normalize_rows(source_rows(source))
    if len(rows) < 2000:
        raise ValueError("规范化后食物条目少于2000，疑似上游结构变化")
    write_dataset(path, rows)
    output = path.read_bytes()
    if len(output) >= 100 * 1024 * 1024:
        raise ValueError("本地数据超过100MiB")
    return {
        "status": "ok",
        "rows": len(rows),
        "output": str(path),
        "bytes": len(output),
        "source_sha256": sha256_bytes(source),
        "output_sha256": sha256_bytes(output),
    }


def read_dataset(path):
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    expected = ["id", "food_name", "aliases", "category", "energy_kcal", "protein_g", "fat_g", "carb_g"]
    if not rows or list(rows[0]) != expected:
        raise ValueError("本地食物数据表头无效")
    return rows


def lookup(path, query, limit=10):
    needle = normalize_text(query)
    if not needle:
        raise ValueError("查询词不能为空")
    matches = []
    for row in read_dataset(path):
        names = [row["food_name"], *re.split(r"[,，、;/；]", row["aliases"])]
        normalized = [normalize_text(name) for name in names if name.strip()]
        exact = any(name == needle for name in normalized)
        partial = any(needle in name or name in needle for name in normalized)
        if exact or partial:
            matches.append((0 if exact else 1, row))
    matches.sort(key=lambda item: (item[0], len(item[1]["food_name"]), item[1]["id"]))
    selected = [item[1] for item in matches[:limit]]
    if not selected:
        status = "not_found"
    elif len(matches) == 1 and matches[0][0] == 0:
        status = "ok"
    else:
        status = "ambiguous"
    return {
        "status": status,
        "query": query,
        "source_region": "台湾地区",
        "basis": "每100克可食部；仅作中文食物离线参考，不能代替包装标签或实际称重",
        "matches": selected,
    }


def parse_args():
    parser = argparse.ArgumentParser(description="构建或查询离线中文食物宏量营养参考。")
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build")
    build.add_argument("--output", type=Path, default=DEFAULT_DATA)
    query = subparsers.add_parser("lookup")
    query.add_argument("food")
    query.add_argument("--data", type=Path, default=DEFAULT_DATA)
    query.add_argument("--limit", type=int, default=10)
    return parser.parse_args()


def main():
    args = parse_args()
    try:
        if args.command == "build":
            result = build_dataset(args.output)
        else:
            result = lookup(args.data, args.food, limit=max(1, min(args.limit, 20)))
    except (OSError, ValueError, urllib.error.URLError, zipfile.BadZipFile) as exc:
        result = {"status": "error", "reason": str(exc)}
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
