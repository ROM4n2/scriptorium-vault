---
title: "跨 Agent 共享工作记忆规范 (Cross-Agent Memory Protocol)"
created: 2026-09-04
updated: 2026-09-09
type: rules
audience: both
tags:
  - category/rules
  - topic/multi-agent
  - topic/memory
  - topic/vault
status: stable
authority: synthetic
claim_risk: high
review_status: unreviewed
---

# 跨 Agent 共享工作记忆规范 (Cross-Agent Memory Protocol)

> **定位**：多 agent 工作流的**工作状态层**。vault 承载规范与结论（应然），各项目 `WORKMEMORY/` 承载进行中任务、交接与踩坑轨迹（实然）。协议本体由各项目 `WORKMEMORY/PROTOCOL.md` 模板承载，本规范钉住其 MUST 层与 vault 联动规则。

---

## 1. 三层记忆分工 (MUST 认知)

| 层 | 位置 | 内容 | 生命周期 |
| --- | --- | --- | --- |
| 程序记忆 | `01-Rules/`、`03-Languages/STANDARDS`、`05-Tools/Workflows/` | 行为铁律与编码规范 | 长期稳定 |
| 语义记忆 | vault 全库（02-07 区） | 蒸馏后的结论、踩坑、模板 | 长期演进 |
| **工作记忆** | **`{{CODE_ROOT}}\{project}\WORKMEMORY\`** | **in-flight 任务、交接包、会话事件流** | **随项目演进，HOT→WARM→COLD 分层** |

- **单一写入层 (MUST)**：跨 agent 状态共享的唯一可靠机制是**共同写入层**，不是互读各 agent 原生记忆（格式 md/sqlite/opaque 互不兼容，OpenCode 甚至无原生记忆）。原生记忆（Claude auto-memory、Codex sqlite、CodeBuddy memery）照常运行，属私有层。
- **蒸馏边界 (MUST)**：WORKMEMORY 只存状态与轨迹；vault 只存规范与结论。成熟知识 MUST 经摄取管线（`save_inbox_draft` → 晋级）入 vault，并在该项目 `WORKMEMORY/INDEX.md` 蒸馏登记表回写 `vault://<路径>` 标注。引用 vault 笔记用 `vault://` 前缀说明性文字，**MUST NOT** 写 Obsidian wikilink（跨库必断链）。

## 2. 协议铁律（与 WORKMEMORY/PROTOCOL.md §1 对齐）(MUST)

1. **读序**：会话开始先读项目 `WORKMEMORY/INDEX.md` → `PROJECT_OVERVIEW.md` → `work.log` 尾 50 行 → **`corrections.md` 顶部 open 条目（本会话 MUST NOT 重犯已登记纠正）**；发现未闭合 `WORK_START` **必须先询问用户**继续还是重开。
2. **追加制**：`work.log` append-only，单事件 ≤4KB，UTF-8 写入（Windows 禁依赖控制台默认编码）；超限正文写 `NOTES-<slug>.md` 留链接。
3. **身份声明**：事件头 `YYYY-MM-DD HH:MM | <model-id>__<harness> | <EVENT_TYPE>` + 能力行（vendor-neutral 词如 `filesystem-write`）；不确定 model-id 问用户，**MUST NOT** 猜。
4. **敏感禁令**：work.log/handoff/NOTES 禁止 key/token/密码字面量；pre-commit 密钥扫描兜底。
5. **分层轮转**：HOT（work.log，默认 50 事件）超 1.5×阈值 → 下一个开工 agent 轮转至 `archive/work-YYYY-MM-DD.log` 并更新 INDEX 主题索引；COLD digest 仅用户显式要求时生成。
6. **交接包**：`handoff_<topic>.md` 含 frontmatter（to/from/created/role/required_capability/status）与正文（上下文/已完成+证据/未完成/风险）；接收方闭环（status→closed + `HANDOFF_RECEIVED` 事件）。
7. **容错**：协议靠约定维持——某 agent 漏写由下一 agent 补 `NOTE` 勘误，不回改历史。
8. **范围与回写纪律（SHOULD，借鉴交付型项目模板）**：`WORK_START` 推荐附「不做范围」一行（本任务明确排除的功能/重构/顺手修改），对抗 agent scope creep；`WORK_END` 推荐做「回写检查」——稳定结论已回写（vault/模块文档/INDEX 蒸馏登记）、临时产物（日志/真实数据/凭据/截图）未入库。收尾即废弃，不留尾债。

## 2.5 CORRECTION 事件与纠正账本 (MUST，#3)

用户纠正 agent 的行为、结论或方向时，纠正本身 MUST 成为可继承状态——不落地则下个会话/下个 agent 必然重犯。

1. **事件**：`CORRECTION` 事件（事件头规范同 §2.3，追加制）——用户原话压缩为 1 行事实 + 问题归属（领域/流程/工具），禁敏感字面量（§2.4 同）。
2. **账本**：每项目 `WORKMEMORY/corrections.md`，表格 schema（列固定）：

   | 日期 | 原话（用户） | 问题归属（领域/流程/工具） | 落地状态 | 蒸馏去向 |
   | --- | --- | --- | --- | --- |
   | YYYY-MM-DD | 用户原话 ≤1 行 | 领域 / 流程 / 工具 | open / in-progress / resolved / closed | vault://路径 或 — |

3. **追加制**：open/in-progress 条目 MUST NOT 删除，只改「落地状态」列；整行废除仅限用户明确撤回。
4. **会话启动注入**：Anchor 读序（§2.1）已含「读 corrections.md 顶部 open 条目」——每个开工 agent MUST 确认已读且本会话不重犯。
5. **闭环**：纠正发生 → `open`；处理中 → `in-progress`；已解决 → `resolved`；成熟纠正经蒸馏管线（`/vault-save` 或 `save_inbox_draft` → 晋级）入 vault 后 → 回填「蒸馏去向」= `vault://<路径>` + 状态 `closed`。蒸馏边界与登记纪律同 §1。
6. **宿主适配**：vault 自身（无 `WORKMEMORY/` 目录）账本为 `11-Agents/corrections.md`，schema 同上。
7. **容错**：对齐 §2.7——某 agent 漏记由下一 agent 补 `NOTE` 勘误，不回改历史。

## 3. Anchor 注入矩阵 (MUST)

使任何 agent 进入项目即知晓协议。项目级 anchor 3 行（读序/写事件/检索与沉淀）注入项目根规则文件；全局 anchor 注入各 agent 的全局规则文件：

| Agent | 全局规则文件 | 注入形态 |
| --- | --- | --- |
| Claude Code | `~/.claude/CLAUDE.md` | 独立章节（控 10KB 红线） |
| Gemini CLI / Antigravity | `~/.gemini/GEMINI.md` | 追加章节（Antigravity 项目级发现序 AGENTS.md 优先，全局侧由 Gemini 家族配置覆盖） |
| Codex | `~/.codex/AGENTS.md` | 完整版（协议摘要 + vault 检索 + 环境要点） |
| OpenCode | `~/.config/opencode/AGENTS.md` | 完整版（OpenCode 无原生记忆，最依赖 anchor） |
| CodeBuddy | 挂载点经 GUI 验证后登记 | fallback：项目级 AGENTS.md 一定被读 |
| 其余（Trae/Copilot 等） | 不注入 | 项目级 anchor 已覆盖 |

## 4. Vault 治理与巡检 (MUST)

1. **healthcheck 第 9 项**：`vault-healthcheck.py` 对存在 `WORKMEMORY/` 的项目校验——INDEX.md 存在、work.log 单事件 ≤4KB、未闭合 `WORK_START` 提醒；无 WORKMEMORY 的项目跳过（不误报）。
2. **蒸馏回写**：`/vault-save` 或晋升流程在项目知识沉淀完成时，回写该项目 INDEX.md 蒸馏登记表；自动化成本高时 MVP 先手动。
3. **新项目 bootstrap**：项目初始化时 MUST 下发 WORKMEMORY 4 件套与项目级 anchor——机械部分由 `bootstrap.ps1`（模板源 `Templates/workmemory/`）或 `/vault-bootstrap` skill 完成，PROJECT_OVERVIEW.md 的内容蒸馏（从代码库提炼 primer）由执行 bootstrap 的 agent 完成脚本无法替代的一步；存量项目按需逐个 bootstrap，不强制全铺。Claude Code 侧另有 SessionStart hook（`~/.claude/hooks/workmemory-sessionstart.sh`）在存在 WORKMEMORY 的项目机械注入读序提醒与 work.log tail。
4. **与 AGENTS.md 交接快照的关系**：项目级 `AGENTS.md` 仍是机器可读静态快照（技术栈/架构约束）；WORKMEMORY 承载动态工作状态。两者并存，交接快照定位不变。

## 5. 关联索引
- 会话现场保护（compact 前后清单 + hook 模板）：[[01-Rules/SESSION-SNAPSHOT-PROTECTION]]
- 协议本体模板：`{{PROJECT_PATH}}\WORKMEMORY\PROTOCOL.md`（首个试点实例）
- 知识摄取与蒸馏管线：[[01-Rules/INGESTION-WORKFLOW]]
- 多 Agent 治理矩阵：`vault://08-Projects/项目档案/MULTI-AGENT-LIMITATIONS-AND-RISKS`
- Agent 注册与派发：[[05-Tools/Subagents/〔子代理派发指南〕]]
- 知识库总览：[[00-MOC/Home]]