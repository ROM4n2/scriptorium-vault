---
title: "子 Agent 注册表与派发管理指南 (Subagent Registry & Dispatch Guide)"
created: 2026-09-02
updated: 2026-09-02
type: rules
tags:
  - category/tools
  - topic/claude-code
  - topic/multi-agent
  - topic/agent-architecture
status: stable
audience: agent
source: "Coding Vault 子代理-* 入档 Claude Code agents 实战验证（2026-08-31）"
authority: synthetic
claim_risk: medium
review_status: unreviewed
---

# 🧭 子 Agent 注册表与派发管理指南 (Subagent Registry & Dispatch)

> **适用平台**：Claude Code 等以 `.claude/agents/*.md` 为注册表的原生子 Agent 环境。
> 本指南面向「维护 agent 注册表」与「在 Skill/文档里派发子 Agent」两件事，收录经真实项目验证的生命周期陷阱、静默降级风险与部署校验 SOP。
> 角色定义文件本体见本目录 `子代理-*.md`；派发执行规范见 `vault-exec` 技能。

---

## 1. 生命周期：注册表是会话启动快照 (Startup Snapshot) (MUST)

- Agent 发现机制 = **进程启动时扫描一次** `.claude/agents/*.md`（项目级）+ `~/.claude/agents/*.md`（全局），构建静态 name→定义 表。
- **会话内新建的 agent 文件当场不生效 (MUST)**：用编辑器写入一个 frontmatter 完全合法的 agent 文件后立刻 `Agent(subagent_type="foo")` 必然失败（`Agent type 'foo' not found`）。同目录下会话启动前就存在的 agent 正常可用。
- **生命周期差异 (MUST 认知)**：Skill 是每次调用现读文件，**Agent 不是**。不得按 Skill 的直觉推断 Agent 的拾取时机。
- **验证 MUST 重启会话 (MUST)**：任何新增/改名 agent 后，部署验证的第一步是重启会话；未重启的"静态校验全绿"不构成完成证据。
- **危害**：「自验证幻觉」——文件写对了、静态校验全绿，就宣称已完成，实际该批 agent 一次都没跑过。

---

## 2. 悬空 subagent_type 会静默降级 (Silent Fallback Trap) (MUST)

- **降级发生在模型侧，不在工具侧 (MUST 认知)**：工具层对未知 agent type 是硬报错，但主 Agent 拿到报错后不会停——它会改用 `general-purpose` **自己现编一份 prompt 继续跑**，报告格式、章节、严重度分级看起来完全正常。
- **后果**：Skill 里精心写的审计清单一行都没进子 Agent，而人类看不出区别。
- **高发场景 (MUST 规避)**：Skill/文档用散文写 `dispatch 子代理-XXX`，而注册表中根本没有该 name。文档写得越正式越容易漏——读起来像已接好线。
- **根因**：`name:` 字段是唯一 dispatch key，且必须与文件名一致；散文提及的名字对注册表没有约束力——与「用了但没 import 的裸标识符」是同一类失败。
- **Skill 派单 MUST 用表格钉住真实 `subagent_type` 并显式禁止 fallback (MUST)**：

```markdown
| Seat | `subagent_type` | Covers |
|---|---|---|
| Database | `dba-optimizer` | Index coverage, EXPLAIN, locks |

这些是 `~/.claude/agents/` 里的真实 agent type。不要臆造 seat 名；
若某个 seat 不存在，直接报告缺失，禁止静默改用 general-purpose 代替。
```

> 最后一句把坑从「模型自作聪明补位」变成「显式报错」。

---

## 3. 部署校验 SOP (Deployment Verification) (MUST)

新 agent 部署或 Skill 引用新 type 时，按下述顺序验证，缺一不可：

1. **静态校验**：
   - `name:` 存在且 == 文件名去后缀；
   - `description:` 足够长可路由；
   - `tools:` 每一项都是真实工具名（builtin 或 `mcp__server__tool` 全名）。
   - **MUST NOT 抄别的 IDE 工具名**：Windsurf 的 `view_file/grep_search/find_by_name` 在 Claude Code 对应 `Read/Grep/Glob`；写错不报错，只会得到一个零工具 agent。
2. **重启会话**（见 §1）。
3. **真派一次最便宜的那个**，确认 `subagent_type` 能解析。**没跑过就不算完成。**

---

## 4. 选型判据：什么才够格做成 Subagent (Eligibility) (SHOULD)

不是所有「有用的角色」都该做成 subagent。够格需同时满足：

1. 中间产物大而主线程不需要（上下文隔离收益显著）；
2. 工具收窄真能防事（权限沙盒收益显著）；
3. 一次性、无需与用户对话；
4. `description` 能让主 Agent 自主判断何时派。

**被否定的典型 (SHOULD 落成 Skill 驾驶主循环，而非 agent)**：
- **需要多轮追问的角色**（如面试考官）——subagent 无法与用户对话，只能吐一题就死；
- **大范围改码且需要人在环确认的角色**（如重构师、排障师）——外派回来的是主 Agent 未参与推理的 diff，而排障恰恰是主线程最需要保留的上下文。

---

## 5. 关联索引

- 子 Agent 角色定义：子代理复核角色（自建） 等本目录全部 `子代理-*.md`
- 派发执行与断点状态机：[[01-Rules/AGENT-CONDUCT]] §10
- 工具链总索引：[[00-MOC/MOC-Tools]]
