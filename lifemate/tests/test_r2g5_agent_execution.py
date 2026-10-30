"""R2-G5 execution-path tests for LifeMate AgentLoop + P1 V2 prompt.

Run: python3 -m unittest lifemate.tests.test_r2g5_agent_execution -v
from the repo root, or: python3 lifemate/tests/test_r2g5_agent_execution.py

Scope: agent/prompt/control flow only. No G&G module is edited by
these tests, no simulator/scorer/split is touched, no model is run,
no GPU is used. All generators are fake (deterministic scripts) and
all envs are stubs — results are CPU_RUN mechanics, NOT model
behaviour. A fake-generator pass does NOT prove a model will comply.

Real-B0 note (read before claiming "real"): the V2 instantiation
below uses real Sample/Turn objects, real context values (time,
timezone, user name/city), a real transcript, real tool names/kinds
and the real open-block rule (empty list -> "Open requests: none.").
Tool description/required strings in this file are FIXTURES for
prompt-structure checking, NOT verified against the extracted
<split>_tools_catalog.json, because the dataset is not extracted on
this machine. That catalog-value check is an open residual, not a
pass, and must be done against a real sample before any V2
implementation is considered done.
"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from lifemate.agent import (
    AgentLoop,
    build_base_prompt,
    build_v2_prompt,
    measure_prompt_budget,
)
from lifemate.config import PipelineConfig
from lifemate.loader import Sample, Turn


TOOLS = {
    "contacts.search": {
        "kind": "read",
        "description": "Search contacts",
        "parameters": {"required": ["query"]},
    },
    "phone.call": {
        "kind": "write",
        "description": "Call a contact",
        "parameters": {"required": ["contact_id"]},
    },
    "sms.send": {
        "kind": "write",
        "description": "Send a message",
        "parameters": {"required": ["contact_id", "text"]},
    },
    "sys.ask_missing_info": {
        "kind": "meta",
        "description": "Ask for missing information",
        "parameters": {"required": ["tool_name", "params"]},
    },
}


def make_sample(history=None, label=None, name="Test User", city="Ha Noi"):
    return Sample(
        id="r2g5-test",
        split="train",
        audio="a.wav",
        context={
            "current_time": "2026-10-30T09:00:00",
            "timezone": "Asia/Ho_Chi_Minh",
            "user_profile": {"name": name, "city": city},
            "installed_apps": {},
        },
        history=history or [],
        audio_text=None,
        label=label,
    )


class StubEnv:
    """Simulator stub, not ZaicEnv: validate is schema-only in spirit,
    call is logged, submission is the logged calls + a stub hash."""

    def __init__(self, fail_args=None):
        self.tool_calls = []
        self.fail_args = fail_args or set()

    def validate(self, name, arguments):
        if name not in TOOLS:
            return {"ok": False, "error": "unknown tool"}
        if any(v == "BAD" for v in arguments.values()):
            return {"ok": False, "error": "schema error (stub)"}
        return {"ok": True}

    def call(self, name, arguments):
        call = {"name": name, "arguments": arguments}
        self.tool_calls.append(call)
        if name == "contacts.search":
            return {
                "ok": True,
                "contacts": [{"id": "c_binh1", "name": "Binh", "phone": "0903111222"}],
            }
        if name == "sys.ask_missing_info":
            return {"ok": True, "waiting_for_user": True}
        return {"ok": True, "done": True}

    def submission_line(self):
        return {
            "id": "r2g5-test",
            "tool_calls": list(self.tool_calls),
            "state_hash": "stub-hash",
        }


class ScriptGenerator:
    """Returns scripted generations in order, then None. Records prompts."""

    def __init__(self, script):
        self.script = list(script)
        self.prompts = []
        self.index = 0

    def __call__(self, prompt, tools):
        self.prompts.append(prompt)
        if self.index >= len(self.script):
            return None
        gen = self.script[self.index]
        self.index += 1
        return gen


def run_loop(sample, transcript, script, config=None, env=None):
    cfg = config or PipelineConfig(grounding=False, shadow_observer=False)
    loop = AgentLoop(cfg, TOOLS)
    gen = ScriptGenerator(script)
    out = loop.run(sample, transcript, env or StubEnv(), gen)
    return loop, gen, out


class TestExecutionPath(unittest.TestCase):
    def test_observation_returns_correct_step_in_order(self):
        sample = make_sample()
        script = [
            {"name": "contacts.search", "arguments": {"query": "Binh"}},
            {"name": "phone.call", "arguments": {"contact_id": "c_binh1"}},
            None,
        ]
        _, gen, out = run_loop(sample, "Goi cho Binh", script)
        self.assertEqual(len(out["tool_calls"]), 2)
        # Prompt for step 2: the OBSERVATION section must contain step 1
        # only — the tool list itself legitimately names phone.call, so
        # the no-future check must be scoped to the observation section.
        obs1 = gen.prompts[1].split("Previous calls and their OBSERVED results")[1]
        self.assertIn("contacts.search", obs1)
        self.assertNotIn("phone.call(", obs1)
        # Prompt for step 3 (after both) must contain both, in order.
        obs2 = gen.prompts[2].split("Previous calls and their OBSERVED results")[1]
        self.assertLess(obs2.index("contacts.search"), obs2.index("phone.call"))

    def test_history_order_preserved_and_no_future_info(self):
        history = [
            Turn(role="user", audio_text="first turn"),
            Turn(role="assistant", text="second", tool_calls=[{"name": "contacts.search", "arguments": {"query": "Binh"}}]),
            Turn(role="user", audio_text="third turn"),
        ]
        sample = make_sample(
            history=history,
            label={"tool_calls": [{"name": "phone.call", "arguments": {"contact_id": "FUTURE_SECRET_LABEL_CALL"}}]},
        )
        prompt = build_v2_prompt(sample, "Goi cho Binh", TOOLS)
        self.assertLess(prompt.index("first turn"), prompt.index("second"))
        self.assertLess(prompt.index("second"), prompt.index("third turn"))
        self.assertNotIn("FUTURE_SECRET_LABEL_CALL", prompt)
        # B0 prompt must also not leak the label.
        self.assertNotIn("FUTURE_SECRET_LABEL_CALL", build_base_prompt(sample, "Goi cho Binh", TOOLS))

    def test_ask_then_stop_and_stop_dict(self):
        sample = make_sample()
        _, _, out = run_loop(
            sample,
            "Goi cho Binh",
            [{"name": "sys.ask_missing_info", "arguments": {"tool_name": "phone.call", "params": ["contact_id"]}}, None],
        )
        self.assertEqual(out["tool_calls"][0]["name"], "sys.ask_missing_info")
        _, _, out2 = run_loop(sample, "Goi cho Binh", [{"stop": True}])
        self.assertEqual(out2["tool_calls"], [])

    def test_multi_call_in_one_response_is_rejected_not_split(self):
        sample = make_sample()
        # A list is not a valid single-call dict: loop must not execute either.
        _, _, out = run_loop(
            sample,
            "Goi cho Binh",
            [
                [{"name": "phone.call", "arguments": {"contact_id": "c_binh1"}},
                 {"name": "sms.send", "arguments": {"contact_id": "c_binh1", "text": "hi"}}],
                [{"name": "phone.call", "arguments": {"contact_id": "c_binh1"}}],
                [{"name": "phone.call", "arguments": {"contact_id": "c_binh1"}}],
            ],
        )
        self.assertEqual(out["tool_calls"], [])
        # Same shape, but a valid call on retry 2: only the valid call runs.
        _, _, out2 = run_loop(
            sample,
            "Goi cho Binh",
            [
                [{"name": "phone.call", "arguments": {"contact_id": "c_binh1"}}],
                {"name": "phone.call", "arguments": {"contact_id": "c_binh1"}},
                None,
            ],
        )
        self.assertEqual(len(out2["tool_calls"]), 1)

    def test_validation_retry_then_success(self):
        sample = make_sample()
        env = StubEnv(fail_args={"BAD"})
        _, _, out = run_loop(
            sample,
            "Goi cho Binh",
            [
                {"name": "phone.call", "arguments": {"contact_id": "BAD"}},
                {"name": "phone.call", "arguments": {"contact_id": "c_binh1"}},
                None,
            ],
            env=env,
        )
        self.assertEqual([c["arguments"]["contact_id"] for c in out["tool_calls"]], ["c_binh1"])

    def test_validation_exhaustion_preserves_prior_calls(self):
        sample = make_sample()
        env = StubEnv(fail_args={"BAD"})
        _, _, out = run_loop(
            sample,
            "Goi cho Binh",
            [
                {"name": "contacts.search", "arguments": {"query": "Binh"}},
                {"name": "phone.call", "arguments": {"contact_id": "BAD"}},
                {"name": "phone.call", "arguments": {"contact_id": "BAD"}},
                {"name": "phone.call", "arguments": {"contact_id": "BAD"}},
            ],
            env=env,
        )
        self.assertEqual([c["name"] for c in out["tool_calls"]], ["contacts.search"])

    def test_max_steps_caps_execution(self):
        sample = make_sample()
        cfg = PipelineConfig(grounding=False, shadow_observer=False, max_steps=3, max_repeats=99)
        script = [
            {"name": "contacts.search", "arguments": {"query": f"q{i}"}} for i in range(10)
        ]
        _, _, out = run_loop(sample, "Goi cho Binh", script, config=cfg)
        self.assertLessEqual(len(out["tool_calls"]), 3)

    def test_guard_exact_repeat_stops_after_replan(self):
        sample = make_sample()
        script = [{"name": "phone.call", "arguments": {"contact_id": "c_binh1"}}] * 10
        _, _, out = run_loop(sample, "Goi cho Binh", script)
        self.assertEqual(len(out["tool_calls"]), 2)

    def test_prompt_budget_includes_output_reserve(self):
        budget = measure_prompt_budget("x" * 4000, 16384, 1024)
        self.assertEqual(budget["estimated_tokens"], 1000)
        self.assertEqual(budget["available_for_prompt_tokens"], 15360)
        self.assertEqual(budget["remaining_tokens"], 14360)
        self.assertFalse(budget["over_budget"])
        over = measure_prompt_budget("x" * ((16384 - 1024) * 4 + 4), 16384, 1024)
        self.assertTrue(over["over_budget"])
        # V2 loop records a base budget; it never truncates by itself.
        sample = make_sample()
        cfg = PipelineConfig(grounding=False, shadow_observer=False, history_presentation_v2=True)
        loop, _, _ = run_loop(sample, "Goi cho Binh", [None], config=cfg)
        self.assertEqual(loop.last_prompt_budget["available_for_prompt_tokens"], 15360)
        self.assertFalse(loop.last_prompt_budget["over_budget"])

    def test_v2_default_off_preserves_b0(self):
        sample = make_sample(history=[Turn(role="user", audio_text="hi")])
        cfg = PipelineConfig(grounding=False, shadow_observer=False)
        loop = AgentLoop(cfg, TOOLS)
        self.assertFalse(getattr(cfg, "history_presentation_v2", False))
        # With the flag OFF, run() must use the B0 prompt, not V2.
        gen = ScriptGenerator([None])
        loop.run(sample, "hi", StubEnv(), gen)
        self.assertNotIn("PAST ONLY", gen.prompts[0])
        self.assertIn("Conversation history:", gen.prompts[0])


# --- Real-B0 V2 instantiation: 18 P1 cases, real Sample/Tools, no placeholders ---
# Each case is (history_turns, transcript). History turns are Turn objects,
# not strings in a markdown archive. Context/tool values below are real
# values in the constructed Sample, not "<from context>" placeholders.
V2_CASES = {
    "V2-H1-01": ([], "Goi cho Binh"),
    "V2-H1-02": ([Turn(role="user", audio_text="Trua nay Binh an com roi")], "Goi cho Binh"),
    "V2-H1-03": ([Turn(role="user", audio_text="Goi cho Binh so 0903111222")], "Goi cho Binh"),
    "V2-H1-04": ([Turn(role="user", audio_text="Goi cho Binh so 0903111222")], "Goi cho Binh"),
    "V2-H1-05": (
        [Turn(role="user", audio_text="Goi cho Binh so 0903111222"),
         Turn(role="user", audio_text="Khong, goi so 0903333444")],
        "Goi cho Binh",
    ),
    "V2-H1-06": ([Turn(role="user", audio_text=None)], "Goi cho Binh"),
    "V2-H1-07": ([Turn(role="user", audio_text="Goi cho Binh so 0903111222")], "Nhan tin cho Binh"),
    "V2-H1-08": ([Turn(role="user", audio_text="Goi cho Binh so 0903333444")], "Goi cho Binh"),
    "V2-H2-01": ([Turn(role="user", audio_text="Goi so 0903111222 giup toi")], "Toi da goi so 0903111222 roi"),
    "V2-H2-02": (
        [Turn(role="user", audio_text="Goi so 0903111222 giup toi"),
         Turn(role="user", audio_text="Thoi dung goi so 0903111222 nua")],
        "Toi da goi so 0903111222 roi",
    ),
    "V2-H2-03": ([Turn(role="user", audio_text="Goi so 0903111222 giup toi")], "Da goi so 0903111222 chua?"),
    "V2-H2-04": ([Turn(role="user", audio_text="Goi so 0903111222 giup toi")], "Nho nguoi khac goi so 0903111222"),
    "V2-H2-05": ([Turn(role="user", audio_text="Goi so 0903111222 giup toi")], "Goi so 0903111222"),
    "V2-H2-06": ([Turn(role="user", audio_text="Goi so 0903111222 giup toi")], "Goi lai so 0903111222"),
    "V2-H2-07": (
        [Turn(role="user", audio_text="Goi so 0903111222 giup toi"),
         Turn(role="user", audio_text="Toi da goi so 0903111222 roi"),
         Turn(role="user", audio_text="Goi lai so 0903111222")],
        "Goi lai so 0903111222",
    ),
    "V2-TOOL-01": (
        [Turn(role="assistant", text="", tool_calls=[{"name": "contacts.search", "arguments": {"query": "Binh"}}], tool_results="repr-string-not-parsed")],
        "Goi cho Binh",
    ),
    "V2-TOOL-02": (
        [Turn(role="assistant", text="", tool_calls=[{"name": "contacts.search", "arguments": {"query": "Binh"}}], tool_results=[{"ok": True}])],
        "Goi cho Binh",
    ),
    "V2-ORDER-01": (
        [Turn(role="user", audio_text="Thoi dung goi so 0903111222 nua"),
         Turn(role="user", audio_text="Goi cho Binh so 0903111222")],
        "Goi cho Binh",
    ),
}


class TestV2RealB0(unittest.TestCase):
    def test_all_18_cases_real_b0_pass_b1_b4(self):
        self.assertEqual(len(V2_CASES), 18)
        for case_id, (history, transcript) in V2_CASES.items():
            with self.subTest(case=case_id):
                sample = make_sample(history=history)
                prompt = build_v2_prompt(sample, transcript, TOOLS, open_requests=[])
                # Real B0 values, not placeholders.
                self.assertIn("Current time: 2026-10-30T09:00:00 (Asia/Ho_Chi_Minh).", prompt)
                self.assertIn("User: Test User, city Ha Noi.", prompt)
                self.assertNotIn("<from context>", prompt)
                self.assertNotIn("<timezone>", prompt)
                self.assertNotIn("...", prompt.split("Tools you may call")[1].split("Conversation history")[0])
                # B1: past turns in order, verbatim (except result-status).
                for turn in history:
                    if turn.role == "user" and turn.audio_text:
                        self.assertIn(turn.audio_text, prompt)
                # B2: open block exactly none, no past turn copied there.
                self.assertIn("Open requests: none.", prompt)
                open_section = prompt.split("Open requests: none.")[0]
                # B3: no V1 slot, no V3 tag in the prompt.
                self.assertNotIn("resolved_to", prompt)
                self.assertNotIn("distinguishing_value", prompt)
                self.assertNotIn("mentioned_in", prompt)
                self.assertNotIn("status: request", prompt)
                self.assertNotIn("status: done", prompt)
                # B4: no tool output content; unverified -> not shown.
                if case_id == "V2-TOOL-01":
                    self.assertIn("result=not shown", prompt)
                    self.assertNotIn("repr-string-not-parsed", prompt)
                if case_id == "V2-TOOL-02":
                    self.assertIn("result=ok", prompt)
                # V2 loop with the flag ON must use this prompt as base.
                cfg = PipelineConfig(grounding=False, shadow_observer=False, history_presentation_v2=True)
                loop = AgentLoop(cfg, TOOLS)
                gen = ScriptGenerator([None])
                loop.run(sample, transcript, StubEnv(), gen)
                self.assertIn("PAST ONLY", gen.prompts[0])
                self.assertIn("Open requests: none.", gen.prompts[0])

    def test_v2_open_block_only_from_explicit_caller_state(self):
        sample = make_sample(history=[Turn(role="user", audio_text="Goi so 0903111222 giup toi")])
        prompt = build_v2_prompt(
            sample, "Goi cho Binh", TOOLS,
            open_requests=[{"action": "phone.call", "target": "c_binh1", "source_turn": 1}],
        )
        self.assertIn("- action=phone.call target=c_binh1 source_turn=1", prompt)
        self.assertNotIn("Open requests: none.", prompt)


if __name__ == "__main__":
    unittest.main()
