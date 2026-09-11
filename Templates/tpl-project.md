---
title: "{{project_name}}"
created: {{date}}
updated: {{date}}
type: project
audience: both
tags:
  - category/project
  - stack/{{stack}}
status: active
repo_path: "{{CODE_ROOT}}/{{project_name}}"
---

# {{project_name}} — 项目工程与规范笔记

---

## 0. 跨项目局部规范路由块 (Cross-Project Local Routing Contract)

> [!TIP]
> **接入指引**：复制以下 3~5 行标准契约，粘贴至代码仓库根目录的 `{{CODE_ROOT}}\{{project_name}}\.agent-rules.md` 或 `CLAUDE.md` / `GEMINI.md` 顶部即可完成规范挂载与检索联动：

```markdown
<!-- 跨项目局部规范路由契约 (Coding Vault Routing Contract) -->
> [!IMPORTANT]
> 1. **全局规范源**：本项目基础通用规范与编码准则遵循 `{{VAULT_ROOT}}\AGENTS.md`。
> 2. **精准规则检索**：遇到特定规范疑问（命名/错误处理/并发等），执行：`python {{VAULT_ROOT}}\scripts\search-vault.py "<query>" --tag lang/{{stack}}`。
> 3. **项目特化约束**：本项目架构与专属规则记录于 `{{VAULT_ROOT}}\08-Projects/{{project_name}}/{{project_name}}-DEV-RULES.md`。
```

---

## 1. 项目简介与业务背景

- **项目定位**：{{description}}
- **代码仓库绝对路径**：`{{repo_path}}`
- **主要技术栈**：#stack/{{stack}}
- **当前状态**：`{{status}}` (active / maintenance / archived)
- **核心业务价值**：

---

## 2. 核心架构与模块分布

### 2.1 整体架构设计
```text
{{project_name}}/
├── cmd/           # 入口点
├── internal/      # 私有核心业务逻辑
├── pkg/           # 可复用公共库
└── config/        # 配置文件与模板
```

### 2.2 核心模块职责矩阵
| 模块 / 目录 | 职责范围 | 关键依赖 | 负责人 / 核心维护者 |
|---|---|---|---|
| `core/` | 核心领域逻辑与数据处理 | 无外部依赖 | |
| `api/` | HTTP/gRPC 接口路由与控制层 | `core/` | |
| `storage/`| 数据持久化与缓存操作 | DB Driver, Redis | |

---

## 3. 项目专属规范与约束

> [!IMPORTANT]
> 基础通用规则遵循 〔你的领域通用规范〕 与对应语言规范。以下为本项目的特化约束：

- **架构约束**：
- **命名与分层约束**：
- **数据一致性与事务要求**：
- **配置与密钥规范**：禁止硬编码，本地敏感文件严格纳入 `.gitignore`。

---

## 4. 常用开发与构建命令

```bash
# 1. 依赖安装与更新
# pnpm install / go mod download / cargo check

# 2. 本地开发调试
# pnpm dev / go run ./cmd/...

# 3. 单元测试与集成测试
# go test -race ./... / pnpm test

# 4. 构建发布产物
# docker build -t {{project_name}}:latest .
```

---

## 5. 关键依赖与环境要求

| 组件 / 依赖项 | 最低版本要求 | 环境变量 / 配置名 | 备注与说明 |
|---|---|---|---|
| Runtime | | `NODE_ENV` / `GO_ENV` | |
| Database | | `DATABASE_URL` | 本机 Docker MySQL:3306 |
| Cache | | `REDIS_URL` | 本机 Docker Redis:6379 |

---

## 6. 踩坑记录与解决方案

### 6.1 {{issue_title_1}}
- **现象描述**：
- **根本原因**：
- **解决方案与修复代码**：
- **后续防御策略**：

---

## 7. 关联索引
- 跨语言规范：〔你的领域通用规范〕
- Git 工作流：[[01-Rules/GIT-CONVENTIONS]]
- 技术栈规范：{{stack}}-STANDARDS
- 知识库首页：[[00-MOC/Home]]
