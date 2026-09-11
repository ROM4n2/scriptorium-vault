---
title: "高效阅读方法规范 (示例 · Agent 约束版)"
created: 2026-09-10
updated: 2026-09-10
type: standards
tags:
  - category/rules
  - topic/reading
  - status/stable
status: stable
audience: agent
source: "示例组（中立领域演示：高效阅读）"
cheatsheet: "[[examples/READING/READING-CHEATSHEET|阅读速查表 (人类版)]]"
authority: synthetic
claim_risk: low
review_status: unreviewed
---

# 高效阅读方法规范（示例）

> **本文件是「双版本制」演示的上半部分**：写给 Agent 的严格约束（RFC 2119）。人类读者请看 [[examples/READING/READING-CHEATSHEET|速查表]]，章节编号与本文件 1:1 对齐。

## 1. 阅读前的准备

1. **阅读 MUST 先写下一个问题**：在开始读之前，用一句话写下「我想从这本书里得到什么」。没有问题的阅读 MUST NOT 开始。
2. **选书 SHOULD 遵循「先广后深」**：同一主题先读 2–3 本入门书建立地图，再挑 1 本深入，MUST NOT 一上来就啃最难的那本。
3. **时间盒 MUST 预先设定**：单次阅读时长 SHOULD 在 25–50 分钟之间；超时未完成 SHOULD 记为下次起点，MUST NOT 无边界延长。

## 2. 阅读中的动作

1. **主动提问 MUST 每章至少一次**：读每章前把标题改写成疑问句，读完自答；答不上来的部分 SHOULD 回读该章。
2. **笔记 MUST 与原文分离**：书中划线属原文，个人复述才属笔记；笔记 MUST NOT 直接抄原句（除非该句本身是定义或数据）。
3. **MUST 记录「与我已有的什么冲突」**：读到与你既有认知冲突的观点时，MUST 记下冲突点，这比记录认同点价值更高。
4. **遇到不懂 SHOULD 先标记后跳过**：单个障碍 SHOULD NOT 阻塞整章；标记后继续，读完全章再回头，MUST NOT 在首次遇到时死磕超过 10 分钟。

## 3. 阅读后的沉淀

1. **读完 MUST 产出一条可复述结论**：用不超过三句话复述本书核心主张；写不出来 SHOULD 视为没读完。
2. **笔记 MUST 进入 Inbox 流转**：阅读笔记先行落 `99-Inbox/`，再由 `vault-inbox-consolidate` 晋级；MUST NOT 直接写入正式区。
3. **落地检查 SHOULD 在 48 小时内进行**：写下「这条结论改变了我的哪个具体行为」；无法写出行为的结论 SHOULD 标为「仅存档」。

## 4. 关联

- 阅读速查（人类版）：[[examples/READING/READING-CHEATSHEET]]
- 演示说明：[[examples/README]]
