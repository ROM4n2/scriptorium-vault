---
title: "{{title}} 代码规范速查 — 人类参考"
created: {{date}}
updated: {{date}}
type: cheatsheet
audience: human
tags:
  - lang/{{lang}}
  - category/cheatsheet
status: draft
source: ""
# authority 默认 synthetic：本表 derived 源 self（由本库 STANDARDS 派生），保守标注；枚举见 08-Projects/README.md
authority: synthetic
standards: "{{LANG}}-STANDARDS"
---

# {{title}} 代码规范速查 — 人类参考

> 基于标准工程实践与官方权威推荐。每条规则一句话核心结论 + 最短关键示例。
> 完整约束规范（Agent 判定标准）请查阅：{{LANG}}-STANDARDS

---

## 1. 一句话核心思想

> **{{core_philosophy_summary}}**（例：保持简单、显式优于隐式、可读性第一、零成本抽象与安全第一）

---

## 2. 常用语法与模式速查

### 2.1 初始化与声明
```{{lang}}
// 推荐的简洁声明与初始化范式
```

### 2.2 卫语句与控制流
```{{lang}}
// 早 return，消灭深层缩进
if (!isValid) return;
```

### 2.3 错误处理与防御
```{{lang}}
// 错误捕获与上下文附加上报
```

### 2.4 资源释放与清理
```{{lang}}
// 资源生命周期安全回收范式
```

---

## 3. 关键规则一览表

| 维度 | 核心规则（一句话） | 核心要点 / 正例简写 |
|---|---|---|
| **命名** | 意图清晰大于字数简短 | 拒绝单字母变量与类型后缀（如 `users` 而非 `usersMap`） |
| **设计** | 单一职责，禁止大杂烩 | 不建 `util`/`common` 包，就近放置到领域模块内 |
| **控制流** | 卫语句提前返回 | 遇到非法输入立即退出，主体逻辑保持 0 缩进 |
| **错误** | 显式处理，严禁吞并 | 记录与抛出二选一，包装错误附加上下文 |
| **并发** | 明确生命周期与取消传播 | 不泄漏后台任务，统一由调用方管理取消信号 |
| **依赖** | 依赖抽象，面向接口 | 参数接收最小接口，返回值提供具体实现 |

---

## 4. 常见陷阱一句话提醒

- ⚠️ **空值解引用**：访问嵌套属性或指针前必须进行空值防护。
- ⚠️ **闭包捕获循环变量**：异步或并发迭代中避免直接引用迭代变量引用。
- ⚠️ **资源泄露**：打开的文件/句柄/流必须配合作用域清理机制立即关闭。
- ⚠️ **错误只处理一次**：千万不要既打 `log.Error` 又 `return err` 导致日志雪崩。
- ⚠️ **隐式副作用**：纯查询函数严禁修改传入的对象状态。

---

## 5. 延伸阅读与标准规范链接

- 📖 **唯一事实源规范 (Agent 版)**：{{LANG}}-STANDARDS
- 🌐 **官方文档 / Style Guide**：[{{title}} Official Style Guide]({{official_guide_url}})
- 📚 **权威书籍 / 来源**：{{source}}
- 🔗 **相关领域 MOC**：[[00-MOC/MOC-Languages]]
