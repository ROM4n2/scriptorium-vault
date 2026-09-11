---
title: "Git 工作流与安全防泄露规范"
created: 2026-08-28
updated: 2026-09-02
type: rules
audience: both
tags:
  - category/rules
  - topic/git
status: stable
authority: synthetic
claim_risk: high
review_status: unreviewed
---

# Git 工作流与安全防泄露规范 (GIT-CONVENTIONS)

> 本规范定义了跨项目统一的 Git 提交消息规范、分支策略、密钥防泄露与历史审计流程。

---

## 1. 提交信息规范 (Conventional Commits)

### 1.1 格式要求 (MUST)

提交信息 MUST 遵循 Conventional Commits 格式：

```text
<type>(<scope>): <subject>

<body>

<footer>
```

### 1.2 Type 类别定义

| Type       | 语义说明   | 适用场景                              |
| ---------- | ---------- | ------------------------------------- |
| `feat`     | 新增功能   | 增加新特性、新 API 或新能力           |
| `fix`      | 修复缺陷   | 修复 Bug 或异常行为                   |
| `docs`     | 文档变更   | 仅修改文档、注释或 README             |
| `refactor` | 重构优化   | 既不增加新特性也不修复 Bug 的代码调整 |
| `perf`     | 性能提升   | 提升运行性能或降低内存占用的变更      |
| `test`     | 测试用例   | 新增测试或修正已有测试                |
| `chore`    | 杂项维护   | 依赖更新、构建流程调整、辅助工具变动  |
| `ci`       | CI/CD 变更 | GitHub Actions 或构建流水线脚本修改   |

### 1.3 Subject 与 Body 准则 (MUST)

- **祈使语气 (MUST)**：首行 Subject MUST 使用祈使句（如 `feat(auth): add jwt validation middleware`，而非 `added ...`）。
- **说明“为什么” (SHOULD)**：Body 中 SHOULD 阐述本次修改的背景原因与权衡，而非单纯罗列改动行。
- **单行摘要字符数 (SHOULD)**：首行摘要建议控制在 50~72 个字符以内。

---

## 2. 分支管理策略 (Branching Strategy)

- `main`：主分支，代码随时保持可发布/生产就绪状态。
- `feat/<feature-name>`：新特性开发分支，自 `main` 切出，完成后 PR/合并回 `main`。
- `fix/<issue-name>`：问题修复分支。
- `chore/<task-name>`：日常维护与技术债偿还。

---

## 3. 密钥与敏感信息安全防线 (Zero-Leakage Policy)

> [!CAUTION]
> 严禁将任何 API Key、Token、私钥或凭据提交至 Git 仓库。本地环境必须在每次工作区初始化时完成防线布设。

### 3.1 预防与本地忽略 (MUST)

- 本地包含敏感信息的配置文件（`config.yaml`, `.env`, `*.secret`, `*.pem`）MUST 纳入 `.gitignore`。
- 真实密钥一律通过环境变量注入，绝不硬编码进源码。

### 3.2 提交前拦截守卫 (Pre-Commit Key Scan) (MUST)

- **全局启用方式 (MUST)**：工作区初始化时 MUST 启用 Git pre-commit hook（`git config core.hooksPath .githooks`）。
- **高性能轻量化设计（Windows Git Bash 友好）(MUST)**：
  - **痛点根因**：Windows 下进程派生开销极高（比 Linux 慢 10~50x）。若采用「每文件 × 每规则」分别起管道，10~20 个暂存文件会派生近千个子进程，单次提交阻塞 >30s。
  - **标准设计架构（快慢路径分离 + 单次多模式 Grep）**：
    1. **模式预组装 (`GREP_ARGS`)**：将全部密钥正则预组装为单组 `-e "<regex>"` 列表；
    2. **单次字节落盘与 NUL 保护**：通过 `git show ":$path" > "$RAW_TMP"` 直接将原始字节落入临时文件，避免将输出存入 Bash 内存变量导致 `\0` (NUL) 字节截断破坏 `grep -I` 二进制判断；
    3. **快路径极速判定 (Fast-Path)**：单次执行 `grep -nIE "${GREP_ARGS[@]}"` 扫描文件，正常提交（0 命中）在 <0.01s 内极速放行，全库提交耗时由 >30s 压降至 <0.5s（近 60x 提速）；
    4. **慢路径精准定位 (Slow-Path)**：仅在确有命中行时，才对命中行逐模式回查标签并输出 `LINE <path>:<line> <Label>`；
    5. **日志安全脱敏 (MUST)**：仅报告位置与 Key 类别，**严禁回显密钥明文本身**（防止密钥二次泄露进终端记录与 CI 日志）；
    6. **显式代码审阅豁免 (Pragma)**：支持行内注释（如 `tool:allow-secret` / `git:allow-secret`）显式豁免误报，使豁免理由留在 diff 中供团队 Code Review；
    7. **二进制与 Keystore Magic 识别**：结合 `head -c 7 | od -An -tx1` 探测文件头 Magic（JKS `feedfeed*`、JCEKS `cececece*`、PKCS12 `3082????020103`），杜绝伪装扩展名（如 `cp x.jks blob.bin`）绕过。

#### 核心正则与通用高性能 Hook 模板 (Reference Implementation)

```bash
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

    # 二进制 Magic 头探测
    magic="$(head -c 7 "$RAW_TMP" | od -An -tx1 | tr -d ' \n')"
    case "$magic" in
        feedfeed*|cececece*|3082????020103)
            printf 'NAME\t%s\tkeystore（按文件头 Magic 认出）不应入库\n' "$path" >> "$HITS"
            ;;
    esac

    # 组合多模式单次扫描 (Fast-Path)
    matched_lines="$(grep -nIE "${GREP_ARGS[@]}" "$RAW_TMP" 2>/dev/null \
        | grep -v -- "$PRAGMA" \
        | cut -d: -f1)"

    # 命中时的慢路径标签匹配 (Slow-Path)
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
```

### 3.3 绝对禁止绕过守卫 (MUST NOT)

- 任何情况下 MUST NOT 使用 `git commit --no-verify` 跳过 hook 校验。

### 3.4 历史泄露与悬空对象审计 (Dangling Objects Check) (MUST)

若怀疑曾发生 Key 泄露，必须执行双层扫描：

1. **可达历史扫描**：
   ```bash
   git log --all -p | grep -E "(sk-[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{16}|ghp_[A-Za-z0-9]{36}|AIza[A-Za-z0-9_-]{30,})"
   ```
2. **悬空对象扫描**（针对 reset / rebase / force-push 留在 `.git` 中的残余对象）：
   ```bash
   git fsck --no-reflogs 2>/dev/null | grep dangling | awk '{print $3}' | while read hash; do git show "$hash"; done | grep -E "(sk-[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{16}|ghp_[A-Za-z0-9]{36})"
   ```
3. **处置原则 (CRITICAL)**：一旦发现 Key 曾被提交，**第一动作必须是立即吊销/轮换该 Key**；重写 Git 历史只能清理仓库体积，无法撤回已泄露密钥的有效性。

---

## 4. 本机环境协同规范 (Windows / Git Bash)

- **SSH 认证链路 (MUST)**：使用 Windows 原生 OpenSSH（环境变量 `GIT_SSH=C:\WINDOWS\System32\OpenSSH\ssh.exe`），确保正确接入系统的 ssh-agent，不走 msys2 隔离层。
- **符号链接创建防静默复制 (MUST)**：
  - Git Bash / MSYS2 默认执行 `ln -s` 会以退出码 0 静默执行目录递归拷贝（`cp -r`），导致多环境内容严重漂移。
  - 创建符号链接 MUST 显式声明前置环境变量 `MSYS=winsymlinks:nativestrict`：
    ```bash
    MSYS=winsymlinks:nativestrict ln -s /target /link
    ```
  - **权限位强校验 (MUST)**：创建后 MUST 立即运行 `ls -la /link` 确认权限位首字符为 `l`（`lrwxrwxrwx`）；若显示为 `d`（目录）或 `-`（普通文件），说明发生静默拷贝，MUST 删除并重新创建。
  - **开发者模式依赖**：本机已开启 Windows 开发者模式（Developer Mode），允许免管理员提权创建原生 NTFS 软链接。

#### 4.1 行尾噪声防护（autocrlf）
- **现象**：开启 `core.autocrlf`（Windows 常见）时，`git status` 报 ` M` 但 `git diff` 为空，提交刷 `warning: LF will be replaced by CRLF`。根因：diff 自动归一化行尾，status 却按「工作区行尾 ≠ 索引期望行尾」标记——差异只是换行符，不是代码。
- **核实**：`git diff --ignore-space-at-eol --stat -- <files>` 输出为空 → 纯行尾噪声，无内容改动。
- **处置**：清噪声 `git checkout -- <files>`；统一策略在仓库加 `.gitattributes`（`* text=auto eol=lf`）；按类型拆分提交前务必排除此类文件，**严禁 `git add -A`** 把噪声收进功能提交。

#### 4.2 钩子 BOM 防护
- **现象**：AI 工具（write_to_file 等）覆盖式写 `.githooks/pre-commit` 会在文件头注入 BOM（EF BB BF），shebang 失效，git 报 `cannot spawn .githooks/pre-commit: No such file or directory`，**所有提交被阻断**。
- **诊断**：`file .githooks/pre-commit` → `UTF-8 (with BOM)` 有问题，`UTF-8 text` 正常。
- **处置**：`tail -c +4 .githooks/pre-commit > /tmp/hook && mv /tmp/hook .githooks/pre-commit && chmod +x .githooks/pre-commit`；落地后用 `file` 校验无 BOM，CI 可加 `grep -rl $'\xef\xbb\xbf' .githooks` 报警。遇 `cannot spawn` 先查 BOM / 可执行位 / 解释器，而非路径。

#### 4.3 check-ignore 误报防护（CRLF gitignore）

- **现象**：`.gitignore` 为 CRLF 行尾时，`git check-ignore -v <path>` 把**空行**（实为 `\r`）当匹配一切的空模式报命中，连 `!X/` 否认规则也因行尾 `\r` 失效——诊断信号骗人（报告"已忽略"），实际 `git add` / `git status` 一直正常。实测于 Git for Windows 2.54。
- **根因**：`\r` 污染模式匹配语义；`check-ignore` 只回答"模式表里有没有命中"，不回答"add 是否真被拒"——模式表异常时两者可以相反。
- **防御 (MUST)**：判定文件是否真被忽略 MUST 以 `git add -n <path>`（dry-run）或 `git status` 为准，check-ignore 只作辅助信号，两信号矛盾时以实际行为为准。
- **处置**：存量修复 `sed -i 's/\r$//' .gitignore` 归一 LF，误报即消失、否认规则恢复语义；生成/编辑 `.gitignore` 的脚本 MUST 用 LF 写出（PowerShell 侧见 〔你的领域通用规范〕 §11 无 BOM 写法，写前统一 CRLF→LF）。给"必须入库"的共享目录（如 `WORKMEMORY/`）MUST 用注释写明"勿加入忽略规则"的设计意图，不依赖 `!X/` 否认规则（CRLF 下自身失效）。

---

#### 4.4 Fork 多 PR 分支独立性 (Multi-PR Branch Isolation) (MUST)

- **现象**：向同一个外部仓库提交多个 PR 时，所有 PR 都基于第一个 PR 的 commit，导致 PR 之间产生隐式依赖（PR #12 的 diff 里包含了 PR #11 的文件变更）。
- **根因**：创建后续分支时，本地 main 已经包含了前序 PR 的 commit（因为本地 merge 了前序 PR）。从这个 main 切出的分支自然继承了前序 PR 的变更。
- **关键错误路径**：
  ```
  正确: origin/main (无前序 PR) → checkout -b pr12 → cherry-pick fix
  错误: local/main (有前序 PR) → checkout -b pr12 → 包含了前序 PR
  ```
- **预防规则 (MUST)**：
  1. 每个 PR 分支 **MUST** 从 `origin/main`（目标仓库的 main）切出；
  2. **MUST NOT** 从包含其他 PR 变更的本地分支切出；
  3. 创建分支前 **MUST** 确认 base 干净：
     ```bash
     git checkout main
     git reset --hard origin/main  # 确保本地 main 干净
     git checkout -b fix/xxx main   # 明确指定 base
     ```
- **已犯错修复**：
  ```bash
  git checkout main
  git branch -D broken-branch
  git checkout -b fixed-branch main
  git cherry-pick <commit-hash>  # 只 pick 自己的 commit
  git push origin fixed-branch --force
  ```
- **推送前验证 (MUST)**：`git log main..HEAD --oneline` 确认只有 1 个 commit；看到多个 commit 说明分支不独立，需 cherry-pick 重建。

---

#### 4.5 git index 0 字节损坏：派生物重建法

- **现象**：任何 git 命令报 `fatal: .git/index: index file smaller than expected`，`ls -la .git/index` 显示 **0 字节**。
- **根因**：`.git/index`（暂存区）是从 HEAD 与工作区派生的缓存，不是对象库。0 字节 = 无暂存信息可丢。真正宝贵的 `.git/objects`（提交/树/blob）与工作区文件完好无损。
- **诊断**：`ls -la .git/index` 看大小 → 0 字节直接 rm+reset；非 0 但解析失败才考虑 `git fsck`。
- **修复**：
  ```bash
  rm .git/index              # 删掉损坏的派生物
  git reset                  # mixed reset：从 HEAD 重建 index，工作区不动
  git status                 # 应显示与 HEAD 的正常差异
  ```
- **边界**：若损坏前确有 `git add` 过但未 commit 的内容，重建 index 后暂存状态会丢（文件本身还在工作区，重新 add 即可）。
- **预防**：Agent/CI 环境高危——并发 agent、被强杀的进程、杀软扫描都可能截断 index；重要半成品**及时 commit**，比"保护 index"更有效。

---

## 5. 关联索引

- Agent 行为守则：[[01-Rules/AGENT-CONDUCT]]
- 通用编码规范：〔你的领域通用规范〕
- 知识库导航中心：[[00-MOC/Home]]

## 6. 关联踩坑索引

- 行尾噪声（autocrlf / CRLF↔LF churn）：见 §4.1。
- 钩子 UTF-8 BOM 破坏（`cannot spawn` 卡死提交）：见 §4.2。
- check-ignore 被 CRLF 空行误报为"匹配一切"：见 §4.3。
- Fork 多 PR 分支不独立（前序 PR commit 泄漏到后续分支）：见 §4.4。
- git index 0 字节损坏（派生物重建法）：见 §4.5。
