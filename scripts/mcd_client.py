#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MCD-Gacha 麦当劳 MCP 客户端
===========================

在「抢救麦券大作战」客户端基础上扩展：新增订单列表 / 订单详情 / 统一菜单目录，
并完整保留 LIVE/DEMO 双模式自动降级。麦门开卡图鉴的全部实时数据都来自这里。

用法（命令行）:
    python mcd_client.py status
    python mcd_client.py meals --store <code>
    python mcd_client.py meal-detail --code <code> --store <code>
    python mcd_client.py price --items "巨无霸:1,大薯:1"
    python mcd_client.py orders                 # 近 10 笔历史订单
    python mcd_client.py order --id <orderId>   # 订单详情
    python mcd_client.py order-create --store <code> --items "巨无霸:1"
    python mcd_client.py now

作为模块:
    from mcd_client import MCDClient
    c = MCDClient()
    c.meals_catalog(store_code)        # 归一化菜单（卡池来源）
    c.order_list()                     # 历史订单
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# ----------------------------------------------------------------------------
# 常量
# ----------------------------------------------------------------------------

MCP_URL = "https://mcp.mcd.cn"
MCP_CONFIG_CANDIDATES = [
    Path.home() / ".workbuddy" / "mcp.json",
    Path(os.environ.get("WORKBUDDY_HOME", Path.home() / ".workbuddy")) / "mcp.json",
]
SKILL_DIR = Path(__file__).resolve().parent.parent
OFFLINE_DATA = SKILL_DIR / "references" / "offline_menu.json"

REQUEST_TIMEOUT = 25

TOKEN_PLACEHOLDERS = (
    "在这里填入",
    "your_mcp_token",
    "your token",
    "填入你的",
    "placeholder",
    "xxxxx",
)

BE_TYPE = {1: "到店取餐", 2: "麦乐送到家", 5: "得来速(DT)", 6: "企业团餐"}
ORDER_TYPE = {1: "到店", 2: "外送"}

# 时段分桶（最爱统计用）
TIME_BUCKETS = [
    ("早餐", 5, 10.5),
    ("午餐", 10.5, 14),
    ("下午茶", 14, 17),
    ("晚餐", 17, 21),
    ("夜宵", 21, 29),  # 21:00-次日05:00（跨天用 hour+24 处理）
]


# ----------------------------------------------------------------------------
# Token 发现
# ----------------------------------------------------------------------------

def find_mcd_token() -> str | None:
    for cfg_path in MCP_CONFIG_CANDIDATES:
        if not cfg_path.is_file():
            continue
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        servers = cfg.get("mcpServers") or cfg.get("mcp_servers") or {}
        for name, spec in servers.items():
            if not isinstance(spec, dict):
                continue
            url = str(spec.get("url", ""))
            looks_like_mcd = ("mcd.cn" in url) or (name.lower() in {"mcd-mcp", "mcd", "mcd-mcp-server"})
            if not looks_like_mcd:
                continue
            headers = spec.get("headers") or {}
            if not isinstance(headers, dict):
                continue
            for hk, hv in headers.items():
                if str(hk).lower() == "authorization" and hv:
                    token = str(hv).strip()
                    if token.lower().startswith("bearer "):
                        token = token[7:].strip()
                    low = token.lower()
                    if not token or any(p in low for p in TOKEN_PLACEHOLDERS):
                        return None
                    return token
    return None


# ----------------------------------------------------------------------------
# 客户端
# ----------------------------------------------------------------------------

class MCDClient:
    """麦当劳 MCP 客户端，带自动降级。"""

    def __init__(self, token: str | None = None, force_mode: str | None = None):
        self.token = token if token is not None else find_mcd_token()
        if force_mode:
            self.mode = force_mode.upper()
        else:
            self.mode = "LIVE" if self.token else "DEMO"
        self.degrade_reason: str | None = None
        self._offline: dict[str, Any] | None = None
        self._req_counter = 0

    def _live_or_fallback(self, resp: dict[str, Any], fallback_fn) -> dict[str, Any]:
        if isinstance(resp, dict) and resp.get("_degraded"):
            data = fallback_fn()
            if isinstance(data, dict):
                data["_degraded"] = True
                data["message"] = resp.get("message", "已降级")
            return data
        return resp

    # -- 基础设施 -----------------------------------------------------------

    @property
    def offline(self) -> dict[str, Any]:
        if self._offline is None:
            if not OFFLINE_DATA.is_file():
                raise FileNotFoundError(f"离线数据集缺失: {OFFLINE_DATA}")
            self._offline = json.loads(OFFLINE_DATA.read_text(encoding="utf-8"))
        return self._offline

    def status(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "has_token": bool(self.token),
            "endpoint": MCP_URL,
            "token_preview": (self.token[:6] + "..." + self.token[-4:]) if self.token and len(self.token) > 12 else None,
        }

    def _call(self, tool: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        if self.mode != "LIVE":
            return {
                "_demo": True,
                "tool": tool,
                "arguments": arguments or {},
                "message": "DEMO 模式：未配置麦当劳 MCP Token，此调用未真实发出。",
            }

        payload = {
            "jsonrpc": "2.0",
            "id": f"mcd-gacha-{self._req_counter}",
            "method": "tools/call",
            "params": {"name": tool, "arguments": arguments or {}},
        }
        self._req_counter += 1

        req = urllib.request.Request(
            MCP_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "Authorization": f"Bearer {self.token}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            if e.code in (401, 403):
                self.mode = "DEMO"
                self.degrade_reason = f"Token 失效（HTTP {e.code}），已自动降级为 DEMO 模式"
                return {"_demo": True, "_degraded": True, "tool": tool, "message": self.degrade_reason, "server_message": body[:200]}
            hint = {429: "触发限流(600次/分钟)，请降低频率"}.get(e.code, "")
            return {"_error": True, "http_status": e.code, "hint": hint, "body": body[:300]}
        except urllib.error.URLError as e:
            self.mode = "DEMO"
            self.degrade_reason = f"网络不可达（{e.reason}），已自动降级为 DEMO 模式"
            return {"_demo": True, "_degraded": True, "tool": tool, "message": self.degrade_reason}

        return _parse_mcp_response(raw)

    # -- 菜单 ---------------------------------------------------------------

    def meals(self, store_code: str, order_type: int = 1, be_type: int = 1) -> dict[str, Any]:
        args = {"storeCode": store_code, "orderType": order_type, "beType": be_type}
        if self.mode == "LIVE":
            return self._live_or_fallback(self._call("query-meals", args), lambda: {"_demo": True, "meals": self.offline["meals"], "query": args})
        return {"_demo": True, "meals": self.offline["meals"], "query": args}

    def meals_catalog(self, store_code: str = "SZ001") -> list[dict[str, Any]]:
        """归一化菜单：返回 [{code,name,category,price,energyKcal,tags}]，LIVE/DEMO 通用。"""
        raw = self.meals(store_code)
        meals = raw.get("meals") or []
        out = []
        for m in meals:
            # 兼容真实 MCP 的 tags 与离线数据集的 tag（单数）
            raw_tags = m.get("tags")
            if not raw_tags:
                raw_tags = m.get("tag")
            if isinstance(raw_tags, str):
                raw_tags = [raw_tags]
            out.append({
                "code": str(m.get("code", "")),
                "name": m.get("name", m.get("title", "未命名")),
                "category": m.get("category", m.get("cat", "其他")),
                "price": float(m.get("price") or m.get("currentPrice") or 0),
                "energyKcal": int(m.get("energyKcal") or m.get("energy") or 0),
                "tags": list(raw_tags or []),
                "image": m.get("image", ""),
            })
        return out

    def meal_detail(self, code: str, store_code: str, order_type: int = 1, be_type: int = 1) -> dict[str, Any]:
        args = {"code": code, "storeCode": store_code, "orderType": order_type, "beType": be_type}

        def _fb() -> dict[str, Any]:
            for m in self.offline["meals"]:
                if m.get("code") == code:
                    return {"_demo": True, "meal": m}
            return {"_demo": True, "meal": None, "message": f"演示数据中无餐品 {code}"}

        if self.mode == "LIVE":
            return self._live_or_fallback(self._call("query-meal-detail", args), _fb)
        return _fb()

    def calculate_price(self, store_code: str, items: list[dict[str, Any]],
                        order_type: int = 1, be_type: int = 1) -> dict[str, Any]:
        args: dict[str, Any] = {"storeCode": store_code, "orderType": order_type, "beType": be_type, "items": items}
        if self.mode == "LIVE":
            return self._live_or_fallback(self._call("calculate-price", args), lambda: self._demo_price(items))
        return self._demo_price(items)

    def _demo_price(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        catalog = {m["code"]: m for m in self.offline["meals"]}
        total = 0.0
        kcal = 0
        lines = []
        for it in items:
            code = it.get("productCode") or it.get("code")
            qty = int(it.get("quantity", 1))
            meal = catalog.get(code)
            if not meal:
                lines.append({"productName": f"未知餐品({code})", "quantity": qty, "price": "0"})
                continue
            subtotal = float(meal["price"]) * qty
            total += subtotal
            kcal += int(meal.get("energyKcal", 0)) * qty
            lines.append({"productName": meal["name"], "quantity": qty, "price": f"{subtotal:.2f}"})
        return {
            "_demo": True,
            "orderDetail": {
                "orderProductList": lines,
                "productPrice": f"{total:.2f}",
                "totalDiscountAmount": "0.00",
                "realTotalAmount": f"{total:.2f}",
                "totalKcal": kcal,
                "couponList": [],
            },
        }

    # -- 订单 ---------------------------------------------------------------

    def order_list(self) -> dict[str, Any]:
        """近 10 笔历史订单。LIVE 调 order-list；DEMO 用 sample_orders 合成。"""
        if self.mode == "LIVE":
            return self._live_or_fallback(self._call("order-list"), lambda: self._demo_orders())
        return self._demo_orders()

    def _demo_orders(self) -> dict[str, Any]:
        catalog = {m["code"]: m for m in self.offline["meals"]}
        now = datetime.now()
        out = []
        for o in self.offline.get("sample_orders", []):
            d = now - timedelta(days=int(o.get("days_ago", 0)))
            d = d.replace(hour=int(o.get("hour", 12)), minute=0, second=0, microsecond=0)
            items = []
            for it in o.get("items", []):
                meal = catalog.get(it.get("code"))
                name = meal["name"] if meal else it.get("code")
                price = float(meal["price"]) if meal else 0.0
                items.append({"code": it.get("code"), "name": name, "qty": int(it.get("qty", 1)), "price": price})
            out.append({
                "orderId": o.get("order_id"),
                "ts": d.strftime("%Y-%m-%d %H:%M:%S"),
                "items": items,
                "store": o.get("store"),
                "total": float(o.get("total", 0)),
                "source": "demo",
            })
        out.sort(key=lambda x: x["ts"])
        return {"_demo": True, "orders": out}

    def query_order(self, order_id: str) -> dict[str, Any]:
        if self.mode == "LIVE":
            return self._live_or_fallback(self._call("query-order", {"orderId": order_id}), lambda: {"_demo": True, "order": None})
        return {"_demo": True, "order": None, "message": "DEMO 模式无此订单详情"}

    def create_order(self, store_code: str, items: list[dict[str, Any]],
                     order_type: int = 1, be_type: int = 1,
                     address_id: str | None = None,
                     take_way_code: str | None = None,
                     remark: str = "") -> dict[str, Any]:
        args: dict[str, Any] = {"storeCode": store_code, "orderType": order_type, "beType": be_type, "items": items}
        if address_id:
            args["addressId"] = address_id
        if take_way_code:
            args["takeWayCode"] = take_way_code
        if remark:
            args["remark"] = remark
        if self.mode == "LIVE":
            return self._live_or_fallback(self._call("create-order", args), lambda: self._demo_order(items))
        return self._demo_order(items)

    def _demo_order(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        import time
        priced = self._demo_price(items)
        return {
            "_demo": True,
            "orderId": f"DEMO-{int(time.time()*1000)}",
            "payH5Url": "(演示模式不产生真实支付链接)",
            "orderDetail": priced["orderDetail"],
            "message": "这是演示订单，未产生任何真实交易。配置 MCP Token 后可真实下单。",
        }

    # -- 其它 ---------------------------------------------------------------

    def now(self) -> dict[str, Any]:
        from datetime import datetime as _dt
        if self.mode == "LIVE":
            r = self._call("now-time-info")
            if not (isinstance(r, dict) and r.get("_degraded")):
                return r
        now = _dt.now()
        return {"_demo": True, "formatted": now.strftime("%Y-%m-%d %H:%M:%S"), "date": now.strftime("%Y-%m-%d")}


# ----------------------------------------------------------------------------
# MCP 响应解析
# ----------------------------------------------------------------------------

def _parse_mcp_response(raw: str) -> dict[str, Any]:
    raw = raw.strip()
    if not raw:
        return {}
    if raw.startswith("event:") or raw.startswith("data:") or "\ndata:" in raw:
        chunks = []
        for line in raw.splitlines():
            if line.startswith("data:"):
                chunks.append(line[5:].strip())
        raw = "".join(chunks)
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return {"_raw": raw}
    if isinstance(obj, dict):
        result = obj.get("result")
        if isinstance(result, dict):
            sc = result.get("structuredContent")
            if isinstance(sc, dict) and sc:
                return sc
            content = result.get("content")
            if isinstance(content, list) and content:
                texts = [c.get("text", "") for c in content if isinstance(c, dict)]
                joined = "".join(texts)
                try:
                    return json.loads(joined)
                except json.JSONDecodeError:
                    return {"_text": joined, "raw_result": result}
            return result
        if "error" in obj:
            return {"_error": obj["error"]}
    return obj


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------

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


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="MCD-Gacha 麦当劳 MCP 客户端")
    p.add_argument("--mode", choices=["LIVE", "DEMO"], help="强制指定模式")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="查看当前模式")
    m = sub.add_parser("meals", help="门店菜单")
    m.add_argument("--store", default="SZ001")
    md = sub.add_parser("meal-detail", help="餐品详情")
    md.add_argument("--code", required=True)
    md.add_argument("--store", default="SZ001")
    pr = sub.add_parser("price", help="算价")
    pr.add_argument("--store", default="SZ001")
    pr.add_argument("--items", required=True)
    o = sub.add_parser("orders", help="历史订单")
    od = sub.add_parser("order", help="订单详情")
    od.add_argument("--id", required=True)
    oc = sub.add_parser("order-create", help="下单")
    oc.add_argument("--store", required=True)
    oc.add_argument("--items", required=True)
    sub.add_parser("now", help="当前时间")

    args = p.parse_args(argv)
    c = MCDClient(force_mode=args.mode)

    if args.cmd == "status":
        out = c.status()
    elif args.cmd == "meals":
        out = {"meals": c.meals_catalog(args.store)}
    elif args.cmd == "meal-detail":
        out = c.meal_detail(args.code, args.store)
    elif args.cmd == "price":
        out = c.calculate_price(args.store, _parse_items(args.items))
    elif args.cmd == "orders":
        out = c.order_list()
    elif args.cmd == "order":
        out = c.query_order(args.id)
    elif args.cmd == "order-create":
        out = c.create_order(args.store, _parse_items(args.items))
    elif args.cmd == "now":
        out = c.now()
    else:
        p.error(f"未知命令 {args.cmd}")
        return 2

    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
