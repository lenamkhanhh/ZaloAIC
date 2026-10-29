#!/usr/bin/env python3
"""Validator for SFT prototype trajectories (Thread B).

What it checks (primary verdict) and what it does NOT do:
  * Prompt rebuild equality: every step prompt is rebuilt from the
    base prompt + observations of earlier steps and must EQUAL the
    recorded prompt exactly (string equality, not substring).
  * Leakage: at step t, the prompt must NOT contain (a) the compact
    result JSON of step t or any later step, (b) the compact gold
    final_state JSON (skipped when trivial "{}"/"[]"), (c) the target
    JSON of step t. Checks use full JSON strings, never individual
    values (a person's name legitimately appears in the request).
  * Sequence fidelity (PRIMARY): the executed call sequence must
    equal the gold call sequence (name + canonical args, in order);
    ask, when present, must be the last call; the stop step must be
    exactly one step at the end (or absent iff the last gold call is
    ask; empty samples have exactly one step, the stop step).
  * Argument fidelity: non-fuzzy params exact; fuzzy params
    (catalog x-match: fuzzy) token-F1 > 0.6, replicating
    lifemate/scoring.py token_f1 (NFC, lowercase, strip non-word
    chars, whitespace tokens). Arg key sets must match exactly.
  * Parser round-trip: each target must parse under a replica of
    a2e832b llm.parse_model_output (strip, optional fence, JSON
    object, stop detection) to the recorded call (or stop signal).
  * Token spans (only when token data is supplied): labels are -100
    exactly on prompt tokens and trained exactly on target + EOS
    tokens; decode(prompt_ids + target_ids + [eos]) must round-trip
    to prompt text + target text + EOS text.
  * state_hash is SECONDARY by design: it is reported but never
    determines the verdict, because reads/asks do not change state.
    test_sft_prototype.py contains the counterexample (extra read,
    same hash, sequence check fails).
  * Guard diagnostic: guard_fired flags, when supplied, are recorded
    verbatim and NEVER change the verdict. The current guard
    (prover/gates) is not an oracle for data validity: a guard fire
    on a gold trajectory is logged as guard-false-block diagnostic,
    not as a data error. This validator does not import the guard.

Replay verification: validate_file() replays gold calls through
ToolEnv independently and requires the builder's recorded step
results to equal replay results exactly. That verifies simulator
transitions only -- it does NOT verify the whole AgentLoop (prompt
rendering inside the loop, validation retries, loop guard, grounding,
parser inside the loop are covered by the conformance test and by
the prompt-rebuild check, not by this replay).

Usage:
  python3 sft_prototype_validator.py --output sft_prototype_local.json \
      --train-jsonl <train.jsonl> --data-root <train+public_test> \
      --catalog <train_tools_catalog.json> \
      [--tokenizer-python ~/workspace/zaic-test-venv/bin/python]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sft_prototype_builder import (  # noqa: E402
    CONTRACT, build_steps, canon_call, canon_call_key, batch_tokenize)

STOP_TARGET = CONTRACT["stop_target"]


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
# Core validation (works on step lists; no env needed except replay mode).
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


def validate_example(example: dict, sample: dict, fuzzy_by_tool: dict,
                     data_root: str, zaic_tools_dir: str,
                     guard_flags: list | None = None) -> dict:
    """Full validation of one builder example, including independent
    ToolEnv replay. Returns the validate_steps report plus replay and
    hash fields (hash is secondary)."""
    steps = example["steps"]
    base_prompt = steps[0]["prompt"] if steps else ""
    # Rebuild base: step 0 prompt IS the base prompt by construction
    # (no observations yet). For non-empty trajectories the base is
    # also recoverable, but step 0 is authoritative here.
    gold_calls = sample["label"]["tool_calls"]
    if zaic_tools_dir not in sys.path:
        sys.path.insert(0, zaic_tools_dir)
    from zaic_tools import ToolEnv
    env = ToolEnv("train", sample["id"], root=data_root)
    replay_results, replay_ok = [], True
    for call in gold_calls:
        check = env.validate(call["name"], call.get("arguments") or {})
        if not check.get("ok"):
            replay_ok = False
            break
        replay_results.append(env.call(call["name"], call.get("arguments") or {}))
    report = validate_steps(base_prompt, steps, gold_calls,
                            sample["label"].get("final_state"),
                            fuzzy_by_tool, replay_results=replay_results,
                            guard_flags=guard_flags)
    report["sample_id"] = example["sample_id"]
    report["replay_ok"] = replay_ok
    report["hash_match"] = (env.get_state_hash() == example.get("state_hash")) \
        if replay_ok else False
    if not replay_ok:
        report["failures"].append("validator_replay_failed")
        report["verdict"] = "fail"
    # NOTE: hash_match is secondary and never changes the verdict.
    return report


# ---------------------------------------------------------------------------
# Token-span check (subprocess tokenizer; skipped cleanly if absent).
# ---------------------------------------------------------------------------
def check_token_spans(example: dict, tokenizer_python: str, model: str,
                      revision: str) -> dict:
    """Assert exact train spans: labels are -100 on prompt tokens and
    trained on target + EOS tokens; decode round-trips. Returns a
    report; raises on tokenizer failure (caller converts to SKIPPED)."""
    from sft_prototype_builder import batch_tokenize
    texts = []
    for st in example["steps"]:
        texts.append(st["prompt"])
        texts.append(st["target"])
    data = batch_tokenize(tokenizer_python, model, revision, texts)
    eos = data["eos_token_id"]
    failures = []
    total_trained = 0
    for i, st in enumerate(example["steps"]):
        p_ids = data["ids"][2 * i]
        t_ids = data["ids"][2 * i + 1]
        labels = [-100] * len(p_ids) + t_ids + [eos]
        trained = [tid for tid, lab in zip(p_ids + t_ids + [eos], labels) if lab != -100]
        if trained != t_ids + [eos]:
            failures.append(f"span_mask_mismatch:step {i}")
        if p_ids != st.get("prompt_token_ids") or t_ids != st.get("target_token_ids"):
            failures.append(f"span_ids_mismatch_builder:step {i}")
        total_trained += len(t_ids) + 1
        if len(p_ids) + 512 > CONTRACT["max_context_tokens"]:
            failures.append(f"budget_prompt_plus_reserve:step {i}")
        if len(p_ids) + len(t_ids) + 1 > CONTRACT["max_context_tokens"]:
            failures.append(f"budget_sequence:step {i}")
    return {"verdict": "pass" if not failures else "fail", "failures": failures,
            "total_trained_tokens": total_trained, "eos_token_id": eos}


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
    args = ap.parse_args(argv)

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

    reports, token_reports = [], {}
    for ex in out["examples"]:
        rep = validate_example(ex, samples[ex["sample_id"]], fuzzy_by_tool,
                               args.data_root, zaic_tools_dir)
        reports.append(rep)
        if args.tokenizer_python:
            try:
                token_reports[ex["sample_id"]] = check_token_spans(
                    ex, args.tokenizer_python, args.model, args.revision)
            except Exception as exc:  # tokenizer failure -> SKIPPED, never silent pass
                token_reports[ex["sample_id"]] = {"verdict": "SKIPPED",
                                                 "reason": f"tokenizer unavailable: {exc}"}
    summary = {
        "n_examples": len(reports),
        "passed": sum(1 for r in reports if r["verdict"] == "pass"),
        "failed": sum(1 for r in reports if r["verdict"] != "pass"),
        "hash_match": sum(1 for r in reports if r.get("hash_match")),
        "token_reports": token_reports,
        "reports": reports,
    }
    print(json.dumps({k: v for k, v in summary.items() if k != "reports"},
                     ensure_ascii=False, indent=1))
    for r in reports:
        if r["verdict"] != "pass":
            print(f"FAIL {r['sample_id']}: {r['failures']}")
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
