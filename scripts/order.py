#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
下单 + 记账 order.py
====================

一步完成：调用麦当劳 MCP create-order（LIVE 返回支付链接 / DEMO 模拟），
并把这笔订单写进「我的麦生」本地记录，供最爱统计使用。

命令行：
    python order.py create --store SZ001 --items "M003:1,大薯条:1"
    python order.py create --store SZ001 --items "麦辣鸡腿堡:1" --live
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from typing import Any

from mcd_client import MCDClient
from order_record import add_order
from gacha import record_order_items, grant_draw
from personalization import build_remark


def _parse_items(spec: str) -> list[dict[str, Any]]:
    out = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            name, _, qty = part.partition(":")
        else:
            name, qty = part, "1"
        out.append({"productCode": name.strip(), "quantity": int(qty.strip() or 1)})
    return out


def create(store: str, items: list[dict[str, Any]], client: MCDClient | None = None) -> dict[str, Any]:
    client = client or MCDClient()
    # 先把下单商品名/价格/code 解析出来（供记账与个性化备注）
    catalog = {m["code"]: m for m in client.meals_catalog(store)}
    name_to_code = {m["name"]: m["code"] for m in catalog.values()}
    rec_items = []
    for it in items:
        code = it.get("productCode")
        meal = catalog.get(code) or catalog.get(name_to_code.get(code, ""))
        rec_items.append({
            "code": code,
            "name": meal["name"] if meal else code,
            "qty": int(it.get("quantity", 1)),
            "price": float(meal["price"]) if meal else 0.0,
        })

    # 汇总个性化需求作为备注（如「巨无霸：不要酸黄瓜」）
    remark = build_remark(rec_items)

    # 真正下单（LIVE 会把备注带过去；DEMO 仅模拟）
    result = client.create_order(store, items, remark=remark)

    # 始终以解析后的明细重算总额，保证 DEMO/LIVE 下记录自洽
    total = round(sum(float(i.get("price", 0)) * int(i.get("qty", 1)) for i in rec_items), 2)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    oid = (result.get("orderId") if isinstance(result, dict) else None) or f"DEMO-{int(datetime.now().timestamp())}"
    record = {
        "order_id": oid,
        "ts": ts,
        "items": rec_items,
        "store": store,
        "total": total,
        "source": client.mode.lower(),
        "remark": remark,
    }
    rec = add_order(record)

    # 下单任意价格 +1 抽卡券；并累加每张卡的下单次数（用于点亮）
    order_codes = [i["code"] for i in rec_items for _ in range(int(i["qty"]))]
    lit = record_order_items(order_codes)
    granted = grant_draw(1, "order")

    return {"mode": client.mode, "order": result, "record": record, "saved": rec,
            "remark": remark, "lit_update": lit, "draw_granted": granted}


def main(argv: list[str] | None = None) -> int:
    mode_parent = argparse.ArgumentParser(add_help=False)
    mode_parent.add_argument("--mode", choices=["LIVE", "DEMO"])
    p = argparse.ArgumentParser(description="下单 + 记账")
    p.add_argument("--mode", choices=["LIVE", "DEMO"])
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create", parents=[mode_parent], help="创建订单并记录")
    c.add_argument("--store", default="SZ001")
    c.add_argument("--items", required=True)
    args = p.parse_args(argv)
    client = MCDClient(force_mode=args.mode)
    if args.cmd == "create":
        out = create(args.store, _parse_items(args.items), client)
    else:
        p.error(f"未知命令 {args.cmd}")
        return 2
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
