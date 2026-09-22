#!/bin/sh
# Build (or locate) the ewm-scene binary from the sibling ewm-state-machine repo.
# The lattice apparatus is unchanged; bonsai-ewm only consumes its JSON protocol.
set -e

SIBLING="$(cd "$(dirname "$0")/../.." && pwd)/ewm-state-machine"
echo $SIBLING

if [ -n "$EWM_SCENE_BIN" ]; then
    echo "using EWM_SCENE_BIN=$EWM_SCENE_BIN"
    exit 0
fi

if [ -x "$SIBLING/target/release/ewm-scene" ]; then
    echo "ewm-scene already built: $SIBLING/target/release/ewm-scene"
    echo "export EWM_SCENE_BIN=$SIBLING/target/release/ewm-scene"
    exit 0
fi

if [ -d "$SIBLING" ]; then
    echo "building ewm-scene from $SIBLING ..."
    (cd "$SIBLING" && cargo build --release -p ewm-scene)
    echo "export EWM_SCENE_BIN=$SIBLING/target/release/ewm-scene"
    exit 0
fi

echo "error: ewm-state-machine repo not found at $SIBLING" >&2
echo "set EWM_SCENE_BIN=/path/to/ewm-scene or clone the repo next to this project" >&2
exit 1
