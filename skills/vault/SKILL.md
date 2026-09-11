---
name: vault
description: Master router and quick-reference directory for all Coding Vault skills. Use when user types /vault, asks for vault help, or needs natural language skill routing with environment auto-detection.
---

# Coding Vault Master Skill Router & Environment Detector

Intelligently detect workspace environment state and route developer intent to the optimal Coding Vault skill.

## 🧭 Environment-Aware Auto-Detection (Step 0)
Before routing, perform non-invasive environment inspection:
1. **Empty / Fresh Directory**: No `.git` or no `.githooks` ➔ Recommend `/vault-bootstrap`
2. **Existing Codebase (Unonboarded)**: No `.agent-context.md` ➔ Recommend `/vault-onboard`
3. **Active Implementation Plan**: `implementation_plan.md` or `.vault-exec-ledger.json` present ➔ Recommend `/vault-exec` or `/vault-pipeline`
4. **Fuzzy Idea / 0-to-1 Exploration**: Vague user prompt ➔ Recommend `/vault-spark` ➔ `/vault-grill`
5. **Bug / Outage / Test Failure**: Stack trace or error log ➔ Recommend `/vault-debug`

> **⚠️ 安装范围说明**：本目录（`skills/`）是模板随包子集——上表与矩阵中的
> `/vault-bootstrap` `/vault-onboard` `/vault-exec` `/vault-pipeline` `/vault-perf`
> `/vault-review` `/vault-refactor` `/vault-interview` **未随包分发**（深度工程技能）。
> 路由时若目标技能未安装，**跳过该推荐并改荐已安装的最近似技能**（默认 `/vault-plan`
> → `/vault-tdd` 链路）；不要把未安装技能当作可执行命令输出。

---

## 🗺️ 18-Skill Lifecycle Navigation Matrix

| Engineering Stage | Trigger Skill | Core Capability & Deliverable |
|---|---|---|
| **0. 环境与接手** | `/vault-bootstrap`<br>`/vault-onboard` | • 仓库安全与防泄露钩子筑基<br>• 代码库极速接手与 Ground Truth 单测基线捕获 |
| **1. 需求与架构** | `/vault-spark`<br>`/vault-grill`<br>`/vault-adr` | • 0到1需求发散与规格书生成<br>• 双镜头 (用户/技术) 极限审讯与前沿决策树<br>• MADR 架构决策自增归档 |
| **2. 规划与执行** | `/vault-plan`<br>`/vault-exec`<br>`/vault-pipeline` | • 细粒度任务拆解与子代理 Prompt 脚手架生成<br>• 多子代理 TDD 派发 + Maker-Checker 状态机 (Zero-Edit)<br>• 端到端 Git Worktree 隔离开发流水线 |
| **3. 质量与重构** | `/vault-tdd`<br>`/vault-refactor`<br>`/vault-debug` | • 契约 TDD 与伪绿变异防线<br>• 极简主义重构 (卫语句展平、YAGNI)<br>• 4步强制根因排障 (复现断言前置) |
| **4. 审计与基准** | `/vault-perf`<br>`/vault-review`<br>`/vault-team` | • 多语言基准压测 (-benchmem, -race, EXPLAIN)<br>• 7语言 RFC 2119 规范与红黄牌门禁<br>• 6大专家全栈 Swarm 并发会审 |
| **5. 沉淀与面试** | `/vault-save`<br>`/vault-handoff`<br>`/vault-interview` | • Karpathy 对话即沉淀 (前置查重入库 99-Inbox)<br>• 会话收尾与 1-Click 续接交接卡<br>• 1v1 高压技术答辩与自适应难度阶梯 |

---

## ⚡ Quick Intent Dispatch Examples
- User: *"帮我看看这个新项目"* ➔ Run `/vault-onboard`
- User: *"我想做一个新功能，但还不确定怎么设计"* ➔ Run `/vault-spark`
- User: *"这个报错怎么解决？"* ➔ Run `/vault-debug`
- User: *"准备开始写代码执行计划"* ➔ Run `/vault-exec`
- User: *"我们要结束今天的开发"* ➔ Run `/vault-handoff`
