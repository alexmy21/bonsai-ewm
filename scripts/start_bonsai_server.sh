#!/bin/sh
# Start the PrismML Bonsai llama.cpp server (OpenAI-compatible) for bonsai-ewm.
#
# IMPORTANT (verified on this machine): the PrismML llama.cpp fork lists the
# RTX 3060 as CUDA0 and the Quadro M1200 as CUDA1 — the opposite of
# nvidia-smi. Do NOT set CUDA_VISIBLE_DEVICES; CUDA0 is the RTX 3060.
set -e

BONSAI_DEMO_DIR="${BONSAI_DEMO_DIR:-$HOME/tools/Bonsai-demo}"
PORT="${BONSAI_PORT:-8081}"
CTX="${BONSAI_CTX:-2048}"
NGL="${BONSAI_NGL:-99}"

if [ ! -x "$BONSAI_DEMO_DIR/bin/cuda/llama-server" ]; then
    echo "error: $BONSAI_DEMO_DIR/bin/cuda/llama-server not found" >&2
    echo "run the PrismML setup first: git clone https://github.com/PrismML-Eng/Bonsai-demo.git" >&2
    exit 1
fi

MODEL="$BONSAI_DEMO_DIR/models/bonsai2-gguf/27B/Ternary-Bonsai-2-27B-PQ2_0.gguf"
if [ ! -f "$MODEL" ]; then
    echo "error: model not found: $MODEL" >&2
    exit 1
fi

exec env -u CUDA_VISIBLE_DEVICES LD_LIBRARY_PATH="$BONSAI_DEMO_DIR/bin/cuda" \
    "$BONSAI_DEMO_DIR/bin/cuda/llama-server" \
    -m "$MODEL" -ngl "$NGL" -fa on -c "$CTX" \
    --host 127.0.0.1 --port "$PORT"
