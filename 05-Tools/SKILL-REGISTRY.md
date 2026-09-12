---
title: "Coding Vault 技能注册表与三层配合模型 (Skill Registry & Layered Model)"
created: 2026-09-02
updated: 2026-09-11
type: moc
tags:
  - category/moc
  - category/tools
  - topic/skills
  - topic/cc-switch
status: stable
audience: both
source: "全域 18-Skills 与 MCP 架构深度反思/第一性原理评估蓝图（2026-08-30）+ 实际技能池盘点（2026-09-02）"
authority: synthetic
claim_risk: none
review_status: unreviewed
---

# 🗂️ Shipped Skills Registry

> **本文件只索引、不复制**：技能实体真值源在各自层级的目录中（全局在 CC Switch、项目级在库内 `.claude/skills/`）。

---

## Shipped Skills (11 skills)

These 11 skills ship with the template package in `skills/`:

| # | Skill | Core Responsibility |
|---|---|---|
| 1 | `vault` | Master router -- detects workspace state and routes to the right skill |
| 2 | `vault-save` | Karpathy-style session-to-knowledge ingestion (dedup, frontmatter, 99-Inbox) |
| 3 | `vault-inbox-consolidate` | Inbox draft classification, routing, and promotion by frontmatter tags |
| 4 | `vault-handoff` | Session wrap-up with 1-click resumption handoff card |
| 5 | `vault-plan` | Task decomposition and subagent prompt scaffolding |
| 6 | `vault-exec` | Multi-subagent TDD dispatch with Maker-Checker state machine |
| 7 | `vault-adr` | MADR architecture decision record auto-numbering and archival |
| 8 | `vault-grill` | Socratic dual-lens (user + tech) architecture stress-testing |
| 9 | `vault-spark` | 0-to-1 idea exploration and spec generation |
| 10 | `vault-debug` | 4-step root-cause debugging with evidence-first protocol |
| 11 | `vault-team` | Parallel multi-expert swarm review and consensus synthesis |

---

## 关联索引

- 技能编写规范：[[01-Rules/SKILL-AUTHORING-SPEC]]
- 工具链总索引：[[00-MOC/MOC-Tools]]
