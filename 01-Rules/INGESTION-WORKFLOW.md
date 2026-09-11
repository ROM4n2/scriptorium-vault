---
title: "知识摄取与 Inbox 流转规范 (Karpathy 模式)"
created: 2026-08-28
updated: 2026-09-04
type: rules
audience: both
tags:
  - category/rules
  - topic/ingestion
  - topic/karpathy-mode
status: stable
authority: synthetic
claim_risk: high
review_status: unreviewed
---

# 知识摄取与 Inbox 流转规范 (Karpathy 模式)

> 本规范定义知识库如何实现 Karpathy 风格的“对话即沉淀”与“外部摄取 ➔ 知识加工 ➔ 规范沉淀”的自循环流水线。
> 所有 AI Agent（Claude Code, Antigravity, OpenCode 等）在摄取知识、生成草稿与流转笔记时 MUST 遵循本规范。

---

## 1. 对话即沉淀机制 (Conversation Ingestion)

### 1.1 双层触发时机 (Dual-Trigger Strategy)

1. **Agent 主动判断 (会话中)**：对话过程中如果发现了值得保留的知识，Agent **应在对话中主动归档**，无需等待 Stop hook。
2. **Stop Hook 提醒 (会话结束)**：每次对话结束时，全局 Stop hook 输出提醒："如果产生了非显而易见的知识，归档到知识库"。Agent 看到提醒后 **MUST 评估** 本次对话是否值得归档。

### 1.2 归档判定标准 (Triage Criteria)

**满足以下任一即归档**：
- 发现了全新的编码模式或架构实践
- 踩坑排查得出的环境/工具 Workaround
- 工具链或 CLI 的高效最佳实践
- 经过验证的跨语言通用工程规则
- 解决了一个具体的技术问题，且答案值得以后复用

**严禁沉淀**：
- 闲聊对话、已有既定规范
- 一次性临时调试输出
- 官方文档直接陈述的常识

### 1.3 归档执行步骤 (Execution Steps)

```
1. 读 AGENTS.md §4（Frontmatter 规范）了解格式要求
2. 生成草稿，写入 99-Inbox/YYYY-MM-DD-{主题}.md
   - 包含完整 frontmatter（title/source/tags/status/audience/confidence）
   - 提炼核心观点，不是原始对话记录
   - 标注来源（"来自 {date} 的对话：{主题}"）
3. 在 11-Agents/review-log.md 追加操作记录
4. 向用户报告："本次对话发现了值得沉淀的知识，已写入 Inbox"
```

### 1.4 沉淀双通道单一性 (Single-Channel Rule) (MUST)

沉淀落盘有两条互不感知的通道：`save_inbox_draft` MCP（自动命名 + A-MAC 校验）与直接 Write 文件（精细控制 frontmatter/结构）。**同一主题的沉淀 MUST 只走一个通道且只走一次**：

1. 默认走 `save_inbox_draft` MCP；仅当需要精细控制 frontmatter/结构时用 Write 直接落盘。
2. Write 落盘后 **MUST NOT** 再为同一主题调用 MCP 补写（反之亦然）——双通道各写一份必然产生冗余草稿，后续 consolidate 可能重复晋级。
3. 误产生冗余后：立即删除多余文件，并跑 `python scripts/vault-healthcheck.py` 确认 Inbox 计数恢复。
4. 注意草稿 frontmatter 最小字段集：draft 也不能缺 `status: draft` 与 `audience`（both/agent/human），否则 Frontmatter Integrity 体检直接 FAIL。

### 1.5 双轨入库决策网关 (Direct Ingestion vs Inbox Landing Gate) (MUST)

当 Agent 通过 `/vault-save`、`/vault-debug`、`/vault-grill` 或 `/vault-handoff` 提炼出高价值工程知识时，**MUST 遵循双轨落地机制**并在收尾阶段主动提供决策选项：

```text
💡 知识沉淀决策选项：
[1] 存入 99-Inbox/ 暂存草稿（默认，进入 Karpathy 待加工区后续批量整理）
[2] 立即晋级合并至正式知识库（直接写入 01-Rules / 03-Languages / 05-Tools，跳过 Inbox 滞留）
```

- **快速通道 (Fast Track)**：若用户明确指示“直接入库 / 移入正式”或知识点属于高置信度的即时工程规范，Agent **MUST 直接创建或合并至正式目录**，同步完成 frontmatter (`status: stable`) 与 MOC 索引更新。
- **草稿通道 (Draft Track)**：若知识点尚待观察、属于临时探索性 Workaround，则先存入 `99-Inbox/`。

---

### 1.6 隔离原则 (Isolation Rule)

- `99-Inbox/` 是知识摄取的 landing zone。
- `10-Daily/` 是个人日志，**MUST NOT** 直接堆积未经加工的规则。
- 若 Daily 中发现有效知识，Agent 提取至 `99-Inbox/` 加工。

---

## 2. Inbox 流转流程（草稿 → 正式笔记）

Inbox 中的草稿不会自动变成正式笔记，需要经过以下流转：

```mermaid
flowchart LR
    A["99-Inbox/草稿.md"] --> B["评估与加工 (Triage)"]
    B --> C["正式目录 / 规范笔记.md"]
```

### 2.1 流转触发方式

1. **手动触发**：用户指令（如"把 inbox 里的 XXX 移到正式目录"）。
2. **定期整理**：Agent 扫描 `99-Inbox/` 报告超龄草稿（>7 天），建议用户处理。
3. **对话触发**：用户讨论特定主题时，Agent 发现 inbox 中有相关草稿，主动建议整合。

### 2.2 流转执行步骤（MUST 完整蒸馏，不得止步于搬移）

> ⚠️ **工具陷阱**：`promote_inbox_draft` MCP **仅做「搬移 + status: stable」**，**不执行重命名、不去叙事化、不补索引**。若用它晋级正式规则区，产出仍是 `99-Inbox` 草稿态（日期前缀 + 中文括号文件名 + source-notes 叙事体），**违反本规范**。正式晋级 MUST 完成下方完整蒸馏，或直接走 `vault-inbox-consolidate`（智能流转晋级）一次性产出规范文件。

```
1. 读取 99-Inbox/ 中的草稿
2. 评估内容价值：
   - 价值高 → 提炼成正式笔记，可能生成双版本（STANDARDS + CHEATSHEET）
   - 价值中 → 合并到已有相关笔记
   - 价值低 → 标记 deprecated，移入归档或删除
3. 选择目标目录与**规范文件名**（MUST 大写 KEBAB-CASE，如 01-Rules/〔领域协作规范〕.md）：
   - 语言规范 → 03-Languages/{LANG}/{LANG}-STANDARDS.md 或 CHEATSHEET.md
   - 工具指南 → 03-Languages/TOOLS/{TOOL}-GUIDE.md
   - 书籍笔记 → 06-Sources/Books/{BOOK}-notes.md
   - 项目规范 → 08-Projects/{PROJECT}/{PROJECT}-RULES.md
   - 通用规则 → 01-Rules/{RULE}.md
   - **MUST NOT** 把 `99-Inbox/YYYY-MM-DD-{主题}.md` 的「日期前缀 + 中文括号标题」原样搬入正式目录；文件名 MUST 重命名为 KEBAB-CASE（git mv 保留历史）。
4. **去叙事化蒸馏**（MUST）：source-notes 草稿 → 正式规则体：
   - `type` 按归属设 `rules`（铁律区）/ `notes`（语言区排查）；去除原始会话叙事。
   - 正文用 `## N.` 编号节 + RFC 2119 关键字；H1 带 `(FILENAME)` 后缀；结尾补 `## 关联索引` wikilink 段。
5. 更新 frontmatter（status: draft → stable，补充 updated 字段；audience/source 齐备，见 [[01-Rules/VAULT-STRUCTURE]] §4）
6. 添加双向链接（关联到已有笔记）
7. 更新对应 MOC 页
8. 从 99-Inbox/ 删除或标记为 processed
9. Git commit（Conventional Commits，禁止 --no-verify；详见 [[01-Rules/AGENT-CONDUCT]] §6）
```

### 2.3 目标目录选择指南

| 内容类型 | 目标目录 | 命名模式 |
|---|---|---|
| 语言规范/速查 | `03-Languages/{LANG}/` | `{LANG}-STANDARDS.md` 或 `{LANG}-CHEATSHEET.md` |
| 工具使用指南 | `03-Languages/TOOLS/` | `{TOOL}-GUIDE.md` |
| 书籍/视频/文章笔记 | `06-Sources/{Type}/` | `{SOURCE}-notes.md` |
| 项目特定规范 | `08-Projects/{PROJECT}/` | `{PROJECT}-RULES.md` |
| 跨语言通用规则 | `01-Rules/` | `{RULE}.md` |

---

## 3. 关联索引
- 知识库交互准则：[[01-Rules/AGENT-CONDUCT]]
- 通用编码规范：〔你的领域通用规范〕
- 来源索引总览：[[00-MOC/MOC-Sources]]
- 知识库总览中心：[[00-MOC/Home]]
