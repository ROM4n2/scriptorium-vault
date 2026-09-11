---
title: "{{title}} 顶校神课实验攻坚与复盘"
created: {{date}}
updated: {{date}}
type: project
tags:
  - category/project
  - topic/academics
  - topic/lab
status: active
audience: both
source: "MIT/CMU/Stanford 课程官网"
---

# {{title}} 顶校神课实验攻坚与复盘

> **实验背景**：记录 分布式课程实验 / 数据库课程实验 / 网络课程实验 / 操作系统课程实验 等硬核实验的设计思路、状态机与调试复盘。

---

## 1. 实验目标与不变式约束 (Invariants)

- **核心任务**：
- **系统必须满足的不变式 (Invariants)**：
  1. 约束 1：
  2. 约束 2：

---

## 2. 核心状态机与协议设计 (State Machine & Protocol)

```text
[State A: Follower] ──(Timeout)──> [State B: Candidate] ──(Votes Granted)──> [State C: Leader]
```

---

## 3. 棘手死锁/竞态排查与 Bug 复盘 (Debugging & Post-mortem)

- 🐛 **Bug 1 (死锁/竞态)**：
  - **现象**：
  - **根因分析**：
  - **修复代码与防护**：

---

## 4. 测试集覆盖与压测通过 (Verification)

```bash
# 测试运行命令与通过证据
```
