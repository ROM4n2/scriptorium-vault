---
name: vault-debug
description: Execute 4-step systematic root-cause debugging with historical Coding Vault pitfalls search and minimal reproduction. Enforces NO fixes without root-cause investigation.
---

# Vault-Debug: 4-Step Systematic Root-Cause Debugging

Resolve bugs, race conditions, memory leaks, and runtime panics with zero guesswork using the 4-step root-cause protocol.

## 🚨 The Zero-Guesswork Iron Rule (HARD GATE)
> **DO NOT modify any production source code until Step 1 (Evidence & Minimal Reproduction) is fully complete and verified.**
> Never try random fixes or poke-and-hope changes.

---

## The 4-Step Root-Cause Protocol

```
  [Step 1: Evidence Capture & Minimal Repro (scratch/repro.*)]
                               │
                               ▼
  [Step 2: Vault Pitfall & Intent Mapping (search_vault)]
                               │
                               ▼
  [Step 3: Root-Cause Remediation & Mutation Defense]
                               │
                               ▼
  [Step 4: Regression Test & Karpathy Ingestion (/vault-save)]
```

### Step 1: Evidence & Minimal Reproduction (MUST)
1. **Exact Error Log**: Capture full stack trace and error message.
2. **Minimal Repro Script**: Create a standalone reproduction script in `scratch/repro.<lang>` or write a failing test.
3. **Execute & Confirm Repro**: Run repro script in terminal and confirm it produces the exact reported failure.

### Step 2: Vault Pitfall & Synonym Search
Query Coding Vault for known gotchas and workarounds:
- Call `search_vault(query="<error_message_or_keyword>")`
- Inspect `01-Rules/〔领域专题规范〕.md` and `05-Tools/OBSIDIAN-SETUP.md`.

### Step 3: Root-Cause Fix & Defense
1. Identify the fundamental flaw (e.g. data race, nil pointer, unhandled encoding, expired context).
2. Implement surgical fix in production code.
3. Run the repro script / failing test and verify it now passes (GREEN).

### Step 4: Regression Lock & Knowledge Ingestion
1. Promote the reproduction script into a permanent regression unit test in `tests/`.
2. If this was a non-obvious pitfall: Call `save_inbox_draft` or run `/vault-save` to persist the solution in `99-Inbox/`.
