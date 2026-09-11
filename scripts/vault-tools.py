#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vault Tools — 统一入口

管理和运行知识库的所有自动化工具。

用法:
  python scripts/vault-tools.py --list                # 列出所有工具
  python scripts/vault-tools.py <tool-name>          # 运行指定工具
  python scripts/vault-tools.py --all                # 依次运行所有工具
  python scripts/vault-tools.py <tool> --help        # 查看工具详细帮助
  python scripts/vault-tools.py --health             # 运行健康巡检（推荐）
"""

import subprocess
import sys
from pathlib import Path

# Windows GBK 兼容：强制 UTF-8 输出
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SCRIPTS_DIR = Path("{{VAULT_ROOT}}/scripts")

TOOLS = {
    "inbox": {
        "name": "vault-inbox-triage",
        "file": "vault-inbox-triage.py",
        "description": "扫描 99-Inbox/ 报告超龄草稿（>7 天）",
        "use_when": "想知道 Inbox 里有哪些待处理草稿、哪些超期"
    },
    "consolidate": {
        "name": "vault-inbox-consolidate",
        "file": "vault-inbox-consolidate.py",
        "description": "Inbox 智能流转与自动吸收引擎（提取规则并晋级至正式规范）",
        "use_when": "需要将 99-Inbox/ 草稿自动归档晋级到语言规范或通用规则"
    },
    "quality": {
        "name": "vault-quality-check",
        "file": "vault-quality-check.py",
        "description": "验证 frontmatter、wikilink、命名规范",
        "use_when": "想检查笔记是否符合 AGENTS.md 规范"
    },
    "dedup": {
        "name": "vault-dedup",
        "file": "vault-dedup.py",
        "description": "检测相似度 >0.7 的笔记对",
        "use_when": "怀疑有重复内容想合并"
    },
    "linker": {
        "name": "vault-auto-linker",
        "file": "vault-auto-linker.py",
        "description": "自动添加 wikilink（默认 --dry-run）",
        "use_when": "想批量补全概念之间的链接"
    },
    "scan": {
        "name": "vault-proactive-scan",
        "file": "vault-proactive-scan.py",
        "description": "扫描 {{CODE_ROOT}} 项目，生成候选知识",
        "use_when": "想从代码库里发现值得提取的知识"
    },
    "graph": {
        "name": "vault-graph-analyzer",
        "file": "vault-graph-analyzer.py",
        "description": "分析 wikilink 图谱，统计孤岛/过载/弱连接",
        "use_when": "想看知识图谱的健康度"
    },
    "visualize": {
        "name": "vault-knowledge-graph",
        "file": "vault-knowledge-graph.py",
        "description": "生成 Obsidian Canvas 知识图谱可视化",
        "use_when": "想直观看到整个知识库的网络结构"
    },
    "healthcheck": {
        "name": "vault-healthcheck",
        "file": "vault-healthcheck.py",
        "description": "综合健康巡检（frontmatter/wikilink/双版本/inbox/symlink/体积/技能注册表）",
        "use_when": "想一次看全库健康状况与技能注册表漂移"
    },
    "search": {
        "name": "search-vault",
        "file": "search-vault.py",
        "description": "本地 BM25 搜索引擎与规则快速检索器 (支持意图扩展与多格式输出)",
        "use_when": "需要快速按关键词/标签查找相关工程规范与踩坑笔记"
    },
}


def list_tools():
    """列出所有工具"""
    print("═" * 70)
    print(" 🛠️  Coding Vault — 自动化工具集")
    print("═" * 70)
    print()
    for key, tool in TOOLS.items():
        print(f"  📌 {key:12s}  {tool['name']}")
        print(f"     {tool['description']}")
        print(f"     何时用: {tool['use_when']}")
        print()


def run_tool(key, extra_args=None):
    """运行指定工具"""
    if key not in TOOLS:
        print(f"❌ 未知工具: {key}")
        print(f"   可用: {', '.join(TOOLS.keys())}")
        sys.exit(1)

    tool = TOOLS[key]
    script_path = SCRIPTS_DIR / tool["file"]
    cmd = ["python", str(script_path)]
    if extra_args:
        cmd.extend(extra_args)

    print(f"▶ 运行 {tool['name']}...")
    print("─" * 70)
    result = subprocess.run(cmd, encoding='utf-8')
    sys.exit(result.returncode)


def run_all():
    """依次运行所有工具"""
    print("═" * 70)
    print(" 🚀 依次运行所有工具")
    print("═" * 70)
    print()

    for key, tool in TOOLS.items():
        script_path = SCRIPTS_DIR / tool["file"]
        cmd = ["python", str(script_path)]
        print(f"\n▶ {key:12s} → {tool['name']}")
        print("─" * 70)
        result = subprocess.run(cmd, encoding='utf-8')
        if result.returncode != 0:
            print(f"⚠️  {tool['name']} 退出码 {result.returncode}")

    print("\n✅ 全部工具运行完毕")


def show_tool_help(key):
    """显示工具的详细帮助（读取脚本的 docstring）"""
    if key not in TOOLS:
        print(f"❌ 未知工具: {key}")
        sys.exit(1)

    tool = TOOLS[key]
    script_path = SCRIPTS_DIR / tool["file"]
    # 提取 docstring
    with open(script_path, encoding='utf-8') as f:
        content = f.read()

    # 找到三引号 docstring
    if '"""' in content:
        start = content.index('"""') + 3
        end = content.index('"""', start)
        docstring = content[start:end].strip()
        print(f"📖 {tool['name']} — 详细说明")
        print("═" * 70)
        print(docstring)
    else:
        print(f"⚠️ {tool['name']} 没有 docstring")


def main():
    if len(sys.argv) < 2:
        list_tools()
        print("═" * 70)
        print("💡 快速开始:")
        print("   python scripts/vault-tools.py --health     # 推荐：一键健康巡检")
        print("   python scripts/vault-tools.py --list       # 列出所有工具")
        print("   python scripts/vault-tools.py <tool>      # 运行指定工具")
        print("   python scripts/vault-tools.py --all        # 依次运行所有")
        return

    arg = sys.argv[1]

    if arg == "--list" or arg == "-l":
        list_tools()
    elif arg == "--all" or arg == "-a":
        run_all()
    elif arg == "--health" or arg == "-h":
        run_tool("healthcheck")
    elif arg in TOOLS:
        extra = sys.argv[2:] if len(sys.argv) > 2 else None
        if extra and ("--help" in extra or "-h" in extra):
            show_tool_help(arg)
        else:
            run_tool(arg, extra)
    else:
        print(f"❌ 未知命令: {arg}")
        print("   可用: --list, --all, --health, 或工具名 (inbox/quality/dedup/...)")
        sys.exit(1)


if __name__ == "__main__":
    main()
