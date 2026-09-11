---
title: "Claude Code 配置推荐"
source: "{{CODE_ROOT}}/Advice/claude-code-setup-guide.md"
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
  - topic/mcp
status: stable
audience: both
confidence: high
authority: community
claim_risk: low
review_status: unreviewed
---

# Claude Code 配置推荐

> 个人实践总结，适合推荐给初次使用 Claude Code 的开发者。

## MCP 服务器（6 个）

| MCP | 安装命令 | 用途 |
|-----|---------|------|
| codegraph | `npm i -g @anthropic-ai/codegraph` | 代码知识图谱 |
| context7 | `npx @upstash/context7-mcp` | 实时文档查询 |
| chrome-devtools | `npx chrome-devtools-mcp@latest` | 浏览器自动化 |
| sequential-thinking | `npx @modelcontextprotocol/server-sequential-thinking` | 结构化推理 |
| memory | `npx @modelcontextprotocol/server-memory` | 知识图谱记忆 |
| fetch | `uvx mcp-server-fetch` | 网页抓取 |

## 核心插件

> ⚠️ **归档注记 (2026-09-04)**：本文为外部来源笔记。所列 **Superpowers** 插件（下文第 2 项）及「高频 Skills Top 10」中的 writing-plans / subagent-driven-development / brainstorming / requesting-code-review 等条目均属 superpowers 技能集，**已于 2026-09-02 自本环境移除**（skill 层经 CC Switch 删除，插件层 `superpowers@superpowers-marketplace` 于 2026-09-04 卸载）。请勿据此重新安装。

1. **Understand Anything** — 代码理解全家桶（/understand 一键理解项目架构）
2. **Superpowers** — 开发方法论工具集（brainstorming + writing-plans + tdd 三件套）

## 高频 Skills Top 10

| Skill | 使用次数 | 场景 |
|-------|---------|------|
| grill-me | 32 | 方案抗压面试 |
| writing-plans | 12 | 多步骤任务先出计划 |
| subagent-driven-development | 9 | 大规模任务并行分发 |
| brainstorming | 7 | 创意/功能设计前对齐需求 |
| requesting-code-review | 8 | 完成后触发代码审查 |
| 领域专题规范 | 8 | 前端 UI 审美指导 |
| ppt-master | 5 | AI 驱动 PPT 生成 |
| ponytail | 5 | YAGNI 极简开发模式 |
| catalyst-status | 5 | 会话智能监控 |
| hyperframes | 2 | 视频/动画制作 |
