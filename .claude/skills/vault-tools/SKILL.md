---
name: vault-tools
description: Coding Vault 库内自动化工具导航。当用户在本库（{{VAULT_ROOT}}）内询问如何运行/使用库内 CLI 脚本（scripts/*.py）或 vault_search_mcp MCP 工具时触发。
---

# Coding Vault Master Toolchain Reference

## 1. 适用范围与职责分界 (MUST)

本技能仅导航**本库内** `scripts/*` 自动化 CLI 与 `vault_search_mcp` MCP 工具用法。

**全局工作流技能（`vault` 路由 + 18 个 `vault-*` 生命周期技能）不在此导航**——它们归属 L1 全局层，由 CC Switch 分发，索引见 `~/.cc-switch/skills/` 与 [[05-Tools/SKILL-REGISTRY]] §2.1；本技能不复制、不罗列任何全局技能实体（防双源漂移，见 [[05-Tools/SKILL-REGISTRY]] §4 职责分界）。

## 2. 库内 CLI 统一入口 (scripts/vault-tools.py)

所有库内工具统一经 `python scripts/vault-tools.py` 调度：

```bash
python scripts/vault-tools.py --list                 # 列出全部工具与用途
python scripts/vault-tools.py --health               # 一键综合健康巡检（现役 vault-healthcheck.py）
python scripts/vault-tools.py <tool> [--help]        # 运行/查看指定工具（inbox/consolidate/quality/dedup/...）
python scripts/vault-tools.py --all                  # 依次运行全部工具
```

高频工具速查（完整清单与典型命令见 [[scripts/README]]）：

| 场景 | 命令 |
|---|---|
| 一键综合健康巡检 | `python scripts/vault-tools.py --health`（7 项内容检查 + 技能注册表同步校验） |
| Frontmatter/Wikilink 严格校验 | `python scripts/vault-tools.py quality -- --strict` |
| Inbox 草稿分诊 / 智能晋级 | `python scripts/vault-tools.py inbox` / `consolidate -- --apply` |
| 精准检索规范与踩坑 | `python scripts/search-vault.py "<关键词>" --format compact` |
| 重复检测 / 图谱分析 / Canvas 图谱 | `dedup` / `graph` / `visualize` |
| 项目主动知识发现 | `python scripts/vault-proactive-scan.py` |

## 3. MCP 2.2 协议原子工具 (scripts/vault_search_mcp.py，共 9 个)

- `search_vault(query, tag, top, format)`: BM25 + 意图扩展 + 1-Hop 图谱顺藤摸瓜
- `get_note(rel_path)`: 读取知识库 Markdown 笔记
- `get_code_template(template_name, lang)`: 提取纯净生产级代码模板
- `list_standards()`: 语言规范与通用规则总览
- `save_inbox_draft(title, content, tags, source)`: A-MAC 准入草稿沉淀至 `99-Inbox/`
- `promote_inbox_draft(draft_filename, target_dir)`: 会话内一键晋级草稿
- `omni_search(query)`: 跨笔记/规则/代码模板聚合检索
- `get_rule_snippet(rule_path, section)`: 提取规则文件指定章节片段
- `vault_proactive_scan()`: 全库主动扫描（断链/漂移/过期前置巡检）

## 4. 维护纪律

- 库内健康巡检与修复闭环：运行 `.claude/skills/vault-maintain/SKILL.md` 引导技能，不要手动零散跑脚本。
- 工具清单变更（新增/退役脚本）时：同步更新 `scripts/vault-tools.py` TOOLS 表、`scripts/README.md`、根 `README.md` 工具矩阵，并在 [[11-Agents/review-log]] 登记。
