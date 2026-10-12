#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分类工具：口味识别 + 时段分桶 + 卡面配图（麦门开卡图鉴与最爱统计共用）
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = SKILL_DIR / "assets"
REFERENCES_DIR = SKILL_DIR / "references"

# 时段分桶（与最爱统计共用）
TIME_BUCKETS = [
    ("早餐", 5, 10.5),
    ("午餐", 10.5, 14),
    ("下午茶", 14, 17),
    ("晚餐", 17, 21),
    ("夜宵", 21, 29),  # 21:00-次日05:00 用 hour+24 处理
]

# 稀有度配色（卡片描边 / 图块底色）
RARITY_COLOR = {"N": "#9e9e9e", "R": "#2196f3", "SR": "#9c27b0", "SSR": "#ff9800"}
# 图块浅色底（DEMO 内联 SVG 用）
RARITY_TINT = {"N": "#eceff1", "R": "#e3f2fd", "SR": "#f3e5f5", "SSR": "#fff3e0"}
RARITY_LABEL = {"N": "普通", "R": "稀有", "SR": "史诗", "SSR": "传说"}


def classify_flavor(meal: dict[str, Any]) -> str:
    """根据餐品名/标签推断口味偏好标签（启发式，非官方字段）。"""
    name = str(meal.get("name", "") or "")
    tags = meal.get("tags") or []
    tag_text = " ".join(str(t) for t in tags)

    if "辣" in name or "辣" in tag_text or "麻" in name or "川" in name:
        return "辣"
    if "甜品" in tag_text or "甜" in name or "糖" in name or "旋风" in name \
            or "冰淇淋" in name or "圆筒" in name or "圣代" in name or "派" in name:
        return "甜"
    if "芝士" in name or "吉士" in name or "芝" in name:
        return "芝士香"
    if "脆" in name or "炸" in name or "香" in name:
        return "香脆"
    if "沙拉" in name or "玉米" in name or "轻" in name or "蔬菜" in name:
        return "轻食"
    if "可乐" in name or "饮" in name or "咖啡" in name or "茶" in name or "果汁" in name:
        return "解腻饮"
    return "经典"


def time_bucket(hour: int) -> str:
    """把下单钟点归入时段桶（夜宵跨天：0-5 点算入前一日夜宵）。"""
    h = hour if hour >= 5 else hour + 24
    for name, start, end in TIME_BUCKETS:
        if start <= h < end:
            return name
    return "夜宵"


# ----------------------------------------------------------------------------
# 卡面配图：实物图原图 + 金属质感徽章框
# 原则：卡面一律不用 emoji。优先用真实产品图（LIVE 麦当劳 MCP 原图 / DEMO 本地图），
#       没有可用图时用「分类食物图标 + 金属徽章」兜底（是图，不是字）。
# ----------------------------------------------------------------------------

def meal_emoji(meal: dict[str, Any]) -> str:
    """（仅作降级/分享卡兜底）给餐品挑一个 emoji。前端卡面优先用金属徽章。"""
    name = str(meal.get("name", "") or "")
    category = str(meal.get("category", "") or "")
    rules = [
        ("薯", "🍟"), ("鸡", "🍗"), ("鱼", "🐟"), ("牛", "🥩"),
        ("麦旋风", "🍦"), ("冰淇淋", "🍦"), ("圣代", "🍦"), ("圆筒", "🍦"),
        ("派", "🥧"), ("松饼", "🥞"), ("蛋", "🍳"), ("沙拉", "🥗"),
        ("玉米", "🌽"), ("薯饼", "🥔"), ("可乐", "🥤"), ("咖啡", "☕"),
        ("茶", "🍵"), ("果汁", "🧃"), ("奶", "🥛"), ("堡", "🍔"),
        ("套餐", "🍱"), ("卷", "🌯"), ("饭", "🍚"), ("粥", "🥣"),
    ]
    for kw, em in rules:
        if kw in name:
            return em
    cat_emoji = {"汉堡": "🍔", "小食": "🍟", "饮料": "🥤", "甜品": "🍰", "套餐": "🍱"}
    return cat_emoji.get(category, "🍴")


def metallic_badge_datauri(name: str, rarity: str = "N") -> str:
    """生成一张「金属徽章」卡面（data URI）：金/银渐变 + 高光 + 镌刻产品名，不用 emoji。"""
    rim = RARITY_COLOR.get(rarity, "#9e9e9e")
    short = name if len(name) <= 5 else name[:4] + "…"
    gold_top = {"N": "#fff3c4", "R": "#d9f0ff", "SR": "#ffe9a8", "SSR": "#fff7d6"}.get(rarity, "#fff3c4")
    gold_mid = {"N": "#e6b800", "R": "#7fb8e6", "SR": "#e0a93b", "SSR": "#f5d04e"}.get(rarity, "#e6b800")
    gold_bot = {"N": "#b8860b", "R": "#3f7fb0", "SR": "#a9760c", "SSR": "#caa11f"}.get(rarity, "#b8860b")
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="120" height="120" viewBox="0 0 120 120">'
        f'<defs>'
        f'<radialGradient id="mg" cx="38%" cy="30%" r="80%">'
        f'<stop offset="0%" stop-color="{gold_top}"/>'
        f'<stop offset="55%" stop-color="{gold_mid}"/>'
        f'<stop offset="100%" stop-color="{gold_bot}"/>'
        f'</radialGradient>'
        f'<linearGradient id="sh" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0%" stop-color="#ffffff" stop-opacity="0.9"/>'
        f'<stop offset="35%" stop-color="#ffffff" stop-opacity="0"/>'
        f'<stop offset="100%" stop-color="#000000" stop-opacity="0.25"/>'
        f'</linearGradient>'
        f'</defs>'
        f'<circle cx="60" cy="60" r="55" fill="url(#mg)" stroke="{rim}" stroke-width="4"/>'
        f'<circle cx="60" cy="60" r="55" fill="url(#sh)"/>'
        f'<circle cx="60" cy="60" r="46" fill="none" stroke="#ffffff" stroke-opacity="0.55" stroke-width="1.5"/>'
        f'<text x="60" y="58" font-size="15" font-weight="700" fill="#4a3500" text-anchor="middle" '
        f'font-family="-apple-system,PingFang SC,Microsoft YaHei,sans-serif">{short}</text>'
        f'<text x="60" y="80" font-size="9" fill="#5a4500" text-anchor="middle" '
        f'font-family="-apple-system,PingFang SC,Microsoft YaHei,sans-serif" opacity="0.8">MCD</text>'
        f'</svg>'
    )
    b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{b64}"


def _guess_mime(name: str) -> str:
    n = (name or "").lower()
    if n.endswith(".png"):
        return "image/png"
    if n.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if n.endswith(".gif"):
        return "image/gif"
    if n.endswith(".svg"):
        return "image/svg+xml"
    if n.endswith(".webp"):
        return "image/webp"
    return "image/png"


def resolve_image(src: str | None) -> str:
    """把各种来源的图片字段统一解析成可直接放进 <img src> 的地址：
    - 已是 data URI / http(s) URL：原样返回
    - MCP 的 image_blob_ref JSON（含本地 blob 文件路径）：读文件 → base64 data URI
    - local:<相对路径>：在工作区 assets/references 内查找 → base64 data URI
    - 其余 / 找不到：返回空字符串（交给调用方走分类图标兜底）
    """
    if not src:
        return ""
    s = str(src).strip()
    if s.startswith("data:"):
        return s
    if s.startswith("http://") or s.startswith("https://"):
        return s
    if s.startswith("local:"):
        rel = s[len("local:"):].lstrip("/")
        for base in (ASSETS_DIR, REFERENCES_DIR, SKILL_DIR):
            p = base / rel
            if p.is_file():
                try:
                    raw = p.read_bytes()
                except OSError:
                    return ""
                b64 = base64.b64encode(raw).decode("ascii")
                return f"data:{_guess_mime(p.name)};base64,{b64}"
        return ""
    # MCP image_blob_ref：{"type":"image_blob_ref","blob_id":...,"mime":...,"blob_path":...,"size":...}
    if s.startswith("{") and "image_blob_ref" in s:
        try:
            obj = json.loads(s)
        except (ValueError, OSError):
            return ""
        if not isinstance(obj, dict) or obj.get("type") != "image_blob_ref":
            return ""
        mime = obj.get("mime") or "image/svg+xml"
        bp = obj.get("blob_path") or obj.get("path")
        if bp and Path(bp).is_file():
            try:
                raw = Path(bp).read_bytes()
            except OSError:
                return ""
            b64 = base64.b64encode(raw).decode("ascii")
            return f"data:{mime};base64,{b64}"
        if obj.get("data"):
            return f"data:{mime};base64,{obj['data']}"
    return ""


# ---- 分类食物图标（DEMO 无真实图时的图形兜底，不是字） --------------------

_FOOD_ICONS = {
    "burger": (
        '<path d="M28 54 Q60 34 92 54 Q60 48 28 54 Z" fill="#e8a93b"/>'
        '<circle cx="44" cy="48" r="1.6" fill="#fff7d6"/><circle cx="58" cy="45" r="1.6" fill="#fff7d6"/>'
        '<circle cx="72" cy="48" r="1.6" fill="#fff7d6"/>'
        '<rect x="30" y="54" width="60" height="11" rx="5" fill="#7c4a1d"/>'
        '<path d="M28 65 q7 -6 14 0 t14 0 t14 0 t14 0" fill="none" stroke="#3fae5a" stroke-width="5" stroke-linecap="round"/>'
        '<path d="M30 68 h60 q5 16 -4 20 q-26 8 -52 0 q-9 -4 -4 -20 Z" fill="#e8a93b"/>'
    ),
    "fries": (
        '<path d="M40 58 L46 106 L74 106 L80 58 Z" fill="#DA291C"/>'
        '<path d="M40 58 L80 58 L75 67 L45 67 Z" fill="#b71c1c"/>'
        '<rect x="50" y="34" width="6" height="32" rx="3" fill="#FFC72C" transform="rotate(-10 53 50)"/>'
        '<rect x="59" y="30" width="6" height="36" rx="3" fill="#FFD34D" transform="rotate(3 62 48)"/>'
        '<rect x="68" y="36" width="6" height="30" rx="3" fill="#FFC72C" transform="rotate(13 71 51)"/>'
    ),
    "drink": (
        '<path d="M46 52 L52 106 L68 106 L74 52 Z" fill="#ffffff" stroke="#DA291C" stroke-width="2.5"/>'
        '<rect x="43" y="45" width="34" height="9" rx="3" fill="#DA291C"/>'
        '<rect x="63" y="26" width="5" height="32" rx="2.5" fill="#DA291C" transform="rotate(13 65 42)"/>'
    ),
    "dessert": (
        '<path d="M52 66 L60 108 L68 66 Z" fill="#e8c98a" stroke="#c9a86a" stroke-width="1.5"/>'
        '<circle cx="60" cy="54" r="17" fill="#fff"/>'
        '<circle cx="54" cy="50" r="5" fill="#ffe0ec" opacity="0.7"/>'
        '<circle cx="66" cy="52" r="4" fill="#ffd9e6" opacity="0.7"/>'
    ),
    "chicken": (
        '<path d="M42 46 q24 -12 38 8 q11 16 -2 30 q-14 13 -32 2 q-15 -13 -4 -40 Z" fill="#c8893a"/>'
        '<path d="M42 46 q-8 -2 -10 6 q-2 8 6 9" fill="none" stroke="#c8893a" stroke-width="6" stroke-linecap="round"/>'
        '<rect x="28" y="44" width="11" height="13" rx="5" fill="#fff"/>'
    ),
    "salad": (
        '<path d="M30 66 a30 24 0 0 0 60 0 Z" fill="#ffffff" stroke="#9e9e9e" stroke-width="2.5"/>'
        '<path d="M38 62 q7 -16 15 -9 q9 -11 17 0 q9 -7 11 7" fill="none" stroke="#3fae5a" stroke-width="4.5" stroke-linecap="round"/>'
        '<circle cx="50" cy="58" r="3" fill="#ff7043"/><circle cx="64" cy="60" r="3" fill="#ffca28"/>'
    ),
}


def _food_icon(category: str, name: str) -> str:
    cat = (category or "").strip()
    if cat in ("汉堡", "堡"):
        return _FOOD_ICONS["burger"]
    if cat in ("小食", "小吃", "炸鸡"):
        return _FOOD_ICONS["chicken"] if ("鸡" in name) else _FOOD_ICONS["fries"]
    if cat in ("饮料", "饮品"):
        return _FOOD_ICONS["drink"]
    if cat in ("甜品", "甜点"):
        return _FOOD_ICONS["dessert"]
    if cat in ("沙拉", "轻食"):
        return _FOOD_ICONS["salad"]
    # 兜底：按名字猜
    if "薯" in name or "鸡" in name or "翅" in name or "麦乐鸡" in name:
        return _FOOD_ICONS["fries"] if "薯" in name else _FOOD_ICONS["chicken"]
    if "可乐" in name or "饮" in name or "咖啡" in name or "茶" in name or "果汁" in name:
        return _FOOD_ICONS["drink"]
    if "圣代" in name or "旋风" in name or "冰淇淋" in name or "派" in name or "圆筒" in name:
        return _FOOD_ICONS["dessert"]
    if "沙拉" in name or "玉米" in name or "蔬菜" in name:
        return _FOOD_ICONS["salad"]
    return _FOOD_ICONS["burger"]


def category_icon_datauri(name: str, category: str = "", rarity: str = "N") -> str:
    """没有真实图时，用「分类食物图标 + 金属徽章底」做图形兜底（是图，不是字）。"""
    rim = RARITY_COLOR.get(rarity, "#9e9e9e")
    inner = _food_icon(category, name)
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="120" height="120" viewBox="0 0 120 120">'
        f'<defs><radialGradient id="bg" cx="38%" cy="30%" r="80%">'
        f'<stop offset="0%" stop-color="#fff3c4"/>'
        f'<stop offset="60%" stop-color="#f0c64e"/>'
        f'<stop offset="100%" stop-color="#d99f1e"/>'
        f'</radialGradient></defs>'
        f'<circle cx="60" cy="60" r="56" fill="url(#bg)" stroke="{rim}" stroke-width="4"/>'
        f'<circle cx="60" cy="60" r="46" fill="none" stroke="#ffffff" stroke-opacity="0.5" stroke-width="1.5"/>'
        f'{inner}'
        f'</svg>'
    )
    b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{b64}"


def card_image(meal: dict[str, Any]) -> str:
    """返回卡面图：LIVE 用真实产品图（麦当劳 MCP 原图）包金属框；
    DEMO 有本地图用本地图；都没有则用「分类食物图标」图形兜底（不是字）。"""
    img = meal.get("image")
    resolved = resolve_image(img)
    if resolved:
        return resolved
    return category_icon_datauri(str(meal.get("name", "")), str(meal.get("category", "")), meal.get("rarity", "N"))
