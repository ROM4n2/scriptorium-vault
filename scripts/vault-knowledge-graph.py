#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
Vault Knowledge Graph Canvas Generator for Coding Vault ({{VAULT_ROOT}})

Features:
  1. Parse all notes and extract wikilinks to construct node/edge graph.
  2. Arrange nodes in a 2D clustered grid layout with visual category groups and color palettes:
     - 00-MOC: Purple (6)
     - 01-Rules: Red (1)
     - 02-Fundamentals: Purple (6)
     - 03-Languages: Green (4)
     - 04-Systems: Cyan (5)
     - 05-Tools: Cyan (5)
     - 06-Sources: Yellow (3)
     - 07-Academics: Yellow (3)
     - 08-Projects: Orange (2)
     - 09-Career: Orange (2)
     - 10-Daily: Purple (6)
     - 11-Agents: Purple (6)
     - 99-Inbox: Yellow (3)
  3. Connect directed canvas edges based on [[...]] wikilinks with directional arrows (toEnd: "arrow").
  4. Generate valid Obsidian JSON Canvas file: `00-MOC/知识图谱白板（自动生成）`.
     Writing is opt-out: a bare invocation writes (backward compatible), while
     `--json` / `--dry-run` are read-only reporting modes and `--write` / `--apply`
     force the write back on. Read-only modes exist so this generator can be used
     as a CI verification command without dirtying the working tree.
  5. Include UTF-8 stdout protection and exit code 0.
  6. Persist a normalized graph-state snapshot (`00-MOC/.graph-state.json`, see
     `save_graph_state`) on every write run and, with `--diff`, report the
     added/removed nodes and edges versus the previous snapshot — human-readable
     on stdout, or merged into the JSON payload under `--json --diff` for
     nightly/dashboard consumption. Read-only modes (`--json` / `--dry-run`)
     report the diff but never write the canvas OR the state (hermeticity).
"""

import sys

# Prevent Windows GBK stdout trap
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import argparse
import datetime
import hashlib
import json
import os
import pathlib
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

EXCLUDED_DIRS: Set[str] = {
    ".git",
    ".obsidian",
    ".claudian",
    ".smart-env",
    ".agents",
    ".opencode",
    ".claude",
    ".githooks",
    ".codebuddy",
    "node_modules",
    "scripts",
    "copilot",
    "Templates",
    ".trash",
}

ROOT_INFRASTRUCTURE_FILES: Set[str] = {
    "AGENTS.md",
    "README.md",
    "项目档案.md",
    "项目档案-V2.md",
    "MULTI-AGENT-LIMITATIONS-AND-RISKS.md",
    "PHASE4-IMPLEMENTATION-PLAN.md",
    "PHASE5-VALIDATION-PLAN.md",
    "PHASE6-AUTOMATION-PLAN.md",
    "CLAUDE.md",
    "GEMINI.md",
    "CONVENTIONS.md",
    ".cursorrules",
    ".windsurfrules",
}

CATEGORY_CONFIG: Dict[str, Dict[str, Any]] = {
    "00-MOC": {
        "label": "🧭 00-MOC 知识导航枢纽",
        "color": "6",
        "col": 0,
        "order": 1,
    },
    "01-Rules": {
        "label": "📐 01-Rules 通用工程规范",
        "color": "1",
        "col": 1,
        "order": 2,
    },
    "02-Fundamentals": {
        "label": "🔬 02-Fundamentals 计算机基础",
        "color": "6",
        "col": 2,
        "order": 3,
    },
    "03-Languages": {
        "label": "💻 03-Languages 语言技术规范",
        "color": "4",
        "col": 2,
        "order": 4,
    },
    "04-Systems": {
        "label": "🏗️ 04-Systems 系统与中间件",
        "color": "5",
        "col": 3,
        "order": 5,
    },
    "05-Tools": {
        "label": "🛠️ 05-Tools 工具与 Agent 技能",
        "color": "5",
        "col": 3,
        "order": 6,
    },
    "06-Sources": {
        "label": "📚 06-Sources 权威知识输入源",
        "color": "3",
        "col": 4,
        "order": 7,
    },
    "07-Academics": {
        "label": "🎓 07-Academics 课程实验与毕设",
        "color": "3",
        "col": 4,
        "order": 8,
    },
    "08-Projects": {
        "label": "📦 08-Projects 工程项目约束",
        "color": "2",
        "col": 5,
        "order": 9,
    },
    "09-Career": {
        "label": "🎯 09-Career 求职面试与高频考点",
        "color": "2",
        "col": 5,
        "order": 10,
    },
    "10-Daily": {
        "label": "🗓️ 10-Daily 个人日常日志",
        "color": "6",
        "col": 6,
        "order": 11,
    },
    "99-Inbox": {
        "label": "📥 99-Inbox 待加工草稿区",
        "color": "3",
        "col": 6,
        "order": 12,
    },
    "11-Agents": {
        "label": "🤖 11-Agents 审计与验证日志",
        "color": "6",
        "col": 6,
        "order": 13,
    },
    "Root": {
        "label": "🏛️ 根级架构与顶层定义",
        "color": "5",
        "col": 0,
        "order": 0,
    },
}


def clean_link_target(raw: str) -> str:
    raw = raw.strip()
    if "\\|" in raw:
        raw = raw.split("\\|")[0]
    elif "|" in raw:
        raw = raw.split("|")[0]
    if "#" in raw:
        raw = raw.split("#")[0]
    return raw.strip().rstrip("\\").rstrip("/")


def extract_wikilinks(content: str) -> List[str]:
    wikilink_pattern = re.compile(r"\[\[([^\]]+)\]\]")
    inline_code_pattern = re.compile(r"`[^`\n]+`")
    links: List[str] = []

    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if fm_match:
        for m in wikilink_pattern.finditer(fm_match.group(1)):
            cleaned = clean_link_target(m.group(1))
            if cleaned:
                links.append(cleaned)
        body = content[fm_match.end():]
    else:
        body = content

    in_code_block = False
    for line in body.splitlines():
        trimmed = line.strip()
        if trimmed.startswith("```") or trimmed.startswith("~~~"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue
        clean_line = inline_code_pattern.sub("", line)
        for m in wikilink_pattern.finditer(clean_line):
            cleaned = clean_link_target(m.group(1))
            if cleaned:
                links.append(cleaned)

    return links


def make_node_id(rel_path: str) -> str:
    r"""Deterministic node id that NEVER truncates away its md5 tail.

    The trailing ``_<md5[:6]>`` is the collision guard: two distinct paths
    hash differently, so their ids differ in the last 6 chars. The sanitized
    path prefix is capped at 28 chars because ``node_`` (5) + prefix (28) +
    ``_`` (1) + hash (6) caps the full id at exactly 40 chars — the old
    ``f"node_{clean}_{h}"[:40]`` slice instead chopped the hash off any path
    whose sanitized prefix reached 35+ chars, collapsing e.g. the seven
    ROADMAP-P*.md notes onto a single node id.
    """
    clean = re.sub(r"[^a-zA-Z0-9_]", "_", rel_path).lower().strip("_")
    h = hashlib.md5(rel_path.encode("utf-8")).hexdigest()[:6]
    return f"node_{clean[:28]}_{h}"


def determine_category(rel_posix: str) -> str:
    parts = rel_posix.split("/")
    if len(parts) > 1:
        top = parts[0]
        if top in CATEGORY_CONFIG:
            return top
    return "Root"


def compute_side_attachment(
    src_x: int, src_y: int, src_w: int, src_h: int,
    tgt_x: int, tgt_y: int, tgt_w: int, tgt_h: int
) -> Tuple[str, str]:
    src_cx = src_x + src_w // 2
    src_cy = src_y + src_h // 2
    tgt_cx = tgt_x + tgt_w // 2
    tgt_cy = tgt_y + tgt_h // 2

    dx = tgt_cx - src_cx
    dy = tgt_cy - src_cy

    if abs(dx) >= abs(dy):
        return ("right", "left") if dx >= 0 else ("left", "right")
    else:
        return ("bottom", "top") if dy >= 0 else ("top", "bottom")


def _atomic_write_json(target: pathlib.Path, payload: Dict[str, Any]) -> None:
    """Serialise *payload* to *target* atomically.

    The single filesystem-mutating idiom of this module, shared by
    ``write_canvas`` and ``save_graph_state``. Write order: serialise into a
    same-directory ``<name>.tmp`` first, then move it onto the target with
    ``os.replace`` (atomic on POSIX and on Windows for same-volume renames). A
    crash mid-write therefore leaves either the previous file intact or a stray
    ``.tmp`` — never a half-written JSON file, which Obsidian would silently
    fail to open.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    json_str = json.dumps(payload, indent=2, ensure_ascii=False)
    tmp_path = target.parent / (target.name + ".tmp")
    tmp_path.write_text(json_str, encoding="utf-8")
    os.replace(tmp_path, target)


def write_canvas(output_path: pathlib.Path, canvas_data: Dict[str, Any]) -> None:
    """Serialise the canvas to disk atomically (via ``_atomic_write_json``).

    Keeping the canvas write behind this named seam is what lets
    ``generate_canvas`` be driven in a read-only mode without duplicating logic.
    """
    _atomic_write_json(output_path, canvas_data)


def build_graph_state(
    canvas_nodes: List[Dict[str, Any]],
    canvas_edges: List[Dict[str, Any]],
    vault_root: pathlib.Path,
) -> Dict[str, Any]:
    """Build the normalized graph-state snapshot dict (pure — no I/O).

    Schema (ROADMAP-P2 Task-1):

    * ``generated_at`` — UTC ISO-8601 timestamp of this run;
    * ``vault_root``   — resolved vault root, POSIX slashes;
    * ``node_ids``     — sorted ids of *file* nodes only: group nodes are layout
      scaffolding whose ids would add diff noise without knowledge meaning;
    * ``edges``        — sorted ``"src_id→tgt_id"`` strings; sequential edge ids
      are meaningless for diffing, so pairs are normalized instead;
    * ``counts``       — ``{"nodes": n, "edges": m}``.

    ``diff_graph_states`` consumes exactly this shape; snapshots persisted by
    ``save_graph_state`` are compatible by construction.
    """
    node_ids: List[str] = sorted(
        node["id"] for node in canvas_nodes if node.get("type") == "file"
    )
    edge_pairs: List[str] = sorted(
        f'{edge["fromNode"]}→{edge["toNode"]}' for edge in canvas_edges
    )
    return {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "vault_root": str(vault_root).replace("\\", "/"),
        "node_ids": node_ids,
        "edges": edge_pairs,
        "counts": {"nodes": len(node_ids), "edges": len(edge_pairs)},
    }


def save_graph_state(
    output_state: pathlib.Path,
    canvas_nodes: List[Dict[str, Any]],
    canvas_edges: List[Dict[str, Any]],
    vault_root: pathlib.Path,
) -> None:
    """Atomically persist ``build_graph_state(...)`` at *output_state*.

    Invoked only when the run actually writes (``resolve_should_write``); the
    read-only modes never touch the snapshot (hermeticity iron law).
    """
    _atomic_write_json(
        output_state, build_graph_state(canvas_nodes, canvas_edges, vault_root)
    )


def load_graph_state(state_path: pathlib.Path) -> Optional[Dict[str, Any]]:
    """Read a previously persisted snapshot; ``None`` when absent (first run).

    A *present but corrupt* file is never silently treated as "first run" —
    that would mask a torn or hand-edited snapshot as a clean baseline (zero
    silent-swallowing rule); it exits loudly with a diagnosable message.
    """
    if not state_path.exists():
        return None
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"vault-knowledge-graph: corrupt state file {state_path}: {exc}"
        )


def diff_graph_states(
    prev: Dict[str, Any], cur: Dict[str, Any]
) -> Dict[str, List[str]]:
    """Set-difference two snapshots into sorted added/removed lists.

    Returns ``{added_nodes, removed_nodes, added_edges, removed_edges}``. Both
    sides are read defensively (missing keys count as empty), which is what
    lets the CLI feed an empty baseline for the first-run case.
    """
    prev_nodes = set(prev.get("node_ids") or [])
    cur_nodes = set(cur.get("node_ids") or [])
    prev_edges = set(prev.get("edges") or [])
    cur_edges = set(cur.get("edges") or [])
    return {
        "added_nodes": sorted(cur_nodes - prev_nodes),
        "removed_nodes": sorted(prev_nodes - cur_nodes),
        "added_edges": sorted(cur_edges - prev_edges),
        "removed_edges": sorted(prev_edges - cur_edges),
    }


def _print_human_diff(report: Dict[str, Any]) -> None:
    """Render a diff report as the human-readable stdout section."""
    print("-" * 68)
    if report["first_run"]:
        print(" 🆕 First run — 未找到历史 state，本次全量视为新增。")
        return
    print(" 🔍 GRAPH DIFF (vs 上次 .graph-state.json)")
    print(f"   ➕ 新增节点 : {len(report['added_nodes'])} 个")
    for node_id in report["added_nodes"]:
        print(f"       + {node_id}")
    print(f"   ➖ 移除节点 : {len(report['removed_nodes'])} 个")
    for node_id in report["removed_nodes"]:
        print(f"       - {node_id}")
    print(f"   🔗 新增链接 : {len(report['added_edges'])} 条")
    for pair in report["added_edges"]:
        print(f"       + {pair}")
    print(f"   ✂️  移除链接 : {len(report['removed_edges'])} 条")
    for pair in report["removed_edges"]:
        print(f"       - {pair}")


def generate_canvas(
    vault_root: pathlib.Path,
    output_path: pathlib.Path,
    include_groups: bool = True,
    write: bool = True,
) -> Dict[str, Any]:
    notes: List[Tuple[pathlib.Path, str]] = []
    rel_to_id: Dict[str, str] = {}
    stem_to_rel: Dict[str, str] = {}
    posix_to_rel: Dict[str, str] = {}

    for root, _, filenames in os.walk(vault_root):
        root_p = pathlib.Path(root)
        if any(p in root_p.parts for p in EXCLUDED_DIRS):
            continue
        for f in filenames:
            if f.endswith(".md") and f not in ROOT_INFRASTRUCTURE_FILES:
                fp = root_p / f
                rel_posix = str(fp.relative_to(vault_root)).replace("\\", "/")
                notes.append((fp, rel_posix))
                node_id = make_node_id(rel_posix)
                rel_to_id[rel_posix] = node_id
                posix_to_rel[rel_posix] = rel_posix
                posix_to_rel[rel_posix[:-3]] = rel_posix
                stem_to_rel[fp.stem] = rel_posix
                stem_to_rel[fp.name] = rel_posix

    notes.sort(key=lambda x: x[1])

    category_notes: Dict[str, List[Tuple[pathlib.Path, str]]] = defaultdict(list)
    for path_obj, rel_posix in notes:
        cat = determine_category(rel_posix)
        category_notes[cat].append((path_obj, rel_posix))

    columns_map: Dict[int, List[str]] = defaultdict(list)
    for cat in CATEGORY_CONFIG.keys():
        if cat in category_notes and category_notes[cat]:
            col_idx = CATEGORY_CONFIG[cat]["col"]
            columns_map[col_idx].append(cat)

    for col_idx in columns_map:
        columns_map[col_idx].sort(key=lambda c: CATEGORY_CONFIG[c]["order"])

    canvas_nodes: List[Dict[str, Any]] = []
    canvas_edges: List[Dict[str, Any]] = []
    node_positions: Dict[str, Dict[str, int]] = {}

    NOTE_W = 280
    NOTE_H = 110
    PAD_X = 30
    PAD_TOP = 60
    PAD_BOTTOM = 30
    GAP_X = 30
    GAP_Y = 25
    COL_BASE_X = -1800
    COL_WIDTH = 700
    COL_GAP = 80
    GROUP_VERTICAL_GAP = 60

    for col_idx in sorted(columns_map.keys()):
        current_x = COL_BASE_X + col_idx * (COL_WIDTH + COL_GAP)
        current_y = -600

        for cat in columns_map[col_idx]:
            notes_in_cat = category_notes[cat]
            cat_cfg = CATEGORY_CONFIG[cat]
            cat_color = cat_cfg["color"]
            num_notes = len(notes_in_cat)

            num_cols_in_group = 2 if num_notes >= 4 else 1
            num_rows_in_group = (num_notes + num_cols_in_group - 1) // num_cols_in_group if num_notes > 0 else 1

            group_w = PAD_X * 2 + num_cols_in_group * NOTE_W + (num_cols_in_group - 1) * GAP_X
            group_h = PAD_TOP + PAD_BOTTOM + num_rows_in_group * NOTE_H + max(0, num_rows_in_group - 1) * GAP_Y

            group_id = f"group_{cat.lower().replace('-', '_')}"

            if include_groups:
                canvas_nodes.append({
                    "id": group_id,
                    "type": "group",
                    "label": f"{cat_cfg['label']} ({num_notes} 篇)",
                    "x": current_x,
                    "y": current_y,
                    "width": group_w,
                    "height": group_h,
                    "color": cat_color,
                })

            for idx, (p, rel_posix) in enumerate(notes_in_cat):
                c_idx = idx % num_cols_in_group
                r_idx = idx // num_cols_in_group

                nx = current_x + PAD_X + c_idx * (NOTE_W + GAP_X)
                ny = current_y + PAD_TOP + r_idx * (NOTE_H + GAP_Y)

                node_id = rel_to_id[rel_posix]
                node_positions[node_id] = {
                    "x": nx, "y": ny, "width": NOTE_W, "height": NOTE_H
                }

                canvas_nodes.append({
                    "id": node_id,
                    "type": "file",
                    "file": rel_posix,
                    "x": nx,
                    "y": ny,
                    "width": NOTE_W,
                    "height": NOTE_H,
                    "color": cat_color,
                })

            current_y += group_h + GROUP_VERTICAL_GAP

    def resolve_target(src_rel: str, raw_target: str) -> Optional[str]:
        target_posix = raw_target.replace("\\", "/").rstrip("/")
        if target_posix in posix_to_rel:
            return posix_to_rel[target_posix]
        if (target_posix + ".md") in posix_to_rel:
            return posix_to_rel[target_posix + ".md"]
        src_parent = str(pathlib.PurePosixPath(src_rel).parent)
        if src_parent != ".":
            rel_cand = f"{src_parent}/{target_posix}"
            if rel_cand in posix_to_rel:
                return posix_to_rel[rel_cand]
            if (rel_cand + ".md") in posix_to_rel:
                return posix_to_rel[rel_cand + ".md"]
        stem = pathlib.PurePosixPath(target_posix).stem
        if stem in stem_to_rel:
            return stem_to_rel[stem]
        return None

    edge_idx = 1
    seen_edges: Set[Tuple[str, str]] = set()

    for p, src_rel in notes:
        src_node_id = rel_to_id.get(src_rel)
        if not src_node_id or src_node_id not in node_positions:
            continue

        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        links = extract_wikilinks(content)
        for raw_target in links:
            if "{{" in raw_target or raw_target in ("...", "..", "目录/文件名", ""):
                continue

            tgt_rel = resolve_target(src_rel, raw_target)
            if tgt_rel and tgt_rel != src_rel and tgt_rel in rel_to_id:
                tgt_node_id = rel_to_id[tgt_rel]
                if tgt_node_id in node_positions:
                    edge_pair = (src_node_id, tgt_node_id)
                    if edge_pair in seen_edges:
                        continue
                    seen_edges.add(edge_pair)

                    src_pos = node_positions[src_node_id]
                    tgt_pos = node_positions[tgt_node_id]

                    from_side, to_side = compute_side_attachment(
                        src_pos["x"], src_pos["y"], src_pos["width"], src_pos["height"],
                        tgt_pos["x"], tgt_pos["y"], tgt_pos["width"], tgt_pos["height"],
                    )

                    src_cat = determine_category(src_rel)
                    edge_color = CATEGORY_CONFIG[src_cat]["color"]

                    canvas_edges.append({
                        "id": f"edge_{edge_idx}",
                        "fromNode": src_node_id,
                        "fromSide": from_side,
                        "toNode": tgt_node_id,
                        "toSide": to_side,
                        "toEnd": "arrow",
                        "color": edge_color,
                    })
                    edge_idx += 1

    canvas_data = {"nodes": canvas_nodes, "edges": canvas_edges}
    if write:
        write_canvas(output_path, canvas_data)

    file_nodes = [n for n in canvas_nodes if n.get("type") == "file"]
    group_nodes = [n for n in canvas_nodes if n.get("type") == "group"]

    return {
        "output": str(output_path).replace("\\", "/"),
        "written": write,
        "total_nodes": len(canvas_nodes),
        "file_nodes_count": len(file_nodes),
        "group_nodes_count": len(group_nodes),
        "edges_count": len(canvas_edges),
        # Exposed for the graph-state snapshot (P2 Task-1). main() pops these
        # before printing, so the --json stdout payload keeps the counts-only
        # contract pinned by test_graph_nowrite.py.
        "_canvas_nodes": canvas_nodes,
        "_canvas_edges": canvas_edges,
    }


def resolve_should_write(write: bool, dry_run: bool, as_json: bool) -> bool:
    """Decide whether the canvas is persisted.

    Precedence, highest first:
      1. `--write` / `--apply` — explicit opt-in, wins over every read-only hint.
      2. `--dry-run` or `--json` — read-only reporting modes.
      3. bare invocation — writes, preserving the behaviour every doc describes.

    `--write` together with `--dry-run` is a contradiction and is rejected by the
    caller before reaching here, so this function never has to guess.
    """
    if write:
        return True
    if dry_run or as_json:
        return False
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Obsidian Canvas Knowledge Graph")
    parser.add_argument("--output", type=str, default=None, help="Output .canvas file path")
    parser.add_argument("--vault-path", type=str, default=None, help="Root path of the Obsidian vault")
    parser.add_argument("--no-groups", action="store_true", help="Do not generate visual category groups")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON summary (read-only: does not write the canvas)")
    # NOTE: unlike vault-auto-linker.py, --dry-run is NOT default=True here. This
    # generator writes on a bare invocation for backward compatibility, so a
    # default of True would make --help state the opposite of what happens.
    parser.add_argument("--dry-run", action="store_true", help="Report only; do not write the canvas file")
    parser.add_argument("--write", "--apply", dest="write", action="store_true", help="Write the canvas file (overrides the read-only default of --json)")
    parser.add_argument(
        "--state-path",
        type=str,
        default=None,
        help="Graph-state snapshot JSON path (default: <vault>/00-MOC/.graph-state.json)",
    )
    parser.add_argument(
        "--diff",
        action="store_true",
        help=(
            "Compare the generated graph against the previous state snapshot and "
            "report added/removed nodes and edges (human-readable; merged into "
            "the JSON payload under --json --diff). Read-only modes report the "
            "diff but never write the state."
        ),
    )
    args = parser.parse_args()

    if args.write and args.dry_run:
        parser.error("--write and --dry-run are mutually exclusive")

    if args.vault_path:
        vault_root = pathlib.Path(args.vault_path).resolve()
    else:
        script_dir = pathlib.Path(__file__).resolve().parent
        vault_root = script_dir.parent if (script_dir.parent / "AGENTS.md").exists() else pathlib.Path("{{VAULT_ROOT}}").resolve()

    output_path = pathlib.Path(args.output).resolve() if args.output else (vault_root / "00-MOC" / "知识图谱白板（自动生成）")
    state_path = (
        pathlib.Path(args.state_path).resolve()
        if args.state_path
        else (vault_root / "00-MOC" / ".graph-state.json")
    )
    should_write = resolve_should_write(args.write, args.dry_run, args.json)

    # Diff (P2 Task-1): read the previous snapshot BEFORE generating, so the
    # report compares old vs current — never new vs new.
    prev_state = load_graph_state(state_path) if args.diff else None

    res = generate_canvas(vault_root, output_path, include_groups=not args.no_groups, write=should_write)
    canvas_nodes: List[Dict[str, Any]] = res.pop("_canvas_nodes")
    canvas_edges: List[Dict[str, Any]] = res.pop("_canvas_edges")

    diff_report: Optional[Dict[str, Any]] = None
    if args.diff:
        first_run = prev_state is None
        cur_state = build_graph_state(canvas_nodes, canvas_edges, vault_root)
        baseline = prev_state if prev_state is not None else {"node_ids": [], "edges": []}
        diff_report = diff_graph_states(baseline, cur_state)
        diff_report["first_run"] = first_run

    # The state snapshot is persisted iff the run actually writes — never in
    # the read-only --json/--dry-run modes (hermeticity iron law, pinned by
    # test_graph_state_diff.py).
    if should_write:
        save_graph_state(state_path, canvas_nodes, canvas_edges, vault_root)

    if args.json:
        if diff_report is not None:
            res["diff"] = diff_report
        print(json.dumps(res, indent=2, ensure_ascii=False))
        sys.exit(0)

    print("\n" + "=" * 68)
    print(" 🎨 OBSIDIAN CANVAS KNOWLEDGE GRAPH GENERATOR")
    print("=" * 68)
    print(f" 📂 Canvas 输出 : {res['output']}")
    print(f" 📄 文件笔记节点 : {res['file_nodes_count']} 个 (带分类色彩)")
    print(f" 🗂️ 架构集群分组 : {res['group_nodes_count']} 组")
    print(f" 🔗 拓扑引用连线 : {res['edges_count']} 条 (带方向箭头)")
    print("-" * 68)
    if res["written"]:
        print(" ✅ Canvas 全景可视化文件已成功生成！可在 Obsidian 中直接打开体验。")
    else:
        print(" ℹ️  Dry run — 未写入任何文件。加 `--write` 或 `--apply` 才会生成 Canvas。")
    if diff_report is not None:
        _print_human_diff(diff_report)
    print("=" * 68 + "\n")

    sys.exit(0)


if __name__ == "__main__":
    main()
