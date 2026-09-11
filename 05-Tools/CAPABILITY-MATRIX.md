---
title: "能力声明矩阵（Capability Contract）"
created: 2026-09-08
updated: 2026-09-08
type: rules
tags:
  - lang/tools
  - category/rules
  - topic/capabilities
status: stable
audience: both
source: "借鉴 claude-obsidian capabilities.json 四态模型"
authority: synthetic
claim_risk: medium
review_status: unreviewed
---

# 🎯 能力声明矩阵（Capability Contract）

> **设计原则**：每个脚本/MCP/技能声明"我怎么被验证"。没有自动验证器的如实标 `configured`，不假装 `verified`。

## 能力状态定义

| 状态 | 含义 | 何时使用 |
| --- | --- | --- |
| `verified` | 有自动验证器且实跑通过 | 有 `verification_command` 且退出码 0 |
| `configured` | 前置就绪但未验证 | 无自动验证器，或未实跑 |
| `degraded` | 验证失败或部分配置 | `verification_command` 退出码非 0 |

## 能力清单

<!-- MATRIX:BEGIN -->

### Scripts（脚本）

| 能力 | 类型 | tier | verification_command | 状态 |
| --- | --- | --- | --- | --- |
| vault-quality-check | script | core | `python scripts/vault-quality-check.py --strict` | verified |
| vault-healthcheck | script | core | `python scripts/vault-healthcheck.py` | verified |
| search-vault | script | core | `python scripts/search-vault.py "test" --format compact` | verified |
| vault-dedup | script | extension | `python scripts/vault-dedup.py --json` | verified |
| vault-auto-linker | script | extension | `python scripts/vault-auto-linker.py --json` | verified |
| vault-graph-analyzer | script | extension | `python scripts/vault-graph-analyzer.py --json` | verified |
| vault-knowledge-graph | script | extension | `python scripts/vault-knowledge-graph.py --json` | verified |
| vault-inbox-triage | script | extension | `python scripts/vault-inbox-triage.py --json` | verified |
| vault-inbox-consolidate | script | extension | `python scripts/vault-inbox-consolidate.py --json` | verified |
| vault-memory-compactor | script | extension | `python scripts/vault-memory-compactor.py --json` | verified |
| vault-proactive-scan | script | extension | `python scripts/vault-proactive-scan.py --json` | verified |

### MCP Services（MCP 服务）

| 能力 | 类型 | tier | verification_command | 状态 |
| --- | --- | --- | --- | --- |
| vault_search_mcp (9 tools) | mcp | core | `python scripts/mcp_probe.py scripts/vault_search_mcp.py --expect-tools 9` | verified |
| arxiv_paper_mcp (2 tools) | mcp | extension | `python scripts/mcp_probe.py scripts/arxiv_paper_mcp.py --expect-tools 2` | verified |
| sqlite_inspector_mcp (3 tools) | mcp | extension | `python scripts/mcp_probe.py scripts/sqlite_inspector_mcp.py --expect-tools 3` | verified |
| system_monitor_mcp (4 tools) | mcp | extension | `python scripts/mcp_probe.py scripts/system_monitor_mcp.py --expect-tools 4` | verified |

### Skills（技能，清理后）

| 能力 | 类型 | tier | verification_command | 状态 |
| --- | --- | --- | --- | --- |
| vault-tools | skill | core | — | configured |
| vault-maintain | skill | core | — | configured |

<!-- MATRIX:END -->

## 验证方法

运行 `python scripts/capability-check.py` 检查所有能力状态。

**唯一真值源**：`05-Tools/capabilities.json`（ADR-0001 #7）。上表三节由
`<!-- MATRIX:BEGIN -->` / `<!-- MATRIX:END -->` 标记包裹，属单向派生视图——
维护流程 = 改 JSON → `python scripts/capability-check.py --render-matrix` → 提交，
禁止手改标记区间；`python scripts/capability-check.py --check-drift`
反查 JSON 与矩阵的 (name, type, tier, verification_command) 四元组对齐，漂移即 exit 1。

**验证命令的硬约束（MUST）**：`verification_command` MUST 为**只读**——不得写入、改名或删除仓库内任何文件。
`capability-check.py` 会在每次巡检时实跑这些命令，一条会写盘的命令等于让巡检本身污染知识库
（`vault-knowledge-graph.py --json` 曾无条件重写 `00-MOC/知识图谱白板（自动生成）`，+4662/-173 行，已于 d3b4950 修复）。
该约束由 `scripts/tests/test_capability_commands.py` 强制：它实跑矩阵里每一条命令，
并断言前后 `git status --porcelain=v1 --untracked-files=all` 逐字节一致。
因此上表 8 个 extension 脚本一律采用只读的 `--json` 形态
（`vault-auto-linker` 写入需 `--write` 显式开启；`vault-inbox-consolidate` 写入需 `--apply` / `--execute` 显式开启）。
4 个 MCP 服务使用 `scripts/mcp_probe.py` 完成 stdio JSON-RPC 握手验证，
`--expect-tools N` 断言工具数与上表声明一致，工具增删会被捕获。

## 与 claude-obsidian 的差异

| 维度 | claude-obsidian | 我们 |
| --- | --- | --- |
| 能力声明 | `05-Tools/capabilities.json`（15 个能力） | `05-Tools/capabilities.json`（17 个能力，唯一真值源）→ 本矩阵渲染视图 |
| 状态模型 | 四态（available/configured/verified/degraded） | 三态（verified/configured/degraded） |
| 自动验证 | `verification_command` 实跑 | `capability-check.py` 实跑 |
| 诚实声明 | 无验证器时写 `verification_reason` | 无验证器时标 `configured` |

## 后续演进

1. ~~给 `vault_search_mcp` 加自动验证（mock JSON-RPC 调用）~~ ✅ 已完成（4 个 MCP server 通过 `mcp_probe.py` 握手验证 + `--expect-tools N`）
2. ~~给 `vault-dedup` 等 extension 脚本加验证命令~~ ✅ 已完成（8 条只读 `--json` 命令入表）
3. 接入 nightly 维护
