#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
Vault Heuristic Conflict Scanner for Coding Vault ({{VAULT_ROOT}})

ROADMAP-P2 Task-2 (#6 冲突扫描) — read-only audit sensor. Mines pairs of
notes that share (1) a frontmatter tag and (2) a core content keyword, where
the two notes make OPPOSITE-style assertions about it:

    positive side : 必须 | 应当 | 一定要 | 推荐 | 正确 | always | must | should
    negative side : 不能 | 禁止 | 不得 | 不要 | 不应 | 切勿 | never | must not | 否

Output is a CANDIDATE list for human review — candidates are results, not
errors (exit code stays 0). The scan is strictly read-only (zero writes, no
git operations); `--json` emits a machine-readable payload for the P5
dashboards.

Grouping & keyword strategy (MVP heuristic, documented per Task-2 contract
「同一句断言中的核心名词/概念词交集」)
------------------------------------------------------------------------
1. Mining domain: every `*.md` under the vault except EXCLUDED_DIRS and
   ROOT_INFRASTRUCTURE_FILES (same convention as `vault-knowledge-graph.py`;
   `11-Agents` and `logs` are additionally excluded per the Task-2 interface
   enumeration — agent audit logs are noise for assertion mining). The
   frontmatter is used for tags only, never mined for assertions.
2. Code is removed before sentence extraction: fenced ```/~~~ blocks are
   dropped entirely and inline `...` spans are blanked (case-d test).
   Markdown table rows (lines starting with `|`) are skipped too — they are
   structural data, not authored assertions (measured on the real vault:
   512/4217 candidates originated from table headers/rows). Sentences are
   split at clause granularity — on 。！？；;，、：: and newlines — so
   enumeration lines (「核心原则：严格执行模式（）、强制引用、禁止反引号…」)
   become per-clause assertions instead of mega-token-sets that match
   anything (measured: 746 -> 178 candidates on the real vault).
3. Polarity markers are STRIPPED from a sentence before tokenization so they
   can never become the shared keyword themselves. Polarity precedence:
   negative wins when both tables match one sentence ("must not" contains
   "must"). 否 is guarded against the common non-assertion compounds
   是否/能否/与否/否则; remaining false positives (quoting others,
   否定之否定) are left for human review by design (MVP: candidates, not
   verdicts).
4. Content tokens of a cleaned sentence:
   - ASCII words >= 2 chars, lower-cased, minus a small English stopword set;
   - CJK sliding n-grams (2-4 chars) over each CJK run, minus a small
     stop-gram table (使用/如果/所以...). Single CJK chars are NOT tokens:
     as cross-note "concept words" they are too ambiguous (measured on the
     real vault: 3376/4217 candidates had a junk 1-char keyword like
     式/强/模/离). Concept pairs carried by a single char (e.g. 锁) are still
     caught whenever both sentences share a 2-gram containing it.   Boundary-spanning grams
   are accepted as heuristic noise — only the INTERSECTION of two sentences
   matters, and a junk gram must appear in both sentences to inflate the
   score.
5. Pairing: two notes are grouped when their frontmatter tags intersect; for
   each shared tag every positive-sentence x negative-sentence combination
   with a non-empty token intersection is a candidate. keyword = the longest
   shared token (ties broken lexicographically -> deterministic); score =
   |shared tokens| — the plan's 简单启发式「共同关键词数」. No score threshold
   is applied (the contract makes any shared-keyword opposite pair a
   candidate); candidates are returned score-DESCENDING so the highest-signal
   pairs surface first for human review (ties broken by paths for
   determinism).
6. Tags parsing uses PyYAML when importable and falls back to a regex parser
   when it is missing (README dependency convention: 「缺失会退化为正则兜底」).
   A YAML failure is reported on stderr before falling back — never silently
   swallowed.

Failure semantics: unreadable files are reported on stderr and skipped
(zero-silent-swallow rule); the scanner itself never raises on note content.
"""

import sys

# Prevent Windows GBK stdout trap (vault-wide convention)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import argparse
import json
import os
import pathlib
import re
from typing import Any, Iterator, NamedTuple, Optional

try:
    import yaml as _yaml
except ImportError:  # regex fallback kicks in (README dependency convention)
    _yaml = None

# Same exclusion convention as vault-knowledge-graph.py; `11-Agents` and
# `logs` are added per the Task-2 interface enumeration.
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

# Polarity tables. English tokens use letter boundaries so "mustard" never
# matches; positive "must" excludes "must not" via lookahead, and the negative
# table is checked FIRST (precedence documented in the module docstring).
_POSITIVE_RE: re.Pattern[str] = re.compile(
    r"一定要|必须|应当|推荐|正确"
    r"|(?<![A-Za-z])always(?![A-Za-z])"
    r"|(?<![A-Za-z])must(?!\s*not)(?![A-Za-z])"
    r"|(?<![A-Za-z])should(?![A-Za-z])"
)
_NEGATIVE_RE: re.Pattern[str] = re.compile(
    r"不能|不应|不得|不要|禁止|切勿"
    r"|(?<![A-Za-z])must\s+not(?![A-Za-z])"
    r"|(?<![A-Za-z])never(?![A-Za-z])"
    r"|(?<![是能与])否(?!则)"
)
# Stripping table = union of both polarity sides (case-insensitive so English
# markers never survive into tokens under any capitalization).
_POLARITY_STRIP_RE: re.Pattern[str] = re.compile(
    r"一定要|必须|应当|推荐|正确|不能|不应|不得|不要|禁止|切勿"
    r"|(?<![A-Za-z])must\s+not(?![A-Za-z])"
    r"|(?<![A-Za-z])always(?![A-Za-z])"
    r"|(?<![A-Za-z])must(?![A-Za-z])"
    r"|(?<![A-Za-z])should(?![A-Za-z])"
    r"|(?<![A-Za-z])never(?![A-Za-z])",
    re.IGNORECASE,
)

_FRONTMATTER_RE: re.Pattern[str] = re.compile(
    r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n?", re.DOTALL
)
_SENTENCE_SPLIT_RE: re.Pattern[str] = re.compile(r"[。！？!?；;，、：:]")
_LEADING_MD_RE: re.Pattern[str] = re.compile(r"^[>\s#*`-]+")
_FENCE_TOKEN = ("```", "~~~")
_INLINE_CODE_RE: re.Pattern[str] = re.compile(r"`[^`\n]*`")
_ASCII_WORD_RE: re.Pattern[str] = re.compile(r"[A-Za-z][A-Za-z0-9_\-]+")
_CJK_RUN_RE: re.Pattern[str] = re.compile(r"[\u4e00-\u9fff]+")

# Heuristic stop-gram table (tunable; it only shapes keyword/score quality,
# and a token must appear in BOTH sentences to matter at all).
_CJK_STOP_GRAMS: frozenset[str] = frozenset({
    "我们", "你们", "他们", "它们", "这个", "那个", "一个", "一些", "一下",
    "什么", "怎么", "如何", "如果", "那么", "因为", "所以", "但是", "然后",
    "或者", "以及", "并且", "其中", "其他", "所有", "任何", "时候", "情况",
    "进行", "使用", "可以", "就是", "还是", "也是", "都是", "不是", "没有",
    "能够", "需要", "应该", "注意", "建议", "这里", "那里", "哪些", "以下",
    "如下", "上面", "下面", "相关", "问题", "方法", "方式", "内容", "笔记",
    "文章", "文档", "说明", "描述", "介绍", "总结", "记录", "整理", "设置",
    "配置", "支持", "默认", "当前", "系统", "数据", "代码", "测试", "运行",
    "执行", "处理", "返回", "参数", "函数", "变量", "类型", "来源", "参考",
    "出自", "来自", "一定",
})
_EN_STOPWORDS: frozenset[str] = frozenset({
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "at", "by", "is",
    "are", "was", "were", "be", "been", "for", "with", "when", "if", "then",
    "this", "that", "it", "its", "as", "we", "you", "they", "he", "she",
    "can", "could", "will", "would", "do", "does", "did", "have", "has",
    "had", "not", "no", "so", "such", "than", "there", "their", "from",
})


class _Assertion(NamedTuple):
    """One mined assertion sentence with its polarity and content tokens."""

    text: str
    polarity: str  # "positive" | "negative"
    tokens: frozenset[str]


class _Note(NamedTuple):
    """A scanned note: POSIX relative path, tag set, mined assertions."""

    rel: str
    tags: frozenset[str]
    assertions: list[_Assertion]


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


def _parse_tags_regex(fm_text: str) -> list[str]:
    """Regex tags parser — the PyYAML-missing fallback (README convention).

    Handles both `tags: [a, b]` / `tags: a, b` inline styles and the block
    style (`tags:` followed by contiguous `  - item` lines).
    """
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


def _parse_frontmatter_tags(fm_text: Optional[str]) -> list[str]:
    """Parse frontmatter tags: PyYAML first, regex fallback when missing.

    A YAML parse failure is reported on stderr before falling back — zero
    silent swallowing.
    """
    if not fm_text:
        return []
    if _yaml is not None:
        try:
            data = _yaml.safe_load(fm_text)
        except _yaml.YAMLError as exc:
            print(
                f"vault-conflict-scan: frontmatter YAML parse failed, "
                f"falling back to regex: {exc}",
                file=sys.stderr,
            )
        else:
            if isinstance(data, dict):
                return _normalize_tag_list(data.get("tags"))
            return []
    return _parse_tags_regex(fm_text)


def _strip_code(body: str) -> str:
    """Drop fenced ```/~~~ blocks entirely and blank inline `code` spans."""
    kept_lines: list[str] = []
    in_fence = False
    for line in body.splitlines():
        trimmed = line.lstrip()
        if trimmed.startswith(_FENCE_TOKEN):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        kept_lines.append(_INLINE_CODE_RE.sub(" ", line))
    return "\n".join(kept_lines)


def _polarity_of(sentence: str) -> Optional[str]:
    """Classify a sentence; negative has precedence over positive."""
    if _NEGATIVE_RE.search(sentence):
        return "negative"
    if _POSITIVE_RE.search(sentence):
        return "positive"
    return None


def _content_tokens(cleaned_sentence: str) -> set[str]:
    """Extract content tokens (see module docstring §4 for the strategy).

    Only tokens >= 2 units qualify: ASCII words (>=2 chars) and CJK 2-4 gram
    sliding windows. Single CJK chars are excluded by design — measured too
    ambiguous as cross-note concept words.
    """
    tokens: set[str] = set()
    for word in _ASCII_WORD_RE.findall(cleaned_sentence):
        lowered = word.lower()
        if lowered not in _EN_STOPWORDS:
            tokens.add(lowered)
    for run in _CJK_RUN_RE.findall(cleaned_sentence):
        max_width = min(4, len(run))
        for width in range(2, max_width + 1):
            for start in range(len(run) - width + 1):
                gram = run[start:start + width]
                if gram not in _CJK_STOP_GRAMS:
                    tokens.add(gram)
    return tokens


def _extract_assertions(body: str) -> list[_Assertion]:
    """Mine assertion sentences from a note body (code already stripped)."""
    assertions: list[_Assertion] = []
    for line in _strip_code(body).splitlines():
        if line.lstrip().startswith("|"):
            continue  # markdown table rows: structural data, not assertions
        plain = _LEADING_MD_RE.sub("", line).strip()
        if not plain:
            continue
        for segment in _SENTENCE_SPLIT_RE.split(plain):
            segment = segment.strip()
            if not segment:
                continue
            polarity = _polarity_of(segment)
            if polarity is None:
                continue
            cleaned = _POLARITY_STRIP_RE.sub(" ", segment)
            assertions.append(
                _Assertion(segment, polarity, frozenset(_content_tokens(cleaned)))
            )
    return assertions


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


def _load_notes(
    vault_root: pathlib.Path, tags_filter: Optional[set[str]]
) -> list[_Note]:
    """Load notes (rel path, tags, assertions), sorted by relative path.

    With a tags_filter, notes carrying none of the requested tags are skipped
    before assertion mining (--tag limits the scan domain).
    """
    notes: list[_Note] = []
    for path in _iter_markdown_files(vault_root):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:
            print(f"vault-conflict-scan: cannot read {path}: {exc}", file=sys.stderr)
            continue
        rel_posix = str(path.relative_to(vault_root)).replace("\\", "/")
        fm_text, body = _split_frontmatter(text)
        tag_list = _parse_frontmatter_tags(fm_text)
        if tags_filter is not None and not (set(tag_list) & tags_filter):
            continue
        notes.append(_Note(rel_posix, frozenset(tag_list), _extract_assertions(body)))
    notes.sort(key=lambda note: note.rel)
    return notes


def _pick_keyword(shared_tokens: frozenset[str]) -> str:
    """Longest shared token wins; ties break lexicographically (deterministic)."""
    return sorted(shared_tokens, key=lambda token: (-len(token), token))[0]


def _match_pair(
    sent_a: _Assertion, sent_b: _Assertion
) -> Optional[tuple[_Assertion, _Assertion, frozenset[str]]]:
    """An opposite-polarity pair sharing >=1 content token, else None."""
    if sent_a.polarity == sent_b.polarity:
        return None
    shared = sent_a.tokens & sent_b.tokens
    if not shared:
        return None
    return sent_a, sent_b, frozenset(shared)


def _opposite_pairs(
    assertions_a: list[_Assertion], assertions_b: list[_Assertion]
) -> Iterator[tuple[_Assertion, _Assertion, frozenset[str]]]:
    """Yield every opposite-polarity, keyword-sharing sentence combination."""
    for sent_a in assertions_a:
        for sent_b in assertions_b:
            pair = _match_pair(sent_a, sent_b)
            if pair is not None:
                yield pair


def _candidates_for_note_pair(
    note_a: _Note, note_b: _Note, cluster_tags: list[str]
) -> list[dict[str, Any]]:
    """Candidates for one note pair; dedupe on (pair, keyword)."""
    candidates: list[dict[str, Any]] = []
    seen_keywords: set[str] = set()
    for tag in cluster_tags:
        for sent_a, sent_b, shared in _opposite_pairs(
            note_a.assertions, note_b.assertions
        ):
            keyword = _pick_keyword(shared)
            if keyword in seen_keywords:
                continue
            seen_keywords.add(keyword)
            candidates.append({
                "file_a": note_a.rel,
                "file_b": note_b.rel,
                "tag": tag,
                "keyword": keyword,
                "sentence_a": sent_a.text,
                "sentence_b": sent_b.text,
                "polarity_a": sent_a.polarity,
                "polarity_b": sent_b.polarity,
                "score": len(shared),
            })
    return candidates


def scan_for_conflicts(
    vault_root: pathlib.Path, tags: Optional[list[str]] = None
) -> list[dict[str, Any]]:
    """Scan the vault for candidate conflicting-assertion pairs (read-only).

    Grouping key = shared frontmatter tag + shared content keyword between two
    opposite-polarity assertion sentences. Returns a sorted candidate list of
    dicts {file_a, file_b, tag, keyword, sentence_a, sentence_b, polarity_a,
    polarity_b, score}. Candidates are results for human review — never errors.
    """
    tags_filter = set(tags) if tags is not None else None
    notes = _load_notes(vault_root, tags_filter)
    candidates: list[dict[str, Any]] = []
    for i in range(len(notes)):
        for j in range(i + 1, len(notes)):
            note_a, note_b = notes[i], notes[j]
            shared_tags = note_a.tags & note_b.tags
            if tags_filter is not None:
                shared_tags &= tags_filter
            if not shared_tags:
                continue
            cluster_tags = sorted(shared_tags)
            candidates.extend(_candidates_for_note_pair(note_a, note_b, cluster_tags))
    candidates.sort(
        key=lambda c: (-c["score"], c["file_a"], c["file_b"], c["keyword"], c["tag"])
    )
    return candidates


def _print_human_report(
    vault_root: pathlib.Path,
    tags_filter: Optional[list[str]],
    candidates: list[dict[str, Any]],
) -> None:
    """Render the default console listing (candidates, not errors)."""
    print("=" * 68)
    print(" 🔥 VAULT CONFLICT SCAN — 启发式矛盾声明扫描（只读）")
    print("=" * 68)
    print(f" 📂 Vault    : {vault_root}")
    print(f" 🎯 Tag 过滤 : {tags_filter if tags_filter else '（无）'}")
    print(f" 🧭 检出候选对: {len(candidates)} 条")
    print("-" * 68)
    for idx, cand in enumerate(candidates, 1):
        print(
            f" [{idx}] keyword={cand['keyword']}  tag={cand['tag']}  "
            f"score={cand['score']}"
        )
        print(f"     A ⬅ {cand['polarity_a']}  {cand['file_a']}")
        print(f"        「{cand['sentence_a']}」")
        print(f"     B ➡ {cand['polarity_b']}  {cand['file_b']}")
        print(f"        「{cand['sentence_b']}」")
        print("-" * 68)
    print(" ℹ️ 候选即结果（交人工复核，非错误）；本扫描零写入。")
    print(" ℹ️ 加 --json 获取机器可读输出（供 P5 dashboards 消费）。")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Vault 启发式矛盾声明扫描器（只读审计传感器，候选交人工复核）"
    )
    parser.add_argument("--vault-path", type=str, default=None, help="Root path of the Obsidian vault")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON (for P5 dashboards)")
    parser.add_argument(
        "--tag",
        dest="tags",
        action="append",
        default=None,
        help="Limit the scan to notes carrying this tag (repeatable)",
    )
    args = parser.parse_args()

    if args.vault_path:
        vault_root = pathlib.Path(args.vault_path).resolve()
    else:
        script_dir = pathlib.Path(__file__).resolve().parent
        vault_root = (
            script_dir.parent
            if (script_dir.parent / "AGENTS.md").exists()
            else pathlib.Path("{{VAULT_ROOT}}").resolve()
        )

    candidates = scan_for_conflicts(vault_root, tags=args.tags)

    if args.json:
        payload = {
            "vault_root": str(vault_root).replace("\\", "/"),
            "tags_filter": args.tags,
            "count": len(candidates),
            "candidates": candidates,
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        _print_human_report(vault_root, args.tags, candidates)
    sys.exit(0)


if __name__ == "__main__":
    main()
