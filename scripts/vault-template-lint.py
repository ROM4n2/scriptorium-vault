#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
Vault Template Lint — 模板包**裸文本引用**体检（根治"假绿"）

问题背景（2026-09-11 评估组发现）：`vault-healthcheck` 只校验 `[[wikilink]]`
与反引号内的引用，而导出模板里绝大多数断引用写成**裸文本**（目录树、表格行、
正文提及）。结果是包内 healthcheck "全绿"，但接收者一打开 README / Home 就看到
指向已剔除内容的引用——假绿。

本工具补上这一层：
1. **禁用 token 扫描**：manifest 的 `exclude` / `drop` 里的具体文件名（词干）+
   手工登记的 `lint_forbidden` 条目，在包内任何文本文件中出现即报（裸文本也算）。
2. **反引号路径存在性**：`` `path/to/file.ext` `` 形态的引用，若指向包内不存在的
   文件则报（只判含 `/` 且带已知扩展名的形态，避免误伤命令与概念词）。
3. **退出码**：发现任一问题 → exit 1（供发布流水线 fail-closed 使用）。

用法：
    python scripts/vault-template-lint.py --package-dir D:/tmp/vault-template \
        --manifest scripts/vault-template-manifest.json --strict
"""

import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import argparse
import fnmatch
import json
import pathlib
import re
from typing import Any, Dict, List, Set, Tuple

# 反引号内、看起来像"仓库内相对路径"的形态（含目录分隔符 + 已知扩展名）
BACKTICK_PATH_RE = re.compile(
    r"`([A-Za-z0-9_./\u4e00-\u9fff-]+\.(?:md|py|sh|json|canvas|css|yml|yaml))`"
)
REPO_PATH_EXT = {".md", ".py", ".sh", ".json", ".canvas", ".css", ".yml", ".yaml"}
TEXT_SUFFIXES = {
    ".md", ".py", ".sh", ".ps1", ".json", ".txt", ".canvas", ".css", ".yml",
    ".yaml", ".toml", ".cfg", ".ini", ".html",
}


def load_manifest(path: pathlib.Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def derive_forbidden_tokens(doc: Dict[str, Any]) -> Set[str]:
    """从 exclude / drop 的**具体文件路径**派生禁用 token（词干 + 全名）。"""
    tokens: Set[str] = set()
    for key in ("exclude", "drop"):
        for item in doc.get(key, []):
            pattern = item.get("pattern", "")
            if "*" in pattern or "?" in pattern:
                continue  # 通配形态不派生（会误伤）
            base = pattern.rsplit("/", 1)[-1]
            if "." not in base:
                continue
            tokens.add(base)
            tokens.add(base.rsplit(".", 1)[0])
    for item in doc.get("lint_forbidden", []):
        token = item.get("token", "").strip()
        if token:
            tokens.add(token)
    return tokens


def lint_skip(doc: Dict[str, Any], rel: str) -> bool:
    return any(
        fnmatch.fnmatch(rel, item["pattern"]) for item in doc.get("lint_skip", [])
    )


def path_allowed(doc: Dict[str, Any], candidate: str) -> bool:
    """反引号路径白名单：跨库/生成物形态的引用不是断链。

    例如 `WORKMEMORY/INDEX.md`（项目侧共享记忆，位于**项目仓库**而非本库）、
    `logs/YYYY-MM.md`（夜间生成的按月分片命名模式）、`vault-tools/SKILL.md`
    （相对技能目录的引用）。
    """
    return any(
        fnmatch.fnmatch(candidate, item["pattern"])
        for item in doc.get("lint_path_allowlist", [])
    )


def iter_text_files(root: pathlib.Path) -> List[str]:
    out: List[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = str(path.relative_to(root)).replace("\\", "/")
        if "/.git/" in f"/{rel}" or rel.startswith(".git/"):
            continue
        suffix = pathlib.PurePosixPath(rel).suffix.lower()
        if suffix in TEXT_SUFFIXES:
            out.append(rel)
        elif suffix == "":  # 无后缀文本文件（pre-commit 等）
            try:
                if b"\0" not in path.read_bytes()[:8192]:
                    out.append(rel)
            except OSError:
                continue
    return out


def derive_forbidden_regex(doc: Dict[str, Any]) -> List[Tuple[str, "re.Pattern[str]"]]:
    """manifest `lint_forbidden_regex` → (rationale, 编译后的 IGNORECASE 正则)。"""
    out: List[Tuple[str, re.Pattern[str]]] = []
    for item in doc.get("lint_forbidden_regex", []):
        pattern = item.get("pattern", "").strip()
        if pattern:
            out.append((item.get("rationale", ""), re.compile(pattern, re.IGNORECASE)))
    return out


def regex_sweep_skip(doc: Dict[str, Any], rel: str) -> bool:
    """正则终扫的豁免面：deidentify_skip（法律文本/清单规则字面量）+ 携带
    示例 pattern 字面量的工具文件自身。注意**不含** scripts/tests/** —— 守卫
    测试也必须过终扫（2026-09-11 二评：测试文件内嵌私有路径字面量被漏掉）。"""
    if any(
        fnmatch.fnmatch(rel, item["pattern"]) for item in doc.get("deidentify_skip", [])
    ):
        return True
    return rel in ("scripts/vault-template-lint.py", "scripts/vault-export-template.py")


def lint_package(
    package_dir: pathlib.Path, doc: Dict[str, Any]
) -> Tuple[List[str], List[str]]:
    """返回 (禁用 token 命中, 反引号路径断引用)，元素形如 'rel:line: 详情'。

    token 匹配**大小写不敏感**（2026-09-11 二评：`示例项目`/`Exam-Prep` 变体
    因大小写敏感匹配全部漏网）。
    """
    forbidden = derive_forbidden_tokens(doc)
    forbidden_lower = {t.lower(): t for t in forbidden}
    regex_rules = derive_forbidden_regex(doc)
    token_hits: List[str] = []
    path_hits: List[str] = []
    for rel in iter_text_files(package_dir):
        skip_tokens = lint_skip(doc, rel)
        skip_regex = regex_sweep_skip(doc, rel)
        if skip_tokens and skip_regex:
            continue
        path = package_dir / rel
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            lower_line = line.lower()
            if not skip_tokens:
                for lower_token, orig in forbidden_lower.items():
                    if lower_token and lower_token in lower_line:
                        token_hits.append(f"{rel}:{lineno}: 禁用 token `{orig}`")
            if not skip_regex:
                for rationale, rx in regex_rules:
                    if rx.search(line):
                        token_hits.append(
                            f"{rel}:{lineno}: 隐私正则命中 [{rationale or rx.pattern}]"
                        )
            if skip_tokens:
                continue
            for match in BACKTICK_PATH_RE.finditer(line):
                candidate = match.group(1)
                if "/" not in candidate:
                    continue
                ext = pathlib.PurePosixPath(candidate).suffix.lower()
                if ext not in REPO_PATH_EXT:
                    continue
                if path_allowed(doc, candidate):
                    continue
                if not (package_dir / candidate).exists():
                    path_hits.append(f"{rel}:{lineno}: 反引号路径不存在 `{candidate}`")
    return token_hits, path_hits


def main(argv: List[str] = None) -> int:
    parser = argparse.ArgumentParser(description="模板包裸文本引用体检（fail-closed）")
    parser.add_argument("--package-dir", required=True)
    parser.add_argument("--vault-root", default=None, help="源库根（用于解析 manifest 相对路径）")
    parser.add_argument("--manifest", default="scripts/vault-template-manifest.json")
    parser.add_argument("--strict", action="store_true", help="发现问题返回 1（默认同样返回 1，保留兼容）")
    args = parser.parse_args(argv)

    package_dir = pathlib.Path(args.package_dir).resolve()
    vault_root = (
        pathlib.Path(args.vault_root).resolve() if args.vault_root
        else pathlib.Path(__file__).resolve().parent.parent
    )
    doc = load_manifest(vault_root / args.manifest)

    token_hits, path_hits = lint_package(package_dir, doc)
    total = len(token_hits) + len(path_hits)
    print("=" * 68)
    print(" 🧹 TEMPLATE LINT — 裸文本引用体检")
    print("=" * 68)
    print(f" 包目录: {package_dir}")
    print(f" 禁用 token 命中: {len(token_hits)} | 反引号断引用: {len(path_hits)}")
    for line in token_hits[:60]:
        print(f"  ❌ {line}")
    for line in path_hits[:60]:
        print(f"  ❌ {line}")
    if total > 60:
        print(f"  … 其余 {total - 60} 条略")
    if total:
        print(f"\n❌ 结论: 发现 {total} 处裸文本引用问题（接收者会看到指向已剔除内容的引用）")
        return 1
    print("\n✅ 结论: 无裸文本引用问题")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
