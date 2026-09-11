---
title: "项目架构设计与工程规约模板"
created: 2026-08-28
updated: 2026-08-28
type: project
tags:
  - category/project
status: stable
audience: both
authority: synthetic
claim_risk: medium
review_status: unreviewed
---

# 📁 {{PROJECT_NAME}} — 架构设计与工程规约

> **仓库路径**：`{{CODE_ROOT}}\{{PROJECT_NAME}}`
> **核心定位**：{{PROJECT_DESCRIPTION}}

---

## 1. 系统架构与模块分布
- `api/`：HTTP / gRPC 路由与协议转换
- `service/`：核心业务逻辑编排
- `store/`：数据库与缓存持久化

## 2. 专属工程约束 (ADR 索引)
- 见 [[08-Projects/_template/01-ADR/0001-template-adr|01-ADR/]] 目录
