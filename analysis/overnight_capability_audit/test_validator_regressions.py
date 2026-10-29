#!/usr/bin/env python3
"""Regression tests for validator Bugs 2 and 3 (Codex audit).

Run with either python:
  python3 analysis/overnight_capability_audit/test_validator_regressions.py
  ~/workspace/zaic-test-venv/bin/python analysis/overnight_capability_audit/test_validator_regressions.py

Conventions (strict, same as test_sft_prototype.py):
  * Sample IDs below are FIXTURES for tests, not validator logic: the
    validator itself contains no sample-ID rules; every failure below
    comes from generic logic (rebuilt-prompt mismatch, manifest
    mismatch, replay outcome, metadata inconsistency, token mismatch).
  * Tests needing the tokenizer use the venv python as a SUBPROCESS
    via the validator's own batch function. If the venv python or the
    tokenizer load fails, those tests report SKIPPED with the reason
    -- they never silently PASS.
  * Tests needing the runtime worktree import it read-only; import
    failure -> SKIP with the reason.
  * Report pass/fail/error/skip separately: unittest prints OK or
    FAILED/SKIPPED counts; this file never folds skips into passes.
  * ok:false end-to-end via real replay is NOT testable from gold
    calls (gold calls all validate; see notes): ok_false is covered
    by classifier unit tests + the 1696 not_done end-to-end case.
    No fabricated e2e case is claimed.
"""
import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, "/home/hatch/workspace/zaic-data/lifemate/extracted/train+public_test/train")

from sft_prototype_builder import (  # noqa: E402
    build_gold_example, replay_gold, sample_tools)
from sft_prototype_validator import (  # noqa: E402
    batch_rendered_tokens, check_token_spans, classify_outcome,
    validate_example)

WORKTREE = Path("/home/hatch/workspace/zaic-branch-a2e832b/lifemate")
VENV_PYTHON = "/home/hatch/workspace/zaic-test-venv/bin/python"
DATA_ROOT = "/home/hatch/workspace/zaic-data/lifemate/extracted/train+public_test"
TRAIN_JSONL = DATA_ROOT + "/train/train.jsonl"
CATALOG_PATH = DATA_ROOT + "/train/train_tools_catalog.json"
MANIFEST_PATH = str(HERE / "inner_split_seed1337_v2.json")
LOCAL_ARTIFACT = str(HERE / "sft_prototype_local.json")
ZAIC_DIR = DATA_ROOT + "/train"
MODEL = "Qwen/Qwen3-4B-Instruct-2507"
REVISION = "cdbee75"


def load_all():
    samples = {}
    with open(TRAIN_JSONL, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                s = json.loads(line)
                samples[s["id"]] = s
    catalog = json.load(open(CATALOG_PATH, encoding="utf-8"))
    fuzzy = {}
    for app in catalog["apps"]:
        for tool in app["tools"]:
            fz = {n for n, spec in tool["parameters"].get("properties", {}).items()
                  if spec.get("x-match") == "fuzzy"}
            if fz:
                fuzzy[tool["name"]] = fz
    manifest = json.load(open(MANIFEST_PATH, encoding="utf-8"))
    return samples, catalog, fuzzy, manifest


SAMPLES, CATALOG, FUZZY, MANIFEST = load_all()


def part_of(sid):
    return MANIFEST["assignment"][sid]


def build_via_builder(sid):
    """Genuine example via builder replay (works when all gold calls
    succeed). Returns (example, sample)."""
    sample = SAMPLES[sid]
    results, state_hash, reason = replay_gold(sample, DATA_ROOT, ZAIC_DIR)
    assert reason is None, f"replay failed for {sid}: {reason}"
    ex = build_gold_example(sample, sample_tools(sample, CATALOG), results,
                            state_hash, "v2", part_of(sid), set())
    assert not ex.get("dropped"), f"builder dropped {sid}: {ex}"
    return ex, sample


def build_direct_1696():
    """train_1696 built DIRECTLY via env.call, bypassing the CLI
    eligibility filter and the builder replay drop (Codex repro)."""
    from zaic_tools import ToolEnv
    sample = SAMPLES["train_1696"]
    env = ToolEnv("train", sample["id"], root=DATA_ROOT)
    results = []
    for call in sample["label"]["tool_calls"]:
        results.append(env.call(call["name"], call.get("arguments") or {}))
    ex = build_gold_example(sample, sample_tools(sample, CATALOG), results,
                            env.get_state_hash(), "v2", part_of("train_1696"),
                            set())
    assert not ex.get("dropped"), f"builder dropped 1696: {ex}"
    return ex, sample


def validate(ex, sample, mode="training", part=None, manifest=MANIFEST,
             catalog=CATALOG, **kw):
    return validate_example(
        ex, sample, FUZZY, DATA_ROOT, ZAIC_DIR,
        manifest=manifest, part=part if part is not None else part_of(sample["id"]),
        mode=mode, runtime_dir=str(WORKTREE), catalog=catalog, **kw)


def assert_failure(testcase, failures, substr):
    testcase.assertTrue(
        any(substr in f for f in failures),
        f"expected failure containing {substr!r} in {failures}")


class TestBug2ForgedBase(unittest.TestCase):
    def test_forged_step0_empty_stop_fails(self):
        ex, sample = build_via_builder("train_0019")
        forged = copy.deepcopy(ex)
        forged["steps"][0]["prompt"] = (
            "FORGED CONTEXT: user requested a different task.")
        rep = validate(forged, sample)
        self.assertEqual(rep["verdict"], "fail")
        assert_failure(self, rep["failures"], "prompt_rebuild_mismatch_runtime")

    def test_genuine_empty_stop_passes(self):
        ex, sample = build_via_builder("train_0019")
        rep = validate(ex, sample)
        self.assertEqual(rep["verdict"], "pass", rep["failures"])
        self.assertTrue(rep["replay_ok"])
        self.assertTrue(rep["hash_match"])

    def test_current_transcript_tamper_fails(self):
        ex, sample = build_via_builder("train_0019")
        tampered = copy.deepcopy(ex)
        prompt = tampered["steps"][0]["prompt"]
        marker = "Current user request (transcript): "
        self.assertIn(marker, prompt)
        head, _, _ = prompt.partition(marker)
        tampered["steps"][0]["prompt"] = head + marker + "FORGED REQUEST"
        rep = validate(tampered, sample)
        self.assertEqual(rep["verdict"], "fail")
        assert_failure(self, rep["failures"], "prompt_rebuild_mismatch_runtime")

    def test_history_turn_tamper_fails(self):
        ex, sample = build_via_builder("train_0063")
        prompt0 = ex["steps"][0]["prompt"]
        self.assertIn("\nuser: ", prompt0, "fixture 0063 must have history user turns")
        tampered = copy.deepcopy(ex)
        p = tampered["steps"][0]["prompt"]
        idx = p.index("\nuser: ")
        end = p.index("\n", idx + 1)
        tampered["steps"][0]["prompt"] = p[:idx] + "\nuser: FORGED HISTORY" + p[end:]
        rep = validate(tampered, sample)
        self.assertEqual(rep["verdict"], "fail")
        assert_failure(self, rep["failures"], "prompt_rebuild_mismatch_runtime")

    def test_catalog_tamper_fails(self):
        ex, sample = build_via_builder("train_0003")
        tampered_catalog = copy.deepcopy(CATALOG)
        # Change one tool description used by this sample's tool list.
        tools = sample_tools(sample, CATALOG)
        first_tool = sorted(tools)[0]
        for app in tampered_catalog["apps"]:
            for tool in app["tools"]:
                if tool["name"] == first_tool:
                    tool["description"] = "TAMPERED DESCRIPTION"
        rep = validate(ex, sample, catalog=tampered_catalog)
        self.assertEqual(rep["verdict"], "fail")
        assert_failure(self, rep["failures"], "prompt_rebuild_mismatch_runtime")

    def test_config_suffix_tamper_fails(self):
        ex, sample = build_via_builder("train_0003")
        suffix = ("Read only to resolve a missing entity or precondition; "
                  "reuse still-valid observations.")
        self.assertIn(suffix, ex["steps"][0]["prompt"])
        tampered = copy.deepcopy(ex)
        tampered["steps"][0]["prompt"] = tampered["steps"][0]["prompt"].replace(
            suffix, "FORGED SUFFIX")
        rep = validate(tampered, sample)
        self.assertEqual(rep["verdict"], "fail")
        assert_failure(self, rep["failures"], "prompt_rebuild_mismatch_runtime")

    def test_sample_id_change_fails(self):
        ex, sample = build_via_builder("train_0003")
        tampered = copy.deepcopy(ex)
        tampered["sample_id"] = "train_0004"
        rep = validate(tampered, sample)
        self.assertEqual(rep["verdict"], "fail")
        assert_failure(self, rep["failures"], "sample_id_mismatch")

    def test_manifest_part_mismatch_fails(self):
        ex, sample = build_via_builder("train_0003")
        # 0003 is inner_train; requesting inner_val must fail.
        self.assertEqual(part_of("train_0003"), "inner_train")
        rep = validate(ex, sample, part="inner_val")
        self.assertEqual(rep["verdict"], "fail")
        assert_failure(self, rep["failures"], "manifest_part_mismatch")

    def test_artifact_manifest_part_tamper_fails(self):
        ex, sample = build_via_builder("train_0003")
        tampered = copy.deepcopy(ex)
        tampered["manifest_part"] = "inner_val"
        rep = validate(tampered, sample)
        self.assertEqual(rep["verdict"], "fail")
        assert_failure(self, rep["failures"], "manifest_part_mismatch")

    def test_future_observation_fails(self):
        ex, sample = build_via_builder("train_0003")
        results, _, reason = replay_gold(sample, DATA_ROOT, ZAIC_DIR)
        self.assertIsNone(reason)
        self.assertGreaterEqual(len(results), 2)
        later_json = json.dumps(results[1], ensure_ascii=False,
                                separators=(",", ":"))
        tampered = copy.deepcopy(ex)
        tampered["steps"][0]["prompt"] += "\n" + later_json
        rep = validate(tampered, sample)
        self.assertEqual(rep["verdict"], "fail")
        assert_failure(self, rep["failures"], "future_observation")

    def test_valid_builder_artifact_passes_token_skipped(self):
        art = json.load(open(LOCAL_ARTIFACT, encoding="utf-8"))
        ex = next(e for e in art["examples"] if e["sample_id"] == "train_0003")
        rep = validate(ex, SAMPLES["train_0003"])
        self.assertEqual(rep["verdict"], "pass", rep["failures"])
        self.assertEqual(rep["token_checks"]["status"], "SKIPPED")
        self.assertIn("legacy", rep["token_checks"]["reason"])


class TestBug3Outcome(unittest.TestCase):
    def test_1696_training_fails_despite_hash_match(self):
        ex, sample = build_direct_1696()
        self.assertEqual(ex["not_done_steps"], [2])
        rep = validate(ex, sample)
        self.assertEqual(rep["verdict"], "fail")
        assert_failure(self, rep["failures"], "not_done:step 2")
        self.assertTrue(rep["replay_ok"])
        self.assertTrue(rep["hash_match"],
                        "hash must still match: it must NOT rescue the verdict")
        self.assertEqual(rep["not_done_steps_replay"], [2])

    def test_outcome_classifier_units(self):
        cases = [
            ({"ok": True, "done": True}, "success"),
            ({"ok": True}, "success"),  # done absent: read case
            ({"ok": True, "done": False}, "not_done"),
            ({"ok": False, "error": "x"}, "ok_false"),
            ({"error": "x"}, "ok_false"),  # ok missing: never a silent pass
            ({"ok": 1}, "ok_false"),  # ok must be exactly True
            ("not-a-dict", "result_not_dict"),
            (None, "result_not_dict"),
        ]
        for result, want in cases:
            status, _ = classify_outcome(result)
            self.assertEqual(status, want, f"result={result!r}")

    def test_1696_forged_empty_not_done_still_fails(self):
        ex, sample = build_direct_1696()
        ex["not_done_steps"] = []
        rep = validate(ex, sample)
        self.assertEqual(rep["verdict"], "fail")
        assert_failure(self, rep["failures"], "not_done:step 2")
        assert_failure(self, rep["failures"], "not_done_steps_mismatch")

    def test_1696_evaluation_passes_with_anomaly(self):
        ex, sample = build_direct_1696()
        rep = validate(ex, sample, mode="evaluation")
        self.assertEqual(rep["verdict"], "pass", rep["failures"])
        self.assertEqual(rep["anomaly"], {"not_done_steps": [2]})
        self.assertIn("SKIPPED", rep["checks"]["eligibility"])

    def test_successful_trajectories_pass(self):
        for sid in ("train_0003", "train_0116", "train_0036"):
            ex, sample = build_via_builder(sid)
            rep = validate(ex, sample)
            self.assertEqual(rep["verdict"], "pass", f"{sid}: {rep['failures']}")
            self.assertEqual(rep["not_done_steps_replay"], [])
            self.assertTrue(rep["replay_ok"])

    def test_manifest_none_skips_membership(self):
        ex, sample = build_via_builder("train_0003")
        rep = validate(ex, sample, manifest=None)
        self.assertEqual(rep["verdict"], "pass", rep["failures"])
        self.assertIn("SKIPPED", rep["checks"]["manifest"])
        self.assertIn("SKIPPED", rep["checks"]["eligibility"])

    def test_cli_training_without_manifest_exits_2(self):
        ex, _ = build_via_builder("train_0003")
        out_path = "/tmp/cli_val_test_output.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({"contract": {"name": "a2e832b-text"}, "examples": [ex]}, f)
        base = [sys.executable, str(HERE / "sft_prototype_validator.py"),
                "--output", out_path, "--train-jsonl", TRAIN_JSONL,
                "--data-root", DATA_ROOT, "--catalog", CATALOG_PATH]
        proc = subprocess.run(base, capture_output=True, text=True, timeout=300)
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("--manifest", proc.stderr)
        proc2 = subprocess.run(
            base + ["--manifest", MANIFEST_PATH, "--part", "inner_train"],
            capture_output=True, text=True, timeout=300)
        self.assertEqual(proc2.returncode, 0, proc2.stdout + proc2.stderr)

    def test_cli_part_mismatch_exits_1(self):
        ex, _ = build_via_builder("train_0003")
        out_path = "/tmp/cli_val_test_output.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({"contract": {"name": "a2e832b-text"}, "examples": [ex]}, f)
        proc = subprocess.run(
            [sys.executable, str(HERE / "sft_prototype_validator.py"),
             "--output", out_path, "--train-jsonl", TRAIN_JSONL,
             "--data-root", DATA_ROOT, "--catalog", CATALOG_PATH,
             "--manifest", MANIFEST_PATH, "--part", "inner_val"],
            capture_output=True, text=True, timeout=300)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("manifest_part_mismatch", proc.stdout + proc.stderr)


class TestTokenChecksIndependent(unittest.TestCase):
    def _rendered_example(self):
        """Genuine 0036 example + validator-rendered token fields.
        SKIPs if the venv tokenizer is unavailable (never passes)."""
        ex, _ = build_via_builder("train_0036")
        try:
            rendered = batch_rendered_tokens(
                VENV_PYTHON, MODEL, REVISION,
                [{"key": (ex["sample_id"], i), "prompt": st["prompt"],
                  "target": st["target"]} for i, st in enumerate(ex["steps"])])
        except Exception as exc:
            self.skipTest(f"tokenizer unavailable: {exc}")
        for i, st in enumerate(ex["steps"]):
            r = rendered[(ex["sample_id"], i)]
            st["rendered_prompt"] = r["rendered"]
            st["rendered_prompt_token_ids"] = r["rendered_ids"]
            st["target_token_ids"] = r["target_ids"]
            st["input_ids"] = r["rendered_ids"] + r["target_ids"] + [r["eos_token_id"]]
            st["labels"] = ([-100] * len(r["rendered_ids"]) + r["target_ids"]
                            + [r["eos_token_id"]])
            st["eos_token_id"] = r["eos_token_id"]
            st["sequence_tokens"] = len(st["input_ids"])
        return ex

    def test_legacy_artifact_token_skipped(self):
        art = json.load(open(LOCAL_ARTIFACT, encoding="utf-8"))
        ex = art["examples"][0]
        rep = check_token_spans(ex, VENV_PYTHON, MODEL, REVISION)
        self.assertEqual(rep["verdict"], "SKIPPED")
        self.assertIn("legacy", rep["reason"])

    def test_rendered_fields_enforced_valid(self):
        ex = self._rendered_example()
        rep = check_token_spans(ex, VENV_PYTHON, MODEL, REVISION)
        self.assertEqual(rep["verdict"], "pass", rep["failures"])
        self.assertGreater(rep["total_trained_tokens"], 0)

    def test_rendered_label_tamper_fails(self):
        ex = self._rendered_example()
        st = ex["steps"][0]
        labels = list(st["labels"])
        trained_pos = next(i for i, lab in enumerate(labels) if lab != -100)
        labels[trained_pos] = -100
        st["labels"] = labels
        rep = check_token_spans(ex, VENV_PYTHON, MODEL, REVISION)
        self.assertEqual(rep["verdict"], "fail")
        assert_failure(self, rep["failures"], "target_masked_or_eos_wrong")

    def test_rendered_prompt_tamper_fails(self):
        ex = self._rendered_example()
        ex["steps"][0]["rendered_prompt"] += " TAMPERED"
        rep = check_token_spans(ex, VENV_PYTHON, MODEL, REVISION)
        self.assertEqual(rep["verdict"], "fail")
        assert_failure(self, rep["failures"], "rendered_prompt_mismatch")

    def test_prompt_trained_fails(self):
        ex = self._rendered_example()
        st = ex["steps"][0]
        labels = list(st["labels"])
        labels[0] = st["rendered_prompt_token_ids"][0]
        st["labels"] = labels
        rep = check_token_spans(ex, VENV_PYTHON, MODEL, REVISION)
        self.assertEqual(rep["verdict"], "fail")
        assert_failure(self, rep["failures"], "prompt_trained_not_masked")

    def test_double_eos_fails(self):
        from sft_prototype_validator import _verify_token_fields
        ex = self._rendered_example()
        st = ex["steps"][0]
        eos = st["eos_token_id"]
        # Consistent fields built from a target that already ends in EOS:
        # the ONLY failure must be double_eos.
        t_ids = st["target_token_ids"] + [eos]
        st["target_token_ids"] = t_ids
        st["input_ids"] = st["rendered_prompt_token_ids"] + t_ids + [eos]
        st["labels"] = ([-100] * len(st["rendered_prompt_token_ids"])
                        + t_ids + [eos])
        st["sequence_tokens"] = len(st["input_ids"])
        rendered_map = {(ex["sample_id"], 0): {
            "rendered": st["rendered_prompt"],
            "rendered_ids": st["rendered_prompt_token_ids"],
            "target_ids": t_ids, "eos_token_id": eos}}
        rep = _verify_token_fields(ex, rendered_map)
        self.assertEqual(rep["verdict"], "fail")
        assert_failure(self, rep["failures"], "double_eos")

    def test_budget_boundary_synthetic(self):
        from sft_prototype_validator import _verify_token_fields
        eos = 151645
        rendered_ids = list(range(1000, 1000 + 16000))  # 16000 + 512 > 16384
        target_ids = [5, 6]
        ex = {"sample_id": "synthetic-budget", "steps": [{
            "prompt": "p", "target": "t",
            "rendered_prompt": "p", "rendered_prompt_token_ids": rendered_ids,
            "target_token_ids": target_ids,
            "input_ids": rendered_ids + target_ids + [eos],
            "labels": [-100] * len(rendered_ids) + target_ids + [eos],
            "eos_token_id": eos,
            "sequence_tokens": len(rendered_ids) + len(target_ids) + 1}]}
        rendered_map = {("synthetic-budget", 0): {
            "rendered": "p", "rendered_ids": rendered_ids,
            "target_ids": target_ids, "eos_token_id": eos}}
        rep = _verify_token_fields(ex, rendered_map)
        self.assertEqual(rep["verdict"], "fail")
        assert_failure(self, rep["failures"], "budget_prompt_plus_reserve")

    def test_validator_does_not_import_builder_token_helpers(self):
        import sft_prototype_validator as vmod
        self.assertFalse(hasattr(vmod, "batch_tokenize"),
                         "validator must not import builder batch_tokenize")
        self.assertFalse(hasattr(vmod, "attach_token_data"),
                         "validator must not import builder attach_token_data")


if __name__ == "__main__":
    unittest.main(verbosity=1)
