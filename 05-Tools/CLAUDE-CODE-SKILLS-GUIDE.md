---
title: "Claude Code 技能日常操作指南"
source: "{{CODE_ROOT}}/Advice/Claude_Skills_Usage_Guide.md"
source-type: article
source-author: "Valiant程"
source-date: 2026-07-25
created: 2026-08-28
updated: 2026-09-04
type: source-notes
tags:
  - lang/tools
  - category/notes
  - topic/claude-code
  - topic/skills
status: stable
audience: both
confidence: high
authority: community
claim_risk: low
review_status: unreviewed
---

# Claude Code 技能日常操作指南

> 基于当前已安装的十二大技能，覆盖新功能开发、调试、项目学习、文档处理、文本润色、PPT 制作、视频创作、应用启动等常见场景。

## 核心技能

> ⚠️ **归档注记 (2026-09-04)**：本文为外部来源笔记。「核心技能」表的 **Superpowers** 行、「推荐工作流」第 1 条（brainstorming → writing-plans → subagent-driven-development → 子代理复核角色（自建））与「推荐优先级」中的 Superpowers 条目均引用 superpowers 技能集，**已于 2026-09-02 自本环境移除**。等效流程现为 vault 原生 `/vault-spark → /vault-plan → /vault-exec`（见 [[01-Rules/AGENT-CONDUCT]] §10）。

| 技能 | 一句话定位 | 关键命令 |
|------|-----------|---------|
| Superpowers | 开发流程规范化 | brainstorming / writing-plans / tdd / systematic-debugging |
| mattpocock/skills | 工程实践工具箱 | /grill-me /tdd /triage |
| CodeGraph | 代码知识图谱 | cg-explore / cg-trace / cg-impact |
| Understand-Anything | 交互式代码可视化 | /understand /understand-dashboard |
| markitdown | 文档格式转换 | /markitdown |
| stop-slop | 去除 AI 腔 | /stop-slop |
| 领域专题规范 | 前端界面设计 | /frontend-design |
| ppt-master | AI 驱动 PPT 生成 | /ppt-master |
| ponytail | 极简开发模式 | /ponytail |
| hyperframes | 视频与动画创作 | /hyperframes |
| caveman | 极致压缩输出 | /caveman |
| catalyst | 会话智能管理 | /catalyst-status |

## 推荐工作流

1. **新功能开发**：brainstorming → writing-plans → subagent-driven-development → code-review
2. **读懂陌生代码库**：/understand → /understand-dashboard → cg-explore
3. **调试 Bug**：systematic-debugging → cg-trace → sequential-thinking
4. **写文档/PPT**：/ppt-master → /stop-slop
5. **前端页面**：/frontend-design → chrome-devtools

## 推荐优先级

1. **codegraph MCP** — 代码库的"Ctrl+F on steroids"
2. **Understand Anything 插件** — 对任何陌生代码库一键理解
3. **Superpowers 插件** — 把"从想法到代码"变成可复现的流程
