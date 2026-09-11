---
title: "{{title}} 开发规范 — Agent 约束版"
created: {{date}}
updated: {{date}}
type: standards
audience: agent
tags:
  - lang/{{lang}}
  - category/rules
status: draft
source: ""
# authority 默认 official（语言规范预期上游为官方标准）；待作者按实际来源改，枚举定义见 scripts/vault-quality-check.py（authority / claim_risk）
authority: official
cheatsheet: "{{LANG}}-CHEATSHEET"
---

# {{title}} 开发规范 — Agent 约束版

> 基于权威工程实践与官方规范。
> 本文件为 AI Agent 编写、重构或审查 {{title}} 代码时必须遵守的唯一事实源 (Source of Truth)。
> 对应人类速查版本请查阅：{{LANG}}-CHEATSHEET

---

## 1. 适用范围与目标

- **适用范围**：所有涉及 {{title}} 的代码编写、重构、审查及测试用例生成。
- **核心目标**：
  1. 保证代码的简单性与可读性，消灭过度抽象与投机设计。
  2. 统一工程风格，降低维护认知负荷。
  3. 杜绝常见运行时陷阱与安全隐患。

---

## 2. 术语与规范级别 (RFC 2119)

- **MUST / 必须**：绝对要求，违反即视为严重 Bug 或工程错误。
- **MUST NOT / 禁止**：绝对禁止，任何情况下不得出现该模式。
- **SHOULD / 应当**：强烈推荐，除存在充分且有据可查的特殊理由外必须遵守。
- **SHOULD NOT / 不应当**：强烈不推荐，除非经过充分权衡并记录技术决策。
- **MAY / 可以**：可选的最佳实践，开发者可根据上下文自主决定。

---

## 3. 核心规范条款

### 3.1 标识符命名与声明 (MUST)

- **表意优先 (MUST)**：命名 MUST 揭示意图，禁止无意义的缩写与单字母变量（局部计数器除外）。
- **作用域法则 (SHOULD)**：标识符长度 SHOULD 随作用域增大而增长。短生命周期用短名，长生命周期、包级别用具名全称。
- **禁止类型编码 (MUST NOT)**：MUST NOT 将变量类型作为名称前缀或后缀（如 `userMap`, `itemArr`, `userPtr`）。
- **一致性 (MUST)**：同一概念在模块及全工程中 MUST 保持统一命名。

### 3.2 架构与包/模块设计 (MUST)

- **单一职责 (MUST)**：模块与函数 MUST 只做一件事，保持小巧且内聚。
- **禁止无意义聚合包 (MUST NOT)**：MUST NOT 创建 `util`, `common`, `base`, `helpers` 等大杂烩包；逻辑应归属到领域调用者内部。
- **最小化公开接口 (SHOULD)**：对外暴露的 API SHOULD 保持极简，优先使用不可变或受限参数接口。
- **防御深层嵌套 (MUST)**：MUST 优先采用 Guard Clauses（卫语句）提前退出，降低认知复杂度。

### 3.3 错误处理与健壮性 (MUST)

- **显式处理 (MUST)**：所有错误 MUST 显式捕获并处理，MUST NOT 吞没异常或静默忽略错误返回值。
- **错误只处理一次 (MUST)**：对同一个错误，MUST 严格在“记录日志”或“向上抛出/包装返回”中二选一，禁止重复处理。
- **附加上下文 (SHOULD)**：向上抛出错误时 SHOULD 附加当前操作层面的语义上下文。

### 3.4 资源管理与生命周期 (MUST)

- **成对申请释放 (MUST)**：所有持有系统资源（文件句柄、网络连接、数据库连接、锁）的操作 MUST 确保生命周期闭环。
- **显式取消机制 (MUST)**：异步任务与长期运行的任务 MUST 提供可被外部打断和优雅退出的机制（如 Context/CancellationToken）。

---

## 4. 推荐模式与反模式 (Bad vs Good)

### 4.1 命名与卫语句

```{{lang}}
// ❌ Bad: 深层嵌套与含糊命名
function process(d, f) {
  if (d != null) {
    if (f) {
      // 业务逻辑
    }
  }
}

// ✅ Good: 意图清晰与卫语句提前退出
function processUserData(userData, isSyncRequired) {
  if (userData == null) {
    return;
  }
  if (!isSyncRequired) {
    return;
  }
  // 业务逻辑
}
```

### 4.2 错误传播与上下文

```{{lang}}
// ❌ Bad: 吞掉错误或无意义裸转
try {
  fetchResource(id);
} catch (e) {
  return null;
}

// ✅ Good: 显式包装附加上下文
try {
  fetchResource(id);
} catch (error) {
  throw new ResourceFetchError(`Failed to fetch resource by ID ${id}`, { cause: error });
}
```

---

## 5. 常见陷阱与防御

| 陷阱类型 | 触发场景 | 潜在危害 | 防御规范与策略 |
|---|---|---|---|
| 空指针 / 悬空引用 | 未验证返回值直接解引用 | 进程 Panic / 运行时崩溃 | 强制非空断言/可选链/显式检查 |
| 资源泄漏 | 循环或异常分支未释放资源 | FD 耗尽、内存 OOM | 使用 `defer`/`try-with-resources`/`using` |
| 并发数据竞争 | 多个线程/协程无锁读写共享内存 | 数据错乱、非预期行为 | 明确所有权或加互斥锁、通道同步 |
| 隐式类型转换 | 宽松比对操作符或隐式强转 | 逻辑漏洞、难以排查的 Bug | 强制使用严格相等比对与静态检查 |

---

## 6. 变更记录

| 日期 | 版本 | 变更内容概要 | 变更人 / Agent | 审阅状态 |
|---|---|---|---|---|
| {{date}} | v0.1.0 | 初始草案建立 | {{author}} | 待初审 |
