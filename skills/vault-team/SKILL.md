---
name: vault-team
description: Orchestrate parallel multi-expert subagent review (Product/UX, Frontend, DBA, Profiler, Reviewer, SRE) on a codebase, feature, or diff. Use when user asks for team review, expert panel, multi-agent audit, or /vault-team.
---

# Multi-Expert Swarm Review & Consensus Synthesis

Orchestrate a full-spectrum domain-specialist subagent swarm to audit code in parallel across **User Experience + Architecture + Database + Performance + Security**, synthesizing an actionable verdict.

## Phase 1: Multi-Expert Review

The skill dispatches a panel of domain specialists in parallel to audit the target from multiple angles. Each expert covers a specific concern:

- **Product & UX** -- validates real user need, journey friction, and error messaging
- **Frontend & State** -- checks async races, offline handling, render cost, and leaks
- **Database & Storage** -- reviews index coverage, query plans, locks, and transaction scope
- **Performance & Concurrency** -- profiles hot paths, data races, allocation pressure
- **Code Quality** -- enforces standards, checks for dead tests and unnecessary complexity
- **SRE & Resilience** -- audits timeouts, retries, failure modes, and resource bounds

Only the experts relevant to the target are dispatched. Recon specialists may run first if the target scope is unclear.

---

## Phase 1.5: Adversarial Verification (for P0/P1 findings)

Before synthesis, verify each **P0 and P1** finding. Dispatch an independent skeptic agent (reuse `code-reviewer` — its anti-sycophancy protocol is the point) with the prompt: *"Try to refute this finding: <finding + file:line + failure scenario>. Read the actual code. If the scenario cannot actually happen, say why."*

- Refutation fails (the finding survives a genuine read of the code) → label **CONFIRMED**.
- Refutation succeeds or the scenario proves unreachable → label **PLAUSIBLE**, keep it in the report with the label visible — do not silently drop it, and do not let it drive a blocker verdict on its own.
- P2 findings are not adversarially verified; label them UNVERIFIED.

Do not skip this step by trusting seat reports at face value — a single-seat P0 that survives an independent skeptic read is worth five that don't.

---

## Phase 2: Evidence Triangulation & Severity Triage
Classify all discovered findings into strict severity tiers:
- **P0 (Blocker)**: Data corruption, race condition deadlock, secret leak, broken core user flow.
- **P1 (Critical)**: Missing index on hot query, unhandled network timeout, confusing error feedback, Goroutine leak.
- **P2 (Improvement)**: Guard clause flattening, touch target adjustment, minor allocation optimization.

---

## Phase 3: Unified Synthesis Report
Output an Executive Expert Panel Synthesis Card:

```markdown
# 🏛️ Multi-Expert Swarm Audit Report: [Target Component]

**Seats dispatched**: <list> · **Seats skipped (why)**: <list>

### 🚨 Critical Findings (P0 / P1)
- **[DBA]** [CONFIRMED]: Missing composite index on `(user_id, status)` causing full table scan.
- **[Frontend]** [PLAUSIBLE]: Rapid button clicking triggers un-aborted concurrent requests.
- **[Product/UX]** [CONFIRMED]: Network failure reports raw 500 error instead of auto-retry feedback.

### 💡 Consensus Action Plan & Patches
1. Apply composite index migration: `CREATE INDEX idx_user_status...`
2. Add `AbortController` signal to API call.
3. Update error handler with user-friendly retry banner.

### ♻️ Reuse Ladder Check (for every "add X / introduce dependency Y" finding)
- <finding>: already covered by <stdlib/existing module> → <prefer reuse / new dep justified because ...>
```

Every P0/P1 finding line carries its **CONFIRMED / PLAUSIBLE** label from Phase 1.5. Every finding that proposes adding code or a dependency gets a **Reuse Ladder** judgment: is there an existing stdlib capability or in-repo module that already does this? A P0 verdict MUST NOT rest on a PLAUSIBLE finding alone.
