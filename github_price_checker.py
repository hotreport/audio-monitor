#!/usr/bin/env python3
"""
GitHub Actions 价格核查脚本
==========================
独立运行，不依赖 WorkBuddy AI。
- JD 产品：调用 https://p.3.cn/prices/mgets 价格 API
- 非 JD 产品：尝试直接抓取产品页
- 偏差 >10% → 自动更新，5-10% → 标记待确认，<5% → 忽略
"""

import re
import json
import sys
import time
import os
from pathlib import Path

# 如果没有 requests，降级用 urllib
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    import urllib.request
    import urllib.error
    HAS_REQUESTS = False
    print("[WARN] requests 不可用，使用 urllib 降级方案")

HTML_FILE = Path(__file__).parent / "speaker-monitor.html" if Path(__file__).parent.name != "workflow" else Path("speaker-monitor.html")

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


def get_http(url, headers=None, timeout=10):
    """统一 HTTP GET"""
    if HAS_REQUESTS:
        try:
            r = requests.get(url, headers=headers or {}, timeout=timeout)
            return r.status_code, r.text
        except Exception as e:
            return None, str(e)
    else:
        try:
            req = urllib.request.Request(url, headers=headers or {})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            return None, str(e)


# ============================================================
# 2. JD 价格 API
# ============================================================
def extract_jd_sku(link):
    """从 JD 链接提取 SKU ID"""
    m = re.search(r'item\.jd\.com/(\d+)\.html', link)
    return m.group(1) if m else None


def fetch_jd_price(sku):
    """通过 JD 价格 API 获取实时价格"""
    url = f"https://p.3.cn/prices/mgets?skuIds=J_{sku}"
    code, text = get_http(url, headers={
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://item.jd.com/",
    })
    if code != 200:
        return None
    try:
        data = json.loads(text)
        if isinstance(data, list) and len(data) > 0:
            p = float(data[0].get("p", "0"))
            return int(p) if p > 0 else None
    except:
        pass
    return None


# ============================================================
# 3. 主流程
# ============================================================
def main():
    print("=" * 60)
    print("GitHub Actions 价格核查")
    print(f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    if not HTML_FILE.exists():
        print(f"[ERROR] 未找到 {HTML_FILE}")
        sys.exit(1)

    html = HTML_FILE.read_text(encoding="utf-8")
    products = parse_prices(html)
    print(f"\n共 {len(products)} 款产品\n")

    changes = []
    jd_count = 0
    fail_count = 0

    for p in products:
        sku = extract_jd_sku(p["link"])
        if not sku:
            continue

        jd_count += 1
        price = fetch_jd_price(sku)

        if price is None:
            fail_count += 1
            continue

        deviation = abs(price - p["promo"]) / p["promo"] * 100
        status = ""
        action = ""

        if deviation > 10:
            status = "⚠️ 大幅变动"
            action = "UPDATE"
        elif deviation >= 5:
            status = "🔶 小变动"
            action = "FLAG"
        else:
            status = "✅ 稳定"

        print(f"  {p['brand']:<8} {p['model']:<20} "
              f"当前 ¥{p['promo']:<6} JD ¥{price:<6} "
              f"偏差 {deviation:5.1f}%  {status}")

        if action == "UPDATE":
            changes.append((p, price))
        elif action == "FLAG":
            changes.append((p, price))

    # 应用变更
    if changes:
        print(f"\n--- 共 {len(changes)} 款产品需要更新 ---")
        for p, new_price in changes:
            # 只自动更新 >10% 偏差的
            deviation = abs(new_price - p["promo"]) / p["promo"] * 100
            if deviation > 10:
                print(f"  🔄 {p['brand']} {p['model']}: ¥{p['promo']} → ¥{new_price}")
                # 更新 HTML
                pattern = (
                    rf"(brand:\s*'{re.escape(p['brand'])}',\s*"
                    rf"model:\s*'{re.escape(p['model'])}',\s*"
                    rf"orig:\s*\d+,\s*promo:\s*)\d+(\s*,)"
                )
                new_html, count = re.subn(pattern, rf"\g<1>{new_price}\g<2>", html)
                if count > 0:
                    html = new_html
                else:
                    print(f"    [WARN] 未匹配到对应条目")
            else:
                print(f"  📋 {p['brand']} {p['model']}: ¥{p['promo']} → ¥{new_price} (偏差{deviation:.1f}%, 需确认)")

        # 写回 HTML
        HTML_FILE.write_text(html, encoding="utf-8")
        print("\n✓ 已更新 speaker-monitor.html")
    else:
        print("\n✓ 所有价格稳定，无需更新")

    print(f"\n统计: JD链接 {jd_count} 个, 成功抓取 {jd_count - fail_count} 个, 失败 {fail_count} 个")
    print("=" * 60)


if __name__ == "__main__":
    main()
