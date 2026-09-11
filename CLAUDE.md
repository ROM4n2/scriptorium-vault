# AGENTS.md — Coding Vault 规范层（多 Agent 唯一共识源）

> **RFC 2119 声明**：本规范 **MUST / MUST NOT / SHOULD / MAY** 遵从 RFC 2119。所有进入本知识库（Vault）的 AI Agent **MUST** 遵循本规范。

---

## 1. 加载与继承顺序

1. **先读全局规则**：Agent **MUST** 首先读取 `~/.claude/CLAUDE.md`（本机环境事实、反奉承哲学与防泄露守卫；若该文件不存在——例如模板包接收者环境——则跳过此步）。
2. **后读 Vault 规则**：Agent **MUST** 随后加载本文件。
3. **开工必读**：任何代码编写/重构/设计前，**MUST** 先加载 〔你的个人画像〕 与 〔你的领域通用规范〕。

> **记号约定**：凡 `〔…〕` 形态的路径，表示"该文件需按你的领域自建"——在本库中它们是实文件；在公开模板包中是占位（质量门禁自动豁免其 wikilink）。
4. **单源一致**：`CLAUDE.md`/`GEMINI.md`/`.cursorrules`/`.windsurfrules`/`CONVENTIONS.md` 均为指向本文件的符号链接（模板包中为**字节一致的内容副本**），**MUST NOT** 覆写为独立实体，修改 **MUST** 仅作用于本文件（副本形态由 `post-write-sync-agents.sh` 同步）。

---

## 2. Vault 定位与作用域

1. **核心定位**：`{{VAULT_ROOT}}` 是编程学习沉淀与工程规则速查的 **LLM-Native 知识库**。
2. **职责边界**：本 Vault **IS** 知识资产与规范源；**IS NOT** 项目运行代码仓库（代码统一在 `{{CODE_ROOT}}\`）。
3. **引用格式**：库内引用 **MUST** 用 Wikilink（`GO-STANDARDS`）；跨库引用项目 **MUST** 标注绝对路径（`{{CODE_ROOT}}\{project}`）。

---

## 3. 目录架构

| 区 | 目录 | 职责 |
|---|---|---|
| 导航 | `00-MOC/` | 全库导航与聚合枢纽 |
| 规范 | `01-Rules/` | 跨语言铁律、Agent 行为、环境事实 |
| 学科 | `02-Fundamentals/` | OS/网络/体系结构/编译原理（壳*） |
| 学科 | `03-Languages/{LANG}/` | 语言双版本规范（STANDARDS+CHEATSHEET） |
| 学科 | `04-Systems/` | MySQL/Redis/Kafka/分布式/云原生（壳*） |
| 学科 | `05-Tools/` | 工具用法与配置（Claude Code/MCP/Obsidian） |
| 摄入 | `06-Sources/{Type}/` | 书/视频/文章/论文研读（壳*） |
| 摄入 | `07-Academics/` | 课程实验与毕设（壳*） |
| 摄入 | `08-Projects/{PROJECT}/` | 项目约束、ADR、Post-mortem |
| 摄入 | `09-Career/` | 面试高频考点与答辩复盘 |
| 过程 | `10-Daily/` | 个人日志，**MUST NOT** 堆积未加工规则 |
| 过程 | `11-Agents/` | Agent 审计日志（`review-log.md` 索引 + `logs/YYYY-MM.md` 按月分片） |
| 流程 | `99-Inbox/` | 摄取 Landing Zone（TTL 内流转） |
| 工具 | `Templates/`/`skills/`/`scripts/` | 模板/技能资产/代码，**不入检索** |

\* 科目壳 = 内容 <3 篇的意图清单，不建 MOC、不入脚本映射、不设门禁（[[01-Rules/VAULT-STRUCTURE]] §2）。

> 完整目录职责、壳目录策略、内容归属裁决表、Frontmatter schema、双版本制、三层记忆分工细则，**MUST** 遵循唯一宿主 [[01-Rules/VAULT-STRUCTURE]]。

---

## 4. Frontmatter 与双版本制

1. 正式笔记（草稿/MOC 除外）**MUST** 含标准 YAML frontmatter；字段与标签空间见 [[01-Rules/VAULT-STRUCTURE]] §4。
2. 语言双版本：STANDARDS 为主真值源；CHEATSHEET 由 Agent 单向浓缩（严禁 Drift）、章节 1:1 对齐；见 [[01-Rules/VAULT-STRUCTURE]] §5。

---

## 5. 通用开发规范与开发者画像

完整 13 条基线见 〔你的个人画像〕、〔你的领域通用规范〕。要点：拒绝奉承、命名表意图（YAGNI）、注释讲为什么、离开时更干净、错误显式处理（领域专题规范）、结构化并发（领域专题规范）、**验证后下结论**。

补充规范：Python 打包与模块入口（工具链规范）、文档治理与入口拆分（[[01-Rules/DOC-GOVERNANCE]]）、子 Agent 定义审计（[[01-Rules/AGENT-AUDIT-CHECKLIST]]）。

---

## 6. 新项目初始化与防泄露

完整规则见 [[01-Rules/GIT-CONVENTIONS]]、[[01-Rules/AGENT-CONDUCT]]。要点：新项目 **MUST** 自动初始化（或 `pwsh scripts/bootstrap.ps1`）；密钥 **MUST** 入 `.gitignore`；提交前过密钥扫描；**MUST NOT** `git commit --no-verify`。

---

## 7. 对话即沉淀（Karpathy 模式）

标准见 [[01-Rules/INGESTION-WORKFLOW]]。要点：自主查库对齐 / 质量自审 / 经验沉淀（[[01-Rules/AGENT-CONDUCT]] §9）；沉淀经 `save_inbox_draft` 落 `99-Inbox/`，定稿后由 `vault-inbox-consolidate` 归位并删除原件。

---

## 8. 自检与维护

1. **符号链接/内容副本**：每月或环境变动后 **MUST** 验证 5 入口与 AGENTS.md 一致（本库为符号链接；模板包为内容副本，由 Check 5 校验）。
2. **体积红线**：本文件 **SHOULD** ~5KB，**MUST NOT** >10,240 B；超限 **MUST** 拆细则至 `01-Rules/`。
3. **Git 审阅**：改规范前 **SHOULD** `git log -n 5`；冲突以 Git 历史回滚。

---

## 9. 自动化工具指引

以下工具位于 `scripts/`，均以 `python scripts/<tool>.py [参数]` 运行（仅 bootstrap 用 pwsh）：

| 场景 | 工具 |
|---|---|
| Inbox 超龄草稿扫描 | vault-inbox-triage |
| **Inbox 智能流转晋级** | **vault-inbox-consolidate** |
| frontmatter 与链接验证 | vault-quality-check `[--strict]` |
| 重复/高相似笔记检测 | vault-dedup |
| 概念 wikilink 自动补全 | vault-auto-linker `--dry-run` |
| 项目主动知识发现 | vault-proactive-scan |
| 知识图谱与孤岛分析 | vault-graph-analyzer |
| 生成 Canvas 关系图谱 | vault-knowledge-graph |
| **精准检索规范与踩坑** | **search-vault** `"<query>"` |
| 全 Agent 检索 MCP 服务 | vault_search_mcp |
| 新项目脚手架初始化 | bootstrap |
| **一键综合健康巡检** | **vault-healthcheck** |
| 智能体记忆蒸馏压缩 | vault-memory-compactor `[--json]` |
