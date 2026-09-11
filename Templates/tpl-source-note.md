---
title: "{{title}}"
created: "{{date}}"
updated: "{{date}}"
type: source-notes
audience: both
tags:
  - source/reading        # 载体细分可加：source/book、source/video、source/article、source/paper（Obsidian 标签不允许 {} | 字符，MUST 手填具体值）
  - topic/{{topic}}
status: draft
source_url: ""
author: ""
rating: ""
# 来源可信度三字段（枚举判据见 08-Projects/README.md）：authority 按实际来源判定，claim_risk 按规范性断言强度评估
authority: unknown
claim_risk: none
review_status: unreviewed
---

# {{title}} — 研读与知识提取笔记

---

## 1. 来源基本信息

- **原始标题**：{{source_title}}
- **作者 / 讲师**：{{author}}
- **来源载体**：{{type}}　（book / video / article / paper 选一）
- **原文链接 / 资源入口**：[{{source_url}}]({{source_url}})
- **推荐评分**：⭐⭐⭐⭐⭐ ({{rating}})
- **相关标签**：#source/{{type}} #topic/{{topic}}

---

## 2. 核心观点总结

> **高维概括（3~5 句话）**：
>
> 1.
> 2.
> 3.

---

## 3. 关键知识点提炼

### 3.1 核心概念与理论机制

- **概念 1**：定义与作用机制。
- **概念 2**：权衡考量与边界条件。

### 3.2 技术演进与方案对比

| 方案 / 选型 | 优势 | 局限性 | 适用业务场景 |
| ----------- | ---- | ------ | ------------ |
| 方案 A      |      |        |              |
| 方案 B      |      |        |              |

---

## 4. 关键方法与可复用范式（技术类来源适用；人文类来源可整节删除）

### 4.1 典型范式

```{{lang}}
// 来源中推荐的高质量范式与落地实现
```

### 4.2 避免的反模式

```{{lang}}
// 来源中指出的反模式或常见设计陷阱
```

---

## 5. 待沉淀为规范的候选规则 (-> Inbox / Rules)

> [!TIP]
> 记录可以提炼并沉淀到 `01-Rules/` 或 `03-Languages/{LANG}/` 中的通用工程规则。Agent 可自动根据此区内容提炼至 `99-Inbox/`。

- [ ] **候选规则 1**：【规则名称】一句话陈述，规范级别 (MUST/SHOULD)。
  - _提炼依据_：源于第 X 节分析。
  - _目标归属_：〔你的领域通用规范〕 或对应语言规范。
- [ ] **候选规则 2**：【规则名称】一句话陈述，规范级别 (MUST/SHOULD)。
  - _提炼依据_：
  - _目标归属_：

---

## 6. 个人思考与延伸

- **启发与共鸣**：
- **现有项目结合点**：
- **后续待探索问题 / 疑问**：
- **关联 MOC**：[[00-MOC/MOC-Sources]]
