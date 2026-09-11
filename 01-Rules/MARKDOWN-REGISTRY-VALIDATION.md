---
title: "Markdown 注册表/清单机器校验防御规范"
created: 2026-09-02
updated: 2026-09-02
type: rules
tags:
  - category/rules
  - topic/automation
  - topic/skills
  - lang/python
  - category/troubleshooting
status: stable
audience: both
source: "Skill Governance Hardening 2026-09-02 (vault-healthcheck Check 8)"
authority: synthetic
claim_risk: high
review_status: unreviewed
---

# Markdown 注册表/清单机器校验防御规范 (Markdown Registry Validation)

> 适用：任何被程序消费的 Markdown 表格/清单（技能注册表、工具索引、目录映射）MUST 配机器闸门。
> 本规范来自 `vault-healthcheck` Check 8（注册表⇄实体一致性）落地中的解析与校验踩坑。

## 1. 为什么要机器校验 (Symptom)

红线"靠人读"不可靠。注册表可写明令"只可引用存在文件"，但无机器闸门时，规则定稿与实体落盘之间的单向链路（[[01-Rules/SKILL-AUTHORING-SPEC]] §7）缺最后一步验证，漂移静默累积——healthcheck 旧 7 项全绿却漏出 `vault-tools` 实体漂移。

## 2. 解析器防御 (Parser Defensive Rules)

1. **标题深度与编号容错**：注册表 section 标题深度不齐（`##`/`###`）且编号后可能无空格（`3. L2` 的 `.` 非 `\s`）；正则 MUST 兼容 `^#{2,3}\s+([0-9]+(?:\.[0-9]+)?)` 而非写死 `^##`。
2. **空注册表边界用例自检 (MUST)**：写校验器后 MUST 先喂一条空注册表/单技能边界输入，确认能解析出非 0 结果——首版漏解析 0/0 即因缺该自检。
3. **表头驱动列定位 (MUST NOT 写死列号)**：`| # | 技能 | … |` 技能在第二列，`| 技能 | … |` 在第一列；MUST 找含 `技能` 的表头行取列下标。
4. **分隔行与一行多技能**：`|---|` 分隔行按序跳过；单元格内 `caveman` / `ponytail` 用反引号 kebab 正则全收。

## 3. 分层校验策略 (Layered Verification)

- **L2（项目内实体，如 `.claude/skills/<name>/SKILL.md`）硬校验**：注册表有、实体缺失 → FAIL。
- **L1（外部目录，如 `~/.cc-switch/skills/<name>/SKILL.md`）软校验**：目录本机不可达 → SKIP 带注记不阻塞（避免无该环境时全库标红、丧失告警可信度）；路径可用 `CC_SWITCH_HOME` 覆盖。
- **把"环境缺依赖"与"真实漂移"分开**：SKIP 是环境结论、FAIL 是实体结论，二者 MUST NOT 混报。

## 4. 通用防御铁律 (Defensive Rule)

1. 任何被程序消费的 Markdown 若需校验，解析器 MUST 对标题深度/编号后无空格容错 + 边界用例自检。
2. 技能/工具变更按单向链路执行后 MUST 由机器闸门兜底：新增 L2 实体后 healthcheck L2 计数应 +1 且全绿（计数器真解析到新行，非巧合）。
3. 向审计日志登记的行内 MUST NOT 写指向被排除目录的 wikilink（如 `copilot/` 不在 wikilink 索引），否则登记动作自身引入断链、反被自己的 wikilink 检查报红。
4. 治理复盘先问"这是缺技能还是缺检查项"——多数红线缺口是后者，补一个 healthcheck 检查比造新技能成本低且可机器回归。

## 5. 关联

- 校验器实现：`scripts/vault-healthcheck.py` 的 `check_skill_registry_sync()`（库内脚本不进检索，路径见 AGENTS.md §9）
- 单向链路定义：[[01-Rules/SKILL-AUTHORING-SPEC]] §7
- 审计日志纪律：[[01-Rules/AGENT-CONDUCT]] §5
- 分片方案背景：MULTI-AGENT-LIMITATIONS-AND-RISKS §4.4
- 规则总索引：[[00-MOC/MOC-Rules]]
