# ewm.py — the ewm-scene subprocess client (stdlib only).
#
# This is the only module that talks to the Rust lattice apparatus. It is a
# thin wrapper over the ewm-scene CLI: JSON in, JSON out. The binary is
# resolved from EWM_SCENE_BIN, then PATH, then the sibling
# ewm-state-machine repo.

from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Optional

SIBLING_BIN = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    "ewm-state-machine",
    "target",
    "release",
    "ewm-scene",
)


def resolve_bin() -> str:
    env = os.environ.get("EWM_SCENE_BIN")
    if env:
        return env
    on_path = shutil.which("ewm-scene")
    if on_path:
        return on_path
    if os.path.exists(SIBLING_BIN):
        return SIBLING_BIN
    return "ewm-scene"  # let subprocess raise a clear error


class EwmScene:
    """Thin subprocess client for the ewm-scene CLI."""

    def __init__(self, bin_path: Optional[str] = None, timeout: int = 600):
        self.bin = bin_path or resolve_bin()
        self.timeout = timeout

    def __call__(self, *args) -> dict:
        r = subprocess.run(
            [self.bin, *args], capture_output=True, text=True, timeout=self.timeout
        )
        if r.returncode != 0:
            raise RuntimeError(f"ewm-scene failed: {r.stderr[-800:]}")
        return json.loads(r.stdout.strip())

    def ingest(self, path: str) -> dict:
        return self("ingest", path)

    def bss(self, path: str) -> dict:
        return self("bss", path)

    def materialize(self, path: str) -> dict:
        return self("materialize", path)

    def noether(self, path: str) -> dict:
        return self("noether", path)

    def project(self, path: str, frame_path: str) -> dict:
        return self("project", path, "--frame", frame_path)

    def pyramid(self, path: str) -> dict:
        return self("pyramid", path)
