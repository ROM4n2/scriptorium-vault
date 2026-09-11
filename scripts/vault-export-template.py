#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
Vault Template Exporter — 领域无关知识库骨架打包器 (manifest v2)

把本库导出为可分发的**领域无关模板**：引擎与治理规则随包，一切领域内容
空壳化（见 scripts/vault-template-manifest.json）。

设计原则
--------
* **清单驱动**：所有取舍由 manifest 声明，本脚本不含硬编码的包含/排除判断。
* **dry-run 默认**：默认只打印计划，`--apply` 才写盘（写盘目标 MUST 在库外）。
* **fail-closed**：清单未匹配的路径默认剔除（与 manifest 的 default 一致）。
* **导出后自检项**：断链修复、路由裁剪、图例映射清空——缺一则包内首跑必红。

暴露的纯函数（可单测，不碰磁盘）
--------------------------------
plan_export       分类统计（keep / structure_only / excluded / stub 区）
repair_links      把指向「未导出文件」的 wikilink 中性化为纯文本
prune_routing     裁掉目标已不存在的路由（含 dual 对存在性校验）
rewrite_legacy_map 清空导出测试里的 LEGACY_TARGET_ROUTING_MAP 基线
"""

import sys

# Windows GBK stdout 防护（全库约定）
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import argparse
import fnmatch
import json
import pathlib
import re
import shutil
import subprocess
from typing import Any, Dict, List, Optional, Set, Tuple

MANIFEST_REL = "scripts/vault-template-manifest.json"
ROUTING_REL = "scripts/routing.json"
ROUTING_TEST_REL = "scripts/tests/routing 契约测试.py"

# 多 Agent 入口：源库以符号链接指向 AGENTS.md；导出时物化为内容副本
AGENT_ENTRY_FILES = frozenset(
    {"CLAUDE.md", "GEMINI.md", ".cursorrules", ".windsurfrules", "CONVENTIONS.md"}
)

# 需要走去标识化的文本类扩展名（含无点号形态的配置文件名）
TEXT_EXTS = frozenset(
    {".md", ".py", ".sh", ".ps1", ".json", ".txt", ".canvas", ".yml", ".yaml",
     ".toml", ".cfg", ".ini", ".cursorrules", ".windsurfrules"}
)

# [[target]] / [[target|alias]] / [[target#anchor|alias]] / ![[embed]]
WIKILINK_RE = re.compile(r"(!?)\[\[([^\]\|#]+)(#[^\]\|]*)?(?:\|([^\]]*))?\]\]")
# 模块级 LEGACY_TARGET_ROUTING_MAP = { ... } 字面量块
LEGACY_MAP_RE = re.compile(
    r"(LEGACY_TARGET_ROUTING_MAP\s*=\s*)\{.*?\n\}", re.S
)

_STUB_README_TMPL = """---
title: "{zone} 区说明（模板初始骨架）"
created: {today}
updated: {today}
type: notes
tags:
  - category/notes
  - topic/onboarding
status: stable
audience: both
authority: synthetic
claim_risk: none
review_status: unreviewed
---

# {zone} 区

> 本目录当前为**初始骨架状态**（空是正常的）。

{hint}

## 下一步

1. 在 `01-Rules/VAULT-STRUCTURE.md` 查看本区职责定义；
2. 用 `Templates/` 下的模板起稿第一篇；
3. 写完跑 `python scripts/vault-quality-check.py --strict` 自检。
"""


def load_manifest(path: pathlib.Path) -> Dict[str, Any]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    if doc.get("schema_version") not in (1, 2):
        raise ValueError(f"{path}: 不支持的 schema_version: {doc.get('schema_version')!r}")
    for key in ("keep", "exclude"):
        if not isinstance(doc.get(key), list):
            raise ValueError(f"{path}: {key} 必须为列表")
    if doc.get("default", {}).get("unmatched") != "exclude":
        raise ValueError(f"{path}: default.unmatched MUST 为 'exclude'（fail-closed）")
    return doc


def _patterns(doc: Dict[str, Any], key: str) -> List[str]:
    return [item["pattern"] for item in doc.get(key, [])]


def _in_stub_zone(doc: Dict[str, Any], path: str) -> bool:
    return any(
        path == z["path"] or path.startswith(z["path"].rstrip("/") + "/")
        for z in doc.get("stub_zones", [])
    )


def tracked_files(vault_root: pathlib.Path) -> List[str]:
    """git 跟踪文件（-z：不转义中文路径，且天然排除 ignored 文件）。"""
    res = subprocess.run(
        ["git", "ls-files", "-z"], cwd=str(vault_root),
        capture_output=True, encoding="utf-8", errors="replace",
    )
    if res.returncode != 0:
        raise RuntimeError(f"git ls-files 失败: {res.stderr.strip()}")
    return [p for p in res.stdout.split("\0") if p.strip()]


def classify_paths(paths: List[str], doc: Dict[str, Any]) -> Dict[str, List[str]]:
    """按清单分类；未匹配者归入 excluded（fail-closed）。

    `drop` 优先级最高（即使命中 keep 也不导出）——用于排除与作者领域强绑定的
    测试 fixture 等「命中 keep 通配、但导出后必红」的文件。
    """
    keep_p, so_p, ex_p = (
        _patterns(doc, "keep"), _patterns(doc, "structure_only"), _patterns(doc, "exclude")
    )
    drop_p = _patterns(doc, "drop")

    out: Dict[str, List[str]] = {"keep": [], "structure_only": [], "exclude": [], "stub_zone": []}
    for path in paths:
        if any(fnmatch.fnmatch(path, p) for p in drop_p):
            out["exclude"].append(path)
        elif any(fnmatch.fnmatch(path, p) for p in keep_p):
            out["keep"].append(path)
        elif any(fnmatch.fnmatch(path, p) for p in so_p):
            out["structure_only"].append(path)
        elif any(fnmatch.fnmatch(path, p) for p in ex_p):
            out["exclude"].append(path)
        elif _in_stub_zone(doc, path):
            out["stub_zone"].append(path)
        else:
            out["exclude"].append(path)  # 默认剔除
    return out


def plan_export(vault_root: pathlib.Path, doc: Dict[str, Any]) -> Dict[str, Any]:
    groups = classify_paths(tracked_files(vault_root), doc)
    return {
        "keep": len(groups["keep"]),
        "structure_only": len(groups["structure_only"]),
        "excluded": len(groups["exclude"]),
        "stub_zone_files": len(groups["stub_zone"]),
        "stub_zones": [z["path"] for z in doc.get("stub_zones", [])],
        "groups": groups,
    }


def exported_targets(paths: List[str]) -> Set[str]:
    """可用于 wikilink 解析的目标集合。

    全路径（去扩展名）始终可用；**文件名形式仅在全局唯一时可用**——否则
    `[[07-Academics/该课程实验/README]]` 会因为导出集里存在别的 README.md
    而被误判为可解析，留下断链（2026-09-10 导出实测踩到）。
    """
    known: Set[str] = set()
    basename_counts: Dict[str, int] = {}
    for path in paths:
        no_ext = re.sub(r"\.(md|canvas)$", "", path, flags=re.I)
        if "/" in no_ext:
            known.add(no_ext)
        base = no_ext.rsplit("/", 1)[-1]
        basename_counts[base] = basename_counts.get(base, 0) + 1
    # 根目录文件的"全路径键"恰好等于其 basename（如 README），必须与子目录同名文件
    # 一起参与唯一性判定，否则 `[[07-Academics/该课程实验/README]]` 会被误判为可解析
    # （2026-09-10 导出实测：残留 2 处断链的根因）。
    known.update(b for b, n in basename_counts.items() if n == 1)
    return known


def repair_links(text: str, known: Set[str]) -> Tuple[str, int]:
    """把指向未导出文件的 wikilink 降级为纯文本（返回新文本与修复数）。"""
    repaired = 0

    def _sub(match: re.Match) -> str:
        nonlocal repaired
        target = match.group(2).strip()
        display = (match.group(4) or target.rsplit("/", 1)[-1]).strip()
        if target in known or target.rsplit("/", 1)[-1] in known:
            return match.group(0)
        repaired += 1
        return display

    return WIKILINK_RE.sub(_sub, text), repaired


def _route_targets_exist(route: Dict[str, Any], known_paths: Set[str]) -> bool:
    """路由目标在导出集内是否存在（含目录型目标）。"""
    rtype = route.get("type")
    if rtype == "dual":
        return all(route.get(k) in known_paths for k in ("standards", "cheatsheet"))
    if rtype in ("rule-append", "source-article"):
        if "target" in route:
            return route["target"] in known_paths
        target_dir = route.get("target_dir", "")
        return any(p.startswith(target_dir.rstrip("/") + "/") for p in known_paths)
    if rtype == "project":
        prefix = f"08-Projects/{route.get('target_project', '')}/"
        return any(p.startswith(prefix) for p in known_paths)
    return False


def prune_routing(doc: Dict[str, Any], known_paths: Set[str]) -> Tuple[Dict[str, Any], List[str]]:
    """裁掉目标已不存在的路由；返回 (新文档, 被裁路由的 tag 列表)。"""
    kept, dropped = [], []
    for route in doc.get("routes", []):
        if _route_targets_exist(route, known_paths):
            kept.append(route)
        else:
            dropped.append(route.get("tag", route.get("name", "?")))
    out = dict(doc)
    out["routes"] = kept
    return out, dropped


def prune_fallbacks(
    doc: Dict[str, Any], known_paths: Set[str]
) -> Tuple[Dict[str, Any], List[str]]:
    """fallback 目标不存在时改写为导出集内必然存在的等价目标。

    healthcheck Check 9 会校验 fallback 目标存在性；固定回退：草稿类 → `99-Inbox`
    （Landing Zone，永远存在），规则追加类 → `01-Rules/INGESTION-WORKFLOW.md`。
    """
    out = dict(doc)
    fallbacks = dict(out.get("fallback", {}))
    dropped: List[str] = []
    for key, entry in list(fallbacks.items()):
        if _route_targets_exist(entry, known_paths):
            continue
        entry = dict(entry)
        if entry.get("type") == "source-article":
            entry["target_dir"] = "99-Inbox"
        elif entry.get("type") == "rule-append":
            entry["target"] = "01-Rules/INGESTION-WORKFLOW.md"
        else:
            continue
        fallbacks[key] = entry
        dropped.append(key)
    out["fallback"] = fallbacks
    return out, dropped


def rewrite_legacy_map(source: str) -> Tuple[str, bool]:
    """把导出测试里的 LEGACY 基线清空（其内容指向已被裁剪的语言路由）。"""
    if not LEGACY_MAP_RE.search(source):
        return source, False
    new = LEGACY_MAP_RE.sub(
        r'\1{}  # 模板导出：语言路由已裁剪，基线随之清空', source, count=1
    )
    return new, True


def deidentify_text(text: str, rules: List[Dict[str, str]]) -> Tuple[str, int]:
    """按清单替换作者个人痕迹（用户名/绝对路径/私有项目名）。

    仅做字面替换，不做正则——避免误伤（例如把普通英文词拆坏）。
    """
    count = 0
    for rule in rules:
        find, repl = rule.get("find", ""), rule.get("replace", "")
        if not find:
            continue
        occurrences = text.count(find)
        if occurrences:
            text = text.replace(find, repl)
            count += occurrences
    return text, count


def _deidentify_allowed(rel: str, doc: Dict[str, Any]) -> bool:
    """按 deidentify_skip 判定该文件是否豁免去标识化（如 LICENSE 署名）。"""
    return any(
        fnmatch.fnmatch(rel, item["pattern"])
        for item in doc.get("deidentify_skip", [])
    )


_SKELETON_FM = """---
title: "{title}"
created: {today}
updated: {today}
type: notes
tags:
  - category/notes
  - topic/onboarding
status: stable
audience: both
authority: synthetic
claim_risk: none
review_status: unreviewed
---

# {title}

{body}
"""


def render_skeleton(entry: Dict[str, str], today: str) -> str:
    """按 manifest 声明渲染一个骨架笔记（frontmatter + 标题 + 正文）。"""
    return _SKELETON_FM.format(
        title=entry.get("title", entry["path"]),
        today=today,
        body=entry.get("body", "").strip(),
    )


def _read_exact(path: pathlib.Path, errors: str = "strict") -> str:
    """字节级读文本：不做 universal-newline 归一（保留 CRLF 原样）。"""
    raw = path.read_bytes()
    if b"\0" in raw[:8192]:
        raise UnicodeDecodeError("utf-8", raw[:3], 0, 1, "looks binary")
    return raw.decode("utf-8", errors=errors)


def _write_exact(path: pathlib.Path, text: str) -> None:
    """字节级写文本：newline='' 关闭翻译，字符串里是 CRLF 就落盘 CRLF。

    背景：默认 write_text 会把字符串里的每个 `\\n` 翻译成 os.linesep——
    已含 CRLF 的文本会变成 `\\r\\r\\n`（孤立 CR），曾把所有被去标识化的
    .py 全部损坏成 IndentationError（2026-09-11 公开库重建前实测抓出）。
    """
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def export_template(
    vault_root: pathlib.Path,
    out_dir: pathlib.Path,
    doc: Dict[str, Any],
    apply: bool = False,
) -> Dict[str, Any]:
    groups = classify_paths(tracked_files(vault_root), doc)
    report: Dict[str, Any] = {
        "keep": len(groups["keep"]),
        "structure_only": len(groups["structure_only"]),
        "excluded": len(groups["exclude"]),
        "stub_readmes": 0,
        "links_repaired": 0,
        "routes_pruned": [],
        "legacy_map_cleared": False,
        "applied": apply,
    }
    if not apply:
        return report

    # 1) keep 原样复制（多 Agent 入口须物化为 AGENTS.md 内容副本）
    exported: List[str] = []
    agents_text = (vault_root / "AGENTS.md").read_text(encoding="utf-8", errors="replace")
    for rel in groups["keep"]:
        src, dst = vault_root / rel, out_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if pathlib.PurePosixPath(rel).name in AGENT_ENTRY_FILES:
            # 符号链接在 Windows 上无法可靠保留（且出包/解压受权限限制），
            # 统一物化为内容副本；healthcheck Check 5 接受该降级形态。
            dst.write_text(agents_text, encoding="utf-8")
        else:
            shutil.copy2(src, dst)
        exported.append(rel)

    # 2) stub 区：生成引导 README（目录因此可见且接收者知道该填什么）
    today = subprocess.run(
        ["git", "log", "-1", "--format=%cd", "--date=short"],
        cwd=str(vault_root), capture_output=True, encoding="utf-8",
    ).stdout.strip() or "1970-01-01"
    for zone in doc.get("stub_zones", []):
        rel = f"{zone['path'].rstrip('/')}/README.md"
        dst = out_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(
            _STUB_README_TMPL.format(
                zone=zone["path"], today=today, hint=zone.get("readme_hint", "")
            ),
            encoding="utf-8",
        )
        exported.append(rel)
        report["stub_readmes"] += 1

    # 2.5) 骨架生成：structure_only 项的空壳替代（账本/审计索引/仪表盘/领域 MOC）
    report["skeletons"] = 0
    for entry in doc.get("skeleton", []):
        rel = entry["path"]
        dst = out_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(render_skeleton(entry, today), encoding="utf-8")
        exported.append(rel)
        report["skeletons"] += 1

    # 3) 路由裁剪（目标已不在导出集内的路由 + fallback MUST 一并处理）
    routing_path = out_dir / ROUTING_REL
    if routing_path.is_file():
        routing_doc = json.loads(routing_path.read_text(encoding="utf-8"))
        pruned, dropped = prune_routing(routing_doc, set(exported))
        pruned, fb_dropped = prune_fallbacks(pruned, set(exported))
        routing_path.write_text(
            json.dumps(pruned, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        report["routes_pruned"] = dropped
        report["fallbacks_rewritten"] = fb_dropped

    # 4) 清空导出测试的 LEGACY 基线
    legacy_path = out_dir / ROUTING_TEST_REL
    if legacy_path.is_file():
        new_src, changed = rewrite_legacy_map(legacy_path.read_text(encoding="utf-8"))
        if changed:
            legacy_path.write_text(new_src, encoding="utf-8")
            report["legacy_map_cleared"] = True

    # 5) 断链修复（须在 stub README 生成后，known 取最终导出集）
    #    ⚠️ 所有**改写既有文件**的步骤必须走 _read_exact/_write_exact：
    #    默认 read_text/write_text 的 universal-newline 会把 CRLF 文件写成
    #    `\r\r\n`（孤立 CR），曾把所有被去标识化的 .py 全部损坏（2026-09-11）。
    known = exported_targets(exported)
    for rel in list(exported):
        if not rel.lower().endswith(".md"):
            continue
        path = out_dir / rel
        text = _read_exact(path, errors="replace")
        repaired_text, count = repair_links(text, known)
        if count:
            _write_exact(path, repaired_text)
            report["links_repaired"] += count

    # 6) 去标识化：替换作者用户名/绝对路径/私有项目名（LICENSE 等法律文本豁免）
    #    文本判定按**可解码性**而非扩展名——无后缀文件（.githooks/pre-commit）
    #    曾因 `.suffix == ""` 被整体跳过，导致作者路径留在公开库（2026-09-11 实测）。
    rules = doc.get("deidentify", [])
    report["deidentified"] = 0

    def apply_deidentify() -> None:
        if not rules:
            return
        for rel in list(exported):
            if _deidentify_allowed(rel, doc):
                continue
            path = out_dir / rel
            raw = path.read_bytes()
            if b"\0" in raw[:8192]:  # 二进制（含 NUL）直接跳过
                continue
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                continue
            new_text, count = deidentify_text(text, rules)
            if count:
                _write_exact(path, new_text)
                report["deidentified"] += count

    apply_deidentify()

    # 7) 内容泛化：把"仅对作者领域成立"的整文件替换为通用版本，或做行级/文本级改写
    #    （README / AGENTS / Home 这类重度作者语境的入口文档用 overrides 整份替换；
    #     长尾引用用 content_rewrites 逐条收敛）
    report["overrides_applied"] = []
    for ov in doc.get("overrides", []):
        src = vault_root / ov["source"]
        if not src.is_file():
            report["detail"] = report.get("detail", []) + [f"missing override: {ov['source']}"]
            continue
        dst = out_dir / ov["path"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        _write_exact(dst, _read_exact(src))
        report["overrides_applied"].append(ov["path"])

    report["lines_dropped"] = 0
    report["texts_replaced"] = 0
    for rule in doc.get("content_rewrites", []):
        pattern = rule.get("pattern", "**/*")
        drops = rule.get("drop_line_if_contains", [])
        replaces = rule.get("replace_text", [])
        for rel in list(exported):
            if not fnmatch.fnmatch(rel, pattern):
                continue
            if _deidentify_allowed(rel, doc):
                continue  # 受保护文件（manifest / LICENSE）不参与文本改写
            path = out_dir / rel
            if not path.is_file():
                continue
            try:
                text = _read_exact(path)
            except (UnicodeDecodeError, UnicodeError):
                continue
            original = text
            if drops:
                kept = [
                    line for line in text.splitlines(keepends=True)
                    if not any(token in line for token in drops)
                ]
                report["lines_dropped"] += len(text.splitlines()) - len(kept)
                text = "".join(kept)
            for item in replaces:
                find, repl = item.get("find", ""), item.get("replace", "")
                if find and find in text:
                    report["texts_replaced"] += text.count(find)
                    text = text.replace(find, repl)
            if text != original:
                _write_exact(path, text)

    # 7.5) 去标识化**补跑**：路由表回注 / 示例重生成等步骤可能在首跑之后把
    #      含个人 token 的原始内容写回文件（2026-09-11 实测：SKILL.md 路由表
    #      在去标识化后仍出现 08-Projects/示例项目）。幂等双跑，skip 清单不变。
    apply_deidentify()

    # 8) 多 Agent 入口最终物化：必须取**修复+去标识+泛化后**的 AGENTS.md，否则内容副本
    #    与 AGENTS.md 不一致（healthcheck Check 5 content-mismatch；实测踩到）。
    #    ⚠️ 必须字节级复制：默认 write_text 会把副本写成 CRLF 而 AGENTS.md 保持 LF，
    #    healthcheck 按字节比对 → 5 个入口全部 content-mismatch（2026-09-11 实测）。
    agents_final = (out_dir / "AGENTS.md").read_bytes()
    for rel in exported:
        if pathlib.PurePosixPath(rel).name in AGENT_ENTRY_FILES:
            (out_dir / rel).write_bytes(agents_final)
    return report


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="导出领域无关知识库模板（manifest 驱动，默认 dry-run）"
    )
    parser.add_argument("--out", required=True, help="输出目录（MUST 在库外）")
    parser.add_argument("--apply", action="store_true", help="写盘（默认只打印计划）")
    parser.add_argument("--vault-root", default=None, help="库根（默认 scripts/ 父目录）")
    parser.add_argument("--manifest", default=MANIFEST_REL, help="清单路径（库内相对）")
    args = parser.parse_args(argv)

    vault_root = (
        pathlib.Path(args.vault_root).resolve()
        if args.vault_root
        else pathlib.Path(__file__).resolve().parent.parent
    )
    out_dir = pathlib.Path(args.out).resolve()
    if out_dir == vault_root or vault_root in out_dir.parents:
        print("❌ 拒绝导出到库内目录（会污染质量门与测试）；请选库外路径。", file=sys.stderr)
        return 2

    doc = load_manifest(vault_root / args.manifest)
    if not args.apply:
        plan = plan_export(vault_root, doc)
        print("=" * 68)
        print(" 📦 TEMPLATE EXPORT PLAN (dry-run)")
        print("=" * 68)
        print(f" 输出目录 : {out_dir}")
        print(f" keep                : {plan['keep']}")
        print(f" structure_only(跳过): {plan['structure_only']}")
        print(f" excluded            : {plan['excluded']}")
        print(f" stub 区内容(丢弃)   : {plan['stub_zone_files']}")
        print(f" stub 区({len(plan['stub_zones'])})      : {', '.join(plan['stub_zones'])}")
        print(" 预估包内文件 ≈ keep + stub README 数")
        return 0

    report = export_template(vault_root, out_dir, doc, apply=True)
    print(f"✅ 导出完成 → {out_dir}")
    for key in ("keep", "excluded", "stub_readmes", "links_repaired"):
        print(f"  {key}: {report[key]}")
    print(f"  routes_pruned: {report['routes_pruned']}")
    print(f"  legacy_map_cleared: {report['legacy_map_cleared']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
