---
title: "示例组说明（中立领域：高效阅读）"
created: 2026-09-10
updated: 2026-09-10
type: notes
tags:
  - category/notes
  - topic/onboarding
status: stable
audience: both
authority: synthetic
claim_risk: none
review_status: unreviewed
---

# 示例组说明

> 本目录是**最小示例组**：用一个中立领域（高效阅读）演示三件事——①双版本制（STANDARDS + CHEATSHEET）②ADR 决策记录 ③RCA 故障复盘。删掉本目录不影响模板运行。

## 为什么需要示例

模板的领域区（`02`–`09`）都是空壳。空壳能保持干净，但接收者会问「一篇合规笔记到底长什么样」。本目录用四个文件回答这个问题，且**不引入任何编程语境**——你可以把「阅读」换成任何你的领域。

## 看什么、学什么

| 文件 | 演示的东西 | 关键点 |
|---|---|---|
| 阅读方法规范 | **双版本制的上半** | RFC 2119 措辞（MUST/SHOULD/MAY）、每条规则可被 Agent 直接执行 |
| 阅读速查表 | **双版本制的下半** | 章节编号与 STANDARDS 1:1 对齐、一句话规则 + 最短示例 |
| ADR-0001 示例 | **决策留痕** | 上下文 → 备选 → 决策 → 后果，五段式 |
| RCA 示例 | **复盘留痕** | 现象 → 根因（5 Whys）→ 改进项 → 验证方式 |

## 如何使用

1. 读一遍 STANDARDS 与 CHEATSHEET，理解「同一套规则的两个读者版本」；
2. 把你的领域写进 `03-Languages/`（或任意领域区）：`<你的主题>-STANDARDS.md` + `<你的主题>-CHEATSHEET.md`；
3. 决策用 `Templates/tpl-adr.md`，故障用 `Templates/tpl-rca.md`；
4. 写完跑 `python scripts/vault-quality-check.py --strict` 自检。

## 关联

- 目录职责与归属裁决：[[01-Rules/VAULT-STRUCTURE]]
- 摄取与沉淀管线：[[01-Rules/INGESTION-WORKFLOW]]
- 使用教程：[[TUTORIAL]]
