# Roadmap — bonsai-ewm & ewm-laya-bonsai-lab

The notes accumulated while building v0.2.0 and the interaction-chain
notebooks, turned into an actionable plan. The two projects are one
product split across two lines:

- **bonsai-ewm** — the production controller. Ship quality, stdlib-only,
  external processes only.
- **ewm-laya-bonsai-lab** — the microscope. Notebooks that show the raw
  traffic the controller automates, and where lessons are discovered
  before they are ported.

Priority markers: **P0** correctness/robustness, **P1** product policy,
**P2** ergonomics/research depth, **P3** distribution polish.

---

## North Star — Governed Context & Control Plane for Enterprise Agents

Confirmed direction (2026-09): **a closed-loop, governed agent platform
built on top of open-source software** — not another agent framework, and
not closed-source. The enterprise value is the *loop itself*: every agent
action leaves evidence, every policy decision is typed and logged, and the
whole conversation is content-addressed and diffable.

Three layers:

1. **Agent runtime (pluggable).** [DeepSeek-Harness](https://github.com/deepseek-ai/DeepSeek-Harness)
   is the current candidate standard runtime: vendor-backed, tool calling,
   planning, multi-agent workflows. The plane stays **runtime-agnostic** —
   any harness that emits token streams and accepts policy decisions can
   plug in (LangChain, custom, or bare model calls all qualify).
2. **Control & memory plane (bonsai-ewm).** Context proposals, typed
   policy decisions, content-addressed `S(t)`, session diff, per-turn
   token accounting, D/R/N retention. This is the proprietary core.
3. **Decision layer (Laya / Jev).** Small, calibrated, typed decisions
   for routing, gating, and human-in-the-loop approval (`noul` gates).
   Open models, single forward pass, auditable.

The closed loop:

```text
policy → context proposal → agent action (harness) → answer tokens
      → ingest → S(t) → diff/audit → next policy
```

Principles that keep the direction honest:

- **Open components, governed loop.** ewm-sm research and Laya stay open
  (open-core); the orchestration/audit/service layer may be proprietary.
- **Sell governability, not autonomy.** The pitch is auditability, cost
  attribution, and memory control — the unmet need in the "wild west".
- **Model gateway, not model lock-in.** Bonsai is the reference because
  of `/tokenize` + `/detokenize`; any OpenAI-compatible endpoint with
  token-space access (vLLM-served DeepSeek, other llama.cpp forks) can
  take its place. Enterprises demand model choice.

### First vertical — Enterprise Metadata (Catalog) Management

The first candidate application for the plane: **metadata catalogs as a
governed agent vertical.** Enterprise data ontology (entities, attributes,
relations, tags, lineage, policies) is modeled as an **HLLSet lattice**;
the ewm proposal machinery becomes the catalog's context and governance
plane.

Why this fits:

- **Catalogs are already sets + relations.** A catalog view is a
  materialized proposal — `ewm-scene materialize` literally produces
  ordered/set views of a frame; the pyramid path supports named
  perceptron dimensions (one per ontology facet: schema, tags, lineage,
  ownership).
- **Catalog drift is a lattice diff.** Two catalog snapshots are two
  sessions; `/diff` (D/R/N + BSS/Jaccard) is schema-drift detection with
  content keys for point-in-time addressing.
- **Governance is the decision layer.** Laya/Jev `choice`/`noul` gates
  become approval and routing policies: "this schema change needs human
  review", "route this metadata question to the lineage catalog".
- **Agents operate on catalogs through the same loop.** DeepSeek-Harness
  asks questions and proposes changes; bonsai-ewm controls what catalog
  context it sees and records every action as evidence.

Prior art that de-risks the vertical:

- [hllset-next-v2](https://github.com/alexmy21/hllset-next-v2) — the
  **canonical HLLSet core (gen2)**. 12 crates, contracts-first
  (`hllset-contracts`: Murmur3/sha1, `BitAddress` hinge, token encodings),
  IICA core, the LUT lattice, the two morphisms (single-touch ingest,
  LUT-first materialize), the Noether context (`S(t)`, D/R/N invariants,
  tropical follow matrix), five derived ranks, Lua/Forth frontends, and
  embedded CID storage (Memory + Sled). It deliberately **dropped the
  legacy Redis storage crate** — so a Redis backend for the metadata
  vertical must be a *new* storage crate aligned to gen2 contracts, not a
  revival of the legacy module.
- [rhs_algebra](https://github.com/alexmy21/rhs_algebra) (v0.3.0, public) —
  the latest **Redis-targeted** development: a Rust Redis module with
  immutable, idempotent, content-addressable HLLSets, ~73 commands, DRN
  decomposition (`d:/r:/n:` bitmaps + transition docs), views, explicit
  lattice edges, PageRank, fractal descent, 3-layer TokenLUT +
  CatalogLUT, DeBruijn graphs, and session/history chains
  (`SESSION.COMMIT` → immutable content-addressed views, ~22 µs logging
  overhead). Built on the *previous* core generation — hence the
  refactoring item below.
- The other public hllset/metadata repos (`redis-mds`, `redis-meta`,
  `redis-meta-engine`, `db_metadata`, `SGS_Redis`, …) are
  **reference-only** — not part of the forward line.

Extracted lessons now documented (item 33, done in part):

- **The lattice is a storage model, not a memory trick.** rhs_algebra ran
  catalogs as content-addressed HLLSets in Redis with RediSearch +
  RedisGraph — enterprise scale was already demonstrated there.
- **DRN was a first-class Redis command** — schema/catalog drift via
  `HLLSET.DRN A B` is the same math as `ewm-scene noether`, proven at
  Redis scale.
- **Sessions/history chains existed** (`SESSION.COMMIT`,
  `HISTORY.ANCESTORS`) — the direct ancestor of bonsai-ewm
  `/save` + content-key addressing.
- **Semantic agnosticism was a design principle** — keys are structural
  (`h:<sha1>`), domain fields live in a `{key}:m` metadata hash. The
  ewm/bonsai line must keep this split: lattice never interprets field
  names.
- **Disambiguation + security mode** (`G1 subset guard`, CatalogLUT) is
  the enterprise entity-resolution primitive to port into the catalog
  vertical.
- **Core drift is real.** The HLLSet core drifted across the line; gen2
  (`hllset-next-v2`) is the corrected reference. Anything Redis-facing
  must be aligned to gen2 contracts, and the ewm-sm hllset crates will
  eventually need a reconciliation plan (respecting the "never modify
  ewm-sm crates in place" invariant until a migration is designed).

Phase gates (each phase starts only when its entry criterion is met):

- **Phase 1 — harden the loop (now).** Current P0/P1 items + a
  memory-quality eval harness. *Entry to Phase 2:* reproducible eval
  suite, empty-answer guard, destructive-action confirmations.
- **Phase 2 — service & multi-session + first harness spike.** Controller
  behind a minimal API, multi-user sessions, and one DeepSeek-Harness
  agent loop running under bonsai-ewm context control. *Entry to
  Phase 3:* one real pilot deployment.
- **Phase 3 — enterprise control plane.** Tenancy/RBAC, audit export
  from session diffs, retention/forgetting via D/R/N, on-prem packaging.
  *Entry:* a signed pilot customer.

New roadmap items this direction adds:

29. **DeepSeek-Harness spike.** One agent loop where bonsai-ewm controls
    the memory the harness sees; measure tokens, decisions, and the audit
    trail per action.
30. **Licensing & terms check.** DeepSeek-Harness license, DeepSeek model
    terms for self-host, PrismML Bonsai commercial terms — before any
    enterprise commitment.
31. **Model gateway.** Generalize `BonsaiAdapter` to detect and use
    `/tokenize` + `/detokenize` on any OpenAI-compatible endpoint
    (vLLM etc.), with Bonsai as the first certified backend.
32. **Catalog lattice spike.** Ingest a real metadata catalog
    (tables/columns/tags/lineage) as tid frames; demonstrate
    `materialize` = catalog view, `/diff` = schema drift, pyramid
    perceptrons = ontology facets.
33. **Prior-art extraction.** ✅ partially done — rhs_algebra v0.3.0 read
    and its lessons recorded above; `redis_hllset_mdb` is skipped (the
    other public hllset/metadata repos are reference-only). Remaining:
    read rhs_algebra's `DOCS/dev/ARCHITECTURE.md` + notebooks for the
    Redis persistence details, and hllset-next-v2's
    `_DOCS/dev/HLLSET_DEVELOPER_GUIDE.md` for the gen2 contracts.
34. **Ontology mapping note.** Write the mapping from ontology
    primitives (entity, attribute, relation, tag, lineage, policy) to
    ewm frames / pyramid perceptrons / projection dimensions — the
    contract the catalog adapter must implement.
35. **rhs_algebra → gen2 gap analysis.** A table mapping every
    rhs_algebra capability (DRN, views, edges/PageRank, fractal descent,
    TokenLUT/CatalogLUT, DeBruijn, sessions/history, G1 security mode)
    to its gen2 (`hllset-next-v2`) or ewm/bonsai equivalent or gap —
    the scoping document for the Redis metadata backend.
36. **Disambiguation / entity-resolution study.** The CatalogLUT +
    `G1 subset guard` pattern is enterprise entity resolution on
    fingerprints; test it on synthetic metadata to see what carries
    into the gen2 LUT crates.
37. **Redis backend decision + gen2 storage crate.** Decide Redis as the
    Phase 2/3 metadata backend (recommended: Redis is already trusted in
    enterprise stacks). Implement a **new** gen2-aligned Redis storage
    crate — contracts from `hllset-contracts`, CIDs from `hllset-cid`,
    DRN from `hllset-context`, command surface from rhs_algebra's 73
    commands as the API spec. This is a refactor/reimplementation, not a
    port of the legacy module (gen2 dropped `hllset-storage-redis`).
38. **Core reconciliation plan.** The ewm-sm hllset crates predate the
    gen2 core; design a migration plan that gets the production line onto
    gen2 contracts without violating the "never modify ewm-sm crates in
    place" invariant (candidate: freeze ewm-sm, point bonsai-ewm at the
    gen2 CLI once `ewm-scene` parity exists).

---

## A. bonsai-ewm (production controller)

### A.0 Recently completed (v0.2.0, tagged)

- `auto` proposal — real TypeSafe Jev decides mode + cap per turn (mock
  fallback).
- `surprise` proposal mode — D-part + Noether-flagged frame tids.
- Persistent, addressable sessions — `/save`, `/load`, `/sessions`,
  `/diff` by content key.
- `bonsai-ewm --health`, podman HEALTHCHECK, CI workflow, user guide.

### A.1 Correctness & robustness (P0)

1. **Empty-answer guard.** Bonsai is a reasoning model: with a small
   `max_tokens`, the reasoning trace can consume the whole budget and
   `content` returns empty. The chain then ingests an empty frame
   (`pop=0`) silently. Add detection (empty `content` but non-empty
   `reasoning_content`) and either retry with a larger budget or record
   the event explicitly in the turn record.
2. **`--reasoning-preserve` evaluation.** The server log suggests
   `--reasoning-preserve`; measure its effect on `prompt_tokens` /
   `content` / empty-answer rate before adopting it in
   `scripts/start_bonsai_server.sh`.
3. **Confirm destructive commands.** `/reset` and `/load` currently
   discard unsaved state with no prompt. Add a confirmation (or
   `--yes`) and an "unsaved turns" warning on `/quit`.
4. **In-flight cancellation.** Ctrl-C during `ask()` aborts with a
   traceback; make it cancel the HTTP request cleanly and return to the
   prompt. Ctrl-C at an empty prompt should clear the line, not exit.
5. **Materialize fallback visibility.** The 1–2-tid materializer panic
   already falls back to raw tids; surface a flag in the turn record so
   downstream logic knows "restored order" was approximated.

### A.2 Context policy (P1)

6. **Feed Noether features to Jev.** The `auto` advisor state currently
   has pop/memory counts only. Add `dp/ind1/ind2/ind3`, sidecar
   `step`/`jumps`, and last Jaccard so Jev can choose `surprise` with
   informed thresholds — the lesson from notebook 04.
7. **Adaptive surprise thresholds.** Keep the manual `/surprise`
   override, but add a "auto" setting that derives thresholds from the
   trajectory (mean + 3σ, like the sidecar jump detector).
8. **Budget semantics.** `cap` is in tids; report the detokenized
   character/word count of the proposal too, so the cap is
   interpretable in text terms.
9. **Ingest the decision.** The trainer line ingests `jev_*` decision
   tokens into the union; decide whether bonsai-ewm should too (makes
   the policy itself a lattice-visible frame).

### A.3 Sessions (P1)

10. **Per-frame diff timelines.** `/diff` compares only the two final
    states. Add the per-turn D/R/N + BSS/Jaccard series between two
    sessions so *where* they diverged is visible, not just *that* they
    diverged.
11. **`ewm-git`-backed addressing.** If the research line converges on
    it, adopt `ewm-git` for content-addressed session storage; until
    then, keep the plain `sessions/<key>/` layout.
12. **Export/import.** A session bundle (union + meta) the user can copy
    out of `BONSAI_EWM_WORK`; currently it is just local files.
13. **Same-key overwrite warning.** Saving two conversations that
    converge to the same S(t) silently overwrites the earlier metadata;
    warn and offer to keep both (e.g. `key#n`).

### A.4 REPL ergonomics (P2)

14. **Persistent history + completion.** Save readline history across
    restarts; tab-complete commands and saved session keys.
15. **Richer `/history`.** Browse full answers (not the 50-char
    preview), show the reasoning trace on demand, resend a past query.
16. **Multi-line input.** A paste mode / continuation marker for long
    prompts.

### A.5 Distribution (P3)

17. **Single-file install.** The package is stdlib-only — a zipapp
    (`bonsai-ewm.pyz`) is feasible and would remove the pip step.
18. **Release automation.** On a version tag, CI should build the
    container image and push it to a registry (e.g. ghcr.io), not just
    build-and-discard.
19. **Bonsai sidecar example.** Document a compose/pod for
    Bonsai-server + controller with the health checks wired.

---

## B. ewm-laya-bonsai-lab (interaction-chain notebooks)

### B.0 Completed

- Six notebooks (ewm-scene surface, Laya daemon surface, Bonsai HTTP
  surface, ewm→Laya, full chain, decision models compared) plus
  `docs/INTERACTION_MAP.md`, all executed live.

### B.1 Next notebooks (in suggested order)

20. **Confidence gating over a long trajectory.** Run Laya's choice with
    a confidence floor + fallback across many turns; plot confidence,
    gates, and sidecar `step`/`jumps` together (the notebook 16 idea,
    zoomed into the gating mechanics).
21. **Per-frame session diff.** Build the two-session D/R/N timeline
    that bonsai-ewm's `/diff` should later expose (feeds A.3.10).
22. **Jev vs Laya A/B.** Same route states, N turns, both decision
    models side by side — measures agreement, latency, and where the
    hosted and local models disagree.
23. **Laya prompt study.** Prose vs struct states; state truncation
    (JSONL path doesn't flag it); how the temperature buckets change
    distributions. Use the laya-rust web console's prompt inspector as
    the visual reference.
24. **Frozen sidecar features.** `ewm-scene sidecar --freeze N` gives a
    fixed-dim soft-key series; feed its step/DFT features to Laya and
    see whether the decision tracks periodicity.
25. **Bonsai reasoning split.** Measure `reasoning_content` vs `content`
    token shares for different `max_tokens`; find the minimum budget
    where empty answers stop (feeds A.1.1/A.1.2).

### B.2 Lab infrastructure (P2)

26. **Reusable clients.** `lab/` is importable as-is; optionally add a
    `pyproject.toml` so notebooks can `pip install -e .`.
27. **Notebook smoke in CI.** Execute notebooks 01/02/04 headlessly
    (they need no GPU); skip or mock 03/05 when Bonsai is absent.
28. **Laya CUDA.** Revisit when the driver/nvcc PTX mismatch is fixed
    (nvcc 12.8 targets ISA 8.7; driver 565.77 supports ≤ 12.7); then
    benchmark CPU vs CUDA decisions.

---

## C. Cross-cutting notes (lessons already learned — keep these true)

- **ewm-sm crates are never modified** — only the `ewm-scene` JSON
  protocol is consumed.
- **`bonsai_ewm` stays Python-stdlib-only**; Bonsai and ewm-sm remain
  external processes.
- **Research line and production line evolve independently** — the lab
  documents raw traffic and discovers lessons; bonsai-ewm ports only
  the ones that earn their keep.
- **Bonsai server:** never set `CUDA_VISIBLE_DEVICES` (the PrismML fork
  orders GPUs opposite to `nvidia-smi`; its CUDA0 is the RTX 3060).
- **Laya:** CPU-only on this machine for now; it rewards prose states;
  the JSONL path silently truncates long states.
- **Bonsai:** reasoning model — `content` can be empty when reasoning
  eats `max_tokens`.
- **ewm-scene:** `materialize` panics on 1–2-tid frames; `ingest` and
  `noether` are safe on tiny frames.
- **Git:** both repos use SSH remotes; push from any shell/VS Code
  without credential prompts.

---

## D. Suggested next three sessions

1. **Robustness sprint (P0).** bonsai-ewm: empty-answer guard +
   confirmation on `/reset` `/load` + clean Ctrl-C. Lab: notebook 20
   (confidence gating) started.
2. **Policy sprint (P1).** bonsai-ewm: Noether features into the `auto`
   advisor + adaptive surprise thresholds. Lab: notebooks 22/23 (Jev vs
   Laya, prompt study).
3. **Sessions sprint (P1).** bonsai-ewm: per-frame `/diff` timelines +
   export/import. Lab: notebook 21 feeding that feature, then push and
   let CI go green on the tag.
