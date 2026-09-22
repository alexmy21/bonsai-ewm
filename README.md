# bonsai-ewm — Bonsai 2 27B through the ewm-sm lattice

A **collaborative context manager**: the PrismML Bonsai 2 27B reasoning
model answers the user, and the ewm-state-machine lattice manages what
context Bonsai sees. The context is not a fixed transcript — it is a
**proposal** recomputed from `S(t)` every turn.

```
query → lattice state S(t-1) → context proposal → Bonsai → new lattice state S(t) → …
```

The architecture is documented in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
End users should start with the [docs/USER_GUIDE.md](docs/USER_GUIDE.md) —
every command, typical scenarios, and known limitations.
Machine-specific setup and the next-tasks list live in
[docs/SESSION_HANDOFF.md](docs/SESSION_HANDOFF.md) — a fresh session needs
nothing more than that file.

## Components

| Piece | Where | Role |
| --- | --- | --- |
| `bonsai-ewm` CLI | this repo (`src/bonsai_ewm`) | the controller + REPL (stdlib only) |
| ewm-sm `ewm-scene` binary | built from the `ewm-state-machine` repo | the lattice apparatus (unchanged) |
| Bonsai 2 27B | PrismML llama.cpp fork | the base model (unchanged) |

## Quick start (local)

```bash
# 1. one-time: Bonsai demo (llama.cpp binaries + 27B GGUF, ~8 GB)
git clone https://github.com/PrismML-Eng/Bonsai-demo.git ~/tools/Bonsai-demo
cd ~/tools/Bonsai-demo && BONSAI_OPENWEBUI=0 BONSAI_CODE_INTERPRETER=0 ./setup.sh

# 2. one-time: build the ewm-scene binary from the sibling ewm-state-machine repo
./scripts/build_ewm_scene.sh   # or: EWM_SCENE_BIN=/path/to/ewm-scene

# 3. start Bonsai's OpenAI-compatible server (do NOT set CUDA_VISIBLE_DEVICES)
./scripts/start_bonsai_server.sh

# 4. the collaborative CLI
python3 -m bonsai_ewm.cli
```

Then:

```text
ewm-bonsai> /context compact
ewm-bonsai> What is the capital of France? Answer in one short sentence.
ewm-bonsai> /state
ewm-bonsai> /history
ewm-bonsai> /quit
```

Commands: `/context full|compact|surprise|auto`, `/cap N`,
`/surprise [dp N|ind1 F|ind2 F|ind3 F]`, `/policy`, `/state`,
`/history`, `/save`, `/sessions`, `/load <key>`, `/diff <key> [<key>]`,
`/reset`, `/help`, `/quit`. In `auto` mode, TypeSafe **Jev** decides the
proposal (mode + cap) each turn and the decision is shown and recorded.
In `surprise` mode, the proposal is the D-part plus the full tids of frames
whose Noether indicators cross their thresholds — only structurally
surprising content reaches Bonsai.

## Configuration

| Env | Default | Purpose |
| --- | --- | --- |
| `BONSAI_URL` | `http://127.0.0.1:8081` | Bonsai llama.cpp server |
| `EWM_SCENE_BIN` | sibling repo or `ewm-scene` on PATH | the lattice binary |
| `BONSAI_EWM_WORK` | `~/.cache/bonsai-ewm` | session work dir (union JSONL, state, saved sessions) |
| `TYPESAFE_API_KEY` | unset → mock Jev | real TypeSafe System One decisions |

## Sessions

`S(t)` has a content key (from `ewm-scene ingest`). `/save` stores the
current session under that key; `/load <key>` restores it; `/sessions`
lists saved sessions; `/diff <key>` diffs the current `S(t)` against a
saved one (or `/diff <keyA> <keyB>` diffs two saved sessions) by their
HLLSets — BSS/Jaccard plus the D/R/N decomposition between the two final
states.

## Podman

The controller ships as a small container (Python + `ewm-scene` binary);
Bonsai runs on the host (GPU) or in a sidecar container. See
[container/README.md](container/README.md).

```bash
# from the directory that contains both repos
podman build --format docker \
  --ignorefile bonsai-ewm/container/.containerignore \
  --build-arg EWM_SM_SRC=ewm-state-machine \
  --build-arg CONTROLLER_SRC=bonsai-ewm \
  -f bonsai-ewm/container/Containerfile \
  -t bonsai-ewm .
podman run --rm -it -e BONSAI_URL=http://host.containers.internal:8081 bonsai-ewm
```

## Layout

```text
bonsai-ewm/
├── pyproject.toml
├── src/bonsai_ewm/
│   ├── adapters.py        # BonsaiAdapter + memory/displacement token helpers
│   ├── ewm.py             # EwmScene subprocess client
│   ├── session.py         # BonsaiSession — the collaborative controller
│   └── cli.py             # the ewm-bonsai REPL
├── scripts/
│   ├── build_ewm_scene.sh
│   └── start_bonsai_server.sh
├── container/
│   ├── Containerfile
│   └── README.md
├── tests/
│   ├── test_adapters.py   # tid helper tests
│   └── test_session.py    # surprise + persistent session tests
└── docs/
    ├── USER_GUIDE.md      # end-user guide: commands, scenarios, limitations
    ├── ARCHITECTURE.md    # how the collaborative model works
    └── SESSION_HANDOFF.md # machine facts + next tasks for a fresh session
```

## Roadmap

1. ✅ Jev decides the proposal mode and cap per turn (`/context auto`,
   real TypeSafe API when `TYPESAFE_API_KEY` is set, mock otherwise).
2. ✅ `surprise` proposal mode (D-part + tids from frames whose Noether
   indicators cross their thresholds).
3. ✅ Persistent, addressable sessions (content keys + save/restore/list +
   HLLSet diff of two sessions).
4. ✅ Distribution polish: `bonsai-ewm --health`, podman HEALTHCHECK,
   CI workflow (`.github/workflows/ci.yml`), tagged release `v0.2.0`.
