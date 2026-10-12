#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
麦麦图鉴 · HTML 生成器 dex_card.py
================================

把「麦门开卡结果 + 图鉴汇总 + 图鉴墙（含点亮）+ 套餐工坊 + 麦门最爱报告」渲染成一份
自包含（内联 CSS/JS）的 HTML，麦当劳红黄配色、明亮、有收集乐趣。

设计要点（参赛改版）：
- 卡面一律不用 emoji：LIVE 用麦当劳 MCP 原图 + 金属质感徽章框；DEMO 用内联金属徽章 SVG。
- UI 含金拱门（Golden Arches）元素：页头 logo、各区块标题小拱、开卡舞台大拱。
- 麦门开卡动画：金拱门中央一条拉链，按住从上往下滑到底 → 推门（金拱门）动画 →
  门后金光闪过 → 现身抽中的产品。
- 个性化定制融入产品本身：每张卡/图鉴格/最爱榜一都标注「你的定制」，点单指令默认带上次选择，
  不单独占用一个区块。
- 新增「图鉴汇总」区块：总收集/点亮 + 各稀有度 拥有/点亮 一览。
- 麦门开卡舞台内嵌「用抽中的卡定制专属套餐」构建器（勾选抽中卡 + 每卡定制 + 套餐名 → 一键生成下单/收藏指令）。

命令行：
    python dex_card.py --out 麦麦图鉴.html [--store SZ001] [--draw 1] [--mode LIVE|DEMO]
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

from mcd_client import MCDClient
from gacha import draw, dex, achievements, LIT_THRESHOLD
from favorites import report
from combo import list_combos
from personalization import all_prefs
from classify import resolve_image

SKILL_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = SKILL_DIR / "assets"

RARITY_COLOR = {"N": "#9e9e9e", "R": "#2196f3", "SR": "#9c27b0", "SSR": "#ff9800"}
RARITY_LABEL = {"N": "普通", "R": "稀有", "SR": "史诗", "SSR": "传说"}

_arch_counter = 0


def esc(s) -> str:
    return html.escape(str(s))


# ---------------------------------------------------------------------------
# 金拱门（Golden Arches）SVG 组件
# ---------------------------------------------------------------------------

def arches_svg(size: int = 40, cls: str = "arch") -> str:
    """返回一个金色双拱「M」形 SVG（金属渐变描边），cls 控制尺寸/位置。"""
    global _arch_counter
    _arch_counter += 1
    gid = f"ag{_arch_counter}"
    h = int(size * 0.66)
    return (
        f'<svg class="{cls}" width="{size}" height="{h}" viewBox="0 0 120 80" '
        f'xmlns="http://www.w3.org/2000/svg" aria-label="金拱门">'
        f'<defs><linearGradient id="{gid}" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0%" stop-color="#FFE89A"/>'
        f'<stop offset="45%" stop-color="#FFC72C"/>'
        f'<stop offset="100%" stop-color="#E0A011"/>'
        f'</linearGradient></defs>'
        f'<path d="M12 78 L12 38 Q12 14 36 14 Q60 14 60 38 L60 78 '
        f'M60 78 L60 38 Q60 14 84 14 Q108 14 108 38 L108 78" '
        f'fill="none" stroke="url(#{gid})" stroke-width="16" '
        f'stroke-linecap="round" stroke-linejoin="round"/>'
        f'</svg>'
    )


# ---------------------------------------------------------------------------
# 卡面图：LIVE 真实图包金属徽章框；DEMO 内联金属徽章；全程不用 emoji
# ---------------------------------------------------------------------------

def img_html(src: str, cls: str = "cimg") -> str:
    """卡面图：把任意来源（MCP 原图 blob 引用 / data URI / URL / 本地图）解析成真图，
    再包一层金属徽章框（含高光）；解析不出真图时回退到分类食物图标徽章，绝不用 emoji 当图。"""
    resolved = resolve_image(src)
    if not resolved:
        return '<span class="imgwrap"><span class="ph">MCD</span></span>'
    return (f'<span class="badge {cls}-wrap"><img class="{cls}" src="{esc(resolved)}" alt="">'
            f'<span class="sheen"></span></span>')


# ---------------------------------------------------------------------------
# 个性化：把定制需求「嵌进产品」而不是单独成块
# ---------------------------------------------------------------------------

def _pref_list(code, prefs) -> list:
    entry = (prefs or {}).get(str(code))
    if isinstance(entry, dict):
        return entry.get("prefs", [])
    return []


def _order_req(name: str, code, store: str, prefs, qty: int = 1) -> str:
    """点单指令：默认带上该产品的上次定制（个性化融入产品）。"""
    lst = _pref_list(code, prefs)
    suf = ("；定制：" + "，".join(lst)) if lst else ""
    return f"请帮我下单：{name} ×{qty}，门店 {store}{suf}（来自麦麦图鉴）"


# ---------------------------------------------------------------------------
# 各区块
# ---------------------------------------------------------------------------

def _card_html(card: dict, prefs, store: str) -> str:
    rar = card.get("rarity", "N")
    color = RARITY_COLOR.get(rar, "#9e9e9e")
    badge = "新" if card.get("is_new") else ""
    lit = " · 已点亮" if card.get("lit") else ""
    pl = _pref_list(card.get("code"), prefs)
    pref_tag = f'<div class="cpref">你的定制：{esc("，".join(pl))}</div>' if pl else ""
    req = _order_req(card.get("name", ""), card.get("code"), store, prefs)
    return f"""
    <div class="gacha-card" data-code="{esc(card.get('code', ''))}" style="border-color:{color}">
      <div class="rar" style="background:{color}">{esc(RARITY_LABEL.get(rar, rar))}{(' · ' + badge) if badge else ''}</div>
      {img_html(card.get('image', ''), 'cimg')}
      <div class="cname">{esc(card.get('name', ''))}{lit}</div>
      <div class="cmeta">{esc(card.get('category', ''))} · ¥{esc(card.get('price', ''))} · {esc(card.get('flavor', ''))}</div>
      <div class="ctags">{' '.join('#' + esc(t) for t in card.get('tags', []))}</div>
      {pref_tag}
      <button class="mini-order" onclick="copyOrder({json.dumps(req)})">点单</button>
      <div class="cown">已拥有 ×{esc(card.get('owned_count', 1))}</div>
    </div>"""


def _draw_stage(draw_data: dict | None, prefs, store: str) -> str:
    """麦门开卡舞台：金拱门 + 拉链 + 推门 + 金光 + 现身产品。并附「用抽中的卡定制专属套餐」。"""
    if not draw_data or not draw_data.get("cards"):
        return ""
    cards = "".join(_card_html(c, prefs, store) for c in draw_data["cards"])
    tk = draw_data.get("tickets", {})
    hint = draw_data.get("hint", "")
    # —— 用抽中的卡定制专属套餐（嵌入个性化，默认带上次的选择） ——
    cb_items = ""
    for c in draw_data["cards"]:
        code = c.get("code", "")
        name = c.get("name", "")
        pl = _pref_list(code, prefs)
        pref_val = "，".join(pl) if pl else ""
        cb_items += (
            f'<label class="cb-item">'
            f'<span class="cb-head"><input type="checkbox" class="cb-pick" data-code="{esc(code)}" '
            f'data-name="{esc(name)}" checked> {esc(name)}</span>'
            f'<input type="text" class="cb-pref" data-code="{esc(code)}" value="{esc(pref_val)}" '
            f'placeholder="定制，如 不要酸黄瓜"></label>'
        )
    builder = (
        f'<button class="build-combo-btn" type="button" onclick="toggleComboBuilder()">'
        f'用抽中的卡定制专属套餐</button>'
        f'<div class="combo-builder" id="comboBuilder" hidden>'
        f'<p class="hint">勾选想组进套餐的卡，可给每张加定制需求（默认带上次的选择）。至少 2 张即可组成专属套餐。</p>'
        f'<div class="cb-list">{cb_items}</div>'
        f'<input type="text" id="comboName" class="cb-name" placeholder="给你的套餐起个名，如「我的欧气套餐」">'
        f'<div class="cb-actions"><button class="order-btn small" type="button" onclick="copyComboPlan()">'
        f'生成套餐指令（下单 / 收藏）</button></div>'
        f'<div class="toast" id="comboToast"></div>'
        f'</div>'
    )
    return f"""
    <section class="block">
      <h2>{arches_svg(26, 'h-arch')} 麦门开卡 <span class="cat-prog">本次抽中 {esc(draw_data.get('drawn', 0))} 张</span></h2>
      <div class="open-stage" id="openStage">
        <div class="arch-top">{arches_svg(150, 'arch-big')}</div>
        <div class="doorway">
          <div class="reveal">{cards}</div>
          <div class="flash"></div>
          <div class="door door-l"></div>
          <div class="door door-r"></div>
        </div>
        <div class="zipper" id="zipper">
          <div class="zip-track"></div>
          <div class="zip-seam"></div>
          <div class="zip-tab" id="zipTab"></div>
        </div>
      </div>
      <button class="open-now" id="openNow" type="button">拉开金拱门</button>
      <p class="stage-tip" id="stageTip">按住拉链，从上往下滑到底，推开金拱门，金光后现身你的产品</p>
      <p class="hint">剩余抽卡券：每日免费 <b>{esc(tk.get('daily', 0))}</b> · 额外券 <b>{esc(tk.get('bonus', 0))}</b> {esc(hint)}</p>
      {builder}
    </section>"""


def _summary_section(dex_data: dict) -> str:
    """图鉴汇总：总收集/点亮 + 各稀有度 拥有/点亮 一览。"""
    p = dex_data.get("progress", {})
    lit = dex_data.get("lit", {})
    grid = dex_data.get("grid", [])
    per: dict = {}
    for g in grid:
        r = g.get("rarity", "N")
        d = per.setdefault(r, {"owned": 0, "lit": 0, "total": 0})
        d["total"] += 1
        if g.get("owned"):
            d["owned"] += 1
        if g.get("lit"):
            d["lit"] += 1
    chips = ""
    for r in ["N", "R", "SR", "SSR"]:
        d = per.get(r, {"owned": 0, "lit": 0, "total": 0})
        chips += (f'<span class="sum-chip" style="border-color:{RARITY_COLOR.get(r)}">'
                  f'<b style="color:{RARITY_COLOR.get(r)}">{esc(RARITY_LABEL.get(r, r))}</b> '
                  f'拥有 {d["owned"]}/{d["total"]} · 点亮 {d["lit"]}</span>')
    return f"""
    <section class="block">
      <h2>{arches_svg(26, 'h-arch')} 图鉴汇总</h2>
      <div class="sum-grid">
        <div class="sum-num"><span class="big">{esc(p.get('owned', 0))}</span><span class="lab">已收集 / 共 {esc(p.get('total', 0))}（{esc(p.get('pct', 0))}%）</span></div>
        <div class="sum-num"><span class="big" style="color:#FFC72C">{esc(lit.get('count', 0))}</span><span class="lab">已点亮 / 共 {esc(lit.get('total', 0))}（{esc(lit.get('pct', 0))}%）</span></div>
      </div>
      <div class="sum-chips">{chips}</div>
      <p class="hint">点亮规则：普通卡下单 {LIT_THRESHOLD['N']} 次 / 稀有 {LIT_THRESHOLD['R']} 次 / 史诗 {LIT_THRESHOLD['SR']} 次 / 传说 {LIT_THRESHOLD['SSR']} 次自动点亮；点亮的卡可自由组合成专属套餐。</p>
    </section>"""


def _dex_section(dex_data: dict, prefs, store: str) -> str:
    cats = dex_data.get("categories", {})
    grid = dex_data.get("grid", [])
    p = dex_data.get("progress", {})
    lit = dex_data.get("lit", {})
    blocks = ""
    for cat, info in cats.items():
        items = [g for g in grid if g.get("category") == cat]
        cells = ""
        for g in items:
            rar = g.get("rarity", "N")
            color = RARITY_COLOR.get(rar, "#9e9e9e")
            owned = g.get("owned", 0) > 0
            is_lit = g.get("lit", False)
            style = "" if owned else "filter:grayscale(1);opacity:.45"
            name = esc(g.get("name", "")) if owned else "？？？"
            lit_badge = '<span class="lit">点亮</span>' if is_lit else ""
            pl = _pref_list(g.get("code"), prefs)
            pref_tag = f'<div class="dx-pref">定制：{esc("，".join(pl))}</div>' if pl else ""
            req = _order_req(g.get("name", ""), g.get("code"), store, prefs)
            cells += f"""
            <div class="dex-cell" style="border-color:{color};{style}">
              <div class="dx-rar" style="color:{color}">{esc(RARITY_LABEL.get(rar, rar))}</div>
              {img_html(g.get('image', ''), 'dximg')}
              <div class="dx-name">{name}</div>
              <div class="dx-own">{'×' + str(g.get('owned', 0)) if owned else '未解锁'}</div>
              {lit_badge}
              {pref_tag}
              <button class="mini-order sm" onclick="copyOrder({json.dumps(req)})">点单</button>
            </div>"""
        blocks += f"""
        <div class="cat-block">
          <h3>{esc(cat)} <span class="cat-prog">{info.get('owned', 0)}/{info.get('total', 0)} · 点亮 {info.get('lit', 0)}</span></h3>
          <div class="dex-row">{cells}</div>
        </div>"""
    return f"""
    <section class="block">
      <h2>{arches_svg(26, 'h-arch')} 麦麦图鉴 <span class="cat-prog">已收集 {p.get('owned', 0)}/{p.get('total', 0)}（{p.get('pct', 0)}%）· 点亮 {lit.get('count', 0)}/{lit.get('total', 0)}</span></h2>
      {blocks}
    </section>"""


def _combo_section(store: str, prefs) -> str:
    try:
        data = list_combos()
    except Exception:
        data = {"combos": []}
    combos = data.get("combos", [])
    cards = ""
    for c in combos:
        items_html = ""
        suffix_parts = []
        for it in c.get("items", []):
            items_html += f'<span class="ci">{esc(it.get("name", it.get("code")))} ×{it.get("qty", 1)}</span>'
            pl = _pref_list(it.get("code"), prefs)
            if pl:
                suffix_parts.append(f"{it.get('name', it.get('code'))}：{('，'.join(pl))}")
        req = ("请帮我下单套餐【" + c.get("name", "") + "】："
               + "、".join(f"{it.get('name', it.get('code'))}×{it.get('qty', 1)}" for it in c.get("items", []))
               + f" 门店 {c.get('store', store)}"
               + ("；定制：" + "；".join(suffix_parts) if suffix_parts else ""))
        cards += f"""
        <div class="combo-card">
          <div class="combo-name">{arches_svg(20, 'h-arch')} {esc(c.get('name', ''))}</div>
          <div class="combo-items">{items_html}</div>
          <button class="order-btn small" onclick="copyOrder({json.dumps(req)})">一键下单这份套餐</button>
        </div>"""
    if not cards:
        cards = '<p class="hint">还没有套餐。点亮的卡可以自由组合 —— 告诉我「把 巨无霸+大薯条+可乐 存成套餐叫『快乐水套餐』」就能创建。</p>'
    new_req = "记住：<餐品名> <个性化需求，如 不要酸黄瓜 / 少冰 / 多酱>"
    return f"""
    <section class="block">
      <h2>{arches_svg(26, 'h-arch')} 套餐工坊 <span class="cat-prog">{len(combos)} 个我的专属套餐</span></h2>
      <div class="combo-row">{cards}</div>
      <button class="ghost-btn" onclick="copyOrder({json.dumps(new_req)})">创建新套餐（复制指令发给我）</button>
    </section>"""


def _meme(fav: dict) -> str:
    """根据数据生成一句俏皮话/梗。"""
    ff = (fav.get("fav_flavor") or {}).get("name", "")
    ft = (fav.get("fav_time") or {}).get("name", "")
    lines = []
    flavor_meme = {
        "辣": "辣是成年人的勇气，你一口一个霸气。",
        "甜": "生活已经够苦了，甜的度你拿捏得死死的。",
        "芝士香": "芝士就是力量，你用胃验证了真理。",
        "香脆": "香脆党认证：快乐的声音就是咔嚓咔嚓。",
        "轻食": "嘴上说轻食，身体很诚实地点了麦门。",
        "解腻饮": "一口肉一口饮，解腻你是专业的。",
        "经典": "经典永流传，你的胃很有品味。",
    }
    lines.append(flavor_meme.get(ff, "麦当劳没有治不好的丧，只有还没点的单。"))
    if ft == "夜宵":
        lines.append("深夜的麦门，是成年人最后的秘密基地。")
    elif ft == "早餐":
        lines.append("别人的早 C 晚 A，你的早麦晚麦。")
    elif ft == "午餐":
        lines.append("午餐定点麦门，打工人的仪式感拉满。")
    lines.append("麦门永不为奴——但你的钱包偶尔会。")
    return " ".join(lines)


def _fav_section(fav: dict, fav_key: str, prefs) -> str:
    top = fav.get("fav_item")
    lb = fav.get("leaderboard", [])
    time_d = fav.get("time_distribution", {})
    flavor_d = fav.get("flavor_distribution", {})

    hero = ""
    if top:
        pl = _pref_list(top.get("code"), prefs)
        pref_tag = f'<div class="hero-pref">你的定制：{esc("，".join(pl))}</div>' if pl else ""
        req = _order_req(top.get("name", ""), top.get("code"), top.get("store", "SZ001"), prefs)
        hero = f"""
        <div class="hero" id="hero-{fav_key}">
          <div class="hero-top">最爱榜一</div>
          {img_html(top.get('image', ''), 'hero-img')}
          <div class="hero-name">{esc(top.get('name', ''))}</div>
          <div class="hero-meta">{esc(top.get('category', ''))} · {esc(top.get('flavor', ''))} · 点单 {esc(top.get('count', 0))} 次</div>
          {pref_tag}
          <button class="order-btn" onclick="copyOrder({json.dumps(req)})">一键复刻这份最爱</button>
          <div class="toast" id="toast-{fav_key}">已复制下单指令，粘到对话框发给我即可下单</div>
        </div>"""

    rows = ""
    for i, it in enumerate(lb, 1):
        hl = " hot" if i == 1 else ""
        rows += f"""
        <tr class="lb{i}{hl}">
          <td class="rk">{i}</td>
          <td>{esc(it['name'])}</td>
          <td>{esc(it.get('category', ''))}</td>
          <td>{esc(it.get('flavor', ''))}</td>
          <td class="num">{esc(it.get('count', 0))}</td>
          <td class="num">¥{esc(it.get('spent', 0))}</td>
        </tr>"""

    time_bars = "".join(f"<span class='pill'>{esc(k)} {v}</span>" for k, v in time_d.items())
    flavor_bars = "".join(f"<span class='pill'>{esc(k)} {v}</span>" for k, v in flavor_d.items())

    ft = fav.get("fav_time") or {}
    ff = fav.get("fav_flavor") or {}
    summ = (f"最爱单品：<b>{esc(top['name'])}</b> · 最爱时段：<b>{esc(ft.get('name', '—'))}</b> · "
            f"最爱口味：<b>{esc(ff.get('name', '—'))}</b>" if top else fav.get("note", ""))

    meme = _meme(fav)

    return f"""
    <section class="block">
      <h2>{arches_svg(26, 'h-arch')} 麦门最爱 · {esc(fav.get('period_label', ''))}
          <span class="cat-prog">{fav.get('orders_in_period', 0)} 单 · ¥{fav.get('total_spend', 0)}</span></h2>
      {hero}
      <p class="summary">{summ}</p>
      <p class="meme">{esc(meme)}</p>
      <table class="lb">
        <thead><tr><th>#</th><th>单品/套餐</th><th>分类</th><th>口味</th><th>次数</th><th>花费</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
      <div class="dist"><div class="dist-t">时段分布</div>{time_bars}</div>
      <div class="dist"><div class="dist-t">口味分布</div>{flavor_bars}</div>
      <button class="save-btn" onclick="saveShareCard('{fav_key}')">一键保存麦门最爱卡片（图片）</button>
    </section>"""


def _ach_section(ach_data: dict) -> str:
    earned = "".join(f"<span class='ach on'>{esc(a['name'])}</span>" for a in ach_data.get("earned", []))
    locked = "".join(f"<span class='ach off'>{esc(a['name'])}（{esc(a['desc'])}）</span>" for a in ach_data.get("locked", []))
    return f"""
    <section class="block">
      <h2>{arches_svg(26, 'h-arch')} 成就</h2>
      <div class="ach-row">{earned or '<span class="ach off">暂无，去麦门开卡/下单吧</span>'}</div>
      <div class="ach-row locked">{locked}</div>
    </section>"""


# ---------------------------------------------------------------------------
# 样式与脚本（普通花括号字符串，作为 .format() 的「值」直接插入，无需转义）
# ---------------------------------------------------------------------------

BASE_CSS = """
:root{--red:#DA291C;--yellow:#FFC72C;}
*{box-sizing:border-box}
body{margin:0;font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;background:#fff8ec;color:#2b2b2b}
.wrap{max-width:880px;margin:0 auto;padding:20px}
header{background:linear-gradient(135deg,var(--red),#b71c1c);color:#fff;border-radius:16px;padding:22px 24px;display:flex;align-items:center;gap:14px;box-shadow:0 6px 18px rgba(218,41,28,.25)}
header .logo{width:64px;height:42px;display:flex;align-items:center;justify-content:center}
header h1{margin:0;font-size:22px}
header p{margin:4px 0 0;opacity:.9;font-size:13px}
.mode{margin-left:auto;font-size:12px;background:rgba(255,255,255,.2);padding:4px 10px;border-radius:20px}
.block{background:#fff;border-radius:16px;padding:18px 20px;margin-top:18px;box-shadow:0 3px 10px rgba(0,0,0,.06)}
h2{font-size:18px;margin:0 0 14px;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.h-arch{width:26px;height:17px;vertical-align:middle}
h3{font-size:15px;margin:14px 0 8px}
.cat-prog{font-size:13px;color:#DA291C;font-weight:600;margin-left:auto}
.hint{color:#888;font-size:13px;margin:10px 0 0}
.gacha-row{display:flex;flex-wrap:wrap;gap:12px}
.gacha-card{width:150px;border:2px solid #ccc;border-radius:12px;padding:12px;background:#fff;position:relative}
.rar{position:absolute;top:-10px;left:10px;color:#fff;font-size:11px;padding:2px 8px;border-radius:10px}
.imgwrap{display:block;width:100%;height:96px;position:relative;text-align:center}
.badge{position:relative;display:inline-block;width:96px;height:96px;border-radius:50%;border:3px solid var(--yellow);box-shadow:0 2px 8px rgba(0,0,0,.15),inset 0 0 0 2px rgba(255,255,255,.4);overflow:hidden;vertical-align:middle}
.badge .cimg,.badge img{width:100%;height:100%;object-fit:cover;display:block}
.badge .sheen{position:absolute;top:0;left:-60%;width:50%;height:100%;background:linear-gradient(120deg,rgba(255,255,255,0) 0%,rgba(255,255,255,.55) 50%,rgba(255,255,255,0) 100%);transform:skewX(-20deg);animation:sheenMove 3.5s ease-in-out infinite}
@keyframes sheenMove{0%{left:-60%}55%{left:120%}100%{left:120%}}
.ph{position:absolute;left:0;right:0;top:36px;font-size:20px;font-weight:800;color:#DA291C}
.cimg{width:96px;height:96px;object-fit:cover;position:relative;z-index:2}
.dximg{width:64px;height:64px;object-fit:cover}
.cname{font-weight:700;font-size:15px;margin-top:6px}
.cmeta{font-size:12px;color:#666;margin-top:4px}
.ctags{font-size:11px;color:#DA291C;margin-top:4px}
.cown{font-size:12px;color:#999;margin-top:6px}
.cpref{font-size:11px;color:#0a7d2c;margin-top:4px;background:#eafaf0;border-radius:8px;padding:2px 6px;line-height:1.4}
.mini-order{margin-top:8px;background:var(--red);color:#fff;border:none;border-radius:18px;padding:5px 12px;font-size:12px;font-weight:700;cursor:pointer}
.mini-order.sm{padding:3px 9px;font-size:11px}
.mini-order:hover{background:#b71c1c}
.cat-block{margin-top:6px}
.dex-row{display:flex;flex-wrap:wrap;gap:10px}
.dex-cell{width:104px;border:2px solid #ccc;border-radius:10px;padding:8px;text-align:center;background:#fff;position:relative}
.dx-rar{font-size:11px;font-weight:700}
.dx-name{font-size:13px;font-weight:600;margin:4px 0}
.dx-own{font-size:11px;color:#999}
.dx-pref{font-size:10px;color:#0a7d2c;margin-top:3px;line-height:1.3}
.lit{position:absolute;bottom:-9px;left:50%;transform:translateX(-50%);font-size:10px;background:var(--yellow);color:#5a3d00;padding:1px 6px;border-radius:8px;white-space:nowrap}
.sum-grid{display:flex;gap:14px;flex-wrap:wrap}
.sum-num{flex:1;min-width:180px;background:linear-gradient(135deg,#fff3d6,#ffe7a8);border:2px solid var(--yellow);border-radius:14px;padding:14px;text-align:center}
.sum-num .big{display:block;font-size:34px;font-weight:800;color:var(--red)}
.sum-num .lab{font-size:13px;color:#666}
.sum-chips{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
.sum-chip{font-size:13px;border:2px solid #ccc;border-radius:20px;padding:5px 12px}
.ach-row{display:flex;flex-wrap:wrap;gap:8px;margin:6px 0}
.ach{font-size:13px;padding:5px 12px;border-radius:20px}
.ach.on{background:var(--yellow);color:#5a3d00;font-weight:600}
.ach.off{background:#f0f0f0;color:#999}
.hero{background:linear-gradient(135deg,#fff3d6,#ffe7a8);border:2px solid var(--yellow);border-radius:14px;padding:16px;text-align:center;margin-bottom:12px}
.hero-top{font-size:13px;color:#DA291C;font-weight:700}
.hero-img{width:84px;height:84px;object-fit:cover}
.hero-name{font-size:24px;font-weight:800;margin:4px 0}
.hero-meta{font-size:13px;color:#666}
.hero-pref{font-size:12px;color:#0a7d2c;margin-top:4px}
.order-btn{margin-top:12px;background:var(--red);color:#fff;border:none;border-radius:24px;padding:11px 22px;font-size:15px;font-weight:700;cursor:pointer}
.order-btn.small{padding:7px 14px;font-size:13px}
.order-btn:hover{background:#b71c1c}
.save-btn{margin-top:14px;background:#2b2b2b;color:#fff;border:none;border-radius:24px;padding:10px 20px;font-size:14px;font-weight:700;cursor:pointer}
.ghost-btn{margin-top:10px;background:#fff;color:var(--red);border:2px dashed var(--red);border-radius:24px;padding:9px 18px;font-size:14px;font-weight:700;cursor:pointer}
.toast{font-size:12px;color:#2e7d32;margin-top:8px;height:14px}
.summary{font-size:14px;margin:0 0 8px}
.meme{font-size:14px;color:#DA291C;background:#fff3f2;border-left:4px solid var(--red);padding:8px 12px;border-radius:8px;margin:10px 0;line-height:1.6}
table.lb{width:100%;border-collapse:collapse;font-size:13px;margin-top:6px}
table.lb th,table.lb td{padding:7px 6px;border-bottom:1px solid #eee;text-align:left}
table.lb th{color:#999;font-weight:600}
table.lb .num{text-align:right}
table.lb tr.hot td{background:#fff7e6;font-weight:600}
.dist{margin-top:12px;font-size:12px}
.dist-t{color:#999;margin-bottom:6px}
.pill{display:inline-block;background:#f5f5f5;border-radius:14px;padding:3px 10px;margin:0 6px 6px 0}
.note{font-size:12px;color:#999;margin-top:10px}
.build-combo-btn{display:block;margin:14px auto 0;background:linear-gradient(135deg,#FFC72C,#e0a011);color:#5a3d00;border:none;border-radius:24px;padding:10px 22px;font-size:14px;font-weight:700;cursor:pointer}
.build-combo-btn:hover{filter:brightness(1.05)}
.combo-builder{margin-top:14px;background:#fffaf0;border:2px dashed var(--yellow);border-radius:14px;padding:14px}
.cb-list{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0}
.cb-item{display:flex;flex-direction:column;gap:4px;background:#fff;border:1px solid #eee;border-radius:10px;padding:6px 8px;font-size:12px;width:150px}
.cb-head{font-weight:600;display:flex;align-items:center;gap:4px}
.cb-item input[type=text]{border:1px solid #ddd;border-radius:6px;padding:3px 6px;font-size:11px;width:100%}
.cb-name{width:100%;border:1px solid #ddd;border-radius:8px;padding:7px 10px;font-size:13px;margin-top:6px}
.cb-actions{margin-top:8px}
.combo-row{display:flex;flex-wrap:wrap;gap:12px}
.combo-card{width:240px;border:2px solid var(--yellow);border-radius:12px;padding:12px;background:#fffaf0}
.combo-name{font-weight:700;font-size:15px;display:flex;align-items:center;gap:4px}
.combo-items{margin:8px 0;font-size:13px;color:#555}
.ci{display:inline-block;background:#fff;border:1px solid #eee;border-radius:10px;padding:2px 8px;margin:0 4px 4px 0}
footer{text-align:center;color:#bbb;font-size:12px;margin:20px 0}
"""

STAGE_CSS = """
.open-stage{position:relative;height:340px;max-width:420px;margin:0 auto;perspective:1000px}
.arch-top{position:absolute;top:0;left:50%;transform:translateX(-50%);z-index:3;height:140px;display:flex;align-items:flex-end;justify-content:center}
.arch-top svg{filter:drop-shadow(0 3px 4px rgba(0,0,0,.2))}
.doorway{position:absolute;top:120px;left:50%;transform:translateX(-50%);width:76%;height:200px;border-radius:14px;overflow:hidden;background:#8a1212;box-shadow:inset 0 0 30px rgba(0,0,0,.45),0 6px 14px rgba(0,0,0,.2)}
.reveal{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;gap:8px;flex-wrap:wrap;padding:10px;opacity:0;transition:opacity .6s .3s}
.open-stage.open .reveal{opacity:1}
.reveal .gacha-card{width:118px;padding:8px}
.reveal .imgwrap{height:70px}
.reveal .badge{width:64px;height:64px}
.reveal .cname{font-size:13px}
.reveal .mini-order{margin-top:4px}
.flash{position:absolute;inset:0;background:radial-gradient(circle at 50% 45%,#fff7c0,#ffd34d 40%,transparent 72%);opacity:0}
.open-stage.open .flash{animation:flashGlow 1.1s ease-out .1s}
@keyframes flashGlow{0%{opacity:0;transform:scale(.4)}30%{opacity:.95}100%{opacity:0;transform:scale(1.3)}}
.door{position:absolute;top:0;height:100%;width:50%;background:linear-gradient(180deg,#ffd34d,#e0a011);border:2px solid #b8830c;backface-visibility:hidden;transition:transform .9s cubic-bezier(.6,.05,.3,1)}
.door-l{left:0;transform-origin:left center;border-right:1px solid #8a6508}
.door-r{right:0;transform-origin:right center;border-left:1px solid #8a6508}
.open-stage.open .door-l{transform:translateX(-100%) rotateY(-62deg)}
.open-stage.open .door-r{transform:translateX(100%) rotateY(62deg)}
.zipper{position:absolute;top:118px;left:50%;transform:translateX(-50%);width:12px;height:204px;z-index:4}
.zip-track{position:absolute;left:50%;top:0;transform:translateX(-50%);width:3px;height:100%;background:#5a3a00;border-radius:2px}
.zip-seam{position:absolute;left:50%;top:0;transform:translateX(-50%);width:6px;height:0;background:linear-gradient(180deg,#fff7d6,#ffd34d);box-shadow:0 0 8px #ffd34d;border-radius:3px}
.zip-tab{position:absolute;left:50%;top:0;transform:translate(-50%,-50%);width:34px;height:22px;border-radius:5px;background:linear-gradient(180deg,#fff,#cfcfcf);border:1px solid #888;cursor:grab;box-shadow:0 2px 5px rgba(0,0,0,.3);z-index:5}
.zip-tab:active{cursor:grabbing}
.open-stage.open .zipper{opacity:0;transition:opacity .4s;pointer-events:none}
.open-now{display:block;margin:14px auto 0;background:var(--red);color:#fff;border:none;border-radius:24px;padding:11px 26px;font-size:15px;font-weight:700;cursor:pointer}
.open-now:hover{background:#b71c1c}
.open-now:disabled{background:#bbb;cursor:default}
.stage-tip{text-align:center;font-size:13px;color:#DA291C;margin-top:10px}
"""

BASE_JS = """
function copyOrder(text){
  function show(id){var t=document.getElementById(id);if(t)t.textContent='已复制下单指令，粘到对话框发给我即可下单';}
  if(navigator.clipboard&&navigator.clipboard.writeText){
    navigator.clipboard.writeText(text).then(function(){show('toast');show('toast-week');show('toast-month');show('toast-all');},
      function(){prompt('复制下面这行发给我：',text);});
  }else{prompt('复制下面这行发给我：',text);}
}
function saveShareCard(key){
  var d=FAV[key]; if(!d) return;
  var c=document.getElementById('shareCanvas'); var x=c.getContext('2d');
  var W=640,H=900;
  var g=x.createLinearGradient(0,0,0,H); g.addColorStop(0,'#DA291C'); g.addColorStop(1,'#b71c1c');
  x.fillStyle=g; x.fillRect(0,0,W,H);
  x.fillStyle='#FFC72C'; x.fillRect(0,0,W,12); x.fillRect(0,H-12,W,12);
  x.fillStyle='#fff'; x.textAlign='center';
  x.font='bold 34px sans-serif'; x.fillText('我的麦门最爱',W/2,70);
  x.font='16px sans-serif';
  x.fillText((d.period_label||'')+' · 共 '+(d.orders_in_period||0)+' 单 · ¥'+(d.total_spend||0),W/2,100);
  // 金属徽章（canvas 自绘，不用 emoji）
  var cx=W/2, cy=235, r=70;
  var rg=x.createRadialGradient(cx-20,cy-25,8,cx,cy,r);
  rg.addColorStop(0,'#fff7d6'); rg.addColorStop(0.55,'#f5d04e'); rg.addColorStop(1,'#caa11f');
  x.beginPath(); x.arc(cx,cy,r,0,Math.PI*2); x.fillStyle=rg; x.fill();
  x.lineWidth=5; x.strokeStyle='#b8860b'; x.stroke();
  x.lineWidth=2; x.strokeStyle='rgba(255,255,255,0.6)'; x.beginPath(); x.arc(cx,cy,r-9,0,Math.PI*2); x.stroke();
  x.fillStyle='#4a3500'; x.font='bold 22px sans-serif'; x.textAlign='center';
  var nm=d.top_name||'—'; if(nm.length>5) nm=nm.slice(0,4)+'…';
  x.fillText(nm,cx,cy+8);
  x.font='12px sans-serif'; x.fillStyle='#5a4500'; x.fillText('MCD',cx,cy+30);
  x.fillStyle='#DA291C'; x.font='bold 16px sans-serif'; x.textAlign='center';
  x.fillText('最爱榜一',W/2,cy+r+30);
  x.fillStyle='#2b2b2b'; x.font='bold 26px sans-serif'; x.fillText((d.top_name||'—'),W/2,cy+r+62);
  x.fillStyle='#666'; x.font='14px sans-serif'; x.fillText((d.top_meta||'')+' · 点单 '+(d.top_count||0)+' 次',W/2,cy+r+88);
  x.fillStyle='#fff'; x.font='bold 20px sans-serif'; x.textAlign='left';
  x.fillText('最爱时段：'+(d.fav_time||'—'),80,cy+r+140);
  x.fillText('最爱口味：'+(d.fav_flavor||'—'),80,cy+r+182);
  x.fillText('最爱单品：'+(d.top_name||'—'),80,cy+r+224);
  x.fillStyle='#FFC72C'; x.font='15px sans-serif';
  wrapText(x,d.meme||'',80,cy+r+270,W-160,22);
  x.fillStyle='#fff'; x.font='bold 16px sans-serif';
  x.fillText('时段分布',80,cy+r+360);
  x.font='14px sans-serif'; var ty=cy+r+388; var line=[];
  for(var k in (d.time_dist||{})){ line.push(k+' '+d.time_dist[k]); }
  x.fillText(line.join('   '),80,ty);
  x.font='bold 16px sans-serif'; x.fillText('口味分布',80,ty+52);
  x.font='14px sans-serif'; var fl=[];
  for(var k2 in (d.flavor_dist||{})){ fl.push(k2+' '+d.flavor_dist[k2]); }
  x.fillText(fl.join('   '),80,ty+80);
  x.fillStyle='#FFC72C'; x.font='13px sans-serif'; x.textAlign='center';
  x.fillText('麦麦图鉴 · 麦当劳程序员节创意开发大赛（非官方）',W/2,H-40);
  c.toBlob(function(blob){var a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download='麦门最爱_'+(d.period_label||'report')+'.png'; a.click();},'image/png');
}
function roundRect(x,X,Y,w,h,r){x.beginPath();x.moveTo(X+r,Y);x.arcTo(X+w,Y,X+w,Y+h,r);x.arcTo(X+w,Y+h,X,Y+h,r);x.arcTo(X,Y+h,X,Y,r);x.arcTo(X,Y,X+w,Y,r);x.closePath();}
function wrapText(x,text,xx,yy,maxW,lh){var chars=text.split('');var line='';var yy2=yy;for(var i=0;i<chars.length;i++){var test=line+chars[i];if(x.measureText(test).width>maxW&&line){x.fillText(line,xx,yy2);line=chars[i];yy2+=lh;}else line=test;}x.fillText(line,xx,yy2);}
function toggleComboBuilder(){
  var b=document.getElementById('comboBuilder');
  if(b) b.hidden = !b.hidden;
}
function copyComboPlan(){
  var boxes=document.querySelectorAll('.cb-pick');
  var picks=[];
  for(var i=0;i<boxes.length;i++){
    var bx=boxes[i];
    if(bx.checked){
      var code=bx.getAttribute('data-code');
      var name=bx.getAttribute('data-name');
      var pf=document.querySelector('.cb-pref[data-code="'+code+'"]');
      var pref=pf?pf.value.trim():'';
      picks.push({code:code,name:name,pref:pref});
    }
  }
  if(picks.length<2){ alert('至少选 2 张卡来组套餐～'); return; }
  var cname=(document.getElementById('comboName').value.trim())||'我的麦门套餐';
  var items=[];
  for(var j=0;j<picks.length;j++){ items.push(picks[j].name+(picks[j].pref?('（'+picks[j].pref+'）'):'')); }
  var lines=[];
  lines.push('请帮我把刚抽到的卡定制成我的专属套餐，并直接下单：');
  lines.push('套餐名：《'+cname+'》，门店 '+STORE+'。');
  lines.push('包含：'+items.join('、')+'。');
  lines.push('这些卡可能还没点亮，请允许「未点亮卡」直接下单，并把这份套餐存为我的常点套餐（方便下次一键复刻）。');
  copyOrder(lines.join('\\n'));
  var t=document.getElementById('comboToast');
  if(t) t.textContent='已复制套餐指令，粘到对话框发给我即可下单 + 收藏';
}
"""

STAGE_JS = """
function setupZipper(stageId){
  var stage=document.getElementById(stageId); if(!stage) return;
  var tab=stage.querySelector('.zip-tab');
  var track=stage.querySelector('.zip-track');
  var seam=stage.querySelector('.zip-seam');
  var btn=document.getElementById('openNow');
  var tip=document.getElementById('stageTip');
  var opened=false; var dragging=false;
  function setProg(p){
    if(p<0)p=0; if(p>1)p=1;
    var h=track.clientHeight;
    tab.style.top=(p*h)+'px';
    seam.style.height=(p*h)+'px';
    if(p>=0.985 && !opened) openDoor();
  }
  function openDoor(){
    if(opened) return; opened=true;
    stage.classList.add('open');
    if(tip) tip.textContent='金拱门已开！这就是你抽中的产品';
    if(btn){btn.textContent='已开卡';btn.disabled=true;}
  }
  function y2p(cy){var r=track.getBoundingClientRect(); return (cy-r.top)/r.height;}
  tab.addEventListener('pointerdown',function(e){dragging=true;try{tab.setPointerCapture(e.pointerId);}catch(_){}e.preventDefault();});
  window.addEventListener('pointermove',function(e){if(!dragging)return;setProg(y2p(e.clientY));});
  window.addEventListener('pointerup',function(e){dragging=false;});
  if(btn) btn.addEventListener('click',function(){
    if(opened) return; var p=0;
    var iv=setInterval(function(){p+=0.03;setProg(p);if(p>=1){clearInterval(iv);openDoor();}},18);
  });
  setProg(0);
}
setupZipper('openStage');
"""


TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>麦麦图鉴 · 麦门开卡 + 麦门最爱</title>
<style>
{BASE_CSS}
{STAGE_CSS}
</style></head>
<body><div class="wrap">
<header>
  <div class="logo">{ARCH_SVG}</div>
  <div><h1>麦麦图鉴</h1><p>麦门开卡 · 图鉴汇总 · 麦门最爱 —— 用麦当劳 MCP 真实菜单养成的你的专属图鉴</p></div>
  <div class="mode">{MODE}</div>
</header>
{DRAW}{SUMMARY}{DEX}{COMBO}{ACH}{FAV_WEEK}{FAV_MONTH}{FAV_ALL}
<p class="note">数据来源：麦当劳官方 MCP（https://mcp.mcd.cn）。{MODE_NOTE}
  「麦门最爱」统计 = 经本 Skill 下的本地订单 + MCP 近 10 笔合并，越用越准。</p>
<footer>麦麦图鉴 · 麦当劳程序员节创意开发大赛参赛作品（非官方）</footer>
</div>
<canvas id="shareCanvas" width="640" height="900" style="display:none"></canvas>
<script>
const FAV = {FAV_JSON};
const STORE = "{STORE}";
{BASE_JS}
{STAGE_JS}
</script>
</body></html>"""


def _fav_min(d: dict) -> dict:
    """抽取分享卡所需的精简字段（去掉 emoji，标题改为麦门最爱）。"""
    top = d.get("fav_item") or {}
    ft = (d.get("fav_time") or {}).get("name", "—")
    ff = (d.get("fav_flavor") or {}).get("name", "—")
    return {
        "period_label": d.get("period_label", ""),
        "orders_in_period": d.get("orders_in_period", 0),
        "total_spend": d.get("total_spend", 0),
        "top_name": top.get("name", "—"),
        "top_meta": f'{top.get("category", "")} · {top.get("flavor", "")}',
        "top_count": top.get("count", 0),
        "fav_time": ft,
        "fav_flavor": ff,
        "time_dist": d.get("time_distribution", {}),
        "flavor_dist": d.get("flavor_distribution", {}),
        "meme": _meme(d),
    }


def render(out_path: str, store: str = "SZ001", draw_count: int = 0,
           client: MCDClient | None = None) -> dict:
    client = client or MCDClient()
    draw_data = draw(draw_count, store, client) if draw_count > 0 else None
    dex_data = dex(store, client)
    ach_data = achievements(store, client)
    fav_week = report("week", store, 5, client)
    fav_month = report("month", store, 5, client)
    fav_all = report("all", store, 5, client)
    prefs = all_prefs()

    mode = client.mode
    mode_note = ("无 Token 时为 DEMO 演示数据；配置麦当劳 MCP Token 后全部切换为真实菜单/订单。"
                 if mode == "DEMO" else "当前为 LIVE 真实数据。")

    fav_json = json.dumps({
        "week": _fav_min(fav_week),
        "month": _fav_min(fav_month),
        "all": _fav_min(fav_all),
    }, ensure_ascii=False)

    html_text = TEMPLATE.format(
        ARCH_SVG=arches_svg(44, "logo"),
        MODE=mode,
        MODE_NOTE=mode_note,
        DRAW=_draw_stage(draw_data, prefs, store),
        SUMMARY=_summary_section(dex_data),
        DEX=_dex_section(dex_data, prefs, store),
        COMBO=_combo_section(store, prefs),
        ACH=_ach_section(ach_data),
        FAV_WEEK=_fav_section(fav_week, "week", prefs),
        FAV_MONTH=_fav_section(fav_month, "month", prefs),
        FAV_ALL=_fav_section(fav_all, "all", prefs),
        FAV_JSON=fav_json,
        STORE=store,
        BASE_CSS=BASE_CSS,
        STAGE_CSS=STAGE_CSS,
        BASE_JS=BASE_JS,
        STAGE_JS=STAGE_JS,
    )
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_text, encoding="utf-8", newline="")
    return {"out": str(out), "mode": mode, "size": out.stat().st_size,
            "draw": draw_data, "progress": dex_data.get("progress")}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="麦麦图鉴 HTML 生成器")
    p.add_argument("--out", default="麦麦图鉴.html")
    p.add_argument("--store", default="SZ001")
    p.add_argument("--draw", type=int, default=0)
    p.add_argument("--mode", choices=["LIVE", "DEMO"])
    args = p.parse_args(argv)
    c = MCDClient(force_mode=args.mode)
    res = render(args.out, args.store, args.draw, c)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
