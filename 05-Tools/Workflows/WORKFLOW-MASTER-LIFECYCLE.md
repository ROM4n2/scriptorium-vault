---
title: "工程全生命周期作业流程与多 Agent 协同标准作业程序 (Master Lifecycle SOP)"
created: 2026-08-28
updated: 2026-08-28
type: notes
tags:
  - category/tools
  - category/workflows
  - topic/engineering-practices
status: stable
audience: both
authority: synthetic
claim_risk: medium
review_status: unreviewed
---

# 🚀 工程全生命周期作业流程与多 Agent 协同 SOP (Master Lifecycle)

> **定位**：定义开发者与多 AI Agent 在知识库全生命周期中的标准协同规范。
> **核心哲学**：**人类在前台发号施令并把控方向，AI 在后台自动查库、严密自审、主动排障与持续沉淀。**

---

## 全生命周期阶段速览

| # | 阶段 | 触发 | 核心产出 |
|---|---|---|---|
| 1 | 新项目筑基 | `/vault-bootstrap` | 安全钩子 + 规范锚点自动注入 |
| 2 | 方案设计 | `/vault-grill` + `/vault-adr` | 极限拷问后的架构决策 (ADR) |
| 3 | 特性开发 | `/vault-tdd` | Red-Green-Refactor 循环产出 |
| 4 | 性能压测 | `/vault-perf` | 竞态/慢查询/资源瓶颈报告 |
| 5 | 审查提交 | `/vault-review` + git | 红黄牌门禁 + 干净提交 |
| 6 | 排障沉淀 | `/vault-debug` + `/vault-save` | 根因修复 + 99-Inbox 复盘入库 |
| 7 | 记忆蒸馏 | `vault-memory-compactor.py` | Inbox 碎片合并晋级至正式区 |
| 8 | 面试演练 | `/vault-interview` | 闭卷答题 + 三段式点评 |

---

## 三大工程铁律 (Invariants)

1. **证据先于断言** -- 所有结论必须附带命令输出或单测证据，禁止空口声称。
2. **拒绝无脑迎合** -- AI 发现设计缺陷时必须提出建设性异议，讲明代价再交还决策权。
3. **离开时更干净** -- 每次变动比来之前更好一点；拒绝过度抽象，优先使用标准库。
