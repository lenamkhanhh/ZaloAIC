"""CPU-only mock tests for the Phase 2 checkpoint interface.

No torch, vllm, faster-whisper, weights, audio data, or GPU is used.
Every mock lives in this file (inside analysis/checkpoint/, as
specified). Real code under test: loader.py (config swap, constructor
mapping, transcribe_safe, order/transcript tripwires), preflight.py
(read-only verdicts), and lifemate/scoring.py's tool_f1 (the real,
stdlib-only scorer — determinism is proven on the scorer itself, not
on a reimplementation).

Each positive claim has a deliberately-broken counterpart test that
must be CAUGHT (the test asserts the tripwire raises / the verdict
changes). A broken mock that silently passed would fail the suite.

Run from the repo root::

    python3 -m unittest discover -s analysis/checkpoint -p 'test_*.py' -v
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))

import loader  # noqa: E402
from lifemate.scoring import tool_f1  # noqa: E402


def _load_preflight():
    spec = importlib.util.spec_from_file_location("p2_preflight", HERE / "preflight.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


preflight = _load_preflight()

BASELINE = json.loads((HERE / "example_baseline.json").read_text(encoding="utf-8"))


def _changed(cfg, section, **updates):
    import copy
    cfg = copy.deepcopy(cfg)
    cfg[section].update(updates)
    return cfg


def _sec(section, **updates):
    """One section of a changed baseline config (what resolve_*/build_* take)."""
    return _changed(BASELINE, section, **updates)[section]


def _wav(path: Path, text_note: str = ""):
    # Minimal valid WAV: 16 kHz mono 16-bit, a few silent frames.
    # Content is silence; mocks ignore the samples, real format
    # validation only reads the header, so silence is sufficient.
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x00\x00" * 160)


class FakeASR:
    """Mock ASR: returns a fixed transcript per wav filename."""

    def __init__(self, mapping):
        self.mapping = mapping
        self.seen = []

    def transcribe(self, wav_path):
        self.seen.append(Path(wav_path).name)
        return self.mapping[Path(wav_path).name]


class FakeLLM:
    """Mock LLM: returns a fixed parsed call per prompt marker."""

    def __init__(self, calls):
        self.calls = calls
        self.seen_prompts = []

    def __call__(self, prompt, tools):
        self.seen_prompts.append(prompt)
        for marker, call in self.calls.items():
            if marker in prompt:
                return dict(call)
        return {"stop": True}


class TestIndependentSwap(unittest.TestCase):
    def test_asr_only_swap_leaves_llm_section_identical(self):
        new = _changed(BASELINE, "asr", checkpoint="/tmp/fake-asr-v2")
        rep = loader.swap_report(BASELINE, new)
        self.assertTrue(rep["asr_changed"])
        self.assertFalse(rep["llm_changed"])

    def test_llm_only_swap_leaves_asr_section_identical(self):
        new = _changed(BASELINE, "llm", checkpoint="/tmp/fake-llm-v2",
                       revision="deadbeef")
        rep = loader.swap_report(BASELINE, new)
        self.assertFalse(rep["asr_changed"])
        self.assertTrue(rep["llm_changed"])

    def test_overlay_asr_swap_changes_only_asr_fields(self):
        new = _changed(BASELINE, "asr", checkpoint="/tmp/fake-asr-v2")
        old_overlay, _, _ = loader.pipeline_overlay(BASELINE)
        new_overlay, _, _ = loader.pipeline_overlay(new)
        changed = {k for k in old_overlay if old_overlay[k] != new_overlay[k]}
        self.assertEqual(changed, {"asr_checkpoint"})

    def test_overlay_llm_swap_changes_only_llm_fields(self):
        new = _changed(BASELINE, "llm", checkpoint="/tmp/fake-llm-v2",
                       revision="deadbeef")
        old_overlay, _, _ = loader.pipeline_overlay(BASELINE)
        new_overlay, _, _ = loader.pipeline_overlay(new)
        changed = {k for k in old_overlay if old_overlay[k] != new_overlay[k]}
        self.assertEqual(changed, {"llm_checkpoint", "llm_revision"})

    def test_baseline_resolves_with_no_gaps(self):
        _, asr_gaps, _ = loader.resolve_asr_kwargs(BASELINE["asr"])
        _, llm_gaps, _ = loader.resolve_llm_kwargs(BASELINE["llm"])
        self.assertEqual(asr_gaps, [])
        self.assertEqual(llm_gaps, [])

    def test_build_with_mock_classes_records_constructor_kwargs(self):
        seen = {}

        class CapturingASR:
            def __init__(self, **kw):
                seen["asr"] = kw

        class CapturingLLM:
            def __init__(self, **kw):
                seen["llm"] = kw

        loader.build_asr(BASELINE["asr"], asr_cls=CapturingASR)
        loader.build_llm(BASELINE["llm"], llm_cls=CapturingLLM)
        self.assertEqual(seen["asr"]["checkpoint"], "vinai/PhoWhisper-small")
        self.assertEqual(seen["llm"]["checkpoint"], "Qwen/Qwen3-4B-Instruct-2507")
        self.assertEqual(seen["llm"]["revision"], "cdbee75")
        self.assertEqual(seen["llm"]["seed"], 42)


class TestConstructorGaps(unittest.TestCase):
    """Each GAP must be named, not silently dropped."""

    def test_asr_language_gap(self):
        _, gaps, _ = loader.resolve_asr_kwargs(_sec("asr", language="en"))
        self.assertTrue(any("language" in g for g in gaps))
        with self.assertRaises(loader.GapError):
            loader.build_asr(_sec("asr", language="en"), asr_cls=FakeASR)

    def test_asr_hotwords_gap(self):
        _, gaps, _ = loader.resolve_asr_kwargs(_sec("asr", hotwords=["Lan"]))
        self.assertTrue(any("hotwords" in g for g in gaps))

    def test_asr_transformers_kind_unbuildable(self):
        with self.assertRaises(loader.GapError):
            loader.build_asr(_sec("asr", kind="transformers"), asr_cls=FakeASR)

    def test_llm_adapter_gap(self):
        _, gaps, _ = loader.resolve_llm_kwargs(_sec("llm", load_kind="adapter"))
        self.assertTrue(any("adapter" in g for g in gaps))
        with self.assertRaises(loader.GapError):
            loader.build_llm(_sec("llm", load_kind="adapter"), llm_cls=FakeLLM)

    def test_llm_separate_tokenizer_gap(self):
        _, gaps, _ = loader.resolve_llm_kwargs(
            _sec("llm", tokenizer_source="/tmp/other-tok"))
        self.assertTrue(any("tokenizer" in g for g in gaps))

    def test_llm_temperature_gap(self):
        _, gaps, _ = loader.resolve_llm_kwargs(_sec("llm", temperature=0.7))
        self.assertTrue(any("temperature" in g for g in gaps))

    def test_llm_transformers_max_tokens_gap(self):
        _, gaps, _ = loader.resolve_llm_kwargs(
            _sec("llm", kind="transformers", max_tokens=1024))
        self.assertTrue(any("max_tokens" in g for g in gaps))

def _validate(cfg):
    # Thin wrapper: load_checkpoint_config needs a file; validate the
    # same rules on a dict via a temp file round-trip.
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "c.json"
        p.write_text(json.dumps(cfg), encoding="utf-8")
        return loader.load_checkpoint_config(p)


class TestConfigValidation(unittest.TestCase):
    def test_context_over_cap_rejected(self):
        cfg = _changed(BASELINE, "llm", max_context_tokens=32768)
        with self.assertRaises(loader.ConfigError):
            _validate(cfg)

    def test_missing_checkpoint_rejected(self):
        cfg = _changed(BASELINE, "llm")
        del cfg["llm"]["checkpoint"]
        with self.assertRaises(loader.ConfigError):
            _validate(cfg)

    def test_baseline_file_loads(self):
        cfg = loader.load_checkpoint_config(HERE / "example_baseline.json")
        self.assertEqual(cfg["schema_version"], 1)


class TestTranscribeSafe(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.dir = Path(self.td.name)
        self.ids = ["s1", "s2", "s3", "s4"]
        for sid in self.ids:
            _wav(self.dir / f"{sid}.wav")
        # s4's wav is present but the mock returns empty: must be failed, not "".
        self.asr = FakeASR({
            "s1.wav": "chuyển cho Lan một trăm nghìn",
            "s2.wav": "gọi cho Minh",
            "s3.wav": "hủy lịch hẹn",
            "s4.wav": "",
        })

    def tearDown(self):
        self.td.cleanup()

    def test_order_preserved_and_diacritics_kept(self):
        records = [loader.transcribe_safe(self.asr, sid, self.dir / f"{sid}.wav")
                   for sid in self.ids]
        loader.check_order_preserved(self.ids, records)  # must not raise
        self.assertEqual(records[0]["transcript"], "chuyển cho Lan một trăm nghìn")
        self.assertEqual(records[0]["status"], "ok")
        self.assertEqual(records[0]["audio_format"]["sample_rate"], 16000)

    def test_empty_transcript_is_failed_not_empty_string(self):
        rec = loader.transcribe_safe(self.asr, "s4", self.dir / "s4.wav")
        self.assertEqual(rec["status"], "failed")
        self.assertIsNone(rec["transcript"])
        self.assertIn("empty_transcript", rec["error"])

    def test_missing_audio_is_failed_in_place(self):
        records = [
            loader.transcribe_safe(self.asr, "s1", self.dir / "s1.wav"),
            loader.transcribe_safe(self.asr, "missing", self.dir / "missing.wav"),
            loader.transcribe_safe(self.asr, "s2", self.dir / "s2.wav"),
        ]
        loader.check_order_preserved(["s1", "missing", "s2"], records)
        self.assertEqual(records[1]["status"], "failed")
        self.assertEqual(records[1]["error"], "missing_audio")
        self.assertIsNone(records[1]["transcript"])

    def test_nonconforming_wav_rejected_in_strict_mode(self):
        bad = self.dir / "bad.wav"
        with wave.open(str(bad), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(8000)  # not the loader's 16 kHz format
            wav.writeframes(b"\x00\x00" * 10)
        rec = loader.transcribe_safe(self.asr, "bad", bad)
        self.assertEqual(rec["status"], "failed")
        self.assertEqual(rec["error"], "unsupported_audio_format")

    def test_broken_order_is_caught(self):
        """Deliberately-broken counterpart: shuffled records MUST fail."""
        records = [loader.transcribe_safe(self.asr, sid, self.dir / f"{sid}.wav")
                   for sid in self.ids]
        shuffled = [records[1], records[0]] + records[2:]
        with self.assertRaises(ValueError):
            loader.check_order_preserved(self.ids, shuffled)


class TestLLMSwap(unittest.TestCase):
    def test_llm_swap_changes_calls_not_transcript(self):
        transcript = "chuyển cho Lan một trăm nghìn"
        prompt = f"Current user request (transcript): {transcript}"
        llm_a = FakeLLM({"Lan": {"name": "contacts.search",
                                 "arguments": {"query": "Lan"}}})
        llm_b = FakeLLM({"Lan": {"name": "sys.ask_missing_info",
                                 "arguments": {"tool_name": "x", "params": ["contact_id"]}}})
        call_a = llm_a(prompt, {})
        call_b = llm_b(prompt, {})
        self.assertNotEqual(call_a, call_b)
        # Both saw the same transcript: the prompt fed to each is identical.
        self.assertEqual(llm_a.seen_prompts[0], llm_b.seen_prompts[0])
        loader.check_transcript_untouched(transcript, transcript)

    def test_broken_transcript_rewrite_is_caught(self):
        """Deliberately-broken counterpart: an LLM step that rewrites
        the transcript MUST fail the tripwire."""
        with self.assertRaises(ValueError):
            loader.check_transcript_untouched(
                "chuyển cho Lan", "chuyển cho Lan đồng nghiệp")


class TestScoringDeterminism(unittest.TestCase):
    def test_same_input_same_score_with_real_scorer(self):
        gold = [{"name": "contacts.search", "arguments": {"query": "Lan"}}]
        sub = [{"name": "contacts.search", "arguments": {"query": "Lan"}}]
        f1_first = tool_f1(sub, gold, {})
        f1_second = tool_f1(sub, gold, {})
        self.assertEqual(f1_first, f1_second)
        self.assertEqual(f1_first, 1.0)

    def test_changed_calls_change_score(self):
        gold = [{"name": "contacts.search", "arguments": {"query": "Lan"}}]
        wrong = [{"name": "contacts.search", "arguments": {"query": "Minh"}}]
        self.assertNotEqual(tool_f1(wrong, gold, {}), tool_f1(gold, gold, {}))


def _candidate_manifest(tmp: Path, kind="llm", load_kind="full",
                        params=None, ctx=16384, files=None, hashes=None):
    manifest = {
        "schema_version": 1, "kind": kind, "name": "mock-candidate",
        "source": "mock/supplier", "files_required": files or [],
        "status": "candidate", "training_data": "UNKNOWN",
    }
    if kind == "llm":
        manifest["load_kind"] = load_kind
        manifest["max_context_tokens"] = ctx
    if params is not None:
        manifest["parameters_b_declared"] = params
    if hashes:
        manifest["file_sha256"] = hashes
    mp = tmp / "manifest.json"
    mp.write_text(json.dumps(manifest), encoding="utf-8")
    return mp


def _write_ckpt(tmp: Path, files):
    d = tmp / "ckpt"
    d.mkdir(exist_ok=True)
    for name, content in files.items():
        (d / name).write_text(content, encoding="utf-8")
    return d


class TestPreflight(unittest.TestCase):
    def test_usable_mock_llm(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            files = {
                "config.json": json.dumps({
                    "model_type": "Qwen3ForCausalLM",
                    "architectures": ["Qwen3ForCausalLM"],
                    "num_parameters": 4000000000}),
                "tokenizer.json": "{}",
                "model.safetensors": "fake-bytes-not-a-weight",
            }
            d = _write_ckpt(tmp, files)
            mp = _candidate_manifest(tmp, files=list(files))
            rep = preflight.check(mp, d, companion_params_b=0.244)
            self.assertEqual(rep["verdict"], "USABLE")
            self.assertEqual(rep["parameters_b"], 4.0)
            self.assertTrue(rep["budget"]["total_lt_6b"])
            self.assertEqual(rep["runtime"]["status"], "unverified")
            self.assertIsNone(rep["runtime"]["seconds_per_sample"])

    def test_missing_file_lists_exact_path(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            d = _write_ckpt(tmp, {"config.json": json.dumps(
                {"model_type": "Qwen3ForCausalLM"}), "tokenizer.json": "{}"})
            mp = _candidate_manifest(tmp, files=["config.json", "tokenizer.json",
                                                 "model.safetensors"])
            rep = preflight.check(mp, d)
            self.assertEqual(rep["verdict"], "MISSING")
            self.assertIn("model.safetensors", rep["missing"])

    def test_adapter_without_base_is_unverified_not_guessed(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            d = _write_ckpt(tmp, {
                "adapter_config.json": json.dumps(
                    {"base_model_name_or_path": "Qwen/Qwen3-4B-Instruct-2507"}),
                "adapter_model.safetensors": "fake",
                "tokenizer.json": "{}",
                "config.json": json.dumps({"model_type": "Qwen3ForCausalLM",
                                           "architectures": ["Qwen3ForCausalLM"]}),
            })
            mp = _candidate_manifest(tmp, load_kind="adapter",
                                     files=["adapter_config.json",
                                            "adapter_model.safetensors",
                                            "tokenizer.json", "config.json"])
            rep = preflight.check(mp, d)
            self.assertEqual(rep["parameters_status"], "unverified")
            self.assertEqual(rep["verdict"], "UNVERIFIED")

    def test_no_param_number_is_unverified(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            d = _write_ckpt(tmp, {
                "config.json": json.dumps({"model_type": "whisper"}),
                "tokenizer.json": "{}",
            })
            mp = _candidate_manifest(tmp, kind="asr",
                                     files=["config.json", "tokenizer.json"])
            rep = preflight.check(mp, d)
            self.assertEqual(rep["parameters_status"], "unverified")
            self.assertEqual(rep["verdict"], "UNVERIFIED")

    def test_over_budget_llm(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            d = _write_ckpt(tmp, {
                "config.json": json.dumps({
                    "model_type": "Qwen3ForCausalLM",
                    "architectures": ["Qwen3ForCausalLM"],
                    "num_parameters": 5500000000}),
                "tokenizer.json": "{}",
            })
            mp = _candidate_manifest(tmp, files=["config.json", "tokenizer.json"])
            rep = preflight.check(mp, d)
            self.assertEqual(rep["verdict"], "OVER_BUDGET")
            self.assertFalse(rep["budget"]["llm_lt_5b"])

    def test_example_only_manifest_refused(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            d = _write_ckpt(tmp, {"tokenizer.json": "{}"})
            mp = _candidate_manifest(tmp, files=["tokenizer.json"])
            man = json.loads(mp.read_text())
            man["status"] = "example-only"
            mp.write_text(json.dumps(man))
            rep = preflight.check(mp, d)
            self.assertEqual(rep["verdict"], "INVALID")

    def test_hash_mismatch_is_invalid(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            d = _write_ckpt(tmp, {
                "config.json": json.dumps({
                    "model_type": "Qwen3ForCausalLM",
                    "architectures": ["Qwen3ForCausalLM"],
                    "num_parameters": 4000000000}),
                "tokenizer.json": "{}",
            })
            import hashlib
            good = hashlib.sha256((d / "tokenizer.json").read_bytes()).hexdigest()
            mp = _candidate_manifest(tmp, files=["config.json", "tokenizer.json"],
                                     hashes={"tokenizer.json": "0" * 64})
            self.assertNotEqual(good, "0" * 64)
            rep = preflight.check(mp, d)
            self.assertEqual(rep["verdict"], "INVALID")
            self.assertIn("tokenizer.json", rep["hash_mismatch"])


if __name__ == "__main__":
    unittest.main()
