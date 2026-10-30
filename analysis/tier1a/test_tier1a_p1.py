"""Phase 1 tests for Tier 1a (LifeMate only) — stdlib unittest, CPU only.

Every test that asserts a gate blocks something also contains an
intentionally-wrong case (missing / duplicate / extra / wrong arm /
provisional / held-out / incomplete model dir / changed input hash)
so the test can only pass if the gate actually catches the error.
No torch, vllm, faster-whisper, GPU, data, or model weight is needed:
ASR checks use mock directories, the completeness gate is pure, and
the score-refusal test stops at the gate before any data is read.

Run from the repo root:
  python3 -m unittest discover -s analysis/tier1a -p "test_tier1a_p1.py" -v
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tier1a_runner as R  # noqa: E402

REPO = Path(__file__).resolve().parent.parent.parent


def fake_trace(sid, mode, run_error=None):
    return {"sample_id": sid, "split": "dev", "arm": mode,
            "tool_calls": [], "state_hash": "hash-" + sid,
            "run_error": run_error}


def make_manifest(ids):
    return {"status": "stratified-frozen", "ids": list(ids),
            "ids_sha256": R.ids_sha256(list(ids))}


def traces_for(ids, mode, drop=(), error=(), wrong_arm=()):
    rows = {}
    for sid in ids:
        if sid in drop:
            continue
        arm = "B-gold" if sid in wrong_arm and mode == "B0" else mode
        rows[sid] = fake_trace(sid, arm, run_error="boom" if sid in error else None)
    return rows


def off_on(ids, identical=True, n_common=None):
    # OFF-vs-ON covers the pilot 20 only, so n_common is 20, not len(ids).
    return {"identical": identical,
            "n_common": len(ids[:20]) if n_common is None else n_common,
            "pilot_ids": list(ids[:20])}


class TestCompletenessGate(unittest.TestCase):
    IDS = [f"dev_{i:03d}" for i in range(25)]

    def gate(self, b0, bgold, off_on_report, pilot=False):
        return R.check_trace_completeness(
            make_manifest(self.IDS),
            {"B0": (b0, []), "B-gold": (bgold, [])},
            off_on_report, pilot=pilot)

    def test_full_pass(self):
        g = self.gate(traces_for(self.IDS, "B0"), traces_for(self.IDS, "B-gold"),
                      off_on(self.IDS))
        self.assertEqual(g["status"], "COMPLETE")

    def test_missing_blocks(self):
        # Intentionally wrong: B0 is missing one manifest id.
        g = self.gate(traces_for(self.IDS, "B0", drop={self.IDS[3]}),
                      traces_for(self.IDS, "B-gold"), off_on(self.IDS))
        self.assertEqual(g["status"], "INCOMPLETE")
        self.assertEqual(g["missing"]["B0"], [self.IDS[3]])

    def test_duplicate_blocks(self):
        # Intentionally wrong: the B0 file contains one id twice.
        g = R.check_trace_completeness(
            make_manifest(self.IDS),
            {"B0": (traces_for(self.IDS, "B0"), [self.IDS[0]]),
             "B-gold": (traces_for(self.IDS, "B-gold"), [])},
            off_on(self.IDS))
        self.assertEqual(g["status"], "INCOMPLETE")
        self.assertIn(self.IDS[0], g["duplicates"]["B0"])

    def test_extra_blocks(self):
        # Intentionally wrong: B-gold contains an id outside the manifest.
        bgold = traces_for(self.IDS, "B-gold")
        bgold["not_in_manifest"] = fake_trace("not_in_manifest", "B-gold")
        g = self.gate(traces_for(self.IDS, "B0"), bgold, off_on(self.IDS))
        self.assertEqual(g["status"], "INCOMPLETE")
        self.assertEqual(g["extra"]["B-gold"], ["not_in_manifest"])

    def test_arm_mismatch_blocks(self):
        # Intentionally wrong: a B0 trace file row claims arm B-gold.
        g = self.gate(traces_for(self.IDS, "B0", wrong_arm={self.IDS[1]}),
                      traces_for(self.IDS, "B-gold"), off_on(self.IDS))
        self.assertEqual(g["status"], "INCOMPLETE")
        self.assertEqual(g["arm_mismatches"]["B0"], [self.IDS[1]])

    def test_arm_id_sets_differ_blocks(self):
        # Intentionally wrong: arms cover different id sets (same size).
        b0 = traces_for(self.IDS, "B0", drop={self.IDS[0]})
        bgold = traces_for(self.IDS, "B-gold", drop={self.IDS[1]})
        g = self.gate(b0, bgold, off_on(self.IDS))
        self.assertEqual(g["status"], "INCOMPLETE")
        self.assertFalse(g["arm_id_sets_equal"])

    def test_run_error_blocks(self):
        # Intentionally wrong: one B0 trace records a run error.
        g = self.gate(traces_for(self.IDS, "B0", error={self.IDS[2]}),
                      traces_for(self.IDS, "B-gold"), off_on(self.IDS))
        self.assertEqual(g["status"], "INCOMPLETE")
        self.assertEqual(g["run_errors"]["B0"], [self.IDS[2]])

    def test_off_on_not_identical_blocks(self):
        # Intentionally wrong: OFF-vs-ON disagrees.
        g = self.gate(traces_for(self.IDS, "B0"), traces_for(self.IDS, "B-gold"),
                      off_on(self.IDS, identical=False))
        self.assertEqual(g["status"], "INCOMPLETE")

    def test_off_on_missing_blocks(self):
        # Intentionally wrong: no OFF-vs-ON report at all.
        g = self.gate(traces_for(self.IDS, "B0"), traces_for(self.IDS, "B-gold"), None)
        self.assertEqual(g["status"], "INCOMPLETE")

    def test_off_on_short_pilot_blocks(self):
        # Intentionally wrong: OFF-vs-ON covers only 19 of the pilot 20.
        g = self.gate(traces_for(self.IDS, "B0"), traces_for(self.IDS, "B-gold"),
                      off_on(self.IDS, n_common=19))
        self.assertEqual(g["status"], "INCOMPLETE")

    def test_pilot_scoring_requires_only_first_20(self):
        pilot = self.IDS[:20]
        g = R.check_trace_completeness(
            make_manifest(self.IDS),
            {"B0": (traces_for(pilot, "B0"), []),
             "B-gold": (traces_for(pilot, "B-gold"), [])},
            off_on(self.IDS), pilot=True)
        self.assertEqual(g["status"], "COMPLETE")
        # Same traces without --pilot must be INCOMPLETE (5 missing).
        g2 = self.gate(traces_for(pilot, "B0"), traces_for(pilot, "B-gold"),
                       off_on(self.IDS), pilot=False)
        self.assertEqual(g2["status"], "INCOMPLETE")
        self.assertEqual(len(g2["missing"]["B0"]), 5)

    def test_load_traces_file_detects_duplicates(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "traces_B0.jsonl"
            path.write_text(
                json.dumps(fake_trace("a", "B0")) + "\n"
                + json.dumps(fake_trace("a", "B0")) + "\n",
                encoding="utf-8")
            rows, duplicates = R.load_traces_file(path)
            self.assertEqual(duplicates, ["a"])
            self.assertEqual(list(rows), ["a"])


class TestManifestGate(unittest.TestCase):
    def test_provisional_manifest_rejected(self):
        # The schema example (status schema-example-only) must never run.
        with self.assertRaises(SystemExit):
            R.validate_manifest(REPO / "analysis" / "tier1a" / "manifest_schema.json", REPO)

    def test_edited_manifest_rejected(self):
        # Intentionally wrong: ids_sha256 does not recompute after an edit.
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "m.json"
            doc = make_manifest(["dev_001", "dev_002"])
            doc["ids"].append("dev_003")  # edited after freezing
            path.write_text(json.dumps(doc), encoding="utf-8")
            with self.assertRaises(SystemExit):
                R.validate_manifest(path, REPO)

    def test_heldout_id_rejected(self):
        # Intentionally wrong: a held-out id in an otherwise frozen manifest.
        # This is a rejection proof only; held-out ids are never selected.
        split = json.loads((REPO / "lifemate" / "splits" / "train_dev_heldout.json")
                           .read_text(encoding="utf-8"))
        held = sorted(k for k, v in split.items() if v == "heldout")
        dev = sorted(k for k, v in split.items() if v == "dev")
        self.assertTrue(held and dev)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "m.json"
            doc = make_manifest([dev[0], held[0]])
            path.write_text(json.dumps(doc), encoding="utf-8")
            with self.assertRaises((SystemExit, AssertionError)):
                R.validate_manifest(path, REPO)


class TestAsrModelCheck(unittest.TestCase):
    def _dir(self, td, name, files):
        path = Path(td) / name
        path.mkdir(parents=True)
        for f in files:
            (path / f).write_text("mock", encoding="utf-8")
        return path

    def test_ct2_good_passes(self):
        with tempfile.TemporaryDirectory() as td:
            d = self._dir(td, "ct2", ["model.bin", "config.json", "tokenizer.json"])
            rep = R.check_ct2_dir(d)
            self.assertTrue(rep["model_bin"] and rep["config_json"])

    def test_ct2_missing_model_bin_blocks(self):
        # Intentionally wrong: a transformers-format dir passed as CT2.
        with tempfile.TemporaryDirectory() as td:
            d = self._dir(td, "ct2", ["config.json", "tokenizer.json"])
            with self.assertRaises(SystemExit) as cm:
                R.check_ct2_dir(d)
            self.assertIn("model.bin", str(cm.exception))

    def test_ct2_missing_tokenizer_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            d = self._dir(td, "ct2", ["model.bin", "config.json"])
            with self.assertRaises(SystemExit):
                R.check_ct2_dir(d)

    def test_transformers_good_passes(self):
        with tempfile.TemporaryDirectory() as td:
            d = self._dir(td, "tf", ["config.json", "preprocessor_config.json",
                                     "tokenizer_config.json", "model.safetensors"])
            rep = R.check_transformers_dir(d)
            self.assertEqual(rep["weights_file"], "model.safetensors")

    def test_transformers_missing_weights_blocks(self):
        # Intentionally wrong: config + tokenizer but no weights.
        with tempfile.TemporaryDirectory() as td:
            d = self._dir(td, "tf", ["config.json", "preprocessor_config.json",
                                     "tokenizer_config.json"])
            with self.assertRaises(SystemExit) as cm:
                R.check_transformers_dir(d)
            self.assertIn("weights", str(cm.exception))

    def test_pinned_vinai_faster_whisper_blocked_before_download(self):
        # No model dir, no Hub listing is attempted for the pinned id:
        # the check must fail immediately with the conversion path.
        with self.assertRaises(SystemExit) as cm:
            R.check_asr_model("faster-whisper", "vinai/PhoWhisper-small", None)
        self.assertIn("cannot load", str(cm.exception))
        self.assertIn("ct2-transformers-converter", str(cm.exception))

    def test_unknown_backend_blocked(self):
        with self.assertRaises(SystemExit):
            R.check_asr_model("openai-whisper", "vinai/PhoWhisper-small", None)


class TestResume(unittest.TestCase):
    def test_skips_unchanged(self):
        ids = ["a", "b", "c"]
        cur = {s: f"h-{s}" for s in ids}
        existing = {s: fake_trace(s, "B0") for s in ids}
        plan = R.resume_plan(ids, existing, dict(cur), dict(cur))
        self.assertEqual(plan["skip"], ids)
        self.assertEqual(plan["rerun"], [])

    def test_reruns_changed_input_hash(self):
        # Intentionally wrong reuse: stored hash differs from recomputed.
        ids = ["a", "b"]
        existing = {s: fake_trace(s, "B0") for s in ids}
        plan = R.resume_plan(ids, existing, {"a": "old", "b": "h-b"},
                             {"a": "new", "b": "h-b"})
        self.assertEqual(plan["skip"], ["b"])
        self.assertEqual(plan["rerun"], ["a"])

    def test_reruns_errored_trace(self):
        # Intentionally wrong reuse: trace exists but records a run error.
        ids = ["a"]
        existing = {"a": fake_trace("a", "B0", run_error="boom")}
        plan = R.resume_plan(ids, existing, {"a": "h-a"}, {"a": "h-a"})
        self.assertEqual(plan["rerun"], ["a"])

    def test_missing_sidecar_reruns_all(self):
        # No stored hashes (sidecar missing) => nothing is reused.
        ids = ["a", "b"]
        existing = {s: fake_trace(s, "B0") for s in ids}
        plan = R.resume_plan(ids, existing, {}, {s: f"h-{s}" for s in ids})
        self.assertEqual(plan["skip"], [])
        self.assertEqual(plan["rerun"], ids)

    def test_input_hash_changes_with_transcript(self):
        base = dict(sample_id="a", mode="B0", wav_sha="w", transcript_current="x",
                    history_transcripts=[], config_sha256="c",
                    asr_checkpoint="vinai/PhoWhisper-small",
                    asr_backend="transformers", llm_checkpoint="Qwen/Qwen3-4B-Instruct-2507",
                    llm_revision="cdbee75")
        h1 = R.input_hash_for_sample(**base)
        h2 = R.input_hash_for_sample(**{**base, "transcript_current": "y"})
        self.assertNotEqual(h1, h2)
        self.assertEqual(h1, R.input_hash_for_sample(**base))


class TestScoreRefusalAndSeparation(unittest.TestCase):
    def test_score_refuses_partial_without_any_total(self):
        # A B0 file missing one manifest id + no OFF-vs-ON report:
        # score must exit 2, write completeness_gate.json INCOMPLETE,
        # and must NOT write score_report.json.
        split = json.loads((REPO / "lifemate" / "splits" / "train_dev_heldout.json")
                           .read_text(encoding="utf-8"))
        dev = sorted(k for k, v in split.items() if v == "dev")[:3]
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            manifest = root / "m.json"
            manifest.write_text(json.dumps(make_manifest(dev)), encoding="utf-8")
            traces = root / "traces"
            traces.mkdir()
            (traces / "traces_B0.jsonl").write_text(
                "".join(json.dumps(fake_trace(s, "B0")) + "\n" for s in dev[:2]),
                encoding="utf-8")
            (traces / "traces_B-gold.jsonl").write_text(
                "".join(json.dumps(fake_trace(s, "B-gold")) + "\n" for s in dev),
                encoding="utf-8")
            out = root / "out"
            args = argparse.Namespace(
                source_tree=str(REPO), traces=str(traces), data=str(root),
                benchmark=str(manifest), out=str(out), pilot=False, off_on=None)
            rc = R.cmd_score(args)
            self.assertEqual(rc, 2)
            self.assertFalse((out / "score_report.json").exists())
            gate = json.loads((out / "completeness_gate.json").read_text(encoding="utf-8"))
            self.assertEqual(gate["status"], "INCOMPLETE")
            self.assertEqual(gate["missing"]["B0"], [dev[2]])

    def test_run_gold_separation_still_passes(self):
        result = R.check_run_gold_separation()
        self.assertTrue(result["passed"], result)


class TestAsrCacheBeforeLlm(unittest.TestCase):
    def test_asr_casts_features_but_keeps_integer_mask(self):
        try:
            import torch
        except ImportError:
            self.skipTest("torch unavailable")
        layer = torch.nn.Conv1d(2, 2, 1).half()

        class Processor:
            def __call__(self, *args, **kwargs):
                return {"input_features": torch.ones(1, 2, 4),
                        "attention_mask": torch.ones(1, 4, dtype=torch.int64)}
            def get_decoder_prompt_ids(self, **kwargs):
                return []
            def batch_decode(self, ids, **kwargs):
                return ["xin chào"]

        class Model:
            dtype = torch.float16
            def generate(self, input_features, attention_mask, **kwargs):
                self.seen_mask = attention_mask.dtype
                layer(input_features)  # Reproduces the actual convolution dtype failure.
                return torch.ones(1, 2, dtype=torch.int64)

        asr = R.TransformersASR.__new__(R.TransformersASR)
        asr.torch, asr.processor, asr.model, asr.device = torch, Processor(), Model(), "cpu"
        asr._read_wav = lambda path: [0.0]
        with self.assertRaises(RuntimeError):
            layer(torch.ones(1, 2, 4))
        self.assertEqual(asr.transcribe("synthetic.wav"), "xin chào")
        self.assertEqual(asr.model.seen_mask, torch.int64)

    def test_three_sample_pilot_rejects_fourth_trace(self):
        ids = [f"dev_{i}" for i in range(25)]
        with patch.object(R, "PILOT_SIZE", 3):
            modes = {m: (traces_for(ids[:3], m), []) for m in ("B0", "B-gold")}
            report = {"identical": True, "n_common": 3, "pilot_ids": ids[:3]}
            self.assertEqual(R.check_trace_completeness(make_manifest(ids), modes,
                             report, pilot=True)["status"], "COMPLETE")
            modes["B0"][0][ids[3]] = fake_trace(ids[3], "B0")
            self.assertEqual(R.check_trace_completeness(make_manifest(ids), modes,
                             report, pilot=True)["status"], "INCOMPLETE")

    def test_cache_coverage_requires_nonempty_transcripts(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            wav = root / "sample.wav"
            wav.write_bytes(b"synthetic wav bytes")
            cache = R.AsrCache(root / "cache.json", "asr", "", "transformers", 1, "vi")
            self.assertEqual(R.missing_cached_wavs(cache, [wav]), [str(wav)])
            cache.put(R.sha256_file(wav), "", str(wav), 0.0)
            self.assertEqual(R.missing_cached_wavs(cache, [wav]), [str(wav)])
            cache.put(R.sha256_file(wav), "xin chào", str(wav), 0.0)
            self.assertEqual(R.missing_cached_wavs(cache, [wav]), [])
            self.assertEqual(R.missing_cached_wavs(cache, [root / "absent.wav"]),
                             [str(root / "absent.wav")])

    def test_lazy_asr_only_loads_on_cache_miss(self):
        builds = []

        class FakeAsr:
            def transcribe(self, wav):
                return "transcript"

        def factory():
            builds.append(True)
            return FakeAsr()

        asr = R.LazyASR(factory)
        self.assertEqual(builds, [])
        self.assertEqual(asr.transcribe("one.wav"), "transcript")
        self.assertEqual(asr.transcribe("two.wav"), "transcript")
        self.assertEqual(len(builds), 1)


if __name__ == "__main__":
    unittest.main()
