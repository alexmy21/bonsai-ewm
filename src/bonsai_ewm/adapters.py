# adapters.py — Bonsai server client and tid helpers (stdlib only).
#
# The model boundary of bonsai-ewm: a thin HTTP client over the PrismML
# llama.cpp server (chat / tokenize / detokenize) plus the two lattice
# memory helpers. No third-party dependencies.

from __future__ import annotations

import json
import os
import urllib.request
from typing import Optional


class BonsaiAdapter:
    """PrismML Bonsai 2 27B served by the PrismML llama.cpp fork.

    Bonsai is a reasoning model; the server exposes the OpenAI-compatible
    chat API plus llama.cpp's /tokenize and /detokenize endpoints, which
    give the controller bidirectional access to the model's token space —
    the property that makes the context a proposal rather than a transcript.
    """

    def __init__(self, base_url: str = "http://127.0.0.1:8081", timeout: int = 600):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _post(self, path: str, payload: dict) -> dict:
        req = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def health(self) -> bool:
        try:
            with urllib.request.urlopen(self.base_url + "/health", timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8")).get("status") == "ok"
        except Exception:
            return False

    def chat(self, prompt: str, max_tokens: int = 256, temperature: float = 0.0):
        """-> (answer_text, reasoning_text)."""
        full = self.chat_full(prompt, max_tokens=max_tokens, temperature=temperature)
        return full["content"], full["reasoning"]

    def chat_full(self, prompt: str, max_tokens: int = 256, temperature: float = 0.0) -> dict:
        """Full response: content, reasoning and usage (incl. prompt_tokens)."""
        r = self._post(
            "/v1/chat/completions",
            {
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": False,
            },
        )
        msg = r["choices"][0]["message"]
        return {
            "content": str(msg.get("content") or ""),
            "reasoning": str(msg.get("reasoning_content") or ""),
            "usage": dict(r.get("usage", {})),
        }

    def tokenize(self, text: str) -> list[int]:
        return list(self._post("/tokenize", {"content": text}).get("tokens", []))

    def detokenize(self, tokens: list[int]) -> str:
        return str(self._post("/detokenize", {"tokens": tokens}).get("content", ""))


def memory_tokens(ordered: list[str], cap: int = 24) -> list[str]:
    """Materialized memory: restored order, consecutive duplicates removed,
    capped to the last `cap` tokens."""
    toks: list[str] = []
    for t in ordered:
        if not toks or toks[-1] != t:
            toks.append(t)
    return toks[-cap:]


def displacement_tokens(seen: set, tids: list[str]) -> list[str]:
    """The D-part of the Noether decomposition at token granularity: only the
    tids that are new to the lattice (`t not in seen`) are returned, and they
    are added to `seen`. Repeated content collapses to nothing, exactly like
    the HLLSet union."""
    out: list[str] = []
    for t in tids:
        if t not in seen:
            out.append(t)
            seen.add(t)
    return out


class JevAdapter:
    """TypeSafe System One (Jev) over its REST API — stdlib only.

    Jev returns typed, probabilistic decisions (choice / noul / score)
    instead of text. This adapter keeps bonsai-ewm stdlib-only by talking
    to `POST https://api.typesafe.ai/v1/systemone` directly with the
    `TYPESAFE_API_KEY` env var, and falls back to a deterministic mock when
    the key is missing.
    """

    ENDPOINT = "https://api.typesafe.ai/v1/systemone"

    def __init__(self):
        self.api_key = os.environ.get("TYPESAFE_API_KEY", "")
        self.mock = not bool(self.api_key)

    def route(
        self,
        state: dict,
        options: dict[str, str],
        instructions: str,
        extra_noul: dict[str, str] | None = None,
    ) -> dict:
        if self.mock:
            return self._mock_route(state, options, extra_noul)
        questions = {
            "route": {"type": "choice", "instructions": instructions, "criteria": dict(options)}
        }
        for name, instr in (extra_noul or {}).items():
            questions[name] = {"type": "noul", "instructions": instr}
        payload = {
            "state": state,
            "model": os.environ.get("TYPESAFE_DEFAULT_MODEL", "jev-latest"),
            "questions": questions,
        }
        req = urllib.request.Request(
            self.ENDPOINT,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            r = json.loads(resp.read().decode("utf-8"))
        ans = r["answers"]["route"]
        probabilities = {str(k): float(v) for k, v in ans.get("probabilities", {}).items()}
        aux = {n: float(r["answers"][n].get("noul", 0.0)) for n in (extra_noul or {})}
        usage = r.get("usage", {})
        return {
            "decision": str(ans.get("choice", "")),
            "confidence": float(ans.get("confidence", 0.0)),
            "probabilities": probabilities,
            "aux": aux,
            "model": str(r.get("model", "jev")),
            "input_tokens": int(usage.get("input_tokens", 0)),
            "output_tokens": int(usage.get("output_tokens", 0)),
            "mock": False,
        }

    def _mock_route(self, state, options, extra_noul=None) -> dict:
        import zlib

        seed = zlib.crc32((str(state.get("turn", 0)) + str(state.get("query", ""))).encode())
        names = list(options)
        # deterministic pseudo-softmax over the option names
        vals = [1.0 + ((seed >> i) & 3) for i in range(len(names))]
        total = sum(vals)
        probs = {n: v / total for n, v in zip(names, vals)}
        choice = max(probs, key=probs.get)
        return {
            "decision": choice,
            "confidence": float(probs[choice]),
            "probabilities": probs,
            "aux": {n: 0.5 for n in (extra_noul or {})},
            "model": "mock-jev",
            "input_tokens": 0,
            "output_tokens": 0,
            "mock": True,
        }
