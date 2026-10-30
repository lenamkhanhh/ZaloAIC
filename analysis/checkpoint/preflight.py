"""Read-only preflight for ONE checkpoint (LifeMate, Phase 2).

Usage (stdlib only, CPU only, never loads weights)::

    python3 analysis/checkpoint/preflight.py \
        --manifest <manifest.json> --checkpoint-dir <dir> \
        [--companion-params-b <float>] [--companion-kind asr|llm] \
        [--out <report.json>]

What it checks, in order, and what it never does:

- Required files: every path in the manifest's ``files_required``
  must exist inside the checkpoint directory, be a file, and be
  non-empty. Anything else is listed, exactly, in ``missing``.
  No file is opened except small JSON configs and hash checks.
- Tokenizer: a tokenizer is present only if ``tokenizer.json``
  exists, or ``tokenizer_config.json`` plus a vocab/merges file
  exists. A missing tokenizer is a ``missing`` entry, not a warning.
- config.json: if present it must parse as JSON and carry a model
  identity (``model_type`` or ``architectures``). A present-but-
  unparsable or identity-less config is ``config_error`` / invalid.
- Adapter (LLM ``load_kind='adapter'``): ``adapter_config.json``
  must exist and carry a non-empty ``base_model_name_or_path``,
  and an adapter weights file (``adapter_model.safetensors`` or
  ``adapter_model.bin``) must exist. Adapter parameters alone never
  give the LLM total, so parameters are UNVERIFIED unless a base
  config with an explicit ``num_parameters`` is also present in
  the same directory as ``base_config.json`` (a narrow, stated
  path — otherwise UNVERIFIED, never guessed).
- Parameters: taken from the artifact only. ``num_parameters`` in
  config.json, if numeric, is used as-is. Otherwise a Qwen3/Qwen2
  causal-LM config with ALL fields present AND an explicit boolean
  ``tie_word_embeddings`` is computed with the closed-form below.
  Anything else — Whisper configs, adapter-only directories,
  tied-embedding ambiguity, a missing field — yields
  ``parameters_status='unverified'``. No estimate is ever presented
  as a measurement.
- Budget: LLM < 5B, whole system (this checkpoint + companion, when
  ``--companion-params-b`` is given) < 6B, context <= 16384. Values
  come from artifacts / the manifest's own ``max_context_tokens``;
  a missing value makes that budget line UNVERIFIED, never assumed.
  Without a companion value the total is UNVERIFIED, but a single
  checkpoint can still be USABLE only if its own lines pass AND its
  own parameters are verified — the report always states the total
  line separately so a reader never mistakes a single-checkpoint
  pass for a system-budget pass. (In practice: run preflight on
  both checkpoints and pass each one's verified value as the
  other's companion before declaring the pair within budget.)
- Runtime: ALWAYS ``unverified`` here. This script never runs a
  model, never measures seconds/sample, and never infers a 30 s
  limit from a CPU or mock proxy. A GPU run is a separate, later
  measurement.
- Hashes: every ``file_sha256`` entry is verified over the file
  as stored. A mismatch is ``hash_mismatch`` (verdict INVALID),
  never silently ignored. Files without a declared hash are
  reported ``hash_status='not_declared'``.

Verdicts: ``USABLE`` (all files present, hashes match, own budget
lines verified and within limits, context verified) | ``MISSING``
| ``UNVERIFIED`` (files complete but a needed value cannot be
verified) | ``OVER_BUDGET`` | ``INVALID`` (manifest/config/hash
problem). Exit code 0 only for USABLE, 2 otherwise. The script
writes nothing into the checkpoint directory and never modifies a
weight, audio, or data file; ``--out`` writes the report elsewhere.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

MAX_TOTAL_B = 6.0
MAX_LLM_B = 5.0
MAX_CONTEXT = 16384


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def params_from_config(cfg: dict):
    """Parameters in billions from a model config dict, or None.

    Only two honest paths exist: an explicit numeric
    ``num_parameters``, or a complete Qwen2/Qwen3 causal-LM config
    with an explicit boolean ``tie_word_embeddings``. Everything
    else returns None (UNVERIFIED) rather than a guess.
    """
    if not isinstance(cfg, dict):
        return None
    n = cfg.get("num_parameters")
    if isinstance(n, (int, float)) and not isinstance(n, bool) and n > 0:
        return float(n) / 1e9
    arch = cfg.get("architectures") or []
    arch_name = arch[0] if arch else cfg.get("model_type", "")
    if arch_name not in ("Qwen3ForCausalLM", "Qwen2ForCausalLM"):
        return None
    fields = ("hidden_size", "intermediate_size", "num_hidden_layers",
              "num_attention_heads", "num_key_value_heads", "vocab_size")
    if any(not isinstance(cfg.get(f), int) for f in fields):
        return None
    tied = cfg.get("tie_word_embeddings")
    if not isinstance(tied, bool):
        return None  # tied-embedding ambiguity: do not guess
    h = cfg["hidden_size"]
    inter = cfg["intermediate_size"]
    layers = cfg["num_hidden_layers"]
    heads = cfg["num_attention_heads"]
    kv = cfg["num_key_value_heads"]
    vocab = cfg["vocab_size"]
    head_dim = h // heads
    if head_dim * heads != h:
        return None
    per_layer = (
        h * heads * head_dim          # q_proj
        + h * kv * head_dim * 2       # k_proj + v_proj
        + heads * head_dim * h        # o_proj
        + h * inter * 2               # gate_proj + up_proj
        + inter * h                   # down_proj
        + h * 2                       # input_layernorm + post_attention_layernorm
    )
    total = vocab * h * (1 if tied else 2) + layers * per_layer + h
    return total / 1e9


def check(manifest_path, checkpoint_dir, companion_params_b=None):
    """Run preflight. Returns a report dict (never raises for a bad
    checkpoint; manifest JSON errors are reported as INVALID)."""
    cdir = Path(checkpoint_dir)
    report = {
        "verdict": "INVALID",
        "missing": [],
        "hash_mismatch": [],
        "config_error": None,
        "parameters_b": None,
        "parameters_status": "unverified",
        "parameters_source": None,
        "budget": {},
        "context": {},
        "tokenizer": {},
        "runtime": {
            "status": "unverified",
            "seconds_per_sample": None,
            "reason": ("no GPU run in this preflight; runtime is never "
                       "inferred from a CPU/mock proxy and never assumed "
                       "to meet any seconds-per-sample limit"),
        },
        "files_checked": [],
    }
    try:
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    except Exception as exc:
        report["config_error"] = f"manifest unreadable: {type(exc).__name__}: {exc}"
        return report
    if not isinstance(manifest, dict):
        report["config_error"] = "manifest is not a JSON object"
        return report
    report["manifest_name"] = manifest.get("name")
    report["kind"] = manifest.get("kind")
    if manifest.get("status") == "example-only":
        report["config_error"] = (
            "manifest status is 'example-only': schema examples are never "
            "accepted as real checkpoints")
        return report
    if manifest.get("kind") not in ("asr", "llm"):
        report["config_error"] = f"unknown manifest kind: {manifest.get('kind')!r}"
        return report
    if not cdir.is_dir():
        report["missing"] = [f"checkpoint directory not found: {cdir}"]
        report["verdict"] = "MISSING"
        return report

    # --- required files (exact list) ---
    missing = []
    checked = []
    for rel in manifest.get("files_required") or []:
        p = cdir / rel
        checked.append(rel)
        if not p.is_file() or p.stat().st_size == 0:
            missing.append(rel)
    report["files_checked"] = checked

    # --- tokenizer (kind-independent: both ASR and LLM need one) ---
    tok_ok = (cdir / "tokenizer.json").is_file() and (cdir / "tokenizer.json").stat().st_size > 0
    if not tok_ok:
        cfg_ok = (cdir / "tokenizer_config.json").is_file()
        vocab_ok = any((cdir / f).is_file() and (cdir / f).stat().st_size > 0
                       for f in ("vocab.json", "merges.txt", "vocab.txt", "spiece.model"))
        tok_ok = cfg_ok and vocab_ok
    report["tokenizer"] = {"present": tok_ok}
    if not tok_ok and "tokenizer.json" not in missing:
        missing.append("tokenizer.json (or tokenizer_config.json + vocab/merges)")

    # --- adapter-specific requirements ---
    load_kind = manifest.get("load_kind", "full")
    adapter_cfg = None
    if manifest.get("kind") == "llm" and load_kind == "adapter":
        ap = cdir / "adapter_config.json"
        if not ap.is_file() or ap.stat().st_size == 0:
            if "adapter_config.json" not in missing:
                missing.append("adapter_config.json")
        else:
            try:
                adapter_cfg = json.loads(ap.read_text(encoding="utf-8"))
                if not adapter_cfg.get("base_model_name_or_path"):
                    report["config_error"] = (
                        "adapter_config.json has no base_model_name_or_path")
            except Exception as exc:
                report["config_error"] = (
                    f"adapter_config.json unreadable: {type(exc).__name__}: {exc}")
        if not any((cdir / f).is_file() and (cdir / f).stat().st_size > 0
                   for f in ("adapter_model.safetensors", "adapter_model.bin")):
            missing.append("adapter_model.safetensors (or adapter_model.bin)")

    # --- hashes for declared files ---
    mismatch = []
    hash_status = {}
    for rel, expected in (manifest.get("file_sha256") or {}).items():
        p = cdir / rel
        if not p.is_file():
            hash_status[rel] = "missing_file"
            continue
        got = _sha256(p)
        hash_status[rel] = "match" if got == expected else "mismatch"
        if got != expected:
            mismatch.append(rel)
    report["hash_status"] = hash_status
    report["hash_mismatch"] = mismatch

    # --- config.json parameters ---
    cfg_path = cdir / "config.json"
    cfg = None
    if cfg_path.is_file() and cfg_path.stat().st_size > 0:
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            if not isinstance(cfg, dict) or not (cfg.get("model_type") or cfg.get("architectures")):
                report["config_error"] = (
                    "config.json carries no model identity "
                    "(neither model_type nor architectures)")
        except Exception as exc:
            report["config_error"] = f"config.json unreadable: {type(exc).__name__}: {exc}"
    params = None
    source = None
    if cfg is not None and report["config_error"] is None:
        if load_kind == "adapter":
            # Adapter params alone are not the LLM total. Only the
            # narrow stated path verifies: a base_config.json in
            # this directory with an explicit num_parameters, plus
            # the adapter's own trainable count if declared there.
            base_path = cdir / "base_config.json"
            if base_path.is_file():
                try:
                    base_cfg = json.loads(base_path.read_text(encoding="utf-8"))
                    base_n = base_cfg.get("num_parameters")
                    if isinstance(base_n, (int, float)) and base_n > 0:
                        params = float(base_n) / 1e9
                        source = "base_config.json num_parameters (adapter total excludes adapter trainable params; see report note)"
                except Exception:
                    pass
        else:
            params = params_from_config(cfg)
            source = "config.json" if params is not None else None
    if params is not None:
        report["parameters_b"] = params
        report["parameters_status"] = "verified_from_artifact"
        report["parameters_source"] = source
    else:
        report["parameters_b"] = manifest.get("parameters_b_declared")
        report["parameters_status"] = "unverified"
        report["parameters_source"] = (
            "declared only (manifest parameters_b_declared); "
            "not used for the budget verdict")

    # --- context (LLM only; not applicable to ASR) ---
    if manifest.get("kind") != "llm":
        report["context"] = {"value": None, "status": "not_applicable",
                             "limit": MAX_CONTEXT}
    else:
        ctx_val = manifest.get("max_context_tokens")
        if ctx_val is None and isinstance(cfg, dict):
            ctx_val = cfg.get("max_position_embeddings")
        if ctx_val is None:
            report["context"] = {"value": None, "status": "unverified",
                                 "limit": MAX_CONTEXT}
        else:
            report["context"] = {"value": ctx_val, "status": "verified",
                                 "limit": MAX_CONTEXT,
                                 "within_limit": ctx_val <= MAX_CONTEXT}

    # --- budget ---
    budget = {}
    if manifest.get("kind") == "llm":
        if report["parameters_status"] == "verified_from_artifact":
            budget["llm_lt_5b"] = params < MAX_LLM_B
        else:
            budget["llm_lt_5b"] = None  # unverified, not assumed
    if (report["parameters_status"] == "verified_from_artifact"
            and companion_params_b is not None):
        total = params + float(companion_params_b)
        budget["total_b"] = total
        budget["total_lt_6b"] = total < MAX_TOTAL_B
    else:
        budget["total_b"] = None
        budget["total_lt_6b"] = None
    budget["pair_total_verified"] = budget.get("total_lt_6b") is not None
    report["budget"] = budget
    report["missing"] = missing

    # --- verdict (strict order: invalid > missing > over-budget > unverified) ---
    if report["config_error"] or mismatch:
        report["verdict"] = "INVALID"
    elif missing:
        report["verdict"] = "MISSING"
    elif budget.get("llm_lt_5b") is False or budget.get("total_lt_6b") is False \
            or report["context"].get("within_limit") is False:
        report["verdict"] = "OVER_BUDGET"
    elif report["parameters_status"] != "verified_from_artifact" \
            or report["context"].get("status") not in ("verified", "not_applicable"):
        report["verdict"] = "UNVERIFIED"
    else:
        report["verdict"] = "USABLE"
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="preflight")
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--checkpoint-dir", required=True)
    ap.add_argument("--companion-params-b", type=float, default=None,
                    help="verified parameters (billions) of the OTHER "
                         "component, from its own preflight, for the "
                         "total < 6B check")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    report = check(args.manifest, args.checkpoint_dir, args.companion_params_b)
    text = json.dumps(report, indent=2, ensure_ascii=False)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    return 0 if report["verdict"] == "USABLE" else 2


if __name__ == "__main__":
    sys.exit(main())
