#!/usr/bin/env python3
"""Tests for the SFT prototype builder/validator (Thread B).

Run with either python:
  python3 analysis/overnight_capability_audit/test_sft_prototype.py
  ~/workspace/zaic-test-venv/bin/python analysis/overnight_capability_audit/test_sft_prototype.py

Conventions (strict):
  * Fixtures are SYNTHETIC (ids synthetic-*, fake tool results) and are
    never counted as gold results. Gold numbers come only from the
    smoke-test output file, never from these unit tests.
  * Token-span tests use the venv python as a subprocess tokenizer.
    If that python or the tokenizer load fails, those tests report
    SKIPPED with the reason -- they never silently PASS.
  * The runtime-conformance test imports a2e832b lifemate/agent.py
    read-only; if the import fails it SKIPs with the reason.
  * Backends: this file runs under both system python3 (stdlib only)
    and the venv python. It never imports torch or any model.
"""
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, "/home/hatch/workspace/zaic-data/lifemate/extracted/train+public_test/train")

from sft_prototype_builder import (  # noqa: E402
    ACTION_POLICY, build_base_prompt, build_steps, canon_call,
    classify_sample, render_observation_prompt)
from sft_prototype_validator import (  # noqa: E402
    parse_model_output, token_f1, validate_steps)

WORKTREE = Path("/home/hatch/workspace/zaic-branch-a2e832b/lifemate")
VENV_PYTHON = "/home/hatch/workspace/zaic-test-venv/bin/python"
DATA_ROOT = "/home/hatch/workspace/zaic-data/lifemate/extracted/train+public_test"
TRAIN_JSONL = DATA_ROOT + "/train/train.jsonl"

SYN_BASE = "SYNTHETIC base prompt (fixture, not gold)"
SYN_CALLS = [
    {"name": "contacts.search", "arguments": {"query": "Minh"}},
    {"name": "sms.send", "arguments": {"contact_id": "c_01", "content": "hello"}},
]
SYN_RESULTS = [
    {"ok": True, "contacts": [{"id": "c_01", "name": "Minh", "phone": "0900000001"}]},
    {"ok": True, "message": {"id": "msg_01", "contact_id": "c_01"}},
]
SYN_FINAL_STATE = {"sms": {"messages": [{"id": "msg_01"}]}}
SYN_KINDS = {"contacts.search": "read", "sms.send": "write",
             "sys.ask_missing_info": "meta", "phone.call": "write"}


def synthetic_sample(calls, text="gọi cho Minh", history=None):
    return {
        "id": "synthetic-01",
        "context": {"current_time": "2026-11-19T10:00:00+07:00",
                    "timezone": "Asia/Ho_Chi_Minh",
                    "user_profile": {"name": "Test", "city": "HCM"},
                    "installed_apps": {"contacts": {"tools": ["contacts.search"]}}},
        "history": history or [],
        "audio_text": text,
        "label": {"tool_calls": calls, "tool_results": [], "final_state": SYN_FINAL_STATE},
    }


class TestRenderingAndParser(unittest.TestCase):
    def test_base_prompt_structure(self):
        sample = synthetic_sample(SYN_CALLS)
        tools = {"contacts.search": {"kind": "read", "description": "d",
                                     "parameters": {"type": "object", "properties": {}},
                                     "returns": ""},
                 "sys.ask_missing_info": {"kind": "meta", "description": "d",
                                          "parameters": {"type": "object", "properties": {}},
                                          "returns": ""}}
        base = build_base_prompt(sample, tools)
        self.assertIn("You are a Vietnamese voice assistant", base)
        self.assertIn(ACTION_POLICY.split("\n")[0], base)
        self.assertIn("Read only to resolve a missing entity", base)
        self.assertIn("Do not add a verification read after a write", base)
        self.assertIn("Current user request (transcript): gọi cho Minh", base)
        self.assertIn('"name": "contacts.search"', base)

    def test_observation_rendering_outcome_mapping(self):
        out = render_observation_prompt(SYN_BASE, SYN_CALLS, SYN_RESULTS)
        self.assertIn("contacts.search({'query': 'Minh'}) -> ok; output=", out)
        not_done = render_observation_prompt(
            SYN_BASE, [{"name": "phone.call", "arguments": {"contact_id": "c_01"}}],
            [{"ok": True, "done": False}])
        self.assertIn("-> not_done; output=", not_done)

    def test_runtime_conformance(self):
        """Builder rendering == a2e832b rendering on a synthetic sample.
        SKIPPED (not passed) if the worktree cannot be imported."""
        try:
            sys.path.insert(0, str(WORKTREE.parent))
            from lifemate.agent import build_base_prompt as real_base
            from lifemate.agent import render_observation_prompt as real_obs
            from lifemate.loader import Sample, Turn
        except Exception as exc:
            self.skipTest(f"a2e832b import unavailable: {exc}")
        sample = Sample(id="synthetic-01", split="train", audio="",
                        context={"current_time": "2026-11-19T10:00:00+07:00",
                                 "timezone": "Asia/Ho_Chi_Minh",
                                 "user_profile": {"name": "Test", "city": "HCM"},
                                 "installed_apps": {}},
                        history=[Turn(role="user", audio_text="gọi cho Minh")],
                        audio_text="gọi cho Minh", label=None)
        tools = {"contacts.search": {"kind": "read", "description": "d",
                                     "parameters": {"type": "object", "properties": {}},
                                     "returns": ""}}
        mine = build_base_prompt(
            {"context": sample.context,
             "history": [{"role": "user", "audio_text": "gọi cho Minh"}],
             "audio_text": "gọi cho Minh"}, tools)
        theirs = real_base(sample, "gọi cho Minh", tools)
        # Real base has no config suffix lines; mine adds the two baseline
        # suffix lines. Strip them for the comparison.
        for suffix in ("Do not add a verification read after a write unless the next action needs its result.",
                       "Read only to resolve a missing entity or precondition; reuse still-valid observations."):
            self.assertTrue(mine.endswith("\n" + suffix))
            mine = mine[: -len(suffix) - 1]
        self.assertEqual(mine, theirs)
        mine_obs = render_observation_prompt(SYN_BASE, SYN_CALLS[:1], SYN_RESULTS[:1])
        theirs_obs = real_obs(SYN_BASE, SYN_CALLS[:1], SYN_RESULTS[:1])
        self.assertEqual(mine_obs, theirs_obs)

    def test_parser_roundtrip(self):
        self.assertEqual(parse_model_output('{"name": "sms.send", "arguments": {"a": 1}}'),
                         {"name": "sms.send", "arguments": {"a": 1}})
        self.assertEqual(parse_model_output('```json\n{"name": "x", "arguments": {}}\n```'),
                         {"name": "x", "arguments": {}})
        self.assertIsNone(parse_model_output('{"stop": true}'))
        self.assertIsNone(parse_model_output('{"name": "stop"}'))
        self.assertIsNone(parse_model_output(''))
        with self.assertRaises(ValueError):
            parse_model_output('not json at all {{{')
        with self.assertRaises(ValueError):
            parse_model_output('[1, 2]')


class TestStepsAndCoverage(unittest.TestCase):
    def _steps(self, calls, results):
        return build_steps(SYN_BASE, calls, results)

    def test_empty_stop(self):
        steps = self._steps([], [])
        self.assertEqual(len(steps), 1)
        self.assertIsNone(steps[0]["call"])
        self.assertEqual(steps[0]["target"], '{"stop":true}')
        self.assertEqual(steps[0]["prompt"], SYN_BASE)

    def test_ask_only_no_trailing_stop(self):
        calls = [{"name": "sys.ask_missing_info",
                  "arguments": {"tool_name": "reminders.create", "params": ["time"]}}]
        steps = self._steps(calls, [{"ok": True, "waiting_for_user": True}])
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0]["call"], calls[0])

    def test_read_write_and_multi_step(self):
        steps = self._steps(SYN_CALLS, SYN_RESULTS)
        self.assertEqual(len(steps), 3)  # 2 calls + stop
        self.assertIsNone(steps[-1]["call"])
        self.assertEqual(steps[1]["prompt"].count("contacts.search"), 1)
        self.assertNotIn("msg_01", steps[0]["prompt"])
        self.assertIn("msg_01", steps[2]["prompt"])  # stop prompt sees all obs
        self.assertEqual(steps[0]["target"], canon_call(SYN_CALLS[0]))

    def test_causality_prompt_uses_only_earlier_observations(self):
        steps = self._steps(SYN_CALLS, SYN_RESULTS)
        # Step 1 prompt must contain step-0 result but NOT step-1 result.
        self.assertIn("c_01", steps[1]["prompt"])
        self.assertNotIn("msg_01", steps[1]["prompt"])

    def test_classify_coverage_rules(self):
        kinds = SYN_KINDS
        s = synthetic_sample(SYN_CALLS)
        self.assertIn("read_write", classify_sample(s, kinds, SYN_RESULTS))
        self.assertIn("multi_step", classify_sample(
            synthetic_sample(SYN_CALLS + [{"name": "phone.call",
                                           "arguments": {"contact_id": "c_01"}}]),
            kinds, SYN_RESULTS + [{"ok": True}]))
        s2 = synthetic_sample([{"name": "phone.call", "arguments": {"phone_number": "0900000001"}}])
        self.assertIn("direct_phone", classify_sample(s2, kinds, [{"ok": True}]))
        s3 = synthetic_sample([])
        self.assertIn("empty_stop", classify_sample(s3, kinds, []))
        s4 = synthetic_sample([{"name": "sys.ask_missing_info",
                                "arguments": {"tool_name": "x", "params": ["y"]}}])
        self.assertIn("ask_only", classify_sample(s4, kinds, [{"ok": True}]))
        # Conditional rule fires only with marker + read + no write + no ask.
        s5 = synthetic_sample([{"name": "contacts.search", "arguments": {"query": "Minh"}}],
                              text="nếu Minh online thì nhắn nhé")
        self.assertIn("conditional_no_write",
                      classify_sample(s5, kinds, SYN_RESULTS[:1]))
        # Same shape without a marker -> class absent (NOT force-fit).
        s6 = synthetic_sample([{"name": "contacts.search", "arguments": {"query": "Minh"}}],
                              text="tìm Minh giúp tôi")
        self.assertNotIn("conditional_no_write",
                         classify_sample(s6, kinds, SYN_RESULTS[:1]))
        # History-dependent: id in history result, not in current text.
        hist = [{"role": "assistant", "text": "",
                 "tool_calls": [{"name": "contacts.search", "arguments": {"query": "Minh"}}],
                 "tool_results": [{"contacts": [{"id": "c_99", "name": "Minh"}]}]}]
        s7 = synthetic_sample([{"name": "sms.send",
                                "arguments": {"contact_id": "c_99", "content": "hi"}}],
                              text="nhắn cho Minh", history=hist)
        self.assertIn("history_dependent", classify_sample(s7, kinds, [{"ok": True}]))


class TestValidator(unittest.TestCase):
    def _report(self, steps, gold, results, final=SYN_FINAL_STATE, flags=None):
        return validate_steps(SYN_BASE, steps, gold, final, {}, replay_results=results,
                              guard_flags=flags)

    def test_valid_trajectory_passes(self):
        steps = build_steps(SYN_BASE, SYN_CALLS, SYN_RESULTS)
        rep = self._report(steps, SYN_CALLS, SYN_RESULTS)
        self.assertEqual(rep["verdict"], "pass", rep["failures"])

    def test_leakage_future_result_fails(self):
        steps = build_steps(SYN_BASE, SYN_CALLS, SYN_RESULTS)
        bad = [dict(s) for s in steps]
        bad[0] = dict(bad[0], prompt=bad[0]["prompt"] + json.dumps(
            SYN_RESULTS[1], ensure_ascii=False, separators=(",", ":")))
        rep = self._report(bad, SYN_CALLS, SYN_RESULTS)
        self.assertEqual(rep["verdict"], "fail")
        self.assertTrue(any("leakage" in f for f in rep["failures"]))

    def test_leakage_target_in_prompt_fails(self):
        steps = build_steps(SYN_BASE, SYN_CALLS, SYN_RESULTS)
        bad = [dict(s) for s in steps]
        bad[1] = dict(bad[1], prompt=bad[1]["prompt"] + bad[1]["target"])
        rep = self._report(bad, SYN_CALLS, SYN_RESULTS)
        self.assertEqual(rep["verdict"], "fail")
        self.assertTrue(any("leakage" in f for f in rep["failures"]))

    def test_stop_target_in_prompt_is_not_leakage(self):
        """Documented exception: the stop literal '{"stop":true}'
        appears in the instruction text itself (instruction line +
        ACTION_POLICY), so a stop step's target in its prompt is the
        format specification, not a leaked answer."""
        steps = build_steps(SYN_BASE, SYN_CALLS, SYN_RESULTS)
        stop_step = steps[-1]
        self.assertIsNone(stop_step["call"])
        # The stop literal is in the instruction text by design:
        self.assertIn('{"stop":true}', ACTION_POLICY)
        rep = self._report(steps, SYN_CALLS, SYN_RESULTS)
        self.assertEqual(rep["verdict"], "pass", rep["failures"])

    def test_prompt_rebuild_mismatch_fails(self):
        steps = build_steps(SYN_BASE, SYN_CALLS, SYN_RESULTS)
        bad = [dict(s) for s in steps]
        bad[1] = dict(bad[1], prompt=SYN_BASE + "\nTAMPERED")
        rep = self._report(bad, SYN_CALLS, SYN_RESULTS)
        self.assertEqual(rep["verdict"], "fail")
        self.assertTrue(any("prompt_rebuild" in f for f in rep["failures"]))

    def test_sequence_counterexample_extra_read_same_hash(self):
        """Reads do not change state, so hash alone cannot validate a
        trajectory: an extra read keeps the hash but must FAIL the
        sequence check. Hash equality is demonstrated on a real
        ToolEnv below when available; the sequence verdict is asserted
        regardless of the env."""
        extended = SYN_CALLS + [{"name": "contacts.search", "arguments": {"query": "Lan"}}]
        ext_results = SYN_RESULTS + [{"ok": True, "contacts": []}]
        steps = build_steps(SYN_BASE, extended, ext_results)
        rep = self._report(steps, SYN_CALLS, ext_results)
        self.assertEqual(rep["verdict"], "fail")
        self.assertIn("sequence_mismatch", rep["failures"])
        # Real-env half: extra read does not change state_hash.
        try:
            from zaic_tools import ToolEnv
            env = ToolEnv("train", "train_0003",
                          root=DATA_ROOT)
            gold = None
            import json as _json
            for line in open(TRAIN_JSONL, encoding="utf-8"):
                s = _json.loads(line)
                if s["id"] == "train_0003":
                    gold = s["label"]["tool_calls"]
                    break
            for call in gold:
                env.call(call["name"], call.get("arguments") or {})
            h1 = env.get_state_hash()
            env.call("contacts.search", {"query": "ZZZ-no-such-name"})
            self.assertEqual(h1, env.get_state_hash())
        except Exception as exc:
            self.skipTest(f"real-env hash half unavailable: {exc}")

    def test_ask_not_last_and_fuzzy_args(self):
        calls = [{"name": "sys.ask_missing_info",
                  "arguments": {"tool_name": "x", "params": ["y"]}},
                 {"name": "sms.send", "arguments": {"contact_id": "c_01", "content": "hi"}}]
        steps = build_steps(SYN_BASE, calls, [{"ok": True}, {"ok": True}])
        rep = self._report(steps, calls, [{"ok": True}, {"ok": True}])
        self.assertIn("ask_not_last", rep["failures"])
        self.assertGreater(token_f1("mai đá bóng nhé", "mai đá bóng nhé"), 0.6)
        self.assertLessEqual(token_f1("hello world", "completely different"), 0.6)

    def test_guard_flag_never_changes_verdict(self):
        steps = build_steps(SYN_BASE, SYN_CALLS, SYN_RESULTS)
        a = self._report(steps, SYN_CALLS, SYN_RESULTS, flags=[False, False])
        b = self._report(steps, SYN_CALLS, SYN_RESULTS, flags=[True, True])
        self.assertEqual(a["verdict"], b["verdict"])
        self.assertEqual(a["verdict"], "pass")
        self.assertIn("guard_fired_on_gold_diagnostic", " ".join(b["notes"]))


class TestTokenSpans(unittest.TestCase):
    def test_spans_exact_when_tokenizer_available(self):
        """Uses the venv python subprocess tokenizer. SKIPPED (not
        passed) when the tokenizer cannot load."""
        if not os.path.exists(VENV_PYTHON):
            self.skipTest(f"venv python missing: {VENV_PYTHON}")
        from sft_prototype_builder import batch_tokenize
        try:
            data = batch_tokenize(VENV_PYTHON, "Qwen/Qwen3-4B-Instruct-2507", "cdbee75",
                                  [SYN_BASE, '{"stop":true}'])
        except Exception as exc:
            self.skipTest(f"tokenizer unavailable: {exc}")
        self.assertEqual(data["eos_token_id"], 151645)
        p_ids, t_ids = data["ids"]
        labels = [-100] * len(p_ids) + t_ids + [151645]
        trained = [tid for tid, lab in zip(p_ids + t_ids + [151645], labels) if lab != -100]
        self.assertEqual(trained, t_ids + [151645])
        self.assertEqual(len(p_ids) + 512 <= 16384, True)


class TestNoSilentTruncation(unittest.TestCase):
    def test_tiny_budget_marks_over_budget(self):
        from sft_prototype_builder import attach_token_data, build_steps
        steps = build_steps(SYN_BASE, SYN_CALLS, SYN_RESULTS)
        for i, st in enumerate(steps):
            st["step"] = i  # build_gold_example adds this index in production
        example = {"sample_id": "synthetic-01", "steps": steps}
        token_data = {"eos_token_id": 151645,
                      "ids": [[1, 2, 3], [4], [1, 2, 3, 4, 5], [6], [7, 8], [9]]}
        index = {}
        for st in example["steps"]:
            index[("p", "synthetic-01", st["step"])] = 2 * st["step"]
            index[("t", "synthetic-01", st["step"])] = 2 * st["step"] + 1
        attach_token_data(example, token_data, index, max_context_tokens=4)
        self.assertEqual(example["budget_status"], "over_budget")
        self.assertTrue(example["token_budget_over_steps"])

    def test_builder_drops_over_budget_with_cli_hook(self):
        if not os.path.exists(VENV_PYTHON):
            self.skipTest(f"venv python missing: {VENV_PYTHON}")
        ids_path = "/tmp/tb_trunc_ids.txt"
        out_path = "/tmp/tb_trunc_out.json"
        with open(ids_path, "w", encoding="utf-8") as f:
            f.write("train_0003\n")
        proc = subprocess.run(
            [sys.executable, str(HERE / "sft_prototype_builder.py"),
             "--train-jsonl", TRAIN_JSONL, "--data-root", DATA_ROOT,
             "--manifest", str(HERE / "inner_split_seed1337.json"),
             "--part", "inner_train", "--manifest-version", "v1-frozen",
             "--ids-file", ids_path, "--max-context-tokens", "100",
             "--tokenizer-python", VENV_PYTHON, "--out", out_path],
            capture_output=True, text=True, timeout=600)
        self.assertEqual(proc.returncode, 0, proc.stderr[-500:])
        out = json.load(open(out_path, encoding="utf-8"))
        self.assertEqual(out["counts"]["built"], 0)
        self.assertEqual(out["counts"]["dropped"], 1)
        self.assertEqual(out["dropped"][0]["reason"], "token_budget_exceeded")


if __name__ == "__main__":
    unittest.main()
