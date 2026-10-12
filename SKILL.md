---
name: mcd-gacha-dex
description: 麦麦图鉴（MCD-GACHA-DEX）——把麦当劳真实菜单变成可收集的图鉴：每天 1 张免费抽卡 + 下单任意价格 +1 券 + 转发好友 +1 券；不同等级卡下单满 3/5/7/10 次自动点亮，点亮的卡可自由组合成专属套餐并一键下单，刚抽中的卡也能在开卡页现搭专属套餐（内嵌定制入口，含每卡个性化）；个性化需求直接嵌在产品卡上（点单默认带上次的选择，不单独成块）；并用真实订单算出本周/本月最爱单品、最爱时段、最爱口味，生成带梗的「麦门最爱」报告可一键存图。开卡动画是金拱门中央拉链（用户从上往下滑）→ 推门（金拱门）→ 门后金光闪过 → 现身抽中的产品；卡面用 MCP 原图加金属徽章质感，不用 emoji，UI 含金拱门元素，并有图鉴汇总区。触发词：麦麦图鉴、麦门开卡、抽卡、图鉴、收集、今天吃什么盲盒、我最爱吃什么、最爱统计、本月最爱、复刻最爱、麦当劳养成、套餐工坊、组合套餐、点亮、不要酸黄瓜、麦门最爱、保存图片。
agent_created: true
---

# 麦麦图鉴 · MCD-GACHA-DEX

## 这是什么（先读这段）

**它不是又一个「帮你点餐/省钱」的工具。** 市面上 90% 的参赛作品都在做同一件事：列菜单、算最省、推券。这是信息搬运。

**这个 Skill 做的是另一件事：把「吃麦当劳」变成一场可养成的收集游戏，再用你自己的订单反向算出「你到底最爱什么」。**

两条主线：

1. **麦门开卡 + 点亮 + 套餐工坊**：麦当劳的真实菜单就是卡池，每道菜按真实价格 + 标签定稀有度（N/R/SR/SSR）。**「开卡」即抽卡，金拱门开卡动画（拉链+推门+金光）就是产品的核心玩法。**
   - **抽卡券模型**：每天 1 张免费抽卡（按日期自动重置），**下单任意价格 +1 券**、**转发好友 +1 券**——越吃越能抽。
   - 稀有度概率经重平衡（N 60% / R 25% / SR 12% / SSR 3%），越稀有越珍贵。
   - **点亮规则**：普通卡(N)下单 3 次、稀有(R) 5 次、史诗(SR) 7 次、传说(SSR) 10 次自动点亮 💡。
   - **套餐工坊**：点亮的卡可自由组合成专属套餐（新图鉴），可取名、一键下单。
   - **个性化融入产品（不单独成块）**：每道菜的个性化需求（如「不要酸黄瓜」）直接标注在它的卡面/图鉴格/最爱榜一上，点单指令默认带上次的选择。
   - 抽到的卡 / 点亮的卡都可以**一键下单**——把游戏落回真实点餐。
2. **最爱统计（麦门最爱）**：基于你真实的订单（经本 Skill 下的单 + 麦当劳 MCP 近 10 笔合并），算出**本周/本月/全部**你最爱点的单品或套餐、最爱在什么时候吃、最爱什么口味，并排出「最爱榜」。**最爱榜一**带「一键复刻」按钮；整页带俏皮话/梗，并支持**一键保存成图片**分享。

**为什么不算换壳**：数据对象从「券/省钱」换成了「菜品收集进度 + 你的饮食偏好画像」；产品类型从「账单」换成了「抽卡养成 + 偏好洞察」；情绪价值从「肉疼」换成了「收集的爽感 + 被懂的感觉」。同样是趣味向玩法，但踩在真实菜单与真实订单之上，评委无 Token 也能跑通全流程。

## 数据来源（唯一）

麦当劳官方 MCP：`https://mcp.mcd.cn`（Streamable HTTP，Bearer Token）。
Token 从 `~/.workbuddy/mcp.json` 的 `mcd-mcp` 条目读取。工具清单见 `references/mcp-tools.md`。

**双模式（必须遵守）**：
1. **有 Token** → **LIVE 模式**：菜单、订单、下单全部来自真实接口，标注 🔴 LIVE。
2. **无 Token 或 Token 失效** → **DEMO 模式**：使用 `references/offline_menu.json`（含 `@today+N` 相对日期，演示永远有数据），标注 ⚪ DEMO。**绝不允许拒绝服务。**

Token 401 / 网络故障自动降级为 DEMO（见 `scripts/mcd_client.py` 的 `_call`）。

## 核心 MCP 工具调用

| 用途 | 工具 | 说明 |
|---|---|---|
| 菜单（卡池） | `query-meals` | 真实菜品 code/名称/分类/价格/标签，作为图鉴卡池 |
| 餐品详情 | `query-meal-detail` | 套餐组成、可替换项 |
| 算价 | `calculate-price` | 真实算价（**单位是分**），下单前校验 |
| 历史订单 | `order-list` | 近 10 笔订单，最爱统计的数据源之一 |
| 订单详情 | `query-order` | 单笔订单明细 |
| 创建订单 | `create-order` | 真实下单，返回 `payH5Url` 支付链接 |
| 当前时间 | `now-time-info` | 每日抽数重置的日期基准 |

> **关键约束**：麦当劳 `order-list` 只返回近 10 笔订单，无法单独支撑「本月/本周」统计。因此本 Skill 把**经它下的每一单都记到本地 `data/my_mcd_life.json`**，与 `order-list` 合并——越用越准。这正是对「MCP 原生只给近 10 笔」短板的弥补，也是作品的工程亮点之一。

## 能力与命令（给 Agent 的 SOP）

所有脚本在 `scripts/` 下，零第三方依赖（仅 Python 标准库）。运行方式：
`python scripts/<脚本>.py <子命令> [--mode LIVE|DEMO]`。不传 `--mode` 时自动按 Token 是否存在判定。

### 1. 麦门开卡（抽卡券模型）
用户说「麦门开卡」「抽卡」「今天吃什么盲盒」「来几张」：
```
python scripts/gacha.py draw --count 1        # 抽 1 张（消耗 1 张券）
python scripts/gacha.py status                # 看剩余抽卡券（每日免费 + 额外券）
python scripts/gacha.py share                 # 转发好友 +1 券
```
- **抽卡券来源**：① 每日 1 张免费（按 `now-time-info` 日期重置）；② 用本 Skill 下单任意价格 +1 券；③ 转发好友 +1 券。
- 稀有度概率：N 60% / R 25% / SR 12% / SSR 3%（重平衡，越稀有越难出）。
- 返回每张卡的 名称/稀有度/是否新解锁/口味/标签/卡面图。把结果念给用户，新解锁的卡重点提一句。
- 抽完可顺手生成图鉴卡（见第 6 步）。

### 2. 图鉴墙 / 收集进度
用户说「图鉴」「我收集了多少」「还差什么」：
```
python scripts/gacha.py dex
```
返回按分类的收集进度（已收集/总数）和每张卡的解锁状态。告诉用户「已收集 X/18（Y%）」，并指出最稀缺的稀有度。

### 3. 成就
用户说「成就」「我解锁了什么」：
```
python scripts/gacha.py achievements
```
返回已达成 + 未达成成就（集齐分类、全集、抽卡里程碑、抽到 SSR、点亮启蒙/十全十美/满堂点亮）。

### 4. 点亮与套餐工坊
**点亮规则**：某张卡被你「用本 Skill 真实下单」累计达到阈值就自动点亮 💡——
普通卡(N) 3 次 / 稀有卡(R) 5 次 / 史诗卡(SR) 7 次 / 传说卡(SSR) 10 次。
点亮状态由 `gacha.py` 的 `order_count` 跟踪（每次下单自动累加），`dex` 命令与图鉴卡都会标出 💡 点亮。

**套餐工坊**：点亮的卡可以自由组合成你的专属套餐（新图鉴），可取名、一键下单：
```
python scripts/combo.py create --name "快乐水套餐" --items "M003,S001,D001"
python scripts/combo.py create --name "现搭套餐" --items "M003,S001" --allow-unlit   # 允许未点亮卡现搭
python scripts/combo.py list
python scripts/combo.py order  --id <combo_id>      # 一键下单套餐（带个性化备注）
python scripts/combo.py delete --id <combo_id>
```
- 默认只有**已点亮**的卡能进套餐（`create` 会校验，未点亮的卡会明确提示缺哪几张）；
  加 `--allow-unlit` 可放宽——**刚抽到还没点亮的卡也能现搭套餐**。
- **抽卡页内嵌「用抽中的卡定制专属套餐」**：图鉴卡 HTML 的麦门开卡舞台下方有套餐构建器——
  勾选本次抽中的卡（默认全选）、给每张卡填定制需求（默认带上次的选择）、给套餐起名，
  点「生成套餐指令（下单 / 收藏）」复制一段指令，粘回对话框即可由 Agent 下单并存为常点套餐
  （Agent 执行时对未点亮卡用 `--allow-unlit`）。
- 套餐下单走 `order.py create`——同样 +1 抽卡券、累加点亮次数、自动带个性化备注。
- 用户也可自然语言：「把 巨无霸+大薯条+可乐 存成套餐叫『快乐水套餐』」，Agent 调 `combo.py create`。

### 5. 个性化记忆（记住口味，融入产品）
记住每道菜的个性化需求（如「不要酸黄瓜」「少冰」「多酱」），**下单时自动拼进备注(remark)**，并直接显示在它的卡面/图鉴格/最爱榜一上（点单默认带上次的选择，不单独成块）：
```
python scripts/personalization.py set  --code M003 --pref "不要酸黄瓜" --name "麦辣鸡腿堡"
python scripts/personalization.py list
python scripts/personalization.py get  --code M003
python scripts/personalization.py clear --code M003
```
- 用户说「记住：巨无霸 不要酸黄瓜」，Agent 调 `set`。之后只要点到它，LIVE 下单的 `create-order` 备注里会自动带上，DEMO 也会在订单记录里记一笔；图鉴卡/最爱卡上会标注「你的定制：不要酸黄瓜」，点单指令默认带上。
- 不再设独立的「口味备忘录」区块——个性化就长在产品自己身上。

### 6. 最爱统计（麦门最爱）
用户说「我最爱吃什么」「本月最爱」「本周最爱」「最爱统计」「我的麦门最爱」：
```
python scripts/favorites.py report --period month      # 本月
python scripts/favorites.py report --period week       # 近 7 天
python scripts/favorites.py report --period all        # 全部
```
向用户呈现：
- **最爱单品/套餐**（榜一，点单次数最多）
- **最爱时段**（早餐/午餐/下午茶/晚餐/夜宵）
- **最爱口味**（辣/甜/芝士香/香脆/轻食/解腻饮/经典）
- **最爱榜**（Top N，含次数与花费）
- 榜单越用越准的提示

### 7. 一键复刻最爱（下单，必须二次确认）
- 用户点了 HTML 里的「🍔 一键复刻」按钮（会复制一段下单指令发给你），或直接说「复刻榜一」「把最爱下单」：
  1. 解析出要下的单品 code 与门店（来自最爱榜一或用户指定）。
  2. **LIVE 模式必须先向用户二次确认**：「确认用门店 X 下单：麦辣鸡腿堡 ×1？」用户确认后才调用。
  3. 调用下单并记账：
     ```
     python scripts/order.py create --store <code> --items "M003:1"
     ```
     LIVE 返回 `payH5Url` → 把支付链接给用户；DEMO 返回模拟订单并标注「未产生真实交易」。
  4. 这笔订单自动写入 `data/my_mcd_life.json`，累加点亮次数、发放 +1 抽卡券，下次最爱统计会把它算进去。

### 8. 生成图鉴卡（HTML 报告，可存图）
用户说「生成图鉴」「给我看我的图鉴」「出个报告」「生成我的麦门最爱卡片」：
```
python scripts/dex_card.py --out 麦麦图鉴.html --draw 1
```
生成一份自包含（内联 CSS/JS）的 HTML，UI 含金拱门（Golden Arches）元素：
- **麦门开卡舞台**：金拱门中央一条拉链，按住从上往下滑到底（或点「拉开金拱门」）→ 推门（金拱门）动画 → 门后金光闪过 → 现身抽中的产品卡。舞台下方内嵌**「用抽中的卡定制专属套餐」构建器**（勾选抽中卡 + 每卡定制 + 套餐名 → 一键生成下单/收藏指令）。
- **图鉴汇总**：总收集/点亮 + 各稀有度（N/R/SR/SSR）拥有/点亮一览。
- **图鉴墙**（含 💡 点亮）→ **套餐工坊** → **成就** → 三段 **麦门最爱** 统计（周/月/全部）。
- **卡面一律不用 emoji，且必须是有图不是字**：卡面图统一经 `classify.resolve_image` 解析——
  LIVE 的 MCP `image` 字段是 `image_blob_ref` JSON（含本地 `blob_path`），会读 blob 文件转 base64 真图；
  `data:`/`http(s)`/`local:` 来源直接用。解析出真图后包**金属徽章框**（环形金边+高光动画）。
  彻底无图时用 `classify.category_icon_datauri` 的**分类食物图标徽章**（汉堡/薯条/饮料/甜品/炸鸡/沙拉
  六类纯 SVG 插画 + 金属渐变底）兜底——是图，不是字；「MCD」文字占位仅作最后兜底。
  卡面/图鉴格/最爱榜一上直接标注「你的定制」，点单默认带上次选择。
- 每段麦门最爱底部有「一键保存麦门最爱卡片（图片）」按钮——纯 canvas 自绘金属徽章分享卡，**离线可用、无外部依赖**，点一下下载 PNG 方便转发。
- 用 `present_files` 打开预览给用户。

## 红线

- **不伪造价格/订单数据。** 全部来自 `query-meals` / `calculate-price` / `order-list` / `create-order`。
- **下单必须二次确认**（LIVE）。DEMO 仅模拟，明确标注。
- **不因为 Token 缺失而拒绝服务**：无 Token 走 DEMO，照常能演示全流程。
- **不做医疗/营养建议**：口味/时段只是趣味洞察，不评「健不健康」。
- 卡面图：统一走 `classify.resolve_image`——LIVE 读 MCP `image_blob_ref` 的本地 blob 文件转 base64 真图，
  并包金属徽章框；DEMO 无真实图资产时用**分类食物图标徽章**（SVG 插画，不是字）兜底。
  **卡面一律不用 emoji**。绝不因图挂了而生成失败，失败时先回退分类图标、最后才回退「MCD」文字占位。
- 保持麦当劳红黄明亮配色，**不用阴间/晦气元素**。

## 目录说明

```
mcd-gacha-dex/
├── SKILL.md                       # 本文件
├── SUBMIT.md                      # 参赛提交指引
├── README.md                      # 项目介绍
├── CONTEST_DECLARATION.md         # 参赛声明（官方原文，不可改）
├── MCP_INTEGRATION.md             # MCP 接入说明
├── workbuddy.md                   # WorkBuddy 开发上下文（联动奖励用）
├── scripts/
│   ├── mcd_client.py              # MCP 客户端 + LIVE/DEMO 自动降级
│   ├── gacha.py                   # 麦门开卡引擎（稀有度/抽卡券/图鉴/点亮/成就）
│   ├── favorites.py               # 麦门最爱统计（周/月/单品/时段/口味 + 榜一）
│   ├── order_record.py            # 本地订单持久化（我的麦生）
│   ├── order.py                   # 下单 + 记账（发券/累加点亮/带个性化备注）
│   ├── combo.py                   # 套餐工坊（点亮卡组合 + 现搭 --allow-unlit + 一键下单）
│   ├── personalization.py         # 个性化记忆（记住口味，如不要酸黄瓜，融入产品卡）
│   ├── classify.py                # 口味/时段分类 + 卡面图解析(resolve_image) + 金属徽章/食物图标 SVG
│   └── dex_card.py                # 图鉴卡 HTML 生成器（金拱门开卡动画 + canvas 存图）
├── references/
│   ├── mcp-tools.md               # 33 个工具速查
│   └── offline_menu.json          # DEMO 离线数据集（含 @today+N）
├── data/                         # 本地生成（collection / my_mcd_life / combos / prefs，已 gitignore）
└── assets/                       # HTML 模板等
```

## 常用命令速查

```bash
cd scripts
python gacha.py draw --count 1              # 抽 1 张（消耗抽卡券）
python gacha.py status                     # 看抽卡券（每日免费 + 额外券）
python gacha.py share                      # 转发好友 +1 券
python gacha.py dex                        # 图鉴墙（含点亮状态）
python gacha.py achievements               # 成就
python favorites.py report --period month   # 本月最爱（麦门最爱）
python favorites.py report --period week    # 本周最爱
python order.py create --store SZ001 --items "M003:1"   # 下单+记账（+1券/累加点亮/带备注）
python combo.py create --name "快乐餐" --items "M003,S001"  # 套餐工坊
python combo.py order --id <combo_id>      # 一键下单套餐
python personalization.py set --code M003 --pref "不要酸黄瓜"  # 记住口味
python dex_card.py --out 麦麦图鉴.html --draw 1            # 生成图鉴卡（可存图）
```
