---
title: "Scriptorium Vault — 领域无关的 LLM 原生知识库模板"
created: 2026-09-11
updated: 2026-09-11
type: notes
tags:
  - category/meta
  - topic/automation
status: stable
audience: both
authority: primary
claim_risk: low
review_status: reviewed
---

# Scriptorium Vault — 领域无关的 LLM 原生知识库模板

> **你拿到的是一个"空壳 + 全自动管线"**：目录骨架是留给你按自己的领域填充的，
> 而 git 三道门、事务化笔记流、可信度账本、夜间仪表盘、跨 Agent 共享记忆协议、
> BM25 检索 MCP、技能包——这些基础设施开箱即用。Bring your own domain.

- 无需理解源码即可使用；所有自动化脚本都在 `scripts/`，全部有测试（`scripts/tests/`）。
- 本模板从作者的真实知识库中**去标识化导出**：不含任何私有内容、绝对路径或个人身份信息。
- License：代码与配置 MIT（`LICENSE`），文档与示例 CC BY-SA 4.0（`LICENSE-CONTENT`）。

---

## 0. 先读懂一个记号：`〔…〕`

模板里凡是写成 `〔你的领域通用规范〕`、`〔子代理派发指南〕` 的地方，含义是：

> **该文件已被剔除（它曾是作者领域的私有内容），请你按自己的领域自建。**

它不是断链，也不是丢了文件。规则文件（`AGENTS.md` 等）中出现 `〔…〕` 的 MUST
条目，语义都是"若尚未创建，先自建再使用"。与之并列的机器占位符：

| 记号 | 含义 |
|---|---|
| `〔…〕` | 被剔除的文件——**需要你自建**（wikilink 中出现时，质量门禁自动豁免） |
| `{{VAULT_ROOT}}` / `{{USER_HOME}}` / `{{CODE_ROOT}}` / `{{PROJECT_PATH}}` | 安装期替换的环境路径 |
| `{{lang}}` / `{{LANG}}` / `{{TITLE}}` 等 | 模板填写占位符（见各 `Templates/tpl-*.md` 头部说明） |

## 1. Clone 后必做（按序，全部可复制）

```bash
git clone https://github.com/{{AUTHOR}}/scriptorium-vault.git <VAULT>
cd <VAULT>

# ① 依赖（frontmatter 解析 + 测试套件）
pip install -r requirements.txt

# ② 激活 pre-commit 三道门（core.hooksPath 属本地配置，不随 clone）
git config core.hooksPath .githooks

# ③ 验证（三条都应 exit 0）
python -m pytest scripts/tests/ -q
python scripts/vault-quality-check.py --strict
python scripts/search-vault.py "费曼" --format compact   # 检索 examples/ 示例，应命中
python scripts/vault-healthcheck.py                      # Check 1-10 全绿
```

> ③ 的检索演示查询的是 `examples/` 里的真实内容——那是官方示范笔记
> （阅读工作流 ADR / RCA / 速查表），也是"一篇合规笔记长什么样"的标准答案。

## 2. 技能与 MCP

**技能**（`skills/`，共 11 个 `/vault-*`）：复制进你的 Agent 技能目录即可——
有 [CC Switch](https://github.com/farion1231/cc-switch) 的装到 `~/.cc-switch/skills/`；
没有就按 `skills/README.md` 的手动路径逐目录复制，或对无技能目录的 harness 在全局规则
里加一行指针。**注意：`skills/vault` 路由器会推荐全部技能，其中 8 个深度工程技能
（onboard/exec/team/tdd/perf/review/refactor/interview）未随包分发**——路由器会自动
跳过未安装项并改荐 `/vault-plan`，介意可自行删改路由表。

**MCP**（模型上下文协议服务器，让 Agent 会话直接获得库能力）：

```bash
# Claude Code（--scope user 使其在本机所有项目生效）
claude mcp add coding-vault-search --scope user -- python <VAULT>/scripts/vault_search_mcp.py

# Cursor / 其他支持 stdio MCP 的客户端：等价 JSON（放进各自的 mcp 配置）
{
  "mcpServers": {
    "coding-vault-search": {
      "command": "python",
      "args": ["<VAULT>/scripts/vault_search_mcp.py"]
    }
  }
}
```

其余三个服务（`system_monitor_mcp.py` / `arxiv_paper_mcp.py` / `sqlite_inspector_mcp.py`）
注册方式相同，验证命令见 `05-Tools/capabilities.json` 与 `05-Tools/CAPABILITY-MATRIX.md`；
连通性探测：`python scripts/mcp_probe.py --help`。

## 3. 目录结构（实际状态）

```
<VAULT>/
├── AGENTS.md                  # 唯一真值源：协作宪法（下面 5 个入口是它的内容副本）
├── CLAUDE.md / GEMINI.md / .cursorrules / .windsurfrules / CONVENTIONS.md
├── 00-MOC/                    # 导航中枢（Home.md 工作台 + 分区 MOC）
├── 01-Rules/                  # 26 条治理规则（含〔你的领域通用规范〕占位——自建处）
├── 02-Fundamentals/ 04-Systems/ 07-Academics/   # 学科壳区：README 引导 + 科目子目录（待自建）
├── 03-Languages/              # 语言双版本规范壳区（STANDARDS ⟷ CHEATSHEET 1:1 对齐契约）
├── 05-Tools/                  # 工具文档、能力矩阵、Subagents 派发指南
├── 06-Sources/                # 外部信息源（书籍/文章/论文壳区）
├── 08-Projects/               # 项目档案（_template/ 四件套 + 01-ADR MADR 编号约定）
├── 09-Career/ 10-Daily/       # 壳区
├── 11-Agents/                 # Agent 基础设施：审计月志、corrections 账本
├── 99-Inbox/                  # 草稿收件箱（inbox-consolidate / TTL 流转）
├── Templates/                 # 11 个笔记模板（含 WORKMEMORY 4 件套下发模板）
├── examples/                  # ★ 官方示范笔记（开始写之前先读这里）
├── dashboards/                # 夜间自动再生成的仪表盘（首次为空属正常）
├── scripts/                   # 全部自动化 + 测试
├── skills/                    # 11 个 /vault-* 技能（见 skills/README.md）
├── hooks/  .githooks/         # 三道门 manifest 分发源 + 薄路由
└── .obsidian/snippets/        # 工作台样式（vault-workbench.css，已随库分发）
```

`02/03/04/06/07/09/10` 的分区 README 都写明了"**空是正常的**"与三步下一步；
`01-Rules/VAULT-STRUCTURE.md` 是完整的结构契约（含壳目录策略）。

## 4. 多 Agent 入口：内容副本，不是符号链接

`CLAUDE.md` / `GEMINI.md` / `.cursorrules` / `.windsurfrules` / `CONVENTIONS.md`
与 `AGENTS.md` **字节一致**（内容副本，随包分发，Windows 开箱即用）。
修改规则时**只改 `AGENTS.md`**，然后运行 `.claude/hooks/post-write-sync-agents.sh`
（或让 hook 自动同步）使五份副本保持一致；`vault-healthcheck.py` 的 Check 5 会校验。

## 5. 日常自动化（可选但推荐）

- **夜间管线**：`python scripts/nightly-maintenance.py --apply`（或 Windows 计划任务：
  `powershell -File scripts/setup-nightly-task.ps1`）——仪表盘再生成、会话洞察、
  图谱 diff、可信度账本、记忆压缩、健康检查、自动提交推送。
- **提交三道门**：Gate 1 密钥扫描 → Gate 1.5 凭证型 URL → Gate 2 `--strict` 质量门
  （frontmatter 六字段、wikilink 完整性、双版本规范 AST 对齐、配置契约）。
- **笔记流事务化**：`vault_transaction.py`（备份 + 原子替换）；审计留痕
  `11-Agents/logs/YYYY-MM.md`。

## 6. 排障

| 症状 | 处置 |
|---|---|
| 提交被 Gate 2 拒绝 | 报告会指出文件与行；通常是 frontmatter 缺字段或新增断链 |
| `search-vault.py` 返回空 | 正常（空库）；往 `examples/` 或你的分区写一篇再试 |
| healthcheck `HEALTHCHECK FAILED` | 按报告定位；Check 8b SKIP 属正常（未设 `CODE_ROOT`） |
| MCP 未出现 | 确认 `<VAULT>` 为绝对路径、`python` 在 PATH；用 `mcp_probe.py` 探测 |
| 想重建自己的领域骨架 | 从 `examples/` 复制结构范式，把 `〔…〕` 逐个自建 |

## 7. 首个会话建议

对你说一句：**"读 AGENTS.md 与 TUTORIAL.md，然后带我走完第一节。"**
—— Agent 会按宪法加载规则（不存在的 `〔…〕` 会提示你先自建），剩下的交给管线。
