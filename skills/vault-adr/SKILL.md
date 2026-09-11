---
name: vault-adr
description: Draft and archive formal Architecture Decision Records (ADRs) with auto-incrementing numbering, context, drivers, considered options, decision outcome, and consequences into the Coding Vault.
---

# Vault-ADR: Architecture Decision Record Generator

Lock in key architectural decisions into permanent history in `08-Projects/{project}/01-ADR/` or `01-Rules/` using the MADR (Markdown Architecture Decision Record) specification.

## Core Invariants (MUST)
1. **Auto-Incrementing Numbering**: Scan existing ADRs in `08-Projects/{project}/01-ADR/` and assign the next sequential number (e.g. `0001`, `0002`, `0003`).
2. **Binary Decision Inquest**: An ADR MUST only be recorded when the decision is **hard to reverse, surprising without context, or involves genuine trade-offs**.
3. **Structured Schema**: MUST strictly follow the 5 core sections: Context, Decision Drivers, Considered Options (Pros/Cons), Decision Outcome, and Consequences.

---

## The 3-Phase ADR Workflow

### Phase 1: Numbering & Path Resolution
1. Target Directory: `08-Projects/{project_name}/01-ADR/` (create if missing).
2. Count existing `[0-9]{4}-*.md` files to determine next index `NNNN`.
3. Generate filename: `NNNN-{kebab-case-title}.md` (e.g. `0004-sqlite-wal-concurrency.md`).

### Phase 2: MADR Template Composition
Fill the standardized MADR template:

```markdown
---
title: "ADR-{NNNN}: {Decision Title}"
created: {YYYY-MM-DD}
updated: {YYYY-MM-DD}
type: project
tags:
  - category/project
  - topic/adr
  - topic/architecture
status: stable
audience: both
---

# ADR-{NNNN}: {Decision Title}

## 1. Context and Problem Statement
{Describe the engineering context, forces at play, and why a decision is necessary.}

## 2. Decision Drivers
- {Driver 1: e.g. Maximize read throughput under concurrent workers}
- {Driver 2: e.g. Zero external daemon dependencies for embedded desktop use}
- {Driver 3: e.g. Prevent database write lock starvation}

## 3. Considered Options
- **Option 1**: {Title & Brief Description}
  - 👍 Pros: {Key advantages}
  - 👎 Cons: {Key drawbacks}
- **Option 2**: {Title & Brief Description}
  - 👍 Pros: {Key advantages}
  - 👎 Cons: {Key drawbacks}

## 4. Decision Outcome
Chosen option: **Option {X}**, because {First-Principles rationale justifying the trade-off}.

## 5. Consequences and Trade-offs
- 🟢 **Positive**: {What becomes easier or faster}
- 🔴 **Negative**: {What becomes more complex, and how we mitigate it}
- 🛡️ **Compliance Guardrail**: {Code rules or static tests enforcing this decision}
```

### Phase 3: Dual-Track Archiving
- Call `save_inbox_draft` MCP to create an entry in `99-Inbox/`, or directly write to `08-Projects/{project}/01-ADR/`.
- Update the project's `README.md` or `AGENT-CONTEXT.md` with the new ADR reference.
