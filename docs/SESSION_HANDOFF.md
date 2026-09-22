# Session handoff — everything a fresh session needs

Start here: **"Continue the bonsai-ewm project per this handoff."**
Project root: `/home/alexmy/SGS/SGS_lib/fractal_manifold_gen2/bonsai-ewm`
End-user guide (commands, scenarios, limitations): `docs/USER_GUIDE.md`.
Research origin: `/home/alexmy/SGS/SGS_lib/fractal_manifold_gen2/ewm-state-machine`
(notebooks 08–20 + `trainer/` package + `docs/BONSAI_COLLAB.md`).

## 1. What bonsai-ewm is

Bonsai 2 27B (PrismML ternary weights, llama.cpp fork) as the **base model**;
ewm-sm as its **collaborative context manager**. The context Bonsai sees is a
*proposal* recomputed every turn from the HLLSet lattice:

```
query → lattice state S(t-1) → context proposal (full|compact) → Bonsai → new S(t) → …
```

Architecture: `docs/ARCHITECTURE.md`. Roadmap: `README.md`.

## 2. Machine facts (this workstation)

- **GPUs**: `nvidia-smi` shows `0 = Quadro M1200 (4 GB, display)`,
  `1 = RTX 3060 (12 GB, compute)`. The PrismML llama.cpp fork orders them
  **opposite** (`CUDA0 = RTX 3060`) — never set `CUDA_VISIBLE_DEVICES` for
  llama.cpp. `~/.bashrc` already exports `CUDA_VISIBLE_DEVICES=0` (hides the
  M1200 from torch/llama; the notebooks override it themselves).
- **Bonsai**: `/home/alexmy/tools/Bonsai-demo` — PrismML llama.cpp binaries
  (`bin/cuda/llama-server`) + model
  `models/bonsai2-gguf/27B/Ternary-Bonsai-2-27B-PQ2_0.gguf` (7.2 GB) +
  `Ternary-Bonsai-2-27B-mmproj-Q8_0.gguf`. ~8 tok/s on the 3060, health at
  `http://127.0.0.1:8081/health`.
- **ewm-sm**: sibling repo `../ewm-state-machine`; binary already built at
  `target/debug/ewm-scene` (release: `cargo build --release -p ewm-scene`).
- **Laya** (open-source Jev alternative, used in notebooks 16–18):
  daemon `/home/alexmy/tools/laya-rust/target/release/laya-jsonl` (CPU,
  ~600 ms/decision; CUDA build blocked by nvcc 12.8 PTX ISA 8.7 vs driver
  565.77 ≤ 12.7), checkpoint `/home/alexmy/.cache/laya/typed-decisions`.
- **Heterogeneous captures** (notebook 15/18):
  `/home/alexmy/.cache/ewm-hetero/capture_{ocr,vla,jepa}.jsonl` +
  `captures/capture_*.py` scripts in ewm-state-machine (each runs in its
  native env: `deepseek-ocr`, `ewm-vla` venv, `ewm-jepa`).
- **TypeSafe Jev**: the API key has **arrived** and is exported in
  `~/.bashrc` from `bonsai-ewm/docs/notes/api-keys.txt` (gitignored).
  Verified live: model `jev-1.13.0`, ~0.5–0.7 s/decision. `bonsai_ewm`
  has a stdlib-only `JevAdapter` (REST `/v1/systemone`) + `/context auto`;
  `ewm-state-machine` notebooks 13/14 use the key via `TYPESAFE_API_KEY`
  automatically. Laya remains the offline/local fallback.

## 3. Run commands

```bash
# Bonsai server (leave running while developing)
cd /home/alexmy/tools/Bonsai-demo
LD_LIBRARY_PATH="$PWD/bin/cuda" ./bin/cuda/llama-server \
  -m models/bonsai2-gguf/27B/Ternary-Bonsai-2-27B-PQ2_0.gguf \
  -ngl 99 -fa on -c 2048 --host 127.0.0.1 --port 8081

# The collaborative CLI (from the bonsai-ewm repo)
cd /home/alexmy/SGS/SGS_lib/fractal_manifold_gen2/bonsai-ewm
EWM_SCENE_BIN=../ewm-state-machine/target/debug/ewm-scene \
  PYTHONPATH=src python3 -m bonsai_ewm.cli

# or installed: pip install . && bonsai-ewm
# podman: see container/README.md (podman 5.3.1 available)
```

CLI: `/context full|compact|surprise|auto`, `/cap N`,
`/surprise [dp N|ind1 F|ind2 F|ind3 F]`, `/policy`, `/state`,
`/history`, `/save`, `/sessions`, `/load <key>`, `/diff <key> [<key>]`,
`/reset`, `/help`, `/quit`. Non-interactive flags: `bonsai-ewm --health`,
`--help`.

## 4. Current status and next tasks

Done: project scaffolded and smoke-tested; `full` + `compact` context
proposal modes; per-turn `prompt_tokens` reporting; **`auto` proposal —
real TypeSafe Jev decides mode+cap per turn** (stdlib-only REST adapter,
mock fallback); **`surprise` proposal mode** (D-part + tids from frames
whose Noether indicators cross thresholds, tunable via `/surprise`);
**persistent, addressable sessions** (`/save`, `/load`, `/sessions`,
`/diff` — save/restore S(t) by content key, diff two sessions by their
HLLSets); stdlib-only unittest suite (`python3 -m unittest discover -s tests`);
**first `podman build` verified** — `bonsai-ewm:0.2.0` image built in
docker format with a `bonsai-ewm --health` HEALTHCHECK (build command in
`container/README.md`); CI workflow (`.github/workflows/ci.yml`) and tag
`v0.2.0` in place.

Next, in priority order:

1. **Jev + surprise policy** — include Noether trajectory features in the
   auto advisor's state so Jev can pick `surprise` with informed thresholds.
2. **Session diff polish** — per-frame D/R/N diff timelines (not just the
   final states), and `ewm-git`-backed content addressing if the research
   line converges on it.
3. **Push + release** — add a remote, push `main` and `v0.2.0`, and let the
   CI workflow build and tag the container image on releases.

## 5. Invariants to preserve

- ewm-sm crates are never modified; only the `ewm-scene` JSON protocol and
  the llama.cpp HTTP API are used.
- `bonsai_ewm` stays Python-stdlib-only; Bonsai and ewm-sm stay external
  processes.
- The research line (ewm-state-machine notebooks + trainer) and the
  production line (bonsai-ewm) evolve independently; port lessons, not code
  churn.
