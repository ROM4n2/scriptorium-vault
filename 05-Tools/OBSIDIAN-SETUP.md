---
title: "Obsidian 端激活与插件配置指南"
created: 2026-09-09
updated: 2026-09-09
type: notes
tags:
  - lang/tools
  - category/notes
  - topic/obsidian
status: stable
audience: both
authority: synthetic
claim_risk: low
review_status: unreviewed
---

# Obsidian 端激活与插件配置指南

> 本库的首页动态仪表盘、模板注入与界面样式均运行在 **Obsidian** 之上。仅用文本编辑器或 IDE 打开只能"只读"静态 Markdown，Clone 后请先完成本文的 4 件事（对应 README「第 0 步：Obsidian 端激活」）。

## 四件事（Step 0-1 至 0-4）

### 1️⃣ 以 Vault 打开本目录

- Obsidian → 右下角库切换器 → **`Open folder as vault`**（管理库 → 打开本地文件夹作为库）；
- 选择本仓库**根目录**（含 `00-MOC/` 到 `99-Inbox/` 的那一层），不要选子目录。

### 2️⃣ 安装 Dataview 并开启 JavaScript Queries

`00-MOC/Home.md` 与多页仪表盘的动态区块由 `dataviewjs` 驱动，Obsidian 默认**禁用** JS 查询，必须手动开启：

1. 设置 → 第三方插件 → 关闭安全模式（若提示）→ **浏览** → 搜索 `Dataview` → 安装并**启用**；
2. 设置 → **Dataview** → 打开 **JavaScript Queries**（`Enable JavaScript Queries`）；
3. 回到 `Home.md`，动态区块应渲染为表格/列表而非灰色代码块。

### 3️⃣ 启用 CSS 代码片段 vault-workbench

片段文件已随库分发于 `.obsidian/snippets/vault-workbench.css`（这是 `.obsidian/` 中**唯一**随 git 分发的文件），无需手动创建：

1. 设置 → 外观 → 滚动到 **CSS 代码片段**；
2. 点击**刷新**图标 🔄 → `vault-workbench` 出现 → 打开其开关。

### 4️⃣ 指认模板与每日笔记目录

| 设置项 | 路径 | 填写值 |
| --- | --- | --- |
| 模板目录 | 设置 → 核心插件 → 模板 (Templates) → 模板文件夹位置 | `Templates` |
| 每日笔记目录 | 设置 → 核心插件 → 每日笔记 (Daily notes) → 新建笔记的存放位置 | `10-Daily` |
| 每日笔记模板 | 同上 → 模板文件的位置 | `Templates/tpl-daily` |
| 日期格式 | 同上 | `YYYY-MM-DD` |

> 提示：每日笔记目录 MUST 为 `10-Daily/`（顶层目录编号以此为准）；若历史配置残留 `07-Daily` 等旧值，请手动改正。

## 插件清单（11 个社区插件）

本表与作者本地 `community-plugins.json` 对齐；该文件**不入库**，新机器请按本表重装。**仅 Dataview 为必需**，其余均为可选增强，按需安装：

| # | 插件 | 必须性 | 用途 |
| --- | --- | --- | --- |
| 1 | **Dataview** | ⭐ 必须 | `Home.md` 与仪表盘的 dataview/dataviewjs 动态查询 |
| 2 | Homepage | 可选 | 启动时自动打开 `00-MOC/Home.md` |
| 3 | Templater | 可选 | 模板动态占位增强（核心"模板"插件够用可不装） |
| 4 | Obsidian Git | 可选 | 库内定时 commit/push（桌面端也可用 nightly 流水线替代） |
| 5 | Linter | 可选 | 保存时自动整理 Markdown 格式 |
| 6 | Style Settings | 可选 | 微调 `vault-workbench` 片段的 CSS 变量 |
| 7 | Smart Connections | 可选 | AI 相似笔记关联推荐 |
| 8 | Tag Wrangler | 可选 | 标签面板重命名与合并 |
| 9 | Claudian (realclaudian) | 可选 | 在库内嵌入 Claude Code 等 coding Agent 协作 |
| 10 | Code Styler | 可选 | 代码块语法高亮与美化 |
| 11 | Omnisearch | 可选 | 全库搜索增强（脚本侧另有 BM25 `search-vault.py`） |

## 插件目录为何不入库

`.obsidian/plugins/`（插件二进制与各插件配置）以及绝大多数 `.obsidian/*.json`（`workspace.json`、`daily-notes.json` 等）**有意不纳入版本控制**——随库分发的仅 `.obsidian/snippets/vault-workbench.css`。这是设计决定而非缺陷：

- 保持模板仓库纯净，避免平台相关配置与第三方插件代码污染；
- 因此**每台新机器**都需要：在社区插件市场重装插件（约 2 分钟）+ 重做本文四件事。

## 常见问题

| 症状 | 原因与处理 |
| --- | --- |
| `Home.md` 动态块显示灰色 `dataviewjs` 代码 | 未开 **JavaScript Queries**（见 2️⃣ 第 2 步）或 Dataview 未启用 |
| CSS 代码片段列表为空 | 未点刷新图标；或未以**仓库根目录**为 vault 打开 |
| 每日笔记落到错误目录 | 检查第 4️⃣ 步，目录 MUST 为 `10-Daily` |
| 新机器插件全部消失 | 正常——插件目录有意不入库，按插件清单重装即可 |
