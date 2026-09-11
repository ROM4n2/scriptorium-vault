---
name: vault-spark
description: 0-to-1 feature ideation, brainstorming, and exploratory design with Dual-Lens (Product/UX + Technical). Turns vague ideas into structured specs grounded in Coding Vault standards, then auto-relays to /vault-plan. Use when direction is unclear, exploring new features, or /vault-spark.
---

# Vault-Spark: 0-to-1 Feature Ideation & Exploratory Design

Turn vague ideas, open-ended feature thoughts, or fuzzy developer needs into structured, vault-grounded design specifications through collaborative dialogue across **Dual Lenses: User Problem Validation + Technical Architecture**.

## The Iron Gate (HARD GATE)
Do NOT invoke any implementation skill, write production code, or scaffold repositories until presenting the design spec and obtaining explicit human partner approval.

---

## Phase 1: Intent Scoping & Three-Path Classification
Classify the task upfront and announce it:
- **Spike** (Feasibility question): "Can we / what is the cost / quick probe". Present probe plan in 2-3 sentences, get nod, investigate, report recommendation. No spec doc.
- **Bounded** (Scoped tweak to existing code): Clarify questions, present 2-3 paragraph design in chat, get explicit approval, then proceed without plan doc.
- **Architectural** (New feature / subsystem / restructuring): Full process (Phase 2 to Phase 5).

---

## Phase 2: Vault & Codebase Knowledge Grounding
1. Query `omni_search(query, scope='ladder')` to check if similar problems were already solved in `05-Projects/` or `01-Rules/`.
2. Inspect codebase dependencies and standard library capabilities to ground ideation in reality.

---

## Phase 3: Socratic Dialogue & Dual-Lens Trade-Off Matrix

### Step 0: User Value & Journey Validation (`子代理体验角色（自建）` Lens)
Before discussing technical implementation, validate:
1. **Real Problem vs Imaginary Need**: Who is the target user? In what exact scenario will they use this? What is the cost of doing nothing?
2. **Core User Journey**: What are the minimal steps (<= 3 steps) to reach value (Time-to-Value)? Where are potential friction points?

### Step 1: Technical & Architectural Trade-offs
Propose **2 to 3 distinct approaches** with explicit trade-offs:
- **Option A (Minimalist)**: Lowest complexity, zero-dependency, standard library first.
- **Option B (Domain-Native)**: Deep integration with existing project engines.
- **Option C (Extensible)**: Pluggable architecture for future multi-tenant growth.

---

## Phase 4: Spec Generation & Self-Review
On user approval of the approach:
1. Generate design document: `docs/specs/YYYY-MM-DD-<topic>-design.md` (or `05-Projects/{project}/`).
2. **Required Schema**:
   - `1. Problem Statement & User Value` (Why build this, target scenario)
   - `2. User Journey & Core Flow` (Step-by-step user interaction & feedback)
   - `3. Architecture & Data Models` (Components, types, persistence)
   - `4. Edge Cases & Resilience` (Network drops, race conditions, error boundaries)
   - `5. Test Strategy` (Unit tests, integration scenarios)
3. Spec Self-Review: Check for zero "TODO/TBD" placeholders, contradictions, or scope creep.

---

## Phase 5: Handoff Gate (Relay to /vault-plan)
Prompt user:
`Design spec ready and approved. Ready to generate implementation plan via /vault-plan?`
Auto-relay to `/vault-plan` upon confirmation.
