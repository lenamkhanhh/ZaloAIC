"""CPU tests for the four-arm harness (stdlib unittest only).

These tests run on CPU, need no data, no GPU, no weights, and prove
plumbing only: arm contract, manifest gates, separation, mock smoke
shape, OFF/ON identity, and score-report shape. They produce NO
model score and must never be quoted as one. A mock score report
here is labelled MOCK ONLY in the report itself.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

from arm_config import build_arms, validate_arms  # noqa: E402
from fourarm_runner import check_separation, cmd_mock_smoke  # noqa: E402
from manifest import validate_manifest  # noqa: E402
from mock_backends import MOCK_SAMPLES  # noqa: E402
from score_fourarm import score_traces  # noqa: E402


class _Args:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class TestArmContract(unittest.TestCase):
    def test_four_arms_differ_only_as_named(self):
        arms = build_arms()
        self.assertEqual(validate_arms(arms, real_mode=False), [])
        # Real mode must refuse the unpinned partner slots.
        errs = validate_arms(arms, real_mode=True)
        self.assertTrue(any("unpinned" in e or "checkpoint" in e for e in errs))

    def test_shared_block_identical(self):
        arms = build_arms()
        shared = {json.dumps(a["shared"], sort_keys=True) for a in arms.values()}
        self.assertEqual(len(shared), 1)

    def test_tampered_arm_fails(self):
        arms = build_arms()
        arms["B"]["llm"] = arms["C"]["llm"]
        self.assertTrue(validate_arms(arms, real_mode=False))


class TestManifestGate(unittest.TestCase):
    def test_mock_manifest_refused_by_real_gate(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            manifest = out / "m.json"
            manifest.write_text(json.dumps(
                {"status": "mock-smoke-only", "ids": MOCK_SAMPLES,
                 "ids_sha256": "x"}), encoding="utf-8")
            # Real gate refuses the mock status (against the real
            # source tree, whose split file exists).
            source_tree = HERE.parent.parent
            with self.assertRaises(SystemExit):
                validate_manifest(manifest, source_tree)

    def test_p2_mapping_baseline_gap_free(self):
        from arm_config import build_arms, to_p2_config
        arms = build_arms()
        _, gaps = to_p2_config(arms["A"])
        self.assertEqual(gaps, [])
        # A partner LLM whose tokenizer differs from its checkpoint
        # must surface GAP L2, not silently map.
        import copy
        partner = {"base": "Partner/LLM", "adapter": None,
                   "merged": "Partner/LLM-merged", "revision": "abc",
                   "tokenizer": "Other/Tokenizer",
                   "template": "model_chat_template",
                   "stop": ["template_stop_token", '{"stop": true}'],
                   "context": 16384,
                   "decoding": {"temperature": 0.0, "seed": 42,
                                "max_tokens": 512},
                   "backend": "vllm"}
        arms2 = build_arms(partner_llm=partner)
        _, gaps = to_p2_config(arms2["C"])
        self.assertTrue(any(g.startswith("L2") for g in gaps))


class TestSeparation(unittest.TestCase):
    def test_run_path_has_no_gold_or_score_access(self):
        report = check_separation()
        self.assertTrue(report["ok"], report["forbidden_hits"])


class TestMockSmokeEndToEnd(unittest.TestCase):
    def test_smoke_traces_score_report_and_off_on(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "smoke"
            self.assertEqual(
                cmd_mock_smoke(_Args(source_tree=".", out=str(out))), 0)
            for arm in ("A", "B", "C", "D"):
                lines = (out / f"traces_{arm}.jsonl").read_text(
                    encoding="utf-8").splitlines()
                self.assertEqual(len(lines), 4)
                for line in lines:
                    trace = json.loads(line)
                    self.assertEqual(trace["mode"], "mock")
                    self.assertIn(trace["sample_id"], MOCK_SAMPLES)
            # OFF/ON via the CLI (mock mode).
            offon_out = Path(td) / "offon"
            proc = subprocess.run(
                [sys.executable, str(HERE / "fourarm_runner.py"),
                 "check-off-on", "--source-tree", ".", "--out", str(offon_out),
                 "--mock"],
                capture_output=True, text=True, cwd=str(HERE))
            self.assertEqual(proc.returncode, 0, proc.stderr)
            rep = json.loads((offon_out / "off_on_report.json").read_text())
            self.assertTrue(rep["identical"])
            # Score via the CLI (mock mode) and check report shape.
            score_out = Path(td) / "score"
            proc = subprocess.run(
                [sys.executable, str(HERE / "score_fourarm.py"),
                 "--traces", str(out), "--out", str(score_out),
                 "--mock", "--mock-fixture",
                 str(out / "mock_gold_fixture.json"),
                 "--off-on-report", str(offon_out / "off_on_report.json")],
                capture_output=True, text=True, cwd=str(HERE))
            self.assertEqual(proc.returncode, 0, proc.stderr)
            report = json.loads((score_out / "score_report.json").read_text())
            self.assertEqual(report["result_kind"], "mock_only")
            self.assertEqual(report["n_paired"], 4)
            self.assertEqual(set(report["per_arm"]), {"A", "B", "C", "D"})
            for arm in ("A", "B", "C", "D"):
                per = report["per_arm"][arm]
                self.assertIn("empty", per["by_label_group"])
                self.assertIn("normal", per["by_label_group"])
                for flag in ("slot_heard_wrong", "wrong_tool",
                             "fabricated_id_time_money", "skipped_read",
                             "extra_call", "early_stop", "late_time"):
                    self.assertIn(flag, per["error_flags"])
            self.assertEqual(len(report["paired_differences"]), 6)
            # Slot error must fire for partner-ASR arms only.
            self.assertEqual(
                report["per_arm"]["A"]["error_flags"]["slot_heard_wrong"]["n"], 0)
            self.assertEqual(
                report["per_arm"]["B"]["error_flags"]["slot_heard_wrong"]["n"], 1)
            self.assertEqual(
                report["per_arm"]["D"]["error_flags"]["slot_heard_wrong"]["n"], 1)
            # Wrong tool: A is wrong only on mock_004 (incomplete:
            # mock_001 empty correct, mock_002 correct, mock_003
            # correct, mock_004 submitted-vs-gold multiset mismatch).
            self.assertEqual(
                report["per_arm"]["A"]["error_flags"]["wrong_tool"]["n"], 1)
            self.assertGreater(
                report["per_arm"]["C"]["error_flags"]["wrong_tool"]["n"],
                report["per_arm"]["A"]["error_flags"]["wrong_tool"]["n"])

    def test_score_refuses_on_failed_off_on(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "smoke"
            self.assertEqual(
                cmd_mock_smoke(_Args(source_tree=".", out=str(out))), 0)
            bad = Path(td) / "bad_offon.json"
            bad.write_text(json.dumps(
                {"identical": False, "differences": [{"field": "tool_calls"}]}),
                encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(HERE / "score_fourarm.py"),
                 "--traces", str(out), "--out", str(Path(td) / "score"),
                 "--mock", "--mock-fixture",
                 str(out / "mock_gold_fixture.json"),
                 "--off-on-report", str(bad)],
                capture_output=True, text=True, cwd=str(HERE))
            self.assertEqual(proc.returncode, 3)


if __name__ == "__main__":
    unittest.main()
