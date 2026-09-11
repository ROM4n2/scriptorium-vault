---
title: "知识库目录结构与内容归属规范 (VAULT-STRUCTURE)"
created: 2026-09-02
updated: 2026-09-11
type: rules
tags:
  - category/rules
  - topic/vault
  - topic/architecture
status: stable
audience: both
authority: synthetic
claim_risk: high
review_status: unreviewed
---

# 知识库目录结构与内容归属规范 (VAULT-STRUCTURE)

> **来源声明**：本规范是 `AGENTS.md` 目录架构相关细则的**唯一宿主**。`AGENTS.md` 只保留路由与铁律索引，本文件承载：目录职责总表（原 AGENTS.md §3）、Frontmatter 规范（原 §4）、双版本制（原 §5）、三层认知记忆分工（原 §8）的完整细则，并新增**壳目录策略**与**内容归属裁决表**。
> RFC 2119 关键字语义与 AGENTS.md 顶层声明一致。

---

## 1. 目录架构职责总表

| 目录 | 职责 | 认知层级 |
|---|---|---|
| `00-MOC/` | 全库知识导航与聚合枢纽（Home / MOC / Canvas） | 语义（索引） |
| `01-Rules/` | 跨语言通用工程规范、Agent 行为准则、环境事实 | 程序（铁律） |
| `02-Fundamentals/` | 计算机底层核心基石（OS、网络、体系结构、编译原理） | 语义（科目壳*） |
| `03-Languages/{LANG}/` | 按语言划分的双版本规范（`{LANG}-STANDARDS.md` + `{LANG}-CHEATSHEET.md`） | 程序 |
| `04-Systems/` | 现代系统架构与中间件（MySQL、Redis、Kafka、分布式、云原生、Linux 性能） | 语义（科目壳*） |
| `05-Tools/` | 工具使用指南与配置参考（Claude Code、MCP、Obsidian、`Workflows/`、`Subagents/`） | 语义 / 程序 |
| `06-Sources/{Type}/` | 外部知识源研读笔记（`Books/` `Videos/` `Articles/` `Papers/`） | 语义 |
| `07-Academics/` | 课程实验（分布式课程实验、数据库课程实验、网络课程实验、操作系统课程实验）、毕设 | 语义（科目壳*） |
| `08-Projects/{PROJECT}/` | 特定项目约束与架构笔记（`01-ADR/`、`AGENT-CONTEXT.md`、`02-Post-mortem`） | 情景 |
| `09-Career/` | 求职面试高频考点、真实项目答辩复盘、算法与系统设计（自带 `00-Career-MOC.md`） | 语义 |
| `10-Daily/` | 开发者个人日常日志，**MUST NOT** 堆积未加工工程规则 | 情景（过程流） |
| `11-Agents/` | Agent 操作审计与验证日志（`review-log.md` + `logs/`） | 情景（过程流） |
| `99-Inbox/` | Agent 自动摄取与沉淀的 Landing Zone（TTL 内流转） | 流程 |
| `Templates/` | 标准模板（`tpl-*.md` 与 `code/` 多语言代码模板） | 语义 |
| `skills/` | **工具资产区**（11 个 `/vault-*` 技能真值源，随模板分发，非知识内容，不参与语义检索） | 工具 |
| `examples/` | **官方示范笔记**（阅读工作流 ADR / RCA / 速查表），"一篇合规笔记长什么样"的标准答案 | 示例 |
| `hooks/` + `.githooks/` | 三道门 manifest 分发源与薄路由（`core.hooksPath` 指向后者） | 工具 |
| `dashboards/` | 夜间管线再生成的仪表盘六页（生成物入库，Home 直链） | 生成物 |
| `scripts/` | 自动化工具源码（`*.py`），非知识内容，不参与语义检索 | 工具 |
| 根目录 | `AGENTS.md`（规范入口）+ 5 个入口（符号链接或内容副本）+ `README.md`（库介绍） | 元 |

\* 标注"科目壳"的目录遵循 §2 壳目录策略，当前主要存 README 意图声明，实质笔记尚少。

---

## 2. 壳目录策略 (Shell-Directory Policy)

**背景**：目录可以先于内容存在，作为"学习意图清单"；但**壳目录不得被过度供养**——不为空壳建 MOC、不做脚本映射、不设健康检查门禁。

1. **壳定义**：目录内实质笔记（非 README/占位）< 3 篇即视为壳。当前壳区：`02-Fundamentals/*`、`04-Systems/*`、`06-Sources/*`、`07-Academics/*`、`10-Daily/`。
2. **壳内允许 (MAY)**：`README.md` 意图声明、课程/科目计划清单、至多 2 篇已读笔记。
3. **禁止动作 (MUST NOT)**：对壳目录创建独立 MOC、将壳路径写入工具 TARGET_DIRS / 语言映射 / 忽略表维护、为壳内空科目设置质量门禁。
4. **激活阈值**：单科目实质笔记 **≥ 3 篇**即为"激活"。激活后 SHOULD：补充 MOC 链接、纳入检索覆盖、允许脚本映射。
5. **状态登记**：壳激活/降级变更 **MUST** 在 `11-Agents/review-log.md` 登记。

---

## 3. 内容归属裁决表 (Content Routing Table)

内容放置按下列顺序裁决。模糊场景**先查本表**，未覆盖再问"它服务哪个使用场景"。

| 模糊对 | 归属判断链 |
|---|---|
| `06-Sources/` vs `07-Academics/` | 内容是否跟随一门课程/实验大纲产出？**是**（含课程笔记、Lab、作业）→ `07-Academics/`；否则按载体（书/视频/文章/论文）→ `06-Sources/` |
| `02-Fundamentals/` vs `09-Career/` | 是否带面试语境（考点标记、高频考点题目、答辩口径）？**是** → `09-Career/`；系统性学科笔记（无面试语境）→ `02-Fundamentals/`。同一主题可双写，但须在两侧 wikilink 互指 |
| `08-Projects/` vs `01-Rules/` / `03-Languages/` | 约束是否绑定单一项目？**是** → `08-Projects/{PROJECT}/`；通用可复用于多项目 → 提升至 `01-Rules/`（跨语言）或 `03-Languages/{LANG}/`（语言特化）。**提升动作 MUST 在 review-log 登记** |
| `01-Rules/` vs `05-Tools/` | 是"工程行为规范/纪律" → `01-Rules/`；是"工具用法/配置步骤" → `05-Tools/` |
| `11-Agents/` vs `10-Daily/` | 记录主体是 Agent 操作/审计 → `11-Agents/`；是开发者个人日常 → `10-Daily/`。两者同为过程记录，不承载最终知识 |
| `10-Daily/` vs 知识区 | 每日反思中的可复用结论 **MUST** 在当日或近期提升至对应知识区，Daily 只留指针 |
| `99-Inbox/` vs 正式区 | 未定稿/未验证 → `99-Inbox/`；定稿并校验 → 按上表归位并删除 Inbox 原件 |

---

## 4. Frontmatter 与元数据规范（自 AGENTS.md §4 下沉）

所有正式 Markdown 文档（除快速草稿与 MOC 外）**MUST** 包含 YAML frontmatter：

```yaml
---
title: "Go 语言工程规范"
created: 2026-08-28
updated: 2026-08-28
type: standards # standards | cheatsheet | rules | source-notes | daily | project | moc | notes
tags:
  - lang/go
  - category/rules
status: stable # draft | stable | archived
audience: agent # agent | human | both
source: "Dave Cheney《Practical Go》" # 选填
---
```

**标签命名空间（两级层级）**：
- `lang/`：`lang/go`, `lang/python`, `lang/typescript`, `lang/rust`, `lang/c`, `lang/cpp`, `lang/bash`
- `category/`：`category/rules`, `category/cheatsheet`, `category/notes`, `category/project`
- `topic/`：`topic/concurrency`, `topic/testing`, `topic/error-handling`, `topic/memory`
- `source/`：`source/book`, `source/video`, `source/article`, `source/paper`
- `status/`：`status/draft`, `status/stable`, `status/archived`

---

## 5. 双版本制（STANDARDS vs CHEATSHEET）（自 AGENTS.md §5 下沉）

1. **STANDARDS（Agent 约束版）**：
   - 命名：`{LANG}-STANDARDS.md`（如 `GO-STANDARDS.md`）；
   - **Source of Truth**：所有规范的主真值源，使用 RFC 2119 描述约束、原理、反例与静态检测。
2. **CHEATSHEET（人类速查版）**：
   - 命名：`{LANG}-CHEATSHEET.md`（如 `GO-CHEATSHEET.md`）；
   - **单向推导**：内容 **MUST** 由 Agent 从对应 STANDARDS 浓缩生成，严禁独立演化产生 Drift；
   - 表达风格：一句话核心法则 + 最短有效代码示例（< 5 行）。
3. **结构对齐**：CHEATSHEET 与 STANDARDS 章节序号 **MUST** 1:1 严格对齐，并在顶部标明指向 STANDARDS 的 Wikilink。
4. **语言扩展**：新增语言目录须同时具备双版本；工具链（quality-check/consolidate）的语言映射应**动态发现**而非逐语言硬编码（迁移完成前允许保留既有映射）。

---

## 6. 三层认知记忆分工与职责边界（自 AGENTS.md §8 下沉）

| 认知层级 | 对应目录与文件 | Agent 交互模式 | 核心价值 |
|---|---|---|---|
| **程序记忆 (Procedural)** | `01-Rules/`, `03-Languages/STANDARDS`, `05-Tools/Workflows/` | **强制加载 / 行为铁律** | 规范 Agent 的编码动作与 SOP 约束 |
| **语义记忆 (Semantic)** | `00-MOC/`, `06-Sources/`, `09-Career/`, `Templates/` | **按需检索 / 概念图谱** | 存放客观事实、高频考点原理、系统设计与生产模板 |
| **情景记忆 (Episodic)** | `10-Daily/`, `11-Agents/logs/`, `08-Projects/*/02-Post-mortem` | **事件溯源 / 经验复盘** | 记录真实项目排障、重大事故 RCA 与踩坑流水 |

---

## 7. 工具链路径契约

1. **检索范围 (MUST)**：语义检索类脚本（`search-vault.py` 等）的 TARGET 常量 **MUST** 覆盖全部知识内容目录：`00-MOC` `01-Rules` `02-Fundamentals` `03-Languages` `04-Systems` `05-Tools` `06-Sources` `07-Academics` `08-Projects` `09-Career` `10-Daily` `99-Inbox` `Templates`。
2. **排除区 (MUST NOT 入检索引擎)**：`11-Agents/`（审计日志）、`copilot/`（工具资产）、`scripts/`（代码）、`.githooks/`、隐藏目录。
3. **目录改名纪律 (MUST)**：任何目录改名（如历史 `06-Agents → 11-Agents`）**MUST** 同步：脚本常量、docstring、`AGENTS.md`/`README.md`/MOC 的目录描述、Canvas file 节点、wikilink、shell 脚本；完成后 grep 验证无旧名残留（历史档案区除外）。
4. **目录改名纪律 2 (MUST)**：`vault-healthcheck.py` 的工具链路径合规检查 **MUST** 保持启用，任何脚本重新引入旧编号目录名即报 Red。
