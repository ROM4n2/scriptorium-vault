<#
.SYNOPSIS
    Automated New Workspace Bootstrap Script (PowerShell / Windows)
    Implements the Mandatory New Workspace Bootstrap Contract (AGENTS.md & AGENT-CONDUCT.md §8)

.DESCRIPTION
    1. Checks and configures .gitignore for sensitive secrets (config.yaml, .env, *.secret, *.pem, *.key)
    2. Installs and configures Git Pre-commit secret scanning hook (.githooks/pre-commit)
    3. Injects 3-line rule anchor into CLAUDE.md / .agent-rules.md / .cursorrules
    4. Scaffolds WORKMEMORY 4-piece set (cross-agent shared working memory) and injects its anchor
    5. Evaluates language defense baselines (Python UTF-8 stdout, Bash pipefail, TS strict)

.PARAMETER TargetPath
    Target workspace/project directory path. Defaults to current directory.
#>

[CmdletBinding()]
param (
    [string]$TargetPath = "."
)

$target = (Resolve-Path $TargetPath).Path
# Vault root derived from script location (portable; no machine-bound literals)
$vaultRoot = Split-Path -Parent $PSScriptRoot
Write-Host "🚀 Initializing Workspace Bootstrap for: $target" -ForegroundColor Cyan
Write-Host ("─" * 70) -ForegroundColor Gray

# 1. Security Guards: .gitignore check
$gitIgnorePath = Join-Path $target ".gitignore"
$requiredIgnores = @(
    "config.yaml",
    "config.yml",
    "config.local.yaml",
    ".env",
    ".env.*",
    "*.env",
    "*.secret",
    "*.pem",
    "*.key",
    "*.local.json",
    "credentials.json"
)

$existingIgnores = @()
if (Test-Path $gitIgnorePath) {
    $existingIgnores = Get-Content $gitIgnorePath -ErrorAction SilentlyContinue
}

$missingIgnores = @()
foreach ($item in $requiredIgnores) {
    if (-not ($existingIgnores -contains $item)) {
        $missingIgnores += $item
    }
}

if ($missingIgnores.Count -gt 0) {
    $appendHeader = if (-not (Test-Path $gitIgnorePath) -or (Get-Content $gitIgnorePath -Raw).Length -eq 0) { "# Sensitive credentials & secrets`n" } else { "`n# Sensitive credentials & secrets`n" }
    $appendContent = $appendHeader + ($missingIgnores -join "`n") + "`n"
    Add-Content -Path $gitIgnorePath -Value $appendContent -Encoding UTF8
    Write-Host "  ✅ [Security] Added $($missingIgnores.Count) sensitive entries to .gitignore" -ForegroundColor Green
}
else {
    Write-Host "  ✅ [Security] .gitignore already contains required secret exclusions" -ForegroundColor Green
}

# 2. Security Guards: Pre-commit Hook
$isGitRepo = Test-Path (Join-Path $target ".git")
if ($isGitRepo) {
    $githooksDir = Join-Path $target ".githooks"
    if (-not (Test-Path $githooksDir)) {
        New-Item -ItemType Directory -Path $githooksDir -Force | Out-Null
    }

    $hookFile = Join-Path $githooksDir "pre-commit"
    if (Test-Path $hookFile) {
        # 已有 hook（可能是项目的 gatekeeper 等自定义守卫）绝不覆写，只确认 hooksPath 生效
        Write-Host "  ℹ️  [Security] Existing .githooks/pre-commit preserved (not overwritten)" -ForegroundColor Yellow
    }
    else {
    $hookContent = @'
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
'@
    # 无 BOM UTF-8：带 BOM 的 pre-commit 会让 shebang 失效，bash 直接报错
    [System.IO.File]::WriteAllText($hookFile, $hookContent.Replace("`r`n", "`n"), (New-Object System.Text.UTF8Encoding($false)))
    }

    Push-Location $target
    try {
        git config core.hooksPath .githooks
        Write-Host "  ✅ [Security] Configured git hooksPath → .githooks (pre-commit secret scanner)" -ForegroundColor Green
    }
    catch {
        Write-Host "  ⚠️  [Security] Unable to run git config: $_" -ForegroundColor Yellow
    }
    finally {
        Pop-Location
    }
}
else {
    Write-Host "  ℹ️  [Security] Not a git repository, skipping git hook installation" -ForegroundColor Yellow
}

# 3. Rule Anchor Injection
$ruleAnchorText = @"

## 工程规范与避坑检索

- 核心规范源：$vaultRoot\AGENTS.md
- 检索避坑规范：python $vaultRoot\scripts\search-vault.py <报错/模式关键词>
- 发现新踩坑自动沉淀：写草稿至 $vaultRoot\99-Inbox\YYYY-MM-DD-{topic}.md
"@

$targetRuleFiles = @("CLAUDE.md", ".agent-rules.md", ".cursorrules")
foreach ($ruleFile in $targetRuleFiles) {
    $ruleFilePath = Join-Path $target $ruleFile
    if (Test-Path $ruleFilePath) {
        $content = Get-Content $ruleFilePath -Raw -Encoding UTF8
        if ($content -notmatch "工程规范与避坑检索") {
            Add-Content -Path $ruleFilePath -Value "`n$ruleAnchorText" -Encoding UTF8
            Write-Host "  ✅ [Rules] Injected 3-line rules anchor into $ruleFile" -ForegroundColor Green
        }
        else {
            Write-Host "  ✅ [Rules] $ruleFile already contains Coding Vault rules anchor" -ForegroundColor Green
        }
    }
    else {
        Set-Content -Path $ruleFilePath -Value "# Project Guidelines`n$ruleAnchorText" -Encoding UTF8
        Write-Host "  ✅ [Rules] Created $ruleFile with 3-line Coding Vault rules anchor" -ForegroundColor Green
    }
}

# 3.5 WORKMEMORY Bootstrap (Cross-Agent Shared Working Memory)
# 下发 4 件套（PROTOCOL/INDEX/PROJECT_OVERVIEW/work.log，模板源 Templates/workmemory/）
# 并向项目级 anchor 注入 3 行 WORKMEMORY 节。已有 WORKMEMORY 的项目跳过（幂等）。
$wmSource = Join-Path $vaultRoot "Templates\workmemory"
$wmTarget = Join-Path $target "WORKMEMORY"
$projectName = Split-Path $target -Leaf

if (-not (Test-Path $wmTarget)) {
    New-Item -ItemType Directory -Path $wmTarget -Force | Out-Null
    $wmFiles = @("PROTOCOL.md", "INDEX.md", "PROJECT_OVERVIEW.md", "work.log")
    foreach ($wmFile in $wmFiles) {
        $src = Join-Path $wmSource $wmFile
        if (Test-Path $src) {
            $body = Get-Content $src -Raw -Encoding UTF8
            $body = $body.Replace("{{PROJECT_NAME}}", $projectName)
            $body = $body.Replace("{{TIMESTAMP}}", (Get-Date -Format "yyyy-MM-dd HH:mm"))
            $body = $body.Replace("{{VAULT_ROOT}}", $vaultRoot)
            # 无 BOM UTF-8：协议要求纯 UTF-8，BOM 会污染 work.log 首字节（Python utf-8 读取不剥 BOM）
            [System.IO.File]::WriteAllText((Join-Path $wmTarget $wmFile), $body, (New-Object System.Text.UTF8Encoding($false)))
        }
        else {
            Write-Host "  ⚠️  [WORKMEMORY] Template missing: $src" -ForegroundColor Yellow
        }
    }
    Write-Host "  ✅ [WORKMEMORY] Scaffolded 4-piece set into WORKMEMORY\ (agent will distill PROJECT_OVERVIEW from codebase)" -ForegroundColor Green
}
else {
    Write-Host "  ✅ [WORKMEMORY] WORKMEMORY\ already exists, skipping scaffold" -ForegroundColor Green
}

# 3.6 WORKMEMORY Anchor Injection (project-level)
$wmAnchorText = @"

## 共享工作记忆 (WORKMEMORY)

- 进入会话先读 WORKMEMORY\INDEX.md → PROJECT_OVERVIEW.md → work.log 尾部 50 行；发现未闭合 WORK_START 先询问用户。
- 工作中：决策/踩坑/交接 MUST 以 ≤4KB 事件追加 WORKMEMORY\work.log（schema 见 WORKMEMORY\PROTOCOL.md）。
- 语义知识检索：调用 search_vault MCP 或 python $vaultRoot\scripts\search-vault.py "<关键词>"；成熟知识沉淀走 /vault-save。
"@

foreach ($ruleFile in @("CLAUDE.md", "AGENTS.md", "GEMINI.md", ".agent-rules.md", ".cursorrules")) {
    $ruleFilePath = Join-Path $target $ruleFile
    if (Test-Path $ruleFilePath) {
        $content = Get-Content $ruleFilePath -Raw -Encoding UTF8
        if ($content -notmatch "WORKMEMORY\\INDEX\.md") {
            Add-Content -Path $ruleFilePath -Value "`n$wmAnchorText" -Encoding UTF8
            Write-Host "  ✅ [WORKMEMORY] Injected anchor into $ruleFile" -ForegroundColor Green
        }
    }
    else {
        # 仅当该文件本来就该存在时才创建：AGENTS.md 是跨 agent 通用锚点，其余只追加不新建
        if ($ruleFile -eq "AGENTS.md") {
            Set-Content -Path $ruleFilePath -Value "# Project Guidelines`n$wmAnchorText" -Encoding UTF8
            Write-Host "  ✅ [WORKMEMORY] Created AGENTS.md with WORKMEMORY anchor" -ForegroundColor Green
        }
    }
}

# 4. Environment Defense Baseline Check
Write-Host "  🔍 [Environment] Checking project language baseline defense:" -ForegroundColor Cyan
if (Get-ChildItem -Path $target -Filter "*.py" -Recurse -Depth 2 -ErrorAction SilentlyContinue) {
    Write-Host "     • Python detected: Ensure sys.stdout.reconfigure(encoding='utf-8', errors='replace') is configured" -ForegroundColor Gray
}
if (Test-Path (Join-Path $target "package.json")) {
    Write-Host "     • Node/TS detected: Ensure tsconfig.json has 'strict': true" -ForegroundColor Gray
}
if (Test-Path (Join-Path $target "go.mod")) {
    Write-Host "     • Go detected: Ensure errgroup / context propagation standards are followed" -ForegroundColor Gray
}
if (Test-Path (Join-Path $target "Cargo.toml")) {
    Write-Host "     • Rust detected: Ensure thiserror / anyhow error handling pattern is used" -ForegroundColor Gray
}

Write-Host ("─" * 70) -ForegroundColor Gray
Write-Host "🎉 Workspace Bootstrap Completed Successfully!" -ForegroundColor Green
