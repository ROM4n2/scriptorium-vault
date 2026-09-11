---
title: "子代理定义文件审计清单：工具名对齐、最小权限与 Maker-Checker 职责分界"
created: 2026-09-06
updated: 2026-09-06
type: standards
tags:
  - category/rules
  - category/subagents
  - topic/agent-architecture
status: stable
audience:
  - architect
  - agent
source: "Session Discovery (示例项目 Phase 2a, 对 Code-Plan Executor 定义文件的实战审计)"
authority: synthetic
claim_risk: high
review_status: unreviewed
---

# 子代理定义文件审计清单：工具名对齐、最小权限与 Maker-Checker 职责分界

## 1. 问题：子代理定义文件的三类致命缺陷

给宿主 IDE 配置编码子代理（maker，执行实施计划）时，审计其定义文件发现三类会导致真事故的问题：

1. **正文引用的工具名不存在**：frontmatter tools 白名单是对的，但正文指令层引用了别的生态的工具名（如 Claude Code 的 `search_code` 而非宿主的 `search_content`）——轻则运行时报错，重则模型绕开指令自由发挥。
2. **自检只有 lint/compile**：静态检查绿 ≠ 回归绿。collect-only 全绿 + 定向跑全绿之后，分片全量回归仍可能抓出运行期断裂。
3. **工具面全开**：17 个 MCP + 递归派发子代理 + 联网 + 云凭证全给一个编码执行器——攻击面、分心面、递归嵌套三重风险。

## 2. 审计清单（六查）

| # | 审计项 | 要求 |
|---|--------|------|
| 1 | 工具名逐个对齐宿主 | frontmatter tools 与正文引用两处都要核对，正文里出现的每个工具名必须在宿主真实存在 |
| 2 | maker 白名单最小化 | 裁掉 `task`（禁递归派发）、`web_fetch`/`web_search`（遇到不认识的 API 应 HALT 上报，不是自查自改）、云凭证类与无关域 MCP |
| 3 | 自检升级为证据门控 | 静态检查 + 计划指定的测试命令，输出贴 tail 存进报告（JSON 加 `test_evidence` 字段）；TDD 任务强制先写失败测试（RED）再实现（GREEN） |
| 4 | 提交边界 | maker 禁 `git commit`/`git push`/`git checkout --`/`git reset`/`git restore`，提交权归编排者主线程 |
| 5 | 补 checker 席位 | 纯只读（物理隔离 > 提示词约束），红黄牌协议，加 anti-sycophancy 条款 |
| 6 | 职责分界写进两边 | maker 报告 → checker 验收 → 编排者 commit/push + 分片全量回归 |

## 3. 防御性工程规范 (Defensive Rule)

- 新建任何子代理 **MUST** 过三查：宿主工具名核对、白名单最小化、自检证据门控。
- checker **MUST** 无写工具（物理隔离 > 提示词约束）；maker **MUST** 无提交权（历史改写类 git 命令逐一点名禁止）。
- 子代理提示词里的禁令必须落到具体命令/工具名，抽象原则对 LLM 执行者约束力弱。

## 4. 运行期实测补充（maker-checker 三律，2026-09-07 vault-exec Phase 2a）

配置审完后，跑 8 轮 maker-checker 流水线的运行期纪律（每轮 ≈CPE 实现 + CRV 验收 + 编排者提交）：

1. **UNVERIFIED 是设计特征，不是缺口**：只读 checker 无 shell，凡需跑命令/看 git 的项一律如实列 `unverified`；**编排者必须逐条核销后才提交**（git diff 范围、`-race` 实跑、真实 e2e 复跑）。两条腿缺一不可：静态审 + 实跑验证。
2. **黄牌债务折入下 Task 的 step0**：CRV 的非阻塞黄牌不返工不遗留——登记进下个 Task 派发 prompt 的「Step 0」，附 fix_hint 原文；跨 Task 语义类偏差（如命名、拓扑口径）记入最终文档回填清单。8 轮黄牌全部闭环，零 backlog。
3. **派发 prompt 完整性 = 质量上限**：每次派发必须自包含（计划原文节选 + 目标文件 + TDD 顺序 + 门禁命令 + 禁令 + plan_id）；prompt 被截断或漏 `subagent_name` 会导致整轮取消/报错——宁可慢发完整，不发残缺。
4. **口述证据校验位**：maker 报告的 test_evidence 必须与代码静态自洽（测试数量、断言强度、依赖树可交叉核对），CRV 对锁版 SDK/服务端真源逐字段比对（如 403 detail 原文），拒绝「我跑过了」式口头证据。

## 5. 关联规范

- Agent 行为守则：[[01-Rules/AGENT-CONDUCT]]
- 交接文档分层：[[01-Rules/DOC-GOVERNANCE]]
- Git 提交安全：[[01-Rules/GIT-CONVENTIONS]]
