#!/usr/bin/env python3
"""Shadow-only G&G observer tests (R5, worker C). Synthetic only:
no gold, no sample ids, no held-out, no model, no GPU.

The core claim under test is NON-INTERFERENCE on CPU fixtures: a
fake generator emitting fixed output sequences must produce
byte-identical behaviour (prompts, generator call count, submitted
calls, state hash) with shadow OFF, shadow ON, and the UNMODIFIED
frozen-v10 agent (old-baseline control, run in a subprocess so the
frozen package cannot collide with the new one).

Covered: normal, empty, ask (direct + grounding-converted), invalid
JSON, validation rejection, noop, repeated call, max steps, observer
exception, multi-sample order/leak, record schema, config flag
default/round-trip, prefix/roster helpers.

Run from the workdir root on both backends:
    python3 tests/test_observer.py
    ~/workspace/zaic-test-venv/bin/python tests/test_observer.py
"""
import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lifemate.agent import AgentLoop  # noqa: E402
from lifemate.config import PipelineConfig  # noqa: E402
import lifemate.lifemate_observer as observer_module  # noqa: E402
from lifemate.lifemate_observer import (  # noqa: E402
    ShadowObserver,
    build_prefix,
    collect_rosters_from_prefix,
)

FROZEN_ROOT = Path("/home/hatch/workspace/zaic-gg-r4-frozen-v10")

TOOLS = {
    "contacts.search": {"kind": "read", "description": "search contacts",
                        "parameters": {"required": []}},
    "contacts.get": {"kind": "read", "description": "get contact",
                     "parameters": {"required": ["contact_id"]}},
    "phone.call": {"kind": "write", "description": "call",
                   "parameters": {"required": ["phone_number"]}},
    "sms.send": {"kind": "write", "description": "send sms",
                 "parameters": {"required": ["contact_id", "content"]}},
    "tasks.add": {"kind": "write", "description": "add task",
                  "parameters": {"required": ["title"]}},
    "sys.ask_missing_info": {"kind": "meta", "description": "ask",
                            "parameters": {"required": ["tool_name",
                                                        "params"]}},
}

CALL_X = {"name": "phone.call", "arguments": {"phone_number": "0902345678"}}
CALL_Y = {"name": "phone.call", "arguments": {"phone_number": "0911111111"}}
SEARCH = {"name": "contacts.search", "arguments": {"query": "Bình"}}
TASK = {"name": "tasks.add", "arguments": {"title": "Nhắc uống nước"}}
SMS = {"name": "sms.send", "arguments": {"contact_id": "c_1",
                                        "content": "hi"}}
ASK = {"name": "sys.ask_missing_info",
       "arguments": {"tool_name": "phone.call", "params": ["contact_id"]}}
STOP = {"stop": True}


class FakeTurn:
    def __init__(self, role, audio_text=None, text=None, tool_calls=None,
                 tool_results=None):
        self.role = role
        self.audio_text = audio_text
        self.text = text
        self.tool_calls = tool_calls or []
        self.tool_results = tool_results


class FakeSample:
    def __init__(self, context=None, history=None):
        self.id = "test-sample"
        self.split = "dev"
        self.audio = ""
        self.context = context or {
            "current_time": "2026-10-30T09:00:00+07:00",
            "timezone": "Asia/Ho_Chi_Minh",
            "user_profile": {"name": "Test", "city": "HCMC"},
        }
        self.history = history or []
        self.audio_text = None
        self.label = None


class FakeEnv:
    """Minimal env double: validate/call/submission_line only."""

    def __init__(self, reject=None, noop_names=None):
        self.calls = []
        self.reject = reject or {}
        self.noop_names = set(noop_names or [])

    def validate(self, name, args):
        if name in self.reject:
            return {"ok": False, "error": self.reject[name]}
        return {"ok": True}

    def call(self, name, args):
        self.calls.append({"name": name, "arguments": dict(args)})
        if name in self.noop_names:
            return {"ok": True, "done": False, "message": "noop"}
        if name == "contacts.search":
            return {"ok": True,
                    "contacts": [{"id": "c_1", "name": "Bình",
                                  "phone": "0902345678"}]}
        return {"ok": True}

    def submission_line(self):
        blob = json.dumps(self.calls, sort_keys=True, ensure_ascii=False)
        return {"tool_calls": [dict(c) for c in self.calls],
                "state_hash": hashlib.sha256(blob.encode()).hexdigest()}


class FakeGenerator:
    def __init__(self, outputs):
        self.outputs = [copy.deepcopy(o) for o in outputs]
        self.prompts = []
        self.index = 0

    def __call__(self, prompt, tools):
        self.prompts.append(prompt)
        if self.index < len(self.outputs):
            out = self.outputs[self.index]
            self.index += 1
            return copy.deepcopy(out)
        return None


def run_case(outputs, shadow=False, grounding=False, max_steps=12,
             max_repeats=2, env=None, sample=None,
             transcript="Gọi số 0902345678 giúp tôi"):
    cfg = PipelineConfig(max_steps=max_steps, max_repeats=max_repeats,
                         grounding=grounding, shadow_observer=shadow)
    loop = AgentLoop(cfg, TOOLS)
    gen = FakeGenerator(outputs)
    env = env if env is not None else FakeEnv()
    sample = sample if sample is not None else FakeSample()
    sub = loop.run(sample, transcript, env, gen)
    return {
        "prompts": list(gen.prompts),
        "gen_calls": len(gen.prompts),
        "submitted": sub["tool_calls"],
        "state_hash": sub["state_hash"],
        "records": [dict(r) for r in loop.observer.records],
        "env_calls": [dict(c) for c in env.calls],
    }


BEHAVIOUR_KEYS = ("prompts", "gen_calls", "submitted", "state_hash",
                  "env_calls")


def assert_behaviour_equal(tc, a, b, label):
    for key in BEHAVIOUR_KEYS:
        tc.assertEqual(a[key], b[key], f"{label}: behaviour differs on {key}")


SCHEMA_KEYS = {"proposal_raw", "proposal_grounded", "validation_outcome",
               "baseline_decision", "candidate_decision", "adjustments",
               "eligibility", "error", "position"}


class TestNonInterference(unittest.TestCase):
    def test_normal_off_on_identical(self):
        off = run_case([SEARCH, CALL_X, STOP], shadow=False)
        on = run_case([SEARCH, CALL_X, STOP], shadow=True)
        assert_behaviour_equal(self, off, on, "normal")
        self.assertEqual(off["records"], [])
        self.assertEqual(len(on["records"]), 2)
        for rec in on["records"]:
            self.assertEqual(rec["validation_outcome"], "ok")
            self.assertIsNone(rec["error"])
        self.assertEqual(on["records"][1]["proposal_raw"], CALL_X)
        self.assertEqual(on["records"][1]["proposal_grounded"], CALL_X)

    def test_empty_off_on_identical(self):
        off = run_case([], shadow=False)
        on = run_case([], shadow=True)
        assert_behaviour_equal(self, off, on, "empty")
        self.assertEqual(off["submitted"], [])
        self.assertEqual(on["records"], [])

    def test_ask_direct(self):
        off = run_case([ASK, STOP], shadow=False)
        on = run_case([ASK, STOP], shadow=True)
        assert_behaviour_equal(self, off, on, "ask-direct")
        self.assertEqual(on["submitted"], [ASK])
        self.assertEqual(len(on["records"]), 1)
        rec = on["records"][0]
        self.assertEqual(rec["validation_outcome"], "ok")
        # Ask proposals are out of gate scope (same as the paired audit).
        self.assertIsNone(rec["baseline_decision"])
        self.assertIsNone(rec["candidate_decision"])
        self.assertEqual(rec["adjustments"], [])

    def test_ask_via_grounding_leftover_name(self):
        # grounding=True + a contact_name with no roster: the loop's
        # leftover-name check converts the proposal to an ask call.
        # The observer must keep raw (sms.send) and grounded (ask)
        # separate, and must not change the conversion.
        sms_name = {"name": "sms.send",
                    "arguments": {"contact_name": "Bình",
                                  "content": "hi"}}
        off = run_case([sms_name, STOP], shadow=False, grounding=True)
        on = run_case([sms_name, STOP], shadow=True, grounding=True)
        assert_behaviour_equal(self, off, on, "ask-via-grounding")
        self.assertEqual(len(off["submitted"]), 1)
        self.assertEqual(off["submitted"][0]["name"], "sys.ask_missing_info")
        self.assertEqual(len(on["records"]), 1)
        rec = on["records"][0]
        self.assertEqual(rec["proposal_raw"], sms_name)
        self.assertEqual(rec["proposal_grounded"]["name"],
                         "sys.ask_missing_info")
        self.assertIsNone(rec["candidate_decision"])

    def test_invalid_generation(self):
        outputs = ["not a dict", {"arguments": {}}, None]
        off = run_case(outputs, shadow=False)
        on = run_case(outputs, shadow=True)
        assert_behaviour_equal(self, off, on, "invalid")
        self.assertEqual(off["submitted"], [])
        self.assertEqual(len(on["records"]), 2)
        for rec in on["records"]:
            self.assertEqual(rec["validation_outcome"], "invalid")
            self.assertIsNone(rec["proposal_grounded"])
            self.assertIsNone(rec["candidate_decision"])

    def test_validation_rejection(self):
        env_off = FakeEnv(reject={"phone.call": "bad args"})
        env_on = FakeEnv(reject={"phone.call": "bad args"})
        off = run_case([CALL_X, TASK, STOP], shadow=False, env=env_off)
        on = run_case([CALL_X, TASK, STOP], shadow=True, env=env_on)
        assert_behaviour_equal(self, off, on, "validation-rejection")
        self.assertEqual(off["submitted"], [TASK])
        self.assertEqual(len(on["records"]), 2)
        self.assertEqual(on["records"][0]["validation_outcome"], "failed")
        self.assertIsNone(on["records"][0]["candidate_decision"])
        self.assertEqual(on["records"][0]["proposal_raw"], CALL_X)
        self.assertEqual(on["records"][1]["validation_outcome"], "ok")

    def test_noop(self):
        env_off = FakeEnv(noop_names={"tasks.add"})
        env_on = FakeEnv(noop_names={"tasks.add"})
        off = run_case([TASK, STOP], shadow=False, env=env_off)
        on = run_case([TASK, STOP], shadow=True, env=env_on)
        assert_behaviour_equal(self, off, on, "noop")
        self.assertEqual(len(on["records"]), 1)
        self.assertEqual(on["records"][0]["validation_outcome"], "ok")
        self.assertIsNone(on["records"][0]["error"])

    def test_repeated_call(self):
        off = run_case([CALL_X, CALL_X, CALL_X, STOP], shadow=False)
        on = run_case([CALL_X, CALL_X, CALL_X, STOP], shadow=True)
        assert_behaviour_equal(self, off, on, "repeated")
        # Executed twice, third generation hits the guard pre-block.
        self.assertEqual(off["submitted"], [CALL_X, CALL_X])
        self.assertEqual(off["gen_calls"], 3)
        self.assertEqual(len(on["records"]), 2)

    def test_max_steps(self):
        outputs = [SEARCH, CALL_X, TASK, SMS, STOP]
        off = run_case(outputs, shadow=False, max_steps=2)
        on = run_case(outputs, shadow=True, max_steps=2)
        assert_behaviour_equal(self, off, on, "max-steps")
        self.assertEqual(off["submitted"], [SEARCH, CALL_X])
        self.assertEqual(len(on["records"]), 2)

    def test_observer_exception_never_becomes_agent_error(self):
        old = observer_module._decide_cache.get("fn")

        def raiser(*args, **kwargs):
            raise RuntimeError("boom from decide")

        observer_module._decide_cache["fn"] = raiser
        try:
            off = run_case([SEARCH, CALL_X, STOP], shadow=False)
            on = run_case([SEARCH, CALL_X, STOP], shadow=True)
        finally:
            observer_module._decide_cache["fn"] = old
        # The run completed normally and matches the OFF run exactly.
        assert_behaviour_equal(self, off, on, "observer-exception")
        self.assertEqual(len(on["records"]), 2)
        for rec in on["records"]:
            self.assertIsNotNone(rec["error"])
            self.assertIn("boom", rec["error"])
            self.assertIsNone(rec["candidate_decision"])


class TestPerSampleReset(unittest.TestCase):
    def test_no_leak_across_samples_same_loop(self):
        cfg = PipelineConfig(shadow_observer=True)
        loop = AgentLoop(cfg, TOOLS)
        gen1 = FakeGenerator([CALL_X, STOP])
        sub1 = loop.run(FakeSample(), "Gọi số X", FakeEnv(), gen1)
        recs1 = [dict(r) for r in loop.observer.records]
        gen2 = FakeGenerator([SMS, STOP])
        sub2 = loop.run(FakeSample(), "Nhắn cho Bình", FakeEnv(), gen2)
        recs2 = [dict(r) for r in loop.observer.records]
        gen3 = FakeGenerator([CALL_X, STOP])
        sub3 = loop.run(FakeSample(), "Gọi số X", FakeEnv(), gen3)
        recs3 = [dict(r) for r in loop.observer.records]
        # Each run's log holds only that run's proposals.
        self.assertEqual([r["proposal_raw"] for r in recs1], [CALL_X])
        self.assertEqual([r["proposal_raw"] for r in recs2], [SMS])
        self.assertEqual(recs3, recs1)
        # NOTE: the loop guard is per-LOOP, not per-run (pre-existing
        # behaviour: run() resets roster/grounding_log but not the
        # guard, so re-running CALL_X on the SAME loop instance
        # legitimately hits the replan path on the second run).
        # Behaviour reproduction is therefore asserted on FRESH loops
        # below, not on same-loop repeats. The observer itself resets
        # per run (recs3 == recs1 proves the log does not leak).
        self.assertEqual(sub1["tool_calls"], sub3["tool_calls"])
        self.assertEqual(sub1["state_hash"], sub3["state_hash"])
        # Order swap on a fresh loop gives the same per-sample outputs.
        loop2 = AgentLoop(cfg, TOOLS)
        g2 = FakeGenerator([SMS, STOP])
        s2 = loop2.run(FakeSample(), "Nhắn cho Bình", FakeEnv(), g2)
        g1 = FakeGenerator([CALL_X, STOP])
        s1 = loop2.run(FakeSample(), "Gọi số X", FakeEnv(), g1)
        self.assertEqual(s1["tool_calls"], sub1["tool_calls"])
        self.assertEqual(s2["tool_calls"], sub2["tool_calls"])
        self.assertEqual(g1.prompts, gen1.prompts)


class TestSchemaAndConfig(unittest.TestCase):
    def test_record_schema_exact(self):
        on = run_case([SEARCH, CALL_X, TASK, STOP], shadow=True)
        for rec in on["records"]:
            self.assertEqual(set(rec.keys()), SCHEMA_KEYS)
            json.dumps(rec)  # must be JSON-serialisable
            self.assertIn(rec["validation_outcome"], ("ok", "failed",
                                                      "invalid"))
            self.assertIsInstance(rec["position"], int)
            self.assertGreaterEqual(rec["position"], 0)
        positions = [r["position"] for r in on["records"]]
        self.assertEqual(positions, [0, 1, 2])

    def test_eligibility_field_present_and_report_only(self):
        # R5 coordinator wiring: gate-applicable decided records carry
        # an eligibility dict (report-only); non-applicable or
        # undecided records carry None. The observer never changes
        # behaviour, so this only checks the record shape, not any
        # enforcement.
        on = run_case([SEARCH, CALL_X, STOP], shadow=True)
        applicable = [r for r in on["records"]
                      if r["candidate_decision"] is not None
                      and r["candidate_decision"]["applicable"]]
        self.assertTrue(applicable)
        for rec in applicable:
            self.assertIsInstance(rec["eligibility"], dict)
            self.assertIn(rec["eligibility"]["status"],
                          ("eligible", "ineligible", "unknown"))
            self.assertTrue(rec["eligibility"]["reason"])
        for rec in on["records"]:
            if rec["candidate_decision"] is None or \
                    not rec["candidate_decision"]["applicable"]:
                self.assertIsNone(rec["eligibility"])

    def test_config_flag_default_and_roundtrip(self):
        cfg = PipelineConfig()
        self.assertIs(cfg.shadow_observer, False)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cfg.json"
            path.write_text(json.dumps({"max_steps": 5}),
                            encoding="utf-8")
            loaded = PipelineConfig.from_json(path)
            self.assertIs(loaded.shadow_observer, False)
            path.write_text(json.dumps({"shadow_observer": True}),
                            encoding="utf-8")
            loaded = PipelineConfig.from_json(path)
            self.assertIs(loaded.shadow_observer, True)
            out = Path(tmp) / "out.json"
            loaded.to_json(out)
            reloaded = PipelineConfig.from_json(out)
            self.assertIs(reloaded.shadow_observer, True)

    def test_prefix_and_roster_helpers(self):
        history = [
            FakeTurn("user", audio_text="Gọi cho Bình"),
            FakeTurn("assistant", text="",
                     tool_calls=[SEARCH],
                     tool_results=[{"ok": True,
                                    "contacts": [{"id": "c_1",
                                                  "name": "Bình",
                                                  "phone": "0902345678"},
                                                 {"id": "c_1",
                                                  "name": "Bình",
                                                  "phone": "0902345678"}]}]),
            FakeTurn("assistant", text="", tool_calls=[],
                     tool_results=None),  # no-call turn: no events
        ]
        prefix, err = build_prefix(history, [CALL_X],
                                   [{"ok": True}])
        self.assertIsNone(err)
        self.assertEqual(prefix[0]["kind"], "user_turn")
        self.assertEqual(prefix[0]["position"], 0)
        self.assertEqual(prefix[1]["origin"], "history")
        self.assertEqual(prefix[1]["position"], 1)
        self.assertEqual(prefix[2]["origin"], "session")
        self.assertEqual(prefix[2]["position"], 2)
        roster = collect_rosters_from_prefix(prefix)
        self.assertEqual(roster, [{"id": "c_1", "name": "Bình",
                                   "phone": "0902345678"}])
        # Unparseable history withholds the prefix (never partial).
        bad = [FakeTurn("assistant", tool_calls=[SEARCH],
                        tool_results="repr-string")]
        prefix, err = build_prefix(bad, [], [])
        self.assertIsNone(prefix)
        self.assertIsNotNone(err)

    def test_observer_never_raises_on_garbage(self):
        obs = ShadowObserver(enabled=True)
        obs.observe_proposal(None, None, history=[object()],
                             executed=[None], results=[None],
                             current_text=None, kinds=None)
        obs.observe_invalid(object(), history=None)
        obs.observe_validation_failure(None, None, None)
        self.assertEqual(len(obs.records), 3)
        for rec in obs.records:
            json.dumps(rec)

# ---------------------------------------------------------------------------
# R3: D1 structured-attribute qualification through the REAL runtime
# path (RAW contacts.search result -> collector -> adapter decide
# -> observer -> AgentLoop). These tests never call decide() directly
# for the D1 verdict: the verdict is read off the observer record
# produced by a real AgentLoop run with shadow ON.
#
# Vocabulary (shadow-only): candidate fired=False means the shadow
# gate PASSES the proposal ("qua"); fired=True means the shadow gate
# BLOCKS it ("chan"). The observer never enforces anything: the
# submitted calls are identical in the pass and block cases, and
# that is asserted explicitly below so a fired=True record is never
# misread as the loop refusing the call.
#
# Fixture shape (paired-dev shape train_0063/0225, synthetic only):
# two contacts share the name "Minh"; a history user turn carries
# the descriptor "khach hang" adjacent to the name. D1 qualifies
# an entry ONLY when the descriptor matches a STRUCTURED roster
# attribute (here "relation") of exactly one duplicate.
# ---------------------------------------------------------------------------

class TestObserverRosterRelationD1(unittest.TestCase):
    HISTORY = "Tìm số của Minh khách hàng dùm tôi"
    CURRENT = "Nhắn tin cho Minh"
    SEARCH = {"name": "contacts.search", "arguments": {"query": "Minh"}}
    STOP = {"stop": True}

    BASE = [{"id": "c_m1", "name": "Minh", "phone": "0903111222",
             "relation": "khách hàng"},
            {"id": "c_m2", "name": "Minh", "phone": "0903777888",
             "relation": "đối tác"}]

    def _sms(self, contact_id):
        return {"name": "sms.send",
                "arguments": {"contact_id": contact_id,
                              "content": "hi"}}

    def _run(self, searches, history_text=None, outputs=None):
        """Run a real AgentLoop (shadow ON) whose contacts.search
        calls return, in order, the (contacts, ok) pairs in
        ``searches``. Returns (records, submitted)."""
        searches = list(searches)

        class RosterEnv:
            def __init__(self):
                self.calls = []
                self.search_index = 0

            def validate(self, name, args):
                return {"ok": True}

            def call(self, name, args):
                self.calls.append({"name": name,
                                   "arguments": dict(args)})
                if name == "contacts.search":
                    idx = min(self.search_index,
                              len(searches) - 1)
                    self.search_index += 1
                    contacts, ok = searches[idx]
                    result = {"ok": ok,
                              "contacts": copy.deepcopy(contacts)}
                    if not ok:
                        result["error"] = "search failed"
                    return result
                return {"ok": True}

            def submission_line(self):
                blob = json.dumps(self.calls, sort_keys=True,
                                  ensure_ascii=False)
                return {"tool_calls": [dict(c) for c in self.calls],
                        "state_hash": hashlib.sha256(
                            blob.encode()).hexdigest()}

        cfg = PipelineConfig(shadow_observer=True)
        loop = AgentLoop(cfg, TOOLS)
        history = [FakeTurn("user", audio_text=(
            self.HISTORY if history_text is None else history_text))]
        env = RosterEnv()
        loop.run(FakeSample(history=history), self.CURRENT,
                 env, FakeGenerator(outputs))
        return ([dict(r) for r in loop.observer.records],
                loop, env)

    def _run_sms(self, searches, contact_id, history_text=None):
        records, _loop, _env = self._run(
            searches, history_text=history_text,
            outputs=[self.SEARCH, self._sms(contact_id), self.STOP])
        sms_records = [r for r in records
                       if isinstance(r["proposal_grounded"], dict)
                       and r["proposal_grounded"].get("name")
                       == "sms.send"]
        self.assertEqual(len(sms_records), 1)
        return sms_records[0]

    def _assert_passed(self, rec):
        self.assertIsNone(rec["error"])
        self.assertIsNotNone(rec["candidate_decision"])
        self.assertTrue(rec["candidate_decision"]["applicable"])
        self.assertFalse(rec["candidate_decision"]["fired"])
        self.assertEqual(rec["adjustments"], [])

    def _assert_blocked_via_selection(self, rec):
        self.assertIsNone(rec["error"])
        self.assertIsNotNone(rec["candidate_decision"])
        self.assertTrue(rec["candidate_decision"]["applicable"])
        self.assertTrue(rec["candidate_decision"]["fired"])
        self.assertTrue(any(
            a.get("mechanism") == "selection_mismatch"
            for a in rec["adjustments"]), rec["adjustments"])

    def _assert_blocked(self, rec):
        self.assertIsNone(rec["error"])
        self.assertIsNotNone(rec["candidate_decision"])
        self.assertTrue(rec["candidate_decision"]["fired"])

    def test_runtime_d1_relation_correct_passes_wrong_blocks(self):
        # BEFORE the R3 fix both arms blocked here (fired=2/2):
        # the observer stripped "relation" before decide() ever
        # saw it, so D1 could match nothing. After the fix the
        # relation-qualified entry passes and the other blocks.
        passed = self._run_sms([(self.BASE, True)], "c_m1")
        self._assert_passed(passed)
        blocked = self._run_sms([(self.BASE, True)], "c_m2")
        self._assert_blocked_via_selection(blocked)
        # Shadow-only: the loop still submits the sms in both
        # cases; the observer record is a log, not a gate.
        for cid in ("c_m1", "c_m2"):
            records, _loop, env = self._run(
                [(self.BASE, True)],
                outputs=[self.SEARCH, self._sms(cid), self.STOP])
            self.assertIn({"name": "sms.send",
                           "arguments": {"contact_id": cid,
                                         "content": "hi"}},
                          [dict(c) for c in env.calls])

    def test_runtime_d1_missing_relation_blocks_both(self):
        contacts = [{"id": "c_m1", "name": "Minh",
                     "phone": "0903111222"},
                    {"id": "c_m2", "name": "Minh",
                     "phone": "0903777888"}]
        for cid in ("c_m1", "c_m2"):
            rec = self._run_sms([(contacts, True)], cid)
            self._assert_blocked_via_selection(rec)

    def test_runtime_d1_duplicate_relation_blocks_both(self):
        contacts = [{"id": "c_m1", "name": "Minh",
                     "phone": "0903111222",
                     "relation": "khách hàng"},
                    {"id": "c_m2", "name": "Minh",
                     "phone": "0903777888",
                     "relation": "khách hàng"}]
        for cid in ("c_m1", "c_m2"):
            rec = self._run_sms([(contacts, True)], cid)
            self._assert_blocked_via_selection(rec)

    def test_runtime_d1_mismatched_descriptor_blocks_both(self):
        # Descriptor "ban hoc" matches NEITHER structured
        # relation, so it qualifies nothing -- both block.
        for cid in ("c_m1", "c_m2"):
            rec = self._run_sms(
                [(self.BASE, True)], cid,
                history_text="Tìm số của Minh bạn học dùm tôi")
            self._assert_blocked_via_selection(rec)

    def test_runtime_d1_stray_string_field_is_not_evidence(self):
        # A free-text "note" carrying the descriptor word is NOT
        # a structured attribute: with no "relation" at all, the
        # descriptor must qualify nothing, even though the note
        # literally says "khach hang".
        contacts = [{"id": "c_m1", "name": "Minh",
                     "phone": "0903111222", "note": "khách hàng"},
                    {"id": "c_m2", "name": "Minh",
                     "phone": "0903777888", "note": "đối tác"}]
        for cid in ("c_m1", "c_m2"):
            rec = self._run_sms([(contacts, True)], cid)
            self._assert_blocked_via_selection(rec)

    def test_runtime_d1_failed_search_is_not_evidence(self):
        # The search FAILED (ok False) even though its payload
        # carries a full roster with the matching relation.
        # A failed read's payload is not roster evidence, so
        # the descriptor qualifies nothing and the proposal
        # stays blocked (safe direction).
        rec = self._run_sms([(self.BASE, False)], "c_m1")
        self._assert_blocked(rec)

    def test_runtime_d1_no_future_result_rewrites_a_record(self):
        # First search returns a SINGLE Minh (no duplicate, so
        # no ambiguity yet): the sms passes. A LATER search
        # then reveals a second Minh with no relation, so a
        # second identical sms blocks. The first record must
        # still say "passed" after the run: observer records
        # are snapshots at proposal time, never recomputed
        # with results that arrived later.
        single = [{"id": "c_m1", "name": "Minh",
                   "phone": "0903111222"}]
        dup_no_relation = [{"id": "c_m1", "name": "Minh",
                            "phone": "0903111222"},
                           {"id": "c_m2", "name": "Minh",
                            "phone": "0903777888"}]
        records, _loop, _env = self._run(
            [(single, True), (dup_no_relation, True)],
            outputs=[self.SEARCH, self._sms("c_m1"),
                     self.SEARCH, self._sms("c_m1"), self.STOP])
        sms_records = [r for r in records
                       if isinstance(r["proposal_grounded"], dict)
                       and r["proposal_grounded"].get("name")
                       == "sms.send"]
        self.assertEqual(len(sms_records), 2)
        self._assert_passed(sms_records[0])
        self._assert_blocked_via_selection(sms_records[1])

    def test_collector_keeps_relation_only_allowlisted_field(self):
        raw = {"ok": True, "contacts": [
            {"id": "c_m1", "name": "Minh", "phone": "0903111222",
             "relation": "khách hàng", "note": "khách hàng",
             "label": "khách hàng", "nickname": "Minh",
             "extra": {"relation": "khách hàng"}},
            {"id": "c_m2", "name": "Minh", "phone": "0903777888",
             "relation": 123},
            {"id": "c_m3", "name": "Minh", "phone": "0903999999",
             "relation": "   "},
            {"id": "c_m4", "name": "Minh", "phone": "0903888888",
             "relation": None}]}
        prefix = [{"tool": "contacts.search", "args": {},
                   "result": raw, "outcome": "succeeded",
                   "position": 0, "origin": "session"}]
        roster = collect_rosters_from_prefix(prefix)
        self.assertEqual(roster, [
            {"id": "c_m1", "name": "Minh", "phone": "0903111222",
             "relation": "khách hàng"},
            {"id": "c_m2", "name": "Minh", "phone": "0903777888"},
            {"id": "c_m3", "name": "Minh", "phone": "0903999999"},
            {"id": "c_m4", "name": "Minh", "phone": "0903888888"}])

    def test_collector_success_only(self):
        def entry(result, outcome=_SENTINEL):
            e = {"tool": "contacts.search", "args": {},
                 "result": result, "position": 0,
                 "origin": "session"}
            if outcome is not _SENTINEL:
                e["outcome"] = outcome
            return e

        good = {"ok": True, "contacts": copy.deepcopy(self.BASE)}
        # Every non-success shape contributes nothing, even
        # with a full contacts payload attached.
        for prefix in (
                [entry({"ok": False, "contacts": self.BASE},
                       "schema_rejected")],
                [entry({"ok": True, "done": False,
                        "contacts": self.BASE}, "noop")],
                [entry({"contacts": self.BASE}, "unknown")],
                [entry({"ok": False, "contacts": self.BASE})],
                [entry({"ok": True, "done": False,
                        "contacts": self.BASE})],
                [entry({"contacts": self.BASE})]):
            self.assertEqual(collect_rosters_from_prefix(prefix), [])
        # Success shapes keep the relation.
        for prefix in ([entry(good, "succeeded")],
                       [entry(good)]):
            self.assertEqual(collect_rosters_from_prefix(prefix), [
                {"id": "c_m1", "name": "Minh",
                 "phone": "0903111222", "relation": "khách hàng"},
                {"id": "c_m2", "name": "Minh",
                 "phone": "0903777888", "relation": "đối tác"}])
        # A failed first read does not poison a later successful
        # one for the same id: the successful entry is the
        # first SUCCESSFUL entry, so it wins the dedup.
        prefix = [entry({"ok": False, "contacts": self.BASE},
                        "schema_rejected"),
                  entry(good, "succeeded")]
        self.assertEqual(collect_rosters_from_prefix(prefix), [
            {"id": "c_m1", "name": "Minh", "phone": "0903111222",
             "relation": "khách hàng"},
            {"id": "c_m2", "name": "Minh", "phone": "0903777888",
             "relation": "đối tác"}])

    # ---- R4 backfill (Run 4, this branch) + R4-CONFLICT ----
    # Rule (same in observer, harness, and agent): same
    # contact_id, first successful read missing a field,
    # later successful read carrying it -> fill ONLY the
    # missing field. Never overwrite with an empty /
    # invalid value, failed reads neither create nor
    # backfill an entry, and a differing valid value
    # from a later successful read REPLACES the older
    # one (last-wins, R4-CONFLICT -- this supersedes the
    # R4 backfill keep-first rule for conflicts).
    def test_collector_backfills_missing_relation(self):
        missing = [{"id": "c_m1", "name": "Minh",
                    "phone": "0903111222"},
                   {"id": "c_m2", "name": "Minh",
                    "phone": "0903777888",
                    "relation": "đối tác"}]
        prefix = [
            {"tool": "contacts.search", "args": {},
             "result": {"ok": True, "contacts": missing},
             "outcome": "succeeded", "position": 0,
             "origin": "session"},
            {"tool": "contacts.search", "args": {},
             "result": {"ok": True, "contacts": self.BASE},
             "outcome": "succeeded", "position": 1,
             "origin": "session"}]
        roster = collect_rosters_from_prefix(prefix)
        # One entry per id, first-seen order kept, and the
        # missing relation is now present on c_m1.
        self.assertEqual(roster, [
            {"id": "c_m1", "name": "Minh", "phone": "0903111222",
             "relation": "khách hàng"},
            {"id": "c_m2", "name": "Minh", "phone": "0903777888",
             "relation": "đối tác"}])

    def test_collector_backfill_converse_keeps_relation(self):
        missing = [{"id": "c_m1", "name": "Minh",
                    "phone": "0903111222"},
                   {"id": "c_m2", "name": "Minh",
                    "phone": "0903777888"}]
        prefix = [
            {"tool": "contacts.search", "args": {},
             "result": {"ok": True, "contacts": self.BASE},
             "outcome": "succeeded", "position": 0,
             "origin": "session"},
            {"tool": "contacts.search", "args": {},
             "result": {"ok": True, "contacts": missing},
             "outcome": "succeeded", "position": 1,
             "origin": "session"}]
        self.assertEqual(collect_rosters_from_prefix(prefix), [
            {"id": "c_m1", "name": "Minh", "phone": "0903111222",
             "relation": "khách hàng"},
            {"id": "c_m2", "name": "Minh", "phone": "0903777888",
             "relation": "đối tác"}])

    def test_collector_backfill_never_overwrites_empty_last_wins_on_conflict(self):
        # Later empty / blank relation: no overwrite.
        for later in ([{"id": "c_m1", "name": "Minh",
                        "phone": "0903111222", "relation": "   "}],
                      [{"id": "c_m1", "name": "Minh",
                        "phone": "0903111222"}]):
            prefix = [
                {"tool": "contacts.search", "args": {},
                 "result": {"ok": True, "contacts": self.BASE},
                 "outcome": "succeeded", "position": 0,
                 "origin": "session"},
                {"tool": "contacts.search", "args": {},
                 "result": {"ok": True, "contacts": later},
                 "outcome": "succeeded", "position": 1,
                 "origin": "session"}]
            self.assertEqual(
                collect_rosters_from_prefix(prefix)[0]["relation"],
                "khách hàng")
        # Later conflicting non-empty relation: LAST-WINS
        # (R4-CONFLICT rule change, not a dodged case: the
        # old keep-first expectation is superseded here).
        conflict = [{"id": "c_m1", "name": "Minh",
                     "phone": "0903111222", "relation": "đối tác"},
                    {"id": "c_m2", "name": "Minh",
                     "phone": "0903777888",
                     "relation": "đối tác"}]
        prefix = [
            {"tool": "contacts.search", "args": {},
             "result": {"ok": True, "contacts": self.BASE},
             "outcome": "succeeded", "position": 0,
             "origin": "session"},
            {"tool": "contacts.search", "args": {},
             "result": {"ok": True, "contacts": conflict},
             "outcome": "succeeded", "position": 1,
             "origin": "session"}]
        self.assertEqual(collect_rosters_from_prefix(prefix), [
            {"id": "c_m1", "name": "Minh", "phone": "0903111222",
             "relation": "đối tác"},
            {"id": "c_m2", "name": "Minh", "phone": "0903777888",
             "relation": "đối tác"}])

    def test_collector_failed_read_neither_creates_nor_backfills(self):
        missing = [{"id": "c_m1", "name": "Minh",
                    "phone": "0903111222"},
                   {"id": "c_m2", "name": "Minh",
                    "phone": "0903777888"}]
        # Failed later read carrying the relation: no backfill.
        prefix = [
            {"tool": "contacts.search", "args": {},
             "result": {"ok": True, "contacts": missing},
             "outcome": "succeeded", "position": 0,
             "origin": "session"},
            {"tool": "contacts.search", "args": {},
             "result": {"ok": False, "contacts": self.BASE},
             "outcome": "schema_rejected", "position": 1,
             "origin": "session"}]
        self.assertEqual(collect_rosters_from_prefix(prefix), missing)
        # Failed first read carrying the relation, then a
        # successful missing read: the failed read created
        # nothing, so the roster stays missing-relation.
        prefix = [
            {"tool": "contacts.search", "args": {},
             "result": {"ok": False, "contacts": self.BASE},
             "outcome": "schema_rejected", "position": 0,
             "origin": "session"},
            {"tool": "contacts.search", "args": {},
             "result": {"ok": True, "contacts": missing},
             "outcome": "succeeded", "position": 1,
             "origin": "session"}]
        self.assertEqual(collect_rosters_from_prefix(prefix), missing)

    def _run_two_searches_sms(self, searches, contact_id):
        records, _loop, _env = self._run(
            searches,
            outputs=[self.SEARCH, self.SEARCH,
                     self._sms(contact_id), self.STOP])
        sms_records = [r for r in records
                       if isinstance(r["proposal_grounded"], dict)
                       and r["proposal_grounded"].get("name")
                       == "sms.send"]
        self.assertEqual(len(sms_records), 1)
        return sms_records[0]

    def test_runtime_backfill_first_missing_later_with_relation(self):
        # Exact R3 final-review item 2 repro: on 99779d8 this
        # blocked via selection_mismatch even after the
        # complete second read. With backfill it must pass
        # for the correct person and still block the wrong one.
        missing = [{"id": "c_m1", "name": "Minh",
                    "phone": "0903111222"},
                   {"id": "c_m2", "name": "Minh",
                    "phone": "0903777888",
                    "relation": "đối tác"}]
        passed = self._run_two_searches_sms(
            [(missing, True), (self.BASE, True)], "c_m1")
        self._assert_passed(passed)
        blocked = self._run_two_searches_sms(
            [(missing, True), (self.BASE, True)], "c_m2")
        self._assert_blocked_via_selection(blocked)

    def test_runtime_backfill_converse_and_failed_paths(self):
        missing = [{"id": "c_m1", "name": "Minh",
                    "phone": "0903111222"},
                   {"id": "c_m2", "name": "Minh",
                    "phone": "0903777888"}]
        # Converse: full first, missing later -> still passes.
        rec = self._run_two_searches_sms(
            [(self.BASE, True), (missing, True)], "c_m1")
        self._assert_passed(rec)
        # Failed first does not poison a later successful full read.
        rec = self._run_two_searches_sms(
            [(self.BASE, False), (self.BASE, True)], "c_m1")
        self._assert_passed(rec)
        # Failed later does not backfill: missing first, failed
        # full later -> still blocks both (no relation evidence).
        rec = self._run_two_searches_sms(
            [(missing, True), (self.BASE, False)], "c_m1")
        self._assert_blocked_via_selection(rec)

    def test_runtime_backfill_conflict_last_wins_blocks(self):
        conflict = [{"id": "c_m1", "name": "Minh",
                     "phone": "0903111222", "relation": "đối tác"},
                    {"id": "c_m2", "name": "Minh",
                     "phone": "0903777888",
                     "relation": "đối tác"}]
        # Last-wins (R4-CONFLICT): the later conflicting
        # relation replaces the first, so c_m1 is now a
        # duplicate đối tác and blocks via selection --
        # the old keep-first pass is superseded, not dodged.
        rec = self._run_two_searches_sms(
            [(self.BASE, True), (conflict, True)], "c_m1")
        self._assert_blocked_via_selection(rec)


_SENTINEL = object()


class TestObserverIdentityContactId(unittest.TestCase):
    """Run 5 identity fix, runtime path: RAW contacts.search
    result -> collector -> adapter -> observer -> real
    AgentLoop (shadow ON). Verdicts are read off observer
    records, never from decide() directly. The loop still
    submits the sms in both arms (shadow-only), asserted
    for the core case.
    """

    SEARCH = {"name": "contacts.search", "arguments": {"query": "Lan"}}
    STOP = {"stop": True}

    def _sms(self, contact_id):
        return {"name": "sms.send",
                "arguments": {"contact_id": contact_id,
                              "content": "hi"}}

    def _run_sms(self, contacts, contact_id, history_text, current):
        searches = [(contacts, True)]

        class RosterEnv:
            def __init__(self):
                self.calls = []
                self.search_index = 0

            def validate(self, name, args):
                return {"ok": True}

            def call(self, name, args):
                self.calls.append({"name": name,
                                   "arguments": dict(args)})
                if name == "contacts.search":
                    contacts_, ok = searches[self.search_index]
                    self.search_index += 1
                    return {"ok": ok,
                            "contacts": copy.deepcopy(contacts_)}
                return {"ok": True}

            def submission_line(self):
                blob = json.dumps(self.calls, sort_keys=True,
                                  ensure_ascii=False)
                return {"tool_calls": [dict(c) for c in self.calls],
                        "state_hash": hashlib.sha256(
                            blob.encode()).hexdigest()}

        cfg = PipelineConfig(shadow_observer=True)
        loop = AgentLoop(cfg, TOOLS)
        history = [FakeTurn("user", audio_text=history_text)]
        env = RosterEnv()
        loop.run(FakeSample(history=history), current, env,
                 FakeGenerator([self.SEARCH,
                                self._sms(contact_id), self.STOP]))
        records = [r for r in loop.observer.records
                   if isinstance(r["proposal_grounded"], dict)
                   and r["proposal_grounded"].get("name")
                   == "sms.send"]
        self.assertEqual(len(records), 1)
        return records[0], env

    def _assert_passed(self, rec):
        self.assertIsNone(rec["error"])
        self.assertFalse(rec["candidate_decision"]["fired"])
        self.assertEqual(rec["adjustments"], [])

    def _assert_blocked_via_selection(self, rec):
        self.assertIsNone(rec["error"])
        self.assertTrue(rec["candidate_decision"]["fired"])
        self.assertTrue(any(
            a.get("mechanism") == "selection_mismatch"
            for a in rec["adjustments"]), rec["adjustments"])

    def test_runtime_identity_core_missing_phone(self):
        contacts = [{"id": "c1", "name": "Lan",
                     "phone": "0903111222",
                     "relation": "đồng nghiệp"},
                    {"id": "c2", "name": "Lan", "phone": "",
                     "relation": "hàng xóm"}]
        history = "Tìm số của Lan đồng nghiệp giúp tôi"
        current = "Nhắn cho Lan: Chào bạn"
        rec, _env = self._run_sms(contacts, "c1", history, current)
        self._assert_passed(rec)
        rec, _env = self._run_sms(contacts, "c2", history, current)
        self._assert_blocked_via_selection(rec)
        for cid in ("c1", "c2"):
            _rec, env = self._run_sms(contacts, cid, history,
                                      current)
            self.assertIn({"name": "sms.send",
                           "arguments": {"contact_id": cid,
                                         "content": "hi"}},
                          [dict(c) for c in env.calls])

    def test_runtime_identity_both_missing(self):
        contacts = [{"id": "c1", "name": "Lan", "phone": "",
                     "relation": "đồng nghiệp"},
                    {"id": "c2", "name": "Lan", "phone": "",
                     "relation": "hàng xóm"}]
        history = "Tìm số của Lan đồng nghiệp giúp tôi"
        current = "Nhắn cho Lan: Chào bạn"
        rec, _env = self._run_sms(contacts, "c1", history, current)
        self._assert_passed(rec)
        rec, _env = self._run_sms(contacts, "c2", history, current)
        self._assert_blocked_via_selection(rec)

    def test_runtime_identity_shared_phone(self):
        contacts = [{"id": "c1", "name": "Lan",
                     "phone": "0903111222",
                     "relation": "đồng nghiệp"},
                    {"id": "c2", "name": "Lan",
                     "phone": "0903111222",
                     "relation": "hàng xóm"}]
        history = "Tìm số của Lan đồng nghiệp giúp tôi"
        for current in ("Nhắn cho Lan: Chào bạn",
                        "Nhắn cho Lan số 0903111222"):
            with self.subTest(current=current):
                rec, _env = self._run_sms(contacts, "c1", history,
                                          current)
                self._assert_passed(rec)
                rec, _env = self._run_sms(contacts, "c2", history,
                                          current)
                self._assert_blocked_via_selection(rec)

    def test_runtime_identity_unseen_name_order_swapped(self):
        # Same structural rule, unseen name, search order
        # swapped: the correct id is second in the roster.
        contacts = [{"id": "c2", "name": "Thu", "phone": "",
                     "relation": "hàng xóm"},
                    {"id": "c1", "name": "Thu",
                     "phone": "0903111222",
                     "relation": "đồng nghiệp"}]
        history = "Tìm số của Thu đồng nghiệp giúp tôi"
        current = "Nhắn cho Thu"
        rec, _env = self._run_sms(contacts, "c1", history, current)
        self._assert_passed(rec)
        rec, _env = self._run_sms(contacts, "c2", history, current)
        self._assert_blocked_via_selection(rec)


class TestObserverSelectionDecisionR4(unittest.TestCase):
    """R4: whole notes.selection_decision dict copied into the
    observer record, additively, shadow-only.

    The Vy scenario is the R3 final-review item 8 H2-S11 path
    (history positive turn, then a search supplying the roster,
    then a phone.call proposal under a question / completion
    current text), run on a REAL AgentLoop. No old field is
    changed: fired/applicable, adjustments and eligibility are
    asserted alongside the new field, and OFF vs ON behaviour
    (submitted calls, state hash) must be identical."""

    POSITIVE = "Gọi số 0903111222 giúp tôi"
    QUESTION = "Tôi đã gọi số 0903111222 chưa?"
    COMPLETED = "Tôi đã gọi số 0903111222 rồi"

    def _run_vy(self, current, shadow=True):
        class VyEnv:
            def __init__(self):
                self.calls = []

            def validate(self, name, args):
                return {"ok": True}

            def call(self, name, args):
                self.calls.append({"name": name,
                                   "arguments": dict(args)})
                if name == "contacts.search":
                    return {"ok": True, "contacts": [
                        {"id": "c_vy", "name": "Vy",
                         "phone": "0903111222"}]}
                return {"ok": True}

            def submission_line(self):
                blob = json.dumps(self.calls, sort_keys=True,
                                  ensure_ascii=False)
                return {"tool_calls": [dict(c) for c in self.calls],
                        "state_hash": hashlib.sha256(
                            blob.encode()).hexdigest()}

        cfg = PipelineConfig(shadow_observer=shadow)
        loop = AgentLoop(cfg, TOOLS)
        env = VyEnv()
        sub = loop.run(
            FakeSample(history=[FakeTurn(
                "user", audio_text=self.POSITIVE)]),
            current, env, FakeGenerator([
                {"name": "contacts.search",
                 "arguments": {"query": "Vy"}},
                {"name": "phone.call",
                 "arguments": {"contact_id": "c_vy"}},
                STOP]))
        records = [dict(r) for r in loop.observer.records]
        if not shadow:
            # Flag OFF: the loop skips every observer call,
            # so there are no records at all by design.
            self.assertEqual(records, [])
            return None, sub, env
        call_records = [r for r in records
                        if isinstance(r["proposal_grounded"], dict)
                        and r["proposal_grounded"].get("name")
                        == "phone.call"]
        self.assertEqual(len(call_records), 1)
        return call_records[0], sub, env

    def test_unknown_pending_selection_decision_copied_whole(self):
        rec, _sub, _env = self._run_vy(self.QUESTION)
        self.assertIsNone(rec["error"])
        self.assertTrue(rec["candidate_decision"]["fired"])
        self.assertTrue(any(
            a.get("mechanism") == "unknown_pending"
            for a in rec["adjustments"]), rec["adjustments"])
        sel = rec.get("selection_decision")
        self.assertIsInstance(sel, dict)
        # Whole dict, verbatim -- not just fired/applicable,
        # and not normalised: unknown_kind and last_event are
        # the fields the old record lost.
        self.assertEqual(sel["decision"], "unknown_pending")
        self.assertEqual(sel["unknown_kind"], "question_after_positive")
        self.assertEqual(sel["active_status"], "pending_unproven")
        self.assertEqual(sel["blocked_subtype"], "question")
        self.assertEqual(sel["mismatch"], "unknown_pending")
        self.assertEqual(sel["last_event"],
                         {"kind": "positive_request",
                          "turn_position": 0,
                          "evidence": "history_text"})
        # JSON round-trip: the field survives serialisation
        # exactly, as an export would re-read it.
        reread = json.loads(json.dumps(rec, ensure_ascii=False))
        self.assertEqual(reread, rec)
        self.assertEqual(reread["selection_decision"], sel)

    def test_mismatch_selection_decision_copied_without_synthesis(self):
        rec, _sub, _env = self._run_vy(self.COMPLETED)
        self.assertTrue(rec["candidate_decision"]["fired"])
        sel = rec.get("selection_decision")
        self.assertIsInstance(sel, dict)
        self.assertEqual(sel["decision"], "mismatch")
        self.assertEqual(sel["active_status"], "discharged")
        self.assertEqual(sel["blocked_subtype"], "completion")
        self.assertEqual(sel["mismatch"], "blocked_request")
        self.assertEqual(sel["last_event"],
                         {"kind": "positive_request",
                          "turn_position": 0,
                          "evidence": "history_text"})
        # The adapter's mismatch dict has NO unknown_kind;
        # the copy must not invent one.
        self.assertNotIn("unknown_kind", sel)

    def test_records_without_selection_decision_keep_old_shape(self):
        on = run_case([SEARCH, CALL_X, STOP], shadow=True)
        for rec in on["records"]:
            self.assertNotIn("selection_decision", rec)
            self.assertEqual(set(rec.keys()), SCHEMA_KEYS)

    def test_selection_decision_does_not_change_behaviour(self):
        on_rec, on_sub, on_env = self._run_vy(self.QUESTION, shadow=True)
        off_rec, off_sub, off_env = self._run_vy(self.QUESTION,
                                                  shadow=False)
        # Shadow ON vs OFF: same submitted calls, same state
        # hash, same env calls. The new log field changes
        # nothing the agent does.
        self.assertEqual(on_sub["tool_calls"], off_sub["tool_calls"])
        self.assertEqual(on_sub["state_hash"], off_sub["state_hash"])
        self.assertEqual([dict(c) for c in on_env.calls],
                         [dict(c) for c in off_env.calls])
        self.assertIn("selection_decision", on_rec)


# ---------------------------------------------------------------------------
# Independent old-baseline control: the same fixtures run on the
# UNMODIFIED frozen-v10 agent in a subprocess (PYTHONPATH = frozen root),
# so the frozen package cannot collide with the new one. The runner is
# self-contained: it duplicates the tiny fakes instead of importing
# this file, so a shared-fixture bug cannot hide a real difference.
# ---------------------------------------------------------------------------

BASELINE_RUNNER = r'''
import copy, hashlib, json, sys
from types import SimpleNamespace

TOOLS = {
    "contacts.search": {"kind": "read", "description": "search contacts",
                        "parameters": {"required": []}},
    "contacts.get": {"kind": "read", "description": "get contact",
                     "parameters": {"required": ["contact_id"]}},
    "phone.call": {"kind": "write", "description": "call",
                   "parameters": {"required": ["phone_number"]}},
    "sms.send": {"kind": "write", "description": "send sms",
                 "parameters": {"required": ["contact_id", "content"]}},
    "tasks.add": {"kind": "write", "description": "add task",
                  "parameters": {"required": ["title"]}},
    "sys.ask_missing_info": {"kind": "meta", "description": "ask",
                            "parameters": {"required": ["tool_name",
                                                        "params"]}},
}
CALL_X = {"name": "phone.call", "arguments": {"phone_number": "0902345678"}}
SEARCH = {"name": "contacts.search", "arguments": {"query": "Bình"}}
TASK = {"name": "tasks.add", "arguments": {"title": "Nhắc uống nước"}}
SMS = {"name": "sms.send", "arguments": {"contact_id": "c_1", "content": "hi"}}
ASK = {"name": "sys.ask_missing_info",
       "arguments": {"tool_name": "phone.call", "params": ["contact_id"]}}
STOP = {"stop": True}
SMS_NAME = {"name": "sms.send",
            "arguments": {"contact_name": "Bình", "content": "hi"}}


class Turn:
    def __init__(self, role, audio_text=None, text=None, tool_calls=None,
                 tool_results=None):
        self.role = role
        self.audio_text = audio_text
        self.text = text
        self.tool_calls = tool_calls or []
        self.tool_results = tool_results


class Sample:
    def __init__(self):
        self.id = "test-sample"
        self.split = "dev"
        self.audio = ""
        self.context = {"current_time": "2026-10-30T09:00:00+07:00",
                        "timezone": "Asia/Ho_Chi_Minh",
                        "user_profile": {"name": "Test", "city": "HCMC"}}
        self.history = []
        self.audio_text = None
        self.label = None


class Env:
    def __init__(self, reject=None, noop_names=None):
        self.calls = []
        self.reject = reject or {}
        self.noop_names = set(noop_names or [])

    def validate(self, name, args):
        if name in self.reject:
            return {"ok": False, "error": self.reject[name]}
        return {"ok": True}

    def call(self, name, args):
        self.calls.append({"name": name, "arguments": dict(args)})
        if name in self.noop_names:
            return {"ok": True, "done": False, "message": "noop"}
        if name == "contacts.search":
            return {"ok": True,
                    "contacts": [{"id": "c_1", "name": "Bình",
                                  "phone": "0902345678"}]}
        return {"ok": True}

    def submission_line(self):
        blob = json.dumps(self.calls, sort_keys=True, ensure_ascii=False)
        return {"tool_calls": [dict(c) for c in self.calls],
                "state_hash": hashlib.sha256(blob.encode()).hexdigest()}


class Gen:
    def __init__(self, outputs):
        self.outputs = [copy.deepcopy(o) for o in outputs]
        self.prompts = []
        self.index = 0

    def __call__(self, prompt, tools):
        self.prompts.append(prompt)
        if self.index < len(self.outputs):
            out = self.outputs[self.index]
            self.index += 1
            return copy.deepcopy(out)
        return None


from lifemate.agent import AgentLoop

FIXTURES = {
    "normal": ([SEARCH, CALL_X, STOP], False, 12, None, None),
    "empty": ([], False, 12, None, None),
    "invalid": (["not a dict", {"arguments": {}}, None], False, 12,
                None, None),
    "validation_rejection": ([CALL_X, TASK, STOP], False, 12,
                             {"phone.call": "bad args"}, None),
    "noop": ([TASK, STOP], False, 12, None, {"tasks.add"}),
    "repeated": ([CALL_X, CALL_X, CALL_X, STOP], False, 12, None, None),
    "max_steps": ([SEARCH, CALL_X, TASK, SMS, STOP], False, 2, None, None),
    "ask_direct": ([ASK, STOP], False, 12, None, None),
    "grounded_ask": ([SMS_NAME, STOP], True, 12, None, None),
}

out = {}
for name, (outputs, grounding, max_steps, reject, noop) in FIXTURES.items():
    cfg = SimpleNamespace(max_steps=max_steps, max_repeats=2,
                          grounding=grounding)
    loop = AgentLoop(cfg, TOOLS)
    gen = Gen(outputs)
    env = Env(reject=reject, noop_names=noop)
    sub = loop.run(Sample(), "Gọi số 0902345678 giúp tôi", env, gen)
    out[name] = {"prompts": list(gen.prompts),
                 "gen_calls": len(gen.prompts),
                 "submitted": sub["tool_calls"],
                 "state_hash": sub["state_hash"],
                 "env_calls": [dict(c) for c in env.calls]}
print(json.dumps(out, ensure_ascii=False))
'''

# (outputs, grounding, max_steps, reject, noop_names) per fixture — the
# same fixtures the baseline runner executes.
CONTROL_FIXTURES = {
    "normal": ([SEARCH, CALL_X, STOP], False, 12, None, None),
    "empty": ([], False, 12, None, None),
    "invalid": (["not a dict", {"arguments": {}}, None], False, 12,
                None, None),
    "validation_rejection": ([CALL_X, TASK, STOP], False, 12,
                             {"phone.call": "bad args"}, None),
    "noop": ([TASK, STOP], False, 12, None, {"tasks.add"}),
    "repeated": ([CALL_X, CALL_X, CALL_X, STOP], False, 12, None, None),
    "max_steps": ([SEARCH, CALL_X, TASK, SMS, STOP], False, 2, None, None),
    "ask_direct": ([ASK, STOP], False, 12, None, None),
    "grounded_ask": ([{"name": "sms.send",
                       "arguments": {"contact_name": "Bình",
                                     "content": "hi"}}, STOP],
                     True, 12, None, None),
}


def run_frozen_baseline():
    """Run the control fixtures on the frozen-v10 agent in a
    subprocess; return {fixture: behaviour dict}."""
    import os
    with tempfile.TemporaryDirectory() as tmp:
        runner = Path(tmp) / "baseline_runner.py"
        runner.write_text(BASELINE_RUNNER, encoding="utf-8")
        env = dict(os.environ)
        env["PYTHONPATH"] = str(FROZEN_ROOT)
        proc = subprocess.run(
            [sys.executable, str(runner)],
            cwd=tmp, env=env, capture_output=True, text=True, timeout=180)
    if proc.returncode != 0:
        raise AssertionError(
            "frozen baseline runner failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr))
    return json.loads(proc.stdout)


class TestOldBaselineControl(unittest.TestCase):
    def test_frozen_agent_matches_off_and_on(self):
        # The frozen-v10 control tree is a local reference, not part
        # of the repo: skip (do not fail) where it is absent, so the
        # suite runs on any checkout without a private workspace path.
        if not FROZEN_ROOT.is_dir():
            self.skipTest("frozen-v10 reference tree absent: %s"
                          % FROZEN_ROOT)
        frozen = run_frozen_baseline()
        self.assertEqual(set(frozen.keys()), set(CONTROL_FIXTURES.keys()))
        for name, (outputs, grounding, max_steps, reject, noop) in \
                CONTROL_FIXTURES.items():
            env_off = FakeEnv(reject=reject, noop_names=noop)
            env_on = FakeEnv(reject=reject, noop_names=noop)
            off = run_case(outputs, shadow=False, grounding=grounding,
                           max_steps=max_steps, env=env_off)
            on = run_case(outputs, shadow=True, grounding=grounding,
                          max_steps=max_steps, env=env_on)
            assert_behaviour_equal(self, frozen[name], off,
                                   f"baseline-control/{name}/OFF")
            assert_behaviour_equal(self, frozen[name], on,
                                   f"baseline-control/{name}/ON")


# ------------------------------------------------------------------
# Clean-process package-mode observer contract (observer import fix).
#
# At d1090d1d the observer computed NO decision in a real entrypoint
# process (repo root on sys.path, no lifemate/ entry) because the
# adapter used top-level imports that only worked when tests added
# lifemate/ to sys.path. This test pins the real contract: a FRESH
# interpreter, cwd = repo root, NO PYTHONPATH, NO preloaded test
# modules, must produce a real baseline/candidate decision with
# error=None -- and the decisions must equal a direct in-process
# decide() call on the same inputs (one code path, one identity).
# ------------------------------------------------------------------

_CLEAN_CHILD = r'''
import json, sys
# For `python -c`, sys.path[0] is '' (the cwd). The repo root must be
# the only lifemate-resolving entry: no entry may be the lifemate/
# directory itself.
assert not any(
    p and (p.rstrip("/") == "lifemate"
           or p.rstrip("/").endswith("/lifemate"))
    for p in sys.path), sys.path
from lifemate.lifemate_observer import ShadowObserver
obs = ShadowObserver(True)
call = {"name": "phone.call",
        "arguments": {"phone_number": "0902345678"}}
obs.observe_proposal(
    call, call, history=[], executed=[], results=[],
    current_text="Gọi số0902345678",
    kinds={"phone.call": "write"})
rec = obs.records[0]
assert rec["error"] is None, rec
assert isinstance(rec["baseline_decision"], dict), rec
assert isinstance(rec["candidate_decision"], dict), rec
assert isinstance(rec["baseline_decision"]["fired"], bool), rec
assert isinstance(rec["candidate_decision"]["fired"], bool), rec
# Package identity: the gate module must be loaded as lifemate.*,
# never a second top-level copy.
assert "lifemate.lifemate_gates" in sys.modules, sorted(sys.modules)
assert "lifemate_gates" not in sys.modules, "dual module identity"
print(json.dumps(rec, ensure_ascii=False))
'''


class TestCleanProcessPackageObserver(unittest.TestCase):
    def test_observer_computes_decision_in_clean_process(self):
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        proc = subprocess.run(
            [sys.executable, "-c", _CLEAN_CHILD],
            cwd=str(ROOT), env=env, capture_output=True, text=True,
            timeout=180)
        self.assertEqual(proc.returncode, 0,
                         "clean-process observer run failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
                         % (proc.stdout, proc.stderr))
        rec = json.loads(proc.stdout.strip().splitlines()[-1])
        self.assertIsNone(rec["error"])
        self.assertIsInstance(rec["baseline_decision"], dict)
        self.assertIsInstance(rec["candidate_decision"], dict)
        # Same inputs through the direct in-process path must give
        # the same decisions: one code path, not two identities.
        from lifemate.lifemate_gates_adapter import decide
        direct = decide(
            {"name": "phone.call",
             "arguments": {"phone_number": "0902345678"}},
            [], [], "Gọi số0902345678", {"phone.call": "write"},
            proposal_position=0, eligibility=True)
        self.assertEqual(rec["baseline_decision"]["fired"],
                         direct.baseline_fired)
        self.assertEqual(rec["baseline_decision"]["applicable"],
                         direct.applicable)
        self.assertEqual(rec["candidate_decision"]["fired"], direct.fired)
        self.assertEqual(rec["candidate_decision"]["applicable"],
                         direct.applicable)


if __name__ == "__main__":
    unittest.main(verbosity=2)
