---
title: "Markdown 表格追加与程序化写操作防御规范"
created: 2026-09-02
updated: 2026-09-02
type: rules
tags:
  - category/rules
  - topic/automation
  - topic/architecture
  - lang/python
  - category/troubleshooting
status: stable
audience: both
source: "review-log 按月分片收尾 session (2026-09-02)"
authority: synthetic
claim_risk: high
review_status: unreviewed
---

# Markdown 表格追加与程序化写操作防御规范 (Markdown Table Append)

> 适用：任何脚本/程序向 Markdown 表格或文件追加内容（审计日志、索引表、注册表、分片明细）的场景。
> 通用机器校验解析防御另见 [[01-Rules/MARKDOWN-REGISTRY-VALIDATION]]；wikilink 总规范见 [[01-Rules/AGENT-CONDUCT]] §2。

## 1. 表格追加陷阱 (Symptom & Root Cause)

把审计明细从「单体 `review-log.md` 滚动追加」重构为「按月分片 `logs/YYYY-MM.md`」后，若多个脚本各自 `open(target, "a")` 追加，当分片文件尾部已存在 prose 段落（如 Inbox 清零详记）时，裸追加把新行落到段落后，Markdown 表格在空行处断裂，新行孤立为无效表格（Obsidian 不渲染、门禁也可能漏判）。

- **根因**：`open(...,"a")` 只追加到文件末尾，不理解 Markdown 表格边界；表格连续性要求新行插在「最后一个表格数据行」之后，而非文件末尾。

### 修复（插入表格块末，保持连续）
```python
def _insert_into_table(content, row):
    lines = content.split("\n")
    sep = next((i for i, ln in enumerate(lines) if ln.lstrip().startswith("| :---")), None)
    if sep is None:  # 无表则裸追加
        return (content if content.endswith("\n") else content + "\n") + row
    j = sep + 1
    while j < len(lines) and lines[j].lstrip().startswith("|"):
        j += 1
    lines.insert(j, row.rstrip("\n"))
    return "\n".join(lines)
```

## 2. 单一写入器 (Single Source of Truth)

多脚本写同一类日志时 MUST 收敛为单一写入器模块（如 `scripts/vault_audit.py` 的 `append_audit_row()`），MUST NOT 各脚本自建重复 append 逻辑——否则修复一处、别处仍漂移。

## 3. Wikilink alias 管道陷阱 (MUST NOT `\|` in alias)

Obsidian wikilink alias 语法是 `alias`。markdown 表格内单元格间管道 MUST 用 `\|` 转义，但 **alias 文本内的 `|` MUST NOT 写成 `\|`**——反斜杠会被当作 target 一部分，导致 `2026-08` 被判 target `…2026-08\|2026-08` 不存在（断链 WARN）。

- 正确：`2026-08 记录`
- 错误：`2026-08`

## 4. 质量门禁排除 IDE 运行时目录

质量/门禁扫描（如 `vault-quality-check.py`）MUST 排除 IDE 运行时目录（`.codebuddy` 等），排除清单与 `.gitignore` 保持同步——否则把 IDE 内部 plans 当正式笔记校验，门禁恒 FAIL。对应 `.gitignore` 规则：`.codebuddy/`。

## 5. 库内 Python 工具模块命名 (MUST 下划线)

库内 Python 工具模块命名 MUST 用下划线（`vault_audit.py`），连字符仅供 CLI/目录层——`import vault-audit` 非法。

## 6. 防御性工程规范 (Defensive Rule)

1. 凡程序向含 prose 的 Markdown 表格文件追加行，MUST 插入「表格数据块末尾」，MUST NOT 裸 `open(a)` 落文件尾。
2. 多脚本写同一类日志 MUST 收敛为单一写入器（single source），避免重复 append 逻辑漂移。
3. wikilink alias 文本内 MUST NOT 写 `\|`；`\|` 只用于 markdown 表格列分隔。
4. 质量/门禁扫描 MUST 排除 IDE 运行时目录，排除清单与 `.gitignore` 同步。
5. 库内 Python 工具模块命名 MUST 用下划线（`vault_audit.py`），连字符仅供 CLI/目录层。

## 7. 关联

- 机器校验解析防御：[[01-Rules/MARKDOWN-REGISTRY-VALIDATION]]
- Wikilink 总规范：[[01-Rules/AGENT-CONDUCT]] §2
- 审计分片锚点：[[11-Agents/review-log]]
- 分片方案背景：MULTI-AGENT-LIMITATIONS-AND-RISKS §4.4
- 规则总索引：[[00-MOC/MOC-Rules]]
