---
title: "随包技能子集（skills/）"
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

# 随包技能子集

> 本目录是**可选增强**：11 个与知识库运作直接相关的 Agent 技能（skill），随模板分发给能识别技能目录的 harness（Claude Code / CodeBuddy / 兼容实现）。不安装也不影响模板的其他能力——脚本、门禁、仪表盘全都照常工作。

## 包含哪些

| 技能 | 用途 |
|---|---|
| `vault` | 路由入口：按意图分发到下面这些技能 |
| `vault-save` | 会话知识沉淀（→ 99-Inbox 草稿） |
| `vault-inbox-consolidate` | 草稿按路由晋级到正式区 |
| `vault-handoff` | 会话收尾：交接卡 + 纠正账本 |
| `vault-plan` | 把需求拆成带测试的可执行计划 |
| `vault-exec` | 按计划派发子代理执行（maker-checker） |
| `vault-adr` | 写架构决策记录 |
| `vault-grill` | 方案拷问（第一性原理 + 复用阶梯） |
| `vault-spark` | 从模糊想法到结构化规格 |
| `vault-debug` | 4 步根因排障（先复现再修） |
| `vault-team` | 多专家面板并行评审 |

> **不含**：编程语言/框架类技能（tdd / refactor / perf / review / onboarding / bootstrap / pipeline / Agent 集成规范）与求职类技能（interview）——本模板定位领域无关，接收者可能不做编程。

## 如何安装

把本目录下的技能文件夹整体复制到**技能目录**即可，分两种情况：

### 有 CC Switch（推荐）

技能统一存放在 `~/.cc-switch/skills/`，**由 CC Switch 统一管理并同步到各应用**——只需放一份，无需逐个应用重复安装。

```bash
cp -r skills/vault skills/vault-* ~/.cc-switch/skills/
```

### 没有 CC Switch

放到你所用应用各自的技能目录，**一一对应**（每个应用各放一份）：

```bash
cp -r skills/vault skills/vault-* ~/.claude/skills/     # 例：类 Claude 的技能目录
# 其它应用按其自身约定放置（各应用目录一一对应，互不共享）
```

> Windows PowerShell 等价：`Copy-Item skills\vault* $HOME\.cc-switch\skills\ -Recurse -Force`
>
> 若某应用没有技能目录机制，可在其全局规则文件（如 `AGENTS.md`）中加一行指针：
> `本项目附带 /vault-* 技能，需要时读取 skills/<name>/SKILL.md 按其步骤执行。`

安装后，输入 `/vault` 可看到路由入口；各技能以 `/vault-save`、`/vault-plan` 等命令形态调用；不装也能用脚本与门禁。

## 与技能定义源的关系

本目录是**随包快照**（vendored subset）：源库外的技能定义目录才是作者侧实时版本，本目录只保留分发所需的稳定子集。更新方式 = 从实时目录复制过来后随模板一并发布（见 `TEMPLATE-RELEASE-PLAN.md` 的发布 SOP）。

## 与库内 `.claude/skills/` 的区别

- `.claude/skills/`：**库内 L2 技能**（json-canvas / obsidian-cli / vault-maintain / vault-tools），由 `05-Tools/SKILL-REGISTRY.md` 登记，healthcheck Check 8 硬校验——它们随库生效，无需安装；
- 本目录：**harness 级技能**（`/vault-*` 命令家族），MUST 安装到 harness 技能目录才可用。
