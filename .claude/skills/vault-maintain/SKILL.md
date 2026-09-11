---
name: vault-maintain
description: 在本库（{{VAULT_ROOT}}）内运行知识库健康巡检、修复 healthcheck 暴露的失败项并确保 review-log 已登记时触发。一条命令验收，禁止零散乱跑脚本。
---

# Coding Vault 库内健康巡检与修复闭环

## 0. 本技能堵死的场景 (TDD Baseline)

**实测基线 (2026-09-02)**：`vault-healthcheck.py` 输出 `ALL CRITICAL CHECKS PASSED`，但库内技能实体仍存在漂移——`vault-tools/SKILL.md` 把 7 个 L1 全局技能当"专属快捷技能"罗列，且残留旧目录名 `08-Inbox/`。全绿 ≠ 无漂移：健康巡检只覆盖**被检查的项**，技能注册表与实体的一致性此前无人值守。

本技能强制：巡检 → 依失败项修复 → **复跑至全绿 + review-log 已登记** 三段闭环，缺一不可。

## 1. 巡检 (Healthcheck) — 判据：输出 ALL CRITICAL CHECKS PASSED

```bash
python scripts/vault-healthcheck.py --log
```

- `--log` 必须带上：全绿时自动向**当月分片** `11-Agents/logs/{YYYY-MM}.md`（如 2026-09）追加一行审计记录，落盘目标由 `scripts/vault_audit.py` 统一按月选取（[[11-Agents/review-log]] 为规范/归档索引锚点）；
- **判据 (MUST)**：最后一行输出 `Overall Health: ✅ ALL CRITICAL CHECKS PASSED`，且 exit code 0。出现任一 `❌ FAIL` 即进入 §2，不得跳过。
- Check 1-10 含 `[8] Skill Registry Sync`（L2 4 项硬校验 + L1 技能软校验），这是注册表红线（[[05-Tools/SKILL-REGISTRY]] §5「只可引用存在文件」）的机器闸门。

## 2. 修复 (Remediation) — 按失败项分类处理，判据：单测/命令输出为证

**Evidence-First（证据先于断言）**：每项修复结束必须复跑对应命令给出证据，严禁空口声称"已修好"。

| 失败项 | 修复动作 | 验收命令 |
|---|---|---|
| [1] Frontmatter | 补 `title/created/type/tags/status/audience` 六字段 | 复跑 healthcheck |
| [2] Wikilink 断链 | 修目标路径或删除悬空引用（清理前先查反向引用，防他处悬空） | 复跑 healthcheck |
| [3] 双版本 | 对齐 STANDARDS/CHEATSHEET 双向 frontmatter 指针 | 复跑 healthcheck |
| [5] Symlink | 重建软链接指向 `AGENTS.md` | 复跑 healthcheck |
| [7] 工具链路径 | 脚本内旧编号目录名改现役名 | 复跑 healthcheck |
| [8] 技能漂移 | 分两类：a) 注册表已登记但实体缺失 → 补 `.claude/skills/<name>/SKILL.md`（L2）或经 CC Switch 落盘（L1）；b) 实体在库但注册表未登记 → 按单向链路补登记 | 复跑 healthcheck |

**技能修复纪律 (MUST)**：任何技能实体变更遵循「规则→技能」单向链路（[[01-Rules/SKILL-AUTHORING-SPEC]] §7）——先定稿 L3 规则/注册表 → 登记 review-log → 再改 `SKILL.md` 实体；本库 L2 技能由 Vault 管理，L1 技能分发由用户经 CC Switch UI 完成，Agent 禁止跨端建链。

## 3. 复检与登记 (Verify & Log) — 判据：退出前二次确认

```bash
python scripts/vault-tools.py --health   # 统一入口二次确认，输出与 healthcheck 一致
```

- 复跑 `python scripts/vault-healthcheck.py --log` 直到全绿且当月 `11-Agents/logs/{YYYY-MM}.md` 已出现本次记录（查详情勿开 review-log 主表，明细已分片）；
- **Campsite Rule（离开时更干净）**：修复过程产生的临时文件/脚本必须清理；修复若涉规范措辞变更，向当月 `logs/{YYYY-MM}.md` 追加登记（可经 `vault-healthcheck --log` 或按表头格式手动追加）。

## 4. 逃逸禁止 (No-Escape)

- 禁止以"只是小问题"为由跳过 §2 直接宣称完成；
- 禁止在技能正文内发明库内不存在的约束（单一真值源：规则在 L3，技能只做执行层包装）；
- 禁止用 `grep`/手动零散方式替代统一入口巡检——统一入口保证检查项不遗漏。
