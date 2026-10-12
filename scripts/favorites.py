#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
最爱统计 favorites.py
====================

基于「我的麦生」合并订单，算出：
  - 本周 / 本月 / 全部 最爱单品或套餐（按点单次数）
  - 最爱时间段（早餐/午餐/下午茶/晚餐/夜宵）
  - 最爱口味（辣/甜/芝士香/香脆/轻食/解腻饮/经典）
  - 最爱榜（按点单次数排序），榜一附「一键复刻」下单指令

注意：麦当劳 MCP 的 order-list 仅返回近 10 笔，无法单独支撑「本月」统计；
本模块以「经本 Skill 下的本地订单 + MCP 近 10 笔」合并为数据源，越用越准。

命令行：
    python favorites.py report [--period week|month|all] [--store SZ001] [--top 5]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any

from mcd_client import MCDClient
from classify import classify_flavor, time_bucket, meal_emoji, card_image
from gacha import rarity_of
from order_record import all_orders


def _parse_ts(ts: str) -> datetime | None:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(ts, fmt)
        except (ValueError, TypeError):
            continue
    return None


def _in_period(ts: str, period: str, now: datetime) -> bool:
    dt = _parse_ts(ts)
    if dt is None:
        return False
    if period == "week":
        return (now - dt).days < 7 and (now - dt).days >= 0
    if period == "month":
        return dt.year == now.year and dt.month == now.month
    return True  # all


def report(period: str = "month", store: str = "SZ001", top: int = 5,
           client: MCDClient | None = None) -> dict[str, Any]:
    client = client or MCDClient()
    orders = all_orders(client)
    now = datetime.now()

    period_label = {"week": "近 7 天", "month": "本月", "all": "全部"}.get(period, period)
    items_counter: Counter = Counter()          # code -> 点单总份数
    item_meta: dict[str, dict[str, Any]] = {}    # code -> {name, flavor, category, spent}
    bucket_counter: Counter = Counter()          # 时段 -> 订单数
    flavor_counter: Counter = Counter()          # 口味 -> 份数
    store_counter: Counter = Counter()
    total_spend = 0.0
    period_orders = 0

    # 用菜单目录给 item 补全 category / code（订单里可能只有 name）
    catalog = {m["code"]: m for m in client.meals_catalog(store)}
    name_to_code = {m["name"]: m["code"] for m in catalog.values()}

    for o in orders:
        if not _in_period(o.get("ts", ""), period, now):
            continue
        period_orders += 1
        total_spend += float(o.get("total") or 0)
        store_counter[o.get("store", "未知门店")] += 1
        h = _parse_ts(o.get("ts", ""))
        bucket_counter[time_bucket(h.hour) if h else "未知"] += 1
        for it in o.get("items", []):
            code = it.get("code") or name_to_code.get(it.get("name", ""), it.get("name", "?"))
            name = it.get("name") or catalog.get(code, {}).get("name", code)
            qty = int(it.get("qty", 1))
            meal = catalog.get(code, {})
            flavor = classify_flavor(meal if meal else {"name": name, "tags": []})
            items_counter[code] += qty
            flavor_counter[flavor] += qty
            meta = item_meta.setdefault(code, {"name": name, "flavor": flavor, "category": meal.get("category", "其他"), "spent": 0.0})
            meta["name"] = name
            meta["flavor"] = flavor
            meta["category"] = meal.get("category", meta["category"])
            meta["spent"] += float(it.get("price") or 0) * qty
            if "emoji" not in meta:
                rar = rarity_of(meal) if meal else "N"
                meta["emoji"] = meal_emoji(meal if meal else {"name": name, "category": meta["category"]})
                meta["image"] = card_image(meal if meal else {"name": name, "category": meta["category"], "rarity": rar})

    # 榜一
    top_item = None
    leaderboard = []
    for code, cnt in items_counter.most_common(top):
        meta = item_meta[code]
        leaderboard.append({
            "code": code, "name": meta["name"], "count": cnt,
            "flavor": meta["flavor"], "category": meta["category"],
            "spent": round(meta["spent"], 2),
            "emoji": meta.get("emoji", "🍴"),
            "image": meta.get("image", ""),
        })
    if leaderboard:
        t = leaderboard[0]
        top_item = {
            "code": t["code"], "name": t["name"], "count": t["count"],
            "flavor": t["flavor"], "category": t["category"],
            "emoji": t.get("emoji", "🍴"), "image": t.get("image", ""),
            "order_items": [{"productCode": t["code"], "quantity": 1}],
            "store": store_counter.most_common(1)[0][0] if store_counter else store,
        }

    fav_time = bucket_counter.most_common(1)[0] if bucket_counter else None
    fav_flavor = flavor_counter.most_common(1)[0] if flavor_counter else None

    return {
        "mode": client.mode,
        "period": period,
        "period_label": period_label,
        "generated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "orders_in_period": period_orders,
        "total_spend": round(total_spend, 2),
        "fav_item": top_item,
        "fav_time": {"name": fav_time[0], "count": fav_time[1]} if fav_time else None,
        "fav_flavor": {"name": fav_flavor[0], "count": fav_flavor[1]} if fav_flavor else None,
        "leaderboard": leaderboard,
        "time_distribution": dict(bucket_counter.most_common()),
        "flavor_distribution": dict(flavor_counter.most_common()),
        "note": "数据来源 = 经本 Skill 下的本地订单 + 麦当劳 MCP 近 10 笔；越用越准。MCP 仅提供近 10 笔，故早期历史依赖本地累积。" if period_orders else "本期还没有订单记录。点菜单里的卡下单、或用本 Skill 真实点一单，就能开始统计最爱。",
    }


def main(argv: list[str] | None = None) -> int:
    mode_parent = argparse.ArgumentParser(add_help=False)
    mode_parent.add_argument("--mode", choices=["LIVE", "DEMO"])
    p = argparse.ArgumentParser(description="最爱统计")
    p.add_argument("--mode", choices=["LIVE", "DEMO"])
    sub = p.add_subparsers(dest="cmd", required=True)
    rp = sub.add_parser("report", parents=[mode_parent], help="生成最爱报告")
    rp.add_argument("--period", choices=["week", "month", "all"], default="month")
    rp.add_argument("--store", default="SZ001")
    rp.add_argument("--top", type=int, default=5)
    args = p.parse_args(argv)
    c = MCDClient(force_mode=args.mode)
    out = report(args.period, args.store, args.top, c)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
