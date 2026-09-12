---
title: "子 Agent 注册表与派发管理指南 (Subagent Registry & Dispatch Guide)"
created: 2026-09-02
updated: 2026-09-02
type: rules
tags:
  - category/tools
  - topic/claude-code
  - topic/multi-agent
  - topic/agent-architecture
status: stable
audience: agent
source: "Coding Vault 子代理-* 入档 Claude Code agents 实战验证（2026-08-31）"
authority: synthetic
claim_risk: medium
review_status: unreviewed
---

# 🧭 子 Agent 注册表与派发管理指南 (Subagent Registry & Dispatch)

> **适用平台**：Claude Code 等以 `.claude/agents/*.md` 为注册表的原生子 Agent 环境。
> 本指南面向「维护 agent 注册表」与「在 Skill/文档里派发子 Agent」两件事。
> 角色定义文件本体见本目录 `子代理-*.md`；派发执行规范见 `vault-exec` 技能。

---

## 子 Agent 派发要点

子 Agent 是按需派发的独立执行单元，用于将耗时的、需要隔离上下文的工作从主会话中分离出去。派发时须注意：

- **注册时机**：Agent 在会话启动时扫描一次 `.claude/agents/*.md`，会话内新建的文件当场不生效。
- **静默降级风险**：如果派发了一个不存在的 agent type，主 Agent 会静默回退到通用 agent 继续执行，产出看似正常但实际未经专业审计。因此派发必须用表格明确 `subagent_type`，缺失时显式报错。
- **部署校验**：新增 agent 后必须重启会话并真派一次，未跑过不算完成。

---

## 关联索引

- 派发执行与断点状态机：[[01-Rules/AGENT-CONDUCT]] §10
- 工具链总索引：[[00-MOC/MOC-Tools]]
