---
title: "ADR-0005: 知识库 CS 专业领域驱动架构与 99-Inbox 兜底重构"
created: 2026-08-30
updated: 2026-08-30
type: notes
tags:
  - category/project
  - topic/adr
  - topic/architecture
  - topic/项目档案
status: stable
audience: both
authority: synthetic
claim_risk: medium
review_status: unreviewed
---

# ADR-0005: 知识库 CS 专业领域驱动架构与 99-Inbox 兜底重构

## 1. 背景与问题陈述 (Context)

原 Coding 知识库（`{{VAULT_ROOT}}`）采用扁平的 `00~09` 编号体系：
1. **语义逻辑倒挂**：暂存区 `08-Inbox` 夹在日常流水 `07-Daily` 与持久知识域 `09-Career` 之间，破坏了 Johnny Decimal 体系中「持久领域连续编号」的一致性；
2. **专业领域缺失**：面向计算机专业学生（CS）与全生命周期工程师演进，缺少计算机底层基石（OS、网络、体系结构、编译原理）、现代系统架构与中间件（MySQL、Redis、Kafka、分布式系统）、以及硬核课程实验（待自建）（分布式课程实验, 数据库课程实验, 网络课程实验, 操作系统课程实验）的专属一级目录；
3. **Agent 路径漂移风险**：未提前预置高频子目录（如 Java, SQL, Dart, Lua），导致 AI Agent 在自动归档时易发生命名随意化或根目录污染。

---

## 2. 决策考量因素 (Decision Drivers)

- **结构纯洁度**：持久知识域与瞬态暂存区必须具有清晰的物理与逻辑边界；
- **全生命周期覆盖**：无缝容纳大学核心课、神课硬核 Lab、实战工程与高并发面试系统设计；
- **自动化稳定性**：零断链（Zero Broken Links），全套门禁脚本与 MCP 工具链 100% 自动自愈；
- **确定性路由 (Deterministic Routing)**：预置标准目录骨架，消除 Agent 自由发挥导致的命名混乱。

---

## 3. 决议方案 (Decision Outcome)

决定将全库重构为 **CS 专业全生命周期领域驱动架构（00~10 + 99-Inbox）**：

1. **核心四大件立域**：新建 `02-Fundamentals/`（OS、Net、Arch、Compilers 4 大核心子域）；
2. **语言矩阵平移**：原 `02-Languages` 顺移至 `03-Languages/`，并预置 `Java/`, `SQL/`, `Dart/`, `Lua/`, `HTML-CSS/` 骨架；
3. **系统与中间件立域**：新建 `04-Systems/`（Databases、Caching-MQ、Distributed-Systems、Cloud-Native、Linux-Perf）；
4. **工具与文献平移**：`05-Tools/`、`06-Sources/`、`08-Projects/` 依次顺移；
5. **硬核课程实验（待自建）立域**：新建 `07-Academics/`（该课程实验, 该课程实验, Stanford-网络课程实验, 该课程实验-操作系统课程实验, Course-Labs, Thesis）；
6. **求职与日常归位**：保留 `09-Career/`，日常台账设为 `10-Daily/`；
7. **暂存池彻底末级兜底**：原 `08-Inbox` 重构为 `99-Inbox/`，作为 A-MAC 准入待分流池；
8. **全量脚本与链接重构**：更新全库 287 条 Wikilink，升级 `vault-quality-check.py`、`vault-healthcheck.py` 与 `vault-inbox-triage.py`。

---

## 4. 积极后果与消极妥协 (Consequences)

### 正面收益
- **逻辑彻底自洽**：`01~10` 均为高凝聚的持久领域，`99-Inbox` 彻底退居末位作为流水线漏斗；
- **零漂移摄取**：预置目录配合 `README.md` 元数据，AI Agent 执行 `vault-save` 自动对号入座；
- **自动化门禁满分**：`vault-quality-check.py --strict` 保持 100.0/100 满分，287 条 Wikilink 0 坏链。

### 妥协与代价
- 顶级目录从 10 个扩充至 12 个，需在 `Home.md` 与 MOC 中维护更丰富的全局星系导航图谱。
