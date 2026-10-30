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
