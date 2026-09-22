# session.py — BonsaiSession: the collaborative controller.
#
# One session = one lattice state S(t) + one context-proposal policy + one
# Bonsai server. Every turn the controller proposes a context, Bonsai
# reasons over it, and the answer is ingested back into the lattice.
#
# Sessions are also *addressable artifacts*: the current lattice state S(t)
# has a content key (reported by `ewm-scene ingest`), and a session can be
# saved under that key, restored by it, and diffed against another session
# by their HLLSets (D/R/N + BSS/Jaccard of the two final states).

from __future__ import annotations

import copy
import json
import os
import shutil
import tempfile
import time
from dataclasses import asdict, dataclass
from typing import Optional

from .adapters import BonsaiAdapter, JevAdapter, displacement_tokens, memory_tokens
from .ewm import EwmScene

# Noether surprise thresholds. A transition between frame t and frame t+1 is
# surprising when any of its indicators crosses its threshold:
#
#   dp   > surprise.dp    (departed atoms — content dropped)
#   ind1 > surprise.ind1  (departure dominates retained+new)
#   ind3 > surprise.ind3  (new dominates retained+departed)
#   ind2 < surprise.ind2  (retention BSS collapses — structure changed)
#
# ind2 is a similarity, so *below* the threshold is the surprising side.
SURPRISE_DEFAULTS = {"dp": 6, "ind1": 0.5, "ind2": 0.5, "ind3": 0.5}


def _dedup_consecutive(tids: list[str]) -> list[str]:
    """Drop consecutive duplicates, like materialized memory restoration."""
    out: list[str] = []
    for t in tids:
        if not out or out[-1] != t:
            out.append(t)
    return out


@dataclass
class TurnRecord:
    turn: int
    query: str
    mode: str
    cap: int
    prefix_tokens: int
    prompt_tokens: int
    answer: str
    reasoning: str
    pop: int
    key: str
    advice: Optional[dict] = None


class BonsaiSession:
    def __init__(
        self,
        bonsai: BonsaiAdapter,
        ewm: EwmScene,
        work_dir: str,
        max_tokens: int = 128,
        temperature: float = 0.0,
        jev: Optional[JevAdapter] = None,
    ):
        self.bonsai = bonsai
        self.ewm = ewm
        self.jev = jev or JevAdapter()
        self.work_dir = work_dir
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.union_path = os.path.join(work_dir, "session_union.jsonl")
        self.sessions_dir = os.path.join(work_dir, "sessions")
        os.makedirs(work_dir, exist_ok=True)
        os.makedirs(self.sessions_dir, exist_ok=True)
        self.reset()

    def reset(self):
        with open(self.union_path, "w") as fh:
            fh.write("")
        self.seen: set = set()
        self.mem_tids: list[str] = []   # full materialized memory (restored order)
        self.comp_mem: list[str] = []   # D-part novelty stream
        self.frame_tids: list[list[str]] = []  # per-turn answer tids (frame i)
        self.turn = 0
        self.history: list[TurnRecord] = []
        self.policy = {
            "mode": "full",
            "cap": 24,
            "surprise": dict(SURPRISE_DEFAULTS),
        }
        self.effective = copy.deepcopy(self.policy)
        self.last_advice: Optional[dict] = None

    # ── context proposal ────────────────────────────────────────────────
    def _advise(self, query: str) -> dict:
        """Ask Jev how the next context should be built (mode + cap)."""
        state = {
            "turn": self.turn,
            "query": query,
            "union_pop": self._pop() if self.turn else 0,
            "full_memory_tids": len(self.mem_tids),
            "novelty_tids": len(self.comp_mem),
            "surprise_frames": len(self.surprise_frames()),
            "last_answer_chars": len(self.history[-1].answer) if self.history else 0,
        }
        r = self.jev.route(
            state,
            {
                "full": "keep the full materialized memory as the context",
                "compact": "keep only new, previously unseen tids as the context",
                "surprise": "keep only structurally surprising content (D-part plus Noether-flagged frames)",
            },
            "How should the next context be built for the base model?",
            extra_noul={"keep_short": "The context should be kept short"},
        )
        mode = r["decision"] if r["decision"] in ("full", "compact", "surprise") else "full"
        cap = 8 if r["aux"].get("keep_short", 0.0) > 0.5 else int(self.policy["cap"])
        advice = {
            "mode": mode,
            "cap": cap,
            "surprise": copy.deepcopy(self.policy["surprise"]),
            "jev": r,
        }
        self.last_advice = advice
        return advice

    def _pop(self) -> int:
        try:
            uni = self.ewm.ingest(self.union_path)
            frames = uni.get("frames", [])
            return int(frames[-1].get("pop", 0)) if frames else 0
        except Exception:
            return 0

    # ── surprise detection ──────────────────────────────────────────────
    def surprise_flags(self) -> list[bool]:
        """One flag per Noether transition; True = the transition is surprising.

        `ewm-scene noether` returns per-transition series over consecutive
        frames: `dp/rp/np/ind1/ind3` have one entry per transition,
        `ind2` starts at the second transition (retention-chain BSS).
        """
        if self.turn < 2:
            return []
        try:
            noe = self.ewm.noether(self.union_path)
        except Exception:
            return [False] * (self.turn - 1)
        thr = self.effective.get("surprise") or self.policy.get("surprise") or SURPRISE_DEFAULTS
        dp = noe.get("dp", [])
        ind1 = noe.get("ind1", [])
        ind2 = noe.get("ind2", [])
        ind3 = noe.get("ind3", [])
        flags = [False] * len(dp)
        for i in range(len(dp)):
            if dp[i] > float(thr.get("dp", 0)):
                flags[i] = True
            if ind1[i] > float(thr.get("ind1", 1.0)):
                flags[i] = True
            if ind3[i] > float(thr.get("ind3", 1.0)):
                flags[i] = True
            # ind2[i-1] is the retention BSS of transition i; low = surprising.
            if i >= 1 and i - 1 < len(ind2) and ind2[i - 1] < float(thr.get("ind2", 0.0)):
                flags[i] = True
        return flags

    def surprise_frames(self) -> list[int]:
        """1-based frame ids touched by a surprising transition."""
        flags = self.surprise_flags()
        frames: set = set()
        for i, flagged in enumerate(flags):
            if flagged:
                frames.add(i + 1)      # frame that the transition departs from
                frames.add(i + 2)      # frame that the transition arrives at
        return sorted(frames)

    def _surprise_tids(self, cap: int) -> list[str]:
        """The `surprise` proposal: D-part plus the full tids of frames whose
        Noether indicators crossed a threshold, deduped and capped."""
        d_part = self.comp_mem[-cap:] if cap > 0 else []
        extra: list[str] = []
        for frame in self.surprise_frames():
            idx = frame - 1
            if 0 <= idx < len(self.frame_tids):
                extra.extend(self.frame_tids[idx])
        return _dedup_consecutive(d_part + extra)[-cap:]

    # ── context proposal ────────────────────────────────────────────────
    def proposal_tids(self) -> list[str]:
        mode = self.effective["mode"]
        cap = int(self.effective["cap"])
        if mode == "full":
            return self.mem_tids[-cap:]
        if mode == "compact":
            return self.comp_mem[-cap:]
        if mode == "surprise":
            return self._surprise_tids(cap)
        raise ValueError(f"unknown context mode {mode!r}")

    def proposal_text(self) -> str:
        tids = self.proposal_tids()
        if not tids:
            return ""
        return self.bonsai.detokenize([int(t[3:]) for t in tids])

    # ── one turn of the collaboration loop ──────────────────────────────
    def ask(self, query: str) -> TurnRecord:
        advice = None
        if self.policy["mode"] == "auto":
            advice = self._advise(query)
            self.effective = {
                "mode": advice["mode"],
                "cap": advice["cap"],
                "surprise": advice["surprise"],
            }
        else:
            self.effective = copy.deepcopy(self.policy)

        mode = self.effective["mode"]
        cap = int(self.effective["cap"])
        prefix_tids = self.proposal_tids()
        if prefix_tids:
            prefix_text = self.bonsai.detokenize([int(t[3:]) for t in prefix_tids])
            prompt = f"Context memory ({mode}):\n{prefix_text}\n\nQuery: {query}"
        else:
            prompt = query

        full = self.bonsai.chat_full(prompt, max_tokens=self.max_tokens, temperature=self.temperature)
        answer = full["content"]
        reasoning = full["reasoning"]
        prompt_tokens = int(full["usage"].get("prompt_tokens", 0))

        tids = [f"tid{i}" for i in self.bonsai.tokenize(answer)]
        self.comp_mem.extend(displacement_tokens(self.seen, tids))
        self.frame_tids.append(tids)
        with open(self.union_path, "a") as fh:
            fh.write(json.dumps({"id": self.turn + 1, "tokens": tids}) + "\n")

        self.mem_tids = self._materialize_memory(tids)
        uni = self.ewm.ingest(self.union_path)
        frame = uni["frames"][-1]

        rec = TurnRecord(
            turn=self.turn,
            query=query,
            mode=mode,
            cap=cap,
            prefix_tokens=len(prefix_tids),
            prompt_tokens=prompt_tokens,
            answer=answer,
            reasoning=reasoning,
            pop=int(frame.get("pop", 0)),
            key=str(frame.get("key", "")),
            advice=advice,
        )
        self.history.append(rec)
        self.turn += 1
        return rec

    # ── persistent, addressable sessions ────────────────────────────────
    def session_key(self) -> Optional[str]:
        """The content key of the current lattice state S(t)."""
        uni = self.ewm.ingest(self.union_path)
        frames = uni.get("frames", [])
        if not frames:
            return None
        return str(frames[-1].get("key", "")) or None

    def _session_dir(self, key: str) -> str:
        return os.path.join(self.sessions_dir, key)

    def _saved_union_path(self, key: str) -> str:
        return os.path.join(self._session_dir(key), "union.jsonl")

    @staticmethod
    def _read_union_frames(path: str) -> list[dict]:
        frames: list[dict] = []
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if line:
                    frames.append(json.loads(line))
        return frames

    def save(self) -> dict:
        """Save S(t) (the union JSONL) under its content key."""
        key = self.session_key()
        if not key:
            raise ValueError("no session state to save (run at least one turn)")
        d = self._session_dir(key)
        os.makedirs(d, exist_ok=True)
        shutil.copyfile(self.union_path, os.path.join(d, "union.jsonl"))
        meta = {
            "key": key,
            "saved_at": time.time(),
            "turn": self.turn,
            "policy": copy.deepcopy(self.policy),
            "history": [asdict(rec) for rec in self.history],
        }
        with open(os.path.join(d, "meta.json"), "w") as fh:
            json.dump(meta, fh, indent=2)
        return {"key": key, "turn": self.turn, "path": d}

    def list_sessions(self) -> list[dict]:
        out: list[dict] = []
        for name in sorted(os.listdir(self.sessions_dir)):
            d = os.path.join(self.sessions_dir, name)
            union = os.path.join(d, "union.jsonl")
            if not os.path.isdir(d) or not os.path.exists(union):
                continue
            meta: dict = {}
            meta_path = os.path.join(d, "meta.json")
            if os.path.exists(meta_path):
                try:
                    with open(meta_path) as fh:
                        meta = json.load(fh)
                except Exception:
                    meta = {}
            out.append({
                "key": name,
                "turn": int(meta.get("turn", 0)),
                "saved_at": float(meta.get("saved_at", 0)),
                "policy": meta.get("policy", {}),
            })
        return out

    def load(self, key: str) -> dict:
        """Restore a saved session (S(t) + derived state + history) by key."""
        union = self._saved_union_path(key)
        if not os.path.exists(union):
            raise FileNotFoundError(f"no session saved under key {key!r}")
        shutil.copyfile(union, self.union_path)
        self._rebuild_from_union()
        self.history = []
        self.policy = {"mode": "full", "cap": 24, "surprise": dict(SURPRISE_DEFAULTS)}
        meta_path = os.path.join(self._session_dir(key), "meta.json")
        if os.path.exists(meta_path):
            try:
                with open(meta_path) as fh:
                    meta = json.load(fh)
                pol = meta.get("policy") or {}
                self.policy = {
                    "mode": pol.get("mode", "full"),
                    "cap": int(pol.get("cap", 24)),
                    "surprise": {**SURPRISE_DEFAULTS, **(pol.get("surprise") or {})},
                }
                fields = set(TurnRecord.__dataclass_fields__)
                self.history = [
                    TurnRecord(**{k: v for k, v in rec.items() if k in fields})
                    for rec in meta.get("history", [])
                ]
            except Exception:
                self.history = []
        self.effective = copy.deepcopy(self.policy)
        self.last_advice = None
        return {"key": key, "turn": self.turn}

    def _materialize_memory(self, fallback_tids: Optional[list[str]] = None) -> list[str]:
        """Full memory of the last frame: `memory_tokens` over the lattice's
        restored order. Falls back to the raw answer tids when the ewm-scene
        materializer cannot handle a degenerate (tiny) frame — the binary's
        materialization walk overflows on very small frames, and the
        controller must not crash on a short answer."""
        try:
            mat = self.ewm.materialize(self.union_path)
            return memory_tokens(mat["frames"][-1]["ordered"])
        except Exception:
            if fallback_tids is None:
                frames = self._read_union_frames(self.union_path)
                fallback_tids = frames[-1].get("tokens", []) if frames else []
            return memory_tokens(list(fallback_tids))

    def _rebuild_from_union(self):
        """Recompute seen / D-part / frame tids / full memory from the union file."""
        frames = self._read_union_frames(self.union_path)
        self.seen = set()
        self.comp_mem = []
        self.frame_tids = []
        for frame in frames:
            tids = list(frame.get("tokens", []))
            self.frame_tids.append(tids)
            self.comp_mem.extend(displacement_tokens(self.seen, tids))
        self.turn = len(frames)
        self.mem_tids = self._materialize_memory(
            self.frame_tids[-1] if self.frame_tids else None
        )

    def _diff_tids(self, a_tids: list[str], b_tids: list[str]) -> dict:
        """HLLSet diff of two final states via a two-frame ewm-scene run."""
        fd, tmp = tempfile.mkstemp(prefix="bonsai-ewm-diff-", suffix=".jsonl")
        try:
            with os.fdopen(fd, "w") as fh:
                fh.write(json.dumps({"id": 1, "tokens": a_tids}) + "\n")
                fh.write(json.dumps({"id": 2, "tokens": b_tids}) + "\n")
            uni = self.ewm.ingest(tmp)
            bss = self.ewm.bss(tmp)
            noe = self.ewm.noether(tmp)
        finally:
            os.unlink(tmp)
        fa, fb = uni["frames"][0], uni["frames"][1]
        return {
            "a": {"pop": int(fa.get("pop", 0)), "key": str(fa.get("key", ""))},
            "b": {"pop": int(fb.get("pop", 0)), "key": str(fb.get("key", ""))},
            "bss": float(bss["tau"][0]),          # how much of B is already in A
            "jaccard": float(bss["jaccard"][0]),
            "departed": int(noe["dp"][0]),
            "retained": int(noe["rp"][0]),
            "new": int(noe["np"][0]),
        }

    def diff_current(self, other_key: str) -> dict:
        """Diff the current session's S(t) against a saved session by key."""
        other_union = self._saved_union_path(other_key)
        if not os.path.exists(other_union):
            raise FileNotFoundError(f"no session saved under key {other_key!r}")
        a_frames = self._read_union_frames(self.union_path)
        b_frames = self._read_union_frames(other_union)
        if not a_frames:
            raise ValueError("current session is empty")
        if not b_frames:
            raise ValueError(f"session {other_key!r} is empty")
        out = self._diff_tids(a_frames[-1].get("tokens", []), b_frames[-1].get("tokens", []))
        out["a_key"] = "current"
        out["b_key"] = other_key
        return out

    def diff_saved(self, key_a: str, key_b: str) -> dict:
        """Diff two saved sessions' S(t) by their content keys."""
        union_a = self._saved_union_path(key_a)
        union_b = self._saved_union_path(key_b)
        if not os.path.exists(union_a):
            raise FileNotFoundError(f"no session saved under key {key_a!r}")
        if not os.path.exists(union_b):
            raise FileNotFoundError(f"no session saved under key {key_b!r}")
        a_frames = self._read_union_frames(union_a)
        b_frames = self._read_union_frames(union_b)
        if not a_frames:
            raise ValueError(f"session {key_a!r} is empty")
        if not b_frames:
            raise ValueError(f"session {key_b!r} is empty")
        out = self._diff_tids(a_frames[-1].get("tokens", []), b_frames[-1].get("tokens", []))
        out["a_key"] = key_a
        out["b_key"] = key_b
        return out

    # ── state report ────────────────────────────────────────────────────
    def state_report(self) -> dict:
        uni = self.ewm.ingest(self.union_path)
        frames = uni.get("frames", [])
        last = frames[-1] if frames else {"pop": 0, "key": ""}
        report = {
            "turn": self.turn,
            "pop": int(last.get("pop", 0)),
            "key": str(last.get("key", ""))[:56],
            "mem_tids": len(self.mem_tids),
            "comp_tids": len(self.comp_mem),
            "policy": copy.deepcopy(self.policy),
            "noether": None,
            "surprise": {
                "thresholds": dict(self.policy.get("surprise") or SURPRISE_DEFAULTS),
                "frames": self.surprise_frames(),
            },
        }
        if frames:
            noe = self.ewm.noether(self.union_path)
            report["noether"] = {
                "dp": noe.get("dp", [])[-1] if noe.get("dp") else None,
                "ind1": noe.get("ind1", [])[-1] if noe.get("ind1") else None,
                "ind2": noe.get("ind2", [])[-1] if noe.get("ind2") else None,
                "ind3": noe.get("ind3", [])[-1] if noe.get("ind3") else None,
            }
        return report
