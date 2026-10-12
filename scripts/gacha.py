#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
麦门开卡引擎 gacha.py
====================

把麦当劳真实菜单变成可收集卡池（麦门开卡 = 金拱门开卡，不用蛋的概念）：
- 稀有度由真实价格 + 标签决定（SSR/SR/R/N）
- 抽卡券模型：每日 1 张免费（按日期重置）+ 下单任意价格 +1 券 + 转发好友 +1 券
- 每张卡稀有度概率经重平衡，越稀有越难出
- 不同等级卡「下单满 3/5/7/10 次」自动点亮（N=3 / R=5 / SR=7 / SSR=10）
- 本地持久化收集进度、抽卡券、点亮状态；抽到的卡可直接「一键下单」

命令行：
    python gacha.py draw [--count N] [--store SZ001]   # 抽卡（消耗抽卡券）
    python gacha.py dex [--store SZ001]                # 图鉴墙（含点亮状态）
    python gacha.py achievements [--store SZ001]       # 成就
    python gacha.py status                             # 抽卡券明细
    python gacha.py share                              # 转发好友 +1 券
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from mcd_client import MCDClient
from classify import classify_flavor, meal_emoji, card_image, RARITY_LABEL

SKILL_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = SKILL_DIR / "data"
COLLECTION_FILE = DATA_DIR / "collection.json"

RARITY_ORDER = ["N", "R", "SR", "SSR"]
# 重平衡后的稀有度权重：新「每日 1 券」经济下，让稀有更稀有、SSR 更珍贵
RARITY_WEIGHTS = {"N": 60, "R": 25, "SR": 12, "SSR": 3}
# 点亮阈值：N 下单 3 次 / R 5 次 / SR 7 次 / SSR 10 次自动点亮
LIT_THRESHOLD = {"N": 3, "R": 5, "SR": 7, "SSR": 10}


# ----------------------------------------------------------------------------
# 稀有度
# ----------------------------------------------------------------------------

def rarity_of(meal: dict[str, Any]) -> str:
    price = float(meal.get("price") or 0)
    tags = meal.get("tags") or []
    if "含玩具" in tags or price >= 30:
        return "SSR"
    if "爆款" in tags or price >= 20:
        return "SR"
    if price >= 12:
        return "R"
    return "N"


# ----------------------------------------------------------------------------
# 持久化
# ----------------------------------------------------------------------------

def _default_collection() -> dict[str, Any]:
    return {
        "daily_draw_date": "",   # 免费每日券已被使用的日期
        "bonus_draws": 0,        # 下单/转发积累的额外抽卡券
        "unlocked": {},          # code -> {count, first_at, name, rarity, order_count}
        "draw_log": [],
        "total_draws": 0,
        "total_orders": 0,
    }


def _load_collection() -> dict[str, Any]:
    if COLLECTION_FILE.is_file():
        try:
            data = json.loads(COLLECTION_FILE.read_text(encoding="utf-8"))
            base = _default_collection()
            base.update(data)
            return base
        except (json.JSONDecodeError, OSError):
            pass
    return _default_collection()


def _save_collection(coll: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    COLLECTION_FILE.write_text(json.dumps(coll, ensure_ascii=False, indent=2), encoding="utf-8", newline="")


def _today(client: MCDClient) -> str:
    n = client.now()
    if isinstance(n, dict) and n.get("date"):
        return n["date"]
    return datetime.now().strftime("%Y-%m-%d")


# ----------------------------------------------------------------------------
# 抽卡券
# ----------------------------------------------------------------------------

def available_draws(coll: dict[str, Any], today: str) -> dict[str, int]:
    """返回抽卡券明细：每日免费是否可用 + 积累的额外券。"""
    daily = 0 if coll.get("daily_draw_date") == today else 1
    bonus = int(coll.get("bonus_draws", 0))
    return {"daily": daily, "bonus": bonus, "available": daily + bonus}


def grant_draw(n: int = 1, reason: str = "manual") -> dict[str, Any]:
    """发放额外抽卡券（下单 / 转发 等场景调用）。"""
    coll = _load_collection()
    coll["bonus_draws"] = int(coll.get("bonus_draws", 0)) + max(0, n)
    _save_collection(coll)
    return {"ok": True, "granted": max(0, n), "reason": reason,
            "bonus_draws": coll["bonus_draws"]}


def record_order_items(codes: list[str]) -> dict[str, Any]:
    """下单后累加每张卡的下单次数（用于点亮）。codes 可重复（份数）。"""
    coll = _load_collection()
    counts: dict[str, int] = {}
    for c in codes:
        c = str(c)
        if not c:
            continue
        counts[c] = counts.get(c, 0) + 1
    for code, n in counts.items():
        rec = coll["unlocked"].setdefault(code, {"count": 0, "first_at": "", "name": "", "rarity": "", "order_count": 0})
        rec["order_count"] = int(rec.get("order_count", 0)) + n
    coll["total_orders"] = int(coll.get("total_orders", 0)) + sum(counts.values())
    _save_collection(coll)
    return {"ok": True, "items": counts, "total_orders": coll["total_orders"]}


# ----------------------------------------------------------------------------
# 抽卡
# ----------------------------------------------------------------------------

def draw(count: int = 1, store: str = "SZ001", client: MCDClient | None = None) -> dict[str, Any]:
    client = client or MCDClient()
    catalog = client.meals_catalog(store)
    if not catalog:
        return {"error": "菜单为空（DEMO 数据缺失或 LIVE 接口异常）"}

    by_rarity: dict[str, list[dict[str, Any]]] = {r: [] for r in RARITY_ORDER}
    for m in catalog:
        by_rarity[rarity_of(m)].append(m)

    coll = _load_collection()
    today = _today(client)

    # 计算可用券并消耗
    tk = available_draws(coll, today)
    actual = max(0, min(count, tk["available"]))
    daily_used = 0
    bonus_used = 0
    if actual > 0:
        if tk["daily"] > 0:
            daily_used = 1
            coll["daily_draw_date"] = today
        bonus_used = min(coll.get("bonus_draws", 0), actual - daily_used)
        coll["bonus_draws"] = int(coll.get("bonus_draws", 0)) - bonus_used

    drawn = []
    for _ in range(actual):
        rarity = random.choices(RARITY_ORDER, weights=[RARITY_WEIGHTS[r] for r in RARITY_ORDER])[0]
        pool = by_rarity.get(rarity) or by_rarity["N"]
        meal = random.choice(pool)
        code = meal["code"]
        rar = rarity_of(meal)
        rec = coll["unlocked"].setdefault(code, {"count": 0, "first_at": "", "name": meal["name"], "rarity": rar, "order_count": 0})
        rec.setdefault("rarity", rar)
        rec.setdefault("name", meal["name"])
        is_new = rec["count"] == 0
        rec["count"] += 1
        if is_new and not rec["first_at"]:
            rec["first_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        coll["total_draws"] = coll.get("total_draws", 0) + 1
        coll["draw_log"].append({
            "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "code": code,
            "name": meal["name"],
            "rarity": rar,
            "is_new": is_new,
        })
        drawn.append({
            "code": code,
            "name": meal["name"],
            "category": meal.get("category"),
            "price": meal.get("price"),
            "rarity": rar,
            "rarity_label": RARITY_LABEL[rar],
            "flavor": classify_flavor(meal),
            "tags": meal.get("tags") or [],
            "image": card_image(meal),
            "emoji": meal_emoji(meal),
            "is_new": is_new,
            "owned_count": rec["count"],
            "lit": int(rec.get("order_count", 0)) >= LIT_THRESHOLD.get(rar, 999),
        })

    coll["draw_log"] = coll["draw_log"][-50:] if coll.get("draw_log") else []
    _save_collection(coll)

    total = len(catalog)
    owned = sum(1 for m in catalog if coll["unlocked"].get(m["code"], {}).get("count", 0) > 0)
    tk_after = available_draws(coll, today)
    return {
        "mode": client.mode,
        "today": today,
        "requested": count,
        "drawn": actual,
        "tickets_used": {"daily": daily_used, "bonus": bonus_used},
        "tickets": tk_after,
        "cards": drawn,
        "progress": {"owned": owned, "total": total, "pct": round(owned / total * 100, 1) if total else 0},
        "new_count": sum(1 for d in drawn if d["is_new"]),
        "hint": "抽卡券用完了～ 今天来店里点一单（任意价格 +1 券）或转发给麦门好友（+1 券）就能再抽！" if actual < count else "",
    }


def lit_map(store: str = "SZ001", client: MCDClient | None = None) -> dict[str, bool]:
    """返回 {code: 是否已点亮}，供套餐工坊校验「只能组合已点亮的卡」。"""
    client = client or MCDClient()
    catalog = client.meals_catalog(store)
    coll = _load_collection()
    out = {}
    for m in catalog:
        rar = rarity_of(m)
        oc = int(coll["unlocked"].get(m["code"], {}).get("order_count", 0))
        out[m["code"]] = oc >= LIT_THRESHOLD.get(rar, 999)
    return out


# ----------------------------------------------------------------------------
# 图鉴墙
# ----------------------------------------------------------------------------

def dex(store: str = "SZ001", client: MCDClient | None = None) -> dict[str, Any]:
    client = client or MCDClient()
    catalog = client.meals_catalog(store)
    coll = _load_collection()
    cats: dict[str, Any] = {}
    grid = []
    lit_total = 0
    for m in catalog:
        rar = rarity_of(m)
        rec = coll["unlocked"].get(m["code"], {})
        owned = rec.get("count", 0) > 0
        oc = int(rec.get("order_count", 0))
        lit = oc >= LIT_THRESHOLD.get(rar, 999)
        if lit:
            lit_total += 1
        entry = {
            "code": m["code"], "name": m["name"], "category": m.get("category"),
            "price": m.get("price"), "rarity": rar, "rarity_label": RARITY_LABEL[rar],
            "flavor": classify_flavor(m), "tags": m.get("tags") or [], "owned": owned,
            "order_count": oc, "lit": lit, "lit_threshold": LIT_THRESHOLD.get(rar, 999),
            "image": card_image(m), "emoji": meal_emoji(m),
        }
        grid.append(entry)
        c = cats.setdefault(m.get("category", "其他"), {"total": 0, "owned": 0, "lit": 0})
        c["total"] += 1
        if owned:
            c["owned"] += 1
        if lit:
            c["lit"] += 1
    total = len(catalog)
    owned = sum(1 for m in catalog if coll["unlocked"].get(m["code"], {}).get("count", 0) > 0)
    return {
        "mode": client.mode,
        "grid": grid,
        "categories": cats,
        "progress": {"owned": owned, "total": total, "pct": round(owned / total * 100, 1) if total else 0},
        "lit": {"count": lit_total, "total": total, "pct": round(lit_total / total * 100, 1) if total else 0},
    }


# ----------------------------------------------------------------------------
# 成就
# ----------------------------------------------------------------------------

def achievements(store: str = "SZ001", client: MCDClient | None = None) -> dict[str, Any]:
    client = client or MCDClient()
    catalog = client.meals_catalog(store)
    coll = _load_collection()
    owned_codes = {m["code"] for m in catalog if coll["unlocked"].get(m["code"], {}).get("count", 0) > 0}
    cats: dict[str, list[dict[str, Any]]] = {}
    for m in catalog:
        cats.setdefault(m.get("category", "其他"), []).append(m)

    earned = []
    locked = []

    def _check(key, name, desc, ok):
        (earned if ok else locked).append({"key": key, "name": name, "desc": desc})

    # 集齐分类
    for cat, items in cats.items():
        ok = all(m["code"] in owned_codes for m in items)
        _check(f"cat_{cat}", f"🍔 {cat}全图鉴", f"集齐全部 {len(items)} 个{cat}", ok)
    # 全集
    _check("all", "🌟 麦门全图鉴大师", f"集齐全部 {len(catalog)} 道菜品", len(owned_codes) == len(catalog))
    # 抽卡里程碑
    td = coll.get("total_draws", 0)
    _check("draw10", "🎰 初出茅庐", "累计抽满 10 次", td >= 10)
    _check("draw50", "🎰 收集控", "累计抽满 50 次", td >= 50)
    # 抽到 SSR
    has_ssr = any(d.get("rarity") == "SSR" for d in coll.get("draw_log", []))
    _check("ssr", "👑 欧皇降临", "抽中至少 1 张传说(SSR)", has_ssr)
    # 点亮成就
    lit_codes = {m["code"] for m in catalog if int(coll["unlocked"].get(m["code"], {}).get("order_count", 0)) >= LIT_THRESHOLD.get(rarity_of(m), 999)}
    _check("lit1", "💡 点亮启蒙", "点亮任意 1 张卡（下单满阈值）", len(lit_codes) >= 1)
    _check("lit10", "🔥 十全十美", "点亮满 10 张卡", len(lit_codes) >= 10)
    _check("litall", "🏅 满堂点亮", f"点亮全部 {len(catalog)} 张卡", len(lit_codes) == len(catalog) and len(catalog) > 0)

    return {"mode": client.mode, "earned": earned, "locked": locked, "total_draws": td,
            "total_orders": coll.get("total_orders", 0)}


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    mode_parent = argparse.ArgumentParser(add_help=False)
    mode_parent.add_argument("--mode", choices=["LIVE", "DEMO"])
    p = argparse.ArgumentParser(description="麦门开卡引擎")
    p.add_argument("--mode", choices=["LIVE", "DEMO"])
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("draw", parents=[mode_parent], help="麦门开卡（消耗抽卡券）")
    d.add_argument("--count", type=int, default=1)
    d.add_argument("--store", default="SZ001")
    sub.add_parser("dex", parents=[mode_parent], help="图鉴墙").add_argument("--store", default="SZ001")
    sub.add_parser("achievements", parents=[mode_parent], help="成就").add_argument("--store", default="SZ001")
    sub.add_parser("status", parents=[mode_parent], help="抽卡券明细")
    sub.add_parser("share", parents=[mode_parent], help="转发好友 +1 券")

    args = p.parse_args(argv)
    c = MCDClient(force_mode=args.mode)

    if args.cmd == "draw":
        out = draw(args.count, args.store, c)
    elif args.cmd == "dex":
        out = dex(args.store, c)
    elif args.cmd == "achievements":
        out = achievements(args.store, c)
    elif args.cmd == "share":
        out = grant_draw(1, "share")
    elif args.cmd == "status":
        coll = _load_collection()
        today = _today(c)
        tk = available_draws(coll, today)
        out = {"mode": c.mode, "today": today, "tickets": tk,
               "daily_draw_date": coll.get("daily_draw_date"),
               "bonus_draws": coll.get("bonus_draws", 0),
               "total_draws": coll.get("total_draws", 0),
               "total_orders": coll.get("total_orders", 0)}
    else:
        p.error(f"未知命令 {args.cmd}")
        return 2

    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
