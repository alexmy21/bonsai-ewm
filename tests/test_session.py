# Tests for BonsaiSession — surprise proposals and persistent sessions.
#
# These use an in-process fake for ewm-scene (same JSON protocol, set-based
# HLL math at token granularity) and a fake Bonsai adapter, so the tests are
# stdlib-only and deterministic: the controller logic is exercised without
# the Rust binary or the model server.

import json
import os
import tempfile
import unittest
import zlib

from bonsai_ewm.session import BonsaiSession, SURPRISE_DEFAULTS, _dedup_consecutive


def _read_frames(path):
    frames = []
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if line:
                frames.append(json.loads(line))
    return frames


def _setof(tokens):
    return set(tokens)


def _key(tokens):
    return "h:%08x" % zlib.crc32(" ".join(sorted(set(tokens))).encode())


class FakeEwm:
    """In-process stand-in for the ewm-scene CLI (JSON in, JSON out)."""

    def __init__(self):
        self.canned = {}

    def __call__(self, cmd, path, *args):
        if cmd in self.canned:
            return self.canned[cmd]
        frames = _read_frames(path)
        if cmd == "ingest":
            return {"frames": [
                {"id": f["id"], "key": _key(f["tokens"]), "pop": len(_setof(f["tokens"]))}
                for f in frames
            ]}
        if cmd == "materialize":
            return {"frames": [
                {
                    "id": f["id"],
                    "ordered": list(f["tokens"]),
                    "set": sorted(_setof(f["tokens"])),
                    "beam2": list(f["tokens"]),
                }
                for f in frames
            ]}
        if cmd == "noether":
            return self._noether(frames)
        if cmd == "bss":
            sets = [_setof(f["tokens"]) for f in frames]
            tau, jac, pops, keys = [], [], [], []
            for i in range(len(sets)):
                pops.append(len(sets[i]))
                keys.append(_key(frames[i]["tokens"]))
            for i in range(1, len(sets)):
                a, b = sets[i - 1], sets[i]
                inter = len(a & b)
                tau.append(inter / len(b) if b else 1.0)
                jac.append(inter / len(a | b) if (a | b) else 1.0)
            return {"tau": tau, "jaccard": jac, "pop": pops, "keys": keys}
        raise AssertionError(f"unexpected ewm-scene command {cmd!r}")

    @staticmethod
    def _noether(frames):
        sets = [_setof(f["tokens"]) for f in frames]
        dp, rp, np, ind1, ind2, ind3 = [], [], [], [], [], []
        r_prev = None
        for i in range(len(sets) - 1):
            a, b = sets[i], sets[i + 1]
            d, r, n = a - b, a & b, b - a
            dp.append(len(d))
            rp.append(len(r))
            np.append(len(n))
            rn = r | n
            rd = r | d
            ind1.append(len(d) / len(rn) if rn else 0.0)
            ind3.append(len(n) / len(rd) if rd else 0.0)
            if r_prev is not None:
                ind2.append(len(r_prev & r) / len(r) if r else 1.0)
            r_prev = r
        return {"dp": dp, "rp": rp, "np": np, "ind1": ind1, "ind2": ind2, "ind3": ind3}

    # The method surface BonsaiSession uses.
    def ingest(self, path):
        return self("ingest", path)

    def bss(self, path):
        return self("bss", path)

    def materialize(self, path):
        return self("materialize", path)

    def noether(self, path):
        return self("noether", path)


class FakeBonsai:
    def __init__(self):
        self.calls = 0

    def chat_full(self, prompt, max_tokens=128, temperature=0.0):
        self.calls += 1
        content = f"answer number {self.calls}"
        return {
            "content": content,
            "reasoning": "",
            "usage": {"prompt_tokens": len(prompt.split())},
        }

    def tokenize(self, text):
        return [int(zlib.crc32(w.encode()) % 9000) for w in text.split()]

    def detokenize(self, tokens):
        return " ".join(f"tok{t}" for t in tokens)


class SessionTestCase(unittest.TestCase):
    def make_session(self, **kwargs):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        ewm = FakeEwm()
        bonsai = FakeBonsai()
        session = BonsaiSession(bonsai, ewm, tmp.name, **kwargs)
        return session, ewm, bonsai


class DedupTests(unittest.TestCase):
    def test_consecutive_dedup(self):
        self.assertEqual(
            _dedup_consecutive(["a", "a", "b", "a", "a"]),
            ["a", "b", "a"],
        )


class SurpriseTests(SessionTestCase):
    def test_flags_empty_below_two_turns(self):
        session, _, _ = self.make_session()
        self.assertEqual(session.surprise_flags(), [])

    def test_flags_departure_above_dp_threshold(self):
        session, ewm, _ = self.make_session()
        # Two frames: frame2 drops tid1, keeps tid2, adds tid3.
        ewm.canned["noether"] = {
            "dp": [1], "rp": [1], "np": [1],
            "ind1": [0.5], "ind3": [0.5], "ind2": [],
        }
        session.turn = 2
        session.policy["surprise"] = {"dp": 0, "ind1": 0.9, "ind2": 0.9, "ind3": 0.9}
        session.effective = {"mode": "surprise", "cap": 8, "surprise": session.policy["surprise"]}
        self.assertEqual(session.surprise_flags(), [True])
        self.assertEqual(session.surprise_frames(), [1, 2])

    def test_flags_retention_collapse_below_ind2(self):
        session, ewm, _ = self.make_session()
        # Three frames; ind2 (retention chain) collapses at transition 1.
        ewm.canned["noether"] = {
            "dp": [0, 0], "rp": [1, 1], "np": [0, 0],
            "ind1": [0.0, 0.0], "ind3": [0.0, 0.0], "ind2": [0.1],
        }
        session.turn = 3
        session.policy["surprise"] = {"dp": 5, "ind1": 0.9, "ind2": 0.5, "ind3": 0.9}
        session.effective = {"mode": "surprise", "cap": 8, "surprise": session.policy["surprise"]}
        self.assertEqual(session.surprise_flags(), [False, True])
        self.assertEqual(session.surprise_frames(), [2, 3])

    def test_surprise_proposal_includes_departed_tids(self):
        session, ewm, bonsai = self.make_session()
        # Turn 1 answer: tid1 tid2 tid3 ; turn 2 answer: tid2 tid3 tid4
        # (tid1 departs, tid4 is new — transition above dp threshold).
        session.policy.update({"mode": "surprise", "cap": 8})
        ewm.canned["noether"] = {
            "dp": [1], "rp": [2], "np": [1],
            "ind1": [0.33], "ind3": [0.33], "ind2": [],
        }
        bonsai.calls = 0
        bonsai.tokenize = lambda text: {"answer number 1": [1, 2, 3], "answer number 2": [2, 3, 4]}[text]
        rec1 = session.ask("one")
        rec2 = session.ask("two")
        self.assertEqual(rec1.mode, "surprise")
        self.assertEqual(rec2.mode, "surprise")
        proposal = session.proposal_tids()
        # D-part: tid1 tid2 tid3 tid4 (all new across the two turns).
        # Flagged frames 1 and 2 re-inject their full tids.
        self.assertIn("tid1", proposal)   # departed content kept by surprise
        self.assertIn("tid4", proposal)   # new content still present
        self.assertLessEqual(len(proposal), 8)

    def test_surprise_degenerates_to_compact_when_nothing_flagged(self):
        session, ewm, _ = self.make_session()
        ewm.canned["noether"] = {
            "dp": [0], "rp": [1], "np": [0],
            "ind1": [0.0], "ind3": [0.0], "ind2": [],
        }
        session.turn = 2
        session.frame_tids = [["tid1", "tid2"], ["tid1", "tid2"]]
        session.comp_mem = ["tid1", "tid2"]
        session.policy["mode"] = "surprise"
        session.effective = {"mode": "surprise", "cap": 8, "surprise": dict(SURPRISE_DEFAULTS)}
        self.assertEqual(session.proposal_tids(), ["tid1", "tid2"])


class PersistentSessionTests(SessionTestCase):
    def test_save_roundtrip_and_restore(self):
        session, _, bonsai = self.make_session()
        bonsai.tokenize = lambda text: [1, 2, 3]
        session.ask("hello")
        key_before = session.session_key()
        saved = session.save()
        self.assertEqual(saved["key"], key_before)
        self.assertTrue(os.path.exists(os.path.join(session.sessions_dir, key_before, "union.jsonl")))
        self.assertTrue(os.path.exists(os.path.join(session.sessions_dir, key_before, "meta.json")))

        # A fresh session in the same work dir (controller restart) restores
        # S(t) by the content key.
        session2 = BonsaiSession(FakeBonsai(), FakeEwm(), session.work_dir)
        loaded = session2.load(key_before)
        self.assertEqual(loaded["turn"], 1)
        self.assertEqual(session2.frame_tids, [["tid1", "tid2", "tid3"]])
        self.assertEqual(session2.comp_mem, ["tid1", "tid2", "tid3"])
        self.assertEqual(session2.mem_tids, ["tid1", "tid2", "tid3"])
        self.assertEqual(session2.history[0].answer, "answer number 1")

    def test_save_preserves_policy_and_history(self):
        session, _, bonsai = self.make_session()
        session.policy.update({"mode": "compact", "cap": 12, "surprise": {"dp": 9, "ind1": 0.7, "ind2": 0.4, "ind3": 0.8}})
        bonsai.tokenize = lambda text: [5, 6]
        session.ask("hi")
        key = session.save()["key"]

        session2 = BonsaiSession(FakeBonsai(), FakeEwm(), session.work_dir)
        session2.load(key)
        self.assertEqual(session2.policy["mode"], "compact")
        self.assertEqual(session2.policy["cap"], 12)
        self.assertEqual(session2.policy["surprise"]["dp"], 9)
        self.assertEqual(session2.history[0].query, "hi")

    def test_list_sessions(self):
        session, _, bonsai = self.make_session()
        bonsai.tokenize = lambda text: [1, 2, 3]
        session.ask("one")
        session.save()
        keys = [s["key"] for s in session.list_sessions()]
        self.assertEqual(keys, [session.session_key()])

    def test_diff_current_against_saved(self):
        session, _, bonsai = self.make_session()
        bonsai.tokenize = lambda text: [1, 2, 3]
        session.ask("one")
        key = session.save()["key"]

        # Advance the current session to a different S(t).
        bonsai.tokenize = lambda text: [4, 5]
        session.ask("two")

        d = session.diff_current(key)
        # Current S(t) = {tid4,tid5}; saved S(t) = {tid1,tid2,tid3}: disjoint.
        # Direction is a=current -> b=saved, so "new" = in saved only,
        # "departed" = in current only.
        self.assertEqual(d["a_key"], "current")
        self.assertEqual(d["b_key"], key)
        self.assertEqual(d["retained"], 0)
        self.assertEqual(d["new"], 3)
        self.assertEqual(d["departed"], 2)

    def test_diff_two_saved_sessions(self):
        session, _, bonsai = self.make_session()
        bonsai.tokenize = lambda text: [1, 2, 3]
        session.ask("one")
        key_a = session.save()["key"]

        session.reset()
        bonsai.tokenize = lambda text: [2, 3, 4]
        session.ask("two")
        key_b = session.save()["key"]

        d = session.diff_saved(key_a, key_b)
        self.assertEqual(d["retained"], 2)  # tid2, tid3 in both
        self.assertEqual(d["new"], 1)       # tid4
        self.assertEqual(d["departed"], 1)  # tid1


if __name__ == "__main__":
    unittest.main()
