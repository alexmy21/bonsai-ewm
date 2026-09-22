# cli.py — the ewm-bonsai REPL.
#
# The user talks to Bonsai through the lattice. Every turn the controller
# proposes a context (full materialized memory, the D-part novelty stream,
# or the Noether-surprise selection), Bonsai reasons over it, and the answer
# is ingested back into S(t). Sessions are addressable by content key and
# can be saved, restored, listed and diffed. See docs/ARCHITECTURE.md.

from __future__ import annotations

import json
import os
import sys
import time
from typing import Optional

from .adapters import BonsaiAdapter
from .ewm import EwmScene
from .session import BonsaiSession, SURPRISE_DEFAULTS, TurnRecord

DEFAULT_URL = "http://127.0.0.1:8081"
DEFAULT_WORK = os.path.join(os.path.expanduser("~"), ".cache", "bonsai-ewm")

HELP = (
    "  /context full|compact|surprise|auto   /cap N   /surprise [dp N|ind1 F|ind2 F|ind3 F]\n"
    "  /policy   /state   /history   /save   /sessions   /load <key>   /diff <key> [<key>]\n"
    "  /reset   /help   /quit"
)


def _print_turn(rec: TurnRecord):
    ans = rec.answer.strip().replace("\n", " ")
    print(f"  [{rec.mode} cap={rec.cap}] prefix_tids={rec.prefix_tokens:3d} "
          f"prompt_tokens={rec.prompt_tokens:4d}  answer={ans[:80]!r}")
    if rec.advice:
        j = rec.advice["jev"]
        print(f"  jev-advice: {j['decision']} (conf={j['confidence']:.2f}, "
              f"keep_short={j['aux'].get('keep_short', 0):.2f}, mock={j['mock']})")


def _print_state(session: BonsaiSession):
    r = session.state_report()
    print(f"  turn={r['turn']}  S(t) pop={r['pop']}  key={r['key']}")
    print(f"  memory: full={r['mem_tids']} tids  compact(D-part)={r['comp_tids']} tids")
    if r["noether"]:
        noe = r["noether"]
        print(f"  noether: dp={noe['dp']} ind1={noe['ind1']} ind2={noe['ind2']} ind3={noe['ind3']}")
    sur = r["surprise"]
    print(f"  surprise thresholds: {sur['thresholds']}")
    print(f"  surprise frames: {sur['frames'] if sur['frames'] else '(none)'}")
    print(f"  policy: mode={r['policy']['mode']} cap={r['policy']['cap']}")


def _print_diff(d: dict):
    print(f"  diff  {d['a_key']} -> {d['b_key']}")
    print(f"    a: pop={d['a']['pop']} key={d['a']['key'][:40]}")
    print(f"    b: pop={d['b']['pop']} key={d['b']['key'][:40]}")
    print(f"    bss(A,B)={d['bss']:.3f}  jaccard={d['jaccard']:.3f}")
    print(f"    departed={d['departed']}  retained={d['retained']}  new={d['new']}")


def _dir_writable(path: str) -> bool:
    """A work dir is healthy when it is writable, or creatable if missing."""
    if os.path.isdir(path):
        return os.access(path, os.W_OK)
    parent = os.path.dirname(path) or "."
    return os.path.isdir(parent) and os.access(parent, os.W_OK)


def _health_check(url: str, work: str, ewm: EwmScene, bonsai: BonsaiAdapter) -> int:
    from . import __version__

    ewm_ok = os.path.exists(ewm.bin) and os.access(ewm.bin, os.X_OK)
    work_ok = _dir_writable(work)
    bonsai_ok = bonsai.health()
    report = {
        "ok": bool(ewm_ok and work_ok and bonsai_ok),
        "version": __version__,
        "ewm_scene": ewm.bin,
        "ewm_scene_ok": ewm_ok,
        "work_dir": work,
        "work_dir_ok": work_ok,
        "bonsai_url": url,
        "bonsai_ok": bonsai_ok,
    }
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


def main(argv: Optional[list[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    url = os.environ.get("BONSAI_URL", DEFAULT_URL)
    work = os.environ.get("BONSAI_EWM_WORK", DEFAULT_WORK)

    bonsai = BonsaiAdapter(base_url=url)
    ewm = EwmScene()

    if "--health" in args:
        return _health_check(url, work, ewm, bonsai)
    if "--help" in args or "-h" in args:
        print("bonsai-ewm — Bonsai 2 27B through the ewm-sm lattice")
        print("usage: bonsai-ewm [--health|--help]")
        print(HELP)
        return 0

    session = BonsaiSession(bonsai, ewm, work)

    print("bonsai-ewm — Bonsai 2 27B through the ewm-sm lattice")
    print(f"  bonsai server: {url}  health={'ok' if bonsai.health() else 'DOWN'}")
    print(f"  lattice: {ewm.bin}")
    print(f"  jev advisor: {'real (TypeSafe API)' if not session.jev.mock else 'mock (no TYPESAFE_API_KEY)'}")
    print(HELP)
    print()

    tty = sys.stdin.isatty()
    while True:
        if tty:
            try:
                line = input("bonsai-ewm> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
        else:
            line = sys.stdin.readline()
            if not line:
                break
            line = line.strip()

        if not line:
            continue
        if line in ("/quit", "/exit"):
            break
        if line == "/help":
            print(HELP)
            continue
        if line.startswith("/context "):
            mode = line.split()[1]
            if mode not in ("full", "compact", "surprise", "auto"):
                print(f"  unknown mode {mode!r} (use full|compact|surprise|auto)")
                continue
            session.policy["mode"] = mode
            print(f"  context proposal: {mode}, cap={session.policy['cap']}")
            continue
        if line.startswith("/cap "):
            try:
                cap = int(line.split()[1])
                assert cap > 0
            except Exception:
                print("  usage: /cap N")
                continue
            session.policy["cap"] = cap
            print(f"  context proposal: {session.policy['mode']}, cap={cap}")
            continue
        if line == "/surprise":
            print(f"  surprise thresholds: {session.policy['surprise']}")
            print("  usage: /surprise [dp N] [ind1 F] [ind2 F] [ind3 F]")
            print("  (ind2 is retention BSS — a transition is surprising when ind2 is BELOW it)")
            continue
        if line.startswith("/surprise "):
            parts = line.split()[1:]
            if len(parts) % 2 != 0:
                print("  usage: /surprise [dp N] [ind1 F] [ind2 F] [ind3 F]")
                continue
            ok = True
            for i in range(0, len(parts), 2):
                name, value = parts[i], parts[i + 1]
                if name not in SURPRISE_DEFAULTS:
                    print(f"  unknown indicator {name!r} (use dp, ind1, ind2, ind3)")
                    ok = False
                    continue
                try:
                    session.policy["surprise"][name] = float(value)
                except ValueError:
                    print(f"  bad value for {name}: {value!r}")
                    ok = False
            if ok:
                print(f"  surprise thresholds: {session.policy['surprise']}")
            continue
        if line == "/policy":
            print(f"  policy: mode={session.policy['mode']} cap={session.policy['cap']}")
            print(f"  surprise thresholds: {session.policy['surprise']}")
            continue
        if line == "/state":
            _print_state(session)
            continue
        if line == "/history":
            if not session.history:
                print("  (no turns yet)")
            for rec in session.history:
                print(f"  t={rec.turn} mode={rec.mode} cap={rec.cap} "
                      f"prefix_tids={rec.prefix_tokens} prompt_tokens={rec.prompt_tokens} "
                      f"pop={rec.pop}  ans={rec.answer[:50]!r}")
            continue
        if line == "/save":
            try:
                saved = session.save()
            except ValueError as exc:
                print(f"  cannot save: {exc}")
                continue
            print(f"  saved S(t) under key {saved['key']} (turn={saved['turn']})")
            print(f"  path: {saved['path']}")
            continue
        if line in ("/sessions", "/list"):
            sessions = session.list_sessions()
            if not sessions:
                print("  (no saved sessions)")
            for s in sessions:
                when = time.strftime("%Y-%m-%d %H:%M", time.localtime(s["saved_at"])) if s["saved_at"] else "?"
                print(f"  key={s['key'][:40]}  turn={s['turn']}  saved={when}")
            continue
        if line.startswith("/load "):
            key = line.split()[1]
            try:
                loaded = session.load(key)
            except FileNotFoundError as exc:
                print(f"  {exc}")
                continue
            print(f"  restored S(t) from key {loaded['key']} (turn={loaded['turn']})")
            continue
        if line.startswith("/diff"):
            parts = line.split()[1:]
            try:
                if len(parts) == 1:
                    d = session.diff_current(parts[0])
                elif len(parts) == 2:
                    d = session.diff_saved(parts[0], parts[1])
                else:
                    print("  usage: /diff <key> | /diff <keyA> <keyB>")
                    continue
            except (FileNotFoundError, ValueError) as exc:
                print(f"  cannot diff: {exc}")
                continue
            _print_diff(d)
            continue
        if line == "/reset":
            session.reset()
            print("  session reset")
            continue

        rec = session.ask(line)
        _print_turn(rec)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
