"""Checkpoint config loader (LifeMate, Phase 2) — stdlib only at import.

One JSON config (see ``checkpoint_config_schema.json``) carries an
``asr`` section and an ``llm`` section. Changing one section never
rewrites the other, and never touches ``lifemate/agent.py``: this
loader only builds the ASR/LLM objects that ``lifemate`` already
provides, through their real constructors:

- ASR: ``lifemate.asr.FasterWhisperASR(checkpoint, device,
  compute_type)``. There is NO transformers ASR class in lifemate.
- LLM: ``lifemate.llm.VLLMGenerator(checkpoint, revision, seed,
  max_tokens)`` or ``lifemate.llm.TransformersGenerator(checkpoint,
  revision, device)``.

Anything the current constructors cannot express is reported as a
GAP (a named constructor / parameter that is missing), never silently
dropped and never hacked around by editing ``lifemate/``. By default
``build_asr`` / ``build_llm`` refuse to build when a GAP is present
(``strict=True``); with ``strict=False`` they still refuse the
unbuildable kinds (transformers ASR, LLM adapter) and return the
object plus the gap list for inspection only.

This module never loads weights itself: the constructors do, lazily,
on the GPU host. Importing this module on CPU is safe. The mock
tests inject fake classes through ``asr_cls`` / ``llm_cls`` so the
swap logic is proven on CPU without any backend.

Error / transcript contract (see README.md for the full contract):
``transcribe_safe`` wraps any object with ``.transcribe(path)`` and
returns one record per sample, in input order, always. A missing
file, an unreadable / non-conforming WAV, a backend exception, or an
empty transcript produces ``status="failed"`` with ``transcript=None``
and an ``error`` string — never an empty string presented as a real
transcript, and never a dropped sample that would shift the order.
"""

from __future__ import annotations

import json
import wave
from pathlib import Path

SCHEMA_VERSION = 1
MAX_CONTEXT_TOKENS = 16384

# What the real loader data looks like (lifemate/loader.py docstring,
# checked on real files with stdlib wave): WAV 16 kHz mono 16-bit.
EXPECTED_SAMPLE_RATE = 16000
EXPECTED_CHANNELS = 1
EXPECTED_SAMPLE_WIDTH = 2  # bytes, i.e. 16-bit


class ConfigError(ValueError):
    """The checkpoint config itself is malformed or unusable."""


class GapError(RuntimeError):
    """The config asks for something no current constructor expresses.

    ``gaps`` names the missing constructor / parameter, so the fix
    request to the owner of ``lifemate/`` (or to the fine-tune
    supplier, for a converted checkpoint) can be exact.
    """

    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("constructor GAP(s): " + "; ".join(self.gaps))


def load_checkpoint_config(path) -> dict:
    """Load and validate one checkpoint config. Returns the dict."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ConfigError("checkpoint config must be a JSON object")
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ConfigError(
            f"schema_version must be {SCHEMA_VERSION}, got {data.get('schema_version')!r}")
    for section in ("asr", "llm"):
        if not isinstance(data.get(section), dict):
            raise ConfigError(f"missing or non-object section: {section!r}")
        if not data[section].get("checkpoint"):
            raise ConfigError(f"section {section!r} needs a non-empty 'checkpoint'")
    asr, llm = data["asr"], data["llm"]
    if asr.get("kind", "faster-whisper") not in ("faster-whisper", "transformers"):
        raise ConfigError(f"unknown asr.kind: {asr.get('kind')!r}")
    if llm.get("kind", "vllm") not in ("vllm", "transformers"):
        raise ConfigError(f"unknown llm.kind: {llm.get('kind')!r}")
    if llm.get("load_kind", "full") not in ("full", "merged", "adapter"):
        raise ConfigError(f"unknown llm.load_kind: {llm.get('load_kind')!r}")
    ctx = llm.get("max_context_tokens", MAX_CONTEXT_TOKENS)
    if not isinstance(ctx, int) or ctx > MAX_CONTEXT_TOKENS or ctx <= 0:
        raise ConfigError(
            f"llm.max_context_tokens must be a positive int <= {MAX_CONTEXT_TOKENS}, got {ctx!r}")
    return data


def _canonical(section: dict) -> str:
    return json.dumps(section, sort_keys=True, ensure_ascii=False)


def swap_report(old_cfg: dict, new_cfg: dict) -> dict:
    """Pure config-layer proof of independent swap.

    Returns which section changed. Swapping ASR must leave the LLM
    section byte-identical (canonically), and vice versa. This
    function does not load anything and does not touch the agent.
    """
    return {
        "asr_changed": _canonical(old_cfg["asr"]) != _canonical(new_cfg["asr"]),
        "llm_changed": _canonical(old_cfg["llm"]) != _canonical(new_cfg["llm"]),
    }


def resolve_asr_kwargs(section: dict):
    """Map an asr section to FasterWhisperASR constructor kwargs.

    Returns ``(kwargs, gaps, warnings)``. ``kwargs`` uses only real
    constructor parameters. Everything else the section declares is
    either honoured by the constructor already (none, beyond these
    three) or listed as a GAP.
    """
    gaps, warnings = [], []
    kind = section.get("kind", "faster-whisper")
    if kind == "transformers":
        gaps.append(
            "lifemate/asr.py has no transformers ASR class: there is no "
            "constructor to pass a transformers ASR checkpoint to "
            "(only FasterWhisperASR + the train-only TranscriptOracle exist)")
    if section.get("language", "vi") != "vi":
        gaps.append(
            "FasterWhisperASR has no language parameter: transcribe() "
            "hardcodes language='vi'; a non-'vi' language cannot be expressed")
    beam = section.get("beam_size", 1)
    if section.get("greedy", True) is False or beam != 1:
        gaps.append(
            "FasterWhisperASR has no beam_size/greedy parameter: "
            "transcribe() hardcodes beam_size=1 (greedy); a beam != 1 "
            "cannot be expressed")
    if section.get("hotwords") or section.get("initial_prompt"):
        gaps.append(
            "FasterWhisperASR has no hotwords/initial_prompt parameter: "
            "transcribe() passes neither to WhisperModel.transcribe; "
            "contextual decoding (P1) cannot be expressed")
    if section.get("revision"):
        gaps.append(
            "FasterWhisperASR has no revision parameter: an HF revision "
            "pin cannot be enforced through this constructor (a local "
            "checkpoint directory sidesteps this; an HF id does not)")
    kwargs = {
        "checkpoint": section["checkpoint"],
        "device": section.get("device", "cuda"),
        "compute_type": section.get("compute_type", "float16"),
    }
    return kwargs, gaps, warnings


def resolve_llm_kwargs(section: dict):
    """Map an llm section to the real LLM constructor kwargs.

    Returns ``(kwargs, gaps, warnings)``. ``load_kind='adapter'`` is
    always a GAP: neither generator takes a base model plus an
    adapter path. ``load_kind='merged'`` loads exactly like 'full'
    (the directory must already contain merged weights).
    """
    gaps, warnings = [], []
    kind = section.get("kind", "vllm")
    checkpoint = section["checkpoint"]
    revision = section.get("revision", "")
    if section.get("load_kind", "full") == "adapter":
        gaps.append(
            "No LLM constructor takes adapter weights: VLLMGenerator and "
            "TransformersGenerator take only (checkpoint, revision, ...). "
            "Missing parameters: base_model + adapter_path (or a merged "
            "checkpoint directory). An adapter-only directory cannot be "
            "loaded by this loader until it is merged or the constructors "
            "gain those parameters")
    for field, what in (("tokenizer_source", "tokenizer"),
                        ("chat_template_source", "chat template")):
        src = section.get(field)
        if src and src != checkpoint:
            gaps.append(
                f"No LLM constructor takes a separate {what} source: both "
                f"generators call AutoTokenizer.from_pretrained(checkpoint) "
                f"and apply the checkpoint's own chat template; "
                f"{field}={src!r} != checkpoint cannot be expressed")
    if section.get("temperature", 0.0) != 0.0:
        gaps.append(
            "No LLM constructor takes a temperature parameter: "
            "VLLMGenerator hardcodes SamplingParams(temperature=0.0) and "
            "TransformersGenerator hardcodes do_sample=False; a "
            "temperature != 0.0 cannot be expressed")
    if section.get("stop"):
        gaps.append(
            "No LLM constructor takes a custom stop-token list: stopping "
            "is the chat template's stop token plus parse_model_output's "
            '{"stop": true} rule only')
    if kind == "vllm":
        if section.get("device"):
            warnings.append(
                "VLLMGenerator has no device parameter: llm.device is "
                "ignored for kind='vllm' (vLLM manages its own device)")
        kwargs = {
            "checkpoint": checkpoint,
            "revision": revision,
            "seed": section.get("seed", 42),
            "max_tokens": section.get("max_tokens", 512),
        }
    else:
        if section.get("seed", 42) != 42:
            warnings.append(
                "TransformersGenerator has no seed parameter: generation "
                "is greedy (do_sample=False), so a seed has no effect "
                "there; the value is recorded, not used")
        if section.get("max_tokens", 512) != 512:
            gaps.append(
                "TransformersGenerator has no max_tokens parameter: "
                "generate() hardcodes max_new_tokens=512; a different "
                "max_tokens cannot be expressed for kind='transformers'")
        kwargs = {
            "checkpoint": checkpoint,
            "revision": revision,
            "device": section.get("device", "cuda"),
        }
    warnings.append(
        "Neither LLM constructor takes max_context_tokens: the 16384 cap "
        "is enforced by this loader's validation and by "
        "PipelineConfig.check_budget, but no generator truncates or "
        "rejects an over-long prompt itself — over-budget prompts fail "
        "inside the backend, not here")
    return kwargs, gaps, warnings


def _default_asr_cls():
    from lifemate.asr import FasterWhisperASR
    return FasterWhisperASR


def _default_llm_cls(kind: str):
    if kind == "vllm":
        from lifemate.llm import VLLMGenerator
        return VLLMGenerator
    from lifemate.llm import TransformersGenerator
    return TransformersGenerator


def build_asr(section: dict, asr_cls=None, strict: bool = True):
    """Build the ASR object for one asr section (or raise GapError).

    With ``strict=False`` a buildable object is still returned when
    gaps are only declarative (e.g. a revision pin), but the gaps are
    attached to the object as ``_checkpoint_gaps`` for inspection.
    Unbuildable kinds always raise.
    """
    kwargs, gaps, warnings = resolve_asr_kwargs(section)
    if section.get("kind", "faster-whisper") == "transformers":
        raise GapError(gaps)
    if gaps and strict:
        raise GapError(gaps)
    cls = asr_cls or _default_asr_cls()
    obj = cls(**kwargs)
    obj._checkpoint_gaps = gaps
    obj._checkpoint_warnings = warnings
    return obj


def build_llm(section: dict, llm_cls=None, strict: bool = True):
    """Build the LLM object for one llm section (or raise GapError)."""
    kwargs, gaps, warnings = resolve_llm_kwargs(section)
    if section.get("load_kind", "full") == "adapter":
        raise GapError(gaps)
    if gaps and strict:
        raise GapError(gaps)
    cls = llm_cls or _default_llm_cls(section.get("kind", "vllm"))
    obj = cls(**kwargs)
    obj._checkpoint_gaps = gaps
    obj._checkpoint_warnings = warnings
    return obj


def pipeline_overlay(checkpoint_cfg: dict) -> dict:
    """Map a checkpoint config onto PipelineConfig field names.

    Only fields that PipelineConfig actually has are returned, so a
    future caller (outside this directory — NOT agent.py) can apply
    the overlay without editing the agent or the loop. Parameter
    budgets are deliberately NOT overlaid here: PipelineConfig's
    total_params_b / llm_params_b are declared floats, not artifact
    measurements, and preflight.py is the authority on whether a
    checkpoint's real parameters fit the budget.
    Returns ``(overlay, gaps, warnings)``.
    """
    asr, llm = checkpoint_cfg["asr"], checkpoint_cfg["llm"]
    _, asr_gaps, asr_warnings = resolve_asr_kwargs(asr)
    _, llm_gaps, llm_warnings = resolve_llm_kwargs(llm)
    overlay = {
        "asr_checkpoint": asr["checkpoint"],
        "asr_backend": asr.get("kind", "faster-whisper"),
        "asr_language": asr.get("language", "vi"),
        "asr_greedy": asr.get("greedy", True),
        "llm_checkpoint": llm["checkpoint"],
        "llm_revision": llm.get("revision", ""),
        "llm_backend": llm.get("kind", "vllm"),
        "llm_max_context_tokens": llm.get("max_context_tokens", MAX_CONTEXT_TOKENS),
        "llm_temperature": llm.get("temperature", 0.0),
        "llm_seed": llm.get("seed", 42),
    }
    return overlay, asr_gaps + llm_gaps, asr_warnings + llm_warnings


def _wav_format(path: Path):
    """Stdlib WAV header check. Returns (format_dict, error_or_None)."""
    try:
        with wave.open(str(path), "rb") as wav:
            info = {
                "sample_rate": wav.getframerate(),
                "channels": wav.getnchannels(),
                "sample_width_bytes": wav.getsampwidth(),
                "n_frames": wav.getnframes(),
            }
    except FileNotFoundError:
        return None, "missing_audio"
    except Exception as exc:  # not a WAV, truncated header, unreadable
        return None, f"unreadable_audio: {type(exc).__name__}: {exc}"
    if (info["sample_rate"] != EXPECTED_SAMPLE_RATE
            or info["channels"] != EXPECTED_CHANNELS
            or info["sample_width_bytes"] != EXPECTED_SAMPLE_WIDTH):
        return info, "unsupported_audio_format"
    return info, None


def transcribe_safe(asr, sample_id: str, wav_path, strict_format: bool = True) -> dict:
    """Transcribe one sample through ``asr`` with the error contract.

    Always returns a record (never raises for a per-sample problem),
    in the caller's order — the caller must keep records in input
    order and use :func:`check_order_preserved` to prove it. The
    transcript is returned exactly as the backend gave it (the real
    FasterWhisperASR already strips surrounding whitespace); this
    layer never lowercases, never strips diacritics, never normalises
    digits, and never substitutes an empty string for a failure.
    """
    path = Path(wav_path)
    fmt, fmt_error = _wav_format(path)
    if fmt_error == "missing_audio":
        return {"sample_id": sample_id, "wav_path": str(path), "transcript": None,
                "status": "failed", "error": "missing_audio", "audio_format": None}
    if fmt_error and strict_format:
        return {"sample_id": sample_id, "wav_path": str(path), "transcript": None,
                "status": "failed", "error": fmt_error, "audio_format": fmt}
    try:
        text = asr.transcribe(path)
    except Exception as exc:
        return {"sample_id": sample_id, "wav_path": str(path), "transcript": None,
                "status": "failed",
                "error": f"asr_error: {type(exc).__name__}: {exc}",
                "audio_format": fmt}
    if not isinstance(text, str) or text == "":
        # An empty transcript is NOT a transcript: a silent / failed
        # decode must not enter the prompt as if the user said nothing.
        return {"sample_id": sample_id, "wav_path": str(path), "transcript": None,
                "status": "failed", "error": "empty_transcript_not_a_transcript",
                "audio_format": fmt}
    record = {"sample_id": sample_id, "wav_path": str(path), "transcript": text,
              "status": "ok", "error": None, "audio_format": fmt}
    if fmt_error and not strict_format:
        record["warning"] = fmt_error
    return record


def check_order_preserved(expected_ids, records) -> None:
    """Raise ValueError if ``records`` are not in ``expected_ids`` order.

    This is the tripwire for the swap invariant: a checkpoint swap
    must never reorder, drop, or duplicate samples. A mock that
    shuffles must fail here, not silently change the benchmark.
    """
    got = [r["sample_id"] for r in records]
    if got != list(expected_ids):
        raise ValueError(
            f"sample order changed: expected {list(expected_ids)!r}, got {got!r}")


def check_transcript_untouched(before: str, after: str) -> None:
    """Raise ValueError if an LLM-side step altered the transcript.

    The LLM swap invariant: changing the LLM changes parsed calls,
    never the transcript that was fed to it. Any layer that rewrites
    the transcript must fail here.
    """
    if before != after:
        raise ValueError(
            f"transcript changed by LLM step: {before!r} -> {after!r}")
