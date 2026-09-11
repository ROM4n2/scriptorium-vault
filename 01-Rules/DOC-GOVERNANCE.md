---
title: "交接文档职责分层与 Deletion Test 应用于文档"
created: 2026-09-05
updated: 2026-09-06
type: standards
tags:
  - category/rules
  - topic/architecture
  - topic/agent-conduct
status: stable
audience:
  - architect
  - agent
source: "Session Discovery (示例项目 文档重构会话, 2026-09-05)"
authority: synthetic
claim_risk: high
review_status: unreviewed
---

# 交接文档职责分层与 Deletion Test 应用于文档

## 1. 问题：入口文档的职责漂移

交接文档（如 AGENTS.md）容易膨胀到数百 KB，同时承担快照、架构手册、变更日志、问题档案四个角色。每个 agent 会话都要读它，token 成本爆炸；更糟的是快照区已与真实状态脱节，版本历史表缺漏——读它的人拿到的是自相矛盾的项目认知。

**根因**：「机器可读快照」没有职责边界，所有维护者都往里追加；「反历史教训」性质的内容天然越积越多，没人敢删。

## 2. 解法：按信息正主分层

每层只回答一类问题：

```text
AGENTS.md（~25 行，纯路由）
  ├─ WORKMEMORY 约定 + 文档路由表 + 一句话定位
  ├─ 状态/红线/待办 → WORKMEMORY/PROJECT_OVERVIEW.md（第二读，60 秒 primer）
  ├─ 架构细节 → docs/agents/architecture.md
  ├─ 安全守卫/本机环境/工作惯例 → docs/agents/ops.md
  └─ 版本历史 → README Roadmap changelog（它本来就是发布记录的正主）
```

## 3. Deletion Test 用于文档而非代码

| 手法 | 规则 |
|------|------|
| 劣化副本直接删 | 两处都写状态 = 两处都会陈旧；只留一处，另一处给指针 |
| 已完结历史直接删 | git 历史本身就是归档，已勾选待办无需保留 |
| 重复信息归一正主 | 每条信息只能有一个权威来源 |
| 防回搬锁 | 入口文件尾注写死「保持纯路由形态——内容只放下游文档，不要往回搬」 |

## 4. 防御性工程规范 (Defensive Rule)

- **「必读文件」只放路由与最小状态**。任何 agent/新人要读的入口文件超过 ~100 行，就该拆——它已经不是入口，是仓库。
- **新增内容前先问正主**：这条信息属于哪个文档的职责？如果已有正主（如 changelog），入口文件只留一行指针，绝不复制第二份（副本必然漂移）。
- **文档也要过 Deletion Test**：重构前先问「能不能删」——尤其已完结的历史记录，git 历史本身就是归档。
- **快照类内容必须有唯一正主 + 下游文档负责更新**，否则快照自己会变成最大的错误信息源。

## 5. 关联规范

- Git 提交与安全：[[01-Rules/GIT-CONVENTIONS]]
- Agent 行为守则：[[01-Rules/AGENT-CONDUCT]]
- Vault 结构规范：[[01-Rules/VAULT-STRUCTURE]]
