---
title: "自动化流水线踩坑清单 (Vault Automation Gotchas)"
created: 2026-09-09
updated: 2026-09-09
type: rules
tags:
  - category/rules
  - topic/automation
  - topic/vault
  - topic/agent
status: active
audience: both
authority: primary
claim_risk: medium
review_status: unreviewed
---

# 自动化流水线踩坑清单 (Vault Automation Gotchas)

> **定位**：vault 自动化（脚本 / 生成器 / pre-commit Gate / 跨 harness hook / 编排流程）的**一手踩坑账本**。每条都来自真实事故，附复现条件与防线。与 环境说明（本机环境事实）、[[01-Rules/TESTING-PATTERNS]]（测试纪律）互补。

## 1. 生成型工具写盘前 MUST 脱敏 URL（Gate 1.5）

- **事故**：`vault-dashboards.py` 把库内既有示例 URL（`…?key=…`）原样引用进新生成的页面 → nightly 提交被 pre-commit Gate 1.5 拦截（rc=1），且**每夜必然复现**。
- **复现条件**：任何"引用原始内容 → 生成新文件 → 自动提交"的工具（仪表盘、摘要、报告）。
- **防线**：生成层统一 `re.sub(r"https?://\S+", "〈URL-已隐去〉")`，并用测试钉死（页面 MUST NOT 含 `https://`）。测试用例自身的字面 URL 也要**拆段构造**（`"https://" + "host?key=" + "…"`），否则测试文件本身被 Gate 1.5 拦。

## 2. 编排者临时文件 MUST 自带 frontmatter

- **事故**：夜间任务书/评审书落在库根（`.tmp-*-brief.md`）无 frontmatter → Gate 2 判 ERROR，连带 `test_capability_commands`（实跑真库双命令）红灯；**同一原因连坐 5 次**。
- **防线**：agent 在库内写任何 `.md`（含临时件）MUST 带 7 必需字段；临时件优先放库外或用 `.txt`；收工 MUST 清理（本条也是"离开时更干净"）。
- **判读提示**：`test_capability_commands` 失败时**先查工作树脏文件**，不要先怀疑被测命令。

## 3. hook 事件选型：先确认 stdout 是否真的进上下文

- **事故**：用 `PostCompact` 打印"恢复现场提醒" → 空转。Claude Code 只有 `UserPromptSubmit` / `SessionStart` / `PostModelSwitch` 的纯文本 stdout 会注入上下文，`PostCompact` 无决策控制、其输出仅进 debug log。
- **防线**：任何"自动注入/恢复上下文"方案 MUST 先查事件契约再选型；注入口用 `SessionStart(matcher: "compact")` 的 `additionalContext`，且 stdout **MUST 只有一行 JSON**。详见 [[01-Rules/SESSION-SNAPSHOT-PROTECTION]]。

## 4. 归档引擎会误判归属，人工复核 + 固化路由

- **事故**：4 篇"自有项目排障复盘"被 `vault-inbox-consolidate` 判入 `06-Sources/Articles`（外部研读区）——标签命中 `topic/architecture` 即走 `source-article`，与"这是谁的经验"无关。
- **防线**：①执行后 MUST 复核目标区是否符合 [[01-Rules/VAULT-STRUCTURE]] 归属裁决表；②项目类复盘加 `project/<name>` 标签并在 `scripts/routing.json` 增设 `type: "project"` 路由（置顶优先于 `topic/*`），让改判只发生一次。

## 5. 防回归断言 MUST NOT 写成"冻结集合"

- **事故**：`routing 契约测试` 用 `set(loaded) == set(LEGACY)` 钉等价性 → 新增一条合法路由即红灯，防回归护栏变成演进阻挡。
- **防线**：基线断言改为**子集回归防护**（旧基线 MUST 全部保留）+ **新增项逐条钉死**（`NEW_ROUTES` 精确比对）。判据：断言失败时应先问"这是回归还是演进"。

## 6. 写盘工具的「已处理」判定 MUST 读回真实状态

- **事故**：`vault-auto-linker.py --apply` 在**已含** `〔你的领域通用规范〕` 的行上再次插入同目标链接（同一行出现两个同目标链接）。`file_linked_concepts` 每文件从空集开始，只记录本次运行插入的链接，从不读取文件既有 wikilink——"已链接防护"只防本次运行内重复，对历史状态失明。
- **防线**：幂等判定 MUST 基于读回的文档真实状态——先提取全部既有目标（全路径与文件名两种形式归一，含别名与 embed），再决定是否插入；MUST NOT 只依赖本次运行的工作内存。
- **同族教训**：测试环境 MUST 与生产语义对齐（把 `current_file` 误设为目标文件会触发"自我链接规避"，差点误判修复无效）。

## 7. 关联索引

- 本机环境事实：环境说明
- 测试纪律与死测试防御：[[01-Rules/TESTING-PATTERNS]]
- 会话现场保护与 hook 契约：[[01-Rules/SESSION-SNAPSHOT-PROTECTION]]
- 目录归属裁决表：[[01-Rules/VAULT-STRUCTURE]]
- 摄入与晋级管线：[[01-Rules/INGESTION-WORKFLOW]]
