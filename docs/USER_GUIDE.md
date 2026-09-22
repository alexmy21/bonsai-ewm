# bonsai-ewm User Guide

This guide is written for the **end user** — someone who wants to talk to
Bonsai through the ewm-sm lattice without needing to know how HLLSets work.
It covers every command, typical scenarios, and the current version's known
limitations.

---

## 1. What bonsai-ewm is

`bonsai-ewm` is a chat application with a difference: before every answer,
a small controller **chooses what Bonsai remembers**. The conversation is
not a fixed transcript — it is a **context proposal** rebuilt every turn
from a compressed lattice state `S(t)`.

```text
you type a question
      → the lattice state S(t-1) is read
      → a context proposal is built (full | compact | surprise | auto)
      → Bonsai answers over that context
      → the answer is ingested back into S(t)
```

Why this matters for you:

- Long conversations stay affordable — the context budget is explicit.
- Repetitive content collapses; genuinely new content survives.
- You can switch memory strategies mid-conversation and compare them.
- Sessions can be **saved, restored, and diffed** by a content key.

Bonsai itself is the PrismML **Bonsai 2 27B** reasoning model running
locally through a llama.cpp fork. The controller talks to it over HTTP;
the lattice apparatus is a small Rust binary called `ewm-scene`.

---

## 2. Before you start

You need three things running/available:

| Piece | Where | How |
| --- | --- | --- |
| Bonsai server | `~/tools/Bonsai-demo` | `./scripts/start_bonsai_server.sh` |
| `ewm-scene` binary | sibling `ewm-state-machine` repo | `./scripts/build_ewm_scene.sh` |
| the CLI | this repo | `pip install . && bonsai-ewm` (or `PYTHONPATH=src python3 -m bonsai_ewm.cli`) |

Do **not** set `CUDA_VISIBLE_DEVICES` when starting Bonsai — on this
machine the PrismML fork lists the GPUs in the opposite order from
`nvidia-smi`.

---

## 3. Starting the CLI

```bash
bonsai-ewm
```

You should see:

```text
bonsai-ewm — Bonsai 2 27B through the ewm-sm lattice
  bonsai server: http://127.0.0.1:8081  health=ok
  lattice: /home/alexmy/.../ewm-scene
  jev advisor: real (TypeSafe API)        # or: mock (no TYPESAFE_API_KEY)
  /context full|compact|surprise|auto   /cap N   /surprise [dp N|ind1 F|ind2 F|ind3 F]
  /policy   /state   /history   /save   /sessions   /load <key>   /diff <key> [<key>]
  /reset   /help   /quit
```

Then just type a question:

```text
bonsai-ewm> What is the capital of France? Answer in one short sentence.
  [full cap=24] prefix_tids=  0  prompt_tokens=  21  answer='The capital of France is Paris.'
```

The line above means: the `full` proposal was used with a cap of 24 tids,
0 prefix tids were sent on the first turn, Bonsai reported 21 prompt
tokens, and the answer is shown.

---

## 4. Command reference

### 4.1 Choosing the context proposal

| Command | Effect |
| --- | --- |
| `/context full` | Bonsai sees the full materialized memory (last `cap` tids). Baseline mode. |
| `/context compact` | Bonsai sees only tids that have **never been seen before** (the D-part). Repeats collapse to nothing. |
| `/context surprise` | Bonsai sees the D-part **plus** full frames whose Noether indicators crossed a threshold — only structurally surprising content. |
| `/context auto` | **Jev** (TypeSafe System One) picks the mode and cap every turn. With `TYPESAFE_API_KEY` set, it uses the real API; otherwise a deterministic mock. |
| `/cap N` | Set the context budget to the last `N` tids (any mode). `N` must be ≥ 1. |

Examples:

```text
bonsai-ewm> /context compact
  context proposal: compact, cap=24

bonsai-ewm> /cap 12
  context proposal: compact, cap=12
```

### 4.2 Tuning `surprise`

```text
/surprise
/surprise dp 8 ind1 0.5 ind2 0.4 ind3 0.6
```

A transition between two turns is flagged as surprising when any of its
Noether indicators crosses its threshold:

| Indicator | Meaning | Surprising when |
| --- | --- | --- |
| `dp` | atoms that departed (content dropped) | above threshold |
| `ind1` | departure dominates retained+new | above threshold |
| `ind3` | new content dominates retained+departed | above threshold |
| `ind2` | retention-chain similarity | **below** threshold (structure collapsed) |

Defaults: `dp=6, ind1=0.5, ind2=0.5, ind3=0.5`.

### 4.3 Looking at the state

| Command | Effect |
| --- | --- |
| `/policy` | Show the current proposal policy (mode, cap, surprise thresholds). |
| `/state` | Show `S(t)`: popcount, content key, memory sizes, last Noether indicators, surprise thresholds and flagged frames. |
| `/history` | Per-turn record: mode, cap, prefix tids, `prompt_tokens`, popcount, answer preview. |

```text
bonsai-ewm> /state
  turn=3  S(t) pop=9  key=h:44043290d267…
  memory: full=5 tids  compact(D-part)=5 tids
  noether: dp=0 ind1=0.0 ind2=0.5 ind3=0.5
  surprise thresholds: {'dp': 6.0, 'ind1': 0.5, 'ind2': 0.5, 'ind3': 0.5}
  surprise frames: [1, 2]
  policy: mode=full cap=24
```

### 4.4 Saving, restoring and diffing sessions

| Command | Effect |
| --- | --- |
| `/save` | Save the current `S(t)` under its **content key** (a hash of the lattice state). Also stores the conversation history and policy. |
| `/sessions` | List saved sessions (key, turn count, save time). Alias: `/list`. |
| `/load <key>` | Restore a saved session by key. This **replaces** the current session. |
| `/diff <key>` | Diff the current session against a saved one by their final HLLSets. |
| `/diff <keyA> <keyB>` | Diff two saved sessions. |

A diff reports BSS/Jaccard similarity and the D/R/N decomposition between
the two final states:

```text
bonsai-ewm> /diff h:0332701d
  diff  current -> h:0332701d
    a: pop=9 key=h:44043290d267…
    b: pop=9 key=h:0332701d…
    bss(A,B)=0.667  jaccard=0.500
    departed=3  retained=6  new=3
```

### 4.5 Utility commands

| Command | Effect |
| --- | --- |
| `/help` | Show the command summary. |
| `/reset` | Clear the session (lattice state + history). Cannot be undone. |
| `/quit` (or `/exit`) | Exit. |

### 4.6 Non-interactive flags

| Flag | Effect |
| --- | --- |
| `bonsai-ewm --help` | Print usage and exit 0. |
| `bonsai-ewm --health` | Print a JSON health report (ewm-scene binary, work dir, Bonsai reachability) and exit 0 only when everything is OK. |

```bash
bonsai-ewm --health
{
  "ok": true,
  "version": "0.2.0",
  "ewm_scene": "/usr/local/bin/ewm-scene",
  "ewm_scene_ok": true,
  "work_dir": "/home/alexmy/.cache/bonsai-ewm",
  "work_dir_ok": true,
  "bonsai_url": "http://127.0.0.1:8081",
  "bonsai_ok": true
}
```

---

## 5. Typical scenarios

### Scenario A — first conversation (default mode)

```text
bonsai-ewm> What is the capital of France? Answer in one short sentence.
  [full cap=24] prefix_tids=  0  prompt_tokens=  21  answer='The capital of France is Paris.'
bonsai-ewm> What river runs through it? Answer in one short sentence.
  [full cap=24] prefix_tids=  9  prompt_tokens=  44  answer='The Seine.'
```

Note how `prefix_tids` grows on turn 2 — Bonsai now sees a context prefix
built from turn 1.

### Scenario B — long conversation, switch to compact

After many turns, `prompt_tokens` keeps growing in `full` mode:

```text
bonsai-ewm> /context compact
  context proposal: compact, cap=24
bonsai-ewm> Summarize what we know so far.
  [compact cap=24] prefix_tids= 24  prompt_tokens=  87  answer='...'
```

Only never-seen content survives, so repeated vocabulary stops costing
prompt tokens.

### Scenario C — comparing proposals on the same question

Ask the same question under different modes and watch `prompt_tokens`:

```text
bonsai-ewm> /context full
bonsai-ewm> What did I ask about first?
bonsai-ewm> /context compact
bonsai-ewm> What did I ask about first?
bonsai-ewm> /context surprise
bonsai-ewm> What did I ask about first?
bonsai-ewm> /history
```

This is the interactive version of the A/B experiment from the research
notebooks — a live context lab.

### Scenario D — saving and restoring a conversation

```text
bonsai-ewm> /save
  saved S(t) under key h:44043290d267255c81f9cf53571dea7c278bc0bd (turn=6)
bonsai-ewm> /quit
```

Tomorrow, in a new session (same `BONSAI_EWM_WORK` directory):

```text
bonsai-ewm> /sessions
  key=h:44043290d267255c81f9cf53571dea7c278bc0bd  turn=6  saved=2026-09-22 17:38
bonsai-ewm> /load h:44043290d267255c81f9cf53571dea7c278bc0bd
  restored S(t) from key h:44043290d267255c81f9cf53571dea7c278bc0bd (turn=6)
bonsai-ewm> /history
```

The lattice state, the D-part stream, the policy and the conversation
history are all restored.

### Scenario E — diffing two sessions

Work through one topic and `/save`; then `/reset` and work through a
related topic; then compare the two final states:

```text
bonsai-ewm> /diff h:keyA h:keyB
  diff  h:keyA -> h:keyB
    a: pop=9 key=h:keyA…
    b: pop=9 key=h:keyB…
    bss(A,B)=0.667  jaccard=0.500
    departed=3  retained=6  new=3
```

- `departed` = atoms only in A.
- `retained` = atoms in both.
- `new` = atoms only in B.

### Scenario F — let Jev drive (`auto`)

```text
bonsai-ewm> /context auto
bonsai-ewm> Explain gravity in one sentence.
  [compact cap=8] prefix_tids= 24  prompt_tokens=  92  answer='...'
  jev-advice: compact (conf=0.61, keep_short=0.82, mock=False)
```

Each turn, the advisor's decision is printed and recorded. Without
`TYPESAFE_API_KEY` the advisor is a deterministic mock — fine for trying
the flow, not for real routing.

### Scenario G — running in a container

```bash
# build (see container/README.md)
podman build --format docker \
  --ignorefile bonsai-ewm/container/.containerignore \
  --build-arg EWM_SM_SRC=ewm-state-machine \
  --build-arg CONTROLLER_SRC=bonsai-ewm \
  -f bonsai-ewm/container/Containerfile -t bonsai-ewm .

# run against Bonsai on the host
podman run --rm -it \
  -e BONSAI_URL=http://host.containers.internal:8081 \
  bonsai-ewm
```

The image carries a HEALTHCHECK that runs `bonsai-ewm --health` every
30 s.

---

## 6. Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `BONSAI_URL` | `http://127.0.0.1:8081` | Bonsai llama.cpp server |
| `EWM_SCENE_BIN` | sibling repo or `ewm-scene` on PATH | lattice binary |
| `BONSAI_EWM_WORK` | `~/.cache/bonsai-ewm` | work dir: union JSONL, state, saved sessions |
| `TYPESAFE_API_KEY` | unset → mock Jev | real TypeSafe System One decisions in `auto` |

---

## 7. Known limitations in v0.2.0

### REPL ergonomics (key shortcuts)

- **No persistent command history across restarts.** Arrow-up history may
  work inside a single session when the `readline` module is available,
  but nothing is saved when you quit.
- **No tab completion** for commands or saved session keys.
- **Ctrl-C behavior is basic.** Pressing Ctrl-C at the prompt exits the
  whole CLI instead of just clearing the current line; pressing Ctrl-C
  while Bonsai is still thinking may abort with a traceback — there is no
  cancellation of an in-flight request.
- **No multi-line input.** Each query is one line; there is no paste
  mode or continuation (`\` does not continue a line).
- **No editing of a previous query.** You cannot recall and edit a past
  line (`/history` shows records, it does not let you resend them).

### Destructive actions have no confirmation

- `/reset` clears everything immediately; there is no undo.
- `/load <key>` overwrites the current session immediately, even if it has
  unsaved turns. Save first if you want to keep the current state.
- There is no "unsaved changes" warning on `/quit`.

### Session and context behavior

- **`auto` without `TYPESAFE_API_KEY` is a mock**, not a real advisor. Its
  choices are deterministic but meaningless for production use.
- **`surprise` thresholds are manual and fixed.** There is no adaptive
  threshold (e.g., mean + 3σ over the trajectory) yet; you tune them with
  `/surprise`.
- **`/diff` compares only the two final states**, not the per-turn
  timeline between sessions.
- **Content-key addressing means same state = same address.** Saving two
  different conversations that converge to the same `S(t)` will overwrite
  the earlier session's metadata.
- **The `cap` is measured in tids** (Bonsai tokens), not words or
  characters; a cap of 24 may be a very different amount of text
  depending on the content.
- **Very short answers** (one or two tokens) hit a known limitation of the
  ewm-scene materializer; the controller falls back to the raw tokens so
  the session keeps working, but the "restored order" path is not used in
  that case.
- **`/history` answer previews are truncated** to 50 characters; the full
  answer text is not stored in a browsable way (full answers are kept in
  saved session metadata, not displayed by a command).

### No streaming / display niceties

- **Answers appear all at once** after Bonsai finishes; there is no
  token-by-token streaming.
- **No Markdown rendering** in the terminal; reasoning is captured but
  not shown by default.
- **The reasoning trace is recorded but not printed** by any current
  command.

### Operational

- **Bonsai is not started for you.** The CLI assumes the server is
  already running; it prints `health=DOWN` and keeps going otherwise (you
  will get connection errors when asking a question).
- **One Bonsai server, one controller.** There is no queueing or session
  multiplexing; two CLIs against the same server share the model but not
  the lattice state.
- **Sessions are local files** under `BONSAI_EWM_WORK`; there is no
  sync/export command yet (you can copy the `sessions/` directory
  manually).

---

## 8. Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `health=DOWN` at startup | Bonsai server not running | run `./scripts/start_bonsai_server.sh` in another terminal |
| `ewm-scene: No such file` | binary not built / not on PATH | `./scripts/build_ewm_scene.sh` or set `EWM_SCENE_BIN` |
| `unknown mode ...` | typo in `/context` | use `full`, `compact`, `surprise` or `auto` |
| `usage: /cap N` | non-positive or missing cap | `/cap 24` |
| `cannot save: no session state to save` | no turns yet | ask a question first |
| `no session saved under key ...` | wrong/absent key | use `/sessions` and copy the full key |
| `jev advisor: mock` | `TYPESAFE_API_KEY` not set | export the key (see `docs/notes/api-keys.txt`) or accept mock |
| Empty context prefix | first turn, or cap too small / mode filters everything | ask again; try `/context full` |
| Bonsai answers slowly | model on GPU, prompt-cache cold | warm-up queries are normal; keep the server running |
| Crash on a short answer | (controller now handles this) | update to v0.2.0+; older versions crashed |
