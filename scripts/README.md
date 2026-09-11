# scripts/ - 知识库自动化工具集

本目录包含 `{{VAULT_ROOT}}` 知识库的全部自动化脚本。统一入口：`vault-tools.py`。

## 工具速查

| 脚本 | 用途 | 典型命令 |
|------|------|----------|
| `vault-healthcheck.py` | **一键综合健康巡检**（推荐首选，Check 1-10，含技能注册表同步） | `python scripts/vault-healthcheck.py` |
| `vault-quality-check.py` | Frontmatter + Wikilink + AST 双版本对齐 | `python scripts/vault-quality-check.py --strict` |
| `vault-inbox-triage.py` | 扫描 Inbox 超龄草稿（>7d 报警） | `python scripts/vault-inbox-triage.py` |
| `vault-inbox-consolidate.py` | **Inbox 智能流转晋级** | `python scripts/vault-inbox-consolidate.py --apply`（`--execute` 兼容别名） |
| `search-vault.py` | **BM25 语义检索**规范与踩坑 | `python scripts/search-vault.py "GBK乱码" --format compact` |
| `vault-dedup.py` | 检测高相似度重复笔记对（>70%） | `python scripts/vault-dedup.py` |
| `vault-auto-linker.py` | 自动补全概念 Wikilink | `python scripts/vault-auto-linker.py --dry-run` |
| `vault-graph-analyzer.py` | 知识图谱拓扑分析（Hub / 孤岛） | `python scripts/vault-graph-analyzer.py` |
| `vault-knowledge-graph.py` | 生成 Canvas 可视化图谱 | `python scripts/vault-knowledge-graph.py` |
| `vault-proactive-scan.py` | 扫描 {{CODE_ROOT}} 项目发现可沉淀知识 | `python scripts/vault-proactive-scan.py` |
| `bootstrap.ps1` | **新项目一键初始化**（Windows/pwsh） | `pwsh scripts/bootstrap.ps1` |
| `bootstrap.sh` | **新项目一键初始化**（Bash/WSL） | `bash scripts/bootstrap.sh` |
| `stop-hook-ingest.py` | Claude Code Stop Hook 摄取提示 | 由 .claude/settings.json 自动调用 |
| `vault-tools.py` | 统一入口，可运行任意子工具 | `python scripts/vault-tools.py --list` |

> 注：`vault-health-check.py`（Phase 6 旧版四支柱看板）已退役并于 2026-09-11 删除（git 历史可考古）；一键巡检统一使用 `vault-healthcheck.py`。

## 场景速查

```
开始新项目   → pwsh scripts/bootstrap.ps1
查规范/踩坑 → python scripts/search-vault.py "<关键词>"
沉淀新知识   → 写 99-Inbox/YYYY-MM-DD-topic.md → --apply
定期巡检     → python scripts/vault-healthcheck.py
Inbox 清理   → python scripts/vault-inbox-consolidate.py --apply
```

## 注意

- 所有脚本含 Windows GBK stdout 防护
- `--strict` 模式下 quality-check 返回 exit 1（供 Git hook 拦截）
- bootstrap 检测目标 .git 存在性，无仓库时跳过 hook 安装
- 技能实体与 `scripts/*` 变更后，运行 `python scripts/vault-healthcheck.py --log` 复检并登记审计日志（自动按月分片至 `11-Agents/logs/{YYYY-MM}.md`，统一经 `scripts/vault_audit.py`）
