# MCP 接入说明 · 麦麦图鉴

本文件说明麦麦图鉴实际使用的麦当劳 MCP Server、Tool、调用流程与业务价值。

## 接入信息

- **Server 地址**：`https://mcp.mcd.cn`
- **协议**：Streamable HTTP
- **鉴权**：`Authorization: Bearer <token>`
- **限流**：每 Token 600 次/分钟（超出 429）；`401` = Token 失效
- **Token 申请**：https://open.mcd.cn/mcp

## 实际使用的工具（7 个，覆盖 3 类场景）

| 场景 | Tool | 在本项目中的用途 | 关键入参 | 关键返回 |
|---|---|---|---|---|
| 菜单 / 卡池 | `query-meals` | 拉取门店可售菜单作为麦门开卡卡池；定稀有度 | `storeCode`、`orderType`、`beType` | 分类 + 餐品（code/名称/价格/标签） |
| 餐品详情 | `query-meal-detail` | 看套餐组成、可替换项（图鉴卡详情） | `code`、`storeCode` | 套餐组成 `modification` |
| 算价 | `calculate-price` | 下单前校验真实价格（**单位是分**） | `storeCode`、`items[]` | `realTotalAmount`（分）、`takeWayList` |
| 历史订单 | `order-list` | 最爱统计的数据源之一（近 10 笔） | 无 | 近 10 笔订单 |
| 订单详情 | `query-order` | 单笔订单明细查询 | `orderId` | 订单详情 |
| 创建订单 | `create-order` | 一键复刻最爱 / 抽卡后直接下单 | `storeCode`、`items[]`、`beType` | `orderId` + **`payH5Url` 支付链接** |
| 当前时间 | `now-time-info` | 每日抽数重置的日期基准 | 无 | 当前日期时间 |

> 其余 26 个工具（优惠券、积分商城、活动、派对、营养等）本项目未使用，但架构预留了扩展位。

## 调用流程

### 流程 A：麦门开卡抽卡（核心玩法）
```
now-time-info（取日期 → 每日抽数重置）
   ↓
query-meals（取真实菜单 → 卡池 + 定稀有度 N/R/SR/SSR）
   ↓
[本地] 按稀有度加权随机抽卡 → 更新 collection.json（图鉴进度/抽卡日志）
   ↓
（可选）create-order：抽到的卡一键下单，落回真实点餐
```

### 流程 B：最爱统计（数据洞察）
```
order-list（近 10 笔真实订单）  ┐
   ├─ 合并去重 → 全量订单
本地 my_mcd_life.json（经本 Skill 下的单） ┘
   ↓
按周期（周/月/全部）过滤 → 统计：
  · 最爱单品/套餐（点单次数 Top1）
  · 最爱时段（早餐/午餐/下午茶/晚餐/夜宵）
  · 最爱口味（辣/甜/芝士香/香脆/轻食/解腻饮/经典）
   ↓
最爱榜一 → 生成「🍔 一键复刻」下单指令（create-order）
```

### 流程 C：一键复刻（下单，LIVE 二次确认）
```
用户确认 → calculate-price（校验真实价）→ create-order → 返回 payH5Url
   ↓
order_record 写入 my_mcd_life.json（供下次最爱统计）
```

## 业务价值

1. **把「点餐」从工具变成游戏**：真实菜单即卡池，降低「今天吃什么」的决策成本，同时提升麦当劳菜单的可探索性。
2. **用订单反哺洞察**：把用户散落的订单沉淀为「个人饮食画像」，最爱单品/时段/口味是 MCP `order-list` 原生不提供的增值分析——弥补了「MCP 仅返回近 10 笔」的短板。
3. **闭环到真实交易**：抽到的卡、最爱榜一都能一键下单，创意最终落在真实 GMV 上，而不是停留在展示层。
4. **零门槛演示**：DEMO 模式用 `@today+N` 相对日期的离线数据集，评委无需 Token 即可完整体验，降低评审成本。

## 降级与健壮性

- Token 缺失 / `401` / 网络故障 → 自动切 DEMO，绝不拒绝服务（`scripts/mcd_client.py` 的 `_call`）。
- `calculate-price` 返回金额单位为**分**，已在代码层统一换算。
- 所有图片失败均有占位兜底，不会因图挂了导致报告生成失败。
