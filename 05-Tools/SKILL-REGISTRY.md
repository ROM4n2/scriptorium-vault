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

# 🗂️ Coding Vault 技能注册表与三层配合模型

> **本文件只索引、不复制**：技能实体真值源在各自层级的目录中（全局在 CC Switch、项目级在库内 `.claude/skills/`）。
> 用途：回答「技能由 CC Switch 集中管理，如何与 Vault 配合」的权威索引——列出每个技能的职责、驱动规则与同步方式，是 [[00-MOC/MOC-Tools]] 技能矩阵的唯一展开页。

---

## 1. 三层技能配合模型 (The Layered Model)

CC Switch 统一管理全局技能并分发到各 AI 客户端；Vault 充当**知识契约层**与**项目技能宿主**。三层各司其职、互不复制：

| 层 | 真值源 | 管辖者 | 内容 | 本 Vault 角色 |
|---|---|---|---|---|
| **L1 全局技能** | `~/.cc-switch/skills/`（29 项，含 18 个 `vault-*`） | CC Switch（注册/开关/symlink 分发） | 与项目无关的工作流/行为技能 | 行为规范出处在此库（§4 驱动规则） |
| **L2 项目技能** | `.claude/skills/`（4 项） | Vault（实体文件，git 管理） | 绑定 `{{VAULT_ROOT}}` 路径的库内脚本/MCP 工具技能 | 本库内作业时可见 |
| **L3 知识契约层** | `01-Rules/` + `AGENTS.md` | Vault（git/quality/review-log） | 规则、模板、变更史 | L1/L2 技能行为的规范来源 |

**配合要点 (MUST)**：
1. **单一物理真值源**：同一技能只在一处存实体，严禁在 Vault 复制全局技能副本（防双源漂移），亦严禁跨层互建符号链接——分发全权由 CC Switch（L1）或 Vault 实体文件（L2）管理，参见 [[01-Rules/AGENT-CONDUCT]] §10 三条铁律。
2. **规则 → 技能单向链路**：技能的行为依据先在 L3 定稿，技能文件只是 L3 规则的"运行时化包装"；变更顺序见 [[01-Rules/SKILL-AUTHORING-SPEC]]。
3. **技能 ← 规则 反向可追溯**：本注册表 §4 的"驱动规则"列即反向索引，保证每个全局技能都能找到其规则出处。

---

## 2. L1 全局技能池（真值源 `~/.cc-switch/skills/`，CC Switch 分发）

> 技能数量与开关状态以 **CC Switch UI** 为准（各客户端接收的同步子集由 CC Switch 控制）。以下为 2026-09-02 实测池。

### 2.1 Vault 全生命周期 18 技能（vault-* 系列）

| # | 技能 | 生命周期阶段 | 核心职责一句话 | 驱动规则/产物 |
|---|---|---|---|---|
| 1 | `vault` | 路由中枢 | 环境探测 + 18 技能智能分发入口 | 本文件 / [[01-Rules/AGENT-CONDUCT]] |
| 2 | `vault-bootstrap` | 0 环境 | 新仓库安全钩子与规范锚点筑基 | `.githooks` 契约 |
| 3 | `vault-onboard` | 0 接手 | 陌生代码库极速建档与单测基线锁死 | `.agent-context.md` 规范 |
| 4 | `vault-spark` | 1 需求 | 0→1 灵感发散与规格书（SPEC）生成 | Frontier Tree 协议 |
| 5 | `vault-grill` | 1 架构 | 双镜头（产品/技术）极限审讯与决策树 | Frontier Tree / ADR |
| 6 | `vault-adr` | 1 决策 | MADR 架构决策自增编号归档 | `01-ADR/` 模板 |
| 7 | `vault-plan` | 2 规划 | 任务拆解 + 子代理 Prompt 脚手架 | 绑定 Subagents 矩阵 |
| 8 | `vault-exec` | 2 执行 | 多子代理派发 + Maker-Checker 状态机 | [[05-Tools/Subagents/〔子代理派发指南〕]] |
| 9 | `vault-pipeline` | 2 流水线 | 端到端 Worktree 隔离串行流水线 | Git Worktree 契约 |
| 10 | `vault-tdd` | 3 质量 | 契约 TDD + 伪绿变异防线 | [[01-Rules/TESTING-PATTERNS]] |
| 11 | `vault-refactor` | 3 重构 | 卫语句展平、YAGNI 极简重构 | The Ladder of Reuse |
| 12 | `vault-debug` | 3 排障 | 4 步根因排障（复现断言前置） | 工作流文档 |
| 13 | `vault-perf` | 4 基准 | 多语言压测与竞态分析 | `-race`/`EXPLAIN` 契约 |
| 14 | `vault-review` | 4 评审 | 7 语言 RFC 2119 审查与红黄牌门禁 | 〔你的领域通用规范〕 |
| 15 | `vault-team` | 4 会诊 | 6 大专家并行联审聚合 | Subagents 专家矩阵 |
| 16 | `vault-save` | 5 沉淀 | Karpathy 对话即沉淀（前置查重） | [[01-Rules/INGESTION-WORKFLOW]] |
| 17 | `vault-handoff` | 5 交接 | 会话收尾与 1-Click 续接交接卡 | 交接卡模板 |
| 18 | `vault-interview` | 5 面试 | 1v1 高压技术答辩与难度阶梯 | `09-Career` 联动 |
| 19 | `vault-inbox-consolidate` | 5 沉淀 | 99-Inbox 草稿按 frontmatter 分类归档（dry-run 预览） | [[01-Rules/INGESTION-WORKFLOW]] |

> **随包技能子集（第 4 个技能位置）**：`skills/`（随模板分发 11 项，真值源即该目录，
> 见 `skills/README.md`）。它与上述三层的映射：随包 = 本表 §2.1 的子集 + 通用技能的
> 模板化版本；安装位置仍是 L1（CC Switch）或各 Agent 技能目录，`skills/` 只是**分发源**。

### 2.2 通用技能 11 项（非 vault-* 系列）

| 技能 | 核心职责一句话 |
|---|---|
| `caveman` / `ponytail` | 极致压缩输出 / YAGNI 懒人开发模式 |
| `stop-slop` | 去除 AI 写作腔 |
| `teach` / `triage` / `claudeception` | 教学讲解 / 草稿分诊 / 会话经验提炼 |
| `domain-modeling` | 领域建模与 ADR 语境 |
| `frontend-design` | 前端审美设计指导（↔ 领域专题规范） |
| `hyperframes` / `ppt-master` | 视频动画 / PPT 生成 |
| `writing-great-skills` | 高质量技能编写元规范（↔ [[01-Rules/SKILL-AUTHORING-SPEC]]） |

---

## 3. L2 库内项目技能（真值源 `.claude/skills/`，Vault 管理）

> 实体为 `.claude/skills/<name>/SKILL.md` 目录，由 Vault 直接管理（git 跟踪），仅在本库 `{{VAULT_ROOT}}` 内作业时可见。

| 技能 | 绑定能力（脚本/MCP） |
|---|---|
| `vault-tools` | 库内自动化 CLI/MCP 工具链导航与速查（统一入口 `scripts/vault-tools.py`） |
| `vault-maintain` | 库内健康巡检→修复→review-log 登记闭环引导（8 项检查修复 SOP） |
| `json-canvas` | `.canvas` 图结构读写 |
| `obsidian-cli` | Obsidian 插件 CLI 用法速查（templater/dataview/git/linter 等） |

---

## 4. 职责分界与重叠理顺 (vault vs vault-tools)

两技能名字相近、皆承担"入口"，分工如下：

| | 全局 `vault`（L1） | 库内 `vault-tools`（L2） |
|---|---|---|
| 归属 | `~/.cc-switch/skills/vault/` | `.claude/skills/vault-tools/` |
| 适用范围 | **任意项目/任意目录**（CC Switch 分发到全部客户端） | **仅本 Vault 库内**（项目级挂载） |
| 职责 | 环境探测 → 把意图路由到 18 个 vault-* 技能 | 速查库内 `scripts/*` CLI 与 MCP 工具的用法 |
| 调用场景 | "我要开始/规划/排障…" 需挑选技能 | "库内有哪些自动化脚本？vault-save 如何调用？" |
| 生命周期矩阵 | 18 技能全量导航（最新） | 仅列出库内挂载的技能子集 |

**判定规则 (MUST)**：路由到工作流技能（`/vault-plan`、`/vault-exec`…）→ 全局 `vault`；查询本库脚本/MCP 工具用法 → `vault-tools`。两者不互为副本，`vault-tools` 的技能速查表以本文件 §2.1 为最新全量。

---

## 5. 变更与防漂移纪律

- 技能实体变更：遵循「规则 → 技能」单向链路（[[01-Rules/SKILL-AUTHORING-SPEC]]），先改 L3 规则 → review-log 登记 → 再落 `~/.cc-switch/skills/` → 用户经 CC Switch UI 同步。
- 本注册表维护 (MUST)：新增/停用任何 L1/L2 技能时 MUST 同步更新 §2/§3 表并登记 review-log；注册表只可引用存在文件，禁止指向未落盘技能。

---

## 6. 关联索引

- CC Switch 管理规范与三条铁律：环境配置指南
- 子 Agent 注册与派发纪律：[[05-Tools/Subagents/〔子代理派发指南〕]]
- 技能编写规范：[[01-Rules/SKILL-AUTHORING-SPEC]]
- 工具链总索引：[[00-MOC/MOC-Tools]]
