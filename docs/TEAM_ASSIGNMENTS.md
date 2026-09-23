# Team assignments — Agent Interface & EMDM Redis Backend

This document finalizes the split between the two development workstreams
for the next phase. It exists so that each team can build independently
against one shared contract, with a clean separation of concerns.

---

## 1. The split at a glance

| | **Team A — Agent Interface** | **Team B — EMDM Redis Backend** |
| --- | --- | --- |
| Owns | `bonsai-ewm` controller, agent runtime integration, decision layer | `rds-hllset` adapter, Redis storage for Enterprise MetaData Management |
| Primary repos | `bonsai-ewm` (production), `ewm-laya-bonsai-lab` (shared notebooks) | `rds-hllset` (new), reads `ewm-state-machine` (read-only), `rhs_algebra` (reference-only) |
| Speaks | agent/harness APIs, Laya/Jev decision protocol | `ewm-scene` JSON protocol over HTTP, Redis protocol internally |
| Does **not** touch | lattice internals, Redis internals | controller logic, agent logic, decision models |
| Key deliverable | agent-facing interface + eval harness | Redis-backed lattice storage that passes the shared conformance suite |

**The split in one sentence:** Team A makes the lattice *useful to agents*;
Team B makes the lattice *durable and enterprise-scale* — and neither may
cross the line without a joint decision.

---

## 2. The contract between the teams

Both teams converge on **one interface**: the `ewm-scene` JSON protocol.
Team B's `rds-hllset` adapter must be a drop-in lattice backend for
Team A's controller — Team A must be able to point the controller at the
adapter with zero code changes.

### 2.1 The lattice protocol (normative)

Input (flat frames, JSONL):

```jsonl
{"id": 1, "tokens": ["tid12", "tid300", ...]}
```

Commands and output shapes (same as `ewm-scene`):

| Command | Output |
| --- | --- |
| `ingest` | `{"frames": [{"id", "key", "pop"} ...]}` |
| `bss` | `{"tau": [...], "jaccard": [...], "pop": [...], "keys": [...]}` |
| `ma --short N --long N` | `{"t0": [...], "fast": [...], "slow": [...]}` |
| `noether` | `{"dp": [...], "rp": [...], "np": [...], "ind1": [...], "ind2": [...], "ind3": [...]}` |
| `materialize [--beam N]` | `{"frames": [{"id", "ordered", "set", "beam2"} ...]}` |
| `sidecar [--cap N] [--freeze N]` | `{"frames": [...], "jumps", "threshold", "basis_history"}` |
| `project --frame <f.json>` | `{"names", "pops", "frames": [{"id", "intersections", "bss"}]}` |
| `pyramid [--cap N]` | `{"names", "frames": [...], "drn": {...}, "ring": {...}}` |

### 2.2 Conventions both teams must honor

- **Token format:** `tid{n}` strings, where `n` is the model token id.
- **Content keys:** `h:<sha1...>` (and `d:/r:/n:` DRN prefixes where
  Redis exposes them). Keys are structural, never domain-meaningful.
- **Noether semantics:** per transition `D = A\B`, `R = A∩B`, `N = B\A`;
  `ind1 = dp/|R∪N|`, `ind3 = np/|R∪D|`, `ind2 = BSS(R_prev, R)`
  (starts at transition 2; low = surprising).
- **Popcount semantics:** HLLSet popcount, approximately `3 × distinct
  tokens` (three seeds per token).
- **Edge cases:** `materialize` may fail on 1–2-tid frames (fall back to
  raw tids); an empty answer frame is legal and has `pop = 0`.

### 2.3 The shared conformance suite

A single fixture set — golden JSONL frames + expected outputs for
`ingest`, `noether`, `materialize`, `bss` — lives in the shared lab repo.
It is the acceptance test for both sides:

- **Team A** runs it against the controller's lattice client.
- **Team B** runs it against the `rds-hllset` adapter.
- **Cross-check (roadmap item 38)** runs it against both `hllset-next-v2`
  and `ewm-sm` to verify semantic identity before Team B builds on the
  ewm-sm crates.

A backend or a client is "done" only when the suite is green.

---

## 3. Team A — Agent Interface (bonsai-ewm side)

### Scope

Everything from the agent/harness boundary down to the lattice protocol —
but not the lattice implementation or its storage.

### Responsibilities

1. **Agent runtime integration.** DeepSeek-Harness spike (roadmap item
   29): one agent loop where bonsai-ewm controls the context the harness
   sees, with per-action token accounting and audit records.
2. **Agent-facing API.** Define and implement the interface agents use:
   session lifecycle, `ask`/`propose-context`/`policy`, streaming vs
   batch, per-turn records. Publish it as a versioned spec.
3. **Decision layer.** Laya/Jev routing, confidence gating, human-in-the-
   loop `noul` gates, and the `auto` advisor features (roadmap items
   6–9).
4. **Controller robustness.** Empty-answer guard, destructive-action
   confirmations, clean Ctrl-C/cancellation (roadmap P0 items).
5. **Eval harness.** Memory-quality evaluation (context relevance,
   compression ratio, answer fidelity) — the entry criterion for Phase 2.
6. **Session & audit surface.** `/save`, `/load`, `/diff` evolution,
   per-frame diff timelines, audit export.

### Deliverables

- Versioned agent-interface spec (openapi or markdown + reference client).
- DeepSeek-Harness spike notebook/report with token+decision accounting.
- Eval harness with a published baseline.
- Controller release with the P0 robustness items.

### Non-goals

- No changes to `ewm-scene`, ewm-sm crates, or Redis internals.
- No storage/persistence engineering beyond the existing file sessions
  (Team B owns durability).
- No model fine-tuning.

### Depends on

- Team B: only the shared conformance suite (green) — Team A can develop
  against `ewm-scene` until the `rds-hllset` adapter exists.

---

## 4. Team B — EMDM Redis Backend

### Scope

Everything from the Redis protocol down to durable, enterprise-scale
HLLSet storage for Enterprise MetaData Management — but not controller or
agent logic.

### Responsibilities

1. **Semantic-identity verification (roadmap item 38, first).**
   Cross-check harness: same frames through `hllset-next-v2` and ewm-sm;
   compare content keys, popcounts, D/R/N, materialized order. Decide the
   canonical side per feature before any build.
2. **`rds-hllset` adapter (roadmap item 37).** Sidecar service speaking
   the `ewm-scene` JSON protocol (section 2.1) over HTTP, built on the
   ewm-sm hllset crates, with `rhs_algebra` (or the Redis HLLSet module)
   used unchanged as a normal database.
3. **Catalog operations for EMDM.** DRN drift, views, edges/PageRank,
   disambiguation (`CatalogLUT` + `G1 subset guard`), session/history
   chains — mapped from the rhs_algebra command surface (roadmap items
   34–36).
4. **Deployment & portability.** Podman/compose packaging; verified
   against Redis, Valkey, and at least one managed Redis-compatible
   service (license-safe).
5. **Scale & persistence.** Benchmarks for ingest/commit overhead and
   multi-tenant layout; define the metadata hash (`{key}:m`) contract
   between structural and domain fields.

### Deliverables

- Verification report (item 38) with the canonical-side decision.
- `rds-hllset` adapter passing the shared conformance suite.
- EMDM catalog operations demo (drift diff, views, disambiguation) on
  synthetic metadata.
- Deployment artifacts + benchmark report.

### Non-goals

- No changes to ewm-sm crates in place (consume as a dependency; any
  needed change is a joint escalation).
- No agent/model/decision-model work.
- No UI beyond a thin admin/health surface.

### Depends on

- Team A: nothing functional — Team B develops against the same
  conformance suite. The adapter's first customer is the Team A
  controller, but the contract in section 2 is sufficient to start
  immediately.

---

## 5. Workflow rules

1. **Shared ground.** `ewm-laya-bonsai-lab` is the common documentation
   and conformance-suite home; both teams may add notebooks, but the
   suite fixtures change only by joint agreement.
2. **Invariants.** `bonsai_ewm` stays Python-stdlib-only; ewm-sm crates
   are never modified in place; research and production lines stay
   independent.
3. **Escalation path.** Any change to the lattice protocol, token
   encoding, content-key format, or ewm-sm crates requires both teams +
   the roadmap owner.
4. **Definition of done.** Spec updated + conformance suite green +
   benchmark/report artifact committed + roadmap items marked.

---

## 6. Milestones (aligned with ROADMAP phases)

| Milestone | Team A | Team B |
| --- | --- | --- |
| M1 (now) | P0 robustness items; eval harness skeleton | Item 38 verification report |
| M2 | DeepSeek-Harness spike + agent-interface spec v1 | `rds-hllset` adapter v0 (conformance green) |
| M3 | Controller behind a minimal API; multi-session | EMDM catalog ops demo + deployment artifacts |
| M4 (Phase 3 entry) | Audit export; pilot readiness | Scale/tenancy benchmarks; managed-Redis validation |

---

## 7. Open items to finalize

- Team names, owners, and communication channel.
- Target dates for M1–M4.
- Where the conformance suite repo/folder lives exactly
  (candidate: `ewm-laya-bonsai-lab/tests/conformance`).
- Whether the agent-interface spec is markdown-first or openapi-first.
