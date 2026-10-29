#!/usr/bin/env python3
"""Validator for SFT prototype trajectories (Thread B, validator fixes).

Fixes Codex-audited bugs in the previous validator (see
validator_fix_notes.md for repro before/after):

  BUG 2 — the old validate_example trusted the artifact: it took
  base_prompt = steps[0]["prompt"] and rebuilt later prompts from it,
  so a forged base was self-consistent and passed. The new validator
  NEVER trusts artifact prompts: it rebuilds the expected base prompt
  from the original sample (train.jsonl) + catalog + the pinned
  runtime (a2e832b agent.py build_base_prompt/render_observation_prompt
  + baseline.json config suffixes) and compares every step prompt
  exactly against the rebuilt prefix. Any change to context, current
  transcript, history, catalog, or config suffix changes the rebuilt
  base and fails. The artifact's declared contract must equal the
  pinned contract (a2e832b-text) or the example fails contract_mismatch.

  BUG 3 — the old replay loop only tracked env.validate failures and
  never checked env.call outcomes, so a gold call returning ok True /
  done False passed with replay_ok=true and hash_match=true. The new
  validator classifies EVERY replayed result (see classify_outcome):
  non-dict -> result_not_dict; ok not exactly True -> ok_false;
  ok True + done False -> not_done; otherwise success (done absent
  is success, which is the read case). In TRAINING mode any not_done
  fails the example. In EVALUATION mode not_done is reported as an
  anomaly and the verdict is decided by fidelity checks only.
  hash_match NEVER rescues a failing trajectory, but a claimed
  state_hash / executed_calls / not_done_steps that disagrees with
  the independent replay IS a metadata failure (the artifact is
  inconsistent with its own recorded trajectory).

  MANIFEST + MODE: with --manifest/--part, the sample must be in the
  manifest assignment and its part must equal the requested part.
  Training mode (default): train_eligible False -> fail
  not_train_eligible. Evaluation mode: eligibility is SKIPPED (it
  bars training only, never evaluation). CLI training mode without
  --manifest exits 2 with a clear error; function-level calls with
  manifest=None report membership/eligibility as SKIPPED, never as
  a silent pass or fail.

  TOKEN CHECKS (independent implementation; this file NEVER imports
  builder token helpers): rendered fields are rendered_prompt,
  rendered_prompt_token_ids, target_token_ids, input_ids, labels,
  eos_token_id, sequence_tokens (= len(input_ids)); prompt_token_ids
  means the RENDERED ids. The validator recomputes rendered ids by
  calling apply_chat_template directly (validator-owned tokenizer
  subprocess, one batch for all examples) and compares every field
  exactly, plus labels/mask/EOS/budget checks. Legacy artifacts
  without rendered fields get token checks SKIPPED with a reason;
  other checks still decide the verdict. Mixed rendered/legacy steps
  fail as inconsistent.

What this validator still does NOT do:
  * state_hash is a secondary signal: hash_match=true never overrides
    a failure, and hash_match=false alone never fails (reads/asks do
    not change state). Only a CLAIMED state_hash that disagrees with
    the independent replay fails, as metadata inconsistency.
  * Guard diagnostic: guard_fired flags are recorded verbatim and
    NEVER change the verdict (the guard is not an oracle for data).
  * Replay via env.call verifies simulator transitions only, NOT the
    whole AgentLoop (prompt rendering inside the loop, validation
    retries, loop guard, grounding, parser inside the loop are
    covered by the runtime-rebuild check and the parser round-trip,
    not by this replay).
  * Token rendering reference is runtime llm._render (single user
    message + add_generation_prompt, encode with
    add_special_tokens=False). Proving that separate prompt/target
    encoding equals the full training serialization is Thread A's
    scope; this validator checks artifacts against the _render
    reference, nothing else.

Usage:
  python3 sft_prototype_validator.py --output sft_prototype_local.json \
      --train-jsonl <train.jsonl> --data-root <train+public_test> \
      --catalog <train_tools_catalog.json> \
      --manifest <inner_split_seed1337_v2.json> --part inner_train \
      [--mode training|evaluation] [--runtime-dir <worktree>/lifemate] \
      [--tokenizer-python ~/workspace/zaic-test-venv/bin/python]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import unicodedata
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sft_prototype_builder import (  # noqa: E402
    CONTRACT, build_steps, canon_call, canon_call_key)

STOP_TARGET = CONTRACT["stop_target"]
PINNED_CONTRACT_NAME = "a2e832b-text"
PINNED_EOS_TOKEN_ID = 151645
PINNED_MAX_CONTEXT_TOKENS = 16384
PINNED_MAX_NEW_TOKENS = 512
DEFAULT_RUNTIME_DIR = "/home/hatch/workspace/zaic-branch-a2e832b/lifemate"
RENDERED_FIELDS = ("rendered_prompt", "rendered_prompt_token_ids",
                   "target_token_ids", "input_ids", "labels")
# Fields that ONLY exist on rendered artifacts (target_token_ids also
# exists on legacy artifacts as the raw target encoding, so it must
# NOT count toward rendered detection -- otherwise every legacy
# artifact looks "mixed" and fails instead of SKIPPING).
RENDERED_ONLY_FIELDS = ("rendered_prompt", "rendered_prompt_token_ids",
                        "input_ids", "labels")


def _rendered_status(steps: list) -> str:
    """Classify token-field presence: "full" (every step has all
    rendered fields), "legacy" (no step has any rendered-only field),
    or "mixed" (anything in between)."""
    if not steps:
        return "legacy"
    full = [all(f in st for f in RENDERED_FIELDS) for st in steps]
    if all(full):
        return "full"
    any_rendered = [any(f in st for f in RENDERED_ONLY_FIELDS) for st in steps]
    if not any(any_rendered):
        return "legacy"
    return "mixed"


# ---------------------------------------------------------------------------
# Scoring replicas (read-only copies of a2e832b lifemate/scoring.py).
# ---------------------------------------------------------------------------
def _tokens(text: str) -> list:
    text = unicodedata.normalize("NFC", str(text)).lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return text.split()


def token_f1(a: str, b: str) -> float:
    ta, tb = Counter(_tokens(a)), Counter(_tokens(b))
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    inter = sum((ta & tb).values())
    if inter == 0:
        return 0.0
    precision = inter / sum(ta.values())
    recall = inter / sum(tb.values())
    return 2 * precision * recall / (precision + recall)


def parse_model_output(text: str):
    """Replica of a2e832b llm.parse_model_output. Returns the call dict,
    or None for a stop signal; raises ValueError for garbage."""
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
    if isinstance(obj, dict) and (obj.get("stop") is True or
           (obj.get("name") == "stop" and not obj.get("arguments"))):
        return None
    return obj


def compact(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


# ---------------------------------------------------------------------------
# Replay outcome contract (pure classifier; unit-tested directly).
# ---------------------------------------------------------------------------
def classify_outcome(result):
    """Classify one env.call result. Returns (status, reason).
    Statuses: success | not_done | ok_false | result_not_dict.
    done absent is success (the read case): only an explicit
    done=False alongside ok True is not_done. ok must be exactly
    True; missing/False/non-True is ok_false, never a silent pass."""
    if not isinstance(result, dict):
        return ("result_not_dict", "replay result is not a dict")
    if result.get("ok") is not True:
        return ("ok_false", "result ok is not exactly True")
    if result.get("done") is False:
        return ("not_done", "ok True but done False: call did not complete")
    return ("success", "ok True and done is not False")


# ---------------------------------------------------------------------------
# Core validation (works on step lists; no env needed except replay mode).
# UNCHANGED from the previous validator: old tests import this directly.
# ---------------------------------------------------------------------------
def validate_steps(base_prompt: str, steps: list, gold_calls: list,
                   gold_final_state, fuzzy_by_tool: dict,
                   replay_results: list | None = None,
                   guard_flags: list | None = None) -> dict:
    """Validate one trajectory. Returns a report dict; 'verdict' is
    'pass' iff every PRIMARY check passes. hash_match and guard
    diagnostics never affect the verdict."""
    failures = []
    notes = []

    calls_from_steps = [st["call"] for st in steps if st["call"] is not None]
    stop_steps = [i for i, st in enumerate(steps) if st["call"] is None]

    # --- structure: stop position.
    if not gold_calls:
        if not (len(steps) == 1 and len(stop_steps) == 1):
            failures.append("empty sample must have exactly one step, the stop step")
    elif gold_calls[-1]["name"] == "sys.ask_missing_info":
        if stop_steps:
            failures.append("ask-terminated trajectory must have no trailing stop step")
    else:
        if stop_steps != [len(steps) - 1]:
            failures.append("exactly one stop step required, at the end")

    # --- ask position.
    ask_idx = [i for i, c in enumerate(calls_from_steps)
               if c["name"] == "sys.ask_missing_info"]
    if ask_idx and ask_idx != [len(calls_from_steps) - 1]:
        failures.append("ask_not_last")

    # --- sequence fidelity (PRIMARY).
    if [canon_call_key(c) for c in calls_from_steps] != \
            [canon_call_key(c) for c in gold_calls]:
        failures.append("sequence_mismatch")

    # --- argument fidelity (PRIMARY): exact except fuzzy params.
    for sub, gold in zip(calls_from_steps, gold_calls):
        if sub["name"] != gold["name"]:
            continue  # already counted in sequence_mismatch
        s_args, g_args = sub.get("arguments") or {}, gold.get("arguments") or {}
        if set(s_args.keys()) != set(g_args.keys()):
            failures.append(f"arg_keys_mismatch:{sub['name']}")
            continue
        fuzzy = fuzzy_by_tool.get(sub["name"], set())
        for key, g_val in g_args.items():
            s_val = s_args[key]
            if key in fuzzy:
                if token_f1(str(s_val), str(g_val)) <= 0.6:
                    failures.append(f"fuzzy_arg_below_threshold:{sub['name']}.{key}")
            elif s_val != g_val:
                failures.append(f"arg_mismatch:{sub['name']}.{key}")

    # --- prompt rebuild equality (PRIMARY): rebuild from base +
    # earlier (call, result) pairs and require exact equality.
    # The builder's step list does not carry results per step in the
    # output file's step dicts, so rebuild uses replay_results when
    # supplied; otherwise rebuild from the recorded calls + results
    # passed by the caller (tests) via replay_results.
    if replay_results is not None:
        rebuilt = build_steps(base_prompt, calls_from_steps, replay_results)
        # build_steps appends a trailing stop step for non-ask endings;
        # compare only the call steps' prompts and the stop prompt.
        for i, st in enumerate(steps):
            if i < len(rebuilt) and rebuilt[i]["prompt"] != st["prompt"]:
                failures.append(f"prompt_rebuild_mismatch:step {i}")
            if i < len(rebuilt) and rebuilt[i]["target"] != st["target"]:
                failures.append(f"target_rebuild_mismatch:step {i}")
        if len(rebuilt) != len(steps):
            failures.append("step_count_mismatch_after_rebuild")

    # --- leakage (PRIMARY): full JSON strings only.
    results = replay_results if replay_results is not None else []
    result_jsons = [compact(r) for r in results if isinstance(r, dict)]
    final_json = compact(gold_final_state) if gold_final_state is not None else None
    for i, st in enumerate(steps):
        prompt = st["prompt"]
        for j in range(i, len(result_jsons)):
            rj = result_jsons[j]
            if len(rj) > 2 and rj in prompt:
                failures.append(f"leakage:result[{j}] in prompt[{i}]")
        if final_json is not None and len(final_json) > 2 and final_json in prompt:
            failures.append(f"leakage:final_state in prompt[{i}]")
        # Target-leakage check applies ONLY to call steps. The stop
        # target '{"stop":true}' is exempt BY DESIGN: the instruction
        # text itself (instruction line + ACTION_POLICY lines 1 and 6)
        # contains that exact literal, so its presence in the prompt
        # is the format specification, not a leaked answer. A call
        # target in its own prompt is always a failure.
        if st["call"] is not None and st["target"] in prompt:
            failures.append(f"leakage:target in prompt[{i}]")

    # --- parser round-trip (PRIMARY).
    for i, st in enumerate(steps):
        try:
            parsed = parse_model_output(st["target"])
        except ValueError as exc:
            failures.append(f"parser_error:step {i}: {exc}")
            continue
        if st["call"] is None:
            if parsed is not None:
                failures.append(f"parser_stop_mismatch:step {i}")
        else:
            if parsed is None or canon_call_key(parsed) != canon_call_key(st["call"]):
                failures.append(f"parser_call_mismatch:step {i}")

    # --- guard diagnostic (NEVER verdict-determining).
    guard_diag = "not_run"
    if guard_flags is not None:
        guard_diag = {"fired_steps": [i for i, f in enumerate(guard_flags) if f]}
        if guard_diag["fired_steps"]:
            notes.append("guard_fired_on_gold_diagnostic (not a data error): "
                         f"steps {guard_diag['fired_steps']}")

    return {
        "verdict": "pass" if not failures else "fail",
        "failures": failures,
        "notes": notes,
        "guard_diagnostic": guard_diag,
        "n_steps": len(steps),
        "n_calls": len(calls_from_steps),
    }


# ---------------------------------------------------------------------------
# Runtime rebuild (Bug 2 fix): the artifact is never the source of truth
# for its own prompts. Base + step prefixes are rebuilt from the original
# sample + catalog + the pinned runtime worktree (read-only import).
# ---------------------------------------------------------------------------
def _load_runtime(runtime_dir: str, zaic_tools_dir: str):
    """Import pinned runtime functions. Raises RuntimeError on any
    problem (fail-closed: without the runtime the base cannot be
    rebuilt, so the example cannot pass)."""
    rdir = Path(runtime_dir)
    parent = str(rdir.parent)
    if parent not in sys.path:
        sys.path.insert(0, parent)
    if zaic_tools_dir and zaic_tools_dir not in sys.path:
        sys.path.insert(0, zaic_tools_dir)
    try:
        import lifemate.agent as agent_mod
        from lifemate.agent import build_base_prompt as rt_base
        from lifemate.agent import render_observation_prompt as rt_obs
        from lifemate.loader import Sample, Turn, catalog_tools_for_sample
    except Exception as exc:
        raise RuntimeError(f"runtime import failed: {exc}") from exc
    mod_file = str(getattr(agent_mod, "__file__", ""))
    if not mod_file.startswith(str(rdir)):
        raise RuntimeError(
            f"runtime import resolved to wrong module: {mod_file} "
            f"(expected under {rdir})")
    cfg_path = rdir / "configs" / "baseline.json"
    if not cfg_path.is_file():
        raise RuntimeError(f"runtime baseline config missing: {cfg_path}")
    config = json.load(open(cfg_path, encoding="utf-8"))
    return rt_base, rt_obs, Sample, Turn, catalog_tools_for_sample, config


def _config_suffix_lines(config: dict) -> list:
    """Baseline config suffix lines, in AgentLoop.run append order."""
    lines = []
    if config.get("selective_reads"):
        lines.append("Read only to resolve a missing entity or precondition; "
                     "reuse still-valid observations.")
    if not config.get("verification_read_after_write"):
        lines.append("Do not add a verification read after a write unless "
                     "the next action needs its result.")
    return lines


def rebuild_expected_prompts(sample: dict, catalog: dict, runtime_dir: str,
                             zaic_tools_dir: str, gold_calls: list,
                             replay_results: list) -> tuple:
    """Rebuild (base_prompt, expected_step_prompts) from the ORIGINAL
    sample + catalog + pinned runtime. Raises RuntimeError if the
    runtime or config cannot be loaded. replay_results must align
    1:1 with gold_calls (caller skips this when replay truncated)."""
    rt_base, rt_obs, Sample, Turn, ctools, config = _load_runtime(
        runtime_dir, zaic_tools_dir)
    history = []
    for t in (sample.get("history") or []):
        history.append(Turn(role=t.get("role"), audio=t.get("audio"),
                            audio_text=t.get("audio_text"), text=t.get("text"),
                            tool_calls=t.get("tool_calls", []),
                            tool_results=t.get("tool_results")))
    sobj = Sample(id=sample["id"], split="train", audio=sample.get("audio", ""),
                  context=sample["context"], history=history,
                  audio_text=sample.get("audio_text"),
                  label=sample.get("label"))
    tools = ctools(catalog, sobj)
    base = rt_base(sobj, sample.get("audio_text"), tools)
    for line in _config_suffix_lines(config):
        base += "\n" + line
    prompts = []
    for j in range(len(gold_calls)):
        if j == 0:
            prompts.append(base)
        else:
            prompts.append(rt_obs(base, gold_calls[:j], replay_results[:j]))
    if not gold_calls or gold_calls[-1]["name"] != "sys.ask_missing_info":
        if not gold_calls:
            prompts.append(base)
        else:
            prompts.append(rt_obs(base, gold_calls, replay_results))
    return base, prompts


# ---------------------------------------------------------------------------
# Token checks (independent implementation; NEVER imports builder token
# helpers). Reference is runtime llm._render: single user message +
# add_generation_prompt, encoded with add_special_tokens=False.
# ---------------------------------------------------------------------------
_TOKENIZER_HELPER = r"""
import json, sys
def main():
    req = json.load(sys.stdin)
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(req["model"], revision=req["revision"],
                                        local_files_only=True)
    out = {"eos_token_id": tok.eos_token_id, "eos_token": tok.eos_token,
           "steps": []}
    for st in req["steps"]:
        rendered = tok.apply_chat_template(
            [{"role": "user", "content": st["prompt"]}],
            tokenize=False, add_generation_prompt=True)
        out["steps"].append({
            "rendered": rendered,
            "rendered_ids": tok.encode(rendered, add_special_tokens=False),
            "target_ids": tok.encode(st["target"], add_special_tokens=False),
        })
    json.dump(out, sys.stdout, ensure_ascii=False)
main()
"""


def batch_rendered_tokens(tokenizer_python: str, model: str, revision: str,
                          requests: list) -> dict:
    """One tokenizer subprocess for many steps. requests: [{key, prompt,
    target}]. Returns {key: {rendered, rendered_ids, target_ids,
    eos_token_id}}. Raises RuntimeError on any tokenizer failure
    (caller converts to SKIPPED, never to a silent pass)."""
    payload = {"model": model, "revision": revision,
               "steps": [{"prompt": r["prompt"], "target": r["target"]}
                         for r in requests]}
    try:
        proc = subprocess.run(
            [tokenizer_python, "-c", _TOKENIZER_HELPER],
            input=json.dumps(payload, ensure_ascii=False),
            capture_output=True, text=True, timeout=600)
    except Exception as exc:
        raise RuntimeError(f"tokenizer subprocess failed: {exc}") from exc
    if proc.returncode != 0:
        raise RuntimeError(
            f"tokenizer subprocess exit {proc.returncode}: "
            f"{proc.stderr[-500:]}")
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"tokenizer output unparseable: {exc}") from exc
    out = {}
    for req, step in zip(requests, data["steps"]):
        out[req["key"]] = {"rendered": step["rendered"],
                           "rendered_ids": step["rendered_ids"],
                           "target_ids": step["target_ids"],
                           "eos_token_id": data["eos_token_id"]}
    return out


def _verify_token_fields(example: dict, rendered_map: dict) -> dict:
    """Compare artifact token fields against independently rendered ids.
    rendered_map keys are (sample_id, step_index). Returns a report
    with verdict pass/fail and total_trained_tokens."""
    failures = []
    total_trained = 0
    eos_seen = None
    for i, st in enumerate(example["steps"]):
        key = (example["sample_id"], i)
        if key not in rendered_map:
            failures.append(f"token_batch_missing:step {i}")
            continue
        r = rendered_map[key]
        r_ids, t_ids, eos = r["rendered_ids"], r["target_ids"], r["eos_token_id"]
        eos_seen = eos
        if st.get("rendered_prompt") != r["rendered"]:
            failures.append(f"rendered_prompt_mismatch:step {i}")
        if st.get("rendered_prompt_token_ids") != r_ids:
            failures.append(f"rendered_ids_mismatch:step {i}")
        if "prompt_token_ids" in st and st["prompt_token_ids"] != r_ids:
            failures.append(f"prompt_token_ids_not_rendered:step {i}")
        if st.get("target_token_ids") != t_ids:
            failures.append(f"target_ids_mismatch:step {i}")
        if t_ids and t_ids[-1] == eos:
            failures.append(f"double_eos:step {i}")
        expect_input = r_ids + t_ids + [eos]
        if st.get("input_ids") != expect_input:
            failures.append(f"input_ids_mismatch:step {i}")
        expect_labels = [-100] * len(r_ids) + t_ids + [eos]
        if st.get("labels") != expect_labels:
            labels = st.get("labels")
            if not isinstance(labels, list) or len(labels) != len(expect_input):
                failures.append(f"labels_shape_mismatch:step {i}")
            else:
                if any(lab != -100 for lab in labels[:len(r_ids)]):
                    failures.append(f"prompt_trained_not_masked:step {i}")
                if labels[len(r_ids):] != t_ids + [eos]:
                    failures.append(f"target_masked_or_eos_wrong:step {i}")
        if st.get("eos_token_id") != eos:
            failures.append(f"eos_token_id_mismatch:step {i}")
        if st.get("sequence_tokens") != len(expect_input):
            failures.append(f"sequence_tokens_mismatch:step {i}")
        if len(r_ids) + PINNED_MAX_NEW_TOKENS > PINNED_MAX_CONTEXT_TOKENS:
            failures.append(f"budget_prompt_plus_reserve:step {i}")
        if len(expect_input) > PINNED_MAX_CONTEXT_TOKENS:
            failures.append(f"budget_sequence:step {i}")
        total_trained += len(t_ids) + 1
    return {"verdict": "pass" if not failures else "fail",
            "failures": failures, "total_trained_tokens": total_trained,
            "eos_token_id": eos_seen}


def check_token_spans(example: dict, tokenizer_python: str, model: str,
                      revision: str) -> dict:
    """Standalone token check for one example (single-example batch).
    Legacy artifacts (no rendered fields on any step) return SKIPPED;
    mixed rendered/legacy steps fail as inconsistent; missing
    tokenizer returns SKIPPED, never a silent pass."""
    steps = example.get("steps") or []
    if not steps:
        return {"verdict": "SKIPPED", "reason": "no steps",
                "failures": [], "total_trained_tokens": 0, "eos_token_id": None}
    status = _rendered_status(steps)
    if status == "legacy":
        return {"verdict": "SKIPPED",
                "reason": "legacy artifact: no rendered token fields",
                "failures": [], "total_trained_tokens": 0, "eos_token_id": None}
    if status == "mixed":
        return {"verdict": "fail",
                "failures": ["token_fields_inconsistent: some steps lack "
                             "rendered fields"],
                "total_trained_tokens": 0, "eos_token_id": None}
    if not tokenizer_python:
        return {"verdict": "SKIPPED", "reason": "no tokenizer supplied",
                "failures": [], "total_trained_tokens": 0, "eos_token_id": None}
    requests = [{"key": (example["sample_id"], i), "prompt": st["prompt"],
                 "target": st["target"]} for i, st in enumerate(steps)]
    rendered_map = batch_rendered_tokens(tokenizer_python, model, revision,
                                         requests)
    rep = _verify_token_fields(example, rendered_map)
    rep["status"] = "enforced"
    return rep


# ---------------------------------------------------------------------------
# Full example validation (Bug 2 + Bug 3 fixes live here).
# ---------------------------------------------------------------------------
def validate_example(example: dict, sample: dict, fuzzy_by_tool: dict,
                     data_root: str, zaic_tools_dir: str,
                     guard_flags: list | None = None,
                     manifest: dict | None = None,
                     part: str | None = None,
                     mode: str = "training",
                     runtime_dir: str | None = None,
                     catalog: dict | None = None,
                     contract_name: str | None = None,
                     tokenizer_python: str | None = None,
                     model: str = "Qwen/Qwen3-4B-Instruct-2507",
                     revision: str = "cdbee75",
                     token_batch: dict | None = None) -> dict:
    """Full validation of one builder example, including independent
    ToolEnv replay with full outcome classification, runtime prompt
    rebuild, manifest/mode checks, metadata consistency, and (when
    rendered fields + tokenizer are present) token checks.

    manifest format: {"assignment": {id: part}, "train_eligible":
    {id: bool}} (the train_eligible map is optional; absent means
    every sample is eligible). mode: "training" or "evaluation".
    token_batch: {(sample_id, step_index): rendered info} as returned
    by batch_rendered_tokens (CLI batches once for all examples)."""
    if mode not in ("training", "evaluation"):
        raise ValueError(f"unknown mode: {mode!r} (training|evaluation)")
    failures = []
    notes = []
    checks = {}
    steps = example.get("steps") or []
    sid = example.get("sample_id")
    gold_calls = sample["label"]["tool_calls"]

    # --- sample identity (generic; no sample-ID lists anywhere).
    if sid != sample["id"]:
        failures.append("sample_id_mismatch:example sample_id != sample id")

    # --- contract (artifact may not declare itself valid).
    if contract_name is not None:
        if contract_name != PINNED_CONTRACT_NAME:
            failures.append(f"contract_mismatch:{contract_name}")
        checks["contract"] = "checked"
    else:
        checks["contract"] = "SKIPPED: no contract declared in artifact"

    # --- manifest membership + part + eligibility.
    if manifest is None:
        checks["manifest"] = "SKIPPED: no manifest supplied"
        checks["eligibility"] = "SKIPPED: no manifest supplied"
    else:
        assignment = manifest.get("assignment") or {}
        if sid not in assignment:
            failures.append("manifest_membership:sample not in manifest assignment")
            checks["manifest"] = "failed"
        elif part is not None and assignment[sid] != part:
            failures.append(
                f"manifest_part_mismatch:assigned {assignment[sid]}, "
                f"requested {part}")
            checks["manifest"] = "failed"
        else:
            checks["manifest"] = "passed"
            if part is None:
                checks["manifest"] += " (part check SKIPPED: no part requested)"
        if "manifest_part" in example and part is not None \
                and example["manifest_part"] != part:
            failures.append(
                f"manifest_part_mismatch:artifact {example['manifest_part']}, "
                f"requested {part}")
        if mode == "evaluation":
            checks["eligibility"] = ("SKIPPED (evaluation mode: eligibility "
                                     "bars training only, never evaluation)")
        else:
            elig = manifest.get("train_eligible")
            if elig is None:
                checks["eligibility"] = "SKIPPED: no eligibility map in manifest"
            elif elig.get(sid, True) is False:
                failures.append("not_train_eligible:sample train_eligible is False")
                checks["eligibility"] = "failed"
            else:
                checks["eligibility"] = "passed"

    # --- independent replay with full outcome classification.
    if zaic_tools_dir not in sys.path:
        sys.path.insert(0, zaic_tools_dir)
    from zaic_tools import ToolEnv
    env = ToolEnv("train", sample["id"], root=data_root)
    replay_results = []
    outcome_statuses = []
    not_done_indices = []
    truncated = False
    for i, call in enumerate(gold_calls):
        check = env.validate(call["name"], call.get("arguments") or {})
        if not check.get("ok"):
            failures.append(f"schema_rejected:step {i}:{check.get('error')}")
            truncated = True
            break
        result = env.call(call["name"], call.get("arguments") or {})
        status, _reason = classify_outcome(result)
        outcome_statuses.append(status)
        if status == "not_done":
            not_done_indices.append(i)
            if mode == "training":
                failures.append(f"not_done:step {i}")
        elif status != "success":
            failures.append(f"{status}:step {i}")
        replay_results.append(result)
    replay_ok = not truncated
    replay_hash = env.get_state_hash() if replay_ok else None
    checks["replay_outcome"] = ("truncated at schema_rejected" if truncated
                                else f"statuses={outcome_statuses}")
    anomaly = {"not_done_steps": not_done_indices} if not_done_indices else None

    # --- metadata consistency (artifact claims vs independent replay).
    if "not_done_steps" in example:
        claimed = example["not_done_steps"]
        if sorted(claimed) != sorted(not_done_indices):
            failures.append(
                f"not_done_steps_mismatch:artifact {claimed} vs replay "
                f"{not_done_indices}")
        checks["metadata_not_done"] = "checked"
    else:
        checks["metadata_not_done"] = "SKIPPED: artifact lacks not_done_steps"
    if "state_hash" in example:
        if replay_ok and replay_hash != example["state_hash"]:
            failures.append("state_hash_mismatch:artifact hash != replay hash")
        checks["metadata_state_hash"] = "checked"
    else:
        checks["metadata_state_hash"] = "SKIPPED: artifact lacks state_hash"
    if "executed_calls" in example:
        if [canon_call_key(c) for c in example["executed_calls"]] != \
                [canon_call_key(c) for c in gold_calls]:
            failures.append("executed_calls_mismatch:artifact calls != gold calls")
        checks["metadata_executed_calls"] = "checked"
    else:
        checks["metadata_executed_calls"] = "SKIPPED: artifact lacks executed_calls"
    hash_match = bool(replay_ok and example.get("state_hash") is not None
                      and replay_hash == example["state_hash"])

    # --- runtime prompt rebuild (Bug 2 fix; authoritative).
    rebuilt_base = None
    if truncated:
        notes.append("runtime prompt rebuild skipped: replay truncated at "
                     "schema_rejected (verdict already fails)")
        checks["prompt_rebuild"] = "SKIPPED: replay truncated"
    elif catalog is None:
        failures.append("runtime_rebuild_unavailable:catalog required to "
                        "rebuild base prompt")
        checks["prompt_rebuild"] = "failed: no catalog"
    else:
        try:
            rebuilt_base, expected_prompts = rebuild_expected_prompts(
                sample, catalog, runtime_dir or DEFAULT_RUNTIME_DIR,
                zaic_tools_dir, gold_calls, replay_results)
        except Exception as exc:
            failures.append(f"runtime_rebuild_failed:{exc}")
            checks["prompt_rebuild"] = "failed"
            expected_prompts = None
        if expected_prompts is not None:
            if len(expected_prompts) != len(steps):
                failures.append(
                    f"step_count_mismatch_runtime:expected "
                    f"{len(expected_prompts)}, artifact {len(steps)}")
            for i, st in enumerate(steps):
                if i < len(expected_prompts) and expected_prompts[i] != st["prompt"]:
                    failures.append(f"prompt_rebuild_mismatch_runtime:step {i}")
            checks["prompt_rebuild"] = "checked"

    # --- fidelity checks (sequence/args/parser/leakage) against the
    # rebuilt base, never against an artifact-declared base.
    if rebuilt_base is not None:
        step_rep = validate_steps(
            rebuilt_base, steps, gold_calls, sample["label"].get("final_state"),
            fuzzy_by_tool,
            replay_results=replay_results if not truncated else None,
            guard_flags=guard_flags)
        failures.extend(step_rep["failures"])
        notes.extend(step_rep["notes"])
        guard_diag = step_rep["guard_diagnostic"]
        n_steps, n_calls = step_rep["n_steps"], step_rep["n_calls"]
    else:
        guard_diag = "not_run"
        n_steps, n_calls = len(steps), sum(
            1 for st in steps if st.get("call") is not None)

    # --- explicit future-observation check (beyond the generic
    # leakage check in validate_steps): no FULL canonical result JSON
    # of a LATER step may appear in an earlier step's prompt.
    result_jsons = [compact(r) for r in replay_results if isinstance(r, dict)]
    for i, st in enumerate(steps):
        prompt = st.get("prompt", "")
        for j in range(i + 1, len(result_jsons)):
            rj = result_jsons[j]
            if len(rj) > 2 and rj in prompt:
                failures.append(f"future_observation:result[{j}] in prompt[{i}]")

    # --- token checks (enforced only for rendered artifacts with a
    # tokenizer; legacy artifacts SKIP with a reason, never pass).
    token_checks = {"status": "SKIPPED",
                    "reason": "not evaluated (see below)"}
    if steps:
        status = _rendered_status(steps)
        if status == "legacy":
            token_checks = {"status": "SKIPPED",
                            "reason": "legacy artifact: no rendered token fields",
                            "failures": []}
        elif status == "mixed":
            failures.append("token_fields_inconsistent: some steps lack rendered fields")
            token_checks = {"status": "fail",
                            "reason": "mixed rendered/legacy steps",
                            "failures": ["token_fields_inconsistent"]}
        elif token_batch is not None:
            rep = _verify_token_fields(example, token_batch)
            token_checks = {"status": "enforced", **rep}
            failures.extend(rep["failures"])
        elif tokenizer_python is not None:
            try:
                rep = check_token_spans(example, tokenizer_python, model, revision)
            except Exception as exc:
                rep = {"verdict": "SKIPPED",
                       "reason": f"tokenizer unavailable: {exc}",
                       "failures": []}
            if rep["verdict"] == "SKIPPED":
                token_checks = {"status": "SKIPPED", "reason": rep.get("reason"),
                                "failures": []}
            else:
                token_checks = {"status": "enforced", **rep}
                failures.extend(rep["failures"])
        else:
            token_checks = {"status": "SKIPPED",
                            "reason": "no tokenizer supplied",
                            "failures": []}
    checks["token"] = token_checks["status"]

    return {
        "verdict": "pass" if not failures else "fail",
        "failures": failures,
        "notes": notes,
        "checks": checks,
        "token_checks": token_checks,
        "anomaly": anomaly,
        "sample_id": sid,
        "replay_ok": replay_ok,
        "hash_match": hash_match,
        "not_done_steps_replay": not_done_indices,
        "guard_diagnostic": guard_diag,
        "n_steps": n_steps,
        "n_calls": n_calls,
    }


# ---------------------------------------------------------------------------
# CLI.
# ---------------------------------------------------------------------------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="sft_prototype_validator")
    ap.add_argument("--output", required=True)
    ap.add_argument("--train-jsonl", required=True)
    ap.add_argument("--data-root", required=True)
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--zaic-tools-dir", default=None)
    ap.add_argument("--tokenizer-python", default=None)
    ap.add_argument("--model", default="Qwen/Qwen3-4B-Instruct-2507")
    ap.add_argument("--revision", default="cdbee75")
    ap.add_argument("--manifest", default=None)
    ap.add_argument("--part", default=None)
    ap.add_argument("--mode", choices=["training", "evaluation"],
                    default="training")
    ap.add_argument("--runtime-dir", default=None)
    args = ap.parse_args(argv)

    if args.mode == "training" and not args.manifest:
        print("ERROR: training mode requires --manifest (membership and "
              "train_eligible checks cannot be skipped silently).",
              file=sys.stderr)
        return 2
    if args.manifest and not args.part:
        print("ERROR: --manifest requires --part (part must equal the "
              "manifest assignment for each sample).", file=sys.stderr)
        return 2

    out = json.load(open(args.output, encoding="utf-8"))
    samples = {}
    with open(args.train_jsonl, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                s = json.loads(line)
                samples[s["id"]] = s
    catalog = json.load(open(args.catalog, encoding="utf-8"))
    fuzzy_by_tool = {}
    for app in catalog["apps"]:
        for tool in app["tools"]:
            fuzzy = {name for name, spec in tool["parameters"].get("properties", {}).items()
                     if spec.get("x-match") == "fuzzy"}
            if fuzzy:
                fuzzy_by_tool[tool["name"]] = fuzzy
    zaic_tools_dir = args.zaic_tools_dir or str(Path(args.data_root) / "train")

    manifest = None
    if args.manifest:
        try:
            manifest = json.load(open(args.manifest, encoding="utf-8"))
        except Exception as exc:
            print(f"ERROR: cannot load manifest {args.manifest}: {exc}",
                  file=sys.stderr)
            return 2
        if not isinstance(manifest.get("assignment"), dict):
            print(f"ERROR: manifest {args.manifest} lacks an assignment map.",
                  file=sys.stderr)
            return 2
    file_contract = None
    if isinstance(out.get("contract"), dict):
        file_contract = out["contract"].get("name")

    # One tokenizer batch for all rendered examples (not one subprocess
    # per example). Legacy examples (no rendered fields) need no batch.
    token_batch = None
    if args.tokenizer_python:
        rendered_examples = [ex for ex in out["examples"]
                             if ex.get("steps") and all(
                                 all(f in st for f in RENDERED_FIELDS)
                                 for st in ex["steps"])]
        if rendered_examples:
            requests = []
            for ex in rendered_examples:
                for i, st in enumerate(ex["steps"]):
                    requests.append({"key": (ex["sample_id"], i),
                                     "prompt": st["prompt"],
                                     "target": st["target"]})
            try:
                token_batch = batch_rendered_tokens(
                    args.tokenizer_python, args.model, args.revision, requests)
            except Exception as exc:
                print(f"WARNING: tokenizer batch failed, token checks "
                      f"SKIPPED: {exc}", file=sys.stderr)
                token_batch = None

    reports, token_reports = [], {}
    for ex in out["examples"]:
        sid = ex.get("sample_id")
        if sid not in samples:
            rep = {"sample_id": sid, "verdict": "fail",
                   "failures": ["sample_not_found:sample id not in train.jsonl"],
                   "notes": [], "checks": {}, "token_checks": {},
                   "anomaly": None, "replay_ok": False, "hash_match": False,
                   "not_done_steps_replay": [], "guard_diagnostic": "not_run",
                   "n_steps": 0, "n_calls": 0}
            reports.append(rep)
            token_reports[sid] = {"status": "SKIPPED",
                                  "reason": "sample not found"}
            continue
        rep = validate_example(
            ex, samples[sid], fuzzy_by_tool, args.data_root, zaic_tools_dir,
            manifest=manifest, part=args.part, mode=args.mode,
            runtime_dir=args.runtime_dir, catalog=catalog,
            contract_name=file_contract,
            tokenizer_python=args.tokenizer_python, model=args.model,
            revision=args.revision, token_batch=token_batch)
        reports.append(rep)
        token_reports[sid] = rep["token_checks"]
    summary = {
        "n_examples": len(reports),
        "passed": sum(1 for r in reports if r["verdict"] == "pass"),
        "failed": sum(1 for r in reports if r["verdict"] != "pass"),
        "hash_match": sum(1 for r in reports if r.get("hash_match")),
        "anomalies": [{"sample_id": r["sample_id"], "anomaly": r["anomaly"]}
                      for r in reports if r.get("anomaly")],
        "token_reports": token_reports,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    for r in reports:
        if r["verdict"] != "pass":
            print(f"FAIL {r['sample_id']}: {r['failures']}")
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
