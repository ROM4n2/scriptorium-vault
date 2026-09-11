#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
Vault Claim Backfill for Coding Vault ({{VAULT_ROOT}})

ROADMAP-P4 Task-4 (#16 全库三步回填 step 2/3) — batch frontmatter backfill of
the three trust fields (authority / claim_risk / review_status) defined by
CLAIM-LEDGER-SCHEMA.md, driven by the CALIBRATION mapping
(08-Projects/项目档案/CLAIM-LEDGER-CALIBRATION.md §2, priorities S1-S15/F1).

Invariants (ROADMAP-P4 Task-4 constraints):
* ADD-ONLY: missing fields are inserted immediately before the closing `---`
  of the frontmatter; pre-existing fields and every other byte round-trip
  unchanged (text-level insertion — the frontmatter is never re-serialized).
* `updated` is never rewritten (avoids vault-wide fake diffs).
* Files without frontmatter are skipped and never gain an empty `---` head.
* All writes go through the P1 VaultTransaction (full vault -> commit, or a
  deterministic rollback); `--dry-run` (default) is strictly read-only.
* Dotfiles (`.tmp-*` briefs, `.agent-context.md`, ...) are never touched.

Mapping note: S5 (community by `source-type: article` + `source-author`)
is frontmatter-driven per CALIBRATION §3 item 1, not directory-driven.

Failure semantics: undecodable/unreadable files are reported on stderr and
skipped — zero silent swallowing.
"""

import sys

# Prevent Windows GBK stdout trap (vault-wide convention)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import argparse
import datetime
import hashlib
import importlib.util
import pathlib
import re
from typing import Any, Callable, Optional, Union

from vault_transaction import TransactionError, VaultTransaction

_SCRIPT_NAME = "scripts/vault-claim-backfill.py"
_FIELDS = ("authority", "claim_risk", "review_status")
_KEY_LINE_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_-]*)\s*:")


def _load_ledger_module() -> Any:
    """Load vault-claim-ledger.py (hyphenated filename) to REUSE its vault
    walk exclusions and frontmatter splitting — one scan convention for the
    whole P4 toolchain (deriver and backfiller must see the same file set)."""
    script_path = pathlib.Path(__file__).resolve().parent / "vault-claim-ledger.py"
    spec = importlib.util.spec_from_file_location("vault_claim_ledger", script_path)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:  # pragma: no cover - defensive
        raise ImportError(f"cannot load ledger module from {script_path}")
    spec.loader.exec_module(module)
    return module


_LEDGER = _load_ledger_module()


def classify(rel_posix: str, meta: dict[str, Any]) -> tuple[str, str]:
    """Default CALIBRATION mapping (S1-S15/F1, priority order).

    Returns (authority, claim_risk). review_status is always unreviewed.
    """
    # S5 — frontmatter-driven community rule (any directory)
    if meta.get("source-type") == "article" and meta.get("source-author"):
        return ("community", "low")
    if rel_posix.startswith("06-Sources/Books/"):                       # S1
        return ("primary", "medium")
    if rel_posix.startswith("06-Sources/Papers/"):                      # S2
        return ("primary", "medium")
    if rel_posix.startswith("06-Sources/Articles/"):                    # S3/S4
        title = str(meta.get("title", ""))
        tags = meta.get("tags") or []
        if "索引" in title or "category/moc" in tags:
            return ("secondary", "low")
        return ("secondary", "medium")
    if rel_posix.startswith("03-Languages/") and rel_posix.endswith(
        "-CHEATSHEET.md"
    ):                                                                  # S6
        return ("synthetic", "low")
    if rel_posix.startswith("03-Languages/") and rel_posix.endswith(
        "-STANDARDS.md"
    ):                                                                  # S7
        return ("synthetic", "high")
    if rel_posix.startswith("01-Rules/"):                               # S8
        return ("synthetic", "high")
    basename = rel_posix.rsplit("/", 1)[-1]
    if (
        rel_posix.startswith("00-MOC/")
        or basename == "README.md"
        or meta.get("type") == "moc"
    ):                                                                  # S9
        return ("synthetic", "none")
    if rel_posix.startswith("08-Projects/"):                            # S10
        return ("synthetic", "medium")
    if rel_posix.startswith("09-Career/"):                              # S11
        return ("synthetic", "medium")
    if rel_posix.startswith("04-Systems/"):                             # S12
        return ("synthetic", "medium")
    if rel_posix.startswith("05-Tools/"):                               # S13
        return ("synthetic", "medium")
    if rel_posix.startswith("10-Daily/"):                               # S14
        return ("unknown", "none")
    if rel_posix.startswith("99-Inbox/"):                               # S15
        return ("unknown", "none")
    return ("unknown", "none")                                          # F1


def _split_frontmatter_raw(raw: str) -> Optional[tuple[list[str], int, str]]:
    """Split raw text into frontmatter lines and locate the closing delimiter.

    Returns (fm_lines, closing_index_in_split_lines, eol) or None when the
    file has no well-formed frontmatter (no empty `---` heads are produced).
    """
    eol = "\r\n" if "\r\n" in raw else "\n"
    lines = raw.split(eol)
    if not lines or lines[0].strip() != "---":
        return None
    closing: Optional[int] = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            closing = index
            break
    if closing is None:
        return None
    return lines[1:closing], closing, eol


def _existing_keys(fm_lines: list[str]) -> set[str]:
    keys: set[str] = set()
    for line in fm_lines:
        match = _KEY_LINE_RE.match(line)
        if match:
            keys.add(match.group(1))
    return keys


def _insert_fields(raw: str, adds: dict[str, str]) -> Optional[str]:
    """Text-level ADD-ONLY insertion before the closing `---`.

    Returns the new text, or None when nothing needs to be added (idempotent)
    or the file lacks well-formed frontmatter.
    """
    split = _split_frontmatter_raw(raw)
    if split is None:
        return None
    fm_lines, closing, eol = split
    existing = _existing_keys(fm_lines)
    insert = [f"{key}: {adds[key]}" for key in _FIELDS if key in adds and key not in existing]
    if not insert:
        return None
    lines = raw.split(eol)
    # recompute the closing index on the full line list (fm starts at index 1)
    full_closing = closing  # closing index is identical in the full list
    new_lines = lines[:full_closing] + insert + lines[full_closing:]
    return eol.join(new_lines)


def plan_backfill(
    vault_root: Union[str, pathlib.Path],
    mapping: Optional[Callable[[str, dict[str, Any]], tuple[str, str]]] = None,
) -> list[dict[str, Any]]:
    """Read-only backfill plan: one entry per note missing any of the three
    fields. Entries: {rel, path, adds: {field: value}} sorted by rel."""
    root = pathlib.Path(vault_root)
    judge = mapping or classify
    plan: list[dict[str, Any]] = []
    for path in _LEDGER._iter_markdown_files(root):
        if path.name.startswith("."):
            continue  # dotfiles (agent briefs/tooling) are never backfilled
        try:
            raw = path.read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            print(f"{_SCRIPT_NAME}: cannot read {path}: {exc}", file=sys.stderr)
            continue
        split = _split_frontmatter_raw(raw)
        if split is None:
            continue  # no frontmatter -> out of scope, never gain a `---` head
        fm_lines, _, _ = split
        existing = _existing_keys(fm_lines)
        missing = [key for key in _FIELDS if key not in existing]
        if not missing:
            continue  # already fully annotated
        rel_posix = str(path.relative_to(root)).replace("\\", "/")
        meta = _LEDGER._parse_frontmatter("\n".join(fm_lines))
        authority, claim_risk = judge(rel_posix, meta)
        values = {"authority": authority, "claim_risk": claim_risk,
                  "review_status": "unreviewed"}
        plan.append({
            "rel": rel_posix,
            "path": path,
            "adds": {key: values[key] for key in _FIELDS if key in missing},
        })
    plan.sort(key=lambda entry: entry["rel"])
    return plan


def apply_backfill(plan: list[dict[str, Any]], tx: VaultTransaction) -> dict[str, int]:
    """Stage every planned insertion into the transaction.

    MUST be called inside the VaultTransaction context: any exception (e.g.
    a mid-loop failure) propagates and triggers the deterministic rollback.
    Each stage is SHA-256-guarded against concurrent modification between
    plan and apply.
    """
    stats = {"files_updated": 0, "lines_added": 0}
    for entry in plan:
        path: pathlib.Path = entry["path"]
        try:
            raw = path.read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            print(f"{_SCRIPT_NAME}: cannot read {path}: {exc}", file=sys.stderr)
            raise  # zero silent swallowing: abort -> rollback
        new_text = _insert_fields(raw, entry["adds"])
        if new_text is None:
            continue  # idempotent: nothing left to insert for this file
        current_sha = hashlib.sha256(path.read_bytes()).hexdigest()
        tx.stage(path, expected_sha256=current_sha, new_text=new_text)
        stats["files_updated"] += 1
        stats["lines_added"] += len(entry["adds"])
    return stats


def summarize(vault_root: pathlib.Path, plan: list[dict[str, Any]]) -> dict[str, Any]:
    """Console/JSON summary of a plan against the scanned note population."""
    scanned = 0
    for path in _LEDGER._iter_markdown_files(vault_root):
        if not path.name.startswith("."):
            scanned += 1
    authority_counts: dict[str, int] = {}
    fallback: list[str] = []
    for entry in plan:
        value = entry["adds"].get("authority", "")
        authority_counts[value] = authority_counts.get(value, 0) + 1
        if value == "unknown":
            fallback.append(entry["rel"])
    return {
        "scanned": scanned,
        "needs_backfill": len(plan),
        "authority_counts": dict(sorted(authority_counts.items())),
        "fallback_unknown": fallback,
        "files_updated_preview": len(plan),
        "lines_added_preview": sum(len(entry["adds"]) for entry in plan),
    }


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="P4 Task-4: batch backfill authority/claim_risk/"
        "review_status (ADD-ONLY, VaultTransaction-guarded)."
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="execute the transaction (default: read-only dry-run preview)",
    )
    parser.add_argument(
        "--vault-root", default=None,
        help="vault root (default: parent of the scripts/ directory)",
    )
    parser.add_argument(
        "--json", action="store_true", help="machine-readable summary on stdout",
    )
    args = parser.parse_args(argv)
    vault_root = (
        pathlib.Path(args.vault_root)
        if args.vault_root
        else pathlib.Path(__file__).resolve().parent.parent
    )
    plan = plan_backfill(vault_root)
    summary = summarize(vault_root, plan)
    if args.json:
        import json

        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(
            f"scanned={summary['scanned']} needs_backfill={summary['needs_backfill']}"
        )
        for value, count in summary["authority_counts"].items():
            print(f"  authority={value}: {count}")
        print(f"  fallback(F1/S14/S15 unknown)={len(summary['fallback_unknown'])}")
    if not args.apply:
        print("dry-run: zero writes (use --apply to execute the transaction)")
        return 0
    tx_id = f"tx-claim-backfill-{datetime.date.today().isoformat()}"
    with VaultTransaction(vault_root, tx_id=tx_id) as tx:
        stats = apply_backfill(plan, tx)
    print(
        f"applied: files_updated={stats['files_updated']} "
        f"lines_added={stats['lines_added']} (tx={tx_id})"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except TransactionError as exc:
        print(f"{_SCRIPT_NAME}: transaction failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
