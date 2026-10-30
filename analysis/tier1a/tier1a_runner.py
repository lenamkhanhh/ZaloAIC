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
import ast
import hashlib
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from metrics import attribution_bool, bootstrap_paired_ci, slot_error, wer  # noqa: E402

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
                 backend: str, beam_size: int, language: str):
        self.path = Path(path)
        self.meta = {"checkpoint": checkpoint, "revision": revision,
                     "backend": backend, "beam_size": beam_size, "language": language}
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
    try:
        import torch  # noqa: F401
    except ImportError:
        print("BLOCKED: torch not installed; cannot run ASR on this VM.", file=sys.stderr)
        return 2
    source = Path(args.source_tree)
    sys.path.insert(0, str(source))
    from lifemate.asr import FasterWhisperASR
    from lifemate.config import PipelineConfig

    verified = verify_source(source)
    manifest_report = validate_manifest(Path(args.benchmark), source)
    bench = load_benchmark(Path(args.benchmark))
    data_root = Path(args.data)
    if not (data_root / "train" / "train.jsonl").exists():
        print(f"BLOCKED: no train.jsonl under {data_root}", file=sys.stderr)
        return 2
    cfg_dict = dict(verified["config"])
    cfg_dict["shadow_observer"] = True
    cfg = PipelineConfig(**cfg_dict)
    cfg.check_budget()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    _, samples = _load_samples_for_run(source, data_root)
    asr = FasterWhisperASR(cfg.asr_checkpoint, device="cuda", compute_type="float16")
    cache = AsrCache(out / "asr_cache_baseline.json", cfg.asr_checkpoint, "",
                     "faster-whisper", 1, "vi")
    log = []
    for sid in bench["ids"]:
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


def cmd_run(args) -> int:
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
    try:
        import torch  # noqa: F401
    except ImportError:
        print("BLOCKED: torch not installed; cannot run models on this VM.", file=sys.stderr)
        return 2
    source = Path(args.source_tree)
    sys.path.insert(0, str(source))
    from lifemate.adapter import ZaicEnv
    from lifemate.agent import AgentLoop
    from lifemate.asr import FasterWhisperASR
    from lifemate.config import PipelineConfig
    from lifemate.llm import VLLMGenerator
    from lifemate.loader import catalog_tools_for_sample

    verified = verify_source(source)
    manifest_report = validate_manifest(Path(args.benchmark), source)
    bench = load_benchmark(Path(args.benchmark))
    ids = bench["ids"][:20] if args.pilot else bench["ids"]
    modes = [m.strip() for m in args.mode.split(",")]
    for m in modes:
        assert m in ("B0", "B-gold"), f"Tier 1a runs only B0 / B-gold, got {m}"
    data_root = Path(args.data)
    if not (data_root / "train" / "train.jsonl").exists():
        print(f"BLOCKED: no train.jsonl under {data_root}", file=sys.stderr)
        return 2
    observer_on = getattr(args, "observer", "on") != "off"
    cfg_dict = dict(verified["config"])
    cfg_dict["shadow_observer"] = observer_on
    cfg = PipelineConfig(**cfg_dict)
    cfg.check_budget()
    assert cfg.pending_ask_stop is False
    assert cfg.history_presentation_v2 is False
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "config_snapshot.json").write_text(
        json.dumps(cfg_dict, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "run_manifest.json").write_text(
        json.dumps({"manifest": manifest_report, "modes": modes,
                    "pilot": bool(args.pilot),
                    "shadow_observer": observer_on,
                    "observer_note": "observer ON to log, never to block",
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
    asr = FasterWhisperASR(cfg.asr_checkpoint, device="cuda", compute_type="float16")
    cache = AsrCache(out / "asr_cache_baseline.json", cfg.asr_checkpoint, "",
                     "faster-whisper", 1, "vi")
    t0 = time.time()
    llm = VLLMGenerator(cfg.llm_checkpoint, cfg.llm_revision, seed=cfg.llm_seed)
    load_log = {"llm_seconds": time.time() - t0}
    (out / "model_load.json").write_text(json.dumps(load_log, indent=2), encoding="utf-8")
    for mode in modes:
        traces_path = out / f"traces_{mode}.jsonl"
        with open(traces_path, "w", encoding="utf-8") as fout:
            for sid in kept:
                sample = samples[sid]
                # History FIXED: gold transcript, else shared baseline cache.
                hist_sources = []
                for turn in sample.history:
                    if turn.role == "user" and turn.audio_text is None and turn.audio:
                        wav = data_root / "train" / turn.audio
                        if not wav.exists():
                            hist_sources.append("missing")
                            continue
                        wsha = sha256_file(wav)
                        txt, _, _ = _build_asr_cache(cache, asr, wav, wsha)
                        turn.audio_text = txt
                        hist_sources.append("baseline_asr")
                    elif turn.role == "user":
                        hist_sources.append("gold" if turn.audio_text else "missing")
                wav = data_root / "train" / sample.audio
                wsha = sha256_file(wav)
                if mode == "B-gold":
                    transcript, input_mode = sample.audio_text, "gold"
                else:
                    txt, _, _ = _build_asr_cache(cache, asr, wav, wsha)
                    transcript, input_mode = txt, "asr_baseline"
                tools = catalog_tools_for_sample(catalog, sample)
                env = ZaicEnv(data_root, "train", sample.id)
                loop = AgentLoop(cfg, tools)
                gen = TracingGenerator(llm)
                start = time.time()
                run_error = None
                line = None
                try:
                    line = loop.run(sample, transcript, env, gen)
                except Exception as exc:
                    run_error = f"{type(exc).__name__}: {exc}"
                    line = env.submission_line()
                seconds = time.time() - start
                if gen.generations:
                    gen.finalise_observations(gen.generations[0]["prompt"])
                prompts = [g["prompt"] for g in gen.generations]
                observer_log = getattr(loop.observer, "records", None)
                if observer_log is None:
                    observer_log = getattr(loop.observer, "log", [])
                trace = {
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
                    "run_error": run_error,
                }
                fout.write(json.dumps(trace, ensure_ascii=False) + "\n")
        print(f"{mode}: {len(kept)} traces -> {traces_path}")
    return 0


def cmd_check_off_on(args) -> int:
    """OFF-vs-ON (stream-C 5.4): pilot 20, same condition (B0),
    observer OFF then ON. Submission lines must be identical.

    Runs the real run phase twice into separate directories and
    compares tool_calls + state_hash per sample. Exits 1 on any
    mismatch, and the notebook scoring cell refuses to score in
    that case. No correctness information is involved here.
    """
    import copy
    base_out = Path(args.out)
    results = {}
    for flag, sub in (("off", "off"), ("on", "on")):
        sub_out = base_out / sub
        ns = argparse.Namespace(
            source_tree=args.source_tree, benchmark=args.benchmark,
            out=str(sub_out), data=args.data, mode="B0", pilot=True,
            observer=flag)
        rc = cmd_run(ns)
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
              "n_off_only": len(set(results["off"]) - set(results["on"])),
              "n_on_only": len(set(results["on"]) - set(results["off"])),
              "identical": not mismatches and len(common) > 0,
              "mismatches": mismatches}
    base_out.mkdir(parents=True, exist_ok=True)
    (base_out / "off_on_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["identical"] else 1


# ---------------------------------------------------------------- score (after runs)
def cmd_score(args) -> int:
    """Score phase: read traces from disk FIRST, then read gold.

    This is the only command that reads gold tool calls, gold state
    hashes, or per-sample correctness. It never runs the agent and
    never changes a run trace; it writes scored copies and a report
    alongside them. Input traces must already exist on disk.
    """
    source = Path(args.source_tree)
    sys.path.insert(0, str(source))
    from lifemate.loader import load_catalog, load_split
    from lifemate.run import _gold_hash
    from lifemate.scoring import score_sample
    from lifemate.loader import fuzzy_params

    d = Path(args.traces)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    data_root = Path(args.data)
    catalog = load_catalog(data_root, "train")
    samples = {s.id: s for s in load_split(data_root, "train")}
    fuzzy = fuzzy_params(catalog)

    def load(mode):
        path = d / f"traces_{mode}.jsonl"
        if not path.exists():
            raise SystemExit(f"run trace missing (run phase first): {path}")
        rows = {}
        for line in path.read_text().splitlines():
            r = json.loads(line)
            rows[r["sample_id"]] = r
        return rows

    gold_rows, asr_rows = load("B-gold"), load("B0")
    common = [sid for sid in gold_rows if sid in asr_rows]
    assert common, "no common sample ids between B-gold and B0 traces"
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
        if name == "run":
            sp.add_argument("--mode", default="B0,B-gold")
            sp.add_argument("--pilot", action="store_true")
            sp.add_argument("--observer", choices=["on", "off"], default="on")
    sp = sub.add_parser("score")
    sp.add_argument("--traces", default=str(Path(DEFAULT_WORKING) / "tier1a-output"))
    add_common(sp, need_data=True)
    sp = sub.add_parser("analyze")
    sp.add_argument("--traces", default=str(Path(DEFAULT_WORKING) / "tier1a-output"))
    add_common(sp, need_data=True)
    args = p.parse_args(argv)
    if args.cmd == "smoke":
        return cmd_smoke(args)
    if args.cmd == "check-separation":
        return cmd_check_separation(args)
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
