"""LLM backends — lazy imports, greedy decoding, one JSON call per turn.

- ``VLLMGenerator`` (primary): Qwen3-4B-Instruct-2507 via vLLM with
  the model's own chat template. Sampling: temperature 0, seed fixed.
   This runner uses validate-and-retry, not XGrammar token masking.
   Both backends enforce the configured prompt-plus-output context cap.
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
from pathlib import Path


class ContextBudgetExceeded(ValueError):
    """Prompt plus reserved output exceeds the configured context budget."""


def _render(tokenizer, prompt, max_context_tokens, max_tokens):
    messages = [{"role": "user", "content": prompt}]
    text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    size = len(tokenizer.encode(text, add_special_tokens=False))
    if size + max_tokens > max_context_tokens:
        raise ContextBudgetExceeded(
            f"prompt={size} + reserved_output={max_tokens} exceeds context={max_context_tokens}; "
            "reduce the input explicitly (no silent schema/history truncation)"
        )
    return text


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
    def __init__(self, checkpoint: str, revision: str, seed: int = 42, max_tokens: int = 512,
                 max_context_tokens: int = 16384, local_files_only: bool = True):
        try:
            from vllm import LLM, SamplingParams
            from transformers import AutoTokenizer
        except ImportError as exc:
            raise RuntimeError(
                "vLLM/transformers not installed. See RUN_LIFEMATE.md §3 for "
                "the GPU/Kaggle install; the CPU-only dev VM cannot run this backend."
            ) from exc
        self.tokenizer = AutoTokenizer.from_pretrained(checkpoint, revision=revision,
                                                       local_files_only=local_files_only)
        if local_files_only:
            # vLLM's LLM API does not accept local_files_only. Resolve the
            # cached snapshot first, then give it a filesystem path.
            from huggingface_hub import snapshot_download
            model_path = checkpoint if Path(checkpoint).is_dir() else snapshot_download(
                checkpoint, revision=revision, local_files_only=True)
        else:
            model_path = checkpoint
        self.llm = LLM(model=model_path, revision=revision, seed=seed,
                       max_model_len=max_context_tokens)
        self.max_context_tokens = max_context_tokens
        self.max_tokens = max_tokens
        self.params = SamplingParams(temperature=0.0, seed=seed, max_tokens=max_tokens)

    def __call__(self, prompt: str, tools: dict) -> dict | None:
        text = _render(self.tokenizer, prompt, self.max_context_tokens, self.max_tokens)
        out = self.llm.generate([text], self.params)[0].outputs[0].text
        try:
            return parse_model_output(out)
        except ValueError:
            return {"name": "__invalid__", "arguments": {}}


class TransformersGenerator:
    def __init__(self, checkpoint: str, revision: str, device: str = "cuda", seed: int = 42,
                 max_context_tokens: int = 16384, max_tokens: int = 512, local_files_only: bool = True,
                 device_map: str | None = None, max_memory_gib: dict[str, int] | None = None):
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:
            raise RuntimeError("transformers/torch not installed (see RUN_LIFEMATE.md §3).") from exc
        self.torch = torch
        torch.manual_seed(seed)
        self.tokenizer = AutoTokenizer.from_pretrained(checkpoint, revision=revision,
                                                       local_files_only=local_files_only)
        dtype = torch.float16 if device.startswith("cuda") else torch.float32
        placement = {}
        if device_map is not None:
            placement["device_map"] = device_map
            if max_memory_gib is not None:
                placement["max_memory"] = {
                    int(key) if key.isdigit() else key: f"{value}GiB"
                    for key, value in max_memory_gib.items()
                }
        elif max_memory_gib is not None:
            raise ValueError("max_memory_gib requires an explicit device_map")
        self.model = AutoModelForCausalLM.from_pretrained(
            checkpoint, revision=revision, local_files_only=local_files_only, torch_dtype=dtype,
            **placement,
        )
        if device_map is None:
            self.model = self.model.to(device)
        self.model.eval()
        # Accelerate dispatches layers itself; .to() must not collapse a
        # sharded model back onto GPU0. Inputs follow the embedding device.
        self.device = self.model.get_input_embeddings().weight.device if device_map else device
        self.max_context_tokens, self.max_tokens = max_context_tokens, max_tokens

    def __call__(self, prompt: str, tools: dict) -> dict | None:
        text = _render(self.tokenizer, prompt, self.max_context_tokens, self.max_tokens)
        ids = self.tokenizer(text, return_tensors="pt", add_special_tokens=False).to(self.device)
        with self.torch.no_grad():
            out = self.model.generate(**ids, max_new_tokens=self.max_tokens, do_sample=False)
        decoded = self.tokenizer.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True)
        try:
            return parse_model_output(decoded)
        except ValueError:
            return {"name": "__invalid__", "arguments": {}}


def build_generator(config, device: str = "cuda"):
    common = dict(checkpoint=config.llm_checkpoint, revision=config.llm_revision,
                  seed=config.llm_seed, max_context_tokens=config.llm_max_context_tokens,
                  max_tokens=config.llm_max_new_tokens, local_files_only=config.local_files_only)
    if config.llm_temperature != 0:
        raise ValueError("This runner supports deterministic greedy decoding only")
    if config.llm_backend == "vllm":
        return VLLMGenerator(**common)
    if config.llm_backend == "transformers":
        return TransformersGenerator(**common, device=device, device_map=config.llm_device_map,
                                     max_memory_gib=config.llm_max_memory_gib)
    raise ValueError(f"Unknown LLM backend: {config.llm_backend!r}")


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
