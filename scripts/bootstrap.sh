#!/usr/bin/env bash
# ===============================================================================
# Automated New Workspace Bootstrap Script (Bash / POSIX / macOS / Linux)
# Implements the Mandatory New Workspace Bootstrap Contract (AGENTS.md & AGENT-CONDUCT.md §8)
# ===============================================================================
set -euo pipefail

TARGET_PATH="${1:-.}"
TARGET_DIR=$(cd "$TARGET_PATH" && pwd)

# Vault root derived from script location (portable; no machine-bound literals)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VAULT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo -e "\033[36m🚀 Initializing Workspace Bootstrap for: ${TARGET_DIR}\033[0m"
echo "──────────────────────────────────────────────────────────────────────"

# 1. Security Guards: .gitignore check
GITIGNORE="${TARGET_DIR}/.gitignore"
REQUIRED_IGNORES=("config.yaml" "config.yml" ".env" ".env.*" "*.secret" "*.pem" "*.key" "*.local.json")

if [ ! -f "$GITIGNORE" ]; then
    touch "$GITIGNORE"
fi

MISSING_IGNORES=()
for item in "${REQUIRED_IGNORES[@]}"; do
    if ! grep -qxF "$item" "$GITIGNORE" 2>/dev/null; then
        MISSING_IGNORES+=("$item")
    fi
done

if [ ${#MISSING_IGNORES[@]} -gt 0 ]; then
    echo "" >> "$GITIGNORE"
    echo "# Sensitive credentials & secrets" >> "$GITIGNORE"
    for item in "${MISSING_IGNORES[@]}"; do
        echo "$item" >> "$GITIGNORE"
    done
    echo -e "\033[32m  ✅ [Security] Added ${#MISSING_IGNORES[@]} sensitive entries to .gitignore\033[0m"
else
    echo -e "\033[32m  ✅ [Security] .gitignore already contains required secret exclusions\033[0m"
fi

# 2. Security Guards: Pre-commit Hook
if [ -d "${TARGET_DIR}/.git" ]; then
    GITHOOKS_DIR="${TARGET_DIR}/.githooks"
    mkdir -p "$GITHOOKS_DIR"
    HOOK_FILE="${GITHOOKS_DIR}/pre-commit"

    if [ -f "$HOOK_FILE" ]; then
        # 已有 hook（可能是项目自定义守卫）绝不覆写——与 bootstrap.ps1 行为对齐，
        # 只确认 core.hooksPath 生效（2026-09-11 二评：sh 无条件覆写会静默替换
        # 接收者的 manifest 路由器，令 Gate 1.5/2 失效）。
        echo "  ℹ️  [Security] Existing .githooks/pre-commit preserved (not overwritten)"
    else
    cat << 'EOF' > "$HOOK_FILE"
#!/usr/bin/env bash
# Git Pre-commit High-Performance Secret Scanner
set -u

PRAGMA='git:allow-secret'
HITS="$(mktemp)"
RAW_TMP="$(mktemp)"
trap 'rm -f "$HITS" "$RAW_TMP"' EXIT

PATTERNS='OpenAI/Anthropic 风格 key|sk-[A-Za-z0-9]{20,}
AWS Access Key ID|AKIA[A-Z0-9]{16}
GitHub PAT (classic)|ghp_[A-Za-z0-9]{36}
GitHub PAT (fine-grained)|github_pat_[A-Za-z0-9_]{20,}
Google API Key|AIza[A-Za-z0-9_-]{30,}
Slack token|xox[baprs]-[A-Za-z0-9-]{10,}
JWT|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}
私钥 PEM 块|-----BEGIN [A-Z ]*PRIVATE KEY-----
Java keystore base64 (JKS)|/u3\+7Q
Java keystore base64 (JCEKS)|zs7[O]z'

GREP_ARGS=()
while IFS='|' read -r label regex; do
    [ -n "${regex:-}" ] || continue
    GREP_ARGS+=(-e "$regex")
done <<< "$PATTERNS"

while IFS= read -r -d '' path; do
    case "$path" in
        *.example|*.sample|*.template) ;;
        .env|*/.env|*.secret|*credentials*|*.pem|*.key|*id_rsa*|*id_ed25519*)
            printf 'NAME\t%s\t敏感配置文件不应入库\n' "$path" >> "$HITS"
            ;;
        *.jks|*.jks.b64|*.keystore|*.p12|*.pfx|*signing.properties|*keystore.properties)
            printf 'NAME\t%s\t签名 keystore 不应入库\n' "$path" >> "$HITS"
            ;;
    esac

    if ! git show ":$path" > "$RAW_TMP" 2>/dev/null; then
        continue
    fi

    # 二进制 Magic 探测
    magic="$(head -c 7 "$RAW_TMP" | od -An -tx1 | tr -d ' \n')"
    case "$magic" in
        feedfeed*|cececece*|3082????020103)
            printf 'NAME\t%s\tkeystore（按文件头 Magic 认出）不应入库\n' "$path" >> "$HITS"
            ;;
    esac

    # 快路径单次扫描
    matched_lines="$(grep -nIE "${GREP_ARGS[@]}" "$RAW_TMP" 2>/dev/null \
        | grep -v -- "$PRAGMA" \
        | cut -d: -f1)"

    # 慢路径标签归因
    if [ -n "$matched_lines" ]; then
        while IFS='|' read -r label regex; do
            [ -n "${regex:-}" ] || continue
            printf '%s\n' "$matched_lines" | while IFS= read -r lineno; do
                if sed -n "${lineno}p" "$RAW_TMP" | grep -qE -e "$regex" 2>/dev/null; then
                    printf 'LINE\t%s:%s\t%s\n' "$path" "$lineno" "$label" >> "$HITS"
                fi
            done
        done <<< "$PATTERNS"
    fi
done < <(git diff --cached --name-only -z --diff-filter=ACMR)

if [ -s "$HITS" ]; then
    echo "❌ [SECURITY ALERT] 发现潜在敏感凭据或密钥，提交已被拦截："
    while IFS=$'\t' read -r kind loc label; do
        printf '   • [%s] %s (%s)\n' "$kind" "$loc" "$label"
    done < "$HITS"
    echo ""
    echo "请撤出该文件或将密钥迁移至环境变量；若为误报可在行内添加注释: # $PRAGMA"
    exit 1
fi
exit 0
EOF
    chmod +x "$HOOK_FILE"
    echo -e "\033[32m  ✅ [Security] Installed git pre-commit secret scanner (.githooks/pre-commit)\033[0m"
    fi
    (cd "$TARGET_DIR" && git config core.hooksPath .githooks)
    echo -e "\033[32m  ✅ [Security] core.hooksPath -> .githooks (guards active)\033[0m"
else
    echo -e "\033[33m  ℹ️  [Security] Not a git repository, skipping git hook installation\033[0m"
fi

# 3. Rule Anchor Injection (runtime-interpolated to the user's own vault copy)
RULE_ANCHOR="
## 📖 工程规范与避坑检索

- 核心规范源：\`$VAULT_ROOT/AGENTS.md\`
- 检索避坑规范：\`python $VAULT_ROOT/scripts/search-vault.py \"<报错/模式关键词>\"\`
- 发现新踩坑自动沉淀：写草稿至 \`$VAULT_ROOT/99-Inbox/YYYY-MM-DD-{topic}.md\`"

for rule_file in "CLAUDE.md" ".agent-rules.md" ".cursorrules"; do
    target_rule_file="${TARGET_DIR}/${rule_file}"
    if [ -f "$target_rule_file" ]; then
        if ! grep -qF "工程规范与避坑检索" "$target_rule_file" 2>/dev/null; then
            echo -e "$RULE_ANCHOR" >> "$target_rule_file"
            echo -e "\033[32m  ✅ [Rules] Injected 3-line rules anchor into ${rule_file}\033[0m"
        else
            echo -e "\033[32m  ✅ [Rules] ${rule_file} already contains Coding Vault rules anchor\033[0m"
        fi
    else
        echo -e "# Project Guidelines\n$RULE_ANCHOR" > "$target_rule_file"
        echo -e "\033[32m  ✅ [Rules] Created ${rule_file} with 3-line Coding Vault rules anchor\033[0m"
    fi
done

# 3.5 Ensure the vault-side 99-Inbox/ draft area exists (git archive drops empty dirs)
mkdir -p "$VAULT_ROOT/99-Inbox"

# 3.6 WORKMEMORY Bootstrap (Cross-Agent Shared Working Memory) — 同构 bootstrap.ps1 §3.5
# 下发 4 件套（PROTOCOL/INDEX/PROJECT_OVERVIEW/work.log，模板源 $VAULT_ROOT/Templates/workmemory/）
WM_SOURCE="${VAULT_ROOT}/Templates/workmemory"
WM_TARGET="${TARGET_DIR}/WORKMEMORY"
PROJECT_NAME="$(basename "$TARGET_DIR")"

if [ ! -d "$WM_TARGET" ]; then
    mkdir -p "$WM_TARGET"
    TIMESTAMP="$(date '+%Y-%m-%d %H:%M')"
    for wm_file in "PROTOCOL.md" "INDEX.md" "PROJECT_OVERVIEW.md" "work.log"; do
        wm_src="${WM_SOURCE}/${wm_file}"
        if [ -f "$wm_src" ]; then
            wm_body="$(cat "$wm_src")"
            # pattern 中的大括号必须转义：未转义的 "}" 会被 bash 当作参数扩展的
            # 终止符，导致 {{PLACEHOLDER}} 错位替换（产出 "…}}…/value}" 脏文本）。
            wm_body="${wm_body//\{\{PROJECT_NAME\}\}/${PROJECT_NAME}}"
            wm_body="${wm_body//\{\{TIMESTAMP\}\}/${TIMESTAMP}}"
            wm_body="${wm_body//\{\{VAULT_ROOT\}\}/${VAULT_ROOT}}"
            printf '%s\n' "$wm_body" > "${WM_TARGET}/${wm_file}"
        else
            echo -e "\033[33m  ⚠️  [WORKMEMORY] Template missing: ${wm_src}\033[0m"
        fi
    done
    echo -e "\033[32m  ✅ [WORKMEMORY] Scaffolded 4-piece set into WORKMEMORY/ (agent will distill PROJECT_OVERVIEW from codebase)\033[0m"
else
    echo -e "\033[32m  ✅ [WORKMEMORY] WORKMEMORY/ already exists, skipping scaffold\033[0m"
fi

# 3.7 WORKMEMORY Anchor Injection (project-level) — 同构 bootstrap.ps1 §3.6
WM_ANCHOR="
## 共享工作记忆 (WORKMEMORY)

- 进入会话先读 WORKMEMORY/INDEX.md → PROJECT_OVERVIEW.md → work.log 尾部 50 行；发现未闭合 WORK_START 先询问用户。
- 工作中：决策/踩坑/交接 MUST 以 ≤4KB 事件追加 WORKMEMORY/work.log（schema 见 WORKMEMORY/PROTOCOL.md）。
- 语义知识检索：调用 search_vault MCP 或 python $VAULT_ROOT/scripts/search-vault.py \"<关键词>\"；成熟知识沉淀走 /vault-save。"

for rule_file in "CLAUDE.md" "AGENTS.md" "GEMINI.md" ".agent-rules.md" ".cursorrules"; do
    target_rule_file="${TARGET_DIR}/${rule_file}"
    if [ -f "$target_rule_file" ]; then
        if ! grep -qF "WORKMEMORY/INDEX.md" "$target_rule_file" 2>/dev/null; then
            echo -e "$WM_ANCHOR" >> "$target_rule_file"
            echo -e "\033[32m  ✅ [WORKMEMORY] Injected anchor into ${rule_file}\033[0m"
        fi
    elif [ "$rule_file" = "AGENTS.md" ]; then
        # 仅当该文件本来就该存在时才创建：AGENTS.md 是跨 agent 通用锚点，其余只追加不新建
        echo -e "# Project Guidelines\n$WM_ANCHOR" > "$target_rule_file"
        echo -e "\033[32m  ✅ [WORKMEMORY] Created AGENTS.md with WORKMEMORY anchor\033[0m"
    fi
done

# 4. Environment Defense Baseline Check
echo -e "\033[36m  🔍 [Environment] Checking project language baseline defense:\033[0m"
if find "$TARGET_DIR" -maxdepth 2 -name "*.py" 2>/dev/null | grep -q .; then
    echo "     • Python detected: Ensure sys.stdout.reconfigure(encoding='utf-8', errors='replace') is configured"
fi
if [ -f "${TARGET_DIR}/package.json" ]; then
    echo "     • Node/TS detected: Ensure tsconfig.json has 'strict': true"
fi
if [ -f "${TARGET_DIR}/go.mod" ]; then
    echo "     • Go detected: Ensure errgroup / context propagation standards are followed"
fi
if [ -f "${TARGET_DIR}/Cargo.toml" ]; then
    echo "     • Rust detected: Ensure thiserror / anyhow error handling pattern is used"
fi

echo "──────────────────────────────────────────────────────────────────────"
echo -e "\033[32m🎉 Workspace Bootstrap Completed Successfully!\033[0m"
