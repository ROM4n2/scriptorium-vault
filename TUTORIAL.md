---
title: "Coding Vault 使用教程（5 分钟上手 + 日常任务 Playbook）"
created: 2026-09-09
updated: 2026-09-11
type: notes
tags:
  - category/rules
  - topic/vault
  - topic/automation
  - topic/agent
status: stable
audience: both
authority: primary
claim_risk: low
review_status: unreviewed
---

# Coding Vault 使用教程

> 读者：接手本知识库的**人类开发者**与 **AI Agent**。规范细节以 `AGENTS.md` 与 `01-Rules/` 为准，本教程只讲「怎么用」；README 讲「是什么与怎么装」。

---

## 1. 五分钟心智模型

- **一句话**：这是一个 LLM-Native 知识库——Agent 负责沉淀与维护，人类负责方向与审核；一切知识经 `99-Inbox/` 草稿区流入，永不直写正式区。
- **三层记忆**：程序记忆（`01-Rules/`、`03-Languages/`）= 长期规范；语义记忆（02-07 区）= 蒸馏结论；工作记忆（各项目 `WORKMEMORY/`）= 进行中任务与交接。
- **可信度三字段**：每篇正式笔记的 frontmatter 带 `authority`（official/primary/secondary/community/synthetic/unknown）+ `claim_risk`（none/low/medium/high）+ `review_status`（unreviewed/reviewed）。字段含义见 `08-Projects/README.md`（模板包接收者：先读 `examples/ADR/0001-example-reading-workflow.md`，那里有带三字段的完整范例）。
- **★ 先看 examples/**：`examples/`（阅读工作流 ADR / RCA / 速查表）是"一篇合规笔记长什么样"的标准答案——写第一篇笔记前先照着它。

**目录速查**：`00-MOC/` 导航 → `01-Rules/` 跨语言铁律 → `03-Languages/` 语言双版本 → `04-Systems/` 架构学科 → `05-Tools/` 工具 → `06-Sources/` 外部研读 → `08-Projects/` 项目与 ADR → `09-Career/` 求职 → `10-Daily/` 个人日志 → `99-Inbox/` 草稿区。完整职责表见 `01-Rules/VAULT-STRUCTURE.md`。

---

## 2. 日常三大高频任务（Playbook）

### 2.1 沉淀一条踩坑/心得（最常用）

1. **对话中**：让 Agent 调用 `save_inbox_draft`（或 `/vault-save`），草稿自动落 `99-Inbox/YYYY-MM-DD-{topic}.md`；
2. **体检**：`python scripts/vault-inbox-triage.py` 看草稿超期状态；
3. **晋级**：`python scripts/vault-inbox-consolidate.py --apply`（`--execute` 为兼容别名）—— 按标签路由自动归档（routing.json 决定去向）并删除草稿；
4. **复核**：晋级结果进 `git diff` 人工过目后再提交。

**无 Agent 手动路径**（未接 Agent 会话时，手动完成同一闭环）：
1. 在 `99-Inbox/` 手动新建草稿 `YYYY-MM-DD-{topic}.md`（命名规范见 `01-Rules/INGESTION-WORKFLOW.md`），frontmatter 照 `Templates/` 对应模板补齐；
2. `python scripts/vault-inbox-triage.py` 体检草稿状态；
3. `python scripts/vault-inbox-consolidate.py --apply` 晋级（先去掉 `--apply` 跑 dry-run 预览路由去向）；
4. `git diff` 人工复核后提交。

> ⚠️ 草稿直写正式区是违规的；`vault-inbox-consolidate` 的路由由 `scripts/routing.json` 声明（改路由 = 改真值源，测试会校验）。

### 2.2 写 / 改一篇规范

1. 从 `Templates/tpl-standards.md`（或对应模板）起稿，frontmatter 七字段必填；
2. 语言规范改 `STANDARDS` 后，**必须同步浓缩** 对应 `CHEATSHEET`（章节 1:1，单向生成，禁止反向改写）；
3. 新术语想让全库自动补链？确认它已进入 `vault-auto-linker` 的概念索引源；
4. 自查：`python scripts/vault-quality-check.py --strict`；
5. 提交（过三道门，见 §4）。

### 2.3 看仪表盘 / 做巡检

- **一键巡检**：`00-MOC/Home.md` 顶部「⚡ 自动化运维控制舱」→ 🛡️ 一键全量只读巡检（healthcheck → quality --strict → 能力漂移 → 账本校验 → Inbox 体检）；
- **六页仪表盘**：`dashboards/`（最近来源 / 时间线 / 矛盾候选 / 开放问题 / 会话洞察 / 索引），nightly 自动再生成，**勿手动编辑**；
- **可信度账本**：`11-Agents/可信度账本「自动生成」`（--check 校验收敛）；**纠正账本**：`11-Agents/corrections.md`（开工必读 open 条目）。

---

## 3. Agent 专属纪律

1. **读序**（进会话第一件事）：`AGENTS.md` → `01-Rules/〔你的个人画像〕` + `〔你的领域通用规范〕` → 项目 `WORKMEMORY/INDEX.md` → `work.log` 尾 50 行 → `corrections.md` open 条目（**不重犯已登记纠正**）。
2. **检索优先**：写代码/查方案前先 `search-vault`（MCP: coding-vault-search）查库，命中即复用，禁止凭记忆重写既有规范。
3. **沉淀闭环**：会话结束前必问「用户纠正过什么」→ 未落地的写入 `corrections.md`（open 行）+ 交接卡；成熟纠正经 `/vault-save` 蒸馏后回填 `vault://` 路径并置 closed。
4. **收尾**：临时文件清干净；`work.log` 补 `WORK_END`；交接卡按 token 预算分节（vault-handoff SKILL v2）。

---

## 4. 提交纪律：三道门

| 门 | 检查 | 被拦了怎么办 |
|---|---|---|
| **Gate 1** 密钥扫描 | staged diff 中的 key/token/密码字面量 | 移除敏感内容或改用环境变量；占位符示例写成 `<YOUR_KEY>` 形态 |
| **Gate 1.5** URL 安全 | URL 携带凭证型参数名（key/token/secret…） | 示例 URL 拆段书写（协议与参数分开），或改非 URL 形态 |
| **Gate 2** 质量门禁 | frontmatter 七字段 + 枚举、断链、双版本漂移 | 按报告逐条修；新 `.md` 必带 frontmatter |

- **绝不** `git commit --no-verify`。
- 写盘类自动化（consolidate/auto-linker/dashboards/insights）执行前**先 git 提交当前改动**，出问题可整体回滚。
- 被拦后先 `git diff` 看是什么被扫中，不要反复盲试。

---

## 5. 自动化全景

| 频率 | 动作 | 入口 |
|---|---|---|
| 随时（只读） | 一键巡检 | Home 控制舱 🛡️ 按钮，或逐条跑 §README 命令表 |
| 随时（写盘，需确认） | 晋级 / 补链 / 仪表盘 / 洞察 | Home 控制舱 ⚠️ 按钮 |
| 每晚 03:00 | nightly 7 步（含 git sync） | `nightly-maintenance.py`（计划任务 `setup-nightly-task.ps1`） |
| 每次提交 | 三道门 | pre-commit（`core.hooksPath .githooks`，clone 后手动配一次） |

---

## 6. 故障排查速查

| 症状 | 定位 |
|---|---|
| 提交被 Gate 1 拦 | `git diff --staged` 找密钥字面量；测试/文档里的示例用 `<YOUR_*>` 占位 |
| 提交被 Gate 1.5 拦 | 输出会列出命中的 URL 与参数名；示例改拆段书写 |
| Gate 2 报 frontmatter ERROR | 报告列出文件名——补七字段；**注意 `.tmp-*` 临时文件也会被扫** |
| `pytest` 里 `test_capability_commands` 失败 | 它实跑真库命令——**先查工作树脏文件**（无 frontmatter 的新 md 等），再怀疑被测命令 |
| healthcheck FAIL | 报告按 Check 1-10 分节，逐条对修复；`Overall: ALL PASSED` 才是干净态 |
| 仪表盘内容过期 | `python scripts/vault-dashboards.py --apply` + `vault-insights.py --apply`（nightly 也会自动刷） |
| 控制舱按钮点了没反应 | 标题栏显示「复制模式」= 当前环境无 Node 集成，命令已复制到剪贴板，去终端执行 |
| clone 首日「最近 7 天精进资产」/沉淀热力图统计虚高 | git 检出把全部文件 mtime 重置为检出时刻，几乎所有笔记入选属正常现象，运行几天自然回落（非数据损坏） |

---

## 7. 延伸阅读

- 架构与设计决策：`examples/ADR/0001-example-reading-workflow.md`
- 跨 Agent 工作记忆协议：`01-Rules/CROSS-AGENT-MEMORY.md`
- 会话现场保护（compact 前后必做）：`01-Rules/SESSION-SNAPSHOT-PROTECTION.md`
- 自动化踩坑清单：`01-Rules/AUTOMATION-GOTCHAS.md`
- 工具链细节：`scripts/README.md`
