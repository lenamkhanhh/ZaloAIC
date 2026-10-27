"""Regression checks for the executable handoff (no weights or GPU)."""
import json
import os
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from lifemate.agent import AgentLoop, build_base_prompt
from lifemate.config import PipelineConfig
from lifemate.loader import Sample
from lifemate.scoring import tool_f1


class IntegrationFixes(unittest.TestCase):
    def setUp(self):
        self.sample = Sample("x", "train", "x.wav", {"installed_apps": {}}, [])
        self.tools = {"banking.transfer": {
            "name": "banking.transfer", "kind": "write", "description": "Transfer",
            "parameters": {"type": "object", "properties": {
                "amount": {"type": "number"},
                "currency": {"type": "string", "enum": ["VND", "USD"]},
            }, "required": ["amount"]},
        }}

    def test_prompt_contains_optional_types_and_enums(self):
        prompt = build_base_prompt(self.sample, "Transfer", self.tools)
        self.assertIn('"currency"', prompt)
        self.assertIn('"enum"', prompt)
        self.assertIn('"VND"', prompt)
        self.assertIn('"number"', prompt)

    def test_fuzzy_matching_is_order_independent(self):
        call = lambda text: {"name": "t", "arguments": {"q": text}}
        gold = [call("a b c"), call("a b d e")]
        submitted = [call("a b"), call("a c")]
        for prediction in (submitted, list(reversed(submitted))):
            for reference in (gold, list(reversed(gold))):
                self.assertEqual(tool_f1(prediction, reference, {"t": {"q"}}), 1.0)

    def test_heldout_selection_happens_before_limit(self):
        from lifemate.run import select_samples
        samples = [Sample(str(i), "train", "x.wav", {}, []) for i in range(4)]
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2]) as temp:
            path = Path(temp) / "split.json"
            path.write_text(json.dumps({"0": "dev", "1": "heldout", "2": "dev", "3": "heldout"}))
            selected = select_samples(samples, "train", "heldout", path, limit=1)
        self.assertEqual([s.id for s in selected], ["1"])

    def test_subset_rejected_on_public(self):
        from lifemate.run import select_samples
        with self.assertRaises(ValueError):
            select_samples([self.sample], "public_test", "heldout", None)

    def test_grounding_flag_changes_executed_arguments(self):
        class Env:
            def __init__(self): self.calls = []
            def validate(self, name, arguments): return {"ok": isinstance(arguments.get("amount"), (int, float))}
            def call(self, name, arguments):
                self.calls.append({"name": name, "arguments": arguments})
                return {"ok": True}
            def submission_line(self): return {"tool_calls": self.calls}
        outputs = []
        for enabled in (False, True):
            env = Env()
            def generate(prompt, tools):
                if env.calls: return None
                return {"name": "banking.transfer", "arguments": {"amount": "1,5 triệu"}}
            outputs.append(AgentLoop(PipelineConfig(grounding=enabled), self.tools).run(
                self.sample, "Transfer", env, generate)["tool_calls"])
        self.assertEqual(outputs[0], [])
        self.assertEqual(outputs[1][0]["arguments"]["amount"], 1500000)

    def test_asr_factory_honours_transformers(self):
        from lifemate import asr
        with patch.object(asr, "TransformersASR") as backend:
            asr.build_asr(PipelineConfig(asr_backend="transformers"), device="cpu")
            self.assertTrue(backend.called)

    def test_unconverted_ct2_checkpoint_fails_before_loading(self):
        from lifemate.asr import FasterWhisperASR
        with self.assertRaisesRegex(ValueError, "model.bin|convert"):
            FasterWhisperASR("vinai/PhoWhisper-small", device="cpu")

    def test_vllm_context_and_output_budget(self):
        from lifemate.llm import VLLMGenerator, ContextBudgetExceeded
        calls = {}
        class Tokenizer:
            def apply_chat_template(self, *a, **kw): return "rendered"
            def encode(self, *a, **kw): return [0] * 20
        class Engine:
            def __init__(self, **kw): calls.update(kw)
            def generate(self, *a): raise AssertionError("oversize request reached GPU")
        vllm = types.SimpleNamespace(LLM=Engine, SamplingParams=lambda **kw: kw)
        transformers = types.SimpleNamespace(AutoTokenizer=types.SimpleNamespace(
            from_pretrained=lambda *a, **kw: Tokenizer()))
        with patch.dict("sys.modules", {"vllm": vllm, "transformers": transformers}):
            generator = VLLMGenerator("model", "rev", max_context_tokens=32, max_tokens=16, local_files_only=False)
            self.assertEqual(calls["max_model_len"], 32)
            with self.assertRaises(ContextBudgetExceeded): generator("prompt", {})

    def test_infer_selects_subset_without_loading_real_models(self):
        from types import SimpleNamespace
        from lifemate import run
        samples = [Sample("dev", "train", "a.wav", {}, []), Sample("held", "train", "b.wav", {}, [])]
        class Env:
            def __init__(self, root, split, sample_id): self.id = sample_id
            def submission_line(self): return {"id": self.id, "tool_calls": [], "state_hash": "fake"}
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2]) as temp:
            split = Path(temp) / "split.json"
            split.write_text(json.dumps({"dev": "dev", "held": "heldout"}))
            out = Path(temp) / "out.jsonl"
            args = SimpleNamespace(config="unused", data=temp, split="train", subset="heldout",
                                   split_file=split, limit=None, out=out, device="cpu")
            asr = SimpleNamespace(transcribe=lambda p: "request")
            with patch.object(run.PipelineConfig, "from_json", return_value=PipelineConfig()), \
                 patch.object(run, "load_catalog", return_value={"apps": []}), \
                 patch.object(run, "load_split", return_value=samples), \
                 patch.object(run, "catalog_tools_for_sample", return_value={}), \
                 patch.object(run, "ZaicEnv", Env), \
                 patch("lifemate.asr.build_asr", return_value=asr), \
                 patch("lifemate.llm.build_generator", return_value=lambda p, t: None):
                run.cmd_infer(args)
            self.assertEqual([json.loads(line)["id"] for line in out.read_text().splitlines()], ["held"])

    def test_submission_rejects_missing_and_duplicate_ids(self):
        from lifemate.run import _submission_lines
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2]) as temp:
            path = Path(temp) / "sub.jsonl"
            path.write_text('{"id":"x"}\n{"id":"x"}\n')
            with self.assertRaisesRegex(ValueError, "duplicate"):
                _submission_lines(path, ["x"])
            path.write_text('{"id":"x"}\n')
            with self.assertRaisesRegex(ValueError, "subset"):
                _submission_lines(path, ["x", "y"])

    @unittest.skipUnless(os.environ.get("LIFEMATE_DATA"), "set LIFEMATE_DATA")
    def test_real_assignment_selects_exact_308_ids(self):
        from lifemate.loader import load_split
        from lifemate.run import select_samples
        samples = load_split(os.environ["LIFEMATE_DATA"], "train")
        selected = select_samples(samples, "train", "heldout")
        self.assertEqual(len(selected), 308)
        self.assertEqual(len({s.id for s in selected}), 308)


if __name__ == "__main__":
    unittest.main()
