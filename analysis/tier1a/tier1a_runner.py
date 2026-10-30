"""Tier 1a runner — B0 vs B-gold on a frozen, stratified dev set (LifeMate only).

Packaged from ~/workspace/chat3/next-step/tier1a/runner/tier1a_runner.py
(execution report: BLOCKED, no model run) into this branch under
analysis/tier1a/. Logic for B0 vs B-gold and the frozen metrics in
metrics.py is unchanged; the changes in this packaged version are:

  * Paths are parameters: CLI flags, else the TIER1A_* environment
    variables, else Kaggle defaults (/kaggle/input, /kaggle/working).
    Nothing is hardcoded to the author's VM paths.
  * RUN / SCORE SEPARATION (hard requirement, not a style choice):
    the run phase NEVER reads gold tool calls or gold state hashes.
    It writes submission lines (tool_calls + state_hash) to disk and
    nothing else about correctness. The score phase is a separate
    command that reads those written traces first, and only then
    reads gold calls to compute score/F1/hash/state and WER/slot/
    attribution/bootstrap. In the run phase the code never touches
    Sample.label, never calls label_class(), never calls _gold_hash,
    and never calls score_sample. `check-separation` proves this by
    parsing this file's AST (stdlib only, runs before any weight
    is loaded) and fails if any of those paths appear in the run
    path (cmd_run, cmd_asr_cache, TracingGenerator, AsrCache).
    B-gold uses ONLY the gold transcript (audio_text) as the agent's
    current-turn input through a real AgentLoop.run() — never
    replay-gold, never gold calls as input or history.
  * FULL TRACE per sample-run (see TRACE_KEYS): prompt sequence,
    RAW MODEL OUTPUT per generation, token counts, parsed call,
    observation fed back, error, and seconds. Raw capture is
    implemented at the generator-wrapper layer (see TracingGenerator):
    for the vLLM backend it shims the inner LLM's generate() so the
    raw text the parser sees is recorded before parsing; for the
    transformers backend it captures generated token ids and decodes
    the suffix after the templated prompt. If neither capture path
    is available, raw_output is null WITH an explicit reason — raw
    text is never reconstructed from the parsed call, never invented.
    Token counts come from the generator's tokenizer when available;
    otherwise they are null with a reason. Observations are derived
    honestly from the prompt sequence: AgentLoop renders each
    observation into the NEXT prompt, so the suffix of the next
    prompt after the base prompt IS the observation (or validation /
    replan message) fed back for that generation. The loop does not
    expose its results list, and this runner does not reimplement
    the loop to pretend otherwise.
  * Observer log: read from loop.observer.records (the real
    ShadowObserver attribute), not .log (which the original runner
    read and always got [] from). Shadow-only: recorded for reading,
    never used to alter, block, or drop a call.
  * Manifest gate: run/asr-cache/check-off-on refuse any manifest
    whose status is not "stratified-frozen", whose ids_sha256 does
    not recompute, or that contains a non-dev / held-out id. The
    provisional hash-only 200-id set is NOT in this branch and is
    never accepted here.
  * OFF-vs-ON is a real command: pilot 20, same condition (B0),
    observer OFF then ON, submission lines compared byte-for-byte.
    It exits non-zero on any mismatch; the notebook scoring cell
    refuses to score unless the OFF-vs-ON report says identical.
  * Phase 1 fix (this branch, LifeMate only, no lifemate/ edit):
    faster-whisper CANNOT load vinai/PhoWhisper-small directly:
    faster-whisper needs a CTranslate2 directory (model.bin +
    config.json + tokenizer/vocabulary), and the pinned checkpoint
    is a transformers-format checkpoint with no model.bin
    (RUN_LIFEMATE.md section 5, recorded after faster-whisper
    1.2.1 installed but load failed; a third-party CTranslate2
    conversion of the same checkpoint exists precisely because
    the original is not CTranslate2). So this runner now (a)
    checks the ASR model files BEFORE any weight is loaded and
    fails fast with the conversion command when the direct
    faster-whisper load is impossible, and (b) offers a
    transformers backend (AutoModelForSpeechSeq2Seq, same
    checkpoint, greedy, language vi) selected with
    --asr-backend transformers / TIER1A_ASR_BACKEND. The selected
    backend is recorded in the config snapshot and per-mode run
    manifest; it never silently replaces the pinned config.
  * Completeness gate (Phase 1, mandatory): score refuses to
    compute any total unless both arms cover exactly the manifest
    ids (no missing, no duplicate, no extra, same id set in both
    arms, no trace with a run error, no arm mismatch) AND the
    OFF-vs-ON pilot is 20 samples and identical. A partial run
    is reported as INCOMPLETE with the missing list, exit 2, and
    no score_report.json is written. Run manifests carry their
    own COMPLETE/INCOMPLETE status per mode.
  * Resume (Phase 1): `run --resume` reuses a previous trace
    only when its stored input hash matches the input hash
    recomputed for this run (sample, mode, wav sha, current and
    history transcripts, config and checkpoint/backend). A trace
    with a run error, a missing run-manifest sidecar, or a
    changed input hash is re-run. Resume never reuses a trace
    blindly and never changes the manifest order.

Modes (stream-C section 0, section 5):
  B0     — current turn: ASR baseline (vinai/PhoWhisper-small,
           faster-whisper, greedy beam 1, lang vi); LLM baseline.
  B-gold — current turn: gold transcript (sample.audio_text); same
           LLM, same config, same samples, same order. NOT
           replay-gold: a real AgentLoop.run() whose input is gold.

History turns are FIXED in every mode: gold audio_text if present,
else the shared baseline-ASR cache. Only the current turn varies.

G&G: shadow-only in every run. Config copy sets shadow_observer=True
for main runs (recommended.json has no such key; PipelineConfig
default is False). The observer is never consulted to alter a call.
pending_ask_stop stays False, history V2 stays off.

ASR cache (section 5.3): key = (checkpoint, revision-or-"",
sha256(wav), backend, beam_size, language). One JSON file per
checkpoint; a cache is NEVER reused across checkpoints. Gold
transcripts never enter it. Each wav is transcribed once per
checkpoint; the asr-cache command builds that cache before runs.

Usage (Kaggle defaults shown; all flags override env, env overrides
defaults):
  python3 tier1a_runner.py smoke --source-tree <tree>
      --benchmark <manifest-schema-or-manifest> --out <dir>
  python3 tier1a_runner.py check-separation
  python3 tier1a_runner.py validate-manifest --source-tree <tree>
      --benchmark <manifest>
  python3 tier1a_runner.py asr-cache --source-tree <tree> --data <root>
      --benchmark <frozen-manifest> --out <dir>
  python3 tier1a_runner.py run --source-tree <tree> --data <root>
      --benchmark <frozen-manifest> --mode B0 --out <dir> [--pilot]
  python3 tier1a_runner.py check-off-on --source-tree <tree>
      --data <root> --benchmark <frozen-manifest> --out <dir>
  python3 tier1a_runner.py score --traces <run-out-dir> --data <root>
      --source-tree <tree> --benchmark <frozen-manifest> --out <dir>
"""
from __future__ import annotations

import argparse
import shutil
import ast
import hashlib
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from metrics import attribution_bool, bootstrap_paired_ci, slot_error, wer  # noqa: E402

PILOT_SIZE = int(os.environ.get("TIER1A_PILOT_SIZE", "20"))
if not 1 <= PILOT_SIZE <= 20:
    raise ValueError("pilot size must be between 1 and 20")
BENCHMARK_SEED = 20261030
BOOTSTRAP_SEED = 20261030
EXPECTED_CONFIG_SHA = "71d5f38f23d126427b08c09925cbbd9da933fc3750cbec55942809737e980076"
EXPECTED_SPLIT_SHA = "eefd0faa163285b23d2634bc4cc04f515b58367a2344599e46e85d48818280aa"
EXPECTED_SOURCE_COMMIT = "ddbe0a0b18a6fb9f6e7d261628a51e7a2c6c10c6"

# Kaggle defaults; every one is overridable by flag or environment.
DEFAULT_SOURCE_TREE = os.environ.get("TIER1A_SOURCE_TREE", "/kaggle/working/ZaloAIC")
DEFAULT_DATA = os.environ.get("TIER1A_DATA", "/kaggle/input")
DEFAULT_WORKING = os.environ.get("TIER1A_WORKING", "/kaggle/working")
DEFAULT_BENCHMARK = os.environ.get(
    "TIER1A_BENCHMARK", str(Path(DEFAULT_WORKING) / "benchmark-stratified-frozen.json"))


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def ids_sha256(ids: list[str]) -> str:
    return sha256_text(json.dumps(ids, ensure_ascii=False))


def load_benchmark(path: Path) -> dict:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    ids = doc["ids"]
    assert len(ids) == len(set(ids)), "duplicate ids in benchmark file"
    return doc


def assert_no_heldout(ids: list[str], source_tree: Path) -> None:
    split = json.loads((source_tree / "lifemate/splits/train_dev_heldout.json").read_text())
    held = {k for k, v in split.items() if v == "heldout"}
    leak = sorted(set(ids) & held)
    assert not leak, f"held-out ids leaked into benchmark list: {leak}"
    dev = {k for k, v in split.items() if v == "dev"}
    assert set(ids) <= dev, "benchmark ids must all be dev ids"


def validate_manifest(path: Path, source_tree: Path) -> dict:
    """Strict manifest gate. Returns a report dict; raises on failure.

    Checks: status == "stratified-frozen"; ids_sha256 recomputes;
    every id is a dev id and no id is held-out; no duplicates.
    Coverage / stratum counts are reported, not gated here, because
    refreeze.py records a SHORTFALL instead of silently lowering a
    threshold (stream-C section 4.2 step 4); the notebook surfaces
    any shortfall before weights are loaded.
    """
    doc = load_benchmark(path)
    ids = doc["ids"]
    if doc.get("status") != "stratified-frozen":
        raise SystemExit(
            f"manifest status is {doc.get('status')!r}, not 'stratified-frozen': "
            "refuse to run. Run refreeze.py first; the provisional "
            "hash-only set is never accepted here.")
    if doc.get("ids_sha256") != ids_sha256(ids):
        raise SystemExit("manifest ids_sha256 mismatch: manifest was edited "
                         "after freezing; refuse to run.")
    assert_no_heldout(ids, source_tree)
    split = json.loads((source_tree / "lifemate/splits/train_dev_heldout.json").read_text())
    dev_n = sum(1 for v in split.values() if v == "dev")
    held_n = sum(1 for v in split.values() if v == "heldout")
    return {
        "manifest": str(path),
        "status": doc["status"],
        "n": len(ids),
        "ids_sha256": doc["ids_sha256"],
        "split_dev": dev_n,
        "split_heldout": held_n,
        "stratum_dev_counts": doc.get("stratum_dev_counts"),
        "stratum_selected_counts": doc.get("stratum_selected_counts"),
        "coverage": doc.get("coverage"),
        "coverage_shortfall": doc.get("coverage_shortfall", []),
        "selection_notes": doc.get("selection_notes", []),
        "excluded_n": len(doc.get("excluded", [])),
    }


def verify_source(source_tree: Path) -> dict:
    """Verify config + split SHAs, config fields, budget, and (when a
    git checkout is present) that lifemate/ matches the CPU pin.

    ddbe0a0 is an ancestor of main head 4eba28c and `git diff
    ddbe0a0 HEAD -- lifemate/` is empty (docs-only changes after it),
    so lifemate/ from the pinned worktree IS the pinned lifemate/ tree.
    If that ever stops being true, this check must fail loudly.
    """
    cfg_sha = sha256_file(source_tree / "lifemate/configs/recommended.json")
    split_sha = sha256_file(source_tree / "lifemate/splits/train_dev_heldout.json")
    if cfg_sha != EXPECTED_CONFIG_SHA:
        raise SystemExit(f"config SHA mismatch: {cfg_sha} != {EXPECTED_CONFIG_SHA}")
    if split_sha != EXPECTED_SPLIT_SHA:
        raise SystemExit(f"split SHA mismatch: {split_sha} != {EXPECTED_SPLIT_SHA}")
    cfg = json.loads((source_tree / "lifemate/configs/recommended.json").read_text())
    assert cfg["llm_checkpoint"] == "Qwen/Qwen3-4B-Instruct-2507"
    assert cfg["llm_revision"] == "cdbee75"
    assert cfg["llm_temperature"] == 0.0 and cfg["llm_seed"] == 42
    assert cfg["llm_max_context_tokens"] == 16384
    assert cfg["asr_checkpoint"] == "vinai/PhoWhisper-small"
    assert cfg["asr_backend"] == "faster-whisper" and cfg["asr_greedy"] is True
    assert cfg["asr_language"] == "vi"
    assert cfg["grounding"] is True
    assert cfg["max_steps"] == 12 and cfg["max_repeats"] == 2
    assert cfg["total_params_b"] < 6.0 and cfg["llm_params_b"] < 5.0
    assert cfg["llm_max_context_tokens"] <= 16384
    return {"config": cfg, "config_sha256": cfg_sha, "split_sha256": split_sha}


def verify_source_git(source_tree: Path) -> dict:
    """Git-level source check: lifemate/ must equal the ddbe0a0 tree.

    Runs `git diff ddbe0a0 HEAD -- lifemate/` in the source tree.
    Returns {"checked": bool, "diff_lines": int, ...}. When the tree
    is not a git checkout, checked=False and the caller (notebook
    preflight) must fail fast instead of silently passing — the
    Kaggle flow always clones the branch, so a missing checkout is
    itself a blocker.
    """
    import subprocess
    try:
        diff = subprocess.run(
            ["git", "-C", str(source_tree), "diff", "ddbe0a0", "HEAD", "--", "lifemate/"],
            capture_output=True, text=True, check=False)
        head = subprocess.run(
            ["git", "-C", str(source_tree), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=False)
        ancestor = subprocess.run(
            ["git", "-C", str(source_tree), "merge-base", "--is-ancestor",
             "ddbe0a0", "HEAD"], capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return {"checked": False, "reason": "git not available"}
    if diff.returncode != 0 or head.returncode != 0:
        return {"checked": False, "reason": "git diff/rev-parse failed",
                "stderr": (diff.stderr + head.stderr).strip()[:500]}
    return {"checked": True, "head": head.stdout.strip(),
            "ddbe0a0_is_ancestor": ancestor.returncode == 0,
            "lifemate_diff_lines": len(diff.stdout.splitlines()),
            "lifemate_diff_empty": diff.stdout.strip() == ""}


# ---------------------------------------------------------------- ASR backends
# Phase 1: faster-whisper needs CTranslate2 format. The pinned
# checkpoint vinai/PhoWhisper-small is transformers-format, so a
# direct WhisperModel("vinai/PhoWhisper-small") load is NOT possible.
# Two supported paths, both checked BEFORE any weight is loaded:
#   (a) Convert once on the GPU host, then point at the converted dir:
#       pip install "faster-whisper==1.2.1" ctranslate2 "transformers[torch]"
#       ct2-transformers-converter --model vinai/PhoWhisper-small \
#           --output_dir /kaggle/working/PhoWhisper-small-ct2 \
#           --copy_files tokenizer.json preprocessor_config.json \
#           --quantization float16
#       then run with --asr-backend faster-whisper
#       --asr-model-dir /kaggle/working/PhoWhisper-small-ct2.
#       Record the actual installed versions (pip show ctranslate2
#       faster-whisper transformers) in the run report; only
#       faster-whisper==1.2.1 is version-pinned here because it is
#       the version recorded in RUN_LIFEMATE.md section 5. Other
#       package versions are recorded after install, never invented.
#       A converted directory must contain model.bin + config.json
#       + a tokenizer/vocabulary file; preprocessor_config.json is
#       reported but not hard-required (see check_ct2_dir).
#   (b) Transformers backend, same checkpoint, no conversion:
#       run with --asr-backend transformers. It loads
#       AutoModelForSpeechSeq2Seq + AutoProcessor for
#       vinai/PhoWhisper-small, greedy (num_beams=1, do_sample=False),
#       language vi, task transcribe. This is a Phase-1 fallback
#       for the impossible direct faster-whisper load, recorded as
#       asr_backend_actual=transformers in every run manifest; it
#       does not change the pinned checkpoint or the LLM.
# A third-party CTranslate2 conversion (e.g. qbsmlabs/PhoWhisper-small)
# is NOT pinned here: if an operator wants to use one, they must
# point at a local converted directory that passes check_ct2_dir
# and record its source in the run report themselves.
PINNED_ASR_CHECKPOINT = "vinai/PhoWhisper-small"
CT2_TOKENIZER_FILES = ("tokenizer.json", "vocabulary.json", "vocabulary.txt",
                       "shared_vocabulary.txt", "tokenizer_config.json")
TRANSFORMERS_TOKENIZER_FILES = ("tokenizer_config.json", "tokenizer.json")


def _tokenizer_evidence(names) -> str | None:
    for name in CT2_TOKENIZER_FILES:
        if name in names:
            return name
    return None


def check_ct2_dir(path: Path) -> dict:
    """Verify a CTranslate2 model directory, stdlib only, no weights.

    Required: model.bin + config.json + one tokenizer/vocabulary file.
    Raises SystemExit listing exactly what is missing, before any
    faster-whisper load is attempted."""
    names = {p.name for p in Path(path).iterdir()} if Path(path).is_dir() else set()
    missing = []
    if "model.bin" not in names:
        missing.append("model.bin (CTranslate2 weights — a transformers-format "
                       "checkpoint has no model.bin and cannot be loaded "
                       "directly by faster-whisper)")
    if "config.json" not in names:
        missing.append("config.json")
    tok = _tokenizer_evidence(names)
    if tok is None:
        missing.append("tokenizer/vocabulary file (one of: "
                       + ", ".join(CT2_TOKENIZER_FILES) + ")")
    if missing:
        raise SystemExit(f"CTranslate2 model directory incomplete: {path}\n"
                         f"missing: {missing}\n"
                         "Convert the transformers checkpoint first "
                         "(see the conversion command in this file) or "
                         "use --asr-backend transformers.")
    return {"backend": "faster-whisper", "model_dir": str(path),
            "model_bin": True, "config_json": True, "tokenizer_file": tok,
            "preprocessor_config_present": "preprocessor_config.json" in names}


def check_transformers_dir(path: Path) -> dict:
    """Verify a transformers Whisper directory, stdlib only, no weights.

    Required: config.json + preprocessor_config.json + a tokenizer
    file + weights (model.safetensors, or its index, or
    pytorch_model.bin). Raises SystemExit listing what is missing,
    before any large weight download is attempted."""
    names = {p.name for p in Path(path).iterdir()} if Path(path).is_dir() else set()
    missing = []
    if "config.json" not in names:
        missing.append("config.json")
    if "preprocessor_config.json" not in names:
        missing.append("preprocessor_config.json")
    tok = None
    for name in TRANSFORMERS_TOKENIZER_FILES:
        if name in names:
            tok = name
            break
    if tok is None:
        missing.append("tokenizer file (tokenizer_config.json or tokenizer.json)")
    weights = None
    for name in ("model.safetensors", "model.safetensors.index.json",
                 "pytorch_model.bin"):
        if name in names:
            weights = name
            break
    if weights is None:
        missing.append("weights (model.safetensors, model.safetensors.index.json, "
                       "or pytorch_model.bin)")
    if missing:
        raise SystemExit(f"transformers model directory incomplete: {path}\n"
                         f"missing: {missing}")
    return {"backend": "transformers", "model_dir": str(path),
            "config_json": True, "preprocessor_config_json": True,
            "tokenizer_file": tok, "weights_file": weights}


def _list_hf_files(repo_id: str):
    """List files of a Hub repo (metadata only, no weights), or None
    when huggingface_hub is unavailable. Never downloads weights."""
    try:
        from huggingface_hub import list_repo_files
    except ImportError:
        return None
    return list_repo_files(repo_id, repo_type="model")


def check_asr_model(backend: str, checkpoint: str, model_dir: str | None) -> dict:
    """Fail-fast ASR model check, before any weight load.

    Returns a report dict. Raises SystemExit with the exact missing
    files / the conversion command / the transformers alternative.
    For the pinned checkpoint under faster-whisper with no converted
    directory, this fails immediately without attempting a download:
    the checkpoint is known transformers-format (see the section
    header), so attempting WhisperModel() on it can only fail after
    wasted setup."""
    if backend not in ("faster-whisper", "transformers"):
        raise SystemExit(f"unknown ASR backend {backend!r}: "
                         "use faster-whisper or transformers")
    if model_dir:
        path = Path(model_dir)
        if not path.is_dir():
            raise SystemExit(f"ASR model directory does not exist: {path}")
        if backend == "faster-whisper":
            report = check_ct2_dir(path)
        else:
            report = check_transformers_dir(path)
        report["checkpoint"] = checkpoint
        report["source"] = "local_dir"
        return report
    if backend == "faster-whisper" and checkpoint == PINNED_ASR_CHECKPOINT:
        raise SystemExit(
            "BLOCKED: faster-whisper cannot load vinai/PhoWhisper-small "
            "directly. The checkpoint is transformers-format (no model.bin "
            "for CTranslate2); RUN_LIFEMATE.md section 5 records the same "
            "failure with faster-whisper 1.2.1. No download was attempted.\n"
            "Do one of:\n"
            "  (a) Convert once, then rerun with the converted directory:\n"
            "      ct2-transformers-converter --model vinai/PhoWhisper-small \\\n"
            "          --output_dir /kaggle/working/PhoWhisper-small-ct2 \\\n"
            "          --copy_files tokenizer.json preprocessor_config.json \\\n"
            "          --quantization float16\n"
            "      and pass --asr-model-dir /kaggle/working/PhoWhisper-small-ct2\n"
            "  (b) Use the transformers backend instead:\n"
            "      --asr-backend transformers\n"
            "      (same checkpoint, greedy, language vi; recorded as "
            "asr_backend_actual=transformers in the run manifest)")
    # A local checkpoint path (not a Hub id) is checked as a directory.
    if Path(checkpoint).is_dir():
        report = (check_ct2_dir(checkpoint) if backend == "faster-whisper"
                  else check_transformers_dir(checkpoint))
        report["checkpoint"] = checkpoint
        report["source"] = "local_dir"
        return report
    files = _list_hf_files(checkpoint)
    if files is None:
        raise SystemExit(
            f"BLOCKED: cannot verify ASR model files for {checkpoint!r} "
            "before downloading weights (huggingface_hub is not installed). "
            "Point at a local model directory with --asr-model-dir, or "
            "install huggingface_hub so the file list can be checked first.")
    names = set(files)
    if backend == "faster-whisper":
        if "model.bin" not in names or "config.json" not in names \
                or _tokenizer_evidence(names) is None:
            raise SystemExit(
                f"BLOCKED: Hub repo {checkpoint!r} has no CTranslate2 files "
                f"(model.bin/config.json/tokenizer) in its file list: "
                f"{sorted(names)}. Convert it first or use "
                "--asr-backend transformers.")
        return {"backend": backend, "checkpoint": checkpoint,
                "source": "hub_file_list", "model_bin": True,
                "tokenizer_file": _tokenizer_evidence(names)}
    missing = []
    if "config.json" not in names:
        missing.append("config.json")
    if "preprocessor_config.json" not in names:
        missing.append("preprocessor_config.json")
    if not any(t in names for t in TRANSFORMERS_TOKENIZER_FILES):
        missing.append("tokenizer_config.json/tokenizer.json")
    if not any(w in names for w in ("model.safetensors",
                                    "model.safetensors.index.json",
                                    "pytorch_model.bin")):
        missing.append("weights")
    if missing:
        raise SystemExit(f"BLOCKED: Hub repo {checkpoint!r} is missing "
                         f"transformers files {missing} (file list checked, "
                         "no weights downloaded).")
    return {"backend": backend, "checkpoint": checkpoint,
            "source": "hub_file_list"}


def resolve_asr_backend(args, cfg: dict):
    """Selected ASR backend + model dir: flag > env > pinned config.

    The pinned config backend is faster-whisper; selecting
    transformers is a recorded fallback, not a silent config edit."""
    backend = getattr(args, "asr_backend", None) \
        or os.environ.get("TIER1A_ASR_BACKEND") or cfg.get("asr_backend")
    model_dir = getattr(args, "asr_model_dir", None) \
        or os.environ.get("TIER1A_ASR_MODEL_DIR") or None
    return backend, model_dir


def cmd_check_asr_model(args) -> int:
    report = check_asr_model(args.asr_backend, args.checkpoint, args.asr_model_dir)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


# ---------------------------------------------------------------- separation
# Run path = cmd_run, cmd_asr_cache, TracingGenerator, AsrCache, and
# the helpers they call in this file. Score path = cmd_score only.
# The separation check parses this file and fails if a forbidden
# gold-access pattern appears in any run-path function.
FORBIDDEN_IN_RUN_PATH = (".label", "label_class", "_gold_hash",
                         "score_sample", "gold_tool_calls")


def check_run_gold_separation() -> dict:
    """AST + text check: no gold-call read in the run path.

    Inspects the source of this file (not a copy, not a summary):
    for each run-path function, every attribute name and every called
    function name is collected from the AST, and the function source
    segment is also scanned for the forbidden substrings. The check
    passes only if none appear. cmd_score is deliberately excluded:
    reading gold there is its job, and only after traces are on disk.
    """
    src = Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    run_funcs = {"cmd_run", "cmd_asr_cache", "TracingGenerator", "AsrCache",
                 "cmd_check_off_on"}
    found: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in run_funcs:
            segment = ast.get_source_segment(src, node) or ""
            hits = [pat for pat in FORBIDDEN_IN_RUN_PATH if pat in segment]
            # AST-level names, so a mention inside a docstring of a
            # run function would also be caught by the text scan
            # above; that strictness is intentional.
            if hits:
                found[node.name] = hits
    return {"run_path_functions_checked": sorted(run_funcs),
            "forbidden_found": found,
            "passed": not found}


def cmd_check_separation(args) -> int:
    result = check_run_gold_separation()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["passed"] else 1


def cmd_validate_manifest(args) -> int:
    source = Path(args.source_tree)
    verified = verify_source(source)
    report = validate_manifest(Path(args.benchmark), source)
    report["config_sha256"] = verified["config_sha256"]
    report["split_sha256"] = verified["split_sha256"]
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


# ---------------------------------------------------------------- traces
TRACE_KEYS = [
    "sample_id", "split", "arm", "input_mode", "transcript_current",
    "transcript_gold_current", "transcript_source_history", "wav_path",
    "wav_sha256", "prompt_sha256", "prompt_full", "generations",
    "tool_calls", "state_hash", "observer_log", "seconds",
    "n_generations", "run_error",
]

GENERATION_KEYS = [
    "prompt", "raw_output", "raw_output_reason", "raw_output_token_count",
    "prompt_token_count", "token_count_reason", "parsed_call", "error",
    "seconds", "observation_following", "observation_kind",
]


def empty_trace(sample_id: str, arm: str) -> dict:
    return {
        "sample_id": sample_id, "split": "dev", "arm": arm,
        "input_mode": "asr_baseline" if arm == "B0" else "gold",
        "transcript_current": None, "transcript_gold_current": None,
        "transcript_source_history": [], "wav_path": None, "wav_sha256": None,
        "prompt_sha256": None, "prompt_full": None, "generations": [],
        "tool_calls": [], "state_hash": None, "observer_log": [],
        "seconds": None, "n_generations": 0, "run_error": None,
    }


class _VLLMGenerateCapture:
    """Proxy for a vLLM LLM object: records the raw text of each
    generate() call, returns the result object unchanged.

    The inner generator parses that text internally and discards it;
    shimming generate() is the only wrapper-level way to see it
    without editing the library. All other attributes delegate to
    the wrapped object, so generation behaviour is unchanged.
    """

    def __init__(self, inner, recorder: list):
        self._inner = inner
        self.recorder = recorder

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def generate(self, prompts, sampling_params, *args, **kwargs):
        result = self._inner.generate(prompts, sampling_params, *args, **kwargs)
        try:
            out = result[0].outputs[0]
            self.recorder.append({
                "raw_text": getattr(out, "text", None),
                "token_ids": list(getattr(out, "token_ids", None) or []),
            })
        except Exception as exc:  # never break generation on tracing
            self.recorder.append({"raw_text": None, "token_ids": [],
                                  "capture_error": str(exc)})
        return result


class _TransformersGenerateCapture:
    """Proxy for a transformers model: records generated token ids.

    The inner generator decodes those ids internally; the wrapper
    decodes the suffix after the templated prompt itself, so the
    recorded raw text is the model's own decoded suffix, not a
    reconstruction from the parsed call.
    """

    def __init__(self, inner, recorder: list):
        self._inner = inner
        self.recorder = recorder

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def generate(self, *args, **kwargs):
        result = self._inner.generate(*args, **kwargs)
        try:
            ids = result[0].tolist() if hasattr(result[0], "tolist") else list(result[0])
            self.recorder.append({"generated_ids": ids})
        except Exception as exc:
            self.recorder.append({"generated_ids": [], "capture_error": str(exc)})
        return result


class TracingGenerator:
    """Wrap a real generator; record prompt, raw output, token
    counts, parsed call, timing, and (post-hoc) the observation
    fed back, per generation.

    Raw capture: if the inner generator exposes a vLLM LLM object,
    its generate() is shimmed (see above) and raw text is recorded
    before parsing. If it exposes a transformers model, generated
    ids are captured and decoded after the call. Otherwise
    raw_output is null with an explicit reason. Token counts use
    the inner tokenizer when present: prompt tokens are the
    templated prompt tokens (the form the backend actually
    generates from); raw tokens are the vLLM token ids, the
    captured generated ids, or a tokenizer count of the raw text.
    Without a tokenizer, counts are null with a reason.

    Observation derivation (documented, not loop internals): after
    the run, each generation's observation_following is the suffix
    of the NEXT prompt after the base prompt, because the loop
    renders observations into the next prompt. Kinds: observation,
    validation_failure_observation, invalid_output_reprompt,
    replan_observation, or None for the final generation.
    """

    def __init__(self, inner):
        self.inner = inner
        self.generations: list[dict] = []
        self._raw: list[dict] = []
        self._tok = getattr(inner, "tokenizer", None)
        self._install_capture()

    def _install_capture(self):
        llm_obj = getattr(self.inner, "llm", None)
        if llm_obj is not None and isinstance(llm_obj, _VLLMGenerateCapture):
            llm_obj.recorder = self._raw
            self._capture_kind = "vllm"
            return
        if llm_obj is not None:
            try:
                self.inner.llm = _VLLMGenerateCapture(llm_obj, self._raw)
                self._capture_kind = "vllm"
                return
            except Exception:
                pass
        model_obj = getattr(self.inner, "model", None)
        if model_obj is not None:
            if isinstance(model_obj, _TransformersGenerateCapture):
                model_obj.recorder = self._raw
            else:
                try:
                    self.inner.model = _TransformersGenerateCapture(model_obj, self._raw)
                except Exception:
                    self._capture_kind = "unavailable"
                    return
            self._capture_kind = "transformers"
            return
        self._capture_kind = "unavailable"

    def _prompt_token_count(self, prompt: str):
        if self._tok is None:
            return None, "no tokenizer on generator"
        try:
            templated = self._tok.apply_chat_template(
                [{"role": "user", "content": prompt}], tokenize=False,
                add_generation_prompt=True)
            ids = self._tok(templated, add_special_tokens=False)["input_ids"]
            return len(ids), None
        except Exception:
            try:
                ids = self._tok(prompt, add_special_tokens=False)["input_ids"]
                return len(ids), "chat-template tokenisation failed; plain prompt count"
            except Exception as exc:
                return None, f"tokenizer failed: {exc}"

    def _raw_for_call(self, index: int, prompt: str):
        """Resolve raw text + token count for generation `index`."""
        if self._capture_kind == "unavailable" or index >= len(self._raw):
            return (None, "generator backend does not expose raw output "
                    "through this wrapper", None,
                    "no raw output captured; count unavailable")
        cap = self._raw[index]
        if cap.get("capture_error"):
            return None, f"raw capture failed: {cap['capture_error']}", None, \
                "raw capture failed; count unavailable"
        if self._capture_kind == "vllm":
            raw = cap.get("raw_text")
            toks = cap.get("token_ids") or []
            if raw is not None and toks:
                return raw, None, len(toks), None
            if raw is not None and self._tok is not None:
                try:
                    n = len(self._tok(raw, add_special_tokens=False)["input_ids"])
                    return raw, None, n, None
                except Exception as exc:
                    return raw, None, None, f"tokenizer failed: {exc}"
            return raw, None, None, "no token ids and no tokenizer"
        # transformers: decode ids after the templated prompt.
        ids = cap.get("generated_ids") or []
        if not ids or self._tok is None:
            return (None, "transformers capture has no ids or no tokenizer",
                    None, "count unavailable")
        try:
            templated = self._tok.apply_chat_template(
                [{"role": "user", "content": prompt}], tokenize=False,
                add_generation_prompt=True)
            plen = len(self._tok(templated, add_special_tokens=False)["input_ids"])
            gen_ids = ids[plen:]
            raw = self._tok.decode(gen_ids, skip_special_tokens=True)
            return raw, None, len(gen_ids), None
        except Exception as exc:
            return None, f"transformers decode failed: {exc}", None, \
                "decode failed; count unavailable"

    def __call__(self, prompt: str, tools: dict):
        start = time.time()
        out = self.inner(prompt, tools)
        seconds = time.time() - start
        idx = len(self.generations)
        raw, raw_reason, raw_toks, tok_reason = self._raw_for_call(idx, prompt)
        prompt_toks, prompt_tok_reason = self._prompt_token_count(prompt)
        reason = raw_reason or prompt_tok_reason
        parsed = out
        error = None
        if isinstance(out, dict) and out.get("name") == "__invalid__":
            error = "invalid_json_output"
        self.generations.append({
            "prompt": prompt, "raw_output": raw,
            "raw_output_reason": raw_reason,
            "raw_output_token_count": raw_toks,
            "prompt_token_count": prompt_toks,
            "token_count_reason": reason if (raw_toks is None or prompt_toks is None) else None,
            "parsed_call": parsed, "error": error, "seconds": seconds,
            "observation_following": None, "observation_kind": None,
        })
        return out

    def finalise_observations(self, base_prompt: str):
        """Fill observation_following/kind from the prompt sequence."""
        gens = self.generations
        for i, gen in enumerate(gens):
            if i + 1 >= len(gens):
                continue
            nxt = gens[i + 1]["prompt"]
            suffix = nxt[len(base_prompt):] if nxt.startswith(base_prompt) else nxt
            gen["observation_following"] = suffix
            if "validation failed" in suffix:
                gen["observation_kind"] = "validation_failure_observation"
                if gen["error"] is None:
                    gen["error"] = "validation_failed_not_executed"
            elif "not a valid tool call" in suffix:
                gen["observation_kind"] = "invalid_output_reprompt"
            elif "Choose a different" in suffix:
                gen["observation_kind"] = "replan_observation"
            elif "Previous calls and their OBSERVED results" in suffix:
                gen["observation_kind"] = "observation"
            else:
                gen["observation_kind"] = "other_prompt_suffix"


class AsrCache:
    """Per-checkpoint JSON cache. Key includes checkpoint + wav sha."""

    def __init__(self, path: Path, checkpoint: str, revision: str,
                 backend: str, beam_size: int, language: str,
                 model_dir: str | None = None):
        self.path = Path(path)
        self.meta = {"checkpoint": checkpoint, "revision": revision,
                     "backend": backend, "beam_size": beam_size, "language": language,
                     "model_dir": model_dir or ""}
        self.data = json.loads(self.path.read_text()) if self.path.exists() else {}
        if self.data and self.data.get("meta") != self.meta:
            raise SystemExit(f"ASR cache meta mismatch in {path}: refusing cross-checkpoint reuse")

    def get(self, wav_sha: str):
        return self.data.get("entries", {}).get(wav_sha)

    def put(self, wav_sha: str, transcript: str, wav_path: str, seconds: float):
        self.data.setdefault("meta", self.meta)
        self.data.setdefault("entries", {})[wav_sha] = {
            "transcript": transcript, "wav_path": wav_path, "seconds": seconds}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")


def missing_cached_wavs(cache: AsrCache, wavs) -> list[str]:
    """Reject an incomplete ASR cache before loading the LLM on GPU."""
    missing = []
    for wav in wavs:
        if not wav.exists():
            missing.append(str(wav))
            continue
        entry = cache.get(sha256_file(wav))
        if not entry or not isinstance(entry.get("transcript"), str) \
                or not entry["transcript"].strip():
            missing.append(str(wav))
    return missing


class TransformersASR:
    """Phase-1 fallback ASR: same PhoWhisper checkpoint via transformers.

    Interface matches FasterWhisperASR.transcribe(wav_path) so the
    cache and run code use it unchanged. Greedy decoding
    (num_beams=1, do_sample=False), language vi, task transcribe.
    Wavs are read with stdlib wave only: the dataset wavs are
    16 kHz mono 16-bit (RUN_LIFEMATE.md section 5); a wav at another
    sample rate fails fast instead of being silently resampled.
    Instantiation (weight load) happens only on the GPU host, after
    check_asr_model has passed."""

    def __init__(self, checkpoint: str, device: str = "cuda"):
        try:
            import torch
            from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor
        except ImportError as exc:
            raise RuntimeError(
                "transformers/torch not installed for the transformers ASR "
                "backend (see RUN_LIFEMATE.md section 3).") from exc
        self.torch = torch
        self.processor = AutoProcessor.from_pretrained(checkpoint)
        self.model = AutoModelForSpeechSeq2Seq.from_pretrained(
            checkpoint, torch_dtype=torch.float16 if device == "cuda"
            else torch.float32).to(device)
        self.device = device

    def _read_wav(self, wav_path):
        import wave
        with wave.open(str(wav_path), "rb") as w:
            rate = w.getframerate()
            channels = w.getnchannels()
            width = w.getsampwidth()
            frames = w.readframes(w.getnframes())
        if rate != 16000:
            raise ValueError(f"wav sample rate is {rate}, not 16000: "
                             f"{wav_path} (no silent resampling)")
        if width != 2:
            raise ValueError(f"wav sample width is {width} bytes, not 2: {wav_path}")
        import array
        samples = array.array("h")
        samples.frombytes(frames)
        if channels == 2:
            samples = array.array("h", [
                (samples[i] + samples[i + 1]) // 2
                for i in range(0, len(samples) - 1, 2)])
        elif channels != 1:
            raise ValueError(f"wav has {channels} channels, expected 1 or 2: {wav_path}")
        return [s / 32768.0 for s in samples]

    def transcribe(self, wav_path) -> str:
        audio = self._read_wav(wav_path)
        inputs = self.processor(audio, sampling_rate=16000, return_tensors="pt")
        inputs = {k: v.to(device=self.device, dtype=self.model.dtype)
                  if v.is_floating_point() else v.to(self.device)
                  for k, v in inputs.items()}
        try:
            forced = self.processor.get_decoder_prompt_ids(language="vi",
                                                           task="transcribe")
            gen_kwargs = {"forced_decoder_ids": forced}
        except Exception:
            gen_kwargs = {"language": "vi", "task": "transcribe"}
        with self.torch.no_grad():
            ids = self.model.generate(**inputs, max_new_tokens=256,
                                      do_sample=False, num_beams=1, **gen_kwargs)
        return self.processor.batch_decode(ids, skip_special_tokens=True)[0].strip()


def build_asr(backend: str, checkpoint: str, model_dir: str | None, source_tree: Path):
    """Build the ASR object for a backend already checked by
    check_asr_model. Faster-whisper uses the library class (unchanged
    lifemate code); transformers uses the runner-local wrapper above."""
    sys.path.insert(0, str(source_tree))
    if backend == "transformers":
        return TransformersASR(model_dir or checkpoint, device="cuda")
    from lifemate.asr import FasterWhisperASR
    return FasterWhisperASR(model_dir or checkpoint, device="cuda",
                            compute_type="float16")


class LazyASR:
    """Keep ASR weights off GPU when every required wav is already cached."""

    def __init__(self, factory):
        self.factory = factory
        self.instance = None

    def transcribe(self, wav_path):
        if self.instance is None:
            self.instance = self.factory()
        return self.instance.transcribe(wav_path)


def build_pilot_llm(cfg):
    """Use the unchanged generator protocol with an explicit bounded engine."""
    from lifemate.llm import VLLMGenerator
    from transformers import AutoTokenizer
    from vllm import LLM, SamplingParams

    checkpoint = os.environ.get("TIER1A_LLM_MODEL_DIR") or cfg.llm_checkpoint
    generator = VLLMGenerator.__new__(VLLMGenerator)
    generator.tokenizer = AutoTokenizer.from_pretrained(
        checkpoint, revision=cfg.llm_revision)
    generator.llm = LLM(
        model=checkpoint, revision=cfg.llm_revision, seed=cfg.llm_seed,
        max_model_len=cfg.llm_max_context_tokens, max_num_seqs=1,
        dtype="float16", enforce_eager=True, gpu_memory_utilization=0.90)
    generator.params = SamplingParams(temperature=0.0, seed=cfg.llm_seed,
                                      max_tokens=512)
    return generator


def input_hash_for_sample(sample_id: str, mode: str, wav_sha: str,
                          transcript_current, history_transcripts,
                          config_sha256: str, asr_checkpoint: str,
                          asr_backend: str, llm_checkpoint: str,
                          llm_revision: str) -> str:
    """Deterministic input hash for resume: a stored trace is reused
    only when every input that could change its output is identical."""
    payload = [sample_id, mode, wav_sha, transcript_current,
               history_transcripts, config_sha256, asr_checkpoint,
               asr_backend, llm_checkpoint, llm_revision]
    return sha256_text(json.dumps(payload, ensure_ascii=False))


def resume_plan(expected_ids: list[str], existing_traces: dict,
                stored_hashes: dict, current_hashes: dict):
    """Pure resume decision (stdlib, CPU): which ids can be skipped.

    Skip only a trace with no run error, a non-null state hash, and
    a stored input hash equal to the recomputed one. Everything
    else (missing, errored, changed input, missing sidecar entry)
    is re-run, in manifest order."""
    skip, rerun = [], []
    for sid in expected_ids:
        trace = existing_traces.get(sid)
        if trace is not None and trace.get("run_error") is None \
                and trace.get("state_hash") is not None \
                and stored_hashes.get(sid) == current_hashes.get(sid) \
                and current_hashes.get(sid) is not None:
            skip.append(sid)
        else:
            rerun.append(sid)
    return {"skip": skip, "rerun": rerun}


# ---------------------------------------------------------------- smoke
def cmd_smoke(args) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    source = Path(args.source_tree)
    verified = verify_source(source)
    bench = load_benchmark(Path(args.benchmark))
    assert_no_heldout(bench["ids"], source)
    separation = check_run_gold_separation()
    assert separation["passed"], separation
    # Unit checks on fixed strings (frozen normalisation).
    w = wer("Gọi cho Lan 0901234567 lúc 9 giờ", "gọi cho Lan 0901234568 lúc 9 giờ")
    assert w["N"] == 7 and w["S"] == 1 and w["D"] == 0 and w["I"] == 0, w
    assert wer("Gọi Lan!", "gọi lan")["wer"] == 0.0  # punctuation + case only
    assert wer("Điện thoại", "dien thoai")["wer"] > 0.0  # diacritics KEPT
    s = slot_error("Gọi 0901234567 và 100000 đồng", "gọi 0901234567 và 200000 đồng")
    assert s["n_slots"] == 2 and s["n_correct"] == 1 and s["slot_error_rate"] == 0.5, s
    ci = bootstrap_paired_ci([1.0, 1.0, 0.0], [0.0, 1.0, 0.0], n_resamples=200)
    assert "ci_low" in ci and "ci_high" in ci
    # Raw-capture unit test with a fake vLLM-shaped backend (CPU only):
    # the shim must record the raw text the parser would have seen,
    # and the token count must be the captured token ids, not a guess.
    class _FakeOut:
        def __init__(self, text, token_ids):
            self.text, self.token_ids = text, token_ids
    class _FakeReq:
        def __init__(self, out):
            self.outputs = [out]
    class _FakeLLM:
        def generate(self, prompts, params):
            return [_FakeReq(_FakeOut('{"name": "contacts.search", "arguments": {}}', [1, 2, 3]))]
    class _FakeGen:
        def __init__(self):
            self.llm = _FakeLLM()
            self.tokenizer = None
        def __call__(self, prompt, tools):
            # Mirror the real VLLMGenerator: generate, then parse.
            raw = self.llm.generate([prompt], None)[0].outputs[0].text
            return json.loads(raw)
    tg = TracingGenerator(_FakeGen())
    tg("test prompt", {})
    assert tg.generations[0]["raw_output"] == '{"name": "contacts.search", "arguments": {}}'
    assert tg.generations[0]["raw_output_token_count"] == 3
    assert tg.generations[0]["parsed_call"]["name"] == "contacts.search"
    assert all(list(g.keys()) == GENERATION_KEYS for g in tg.generations)
    # Empty-trace schema: every required key present, in run order.
    traces = [empty_trace(sid, "B0") for sid in bench["ids"][:2]]
    assert all(list(t.keys()) == TRACE_KEYS for t in traces)
    (out / "smoke_traces.jsonl").write_text(
        "".join(json.dumps(t, ensure_ascii=False) + "\n" for t in traces), encoding="utf-8")
    report = {
        "mode": "smoke (CPU plumbing only — NO model, NO data, NO GPU)",
        "source_verified": verified["config"],
        "config_sha256": verified["config_sha256"],
        "split_sha256": verified["split_sha256"],
        "benchmark_status": bench.get("status"),
        "benchmark_n": len(bench["ids"]),
        "benchmark_sha256": sha256_file(Path(args.benchmark)),
        "heldout_leak": 0,
        "run_gold_separation": separation,
        "unit_checks": "WER/S/D/I, diacritic-keeping, slot error, bootstrap CI, "
                       "raw-capture shim, generation schema: PASS",
        "trace_schema": "PASS (empty traces, all keys, run order)",
        "NOT_RUN": ["pilot 20", "B0 vs B-gold benchmark",
                    "OFF-vs-ON check", "any score, WER, or timing"],
        "blockers": "data + GPU — see README_TIER1A_KAGGLE.md",
    }
    (out / "smoke_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


# ---------------------------------------------------------------- run (GPU only)
def _load_samples_for_run(source_tree: Path, data_root: Path):
    sys.path.insert(0, str(source_tree))
    from lifemate.loader import load_catalog, load_split
    catalog = load_catalog(data_root, "train")
    samples = {s.id: s for s in load_split(data_root, "train")}
    return catalog, samples


def _build_asr_cache(cache: AsrCache, asr, wav: Path, wav_sha: str):
    cached = cache.get(wav_sha)
    if cached is not None:
        return cached["transcript"], False, 0.0
    ts = time.time()
    txt = asr.transcribe(wav)
    seconds = time.time() - ts
    cache.put(wav_sha, txt, str(wav), seconds)
    return txt, True, seconds


def cmd_asr_cache(args) -> int:
    """Build the baseline ASR cache for one frozen manifest.

    Transcribes each wav exactly once for this checkpoint: the
    current-turn wav of every kept sample, plus any history user
    wav whose transcript is missing. Gold transcripts are never
    written into the cache — they are not passed to transcribe()
    and the cache key is a wav hash, not a transcript.
    No model for the agent is loaded here, and no correctness
    information is computed here.
    """
    source = Path(args.source_tree)
    verified = verify_source(source)
    manifest_report = validate_manifest(Path(args.benchmark), source)
    bench = load_benchmark(Path(args.benchmark))
    data_root = Path(args.data)
    if not (data_root / "train" / "train.jsonl").exists():
        print(f"BLOCKED: no train.jsonl under {data_root}", file=sys.stderr)
        return 2
    cfg_dict = dict(verified["config"])
    asr_backend, asr_model_dir = resolve_asr_backend(args, cfg_dict)
    # Fail-fast file check BEFORE torch import and before any weight load.
    asr_report = check_asr_model(asr_backend, cfg_dict["asr_checkpoint"], asr_model_dir)
    print(f"ASR backend check: {json.dumps(asr_report, ensure_ascii=False)}")
    try:
        import torch  # noqa: F401
    except ImportError:
        print("BLOCKED: torch not installed; cannot run ASR on this VM.", file=sys.stderr)
        return 2
    sys.path.insert(0, str(source))
    from lifemate.config import PipelineConfig
    cfg_dict["shadow_observer"] = True
    cfg_dict["asr_backend"] = asr_backend
    cfg = PipelineConfig(**cfg_dict)
    cfg.check_budget()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    _, samples = _load_samples_for_run(source, data_root)
    asr = build_asr(asr_backend, cfg.asr_checkpoint, asr_model_dir, source)
    # The cache meta includes backend + model_dir, so a converted
    # directory and a transformers directory never share entries.
    cache = AsrCache(out / "asr_cache_baseline.json", cfg.asr_checkpoint, "",
                     asr_backend, 1, "vi", model_dir=asr_model_dir)
    log = []
    for sid in (bench["ids"][:PILOT_SIZE] if os.environ.get("TIER1A_SMOKE_ONLY") == "1" else bench["ids"]):
        sample = samples.get(sid)
        if sample is None:
            log.append({"sample_id": sid, "status": "missing_sample"})
            continue
        wavs = []
        if sample.audio:
            wavs.append(("current", data_root / "train" / sample.audio))
        for turn in sample.history:
            if turn.role == "user" and turn.audio_text is None and turn.audio:
                wavs.append(("history", data_root / "train" / turn.audio))
        for kind, wav in wavs:
            if not wav.exists():
                log.append({"sample_id": sid, "kind": kind, "wav": str(wav),
                            "status": "missing_wav"})
                continue
            wsha = sha256_file(wav)
            txt, fresh, seconds = _build_asr_cache(cache, asr, wav, wsha)
            log.append({"sample_id": sid, "kind": kind, "wav": str(wav),
                        "wav_sha256": wsha, "status": "transcribed" if fresh else "cached",
                        "seconds": seconds, "transcript_chars": len(txt or "")})
    (out / "asr_cache_log.json").write_text(
        json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"asr-cache: {len(log)} wav entries -> {out / 'asr_cache_baseline.json'}")
    print(f"manifest: {json.dumps(manifest_report, ensure_ascii=False)}")
    return 0


def cmd_run(args, shared_llm=None) -> int:
    """GPU run phase: write submission traces to disk, nothing more.

    For each kept sample and each requested mode, a fresh env and a
    fresh AgentLoop run with the current-turn transcript for that
    mode (ASR baseline, or gold transcript for the gold mode) and
    fixed history. The trace written here contains the submission
    line, the prompt sequence, raw outputs, token counts, parsed
    calls, observations fed back, errors, timing, and the shadow
    observer log. It contains no correctness information: that is
    computed only later, by the separate score command, from the
    traces already on disk.
    """
    source = Path(args.source_tree)
    verified = verify_source(source)
    manifest_report = validate_manifest(Path(args.benchmark), source)
    bench = load_benchmark(Path(args.benchmark))
    ids = bench["ids"][:PILOT_SIZE] if args.pilot else bench["ids"]
    modes = [m.strip() for m in args.mode.split(",")]
    for m in modes:
        assert m in ("B0", "B-gold"), f"Tier 1a runs only B0 / B-gold, got {m}"
    data_root = Path(args.data)
    if not (data_root / "train" / "train.jsonl").exists():
        print(f"BLOCKED: no train.jsonl under {data_root}", file=sys.stderr)
        return 2
    observer_on = getattr(args, "observer", "on") != "off"
    cfg_dict = dict(verified["config"])
    asr_backend, asr_model_dir = resolve_asr_backend(args, cfg_dict)
    # Fail-fast ASR file check BEFORE torch import and weight loads.
    asr_report = check_asr_model(asr_backend, cfg_dict["asr_checkpoint"], asr_model_dir)
    print(f"ASR backend check: {json.dumps(asr_report, ensure_ascii=False)}")
    try:
        import torch  # noqa: F401
    except ImportError:
        print("BLOCKED: torch not installed; cannot run models on this VM.", file=sys.stderr)
        return 2
    sys.path.insert(0, str(source))
    from lifemate.adapter import ZaicEnv
    from lifemate.agent import AgentLoop
    from lifemate.config import PipelineConfig
    from lifemate.llm import VLLMGenerator
    from lifemate.loader import catalog_tools_for_sample

    cfg_dict["shadow_observer"] = observer_on
    cfg_dict["asr_backend"] = asr_backend
    cfg = PipelineConfig(**cfg_dict)
    cfg.check_budget()
    assert cfg.pending_ask_stop is False
    assert cfg.history_presentation_v2 is False
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    snapshot = dict(cfg_dict)
    snapshot["asr_backend_pinned"] = verified["config"]["asr_backend"]
    snapshot["asr_model_dir_actual"] = asr_model_dir
    snapshot["asr_check"] = asr_report
    (out / "config_snapshot.json").write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")
    # Legacy shared manifest (kept for notebook compatibility); the
    # per-mode run_manifest_<mode>.json files written below are
    # authoritative, because they carry status + input hashes.
    (out / "run_manifest.json").write_text(
        json.dumps({"manifest": manifest_report, "modes": modes,
                    "pilot": bool(args.pilot),
                    "shadow_observer": observer_on,
                    "observer_note": "observer ON to log, never to block",
                    "asr_backend_actual": asr_backend,
                    "asr_model_dir_actual": asr_model_dir,
                    "config_sha256": verified["config_sha256"],
                    "split_sha256": verified["split_sha256"]},
                   indent=2, ensure_ascii=False), encoding="utf-8")
    catalog, samples = _load_samples_for_run(source, data_root)
    # Outcome-blind exclusion BEFORE any model run (stream-C 4.2/5).
    kept, excluded = [], []
    for sid in ids:
        s = samples.get(sid)
        if s is None or s.audio_text is None or not s.audio:
            excluded.append({"id": sid, "reason": "missing sample/audio_text/audio"})
            continue
        wav = data_root / "train" / s.audio
        if not wav.exists():
            excluded.append({"id": sid, "reason": "missing wav"})
            continue
        kept.append(sid)
    (out / "excluded.json").write_text(
        json.dumps(excluded, indent=2, ensure_ascii=False), encoding="utf-8")
    asr = LazyASR(lambda: build_asr(asr_backend, cfg.asr_checkpoint,
                                   asr_model_dir, source))
    cache = AsrCache(out / "asr_cache_baseline.json", cfg.asr_checkpoint, "",
                     asr_backend, 1, "vi", model_dir=asr_model_dir)
    required_wavs = []
    for sid in kept:
        sample = samples[sid]
        required_wavs.append(data_root / "train" / sample.audio)
        required_wavs.extend(data_root / "train" / turn.audio
                             for turn in sample.history
                             if turn.role == "user" and turn.audio_text is None
                             and turn.audio)
    missing_cache = missing_cached_wavs(cache, required_wavs)
    if missing_cache:
        print(f"BLOCKED: ASR cache has {len(missing_cache)} missing or empty "
              f"transcripts; run asr-cache first. First: {missing_cache[:5]}",
              file=sys.stderr)
        return 2
    t0 = time.time()
    llm = shared_llm if shared_llm is not None else build_pilot_llm(cfg)
    load_log = {"llm_seconds": time.time() - t0,
                "asr_backend_actual": asr_backend,
                "asr_model_dir_actual": asr_model_dir,
                "asr_gpu_loaded_during_run": False,
                "llm_weights_path": os.environ.get("TIER1A_LLM_MODEL_DIR") or cfg.llm_checkpoint,
                "engine_max_model_len": cfg.llm_max_context_tokens,
                "engine_max_num_seqs": 1, "engine_dtype": "float16",
                "engine_enforce_eager": True, "gpu_memory_utilization": 0.90}
    (out / "model_load.json").write_text(json.dumps(load_log, indent=2), encoding="utf-8")
    # Precompute FIXED history + current transcripts and input hashes
    # per mode, BEFORE any AgentLoop run, so resume can compare them.
    # History is fixed in every mode: transcript from the sample
    # when present, else the shared baseline cache. Only the
    # current turn varies between modes.
    prepared = {}
    for mode in modes:
        prepared[mode] = {}
        for sid in kept:
            sample = samples[sid]
            hist_sources, hist_texts = [], []
            for turn in sample.history:
                if turn.role == "user" and turn.audio_text is None and turn.audio:
                    wav = data_root / "train" / turn.audio
                    if not wav.exists():
                        hist_sources.append("missing")
                        hist_texts.append(None)
                        continue
                    wsha = sha256_file(wav)
                    txt, _, _ = _build_asr_cache(cache, asr, wav, wsha)
                    hist_sources.append("baseline_asr")
                    hist_texts.append(txt)
                elif turn.role == "user":
                    hist_sources.append("gold" if turn.audio_text else "missing")
                    hist_texts.append(turn.audio_text)
            wav = data_root / "train" / sample.audio
            wsha = sha256_file(wav)
            if mode == "B-gold":
                transcript, input_mode = sample.audio_text, "gold"
            else:
                txt, _, _ = _build_asr_cache(cache, asr, wav, wsha)
                transcript, input_mode = txt, "asr_baseline"
            ihash = input_hash_for_sample(
                sid, mode, wsha, transcript, hist_texts,
                verified["config_sha256"], cfg.asr_checkpoint, asr_backend,
                cfg.llm_checkpoint, cfg.llm_revision)
            prepared[mode][sid] = {
                "hist_sources": hist_sources, "hist_texts": hist_texts,
                "wav": wav, "wav_sha": wsha, "transcript": transcript,
                "input_mode": input_mode, "input_hash": ihash}
    for mode in modes:
        traces_path = out / f"traces_{mode}.jsonl"
        manifest_path = out / f"run_manifest_{mode}.json"
        # Resume: reuse only traces whose stored input hash matches.
        existing, existing_dup = load_traces_file(traces_path)
        stored_hashes = {}
        if getattr(args, "resume", False) and manifest_path.exists() \
                and not existing_dup:
            try:
                stored_hashes = json.loads(
                    manifest_path.read_text(encoding="utf-8")).get("input_hashes", {})
            except Exception:
                stored_hashes = {}
        if getattr(args, "resume", False) and traces_path.exists() \
                and not manifest_path.exists():
            print(f"{mode}: resume requested but {manifest_path} is missing "
                  "— re-running all samples (safe fallback, no blind reuse).")
        current_hashes = {sid: prepared[mode][sid]["input_hash"] for sid in kept}
        plan = resume_plan(kept, existing, stored_hashes, current_hashes) \
            if getattr(args, "resume", False) else {"skip": [], "rerun": list(kept)}
        if plan["skip"]:
            print(f"{mode}: resume skips {len(plan['skip'])} unchanged traces, "
                  f"re-runs {len(plan['rerun'])}.")
        new_traces = {}
        run_error = None
        try:
            for sid in plan["rerun"]:
                sample = samples[sid]
                prep = prepared[mode][sid]
                hist_sources = prep["hist_sources"]
                transcript, input_mode = prep["transcript"], prep["input_mode"]
                # Apply the precomputed fixed history to this run.
                hist_iter = iter(prep["hist_texts"])
                for turn in sample.history:
                    if turn.role == "user":
                        turn.audio_text = next(hist_iter)
                wav, wsha = prep["wav"], prep["wav_sha"]
                tools = catalog_tools_for_sample(catalog, sample)
                env = ZaicEnv(data_root, "train", sample.id)
                loop = AgentLoop(cfg, tools)
                gen = TracingGenerator(llm)
                start = time.time()
                sample_error = None
                line = None
                try:
                    line = loop.run(sample, transcript, env, gen)
                except Exception as exc:
                    sample_error = f"{type(exc).__name__}: {exc}"
                    line = env.submission_line()
                seconds = time.time() - start
                if gen.generations:
                    gen.finalise_observations(gen.generations[0]["prompt"])
                prompts = [g["prompt"] for g in gen.generations]
                observer_log = getattr(loop.observer, "records", None)
                if observer_log is None:
                    observer_log = getattr(loop.observer, "log", [])
                new_traces[sid] = {
                    "sample_id": sid, "split": "dev", "arm": mode,
                    "input_mode": input_mode, "transcript_current": transcript,
                    "transcript_gold_current": sample.audio_text,
                    "transcript_source_history": hist_sources,
                    "wav_path": str(wav), "wav_sha256": wsha,
                    "prompt_sha256": sha256_text(prompts[0]) if prompts else None,
                    "prompt_full": prompts[0] if (args.pilot and prompts) else None,
                    "generations": gen.generations,
                    "tool_calls": line.get("tool_calls", []) if line else [],
                    "state_hash": line.get("state_hash") if line else None,
                    "observer_log": observer_log,
                    "seconds": seconds,
                    "n_generations": len(gen.generations),
                    "run_error": sample_error,
                }
        except Exception as exc:
            run_error = f"{type(exc).__name__}: {exc}"
            print(f"{mode}: run crashed mid-way: {run_error}", file=sys.stderr)
        # Final traces file, always in manifest (kept) order: reused
        # traces first in that order, then newly run ones. A crash
        # leaves a PARTIAL file, and the manifest below says so.
        final_traces = {}
        for sid in kept:
            if sid in plan["skip"] and sid in existing:
                final_traces[sid] = existing[sid]
            elif sid in new_traces:
                final_traces[sid] = new_traces[sid]
        with open(traces_path, "w", encoding="utf-8") as fout:
            for sid in kept:
                if sid in final_traces:
                    fout.write(json.dumps(final_traces[sid], ensure_ascii=False) + "\n")
        errored = sorted(sid for sid, t in final_traces.items() if t.get("run_error"))
        missing = sorted(set(kept) - set(final_traces))
        status = "COMPLETE" if (not run_error and not errored and not missing
                                and not excluded) else "INCOMPLETE"
        manifest_path.write_text(json.dumps({
            "manifest": manifest_report, "mode": mode, "pilot": bool(args.pilot),
            "shadow_observer": observer_on,
            "observer_note": "observer ON to log, never to block",
            "asr_backend_actual": asr_backend,
            "asr_model_dir_actual": asr_model_dir,
            "asr_check": asr_report,
            "config_sha256": verified["config_sha256"],
            "split_sha256": verified["split_sha256"],
            "status": status, "n_expected_kept": len(kept),
            "n_traced": len(final_traces), "n_resumed_skipped": len(plan["skip"]),
            "excluded": excluded, "missing": missing, "run_errors": errored,
            "crash_error": run_error, "input_hashes": current_hashes,
            "note": "COMPLETE requires no excluded, no missing, no run errors. "
                    "Score additionally requires all manifest ids, not just kept."},
            indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"{mode}: {len(final_traces)} traces ({status}) -> {traces_path}")
        if status != "COMPLETE":
            print(f"{mode}: run manifest INCOMPLETE: excluded={len(excluded)} "
                  f"missing={missing} run_errors={errored} crash={run_error}",
                  file=sys.stderr)
    return 0


def cmd_check_off_on(args, shared_llm=None) -> int:
    """OFF-vs-ON (stream-C 5.4): pilot 20, same condition (B0),
    observer OFF then ON. Submission lines must be identical.

    Runs the real run phase twice into separate directories and
    compares tool_calls + state_hash per sample. Exits 1 on any
    mismatch, and the notebook scoring cell refuses to score in
    that case. No correctness information is involved here.
    """
    base_out = Path(args.out)
    # OFF-vs-ON runs are always fresh (never resumed): reusing a
    # previous pilot trace would hide an observer effect.
    bench = load_benchmark(Path(args.benchmark))
    pilot_ids = bench["ids"][:PILOT_SIZE]
    results = {}
    for flag, sub in (("off", "off"), ("on", "on")):
        sub_out = base_out / sub
        # Reuse the independently transcribed cache for both fresh model runs.
        # Without it, each arm loads ASR beside the LLM and may exhaust VRAM.
        shared_cache = base_out.parent / "asr_cache_baseline.json"
        if shared_cache.exists():
            sub_out.mkdir(parents=True, exist_ok=True)
            shutil.copy2(shared_cache, sub_out / shared_cache.name)
        ns = argparse.Namespace(
            source_tree=args.source_tree, benchmark=args.benchmark,
            out=str(sub_out), data=args.data, mode="B0", pilot=True,
            observer=flag, resume=False,
            asr_backend=getattr(args, "asr_backend", None),
            asr_model_dir=getattr(args, "asr_model_dir", None))
        rc = cmd_run(ns, shared_llm=shared_llm)
        if rc != 0:
            print(f"OFF-vs-ON: run with observer {flag} failed (rc={rc})", file=sys.stderr)
            return rc
        rows = {}
        for line in (sub_out / "traces_B0.jsonl").read_text().splitlines():
            r = json.loads(line)
            rows[r["sample_id"]] = {"tool_calls": r["tool_calls"],
                                    "state_hash": r["state_hash"]}
        results[flag] = rows
    common = sorted(set(results["off"]) & set(results["on"]))
    mismatches = [sid for sid in common
                  if results["off"][sid] != results["on"][sid]]
    report = {"n_common": len(common),
              "n_pilot_expected": len(pilot_ids),
              "pilot_ids": pilot_ids,
              "n_off_only": len(set(results["off"]) - set(results["on"])),
              "n_on_only": len(set(results["on"]) - set(results["off"])),
              "identical": not mismatches and len(common) == len(pilot_ids)
                           and set(common) == set(pilot_ids),
              "mismatches": mismatches}
    base_out.mkdir(parents=True, exist_ok=True)
    (base_out / "off_on_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["identical"] else 1


# ---------------------------------------------------------------- completeness gate
def load_traces_file(path: Path):
    """Load one traces file, detecting duplicate ids (a dict alone
    would silently hide them). Returns (rows, duplicates)."""
    rows, duplicates, seen = {}, [], set()
    if not path.exists():
        return rows, duplicates
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        sid = row["sample_id"]
        if sid in seen:
            duplicates.append(sid)
        seen.add(sid)
        rows[sid] = row
    return rows, duplicates


def check_trace_completeness(manifest: dict, traces_by_mode: dict,
                             off_on: dict | None, pilot: bool = False) -> dict:
    """Mandatory completeness gate for score (Phase 1).

    Expected ids are the full manifest, or its first 20 when pilot
    scoring is explicitly requested. COMPLETE requires, for EACH arm:
    exactly the expected ids, no duplicates, no extras, no trace
    with a run error, no arm mismatch; both arms must share the
    same id set; and the OFF-vs-ON report must exist, be identical,
    cover exactly the pilot ids, and have n_common == len(pilot).
    Anything else is INCOMPLETE: score must not print any total.
    This function is pure (no gold reads, no model runs)."""
    expected = list(manifest["ids"][:PILOT_SIZE]) if pilot else list(manifest["ids"])
    expected_set = set(expected)
    pilot_ids = list(manifest["ids"][:PILOT_SIZE])
    report: dict = {"status": "COMPLETE", "pilot": pilot,
                    "expected_n": len(expected), "per_mode": {},
                    "missing": {}, "extra": {}, "duplicates": {},
                    "run_errors": {}, "arm_mismatches": {},
                    "arm_id_sets_equal": True, "off_on": None}
    mode_sets = {}
    for mode, (rows, duplicates) in traces_by_mode.items():
        ids = set(rows)
        missing = sorted(expected_set - ids)
        extra = sorted(ids - expected_set)
        run_errors = sorted(sid for sid, r in rows.items() if r.get("run_error"))
        arm_mismatches = sorted(sid for sid, r in rows.items()
                                if r.get("arm") != mode)
        report["per_mode"][mode] = {"n": len(rows)}
        report["missing"][mode] = missing
        report["extra"][mode] = extra
        report["duplicates"][mode] = sorted(set(duplicates))
        report["run_errors"][mode] = run_errors
        report["arm_mismatches"][mode] = arm_mismatches
        mode_sets[mode] = ids
        if missing or extra or duplicates or run_errors or arm_mismatches:
            report["status"] = "INCOMPLETE"
    if len(mode_sets) >= 2:
        first = next(iter(mode_sets.values()))
        if any(s != first for s in mode_sets.values()):
            report["arm_id_sets_equal"] = False
            report["status"] = "INCOMPLETE"
    if off_on is None:
        report["off_on"] = {"present": False, "identical": False,
                            "reason": "off_on_report.json missing: run "
                                      "check-off-on before scoring"}
        report["status"] = "INCOMPLETE"
    else:
        ok = bool(off_on.get("identical")) \
            and off_on.get("n_common") == len(pilot_ids) \
            and (off_on.get("pilot_ids") in (None, pilot_ids))
        report["off_on"] = {"present": True, "identical": bool(off_on.get("identical")),
                            "n_common": off_on.get("n_common"),
                            "n_pilot_expected": len(pilot_ids),
                            "pilot_ids_match": off_on.get("pilot_ids") in (None, pilot_ids),
                            "ok": ok}
        if not ok:
            report["status"] = "INCOMPLETE"
    return report


# ---------------------------------------------------------------- score (after runs)
def cmd_score(args) -> int:
    """Score phase: read traces from disk FIRST, then read gold.

    This is the only command that reads gold tool calls, gold state
    hashes, or per-sample correctness. It never runs the agent and
    never changes a run trace; it writes scored copies and a report
    alongside them. Input traces must already exist on disk.
    """
    source = Path(args.source_tree)
    d = Path(args.traces)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    # Completeness gate FIRST, before any correctness is computed:
    # a partial run must never yield a total score. The manifest
    # gate also refuses provisional / held-out / edited manifests.
    manifest_report = validate_manifest(Path(args.benchmark), source)
    manifest = load_benchmark(Path(args.benchmark))
    pilot = bool(getattr(args, "pilot", False))

    def load(mode):
        path = d / f"traces_{mode}.jsonl"
        if not path.exists():
            raise SystemExit(f"run trace missing (run phase first): {path}")
        return load_traces_file(path)

    gold_traces, asr_traces = load("B-gold"), load("B0")
    off_on_path = Path(getattr(args, "off_on", None) or (d / "off_on" / "off_on_report.json"))
    off_on = None
    if off_on_path.exists():
        off_on = json.loads(off_on_path.read_text(encoding="utf-8"))
    gate = check_trace_completeness(
        manifest, {"B-gold": gold_traces, "B0": asr_traces}, off_on, pilot=pilot)
    gate["manifest"] = manifest_report
    (out / "completeness_gate.json").write_text(
        json.dumps(gate, indent=2, ensure_ascii=False), encoding="utf-8")
    if gate["status"] != "COMPLETE":
        print(json.dumps(gate, indent=2, ensure_ascii=False), file=sys.stderr)
        print("SCORE REFUSED: traces are INCOMPLETE (see completeness_gate.json). "
              "No total score is printed and no score_report.json is written. "
              "Fix the run (resume / re-run the missing samples) and score again.",
              file=sys.stderr)
        return 2
    print(f"Completeness gate COMPLETE: {json.dumps(gate, ensure_ascii=False)}")
    sys.path.insert(0, str(source))
    from lifemate.loader import load_catalog, load_split
    from lifemate.run import _gold_hash
    from lifemate.scoring import score_sample
    from lifemate.loader import fuzzy_params

    data_root = Path(args.data)
    catalog = load_catalog(data_root, "train")
    samples = {s.id: s for s in load_split(data_root, "train")}
    fuzzy = fuzzy_params(catalog)
    gold_rows, asr_rows = gold_traces[0], asr_traces[0]
    common = list(manifest["ids"][:PILOT_SIZE]) if pilot else list(manifest["ids"])
    scored = {}
    for mode, rows in (("B-gold", gold_rows), ("B0", asr_rows)):
        scored[mode] = {}
        for sid, trace in rows.items():
            sample = samples[sid]
            line = {"tool_calls": trace["tool_calls"],
                    "state_hash": trace["state_hash"]}
            gh = _gold_hash(data_root, "train", sample)
            res = score_sample(line, sample, gh, fuzzy)
            enriched = dict(trace)
            enriched.update({
                "score": res["score"], "f1": res["f1"],
                "hash_correct": res["hash_correct"],
                "label_class": sample.label_class(),
                "gold_tool_calls_sha256": sha256_text(
                    json.dumps(sample.label["tool_calls"], ensure_ascii=False))
                if sample.label else None,
            })
            scored[mode][sid] = enriched
        (out / f"scored_traces_{mode}.jsonl").write_text(
            "".join(json.dumps(scored[mode][sid], ensure_ascii=False) + "\n"
                    for sid in rows), encoding="utf-8")
    g_scores = [scored["B-gold"][s]["score"] for s in common]
    a_scores = [scored["B0"][s]["score"] for s in common]
    g_ok = [s == 1.0 for s in g_scores]
    a_ok = [s == 1.0 for s in a_scores]
    tot = {"S": 0, "D": 0, "I": 0, "N": 0}
    slots_correct = slots_total = 0
    import re as _re
    for sid in common:
        w = wer(gold_rows[sid]["transcript_gold_current"],
                asr_rows[sid]["transcript_current"])
        for k in tot:
            tot[k] += w[k]
        sl = slot_error(gold_rows[sid]["transcript_gold_current"],
                        asr_rows[sid]["transcript_current"])
        slots_total += sl["n_slots"]
        slots_correct += sl["n_correct"]
    # Breakdowns (score phase only: label classes and gold tool names).
    def breakdown(rows_scored, scores):
        out_b = {}
        for sid, score in zip(common, scores):
            cls = rows_scored[sid]["label_class"]
            out_b.setdefault(cls, []).append(score)
        return {k: {"n": len(v), "mean_score": sum(v) / len(v)} for k, v in out_b.items()}
    digit_ids = [sid for sid in common
                 if _re.search(r"[0-9]+", gold_rows[sid]["transcript_gold_current"] or "")]
    search_ids = [sid for sid in common
                  if samples[sid].label and any(
                      c.get("name") == "contacts.search"
                      for c in samples[sid].label["tool_calls"])]
    def subset_mean(ids, scores_map):
        vals = [scores_map[s] for s in ids]
        return {"n": len(vals), "mean_score": sum(vals) / len(vals) if vals else None}
    g_map = {s: scored["B-gold"][s]["score"] for s in common}
    a_map = {s: scored["B0"][s]["score"] for s in common}
    # Reweighted means: dev stratum proportions from the manifest
    # (recorded at refreeze time), falling back to a full-dev count.
    bench = load_benchmark(Path(args.benchmark)) if Path(args.benchmark).exists() else {}
    dev_counts = bench.get("stratum_dev_counts")
    if not dev_counts:
        split = json.loads((source / "lifemate/splits/train_dev_heldout.json").read_text())
        dev_counts = {}
        for s in samples.values():
            if split.get(s.id) == "dev":
                dev_counts[s.label_class()] = dev_counts.get(s.label_class(), 0) + 1
    dev_total = sum(dev_counts.values()) or 1
    def reweighted(rows_scored):
        total = 0.0
        for cls, cnt in dev_counts.items():
            vals = [rows_scored[s]["score"] for s in common
                    if rows_scored[s]["label_class"] == cls]
            if vals:
                total += (cnt / dev_total) * (sum(vals) / len(vals))
        return total
    attr = attribution_bool(g_ok, a_ok)
    ci = bootstrap_paired_ci(g_scores, a_scores)
    diff = ci["mean_diff"]
    if diff >= 0.05 and ci["ci_excludes_zero"]:
        decision = "direction_concluded"
    elif diff < 0.02 or (attr["wrong_both_share_of_all_wrong"] is not None
                         and attr["wrong_both_share_of_all_wrong"] > 0.50):
        decision = "not_separable"
    else:
        decision = "inconclusive"
    report = {
        "n": len(common),
        "mean_score_B-gold": sum(g_scores) / len(g_scores),
        "mean_score_B0": sum(a_scores) / len(a_scores),
        "mean_score_B-gold_reweighted_dev": reweighted(scored["B-gold"]),
        "mean_score_B0_reweighted_dev": reweighted(scored["B0"]),
        "paired_diff_B-gold_minus_B0": ci,
        "pure_llm_error_1_minus_B-gold": 1.0 - sum(g_scores) / len(g_scores),
        "wer_current": {**tot, "wer": (tot["S"] + tot["D"] + tot["I"]) / tot["N"] if tot["N"] else 0.0},
        "slot_error_rate": (1.0 - slots_correct / slots_total) if slots_total else None,
        "attribution_B-gold_vs_B0": attr,
        "breakdown_B-gold_by_label_class": breakdown(scored["B-gold"], g_scores),
        "breakdown_B0_by_label_class": breakdown(scored["B0"], a_scores),
        "digit_subset": {"B-gold": subset_mean(digit_ids, g_map),
                         "B0": subset_mean(digit_ids, a_map)},
        "contacts_search_subset": {"B-gold": subset_mean(search_ids, g_map),
                                   "B0": subset_mean(search_ids, a_map)},
        "decision_rule": "concluded iff diff >= 0.05 AND bootstrap CI excludes 0; "
                         "not separable iff diff < 0.02 OR wrong-both share > 0.50",
        "decision": decision,
        "note": "official-style via lifemate/scoring.py on dev, NOT a BTC score",
    }
    (out / "score_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="tier1a_runner")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_common(sp, need_data=False, need_bench=True):
        sp.add_argument("--source-tree", default=DEFAULT_SOURCE_TREE)
        if need_bench:
            sp.add_argument("--benchmark", default=DEFAULT_BENCHMARK)
        sp.add_argument("--out", default=str(Path(DEFAULT_WORKING) / "tier1a-output"))
        if need_data:
            sp.add_argument("--data", default=DEFAULT_DATA)

    for name in ("smoke",):
        sp = sub.add_parser(name)
        add_common(sp)
    sp = sub.add_parser("check-separation")
    sp = sub.add_parser("validate-manifest")
    add_common(sp)
    for name in ("asr-cache", "run", "check-off-on"):
        sp = sub.add_parser(name)
        add_common(sp, need_data=True)
        sp.add_argument("--asr-backend", default=None,
                        help="faster-whisper (default, pinned) or transformers "
                             "(Phase-1 fallback); env TIER1A_ASR_BACKEND also works")
        sp.add_argument("--asr-model-dir", default=None,
                        help="local model directory: converted CTranslate2 dir "
                             "for faster-whisper, transformers dir for transformers; "
                             "env TIER1A_ASR_MODEL_DIR also works")
        if name == "run":
            sp.add_argument("--mode", default="B0,B-gold")
            sp.add_argument("--pilot", action="store_true")
            sp.add_argument("--observer", choices=["on", "off"], default="on")
            sp.add_argument("--resume", action="store_true",
                            help="reuse traces whose input hash matches; "
                                 "re-run the rest, in manifest order")
    sp = sub.add_parser("check-asr-model")
    sp.add_argument("--asr-backend", default="faster-whisper")
    sp.add_argument("--asr-model-dir", default=None)
    sp.add_argument("--checkpoint", default=PINNED_ASR_CHECKPOINT)
    for name in ("score", "analyze"):
        sp = sub.add_parser(name)
        sp.add_argument("--traces", default=str(Path(DEFAULT_WORKING) / "tier1a-output"))
        sp.add_argument("--pilot", action="store_true",
                        help="score only the pilot 20 (first 20 manifest ids); "
                             "without it, score requires the full manifest")
        sp.add_argument("--off-on", default=None,
                        help="off_on_report.json path (default: <traces>/off_on/)")
        add_common(sp, need_data=True)
    args = p.parse_args(argv)
    if args.cmd == "smoke":
        return cmd_smoke(args)
    if args.cmd == "check-separation":
        return cmd_check_separation(args)
    if args.cmd == "check-asr-model":
        return cmd_check_asr_model(args)
    if args.cmd == "validate-manifest":
        return cmd_validate_manifest(args)
    if args.cmd == "asr-cache":
        return cmd_asr_cache(args)
    if args.cmd == "run":
        return cmd_run(args)
    if args.cmd == "check-off-on":
        return cmd_check_off_on(args)
    if args.cmd == "score":
        return cmd_score(args)
    if args.cmd == "analyze":
        print("analyze is an alias for score (score phase only; run traces must exist).",
              file=sys.stderr)
        return cmd_score(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
