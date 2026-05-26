#!/usr/bin/env python3
"""
价格核查辅助脚本
==================
从 speaker-monitor.html 提取 PRICES 数组，输出结构化 JSON，
供自动化流程使用。

自动化流程：
  1. 运行此脚本 → 输出 price_snapshot.json
  2. 自动化读取快照，逐产品 WebSearch 查最新价格
  3. 对比偏差，更新 HTML 中的 promo 字段

用法：
  python price_checker.py [--output price_snapshot.json]
"""

import re
import json
import sys
from pathlib import Path

HTML_FILE = Path(__file__).parent / "speaker-monitor.html"


def parse_prices(filepath):
    """从 HTML 解析 PRICES 数组 → 产品列表"""
    with open(filepath, "r", encoding="utf-8") as f:
        html = f.read()

    prices_section = re.search(r"const PRICES = \[(.*?)\];", html, re.DOTALL)
    if not prices_section:
        print("[ERROR] 未找到 PRICES 数组", file=sys.stderr)
        return []

    products = []
    entries = re.finditer(
        r"\{\s*brand:\s*'([^']+)',\s*model:\s*'([^']+)',"
        r"\s*orig:\s*(\d+),\s*promo:\s*(\d+),"
        r"\s*category:\s*'([^']+)',"
        r"\s*platform:\s*'([^']*)',"
        r"\s*img:\s*'([^']*)',"
        r"\s*link:\s*'([^']*)'\s*\}",
        prices_section.group(1),
    )

    for m in entries:
        products.append(
            {
                "brand": m.group(1),
                "model": m.group(2),
                "orig": int(m.group(3)),
                "promo": int(m.group(4)),
                "category": m.group(5),
                "platform": m.group(6),
                "link": m.group(8),
                "search_query": f"{m.group(1)} {m.group(2)} 京东 价格 2026",
            }
        )

    return products


def update_promo(filepath, brand, model, new_promo):
    """更新单个产品的 promo 价格"""
    with open(filepath, "r", encoding="utf-8") as f:
        html = f.read()

    pattern = (
        rf"(brand:\s*'{re.escape(brand)}',\s*"
        rf"model:\s*'{re.escape(model)}',\s*"
        rf"orig:\s*\d+,\s*promo:\s*)\d+(\s*,)"
    )
    replacement = rf"\g<1>{new_promo}\g<2>"

    new_html, count = re.subn(pattern, replacement, html)
    if count > 0:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(new_html)
        return True
    return False


# ============================================================
# CLI
# ============================================================
if __name__ == "__main__":
    output_file = "price_snapshot.json"
    for i, arg in enumerate(sys.argv):
        if arg == "--output" and i + 1 < len(sys.argv):
            output_file = sys.argv[i + 1]

    products = parse_prices(HTML_FILE)

    snapshot = {
        "generated_at": __import__("time").strftime("%Y-%m-%d %H:%M:%S"),
        "total": len(products),
        "products": products,
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)

    print(f"✓ 已导出 {len(products)} 款产品 → {output_file}")

    # 打印摘要表
    print(f"\n{'品牌':<10} {'型号':<22} {'原价':>6} {'促销价':>6} {'品类':<8}")
    print("-" * 58)
    for p in products:
        print(
            f"{p['brand']:<10} {p['model']:<22} "
            f"¥{p['orig']:<5} ¥{p['promo']:<5} {p['category']:<8}"
        )
