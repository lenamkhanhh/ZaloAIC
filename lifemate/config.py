"""Pipeline configuration — explicit, JSON-serialisable, no hidden defaults.

Two named configs ship in ``configs/``:

- ``baseline.json`` (minimal reference): PhoWhisper-small + Qwen3-4B
  prompt-only, catalog filtered by installed_apps, validator, loop
  guard, observation after every call. No grounding repair, no
  acoustic rescoring, no contextual decoding, no SFT.
- ``recommended.json`` (main config): baseline + typed grounding
    (rule-based, zero extra model parameters) + a selective-read prompt
    policy. Duplicate calls are bounded by the loop guard, not a cache.

Acoustic rescoring, contextual decoding (initial_prompt/hotwords) and
SFT are NOT in either config: they are proposals from the round-3
research drafts, each with a defined experiment (P1/P2), and they enter
the main config only after beating the baseline on train held-out by
the official-style metric. See RUN_LIFEMATE.md §1 and §6.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class PipelineConfig:
    # ASR
    asr_checkpoint: str = "vinai/PhoWhisper-small"
    asr_backend: str = "transformers"  # original PhoWhisper weights; CT2 needs conversion
    asr_language: str = "vi"
    asr_greedy: bool = True
    # LLM
    llm_checkpoint: str = "Qwen/Qwen3-4B-Instruct-2507"
    llm_revision: str = "cdbee75"  # HF commit, card-confirmed 2026-10-27
    llm_backend: str = "vllm"  # or "transformers"
    llm_max_context_tokens: int = 16384
    llm_temperature: float = 0.0
    llm_seed: int = 42
    llm_max_new_tokens: int = 512
    local_files_only: bool = True  # pre-download weights; inference stays offline
    # Agent
    max_steps: int = 12
    max_repeats: int = 2  # a call seen this many times is pre-blocked
    grounding: bool = True  # False in baseline.json
    selective_reads: bool = True
    verification_read_after_write: bool = False
    constrained_decoding: str = "validate-and-retry"  # XGrammar via vLLM when available
    # Budget check (billions of parameters, total — the safe counting rule)
    total_params_b: float = 4.244  # PhoWhisper-small 0.244 + Qwen3-4B 4.0
    llm_params_b: float = 4.0
    # Splits / reproducibility
    split_seed: int = 42
    heldout_frac: float = 0.2

    def check_budget(self) -> None:
        assert self.total_params_b < 6.0, "whole system must be < 6B params"
        assert self.llm_params_b < 5.0, "LifeMate LLM must be < 5B params"
        assert self.llm_max_context_tokens <= 16384, "context must be <= 16,384"
        assert 0 < self.llm_max_new_tokens < self.llm_max_context_tokens

    @classmethod
    def from_json(cls, path: str | Path) -> "PipelineConfig":
        cfg = cls(**json.loads(Path(path).read_text(encoding="utf-8")))
        cfg.check_budget()
        return cfg

    def to_json(self, path: str | Path) -> None:
        self.check_budget()
        Path(path).write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")
