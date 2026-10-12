#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
个性化记忆 personalization.py
=============================

记住每个餐品的个性化需求（例如「不要酸黄瓜」「少冰」「多酱」），
下单时自动拼进备注（remark）。数据存本地 data/prefs.json。

命令行：
    python personalization.py set  --code M001 --pref "不要酸黄瓜"
    python personalization.py get  --code M001
    python personalization.py list
    python personalization.py clear --code M001
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = SKILL_DIR / "data"
PREFS_FILE = DATA_DIR / "prefs.json"


def load() -> dict[str, Any]:
    if PREFS_FILE.is_file():
        try:
            return json.loads(PREFS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save(data: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PREFS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8", newline="")


def set_pref(code: str, pref: str, name: str = "") -> dict[str, Any]:
    code = str(code).strip()
    pref = (pref or "").strip()
    if not code or not pref:
        return {"ok": False, "reason": "code 与 pref 均不能为空"}
    data = load()
    entry = data.setdefault(code, {"name": name, "prefs": []})
    if name and not entry.get("name"):
        entry["name"] = name
    if pref not in entry["prefs"]:
        entry["prefs"].append(pref)
    save(data)
    return {"ok": True, "code": code, "prefs": entry["prefs"]}


def get_pref(code: str) -> list[str]:
    entry = load().get(str(code), {})
    return entry.get("prefs", [])


def all_prefs() -> dict[str, Any]:
    return load()


def clear_pref(code: str, pref: str | None = None) -> dict[str, Any]:
    code = str(code).strip()
    data = load()
    if code not in data:
        return {"ok": True, "msg": "无记录"}
    if pref is None:
        del data[code]
    else:
        data[code]["prefs"] = [p for p in data[code].get("prefs", []) if p != pref]
        if not data[code]["prefs"]:
            del data[code]
    save(data)
    return {"ok": True, "code": code, "prefs": data.get(code, {}).get("prefs", [])}


def build_remark(items: list[dict[str, Any]]) -> str:
    """把下单商品里所有个性化需求汇总成备注字符串。"""
    parts = []
    for it in items:
        code = it.get("code") or it.get("productCode")
        prefs = get_pref(code) if code else []
        if prefs:
            nm = it.get("name") or str(code)
            parts.append(f"{nm}：{'，'.join(prefs)}")
    return "；".join(parts)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="个性化需求记忆")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("set", help="设置某餐品个性化需求")
    s.add_argument("--code", required=True)
    s.add_argument("--pref", required=True)
    s.add_argument("--name", default="")
    g = sub.add_parser("get", help="查看某餐品需求")
    g.add_argument("--code", required=True)
    sub.add_parser("list", help="列出全部需求")
    cl = sub.add_parser("clear", help="清除需求")
    cl.add_argument("--code", required=True)
    cl.add_argument("--pref", default=None)
    args = p.parse_args(argv)

    if args.cmd == "set":
        out = set_pref(args.code, args.pref, args.name)
    elif args.cmd == "get":
        out = {"code": args.code, "prefs": get_pref(args.code)}
    elif args.cmd == "list":
        out = {"prefs": all_prefs()}
    elif args.cmd == "clear":
        out = clear_pref(args.code, args.pref)
    else:
        p.error(f"未知命令 {args.cmd}")
        return 2
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
