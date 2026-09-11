---
title: "ADR-0002: server.py 单体拆分为多模块"
created: 2026-08-29
updated: 2026-08-29
type: notes
tags:
  - category/project
  - topic/adr
  - project/demo-project
status: stable
audience: both
authority: synthetic
claim_risk: medium
review_status: unreviewed
---

# ADR-0002: server.py 单体拆分为多模块

## 1. 背景与问题陈述

示例项目 后端 `server.py` 增长到3053行，路由、NLP处理、数据库操作、SSRF安全、备份恢复、TTS语音合成全部混在一个文件里。改动任何一个功能都要通读全文，代码导航困难，新贡献者入门成本高。

## 2. 决策考量因素

- **可维护性**：按职责分文件后，每个模块约200-900行，职责边界清晰
- **零行为变化**：重构不改变任何API行为，316测试必须全绿
- **依赖无环**：拆分后模块间不能形成循环导入
- **向后兼容**：`test_server.py` 大量 `from server import ...`，通过重导出保持兼容
- **渐进式**：分4个阶段（nlp → database → security → 清理），每阶段独立可验证

## 3. 决议方案

拆为4个文件：

| 模块 | 行数 | 职责 |
|---|---|---|
| `nlp.py` | ~400 | spaCy加载 + CEFR + 文本分析 |
| `database.py` | ~900 | DB初始化 + CRUD + 备份恢复 + Anki导出 |
| `security.py` | ~200 | SSRF + URL安全 + HTML清洗 + RSS解析 |
| `server.py` | ~600 | app对象 + 路由注册 + 中间件 + 静态文件 |

依赖图：`server → database → nlp`，无环。`nlp.py` 不依赖database，保持纯计算。

被拒绝的方案：
- 不拆（维持现状）：3053行单文件继续恶化
- 按路由分（article_routes.py, card_routes.py）：路由函数依赖database层的函数，拆路由就要传参或全局状态，增加复杂度
- 按技术层分（routes/models/services）：FastAPI路由本身就是"service"，额外抽象层是YAGNI

## 4. 积极后果与消极妥协

- **正面收益**：每个模块职责单一，新贡献者只需读相关模块；IDE跳转更快；模块可独立测试
- **妥协风险**：`server.py` 通过 `from nlp import ...` 重导出，测试import路径不变但实际代码位置变了，grep搜函数名要多看一个文件；`nlp.py` 顶层加载spaCy的副作用保留在import时执行，跟拆分前行为一致但不够显式
