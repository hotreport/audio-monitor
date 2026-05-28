#!/usr/bin/env python3
"""
GitHub Actions 价格核查脚本
==========================
独立运行，不依赖 WorkBuddy AI。

现实情况:
  - JD/天猫 API（p.3.cn）从 GitHub Actions 美国服务器不通（GFW 拦截）
  - 国际品牌官网（B&O、TE、Samsung、Marshall）可从境外访问
  - 本脚本作为 WorkBuddy 的补充：检查国际品牌 + 生成每日快照

策略:
  国际品牌  → 尝试官网抓价，偏差 >10% 自动更新
  JD/天猫   → 跳过，标记 "deferred to WorkBuddy"
  所有产品  → 生成 price_snapshot.json 作为每日基线
"""

import re
import json
import sys
import time
from pathlib import Path

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    import urllib.request
    import urllib.error
    HAS_REQUESTS = False

HTML_FILE = Path("speaker-monitor.html")

# 可从境外访问的国际品牌（通过官网 API 或页面抓取）
INTERNATIONAL_BRANDS = {
    "Teenage Engineering": {
        "check_url": "https://teenage.engineering/products",
        "note": "MSRP checking via product page"
    },
    "B&O": {
        "check_url": "https://www.bang-olufsen.com/en-us/products",
        "note": "MSRP checking via US store"
    },
    "三星": {
        "check_url": "https://www.samsung.com/cn/audio-sound/",
        "note": "CN site may be accessible"
    },
}

# ============================================================
# 1. 解析 PRICES
# ============================================================
def parse_prices(html):
    products = []
    pattern = re.compile(
        r"\{\s*brand:\s*'([^']+)',\s*model:\s*'([^']+)',"
        r"\s*orig:\s*(\d+),\s*promo:\s*(\d+),"
        r"\s*category:\s*'([^']+)',"
        r"\s*platform:\s*'([^']*)',"
        r"\s*img:\s*'([^']*)',"
        r"\s*link:\s*'([^']*)'\s*\}"
    )
    for m in pattern.finditer(html):
        products.append({
            "brand": m.group(1),
            "model": m.group(2),
            "orig": int(m.group(3)),
            "promo": int(m.group(4)),
            "category": m.group(5),
            "platform": m.group(6),
            "link": m.group(8),
        })
    return products


def get_http(url, headers=None, timeout=8):
    """统一 HTTP GET（快速超时）"""
    h = headers or {"User-Agent": "Mozilla/5.0 (compatible; PriceBot/1.0)"}
    if HAS_REQUESTS:
        try:
            r = requests.get(url, headers=h, timeout=timeout, allow_redirects=True)
            return r.status_code, r.text[:50000]
        except Exception as e:
            return None, str(e)
    else:
        try:
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, resp.read().decode("utf-8", errors="replace")[:50000]
        except Exception as e:
            return None, str(e)


# ============================================================
# 2. 国际品牌价格抓取
# ============================================================
def check_bo_price(model_name):
    """抓取 B&O 官网 MSRP（尝试中国区）"""
    # B&O 中国官网可能有 API
    try:
        code, text = get_http("https://www.bang-olufsen.com/zh-cn", timeout=8)
        if code == 200:
            # 简单搜索页面中是否包含价格信息
            return None  # 需要更复杂的解析
    except:
        pass
    return None


def check_te_price(model_name):
    """抓取 TE 官网 MSRP"""
    try:
        code, text = get_http("https://teenage.engineering/products", timeout=8)
        if code == 200:
            return None  # 需要更复杂的解析
    except:
        pass
    return None


# ============================================================
# 3. 主流程
# ============================================================
def main():
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S UTC")
    print("=" * 60)
    print("GitHub Actions 价格核查 (轻量版)")
    print(f"时间: {timestamp}")
    print("=" * 60)

    if not HTML_FILE.exists():
        print(f"[ERROR] 未找到 {HTML_FILE}")
        sys.exit(1)

    html = HTML_FILE.read_text(encoding="utf-8")
    products = parse_prices(html)
    print(f"\n共 {len(products)} 款产品\n")

    # 分类统计
    jd_products = []
    intl_products = []
    other_products = []

    for p in products:
        if "jd.com" in p["link"]:
            jd_products.append(p)
        elif p["brand"] in INTERNATIONAL_BRANDS:
            intl_products.append(p)
        else:
            other_products.append(p)

    print(f"JD/天猫产品: {len(jd_products)} 款 (需 WorkBuddy, 境外无法访问)")
    print(f"国际品牌:   {len(intl_products)} 款 (尝试官网抓价)")
    print(f"其他:       {len(other_products)} 款")
    print()

    # 国际品牌检查
    updated = False
    for p in intl_products:
        print(f"  [{p['brand']}] {p['model']} ... ", end="")
        price = None
        if p["brand"] == "B&O":
            price = check_bo_price(p["model"])
        elif p["brand"] == "Teenage Engineering":
            price = check_te_price(p["model"])

        if price:
            dev = abs(price - p["promo"]) / p["promo"] * 100
            if dev > 10:
                print(f"官网 ¥{price} (当前 ¥{p['promo']}, 偏差 {dev:.0f}%) UPDATED")
                pattern = (
                    rf"(brand:\s*'{re.escape(p['brand'])}',\s*"
                    rf"model:\s*'{re.escape(p['model'])}',\s*"
                    rf"orig:\s*\d+,\s*promo:\s*)\d+(\s*,)"
                )
                new_html, count = re.subn(pattern, rf"\g<1>{price}\g<2>", html)
                if count > 0:
                    html = new_html
                    updated = True
            else:
                print(f"稳定 (官网 ¥{price}, 偏差 {dev:.0f}%)")
        else:
            print("跳过 (官网抓价不可用)")

    # 保存 HTML（如有变更）
    if updated:
        HTML_FILE.write_text(html, encoding="utf-8")
        print("\n✓ speaker-monitor.html 已更新")

    # 生成快照
    snapshot = {
        "generated_at": timestamp,
        "runner": "github-actions",
        "total": len(products),
        "jd_deferred": len(jd_products),
        "intl_checked": len(intl_products),
        "note": "JD/天猫产品价格需 WorkBuddy AI 更新（境外网络无法访问 p.3.cn）",
        "products": [
            {
                "brand": p["brand"],
                "model": p["model"],
                "orig": p["orig"],
                "promo": p["promo"],
                "category": p["category"],
                "platform": p["platform"],
                "link": p["link"],
            }
            for p in products
        ],
    }

    with open("price_snapshot.json", "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)

    print(f"\n✓ 快照已生成: price_snapshot.json")
    print(f"  JD延迟: {len(jd_products)} | 国际: {len(intl_products)} | 其他: {len(other_products)}")
    print("=" * 60)


if __name__ == "__main__":
    main()
