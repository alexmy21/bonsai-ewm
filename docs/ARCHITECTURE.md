# Architecture — the collaborative model

## 1. The base model property

Bonsai 2 27B (PrismML ternary weights, llama.cpp fork) is the first model
where the controller has **bidirectional access to the model's token
space**: the server exposes `/tokenize` and `/detokenize` next to the
OpenAI-compatible chat API. Combined with the 262K-token context plane and
its prompt/KV cache, this makes the context a *proposal* — an artifact the
controller recomputes every turn — rather than a fixed transcript.

## 2. The collaboration loop

```text
                       ┌─────────────────────────────────────────────┐
                       │              bonsai-ewm (controller)        │
   user query ────────►│                                             │
                       │  1. state S(t-1)  = HLLSet lattice          │
                       │  2. context proposal P(t)                   │
                       │       full  = materialize(S) → cap          │
                       │       compact = D-part only (new tids)      │
                       │       surprise = D + Noether R/N tids       │
                       │  3. P(t) --detokenize--> text prefix        │
                       │                                             │
                       │  4. Bonsai.chat(prefix + query)             │
                       │     → answer + reasoning + usage            │
                       │                                             │
                       │  5. tokenize(answer) → tid stream           │
                       │  6. ingest → S(t), D/R/N, materialize       │
                       └──────────────┬──────────────────────────────┘
                                      |
                                      ▼ 
              ┌────────────────────────────────────────────────────────────┐
              │                                                            │
              | ewm-sm (unchanged)          PrismML llama.cpp (unchanged)  │
              | ingest / materialize /      Bonsai 2 27B + KV cache +      │
              | noether / project           prompt cache + 262K context    │
              └────────────────────────────────────────────────────────────┘
```

> query → lattice state → proposed context → Bonsai → new lattice state → …

## 3. Components

| Component | Module | Responsibility |
| --- | --- | --- |
| `BonsaiAdapter` | `bonsai_ewm/adapters.py` | chat / chat_full / tokenize / detokenize over HTTP |
| `JevAdapter` | `bonsai_ewm/adapters.py` | TypeSafe System One over REST (choice/noul) for the `auto` proposal |
| `EwmScene` | `bonsai_ewm/ewm.py` | the only lattice-facing module (subprocess, JSON in/out) |
| `BonsaiSession` | `bonsai_ewm/session.py` | state tracker + context proposer + turn loop + persistent sessions (save/restore/list/diff by content key) |
| CLI | `bonsai_ewm/cli.py` | the REPL |
| `memory_tokens` / `displacement_tokens` | `bonsai_ewm/adapters.py` | full memory and the D-part novelty filter |
| ewm-sm crates | sibling `ewm-state-machine` repo | unchanged |
| PrismML llama.cpp | `~/tools/Bonsai-demo` | unchanged |

Everything in `bonsai_ewm` is Python stdlib only; the lattice and the model
are external processes connected by JSON/HTTP.

## 4. The context proposal

A proposal is a triple `(mode, cap, detokenize)`:

| Mode | tids that enter the prefix | Use |
| --- | --- | --- |
| `full` | `memory_tokens(materialize(S))`, last `cap` | baseline transcript memory |
| `compact` | `displacement_tokens` history, last `cap` | novelty-only; repeats collapse |
| `auto` | Jev (TypeSafe System One) decides mode + cap each turn from trajectory features | learned context policy; mock fallback without `TYPESAFE_API_KEY` |
| `surprise` | D-part plus the full tids of frames whose Noether indicators cross their thresholds | keeps only structurally surprising content |

The `surprise` detector flags a transition between frame `t` and `t+1`
when any of its Noether indicators crosses its threshold: `dp` above
(departed atoms), `ind1` above (departure dominates), `ind3` above (new
dominates), or `ind2` **below** (retention-chain BSS collapses). Thresholds
are per-session policy (`/surprise`) with defaults
`dp=6, ind1=0.5, ind2=0.5, ind3=0.5`. Flagged frames re-inject their full
tid lists after the D-part; nothing flagged degenerates to `compact`.

Per turn the controller records `prefix_tokens` and Bonsai's own
`prompt_tokens`, making the context a measurable, switchable artifact.

## 5. Persistent sessions

A session's lattice state `S(t)` has a content key (`ewm-scene ingest`).
The controller stores saved sessions in
`$BONSAI_EWM_WORK/sessions/<key>/{union.jsonl,meta.json}` — the union
frames that define `S(t)` plus the conversation metadata (turn count,
policy, history). `/load <key>` restores `S(t)` and rebuilds the derived
state (seen set, D-part stream, frame tids, full memory) by replaying the
union. `/diff` compares two sessions' final HLLSets by writing them as a
two-frame file and running `ewm-scene bss` + `ewm-scene noether` — BSS and
Jaccard between the two states, plus their D/R/N decomposition.

## 6. Distribution model

- **Local**: `pip install .` + the two scripts (`build_ewm_scene.sh`,
  `start_bonsai_server.sh`).
- **Podman**: multi-stage `container/Containerfile` — stage 1 builds
  `ewm-scene` from a local copy of the `ewm-state-machine` repo placed in
  the build context (clone it first for a git URL), stage 2 installs the
  stdlib-only controller. A `.containerignore` keeps the parent-directory
  context small. Bonsai stays out of the image (GPU host / sidecar
  container) and is reached via `BONSAI_URL`; the image carries a
  `bonsai-ewm --health` HEALTHCHECK.

## 7. Roadmap

1. ✅ Jev decides the proposal mode and cap per turn (`/context auto`).
2. ✅ `surprise` proposal mode (D-part + Noether-flagged frame tids).
3. ✅ Persistent, addressable sessions (content keys + save/restore/diff).
4. ✅ Distribution polish: `--health` check, CI workflow, tagged release
   `v0.2.0` (first `podman build` verified on this machine).
