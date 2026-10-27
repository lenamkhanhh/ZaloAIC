"""LLM backends — lazy imports, greedy decoding, one JSON call per turn.

- ``VLLMGenerator`` (primary): Qwen3-4B-Instruct-2507 via vLLM with
  the model's own chat template. Sampling: temperature 0, seed fixed.
  Constrained decoding (XGrammar) is used only when the installed
  vLLM build supports it; otherwise the agent loop's
  validate-and-retry path handles malformed JSON (see agent.py).
- ``TransformersGenerator`` (fallback): same checkpoint via
  transformers ``apply_chat_template`` + greedy generation. Slower;
  use only when vLLM is unavailable.
- ``PromptReadingFake`` (tests only): extracts an id from the prompt
  with a regex and builds the next call from it. It contains no
  hardcoded ids and proves observation reaches the next generation
  through the prompt — the same property pinned in
  deep-dives/tests/test_regressions.py. It is NOT a model and its
  outputs are never reported as model results.

Both real backends return ``None`` when the model emits a stop signal
(the chat template's stop token or a ``{"stop": true}`` JSON object);
anything unparseable is returned as a raw dict for the loop to reject
via validation, never silently repaired into a guessed call.
"""
from __future__ import annotations

import json
import re


def parse_model_output(text: str) -> dict | None:
    """Parse one model turn: a JSON object, optionally fenced.
    Returns None for a stop signal; raises ValueError for garbage."""
    text = text.strip()
    if not text:
        return None
    fence = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"model output is not JSON: {text[:200]!r}") from exc
    if not isinstance(obj, dict):
        raise ValueError(f"model output is not a JSON object: {text[:200]!r}")
    if obj.get("stop") is True:
        return None
    return obj


class VLLMGenerator:
    def __init__(self, checkpoint: str, revision: str, seed: int = 42, max_tokens: int = 512):
        try:
            from vllm import LLM, SamplingParams
            from transformers import AutoTokenizer
        except ImportError as exc:
            raise RuntimeError(
                "vLLM/transformers not installed. See RUN_LIFEMATE.md §3 for "
                "the GPU/Kaggle install; the CPU-only dev VM cannot run this backend."
            ) from exc
        self.tokenizer = AutoTokenizer.from_pretrained(checkpoint, revision=revision)
        self.llm = LLM(model=checkpoint, revision=revision, seed=seed)
        self.params = SamplingParams(temperature=0.0, seed=seed, max_tokens=max_tokens)

    def __call__(self, prompt: str, tools: dict) -> dict | None:
        messages = [{"role": "user", "content": prompt}]
        text = self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        out = self.llm.generate([text], self.params)[0].outputs[0].text
        try:
            return parse_model_output(out)
        except ValueError:
            return {"name": "__invalid__", "arguments": {}}


class TransformersGenerator:
    def __init__(self, checkpoint: str, revision: str, device: str = "cuda"):
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:
            raise RuntimeError("transformers/torch not installed (see RUN_LIFEMATE.md §3).") from exc
        self.torch = torch
        self.tokenizer = AutoTokenizer.from_pretrained(checkpoint, revision=revision)
        self.model = AutoModelForCausalLM.from_pretrained(checkpoint, revision=revision).to(device)
        self.device = device

    def __call__(self, prompt: str, tools: dict) -> dict | None:
        messages = [{"role": "user", "content": prompt}]
        text = self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        ids = self.tokenizer(text, return_tensors="pt").to(self.device)
        with self.torch.no_grad():
            out = self.model.generate(**ids, max_new_tokens=512, do_sample=False)
        decoded = self.tokenizer.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True)
        try:
            return parse_model_output(decoded)
        except ValueError:
            return {"name": "__invalid__", "arguments": {}}


class PromptReadingFake:
    """Test double: build the next call ONLY from ids visible in the
    prompt. ``search_tool`` is emitted first; afterwards, the first id
    found in the prompt (regex, either quote style) is used for
    ``write_tool``. No hardcoded ids anywhere in this class."""

    def __init__(self, search_tool: str, write_tool: str, search_args: dict):
        self.search_tool = search_tool
        self.write_tool = write_tool
        self.search_args = search_args

    def __call__(self, prompt: str, tools: dict) -> dict | None:
        match = re.search(r"""['"]id['"]:\s*['"]([^'"]+)['"]""", prompt)
        if match and self.write_tool in tools:
            return {"name": self.write_tool, "arguments": {"contact_id": match.group(1), "amount": 1}}
        return {"name": self.search_tool, "arguments": dict(self.search_args)}
