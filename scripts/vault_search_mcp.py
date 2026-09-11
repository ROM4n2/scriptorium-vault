#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coding Vault Search & Operations MCP Server (Model Context Protocol v2.3.0)
===========================================================================
Pure Python stdio JSON-RPC MCP Server.
Provides knowledge retrieval, standards lookup, pure code template extraction,
omni-search escalation gateway (The Ladder), automated draft harvesting (A-MAC),
and in-session draft promotion from {{VAULT_ROOT}} to any AI Agent
(Claude Code, OpenCode, Hermes, Codex, Antigravity, etc.).

Tools:
  - omni_search: The Retrieval Escalation Gateway (L1 Vault -> L0 CodeGraph -> L2 context7 -> L3 Web)
  - search_vault: Hybrid BM25 keyword + semantic intent + 1-Hop Graph-Aware retriever (Priority 1)
  - get_note: Direct note/standard reader
  - list_standards: Dual-version standards & rules catalog
  - get_code_template: Pure production code template extractor (Go, Python, SQL, Docker, etc.)
  - save_inbox_draft: A-MAC protected knowledge harvester into 99-Inbox/
  - promote_inbox_draft: In-session draft consolidator to formal standards
"""

import sys
import os
import json
import pathlib
import subprocess
import traceback
import re
import shutil
from datetime import date
from typing import Any, Dict, List, Optional

# Windows UTF-8 stdout/stdin protection
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stdin, "reconfigure"):
    sys.stdin.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

VAULT_ROOT = pathlib.Path(__file__).resolve().parent.parent
SEARCH_SCRIPT = VAULT_ROOT / "scripts" / "search-vault.py"


def tool_search_vault(query: str, tag: Optional[str] = None, top: int = 5, output_format: str = "detailed") -> str:
    """Execute search-vault.py with 1-Hop graph support."""
    if not query.strip():
        return "❌ 搜索关键词不能为空。"

    cmd = [
        sys.executable,
        str(SEARCH_SCRIPT),
        query,
        "--top", str(top),
        "--vault-path", str(VAULT_ROOT),
        "--format", output_format
    ]
    if tag:
        cmd.extend(["--tag", tag])

    try:
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15
        )
        output = res.stdout.strip()
        if not output and res.stderr:
            output = f"⚠️ Search warning/stderr: {res.stderr.strip()}"
        return output or "未找到匹配的规范或笔记。"
    except Exception as e:
        return f"❌ 检索失败: {e}"


def tool_omni_search(query: str, scope: str = "ladder", top: int = 5) -> str:
    """
    Execute the Retrieval Escalation Protocol:
    1. L1: Vault BM25 & Intent Match (Short-circuit if confident hit, <10ms)
    2. L0: Local CodeGraph / Codebase Search (Reuse existing wheels)
    3. L2/L3: Upstream Docs / Web Search recommendation
    """
    q = query.strip()
    if not q:
        return "❌ 搜索关键词不能为空。"

    mode = scope.lower().strip()

    if mode == "vault":
        return "# 🏛️ [L1_VAULT] 知识库专用检索\n\n" + tool_search_vault(q, top=top)

    # 1. 阶梯 1：优先检索本地知识库 (L1 Vault)
    vault_res = tool_search_vault(q, top=top, output_format="detailed")
    has_results = ("pts]" in vault_res or " [1] " in vault_res) and "No relevant notes found" not in vault_res and "未找到匹配" not in vault_res
    if has_results:
        return f"# 🚀 [L1_VAULT_HIT: 本地知识库秒级命中 (0ms 网络消耗)]\n\n{vault_res}\n\n💡 命中提示：知识库已收录该工程规范/踩坑解法，请优先遵循上述规范，无需发起外部网络搜索。"

    if mode == "code" or mode == "ladder":
        # 2. 阶梯 2：检索本地已有代码库 (L0 CodeGraph / {{CODE_ROOT}})
        if shutil.which("codegraph"):
            try:
                cg_res = subprocess.run(
                    ["codegraph", "search", q, "--limit", str(top)],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=5
                )
                cg_out = cg_res.stdout.strip()
                if cg_out and "0 results" not in cg_out and "No results" not in cg_out:
                    return f"# 📦 [L0_CODE_REUSE: 发现本地工程已有现成代码/函数]\n\n{cg_out}\n\n💡 复用提示：本地代码库已包含相关实现，请直接复用已有轮子，严禁重复手写！"
            except Exception:
                pass

    if mode == "doc":
        return f"# 📖 [L2_DOCS: 第三方库文档推荐]\n\n请调用 `context7` MCP 查询 '{q}' 的官方库文档与函数签名。"

    if mode == "web":
        return f"# 🌐 [L3_WEB: 全网搜索]\n\n请使用带系统代理的 `chrome-devtools` 或 `search_web` 检索 '{q}'。"

    # 3. 阶梯 3 & 4：本地未命中时的递进指引
    return f"# ⚠️ [L1/L0 未直接命中] 触发检索升级阶梯 (The Retrieval Escalation Protocol)\n\n1. 本地知识库与代码库未直接匹配针对 '{q}' 的特定红线；\n2. 下一步推荐动作：\n   - 🔹 第三方库 API 签名：请调用 `context7` MCP 获取官方库标准文档；\n   - 🔹 突发 Issue / 动态页面：若仍未解决，请调用 `chrome-devtools` 抓取 GitHub 官方仓库或发起网络检索；\n3. 对话即沉淀提醒：攻克该问题后，请执行 `/vault-save` 将新 Workaround 沉淀至 `99-Inbox/`。"


def tool_get_note(rel_path: str) -> str:
    """Read a markdown note or list directory contents from vault with smart fuzzy resolution."""
    raw_input = rel_path.strip()

    # 1. Clean Wikilink brackets [[path|alias]]
    clean_path = raw_input.strip("[]")
    if "|" in clean_path:
        clean_path = clean_path.split("|")[0].strip()
    clean_path = clean_path.strip().lstrip("/\\")

    # 2. Try direct resolution
    target = (VAULT_ROOT / clean_path).resolve()

    # Security check: must be inside VAULT_ROOT
    try:
        target.relative_to(VAULT_ROOT)
    except ValueError:
        return f"❌ 越界访问拒绝: {rel_path}"

    # 3. If exact path not found, try adding .md suffix
    if not target.exists() and not target.suffix and (target.with_suffix(".md")).exists():
        target = target.with_suffix(".md")

    # 4. If still not found, try fuzzy filename search across the entire vault
    if not target.exists():
        query_name = pathlib.Path(clean_path).stem.lower()
        candidates = []
        for f in VAULT_ROOT.rglob("*.md"):
            if f.is_file() and not any(p.startswith(".") for p in f.parts):
                if f.stem.lower() == query_name or query_name in f.stem.lower():
                    candidates.append(f)

        if len(candidates) == 1:
            target = candidates[0]
        elif len(candidates) > 1:
            # Prefer exact stem match
            exact = [c for c in candidates if c.stem.lower() == query_name]
            if exact:
                target = exact[0]
            else:
                matches_list = "\n".join([f"- `{c.relative_to(VAULT_ROOT).as_posix()}`" for c in candidates[:10]])
                return f"🔍 找到多个匹配笔记，请指定具体相对路径：\n{matches_list}"
        else:
            return f"❌ 知识库中未找到笔记: '{rel_path}'\n💡 提示：可使用 `search_vault` 或 `omni_search` 进行语义/关键词搜索。"

    # 5. Handle Directory Path gracefully (Instead of erroring '目标不是文件')
    if target.is_dir():
        rel_dir = target.relative_to(VAULT_ROOT).as_posix()
        readme = target / "README.md"
        if readme.is_file():
            content_txt = readme.read_text(encoding="utf-8", errors="replace")
            return f"# 📁 目录概览: {rel_dir} (自动读取 README.md)\n\n{content_txt}"

        # List all markdown files in directory
        md_files = [f for f in sorted(target.iterdir()) if f.is_file() and f.suffix == ".md"]
        sub_dirs = [d for d in sorted(target.iterdir()) if d.is_dir() and not d.name.startswith(".")]

        lines = [f"# 📁 知识库目录: `{rel_dir}/`\n"]
        if sub_dirs:
            lines.append("### 📂 子目录:")
            for d in sub_dirs:
                lines.append(f"- `📂 {d.name}/`")
        if md_files:
            lines.append("\n### 📄 文档列表:")
            for f in md_files:
                title_desc = f.name
                try:
                    txt = f.read_text(encoding="utf-8", errors="replace")[:300]
                    m = re.search(r'title:\s*["\']?([^"\'\n]+)["\']?', txt)
                    if m:
                        title_desc = f"{f.name} — {m.group(1)}"
                except Exception:
                    pass
                lines.append(f"- `📄 {target.relative_to(VAULT_ROOT).as_posix()}/{f.name}` ({title_desc})")

        if not md_files and not sub_dirs:
            lines.append("*(该目录下暂无 Markdown 文档)*")

        return "\n".join(lines)

    # 6. Read and return file content
    try:
        content_txt = target.read_text(encoding="utf-8", errors="replace")
        return f"# 📄 {target.relative_to(VAULT_ROOT).as_posix()}\n\n{content_txt}"
    except Exception as e:
        return f"❌ 读取失败: {e}"




def tool_get_rule_snippet(rule_name: str, section: Optional[str] = None) -> str:
    """Extract a precise section or heading snippet from a rule file to minimize token usage (JIT Micro-Slicing)."""
    # 1. Read note via tool_get_note
    note_content = tool_get_note(rule_name)
    if note_content.startswith("❌") or note_content.startswith("🔍"):
        return note_content

    if not section or not section.strip():
        # Return H1 and TOC / first 40 lines
        lines = note_content.splitlines()
        preview = "\n".join(lines[:45])
        return f"{preview}\n\n*(💡 提示：可传入 `section='章节关键词'` 获取具体细分段落)*"

    sec_query = section.strip().lower()
    lines = note_content.splitlines()

    matched_chunks = []
    current_chunk = []
    in_target_section = False
    current_level = 2

    for line in lines:
        if line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            heading_text = line.lstrip("#").strip().lower()

            if in_target_section:
                if level <= current_level:
                    # End of target section
                    matched_chunks.append("\n".join(current_chunk))
                    current_chunk = []
                    in_target_section = False

            if sec_query in heading_text:
                in_target_section = True
                current_level = level
                current_chunk.append(line)
                continue

        if in_target_section:
            current_chunk.append(line)

    if in_target_section and current_chunk:
        matched_chunks.append("\n".join(current_chunk))

    if not matched_chunks:
        return f"⚠️ 在 `{rule_name}` 中未找到包含 '{section}' 的章节。\n\n💡 提示：该文档包含以下核心二级章节：\n" + "\n".join([f"- {l}" for l in lines if l.startswith("## ")][:10])

    return f"# 🎯 [JIT 规则微切片: {rule_name} ➔ {section}]\n\n" + "\n\n---\n\n".join(matched_chunks)


def tool_list_standards() -> str:
    """List all available language standards and cross-language rules."""
    lang_dir = VAULT_ROOT / "03-Languages"
    rules_dir = VAULT_ROOT / "01-Rules"
    career_dir = VAULT_ROOT / "09-Career"

    lines = ["# 📚 Coding Vault 知识库目录索引\n"]

    if lang_dir.is_dir():
        lines.append("## 💻 语言工程双版本规范 (03-Languages/)")
        for lang_subdir in sorted(lang_dir.iterdir()):
            if lang_subdir.is_dir():
                st = list(lang_subdir.glob("*-STANDARDS.md"))
                cs = list(lang_subdir.glob("*-CHEATSHEET.md"))
                st_name = st[0].name if st else "无"
                cs_name = cs[0].name if cs else "无"
                lines.append(f"- **{lang_subdir.name}**:")
                lines.append(f"  - 规范 (Agent 约束版): `03-Languages/{lang_subdir.name}/{st_name}`")
                lines.append(f"  - 速查 (人类速查版): `03-Languages/{lang_subdir.name}/{cs_name}`")

    if rules_dir.is_dir():
        lines.append("\n## 🏛️ 跨语言架构与通用规则 (01-Rules/)")
        for rule_file in sorted(rules_dir.glob("*.md")):
            lines.append(f"- `01-Rules/{rule_file.name}`")

    if career_dir.is_dir():
        lines.append("\n## 🎯 面试高频考点与职业储备 (09-Career/)")
        for note_file in sorted(career_dir.rglob("*.md")):
            rel = note_file.relative_to(VAULT_ROOT).as_posix()
            lines.append(f"- `{rel}`")

    return "\n".join(lines)


def tool_get_code_template(template_name: str, lang: Optional[str] = None) -> str:
    """Extract pure production code template without markdown wrapper."""
    tpl_dir = VAULT_ROOT / "Templates" / "code"
    clean_name = template_name.strip().lower()

    matches = []
    for f in tpl_dir.rglob("*"):
        if f.is_file():
            if clean_name in f.name.lower():
                if lang:
                    if lang.lower() in f.parent.name.lower() or lang.lower() in f.name.lower():
                        matches.append(f)
                else:
                    matches.append(f)

    if not matches:
        return f"❌ 未找到匹配的代码模板: '{template_name}' (可选语言: go, python, typescript, sql, docker-k8s)"

    target_file = matches[0]
    try:
        content = target_file.read_text(encoding="utf-8", errors="replace")
        rel_path = target_file.relative_to(VAULT_ROOT).as_posix()
        return f"// ==============================================================================\n// 📦 Code Template: {rel_path}\n// ==============================================================================\n\n{content}"
    except Exception as e:
        return f"❌ 读取模板失败: {e}"


def tool_save_inbox_draft(title: str, content: str, tags: Optional[List[str]] = None, source: Optional[str] = None) -> str:
    """Save a new knowledge learning or pitfall workaround draft into 99-Inbox/ with A-MAC admission gate."""
    t_clean = title.strip()
    c_clean = content.strip()

    if not t_clean or len(t_clean) < 4:
        return "❌ [A-MAC 准入拦截] 标题过短，必须清晰揭示技术主题（如 'Python 在 Windows 下 GBK 乱码修复'）。"
    if not c_clean or len(c_clean) < 30:
        return "❌ [A-MAC 准入拦截] 内容过短（<30字符），必须包含现象、根因分析与代码块。"

    trivial_keywords = ["test", "temp", "123", "todo", "fix typo", "临时", "测试"]
    if t_clean.lower() in trivial_keywords:
        return "❌ [A-MAC 准入拦截] 检测到一次性测试/琐碎记录，拒绝存入知识库。"

    inbox_dir = VAULT_ROOT / "99-Inbox"
    inbox_dir.mkdir(parents=True, exist_ok=True)

    today = date.today().strftime("%Y-%m-%d")

    safe_slug = re.sub(r'[\\/:*?"<>|\s]+', '-', t_clean.lower())
    safe_slug = re.sub(r'-+', '-', safe_slug).strip('-')
    if not safe_slug:
        safe_slug = "knowledge-note"

    filename = f"{today}-{safe_slug}.md"
    file_path = inbox_dir / filename

    counter = 1
    while file_path.exists():
        filename = f"{today}-{safe_slug}-{counter}.md"
        file_path = inbox_dir / filename
        counter += 1

    tag_list = tags if isinstance(tags, list) else []
    if "status/draft" not in tag_list:
        tag_list.append("status/draft")
    if "category/troubleshooting" not in tag_list and "category/rules" not in tag_list and "category/notes" not in tag_list:
        tag_list.append("category/notes")

    tag_lines = "\n".join(f"  - {t.lstrip('#')}" for t in tag_list)
    source_val = source.strip() if source else "会话自动沉淀"

    frontmatter = f"""---
title: "{t_clean}"
created: {today}
updated: {today}
type: source-notes
tags:
{tag_lines}
status: draft
audience: both
source: "{source_val}"
---

"""
    full_text = frontmatter + c_clean + "\n"

    try:
        file_path.write_text(full_text, encoding="utf-8")
        rel_path = file_path.relative_to(VAULT_ROOT).as_posix()
        return f"🎉 成功沉淀草稿至知识库 (A-MAC Passed)！\n\n- 📄 相对路径: `{rel_path}`\n- 📌 标题: {t_clean}\n- 🏷️ 标签: {', '.join(tag_list)}\n\n💡 提示：后续可调用 `promote_inbox_draft` 或运行 `python scripts/vault-inbox-consolidate.py --apply` 将其智能晋级至正式规范。"
    except Exception as e:
        return f"❌ 写入草稿失败: {e}"


def tool_vault_proactive_scan(project_path: Optional[str] = None, limit: int = 15) -> str:
    """Run proactive scanner across codebases to discover TODOs, HACKs, workarounds, and technical debt."""
    scanner_script = VAULT_ROOT / "scripts" / "vault-proactive-scan.py"
    if not scanner_script.is_file():
        return f"❌ 找不到扫描脚本: {scanner_script}"

    cmd = [sys.executable, str(scanner_script), "--limit", str(limit)]
    if project_path:
        cmd.extend(["--code-dir", project_path])

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=30)
        return res.stdout if res.stdout.strip() else res.stderr
    except Exception as e:
        return f"❌ 扫描器执行异常: {e}"


def tool_promote_inbox_draft(draft_filename: str, target_dir: str) -> str:
    """Promote an inbox draft into formal 03-Languages/ or 01-Rules/ with updated frontmatter."""
    inbox_dir = VAULT_ROOT / "99-Inbox"
    target_clean = target_dir.strip().lstrip("/\\")
    dest_dir = (VAULT_ROOT / target_clean).resolve()

    try:
        dest_dir.relative_to(VAULT_ROOT)
    except ValueError:
        return f"❌ 越界目标目录: {target_dir}"

    draft_path = (inbox_dir / draft_filename).resolve()
    try:
        draft_path.relative_to(inbox_dir.resolve())
    except ValueError:
        return f"❌ 越界源文件: {draft_filename} 不在 99-Inbox/ 内"

    if not draft_path.exists():
        matches = list(inbox_dir.glob(f"*{draft_filename}*"))
        if len(matches) > 1:
            names = [m.name for m in matches[:5]]
            return f"❌ 多个匹配，请指定具体文件名: {', '.join(names)}..."
        elif matches:
            draft_path = matches[0].resolve()
        else:
            return f"❌ 未在 99-Inbox/ 找到草稿: {draft_filename}"

    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file = dest_dir / draft_path.name

    try:
        content = draft_path.read_text(encoding="utf-8", errors="replace")
        today = date.today().strftime("%Y-%m-%d")
        content = re.sub(r'status:\s*draft', 'status: stable', content)
        content = re.sub(r'updated:\s*\S+', f'updated: {today}', content)
        dest_file.write_text(content, encoding="utf-8")
        draft_path.unlink()
        rel_dest = dest_file.relative_to(VAULT_ROOT).as_posix()
        return f"🎉 成功将草稿晋级为正式资产！\n\n- 🚀 新路径: `{rel_dest}`\n- 🟢 状态: `status: stable`\n- 📅 更新时间: `{today}`"
    except Exception as e:
        return f"❌ 晋级失败: {e}"


# ==============================================================================
# MCP Definitions: Tools & Prompts
# ==============================================================================
TOOLS_DEFINITION = [
    {
        "name": "vault_proactive_scan",
        "description": "【代码库主动体检与待办挖掘】深度扫描指定项目 (如 '{{CODE_ROOT}}\\示例项目')，挖掘未决 TODO、FIXME、HACK、架构妥协 Workaround 与高价值技术债，输出高 ROI 改进候选表。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_path": {
                    "type": "string",
                    "description": "目标项目绝对或相对路径，例如 '{{CODE_ROOT}}\\示例项目'。默认扫描 {{CODE_ROOT}} 全局。"
                },
                "limit": {
                    "type": "integer",
                    "description": "最多返回的高价值待办条数 (默认 15)",
                    "default": 15
                }
            }
        }
    },
    {
        "name": "omni_search",
        "description": "【全景阶梯智能检索中枢 (The Retrieval Escalation Gateway)】自动执行多级阶梯检索策略 (L1 Vault -> L0 CodeGraph -> L2 context7 -> L3 Web)。在 'ladder' 模式下命中本地知识库时自动短路截断 (<10ms)，彻底消灭重复造轮子与盲目外部网络搜索。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "检索关键词、报错信息或技术需求（如 'Go 并发锁', 'Redis 分布式锁', 'Windows GBK stdout', 'FastAPI 依赖注入'）"
                },
                "scope": {
                    "type": "string",
                    "enum": ["ladder", "vault", "code", "doc", "web"],
                    "description": "检索模式：'ladder' (默认智能阶梯短路), 'vault' (仅知识库规范), 'code' (仅本地工程代码库), 'doc' (仅第三方库官方文档), 'web' (仅全网搜索)",
                    "default": "ladder"
                },
                "top": {
                    "type": "integer",
                    "description": "返回最多条数 (默认 5)",
                    "default": 5
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "search_vault",
        "description": "【首选第一顺位检索工具 (Priority 1)】在执行任何代码编写、技术方案设计、架构决策或发起外部网络搜索（fetch / web_search / context7）前，MUST 必须首先调用本工具检索 Coding Vault 本地工程规范、踩坑记录与成熟代码模板。本地未命中时方可逐级向外检索。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词或报错模式，如 'Go 命名规范', 'Windows GBK 乱码', '死锁', '秒杀系统', 'Worker Pool', 'Redis 分布式锁', '滑动窗口'"
                },
                "tag": {
                    "type": "string",
                    "description": "可选标签过滤，如 'lang/go', 'topic/concurrency', 'category/interview', 'category/system-design'"
                },
                "top": {
                    "type": "integer",
                    "description": "返回最多结果条数 (默认 5)",
                    "default": 5
                },
                "format": {
                    "type": "string",
                    "enum": ["compact", "detailed", "json"],
                    "description": "输出格式：compact (极简行), detailed (带上下文与1-Hop图谱), json (结构化数据)",
                    "default": "detailed"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_note",
        "description": "根据相对路径读取 Coding 知识库中的 Markdown 规范、设计文档、面试高频考点或代码模板完整内容。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "rel_path": {
                    "type": "string",
                    "description": "知识库相对路径，例如 '03-Languages/GO/GO-STANDARDS.md', '09-Career/System-Design/系统设计笔记.md'"
                }
            },
            "required": ["rel_path"]
        }
    },
    {
        "name": "get_rule_snippet",
        "description": "【JIT 规则微切片 (Token 极省)】根据规范名称和章节关键词（如 '命名', '错误处理', '并发', '最左前缀'），精准提取具体段落与代码块（<50行），杜绝整篇大文件污染上下文窗口。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "rule_name": {
                    "type": "string",
                    "description": "规范名称或相对路径，如 'GO-STANDARDS', '〔你的领域通用规范〕', 'PYTHON-STANDARDS', '领域专题规范'"
                },
                "section": {
                    "type": "string",
                    "description": "章节关键词，如 '命名', '并发', '错误处理', '移动端', '模块链接期'"
                }
            },
            "required": ["rule_name"]
        }
    },
    {
        "name": "get_code_template",
        "description": "【生产级纯代码提取】根据模板名与编程语言直接提取干净的生产级源码模板（无需剥离 Markdown）。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "template_name": {
                    "type": "string",
                    "description": "模板名称关键词，如 'worker-pool', 'http-server', 'redis-lock', 'cli-tool', 'schema-best-practices', 'deployment', 'multistage'"
                },
                "lang": {
                    "type": "string",
                    "description": "编程语言/生态，如 'go', 'python', 'typescript', 'sql', 'docker-k8s'"
                }
            },
            "required": ["template_name"]
        }
    },
    {
        "name": "list_standards",
        "description": "列出 Coding 知识库中所有支持语言的双版本工程规范、通用架构规则与面试高频考点清单。",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "save_inbox_draft",
        "description": "【A-MAC 准入保护】一键将本次对话中发现的非直觉 Bug 排障、踩坑 Workaround、架构决策沉淀为草稿存入 99-Inbox/。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "笔记标题，清晰揭示技术问题与核心解法"
                },
                "content": {
                    "type": "string",
                    "description": "沉淀正文（包含：1. 现象与危害; 2. 根因剖析; 3. 终极解决方案与代码块）"
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "分级标签列表，如 ['lang/go', 'topic/concurrency', 'category/troubleshooting']"
                },
                "source": {
                    "type": "string",
                    "description": "知识来源备注（如 '真实项目排障复盘'）"
                }
            },
            "required": ["title", "content"]
        }
    },
    {
        "name": "promote_inbox_draft",
        "description": "【会话内一键晋级】将 99-Inbox/ 中的草稿流转提升为 03-Languages/ 或 01-Rules/ 的正式稳定规范。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "draft_filename": {
                    "type": "string",
                    "description": "99-Inbox/ 下的草稿文件名或关键词"
                },
                "target_dir": {
                    "type": "string",
                    "description": "目标目录，例如 '03-Languages/Python' 或 '01-Rules'"
                }
            },
            "required": ["draft_filename", "target_dir"]
        }
    }
]

PROMPTS_DEFINITION = [
    {
        "name": "vault-researcher",
        "description": "代码库探路者：遵循反造轮子天梯，极速理清符号、架构与调用链",
        "arguments": []
    },
    {
        "name": "vault-code-reviewer",
        "description": "质量与安全审阅者：依照 STANDARDS 与复用天梯深挖并发竞争与冗余造轮子",
        "arguments": []
    },
    {
        "name": "vault-interview-coach",
        "description": "大厂面试考官：依照 09-Career 考点进行 1v1 高压答辩与扣分点评",
        "arguments": []
    },
    {
        "name": "vault-grill-master",
        "description": "架构设计极限压测与 ADR 自动生成器：以知识库为尺拷打设计决策",
        "arguments": []
    }
]


def handle_request(req: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Process a single JSON-RPC request."""
    method = req.get("method", "")
    req_id = req.get("id")
    params = req.get("params", {})

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {},
                    "prompts": {}
                },
                "serverInfo": {
                    "name": "coding-vault-search",
                    "version": "2.6.0"
                }
            }
        }

    elif method == "notifications/initialized" or method == "initialized":
        return None

    elif method == "ping":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {}
        }

    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": TOOLS_DEFINITION
            }
        }

    elif method == "prompts/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "prompts": PROMPTS_DEFINITION
            }
        }

    elif method == "prompts/get":
        p_name = params.get("name", "")
        prompt_map = {
            "vault-researcher": "05-Tools/Subagents/子代理调研角色（自建）.md",
            "vault-code-reviewer": "05-Tools/Subagents/子代理复核角色（自建）.md",
            "vault-interview-coach": "05-Tools/Subagents/子代理面试角色（自建）.md",
            "vault-grill-master": "05-Tools/Subagents/子代理重构角色（自建）.md",
        }
        rel_p = prompt_map.get(p_name)
        if rel_p and (VAULT_ROOT / rel_p).exists():
            text_p = (VAULT_ROOT / rel_p).read_text(encoding="utf-8", errors="replace")
        else:
            text_p = f"You are an expert engineering assistant powered by Coding Vault ({VAULT_ROOT})."

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "description": f"Standard System Prompt for {p_name}",
                "messages": [
                    {
                        "role": "user",
                        "content": {
                            "type": "text",
                            "text": text_p
                        }
                    }
                ]
            }
        }

    elif method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        try:
            if tool_name == "vault_proactive_scan":
                p_path = arguments.get("project_path")
                l_val = arguments.get("limit", 15)
                text_result = tool_vault_proactive_scan(p_path, limit=l_val)
            elif tool_name == "omni_search":
                query = arguments.get("query", "")
                scope = arguments.get("scope", "ladder")
                top = arguments.get("top", 5)
                text_result = tool_omni_search(query, scope=scope, top=top)
            elif tool_name == "search_vault":
                query = arguments.get("query", "")
                tag = arguments.get("tag")
                top = arguments.get("top", 5)
                fmt = arguments.get("format", "detailed")
                text_result = tool_search_vault(query, tag=tag, top=top, output_format=fmt)
            elif tool_name == "get_note":
                rel_path = arguments.get("rel_path", "")
                text_result = tool_get_note(rel_path)
            elif tool_name == "get_code_template":
                t_name = arguments.get("template_name", "")
                lang = arguments.get("lang")
                text_result = tool_get_code_template(t_name, lang=lang)
            elif tool_name == "list_standards":
                text_result = tool_list_standards()
            elif tool_name == "get_rule_snippet":
                r_name = arguments.get("rule_name", "")
                sec = arguments.get("section")
                text_result = tool_get_rule_snippet(r_name, section=sec)
            elif tool_name == "save_inbox_draft":
                title = arguments.get("title", "")
                content = arguments.get("content", "")
                tags = arguments.get("tags")
                source = arguments.get("source")
                text_result = tool_save_inbox_draft(title, content, tags=tags, source=source)
            elif tool_name == "promote_inbox_draft":
                d_file = arguments.get("draft_filename", "")
                t_dir = arguments.get("target_dir", "")
                text_result = tool_promote_inbox_draft(d_file, t_dir)
            else:
                text_result = f"❌ 未知工具: {tool_name}"

            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": text_result
                        }
                    ]
                }
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": f"❌ 执行异常: {e}\n{traceback.format_exc()}"
                        }
                    ],
                    "isError": True
                }
            }

    else:
        if req_id is not None:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32601,
                    "message": f"Method not found: {method}"
                }
            }
        return None


def main():
    """Main stdio loop for JSON-RPC MCP Server."""
    for line in sys.stdin:
        line_clean = line.strip()
        if not line_clean:
            continue

        try:
            req = json.loads(line_clean)
            resp = handle_request(req)
            if resp is not None:
                sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
                sys.stdout.flush()
        except json.JSONDecodeError:
            pass
        except Exception as e:
            sys.stderr.write(f"MCP Server error: {e}\n")
            sys.stderr.flush()


if __name__ == "__main__":
    main()
