#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
Vault Inbox Consolidator & Promotion Pipeline (Inbox 智能流转与自动吸收引擎)
================================================================================
功能：
1. 扫描 99-Inbox/ 下的待办草稿笔记
2. 依据 Frontmatter tags 自动推荐或定向归档目标
3. --dry-run（默认）：预览推荐目标与执行计划
4. --apply / --execute（等效别名，对外文档统一 --apply 口径）：执行归档
   （创建/追加目标文件 + 删除原件，单事务保护：全部动作包进单个
   VaultTransaction，任何一步失败 → 整体回滚、非 0 退出）
5. 支持 --json / --file / --vault-path
================================================================================
"""

import os
import sys
import re
import json
import argparse
from pathlib import Path
from datetime import datetime

# Windows GBK stdout protection
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# vault 级事务原语（P1 Task-3）：本脚本以脚本目录为 sys.path 根被运行/加载，
# vault_transaction.py 与本文件同目录，可直接导入。
from vault_transaction import TransactionError, VaultTransaction

# VAULT-STRUCTURE §5: CHEATSHEET MUST 由 STANDARDS 单向浓缩，章节 1:1 对齐
CHEATSHEET_STALE = (
    "⚠️ CHEATSHEET 需要更新：VAULT-STRUCTURE §5 要求 CHEATSHEET 由 STANDARDS "
    "单向浓缩生成、章节 1:1 对齐。请阅读 {standards} 中新增章节，"
    "在 {cheatsheet} 对应位置追加浓缩版（一句话核心法则 + ≤5 行代码示例）。"
)

# ---------------------------------------------------------------------------
# Routing config (P3 Task-2): tag → destination 数据化于 routing.json
# （ADR-0001 #15 路由配置化；唯一消费者 = 本脚本，triage 实测不消费路由）
# ---------------------------------------------------------------------------
ROUTING_JSON = Path(__file__).resolve().parent / "routing.json"

_VALID_ROUTE_TYPES = frozenset({"dual", "rule-append", "source-article", "project"})
_REQUIRED_KEYS_BY_TYPE = {
    "dual": ("standards", "cheatsheet"),
    "rule-append": ("target",),
    "source-article": ("target_dir",),
    "project": ("target_project",),
}


def _validate_tag(tag: "str | None") -> None:
    """tag 必须为 ``namespace/name`` 形式（VAULT-STRUCTURE 五命名空间 tag 双轨）。"""
    if (not isinstance(tag, str) or "/" not in tag
            or tag.startswith("/") or tag.endswith("/")):
        raise ValueError(f"非法 tag 键 {tag!r}：必须为 namespace/name 形式")


def _validate_target_info(where: str, info: dict) -> None:
    """校验单条路由/回退目标：type 枚举 + name + 按 type 必需键，缺一抛 ValueError。"""
    route_type = info.get("type")
    if not isinstance(route_type, str) or not route_type:
        raise ValueError(f"{where}: 缺少 type 字段")
    if route_type not in _VALID_ROUTE_TYPES:
        raise ValueError(
            f"{where}: 未知 type {route_type!r}（合法: {sorted(_VALID_ROUTE_TYPES)}）"
        )
    if not isinstance(info.get("name"), str) or not info.get("name"):
        raise ValueError(f"{where}: 缺少 name 字段")
    missing = [k for k in _REQUIRED_KEYS_BY_TYPE[route_type] if not info.get(k)]
    if missing:
        raise ValueError(f"{where}: type={route_type} 缺少必需键: {', '.join(missing)}")


def _load_routing_doc(json_path: "str | Path") -> dict:
    """读取并校验 routing.json 顶层结构（schema_version / routes / fallback）。"""
    path = Path(json_path)
    if not path.is_file():
        raise FileNotFoundError(f"routing 配置不存在: {path}")
    doc = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise ValueError(f"{path}: 顶层必须为 JSON object")
    if doc.get("schema_version") != 1:
        raise ValueError(f"{path}: 不支持的 schema_version: {doc.get('schema_version')!r}")
    routes = doc.get("routes")
    if not isinstance(routes, list) or not routes:
        raise ValueError(f"{path}: routes 必须为非空数组")
    fallback = doc.get("fallback")
    if not isinstance(fallback, dict) or "default" not in fallback:
        raise ValueError(f"{path}: fallback 必须为含 default 分支的 object")
    return doc


def load_routing(json_path: "str | Path") -> dict:
    """读取 routing.json 并展平为 ``tag → target_info`` 映射。

    返回值与抽取前的硬编码 ``TARGET_ROUTING_MAP`` 完全等价（等价性由
    ``scripts/tests/routing 契约测试.py`` 参照基线锁定）。

    Raises:
        FileNotFoundError: 配置文件不存在。
        ValueError: schema_version 非法 / routes 缺失、tag 键非法或重复 /
            缺 type 或 name / type 必需键缺失。
    """
    doc = _load_routing_doc(json_path)
    routing: dict = {}
    for i, route in enumerate(doc["routes"]):
        where = f"routes[{i}] ({json_path})"
        if not isinstance(route, dict):
            raise ValueError(f"{where}: 必须为 object")
        tag = route.get("tag")
        _validate_tag(tag)
        _validate_target_info(f"tag={tag!r} {where}", route)
        if tag in routing:
            raise ValueError(f"{where}: 重复 tag 键: {tag!r}")
        routing[tag] = {k: v for k, v in route.items() if k != "tag"}
    return routing


def load_fallback(json_path: "str | Path") -> dict:
    """读取 routing.json 的 fallback 段，返回 ``note_type → target_info`` 映射。

    ``default`` 键为 note_type 未命中时的 else 分支（与抽取前 analyze_draft
    内嵌 fallback if/else 语义 1:1）。校验规则同 :func:`load_routing`。
    """
    doc = _load_routing_doc(json_path)
    fallback: dict = {}
    for note_type, info in doc["fallback"].items():
        where = f"fallback[{note_type!r}] ({json_path})"
        if not isinstance(info, dict):
            raise ValueError(f"{where}: 必须为 object")
        _validate_target_info(where, info)
        fallback[note_type] = dict(info)
    return fallback


# ---------------------------------------------------------------------------
# Frontmatter parser
# ---------------------------------------------------------------------------
def parse_frontmatter(content: str):
    """解析 YAML Frontmatter，返回 (meta_dict, body_str)。"""
    if not content.startswith("---"):
        return {}, content

    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content

    fm_raw = parts[1].strip()
    body = parts[2].strip()
    meta = {}

    current_key = None
    for line in fm_raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("- ") and current_key:
            val = line[2:].strip().strip('"').strip("'")
            if isinstance(meta.get(current_key), list):
                meta[current_key].append(val)
            else:
                meta[current_key] = [val]
        elif ":" in line:
            k, v = line.split(":", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            current_key = k
            if v:
                meta[k] = v
            else:
                meta[k] = []

    return meta, body


def rewrite_frontmatter(content: str, extra_fields: dict) -> str:
    """在 frontmatter 中追加/更新字段，返回新文件内容。"""
    if not content.startswith("---"):
        return content

    parts = content.split("---", 2)
    if len(parts) < 3:
        return content

    fm_text = parts[1]
    body = parts[2]

    # 检查并更新/追加字段
    for key, value in extra_fields.items():
        pattern = rf"^{re.escape(key)}:\s*.*$"
        replacement = f'{key}: "{value}"'
        if re.search(pattern, fm_text, flags=re.MULTILINE):
            fm_text = re.sub(pattern, replacement, fm_text, flags=re.MULTILINE)
        else:
            fm_text = fm_text.rstrip() + f"\n{replacement}\n"

    return f"---\n{fm_text}---{body}"


# ---------------------------------------------------------------------------
# Content extraction helpers
# ---------------------------------------------------------------------------
def extract_body_sections(body: str) -> dict:
    """Extract body into {header, sections, code_blocks}."""
    sections = re.findall(r"^(#{1,3})\s+(.+)$", body, flags=re.MULTILINE)
    code_blocks = re.findall(r"```[\s\S]*?```", body, re.MULTILINE)
    return {
        "sections": sections,
        "code_blocks_count": len(code_blocks),
        "line_count": len(body.splitlines()),
    }


def format_for_append(title: str, body: str, source_file: str) -> str:
    """Format inbox content for appending to an existing file."""
    return f"\n\n---\n\n#### {title}\n\n> 来源: `{source_file}` | 日期: {datetime.now().strftime('%Y-%m-%d')}\n\n{body}\n"


# ---------------------------------------------------------------------------
# Core: analyze one draft
# ---------------------------------------------------------------------------
def analyze_draft(file_path: Path, vault_root: Path):
    """分析单个草稿，返回 summary dict。"""
    content = file_path.read_text(encoding="utf-8", errors="replace")
    meta, body = parse_frontmatter(content)

    title = meta.get("title", file_path.stem)
    tags = meta.get("tags", [])
    if isinstance(tags, str):
        tags = [tags]
    status = meta.get("status", "draft")
    note_type = meta.get("type", "source-notes")

    # 匹配路由（按优先级：lang > topic > category > fallback；P3 Task-2 起读 routing.json）
    routing_map = load_routing(ROUTING_JSON)
    matched_tag = None
    target_info = None
    for tag in tags:
        if tag in routing_map:
            matched_tag = tag
            target_info = routing_map[tag]
            break

    if not target_info:
        # Fallback: source-notes → Articles, rules → 01-Rules/（语义与抽取前 1:1）
        fallback_map = load_fallback(ROUTING_JSON)
        fb = fallback_map.get(note_type)
        if fb is None:
            fb = fallback_map["default"]
        target_info = dict(fb)

    info = extract_body_sections(body)

    # 计算目标文件路径
    target_path = None
    if target_info["type"] == "dual":
        target_path = target_info["standards"]
    elif target_info["type"] == "rule-append":
        target_path = target_info["target"]
    elif target_info["type"] == "source-article":
        # SCREAMING-SNAKE-CASE from title
        snake = re.sub(r"[^A-Za-z0-9一-鿿]+", "-", title).strip("-").upper()
        snake = re.sub(r"-{2,}", "-", snake)
        target_path = f"{target_info['target_dir']}/{snake}.md"
    elif target_info["type"] == "project":
        project = target_info.get("target_project", "Project")
        snake = re.sub(r"[^A-Za-z0-9一-鿿]+", "-", title).strip("-").upper()
        snake = re.sub(r"-{2,}", "-", snake)
        target_path = f"08-Projects/{project}/{snake}.md"

    return {
        "file": str(file_path.relative_to(vault_root)).replace("\\", "/"),
        "filename": file_path.name,
        "title": title,
        "tags": tags,
        "status": status,
        "note_type": note_type,
        "matched_tag": matched_tag,
        "target": target_info,
        "target_path": target_path,
        "info": info,
        "content": content,
        "body": body,
    }


# ---------------------------------------------------------------------------
# Transaction plan: collect execute actions, commit via single VaultTransaction
# ---------------------------------------------------------------------------
class _ArchivePlan:
    """``--execute`` 模式的动作收集器：只登记、不落盘（P1 Task-3）。

    所有"建目标 + 删原件"动作先在内存累积——``VaultTransaction`` 禁止同一
    事务内重复登记同一路径，因此同一目标文件的多次追加先合并为最终全文；
    循环结束后由 :func:`_commit_plan` 包进单个事务一次性提交，任何一步失败
    由事务整体回滚，不会产生半成品。
    """

    def __init__(self, vault_root: Path) -> None:
        self.vault_root = vault_root
        self.writes: dict[Path, str] = {}   # 目标绝对路径 → 累积后的最终全文
        self.deletes: list[Path] = []       # 待删除的 Inbox 原件绝对路径

    def stage_write(self, path: Path, new_text: str) -> None:
        """登记一次目标写入；同一路径后写覆盖前写（追加已提前合并进全文）。"""
        self.writes[path] = new_text

    def stage_delete(self, path: Path) -> None:
        """登记一次原件删除。"""
        self.deletes.append(path)


def _current_text(path: Path, plan: "_ArchivePlan | None") -> "str | None":
    """execute 写路径的"当前文本"来源：计划内已累积版本优先，其次读盘，均无则 None。"""
    if plan is not None and path in plan.writes:
        return plan.writes[path]
    if path.exists():
        return path.read_text(encoding="utf-8")
    return None


def _write_text(path: Path, new_text: str, plan: "_ArchivePlan | None") -> None:
    """execute 写路径统一出口：plan 为 None 直接写盘（旧行为），否则登记进事务计划。"""
    if plan is None:
        path.write_text(new_text, encoding="utf-8")
    else:
        plan.stage_write(path, new_text)


def _commit_plan(vault_root: Path, plan: _ArchivePlan) -> None:
    """把收集到的建目标+删原件动作包进单个 VaultTransaction 提交（P1 Task-3）。

    任何一步失败（含 commit 中途）→ 事务整体回滚并抛出异常；调用方负责
    stderr 说明与非 0 退出码。
    """
    tx_id = f"inbox-consolidate-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}"
    with VaultTransaction(vault_root, tx_id=tx_id) as tx:
        for path, text in plan.writes.items():
            tx.stage(path, new_text=text)
        for path in plan.deletes:
            tx.stage_deletion(path)


# ---------------------------------------------------------------------------
# Execute: perform the actual archival
# ---------------------------------------------------------------------------
def execute_archival(vault_root: Path, draft: dict, dry_run: bool = True,
                     plan: "_ArchivePlan | None" = None) -> dict:
    """执行单个草稿的归档操作。返回 {ok, message, action}。

    ``plan`` 非空（execute 事务模式）时只把写入动作登记进计划、不落盘；
    为 None 时保持旧行为：直接写盘。
    """
    target = draft["target"]
    target_type = target["type"]
    target_path_rel = draft["target_path"]
    source_rel = draft["file"]

    if target_type == "dual":
        return _archive_dual(vault_root, draft, target, dry_run, plan)
    elif target_type == "rule-append":
        return _archive_rule_append(vault_root, draft, target, dry_run, plan)
    elif target_type in ("source-article", "project"):
        return _archive_new_file(vault_root, draft, dry_run, plan)
    else:
        return {"ok": False, "message": f"未知目标类型: {target_type}", "action": "skip"}


def _archive_dual(vault_root, draft, target, dry_run,
                  plan: "_ArchivePlan | None" = None):
    """追加到 STANDARDS 文件，并检测 CHEATSHEET 是否需要同步更新。

    VAULT-STRUCTURE §5: CHEATSHEET MUST 由 STANDARDS 单向浓缩，章节 1:1 对齐。
    STANDARDS 追加后，CHEATSHEET 自动过期——脚本返回明确的 agent 更新指令。
    """
    std_path = vault_root / target["standards"]
    ch_path = vault_root / target["cheatsheet"]
    title = draft["title"]
    body = draft["body"]
    source = draft["file"]
    lang = target["name"]

    append_text = format_for_append(title, body, source)

    # 生成章节标题（与 CHEATSHEET 中的 heading 对齐）
    section_heading = re.sub(r"[^A-Za-z0-9一-鿿]+", "-", title).strip("-").upper()

    if dry_run:
        warning = ""
        if ch_path.exists():
            ch_content = ch_path.read_text(encoding="utf-8")
            if section_heading not in ch_content:
                warning = (
                    f"\n⚠️  CHEATSHEET 同步: {target['cheatsheet']} 中未找到 "
                    f"「{section_heading}」章节，STANDARDS 追加后需浓缩补入。"
                )
            else:
                warning = f"\n✅  CHEATSHEET 已包含「{section_heading}」，无需更新。"
        else:
            warning = (
                f"\n⚠️  CHEATSHEET 缺失: {target['cheatsheet']} 不存在，"
                f"请从 STANDARDS 浓缩生成完整双版本。"
            )

        return {
            "ok": True,
            "action": "dual-append",
            "target": target["standards"],
            "cheatsheet": target["cheatsheet"],
            "message": (
                f"[DRY-RUN] 将追加至 STANDARDS: {target['standards']}"
                f" ({len(body.splitlines())} 行)"
                f"{warning}"
            ),
        }

    # 执行追加到 STANDARDS（plan 非空 = 事务模式：只登记不落盘）
    existing = _current_text(std_path, plan)
    if existing is not None:
        new_text = existing + append_text
    else:
        new_text = f"# {lang.upper()} Standards\n{append_text}"
    _write_text(std_path, new_text, plan)

    # 检测 CHEATSHEET 同步状态
    cheatsheet_action = "synced"
    cheatsheet_msg = ""
    if ch_path.exists():
        ch_content = ch_path.read_text(encoding="utf-8")
        if section_heading not in ch_content:
            cheatsheet_action = "stale"
            cheatsheet_msg = CHEATSHEET_STALE.format(
                standards=target["standards"], cheatsheet=target["cheatsheet"]
            )
        else:
            cheatsheet_msg = f"✅ CHEATSHEET 已包含「{section_heading}」"
    else:
        cheatsheet_action = "missing"
        cheatsheet_msg = (
            f"⚠️ CHEATSHEET 缺失: {target['cheatsheet']} 不存在，"
            f"请从 STANDARDS 浓缩生成完整双版本。"
        )

    result = {
        "ok": True,
        "action": "dual-append",
        "target": target["standards"],
        "cheatsheet": target["cheatsheet"],
        "cheatsheet_action": cheatsheet_action,
        "message": f"已追加至 STANDARDS: {target['standards']}",
    }
    if cheatsheet_msg:
        result["message"] += f"\n{cheatsheet_msg}"
    return result


def _archive_rule_append(vault_root, draft, target, dry_run,
                         plan: "_ArchivePlan | None" = None):
    """追加到规则文件。"""
    target_path = vault_root / target["target"]
    title = draft["title"]
    body = draft["body"]
    source = draft["file"]

    append_text = format_for_append(title, body, source)

    if dry_run:
        return {
            "ok": True,
            "action": "append",
            "target": target["target"],
            "message": f"[DRY-RUN] 将追加至 {target['target']} ({len(body.splitlines())} 行)",
        }

    # plan 非空 = 事务模式：只登记不落盘
    existing = _current_text(target_path, plan)
    if existing is not None:
        new_text = existing + append_text
    else:
        new_text = f"# {target['name']}\n{append_text}"
    _write_text(target_path, new_text, plan)

    return {"ok": True, "action": "append", "target": target["target"],
            "message": f"已追加至 {target['target']}"}


def _archive_new_file(vault_root, draft, dry_run,
                      plan: "_ArchivePlan | None" = None):
    """创建新文件（source-article / project）。"""
    target_path_rel = draft["target_path"]
    target_path = vault_root / target_path_rel

    # 更新 frontmatter: status → stable
    new_content = rewrite_frontmatter(draft["content"], {"status": "stable"})

    if dry_run:
        exists_tag = " [已存在，将覆盖]" if target_path.exists() else ""
        return {
            "ok": True,
            "action": "create",
            "target": target_path_rel,
            "message": f"[DRY-RUN] 将创建 {target_path_rel}{exists_tag}",
        }

    # 目录创建在事务外（目录可能已含既有内容，不可事务回滚）；
    # commit 失败仅残留空目录，属可接受残留。
    target_path.parent.mkdir(parents=True, exist_ok=True)
    _write_text(target_path, new_content, plan)

    return {"ok": True, "action": "create", "target": target_path_rel,
            "message": f"已创建 {target_path_rel}"}


def _delete_original(file_path: Path, dry_run: bool,
                     plan: "_ArchivePlan | None" = None) -> dict:
    """删除 Inbox 原件（plan 非空 = 事务模式：登记删除，commit 时统一执行）。"""
    if dry_run:
        return {"ok": True, "action": "delete",
                "message": f"[DRY-RUN] 将删除 {file_path.name}"}

    if plan is None:
        file_path.unlink(missing_ok=True)
        message = f"已删除 {file_path.name}"
    else:
        # 事务模式此刻文件尚未删除："已删除"会在回滚场景误导排查
        plan.stage_delete(file_path)
        message = f"已登记删除（事务提交时执行）：{file_path.name}"
    return {"ok": True, "action": "delete", "message": message}


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------
def consolidate(vault_root: Path, target_file=None, dry_run=True, execute=False, as_json=False):
    """主流程：扫描 → 分析 → 执行（可选）。"""
    inbox_dir = vault_root / "99-Inbox"
    if not inbox_dir.exists():
        print(f"❌ Inbox 目录未找到: {inbox_dir}")
        return 1

    # 收集草稿
    if target_file:
        p = Path(target_file)
        if not p.is_absolute():
            p = vault_root / "99-Inbox" / target_file
        if not p.exists():
            found = list(inbox_dir.glob(f"*{target_file}*"))
            if found:
                p = found[0]
        drafts_raw = [p] if p.exists() and p.suffix == ".md" else []
    else:
        drafts_raw = [f for f in inbox_dir.glob("*.md") if not f.name.startswith("tpl-")]

    if not drafts_raw:
        msg = "📭 99-Inbox/ 当前无待处理草稿。"
        if as_json:
            print(json.dumps({"status": "empty", "message": msg}, ensure_ascii=False))
        else:
            print(msg)
        return 0

    # 分析所有草稿
    analyses = []
    for d in drafts_raw:
        try:
            a = analyze_draft(d, vault_root)
            analyses.append(a)
        except Exception as e:
            print(f"⚠️ 分析失败 {d.name}: {e}")

    if not analyses:
        print("⚠️ 无可处理草稿。")
        return 0

    # 输出分析结果
    if not as_json:
        print("=" * 72)
        print(f"  📥 INBOX CONSOLIDATION {'PREVIEW' if dry_run else 'EXECUTION'}")
        print("=" * 72)
        print(f"  Vault: {vault_root}")
        print(f"  Drafts: {len(analyses)}")
        print("-" * 72)

    # P1 Task-3: execute 模式先收集全部建目标+删原件动作，循环结束后包进单个事务
    plan = _ArchivePlan(vault_root) if execute else None
    results = []
    for i, a in enumerate(analyses, 1):
        arch_result = execute_archival(vault_root, a, dry_run=dry_run, plan=plan)

        if not as_json:
            print(f"\n  [{i}] {a['title']}")
            print(f"      Tags: {', '.join(a['tags'])}")
            print(f"      Target: {a['target']['name']} → {a['target_path']}")
            print(f"      Action: {arch_result['action']} — {arch_result['message']}")

        # 删除原件
        del_result = _delete_original(Path(vault_root / a["file"]), dry_run, plan)
        if not as_json and execute:
            print(f"      Delete: {del_result['message']}")

        row = {
            "file": a["file"],
            "title": a["title"],
            "target": a["target_path"],
            "action": arch_result["action"],
            "ok": arch_result["ok"],
            "message": arch_result["message"],
        }
        if "cheatsheet" in arch_result:
            row["cheatsheet"] = arch_result["cheatsheet"]
            row["cheatsheet_action"] = arch_result.get("cheatsheet_action", "unknown")
        results.append(row)

    if plan is not None:
        # 全部建目标+删原件动作包进单个事务：任何一步失败 → 整体回滚、非 0 退出
        try:
            _commit_plan(vault_root, plan)
        except TransactionError as exc:
            print(
                f"❌ 归档事务提交失败，已整体回滚（无半成品写入）: {exc}",
                file=sys.stderr,
            )
            return 1

    if not as_json:
        # CHEATSHEET 同步待办汇总
        ch_stale = [r for r in results if r.get("cheatsheet_action") == "stale"]
        ch_missing = [r for r in results if r.get("cheatsheet_action") == "missing"]
        if ch_stale or ch_missing:
            print("\n" + "-" * 72)
            print("  📋 CHEATSHEET 同步待办 (VAULT-STRUCTURE §5):")
            for r in ch_stale:
                print(f"    ⚠️  {r['cheatsheet']} ← 需从 STANDARDS 浓缩「{r['title']}」")
            for r in ch_missing:
                print(f"    ⚠️  {r['cheatsheet']} ← 整份 CHEATSHEET 缺失，需从 STANDARDS 生成")
            print("-" * 72)

        print("\n" + "=" * 72)
        ok_count = sum(1 for r in results if r["ok"])
        print(f"  ✅ {ok_count}/{len(results)} drafted processed"
              f" ({'preview' if dry_run else 'executed'})")
        print("=" * 72)
    else:
        print(json.dumps(results, indent=2, ensure_ascii=False))

    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Vault Inbox 智能流转与自动吸收引擎"
    )
    parser.add_argument("--file", "-f", help="指定处理的草稿文件名或路径")
    parser.add_argument("--execute", "--apply", dest="execute", action="store_true",
                        help="执行归档（创建目标文件 + 删除原件；--apply 为等效别名）。默认仅预览")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="仅预览（默认行为，--execute 覆盖）")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    parser.add_argument("--vault-path", help="知识库根目录")

    args = parser.parse_args()

    vault_root = (Path(args.vault_path).resolve() if args.vault_path
                  else Path(__file__).resolve().parent.parent)

    dry_run = not args.execute
    sys.exit(consolidate(vault_root, args.file, dry_run=dry_run,
                         execute=args.execute, as_json=args.json))


if __name__ == "__main__":
    main()
