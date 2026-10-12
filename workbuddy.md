# WorkBuddy 开发上下文 · 麦麦图鉴

> 本文件用于核验是否符合「麦当劳程序员节创意开发大赛」WorkBuddy 联动奖励条件（提交 `workbuddy.md` 可额外获 3,000 积分）。

## 一句话

麦麦图鉴（MCD-GACHA-DEX）全程使用 **WorkBuddy** 开发：从概念澄清、架构设计、MCP 客户端与降级逻辑、麦门开卡引擎、最爱统计、订单记账与 HTML 报告生成，到参赛文档与提交校验，均在 WorkBuddy 对话中完成。

## 开发过程（与 WorkBuddy 协作的关键节点）

1. **概念去重（避免换壳）**：WorkBuddy 辅助我把创意拆成「数据对象 / 产品类型 / 对手」三个轴，确认麦门开卡图鉴是真正的新轴——数据从券变成菜品收集进度 + 饮食画像，类型从账单变成抽卡养成。
2. **MCP 能力梳理**：通过 WorkBuddy 拉取官方 `mcd-mcp-server` 的 33 个工具清单，按 9 类归并，锁定本项目实际用到的 7 个（菜单/详情/算价/订单/下单/时间）。
3. **双模式架构**：复用已验证的 `mcd_client` 自动降级范式（LIVE/DEMO，`@today+N` 离线兜底），保证评委无 Token 也能跑通。
4. **最爱统计的工程取舍**：发现 `order-list` 仅返回近 10 笔、无法支撑「本月」统计，于是设计「本地订单累积 + MCP 近 10 笔合并」的数据源，越用越准。
5. **端到端验证**：在 WorkBuddy 中用 Bash 工具以 DEMO 模式跑通 抽卡 → 图鉴 → 成就 → 最爱 → 下单+记账 → HTML 生成，并修复了 CLI 子命令 `--mode` 参数位置、DEMO 算价按 code 查不到名称导致记录总额偏低等问题。
6. **参赛合规校验**：核对官方报名格式，定位到旧作品 `#341` 审核未过的根因（报名 Issue 把项目地址写成了 Markdown 链接，违反「项目地址暂不要使用 Markdown 格式」的严格校验），并给出修正文本。

## 技术栈

- 语言：Python 3.13，**零第三方依赖**（仅标准库 `urllib`/`json`/`argparse`/`datetime`/`random`/`collections`）。
- 运行环境：WorkBuddy 自带的隔离 Python 运行时。
- 产物：可导入的 WorkBuddy Skill（`SKILL.md` + `scripts/` + `references/`），以及自包含 HTML 报告。

## 产出文件

```
mcd-gacha-dex/
├── SKILL.md / README.md / MCP_INTEGRATION.md / CONTEST_DECLARATION.md / workbuddy.md / SUBMIT.md
├── scripts/   (mcd_client, gacha, favorites, order_record, order, classify, dex_card)
├── references/ (mcp-tools.md, offline_menu.json)
└── data/      (collection.json, my_mcd_life.json —— 运行生成)
```

本作品为开发者独立创作，非麦当劳官方产品。
