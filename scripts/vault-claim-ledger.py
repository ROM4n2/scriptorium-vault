#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
Vault Claim Ledger Deriver for Coding Vault ({{VAULT_ROOT}})

ROADMAP-P4 Task-2 (#9 声明账本 + #16 来源摘要 合一) — one-way derivation
sensor. Scans every `*.md` frontmatter and derives
`11-Agents/可信度账本「自动生成」` for agent consumption and backfill tracking.

Truth-source hierarchy (STANDARDS->CHEATSHEET precedent, ADR-0001 §2/§4 #9):
frontmatter IS the truth; the ledger is a DERIVED artifact and must never be
hand-edited to "fix" the account (CLAIM-LEDGER-SCHEMA.md §6 rule 5).

Field contract (CLAIM-LEDGER-SCHEMA.md §1 — normative enums and defaults):

    authority      official|primary|secondary|community|synthetic|unknown
                   (missing -> unknown, note additionally lands in
                   stats.missing_authority)
    claim_risk     none|low|medium|high          (missing -> none)
    review_status  unreviewed|reviewed           (missing -> unreviewed)

Explicit values are kept verbatim in the ledger even when illegal, so
`--check` can flag the offending file instead of silently coercing it.

Modes
-----
* default        : derive + write the ledger file (the ONLY writing mode,
                   atomic via tmp file + os.replace)
* --dry-run      : derive + console summary, zero writes
* --json         : derive + machine-readable ledger on stdout, zero writes
* --check        : enum-legality + missing_authority report, zero writes;
                   exit 1 on (a) ANY illegal enum value or (b) an all-unknown
                   vault (「全 unknown」— ADR-0001 #9 wording contrasts
                   「全 unknown」 vs 「有非法枚举」 within one clause; SCHEMA
                   §2.2 declares unknown a legal deferred state, so a
                   PARTIALLY annotated vault stays exit 0); exit 0 otherwise.

claims extraction (SCHEMA §7 — machine-reviewable basis for claim_risk):
body lines whose text — after stripping leading markdown list/quote/heading
decorations — starts with 必须|禁止|不得|应|推荐|MUST|SHOULD|NEVER|is |is not
(case-sensitive per contract), capped at 20 lines per file. Fenced code
blocks are ignored (same convention as vault-conflict-scan.py); inline code
is naturally excluded because the prefix must start the cleaned line.

sources_summary (#16 并入): one entry per unique non-empty `source` with
note_count, max_authority (rank official>primary>secondary>community>
synthetic>unknown), reviewed_count and the deduplicated set of first-level
directories — consumed by #12 「最近来源」 without a separate CLI.

Failure semantics: unreadable files are reported on stderr and skipped;
frontmatter YAML parse failures fall back to the regex parser with a stderr
warning — zero silent swallowing.
"""

import sys

# Prevent Windows GBK stdout trap (vault-wide convention)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import argparse
import datetime
import json
import os
import pathlib
import re
from typing import Any, Iterator, Optional, Union

try:
    import yaml as _yaml
except ImportError:  # regex fallback kicks in (README dependency convention)
    _yaml = None

_SCRIPT_NAME = "scripts/vault-claim-ledger.py"
_LEDGER_DIR_NAME = "11-Agents"
_LEDGER_FILE_NAME = "可信度账本「自动生成」"
_CLAIM_LINE_LIMIT = 20

# Same exclusion convention as vault-conflict-scan.py (vault-knowledge-graph
# base set extended with `11-Agents`/`logs` per the Task-2 interface
# enumeration: the ledger itself lives in 11-Agents and agent audit logs are
# noise for trust accounting).
EXCLUDED_DIRS: set[str] = {
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
    "11-Agents",
    "logs",
}

# Root-level meta/agent instruction files are infrastructure, not knowledge
# notes — same rationale and same set as vault-knowledge-graph.py.
ROOT_INFRASTRUCTURE_FILES: set[str] = {
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

# Normative enums (CLAIM-LEDGER-SCHEMA.md §1) and default semantics.
AUTHORITY_ENUMS: frozenset[str] = frozenset(
    {"official", "primary", "secondary", "community", "synthetic", "unknown"}
)
CLAIM_RISK_ENUMS: frozenset[str] = frozenset({"none", "low", "medium", "high"})
REVIEW_STATUS_ENUMS: frozenset[str] = frozenset({"unreviewed", "reviewed"})
DEFAULT_AUTHORITY = "unknown"
DEFAULT_CLAIM_RISK = "none"
DEFAULT_REVIEW_STATUS = "unreviewed"

# Rank for max_authority in sources_summary: best (=lowest) wins; values
# outside the enum rank last so a malformed note can never outrank a judged
# one (deterministic tie-break on the value string).
_AUTHORITY_RANK: dict[str, int] = {
    "official": 0,
    "primary": 1,
    "secondary": 2,
    "community": 3,
    "synthetic": 4,
    "unknown": 5,
}

# Claim-line prefix table (SCHEMA §7), case-sensitive per contract; "is not"
# is subsumed by "is " but kept for literal spec fidelity. _LEADING_MD_RE
# strips leading markdown list markers (incl. ordered "1."/"2)"), blockquote
# and heading decorations so 「- 必须…」「> 推荐…」 match; fenced code blocks
# are skipped entirely.
_CLAIM_PREFIXES: tuple[str, ...] = (
    "必须", "禁止", "不得", "应", "推荐",
    "MUST", "SHOULD", "NEVER", "is ", "is not",
)
_LEADING_MD_RE: re.Pattern[str] = re.compile(r"^(?:[>\s#*`-]|\d+[.)\]])+")
_FENCE_TOKENS: tuple[str, ...] = ("```", "~~~")

_FRONTMATTER_RE: re.Pattern[str] = re.compile(
    r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n?", re.DOTALL
)

# Scalar fields parsed by the regex fallback (PyYAML-missing convention).
_SCALAR_KEYS: tuple[str, ...] = (
    "title", "type", "source", "authority", "claim_risk", "review_status",
)


def _split_frontmatter(text: str) -> tuple[Optional[str], str]:
    """Return (frontmatter_text_or_None, body)."""
    match = _FRONTMATTER_RE.match(text)
    if match is None:
        return None, text
    return match.group(1), text[match.end():]


def _normalize_tag_list(raw: Any) -> list[str]:
    """Coerce a frontmatter `tags` value into a clean list of strings."""
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    if isinstance(raw, str):
        return [part.strip() for part in raw.split(",") if part.strip()]
    return []


def _tags_from_regex(fm_text: str) -> list[str]:
    """Regex tags parser (block + inline styles), used by the fallback path."""
    match = re.search(r"(?m)^tags:[ \t]*(.*)$", fm_text)
    if match is None:
        return []
    inline = match.group(1).strip()
    if inline:
        if inline.startswith("[") and inline.endswith("]"):
            inline = inline[1:-1]
        return [part.strip().strip("'\"") for part in inline.split(",") if part.strip()]
    tags: list[str] = []
    # match.end() sits BEFORE the newline of the "tags:" line, so the first
    # split line is empty — skip blanks, stop at the first non-item line.
    for line in fm_text[match.end():].splitlines():
        if not line.strip():
            continue
        item = re.match(r"[ \t]+-[ \t]*(.+?)[ \t]*$", line)
        if item is None:
            break
        tags.append(item.group(1).strip("'\""))
    return tags


def _parse_fields_regex(fm_text: str) -> dict[str, Any]:
    """Regex frontmatter parser — the PyYAML-missing fallback (README
    dependency convention: 「缺失会退化为正则兜底」)."""
    fields: dict[str, Any] = {}
    for key in _SCALAR_KEYS:
        match = re.search(rf"(?m)^{key}:[ \t]*(.*)$", fm_text)
        if match is None:
            continue
        fields[key] = match.group(1).strip().strip("'\"")
    tags = _tags_from_regex(fm_text)
    if tags:
        fields["tags"] = tags
    return fields


def _parse_frontmatter(fm_text: Optional[str]) -> dict[str, Any]:
    """Parse frontmatter text into a dict: PyYAML first, regex fallback when
    missing. A YAML parse failure is reported on stderr before falling back —
    zero silent swallowing."""
    if not fm_text:
        return {}
    if _yaml is not None:
        try:
            data = _yaml.safe_load(fm_text)
        except _yaml.YAMLError as exc:
            print(
                f"vault-claim-ledger: frontmatter YAML parse failed, "
                f"falling back to regex: {exc}",
                file=sys.stderr,
            )
        else:
            return dict(data) if isinstance(data, dict) else {}
    return _parse_fields_regex(fm_text)


def _scalar(fm: dict[str, Any], key: str) -> str:
    """Single scalar field as a clean string ("" when absent/empty)."""
    value = fm.get(key)
    if value is None:
        return ""
    return str(value).strip()


def _extract_claims(
    body: str, limit: int = _CLAIM_LINE_LIMIT
) -> list[dict[str, str]]:
    """Extract normative-assertion lines from a note body (frontmatter
    excluded by the caller). Each claim is {"line": <cleaned line text>};
    at most `limit` lines per file (SCHEMA §7 cap of 20)."""
    claims: list[dict[str, str]] = []
    in_fence = False
    for raw_line in body.splitlines():
        if raw_line.lstrip().startswith(_FENCE_TOKENS):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        plain = _LEADING_MD_RE.sub("", raw_line).strip()
        if not plain or not plain.startswith(_CLAIM_PREFIXES):
            continue
        claims.append({"line": plain})
        if len(claims) >= limit:
            break
    return claims


def _build_record(rel: str, fm: dict[str, Any], body: str) -> dict[str, Any]:
    """One ledger note record: parsed fields + default semantics applied.

    `authority_missing` is an internal derivation flag (True iff the
    authority key is absent/empty from frontmatter); it drives
    stats.missing_authority and is stripped from the public files[] entries.
    """
    authority_raw = _scalar(fm, "authority")
    return {
        "rel": rel,
        "title": _scalar(fm, "title"),
        "type": _scalar(fm, "type"),
        "tags": _normalize_tag_list(fm.get("tags")),
        "source": _scalar(fm, "source") or None,
        "authority": authority_raw or DEFAULT_AUTHORITY,
        "claim_risk": _scalar(fm, "claim_risk") or DEFAULT_CLAIM_RISK,
        "review_status": _scalar(fm, "review_status") or DEFAULT_REVIEW_STATUS,
        "authority_missing": authority_raw == "",
        "claims": _extract_claims(body),
    }


def _iter_markdown_files(vault_root: pathlib.Path) -> Iterator[pathlib.Path]:
    """Yield candidate note paths, pruned by the vault exclusion convention."""
    for dirpath, dirnames, filenames in os.walk(vault_root):
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDED_DIRS)
        for name in sorted(filenames):
            if not name.endswith(".md"):
                continue
            if name in ROOT_INFRASTRUCTURE_FILES:
                continue
            yield pathlib.Path(dirpath) / name


def scan_notes(vault_root: Union[str, pathlib.Path]) -> list[dict[str, Any]]:
    """Scan the vault and return one record per markdown note (read-only).

    Walks every *.md under `vault_root` except EXCLUDED_DIRS and the root
    infrastructure files; parses the frontmatter (title/type/tags/source +
    authority/claim_risk/review_status) and mines the claim lines from the
    body. Records are sorted by POSIX relative path for deterministic output.
    Notes without frontmatter are kept with default semantics — they are
    prime missing_authority entries and the ledger must stay complete.
    """
    root = pathlib.Path(vault_root)
    records: list[dict[str, Any]] = []
    for path in _iter_markdown_files(root):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:
            print(f"vault-claim-ledger: cannot read {path}: {exc}", file=sys.stderr)
            continue
        rel_posix = str(path.relative_to(root)).replace("\\", "/")
        fm_text, body = _split_frontmatter(text)
        records.append(_build_record(rel_posix, _parse_frontmatter(fm_text), body))
    records.sort(key=lambda record: record["rel"])
    return records


def _authority_rank(value: str) -> int:
    """Rank a note's authority for max_authority; illegal values rank last."""
    return _AUTHORITY_RANK.get(value, len(_AUTHORITY_RANK))


def _derive_stats(notes: list[dict[str, Any]]) -> dict[str, Any]:
    """stats block: enum partition (illegal values increment no bucket),
    with_authority = explicitly annotated notes, missing_authority = rel
    paths whose authority field is absent (SCHEMA §1 default semantics)."""
    authority_counts = {name: 0 for name in AUTHORITY_ENUMS}
    missing_authority: list[str] = []
    with_authority = 0
    for note in notes:
        authority = note["authority"]
        if authority in authority_counts:
            authority_counts[authority] += 1
        if note["authority_missing"]:
            missing_authority.append(note["rel"])
        else:
            with_authority += 1
    return {
        "total": len(notes),
        "with_authority": with_authority,
        "official": authority_counts["official"],
        "primary": authority_counts["primary"],
        "secondary": authority_counts["secondary"],
        "community": authority_counts["community"],
        "synthetic": authority_counts["synthetic"],
        "unknown": authority_counts["unknown"],
        "missing_authority": sorted(missing_authority),
    }


def _derive_sources_summary(notes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """#16 并入: aggregate notes by their non-empty `source` — note_count,
    max_authority (authority rank, best first), reviewed_count and the
    deduplicated first-level dirs. Sorted by source name."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for note in notes:
        source = note["source"]
        if not source:
            continue
        grouped.setdefault(source, []).append(note)
    summary: list[dict[str, Any]] = []
    for source in sorted(grouped):
        members = grouped[source]
        dirs = sorted({
            note["rel"].split("/")[0] if "/" in note["rel"] else "."
            for note in members
        })
        best = min(members, key=lambda n: (_authority_rank(n["authority"]), n["authority"]))
        summary.append({
            "source": source,
            "note_count": len(members),
            "max_authority": best["authority"],
            "reviewed_count": sum(
                1 for note in members if note["review_status"] == "reviewed"
            ),
            "dirs": dirs,
        })
    return summary


def _file_entry(note: dict[str, Any]) -> dict[str, Any]:
    """Public files[] entry: the note record minus the internal flag."""
    return {key: value for key, value in note.items() if key != "authority_missing"}


def derive_ledger(
    notes: list[dict[str, Any]],
    vault_root: Optional[Union[str, pathlib.Path]] = None,
) -> dict[str, Any]:
    """Derive the claim-ledger payload from scanned notes (pure, no I/O).

    Shape (ROADMAP-P4 Task-2): {generated_at, script, vault_root, files:
    [{rel, title, type, tags, authority, claim_risk, review_status, source,
    claims:[{line}]}], sources_summary: [{source, note_count, max_authority,
    reviewed_count, dirs}], stats: {total, with_authority, official, primary,
    secondary, community, synthetic, unknown, missing_authority: []}}.
    """
    return {
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "script": _SCRIPT_NAME,
        "vault_root": _to_posix(vault_root) if vault_root else "",
        "files": [_file_entry(note) for note in notes],
        "sources_summary": _derive_sources_summary(notes),
        "stats": _derive_stats(notes),
    }


def _to_posix(value: Union[str, pathlib.Path]) -> str:
    """Path-ish value as a POSIX-style string (Windows backslash guard)."""
    return str(value).replace("\\", "/")


def _resolve_vault_root(cli_value: Optional[str]) -> pathlib.Path:
    """CLI --vault-path, or the script's parent dir when it looks like the
    vault root (AGENTS.md present), or the hardcoded default."""
    if cli_value:
        return pathlib.Path(cli_value).resolve()
    script_dir = pathlib.Path(__file__).resolve().parent
    parent = script_dir.parent
    if (parent / "AGENTS.md").exists():
        return parent
    return pathlib.Path("{{VAULT_ROOT}}").resolve()


def _ledger_path(
    vault_root: pathlib.Path, override: Optional[str]
) -> pathlib.Path:
    """Default output <vault>/11-Agents/可信度账本「自动生成」, or --override."""
    if override:
        return pathlib.Path(override)
    return vault_root / _LEDGER_DIR_NAME / _LEDGER_FILE_NAME


def _write_ledger(out_path: pathlib.Path, ledger: dict[str, Any]) -> None:
    """Atomic single-file write: tmp file + os.replace (derived artifact)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_name(out_path.name + ".tmp")
    payload = json.dumps(ledger, indent=2, ensure_ascii=False) + "\n"
    tmp_path.write_text(payload, encoding="utf-8")
    os.replace(tmp_path, out_path)


def _illegal_enum_entries(files: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Entries whose authority/claim_risk/review_status is outside the
    SCHEMA §1 enum (missing fields default to legal values, so only explicit
    bad values surface here)."""
    bad: list[dict[str, str]] = []
    for entry in files:
        checks = (
            ("authority", AUTHORITY_ENUMS),
            ("claim_risk", CLAIM_RISK_ENUMS),
            ("review_status", REVIEW_STATUS_ENUMS),
        )
        for field, enums in checks:
            value = entry[field]
            if value not in enums:
                bad.append({"rel": entry["rel"], "field": field, "value": value})
    return bad


def _run_check(ledger: dict[str, Any]) -> int:
    """--check report: enum legality + missing count; exit 1 on any illegal
    enum value or an all-unknown vault, else 0 (see module docstring)."""
    stats = ledger["stats"]
    illegal = _illegal_enum_entries(ledger["files"])
    all_unknown = stats["total"] > 0 and stats["unknown"] == stats["total"]
    print("=" * 68)
    print(" VAULT CLAIM LEDGER --check — 枚举合法性 + 回填收敛检查（只读）")
    print("=" * 68)
    print(
        f" notes={stats['total']} with_authority={stats['with_authority']} "
        f"missing={len(stats['missing_authority'])}"
    )
    print(f" 非法枚举条目: {len(illegal)}")
    for item in illegal:
        print(f"   - {item['rel']}: {item['field']}={item['value']!r} 不在合法枚举内")
    if illegal:
        print(" 结论: 存在非法枚举值 -> exit 1")
    elif all_unknown:
        print(" 结论: 全库 unknown（尚无任何 authority 标注）-> exit 1")
    else:
        print(" 结论: OK -> exit 0")
    return 1 if (illegal or all_unknown) else 0


def _print_summary(
    ledger: dict[str, Any], out_path: pathlib.Path, wrote: bool
) -> None:
    """Console summary for the default and --dry-run modes."""
    stats = ledger["stats"]
    print("=" * 68)
    print(" VAULT CLAIM LEDGER — 声明账本单向派生（frontmatter 真值 -> 账本）")
    print("=" * 68)
    print(f" Vault           : {ledger['vault_root']}")
    print(f" 笔记总数         : {stats['total']}")
    print(
        f" authority 标注  : {stats['with_authority']} 已标注 / "
        f"{len(stats['missing_authority'])} 缺失"
    )
    print(f" source 摘要(#16): {len(ledger['sources_summary'])} 个唯一来源")
    if wrote:
        print(f" 已写入          : {_to_posix(out_path)}")
    else:
        print(f" DRY-RUN 不写盘   （目标将为: {_to_posix(out_path)}）")
    print(" 加 --json 获取机器可读账本；--check 校验枚举与回填收敛。")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Vault 声明账本派生器（#9+#16 合一）：扫描全库 md frontmatter，"
            "单向派生 11-Agents/可信度账本「自动生成」；--dry-run/--json/--check 只读"
        )
    )
    parser.add_argument(
        "--vault-path", type=str, default=None, help="Root path of the Obsidian vault"
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Override ledger output path (default: <vault>/11-Agents/可信度账本「自动生成」)",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Print the machine-readable ledger JSON to stdout (read-only)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Derive and summarize but never write the ledger file",
    )
    parser.add_argument(
        "--check", action="store_true",
        help=(
            "Enum legality + missing count report (read-only); "
            "exit 1 on illegal enums or an all-unknown vault"
        ),
    )
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    vault_root = _resolve_vault_root(args.vault_path)
    notes = scan_notes(vault_root)
    ledger = derive_ledger(notes, vault_root=vault_root)
    if args.check:  # --check wins over output flags; strictly read-only
        sys.exit(_run_check(ledger))
    if args.json:  # stdout schema report, strictly read-only
        print(json.dumps(ledger, indent=2, ensure_ascii=False))
        sys.exit(0)
    out_path = _ledger_path(vault_root, args.output)
    if args.dry_run:  # derive + summarize, zero writes
        _print_summary(ledger, out_path, wrote=False)
        sys.exit(0)
    _write_ledger(out_path, ledger)  # the ONLY writing mode
    _print_summary(ledger, out_path, wrote=True)
    sys.exit(0)


if __name__ == "__main__":
    main()
