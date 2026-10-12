#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
套餐工坊 combo.py
================

把「已点亮的图鉴卡」自由组合成套餐（新图鉴），可取名、一键下单。
只有下单满阈值点亮的卡才能参与组合（呼应点亮规则）。

命令行：
    python combo.py create --name "我的快乐水套餐" --items "M003,S001,D001" [--store SZ001]
    python combo.py list
    python combo.py order  --id <combo_id> [--store SZ001]
    python combo.py delete --id <combo_id>
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from mcd_client import MCDClient
from gacha import lit_map
from order import create as order_create

SKILL_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = SKILL_DIR / "data"
COMBOS_FILE = DATA_DIR / "combos.json"


def load() -> dict[str, Any]:
    if COMBOS_FILE.is_file():
        try:
            return json.loads(COMBOS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"combos": []}


def save(data: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    COMBOS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8", newline="")


def create(name: str, codes: list[str], store: str = "SZ001", client: MCDClient | None = None,
           allow_unlit: bool = False) -> dict[str, Any]:
    client = client or MCDClient()
    name = (name or "").strip()
    codes = [str(c).strip() for c in codes if str(c).strip()]
    if not name:
        return {"ok": False, "reason": "套餐名不能为空"}
    if len(codes) < 2:
        return {"ok": False, "reason": "套餐至少需要 2 张卡"}

    lit = lit_map(store, client)
    catalog = {m["code"]: m for m in client.meals_catalog(store)}
    if not allow_unlit:
        not_lit = [c for c in codes if not lit.get(c)]
        if not_lit:
            names = [catalog.get(c, {}).get("name", c) for c in not_lit]
            return {"ok": False, "reason": "以下卡尚未点亮，不能组套餐（需下单满阈值点亮）：" + "、".join(names),
                    "not_lit": not_lit}
    items = []
    for c in codes:
        meal = catalog.get(c, {})
        items.append({"code": c, "name": meal.get("name", c), "qty": 1})
    data = load()
    cid = "C" + datetime.now().strftime("%Y%m%d%H%M%S") + uuid.uuid4().hex[:4]
    combo = {"id": cid, "name": name, "store": store, "items": items,
             "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    data["combos"].append(combo)
    save(data)
    return {"ok": True, "combo": combo}


def list_combos() -> dict[str, Any]:
    data = load()
    return {"combos": data.get("combos", []), "count": len(data.get("combos", []))}


def delete(cid: str) -> dict[str, Any]:
    data = load()
    before = len(data.get("combos", []))
    data["combos"] = [c for c in data.get("combos", []) if c.get("id") != cid]
    save(data)
    return {"ok": True, "removed": before - len(data["combos"])}


def order(cid: str, store: str | None = None, client: MCDClient | None = None) -> dict[str, Any]:
    """一键下单套餐：把组合里的卡作为商品下单（带个性化备注）。"""
    client = client or MCDClient()
    data = load()
    combo = next((c for c in data.get("combos", []) if c.get("id") == cid), None)
    if not combo:
        return {"ok": False, "reason": f"未找到套餐 {cid}"}
    use_store = store or combo.get("store", "SZ001")
    items = [{"productCode": it["code"], "quantity": int(it.get("qty", 1))} for it in combo.get("items", [])]
    result = order_create(use_store, items, client)
    result["ok"] = True
    result["combo_name"] = combo.get("name")
    return result


def main(argv: list[str] | None = None) -> int:
    mode_parent = argparse.ArgumentParser(add_help=False)
    mode_parent.add_argument("--mode", choices=["LIVE", "DEMO"])
    p = argparse.ArgumentParser(description="套餐工坊")
    p.add_argument("--mode", choices=["LIVE", "DEMO"])
    sub = p.add_subparsers(dest="cmd", required=True)

    cr = sub.add_parser("create", parents=[mode_parent], help="新建套餐")
    cr.add_argument("--name", required=True)
    cr.add_argument("--items", required=True, help="逗号分隔的 code 列表")
    cr.add_argument("--store", default="SZ001")
    cr.add_argument("--allow-unlit", action="store_true", help="允许未点亮的卡组套餐（用抽中的卡现搭时用）")
    sub.add_parser("list", parents=[mode_parent], help="列出套餐")
    od = sub.add_parser("order", parents=[mode_parent], help="下单套餐")
    od.add_argument("--id", required=True)
    od.add_argument("--store", default=None)
    dl = sub.add_parser("delete", parents=[mode_parent], help="删除套餐")
    dl.add_argument("--id", required=True)

    args = p.parse_args(argv)
    c = MCDClient(force_mode=args.mode)

    if args.cmd == "create":
        out = create(args.name, args.items.split(","), args.store, c, allow_unlit=args.allow_unlit)
    elif args.cmd == "list":
        out = list_combos()
    elif args.cmd == "order":
        out = order(args.id, args.store, c)
    elif args.cmd == "delete":
        out = delete(args.id)
    else:
        p.error(f"未知命令 {args.cmd}")
        return 2
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
