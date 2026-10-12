#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
我的麦生 · 订单记录 order_record.py
==================================

经本 Skill 下单的订单会被持久化到本地，与麦当劳 MCP 的近 10 笔历史订单合并，
作为「最爱统计」的完整数据源。

为什么需要本地记录：
    麦当劳 MCP 的 order-list 只返回近 10 笔订单，算不出「本月/本周最爱」。
    用户通过本 Skill 下的每一单都会被记下来，越用越准。

命令行：
    python order_record.py record --json '<order json>'   # 记录一笔（agent 下单后调用）
    python order_record.py list                           # 列出本地记录
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from mcd_client import MCDClient

SKILL_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = SKILL_DIR / "data"
LIFE_FILE = DATA_DIR / "my_mcd_life.json"


def load() -> dict[str, Any]:
    if LIFE_FILE.is_file():
        try:
            return json.loads(LIFE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"orders": []}


def save(data: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LIFE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8", newline="")


def add_order(record: dict[str, Any]) -> dict[str, Any]:
    """追加一笔订单（按 order_id 去重）。record 形如：
    {"order_id":"...","ts":"2026-10-11 19:30:00","items":[{"code","name","qty","price"}],"store","total","source"}
    """
    data = load()
    existing = {o.get("order_id") for o in data["orders"]}
    if record.get("order_id") and record["order_id"] in existing:
        return {"ok": False, "reason": "duplicate", "order_id": record.get("order_id")}
    data["orders"].append(record)
    data["orders"].sort(key=lambda x: x.get("ts", ""))
    save(data)
    return {"ok": True, "order_id": record.get("order_id"), "total_orders": len(data["orders"])}


def all_orders(client: MCDClient | None = None, include_mcp: bool = True) -> list[dict[str, Any]]:
    """合并本地记录 + MCP 近 10 笔订单，按 order_id 去重。"""
    client = client or MCDClient()
    merged: dict[str, dict[str, Any]] = {}

    # 1) 本地经本 Skill 下的单（最完整）
    for o in load().get("orders", []):
        merged[o.get("order_id") or f"local-{o.get('ts')}"] = o

    # 2) MCP 近 10 笔（补充更早的历史）
    if include_mcp:
        try:
            resp = client.order_list()
            for o in resp.get("orders", []):
                oid = o.get("orderId") or o.get("order_id")
                if oid and oid not in merged:
                    merged[oid] = {
                        "order_id": oid,
                        "ts": o.get("ts") or o.get("createTime", ""),
                        "items": o.get("items", []),
                        "store": o.get("store", ""),
                        "total": float(o.get("total") or 0),
                        "source": "mcp",
                    }
        except Exception:
            pass

    orders = list(merged.values())
    orders.sort(key=lambda x: x.get("ts", ""))
    return orders


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="我的麦生订单记录")
    p.add_argument("--mode", choices=["LIVE", "DEMO"])
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("record", help="记录一笔订单")
    r.add_argument("--json", required=True, help="订单 JSON 字符串")
    sub.add_parser("list", help="列出本地订单")

    args = p.parse_args(argv)
    if args.cmd == "record":
        try:
            rec = json.loads(args.json)
        except json.JSONDecodeError as e:
            print(json.dumps({"ok": False, "error": f"JSON 解析失败: {e}"}, ensure_ascii=False))
            return 2
        out = add_order(rec)
    elif args.cmd == "list":
        out = {"orders": load().get("orders", [])}
    else:
        p.error(f"未知命令 {args.cmd}")
        return 2
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
