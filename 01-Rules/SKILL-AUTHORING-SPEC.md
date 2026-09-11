---
title: "Agent 技能工程与编写规范 (Skill Authoring Standards)"
created: 2026-08-29
updated: 2026-09-02
type: standards
tags:
  - category/rules
  - category/tools
  - topic/skills
  - topic/agent-architecture
status: stable
audience: both
source: "writing-great-skills / writing-skills 元规范"
authority: synthetic
claim_risk: high
review_status: unreviewed
---

# 🛠️ Agent 技能工程与编写规范 (Skill Authoring Standards)

> **核心定义 (The First Principle)**：
> **Skill 绝不是给人类阅读的使用说明书，而是从大模型随机采样（Stochastic Token Sampling）中榨取确定性（Process Predictability）的约束函数。**
> 一个技能存在的唯一合法理由，是迫使 Agent 在面对特定任务时，采取**经过实证检验的唯一正确执行过程**，并彻底堵死模型偷懒、幻觉与过早交差的逃逸漏洞。

---

## 1. 技能设计的 TDD 铁律 (Test-Driven Skill Authoring) (MUST)

编写 Skill 的过程，本质上是 **TDD（测试驱动开发）在过程文档上的完整映射 (RFC 2119 MUST)**：

```
┌────────────────────────────────────────────────────────────────────────────┐
│                    Skill 编写的 TDD 闭环 (Red-Green-Refactor)              │
├───────────────────┬────────────────────────────────────────────────────────┤
│ 🔴 RED (测试失败)  │ 构造高压测试场景，观察 Agent 在没有 Skill 时的失败与借口 │
│ 🟢 GREEN (通过)   │ 编写精准堵死该逃逸漏洞的最小 Skill，验证 Agent 严格合规   │
│ 🔵 REFACTOR (重构) │ 消除 No-Op 废话、概念锚定化 (Leading Words)、精简描述   │
└───────────────────┴────────────────────────────────────────────────────────┘
```

1. **先见红后写文档 (MUST)**：若未曾亲眼观测到 Agent 在缺少该 Skill 时的具体违规表现与狡辩借口（Rationalizations），**严禁凭空脑补编写 Skill**。
2. **针对性封堵 (MUST)**：Skill 的正文必须精准狙击基线测试中暴露出的具体违规行为。
3. **闭环重构 (SHOULD)**：在确保 Agent 100% 遵守的前提下，持续削减 Token，提炼 Leading Words。

---

## 2. 触发机制与描述工程 (Invocation & Description Engineering) (MUST)

Skill 的 `description` 是常驻在注意力窗口中的高成本资产，**MUST** 遵循严格的上下文经济学：

### 2.1 模型唤起 vs 用户手动唤起
- **Model-Invoked (默认)**：由模型自主唤起或其他 Skill 调度。`description` **MUST** 极度精炼，专门列出独立触发场景（Trigger Branches）；
- **User-Invoked (`disable-model-invocation: true`)**：仅限人类手动输入指令触发。此时 `description` **MUST NOT** 堆砌长篇触发词，仅留一行简述，实现 **Zero Context Load**。

### 2.2 Description 编写三铁律 (MUST)
1. **前置动作词 (Front-load Leading Words)**：开头第一句明确核心动作与目的；
2. **一分支一触发 (One Trigger per Branch)**：**MUST NOT** 堆砌同义词（如“构建功能使用 TDD...要求测试先行开发”属于同一分支写了两次，必须合并）；
3. **剥离正文定义 (Cut Body Duplication)**：Description 仅声明“何时触发”，正文内容严禁在 Description 中复述。

---

## 3. 信息层级与渐进式披露 (Information Hierarchy & Progressive Disclosure) (MUST)

Skill 内容由两部分构成：**有序步骤（Steps）** 与 **平级参考（Reference）**。

```markdown
                                【信息层级天梯】
                                      │
  1. 顶级动作步骤 (In-skill Steps) ────┴──> 核心执行流 + 二元化完成判据 (Checkable Criteria)
  2. 顶级平级参考 (In-skill Reference) ───> 扁平规则、Bad vs Good 代码对比
  3. 二级上下文指针 (External Context) ───> 复杂 API 字典、长模版推入外部文件 (Progressive Disclosure)
```

1. **检查性完成判据 (Checkable Completion Criteria) (MUST)**：
   - 每一个 Step 的结束点 **MUST** 具备二元可观测状态（如“单测运行器输出 0 failures”，而非“确保测试写得很好”）；
   - 模糊的完成判据是引发 **Premature Completion（过早完成/偷懒交差）** 的头号元凶。
2. **渐进式披露 (Progressive Disclosure) (SHOULD)**：
   - 超过 50 行的代码模板、长篇 API 字典或特定分支专属协议，**SHOULD** 独立存入 `references/` 或知识库专用路径，通过上下文指针按需读取，保持顶层 `SKILL.md` 紧凑轻量。

---

## 4. 概念锚定词机制 (Leading Words Protocol) (MUST)

大模型在海量预训练中已经内化了大量高阶工程先验。Skill **MUST** 优先采用 **Leading Words（概念锚定词）** 唤醒高维先验，而非冗长解释：

| 冗长啰嗦表达 (Anti-Pattern) | 概念锚定词 (Leading Word) | 调动的模型先验与行为约束 |
|---|---|---|
| “每次必须先写一个会报错的测试用例，确认它确实是因为缺少功能而失败...” | **`The Iron Law of TDD`** | 严禁生产代码先行，违者立刻全删 |
| “把所有可能的设计分支和依赖关系梳理出来，只问前置条件明确的问题...” | **`Frontier Tree Protocol`** | 依赖拓扑排序，按轮次推进前沿问题 |
| “优先用标准库，没有标准库再看既有依赖，不要自己写复杂的类...” | **`The Ladder of Reuse`** | 反过度抽象天梯，第一顺位选用标准库 |
| “一个人负责编写代码，另一个人负责严格对照规范核验...” | **`Maker-Checker Cycle`** | 执行者与审阅者分离的双人复核制 |
| “故意修改代码把逻辑搞错，看看测试会不会变红...” | **`Fake Green Mutation`** | 变异测试检验测试用例的真实有效性 |
| “嵌套不要超过两层，条件不满足立刻退出，主逻辑全部靠左对齐...” | **`Guard Clauses (卫语句)`** | 圈复杂度控制，主干业务流左对齐 |

---

## 5. 六大底层失效模式与终极防线 (Failure Modes & Defenses) (MUST)

编写与审阅任何 Skill 时，**MUST 逐条核验是否触发以下 6 大失效模式**：

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        Skill 编写的六大底层失效模式与防线                              │
├───────────────────────┬────────────────────────────────────────────────────────────────┤
│ 1. Premature Completion│ 偷懒过早交差 ➔ 设立严格的物理机执行证据（Evidence-First）门禁   │
│ 2. Duplication        │ 重复罗嗦 ➔ 确立单一真值源（Single Source of Truth），一处修改 │
│ 3. Sediment (陈旧沉积) │ 只增不减 ➔ 定期执行 No-Op 扫描，果断删除失效规则               │
│ 4. Sprawl (膨胀失控)   │ 文件过长 ➔ 启用渐进式披露（Progressive Disclosure）推入二级文件│
│ 5. No-Op (无用废话)   │ “请仔细思考”等废话 ➔ 删除！仅保留能显著改变模型行为的指令       │
│ 6. Negation Backfire  │ “不要想大象”反向激发 ➔ 严禁纯否定句，必须给出正向对标行为      │
└───────────────────────┴────────────────────────────────────────────────────────────────┘
```

1. **Premature Completion（过早完成）**：Agent 急于结束当前步骤。**防线**：设立不可绕过的检查证据链（如必须输出测试运行日志）。
2. **Duplication（重复定义）**：同一个含义在多处阐述。**防线**：单一真值源，修改只需改一处。
3. **Sediment（陈旧沉积）**：随时间推移只加不删。**防线**：坚决剔除已过时的历史补丁。
4. **Sprawl（膨胀失控）**：`SKILL.md` 动辄上千行。**防线**：拆分至 `references/`，按分支按需加载。
5. **No-Op（无操作废话）**：模型默认就会做的事情（如“请遵循良好的编码风格”）。**防线**：句子级 No-Op 审计，通不过则整句删除。
6. **Negation Backfire（否定句反噬）**：使用“严禁做 X”却不给替代方案，反而提高了 X 在注意力中的概率。**防线**：**正向肯定句驱动**（“做 Y 并保持左对齐”，而非单纯“不要写嵌套”）。

---

## 6. 技能质量自检与准入清单 (Quality Checklist) (MUST)

在将任何新 Skill 部署到 `~/.cc-switch/skills/` 前，**MUST** 通过以下 7 项自检：

- [ ] **Frontmatter 格式**：`name` 符合 kebab-case，`description` 严格限制在触发场景且前置动作词。
- [ ] **TDD 验证证据**：明确记录了该 Skill 封堵的 Baseline 违规场景。
- [ ] **无 No-Op 废话**：逐句通读，剔除所有“尽量”、“认真”、“仔细”等无约束力的修饰词。
- [ ] **概念锚定词到位**：核心逻辑已提炼为 Leading Words，无长篇累赘解释。
- [ ] **完成判据绝对客观**：每个阶段都有明确的、机器可验证的验收标准。
- [ ] **渐进式披露合规**：长篇代码模板与外部 API 已推入专用模板库或二级文件。
- [ ] **生态链闭环对齐**：明确指向上游输入（由谁唤起）与下游交接（移交给谁）。

---

## 7. 规则 → 技能单向变更链路 (Rule-to-Skill Change Pipeline) (MUST)

知识库采用三层技能架构（全局技能 / 项目技能 / 知识契约层，索引见 [[05-Tools/SKILL-REGISTRY]]）。规则文件是技能行为唯一出处，技能只是规则的运行时化包装。任何技能新增与更新 MUST 按单向链路执行：

```
┌──────────────┐    ①      ┌────────────────┐    ②     ┌────────────────────┐
│ L3 规则定稿   │ ────────► │ review-log 登记  │ ───────► │ SKILL.md 物理落盘   │
│ 01-Rules/…   │  先改规则  │ 11-Agents/…     │  登记     │ cc-switch 或库内    │
└──────────────┘           └────────────────┘           └─────────┬──────────┘
                                                                   │ ③
                                                          ┌────────▼─────────┐
                                                          │ 用户 UI 同步分发   │
                                                          │ (禁止 Agent 代劳)  │
                                                          └──────────────────┘
```

1. **先改规则后改技能 (MUST)**：行为变更先在 `01-Rules/*.md` 或 `AGENTS.md` 定稿；技能正文只做执行层封装，MUST NOT 在技能里发明库内不存在的约束。
2. **review-log 登记 (MUST)**：每次技能新增/更新 MUST 在 `11-Agents/review-log.md` 登记（变更内容、对应规则出处、日期）。
3. **物理落盘 (MUST)**：全局技能写入 `~/.cc-switch/skills/<name>/SKILL.md`（管理规范见 环境配置指南）；库内项目技能写入 `.claude/skills/<name>/`。
4. **用户 UI 同步 (MUST NOT 代劳)**：全局技能分发由用户在 CC Switch 客户端勾选同步；Agent MUST NOT 跨端建链或直接写 `cc-switch.db`（[[01-Rules/AGENT-CONDUCT]] §10 三条铁律）。
5. **注册表同步 (MUST)**：新增/停用技能 MUST 同步更新 [[05-Tools/SKILL-REGISTRY]] 对应表。

---

## 8. 关联索引

- 通用编码规范：〔你的领域通用规范〕
- Agent 行为守则：[[01-Rules/AGENT-CONDUCT]]
- 技能注册表与三层模型：[[05-Tools/SKILL-REGISTRY]]
- 跨项目测试防死测模式：[[01-Rules/TESTING-PATTERNS]]
- 工具链与技能导航：[[00-MOC/MOC-Tools]]
- 知识库主索引：[[00-MOC/Home]]
