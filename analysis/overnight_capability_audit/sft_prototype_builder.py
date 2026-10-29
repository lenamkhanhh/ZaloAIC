#!/usr/bin/env python3
"""Deterministic SFT prototype builder for LifeMate (Thread B).

Builds training examples from gold trajectories WITHOUT training anything
and WITHOUT running any model. Each example is a list of turns:

    step t: prompt_t (full rendered prompt the runtime would feed the
            model at that turn) -> target_t (canonical JSON of the gold
            call at that turn, or '{"stop":true}' as the final step).

Contract pinned (see sft_prototype_report.md for the evidence table):
  * a2e832b TEXT contract, NOT the V10/V11 native contract.
  * Single user message via the Qwen chat template; prose tool list in
    the user message; observations appended as text lines; one JSON
    object per turn parsed by llm.parse_model_output; stop =
    '{"stop":true}' (canonical compact form) + EOS <|im_end|> (151645).
  * Prompt rendering replicates lifemate/agent.py build_base_prompt +
    render_observation_prompt (baseline config suffix lines included).
    The conformance test in test_sft_prototype.py compares this
    rendering against the real a2e832b functions when importable.
  * Observations come ONLY from real simulator replay (ToolEnv
    env.call, in gold order). No guard, no model, no hand-written
    observations.
  * Transcript mode is GOLD (train audio_text). ASR-transcript mode is
    NOT implemented: it needs a GPU production-ASR pass that does not
    exist locally (see report §6). Building on ASR text without that
    pass would be fabrication, not a prototype.
  * Tokenization (FIXED 2026-10-29, see tokenization_fix_notes.md):
    prompt ids are the RUNTIME chat-template ids, not raw encodes.
    Runtime llm._render builds messages=[{"role": "user", "content":
    prompt}] and applies the tokenizer's chat template with
    add_generation_prompt=True; the builder does exactly that
    (tokenize=True) and asserts equality with the runtime path
    encode(rendered_text, add_special_tokens=False). BREAKING CHANGE:
    step["prompt_token_ids"] now means RENDERED prompt ids; the old
    raw-encode meaning is deleted, not kept as a fallback. Training
    input per step = rendered_prompt_ids + target_ids + [EOS];
    labels = [-100]*len(rendered_prompt_ids) + target_ids + [EOS].
    Budget uses rendered prompt + 512 reserved output, never the
    raw prompt length.

Determinism: no randomness anywhere. Selection scans manifest-part
samples in sorted-id order and takes the first matches per class.
Same inputs -> byte-identical outputs (modulo JSON float formatting,
of which there is none: all counts are ints).

Safety rules (generic, never sample-ID based):
  * Only samples in the manifest part passed via --manifest/--part are
    built. An --ids-file entry outside that part aborts the run.
  * A gold call that fails env.validate is NEVER executed and the
    sample is DROPPED with reason (validation_failed), not repaired.
  * A trajectory with an ask call anywhere but last is DROPPED
    (ask_not_last); a trajectory repeating one identical call more
    than max_repeats (2, the loop guard) times is DROPPED
    (loop_guard_exceeded) because the runtime loop could not
    reproduce it. More than max_steps (12) gold calls -> DROPPED.
  * Token budget (prompt tokens + 512 reserved <= 16384 AND full
    training sequence <= 16384) is enforced ONLY when a tokenizer
    python is supplied (--tokenizer-python); otherwise the example is
    marked budget_status="unchecked" and the validator must re-check
    with a tokenizer. NOTHING is ever silently truncated.
  * Output contains full prompt texts, so it is LOCAL ONLY and must
    never be pushed (see report §7).

Usage:
  python3 sft_prototype_builder.py --train-jsonl <train.jsonl> \
      --data-root <train+public_test dir> --manifest <split json> \
      --part inner_train --manifest-version v1-frozen \
      --select-coverage --per-class 2 --out sft_prototype_local.json \
      --tokenizer-python ~/workspace/zaic-test-venv/bin/python
  python3 sft_prototype_builder.py ... --ids-file ids.txt --out out.json
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

# ---------------------------------------------------------------------------
# Pinned contract constants (a2e832b, baseline config).
# ---------------------------------------------------------------------------
CONTRACT = {
    "name": "a2e832b-text",
    "worktree": "~/workspace/zaic-branch-a2e832b/lifemate/",
    "agent_commit": "a2e832b",
    "prompt_contract": "single user message; prose tool list; text observations",
    "parser": "llm.parse_model_output (one JSON object, optional fence; "
              '{"stop": true} or {"name": "stop"} without arguments -> stop)',
    "stop_target": '{"stop":true}',
    "tokenization": "chat template rendered prompt ids (llm._render: single user "
                    "message, add_generation_prompt=True); prompt_token_ids are "
                    "RENDERED ids, not raw encodes (breaking change 2026-10-29)",
    "eos_token": "<|im_end|>",
    "eos_token_id": 151645,
    "max_steps": 12,
    "max_repeats": 2,
    "max_context_tokens": 16384,
    "max_new_tokens": 512,
    "config_baseline": "lifemate/configs/baseline.json (grounding=false; "
                       "selective_reads=true; verification_read_after_write=false)",
    "transcript_mode": "gold",
    "status": "PROVISIONAL (zero-shot benchmark output not in workspace)",
}

ACTION_POLICY = """Action policy (apply to the CURRENT request, not old requests in history):
1. Identify the user's final intent, corrections, cancellations and each requested action. Do not add follow-up actions the user did not request. A cancelled sole request, chat, or an unavailable capability needs no tool call; output {"stop":true}.
2. Evaluate conditions BEFORE their dependent writes. Resolve the target date/location using current_time and context. Reuse a still-valid matching observation in history; otherwise read the needed fact first. Do not execute both branches. If the selected branch requests no action, stop.
3. Resolve entities BEFORE acting. Use catalog x-ref IDs from matching observed collections or an ID explicitly provided by the user. Names are not IDs. Read/search when an entity is not yet resolved. One returned entity is not proof of user intent: check name/relation/room and the request. Several candidates require a unique explicit discriminator or sys.ask_missing_info; do not pick the first.
4. Every argument needs evidence: the user's request/context, applicable history, a tool result, a schema default, or a calculation from those facts. Never invent phone numbers, amounts or dates/times. Read a bill/balance/event when the request refers to its value. Missing required information that cannot be obtained by a relevant read must be asked using sys.ask_missing_info with the exact tool_name and missing params. Do not assume the current time is a requested reminder time.
5. Tool results with done:false did NOT complete the requested action even if ok:true. Change the plan using evidence; do not repeat the same failed call. A created reminder is not a completed reminder: do not mark it done unless the user requested completion. A condition written into a label does not make an immediate write conditional.
6. After all requested actions of the selected branch succeed, output {"stop":true}. Do not undo, mark complete, recreate or verify writes without a separate need in this request. Repeat an identical action only if the user explicitly requested multiple instances; otherwise avoid duplicate calls. sys.ask_missing_info ends this turn while waiting for the user.
Output exactly one tool-call JSON or {"stop":true}; no invented tool named stop, no narrative, no list of calls."""

BASE_SUFFIX_LINES = [
    "Read only to resolve a missing entity or precondition; reuse still-valid observations.",
    "Do not add a verification read after a write unless the next action needs its result.",
]

CONDITIONAL_MARKERS = [
    r"nếu", r"trừ khi", r"trong trường hợp", r"chỉ khi",
    r"nếu không", r"còn không", r"\bkhi\b", r"\bif\b",
    r"\bunless\b", r"in case",
]


# ---------------------------------------------------------------------------
# Rendering (replicates a2e832b lifemate/agent.py; conformance-tested).
# ---------------------------------------------------------------------------
def canon_call(call: dict) -> str:
    """Canonical target text for one gold call (compact JSON)."""
    return json.dumps({"name": call["name"], "arguments": call.get("arguments") or {}},
                      ensure_ascii=False, separators=(",", ":"))


def canon_call_key(call: dict) -> str:
    """Canonical key for call identity (sorted keys, for comparisons)."""
    return json.dumps({"name": call["name"], "arguments": call.get("arguments") or {}},
                      ensure_ascii=False, sort_keys=True)


def build_base_prompt(sample: dict, tools: dict) -> str:
    """Replicates AgentLoop base prompt (baseline config suffixes on)."""
    ctx = sample["context"]
    profile = ctx.get("user_profile", {})
    lines = [
        "You are a Vietnamese voice assistant. Output exactly one JSON "
        "object per turn: {\"name\": \"<tool>\", \"arguments\": {...}} or "
        "{\"stop\": true} when done. Never invent ids: use only ids from "
        "previous tool results in this conversation or explicit user input.",
        ACTION_POLICY,
        f"Current time: {ctx.get('current_time')} ({ctx.get('timezone')}).",
        f"User: {profile.get('name', '')}, city {profile.get('city', '')}.",
        "User-provided context: " + json.dumps(ctx, ensure_ascii=False),
        "Tools you may call (this sample only):",
    ]
    for name, spec in sorted(tools.items()):
        lines.append(json.dumps({"name": name, "kind": spec["kind"],
                                 "description": spec.get("description", ""),
                                 "parameters": spec["parameters"],
                                 "returns": spec.get("returns", "")},
                                ensure_ascii=False))
    lines.append("Conversation history:")
    for turn in sample.get("history", []):
        if turn.get("role") == "user":
            text = turn.get("audio_text")
            if text is None:
                text = "[audio, no transcript available]"
            lines.append(f"user: {text}")
        else:
            lines.append(
                f"assistant: {turn.get('text') or ''} "
                f"calls={json.dumps(turn.get('tool_calls', []), ensure_ascii=False)} "
                f"results={turn.get('tool_results')!r}")
    lines.append(f"Current user request (transcript): {sample.get('audio_text')}")
    base = "\n".join(lines)
    for suffix in BASE_SUFFIX_LINES:
        base += "\n" + suffix
    return base


def render_observation_prompt(base_prompt: str, executed: list, results: list) -> str:
    """Replicates agent.render_observation_prompt (no replan line: gold
    trajectories never trigger the loop guard replan path)."""
    lines = []
    for call, result in zip(executed, results):
        if result.get("ok") and result.get("done") is False:
            outcome = "not_done"
        elif result.get("ok"):
            outcome = "ok"
        else:
            outcome = f"error: {result.get('error')}"
        output = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
        lines.append(f"- {call['name']}({call['arguments']}) -> {outcome}; output={output}")
    return (
        f"{base_prompt}\n\nPrevious calls and their OBSERVED results "
        "(use these, do not repeat failed calls, do not guess new ids):\n"
        + "\n".join(lines)
    )


def build_steps(base_prompt: str, calls: list, results: list) -> list:
    """Pure step construction: prompt_t uses ONLY observations of steps
    < t. The final stop step is appended unless the last call is ask
    (ask ends the turn in the runtime loop). Returns step dicts with
    call=None for the stop step."""
    steps = []
    executed, observed = [], []
    for call in calls:
        prompt = base_prompt if not executed else render_observation_prompt(
            base_prompt, executed, observed)
        steps.append({"prompt": prompt, "target": canon_call(call), "call": call})
        executed.append(call)
        observed.append(results[len(executed) - 1])
    if not calls or calls[-1]["name"] != "sys.ask_missing_info":
        prompt = base_prompt if not executed else render_observation_prompt(
            base_prompt, executed, observed)
        steps.append({"prompt": prompt, "target": CONTRACT["stop_target"], "call": None})
    return steps


# ---------------------------------------------------------------------------
# Generic coverage classification (no sample IDs, no answer keys).
# ---------------------------------------------------------------------------
def gold_kind(calls: list) -> str:
    names = [c["name"] for c in calls]
    if not calls:
        return "empty"
    if names == ["sys.ask_missing_info"]:
        return "ask_only"
    if "sys.ask_missing_info" in names:
        return "ask_after"
    return "normal"


def flatten_values(obj) -> list:
    """Scalar leaf values of a result/history object (for id linkage)."""
    out = []
    if isinstance(obj, dict):
        for v in obj.values():
            out.extend(flatten_values(v))
    elif isinstance(obj, list):
        for v in obj:
            out.extend(flatten_values(v))
    elif isinstance(obj, (str, int, float)) and not isinstance(obj, bool):
        out.append(obj)
    return out


def classify_sample(sample: dict, kind_by_tool: dict, replay_results: list) -> set:
    """Coverage classes for one gold trajectory. replay_results are the
    ToolEnv results of the gold calls, in order (empty for 0 calls).
    Rules are stated in sft_prototype_report.md §4; a class is present
    only if its rule fires, never by analogy."""
    calls = sample["label"]["tool_calls"]
    kinds = [kind_by_tool.get(c["name"], "") for c in calls]
    classes = set()
    if not calls:
        classes.add("empty_stop")
    if gold_kind(calls) == "ask_only":
        classes.add("ask_only")
    has_read = "read" in kinds
    has_write = "write" in kinds
    if has_read and not has_write and calls and calls[-1]["name"] == "sys.ask_missing_info":
        classes.add("read_ask")
    # read_write: a write whose *_id arg value appears as an "id" (or
    # same-slot) field value in an EARLIER gold-step result.
    earlier_id_values = []
    for idx, call in enumerate(calls):
        if kinds[idx] == "write":
            for arg, val in (call.get("arguments") or {}).items():
                if arg.endswith("_id") and val in earlier_id_values:
                    classes.add("read_write")
                    break
        if idx < len(replay_results):
            res = replay_results[idx]
            if kinds[idx] == "read" and isinstance(res, dict):
                for field, val in _iter_result_entries(res):
                    if field == "id":
                        earlier_id_values.append(val)
    if len(calls) >= 3:
        classes.add("multi_step")
    # conditional_no_write: 0 writes, >=1 read, conditional marker in
    # the CURRENT request text, no ask anywhere (trajectory ends by
    # stop after reads). Branch-verification is NOT claimed: the rule
    # cannot prove the read result decided the branch.
    text = sample.get("audio_text") or ""
    if (not has_write and has_read and "sys.ask_missing_info" not in
            [c["name"] for c in calls]
            and any(re.search(m, text) for m in CONDITIONAL_MARKERS)):
        classes.add("conditional_no_write")
    # direct_phone: phone.call/sms.send with phone_number, no
    # contacts.search anywhere in gold.
    names = [c["name"] for c in calls]
    if "contacts.search" not in names:
        for call in calls:
            if call["name"] in ("phone.call", "sms.send") and \
                    (call.get("arguments") or {}).get("phone_number"):
                classes.add("direct_phone")
                break
    # history_dependent: an *_id arg value appears in a history
    # tool_result (flattened) and NOT in the current request text.
    hist_values = set()
    for turn in sample.get("history", []):
        if turn.get("role") == "assistant":
            for val in flatten_values(turn.get("tool_results")):
                hist_values.add(str(val))
    for call in calls:
        for arg, val in (call.get("arguments") or {}).items():
            if arg.endswith("_id") and str(val) in hist_values \
                    and str(val) not in text:
                classes.add("history_dependent")
                break
        if "history_dependent" in classes:
            break
    return classes


def _iter_result_entries(obj, _path=""):
    """Yield (field, value) for dict leaves of a tool result."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                yield from _iter_result_entries(v, _path)
            elif isinstance(v, (str, int, float)) and not isinstance(v, bool):
                yield (k, v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _iter_result_entries(v, _path)


# ---------------------------------------------------------------------------
# Gold replay + example construction.
# ---------------------------------------------------------------------------
class BuilderError(Exception):
    pass


def load_manifest(path: str) -> tuple:
    """Return (assignment, train_eligible). Manifests without a
    train_eligible map (v1, synthetic) treat every sample as eligible.
    COORDINATOR FIX 2026-10-29: v1's load_manifest returned only the
    assignment and silently dropped train_eligible, so the builder
    built the one v2-ineligible sample when asked for it by id (repro:
    --ids-file train_1696 -> built 1). Eligibility is now enforced
    (see main): ids-mode aborts on ineligible ids, coverage mode
    excludes them from scanning."""
    data = json.load(open(path, encoding="utf-8"))
    if isinstance(data, dict) and isinstance(data.get("assignment"), dict):
        return data["assignment"], data.get("train_eligible") or {}
    if isinstance(data, dict):
        return data, {}
    raise BuilderError(f"unrecognised manifest format: {path}")


def load_samples(train_jsonl: str) -> dict:
    out = {}
    with open(train_jsonl, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                s = json.loads(line)
                out[s["id"]] = s
    return out


def sample_tools(sample: dict, catalog: dict) -> dict:
    wanted = set()
    for app in sample["context"]["installed_apps"].values():
        wanted.update(app.get("tools", []))
    wanted.add("sys.ask_missing_info")
    out = {}
    for app in catalog["apps"]:
        for tool in app["tools"]:
            if tool["name"] in wanted:
                out[tool["name"]] = tool
    return out


def replay_gold(sample: dict, data_root: str, zaic_tools_dir: str):
    """Replay gold calls through ToolEnv. Returns (results, state_hash,
    dropped_reason or None). Validation failure -> dropped (never
    executed, never repaired)."""
    if zaic_tools_dir not in sys.path:
        sys.path.insert(0, zaic_tools_dir)
    from zaic_tools import ToolEnv
    env = ToolEnv("train", sample["id"], root=data_root)
    results = []
    for call in sample["label"]["tool_calls"]:
        check = env.validate(call["name"], call.get("arguments") or {})
        if not check.get("ok"):
            return None, None, f"validation_failed: {check.get('error')}"
        result = env.call(call["name"], call.get("arguments") or {})
        # COORDINATOR FIX 2026-10-29: a gold call that returns ok True
        # with done False did NOT execute, so the trajectory cannot pass
        # the D1 all-succeed construction filter. Previously such calls
        # were recorded as ordinary steps (repro: train_1696 built with
        # its failing send_message step). Drop, never repair.
        if isinstance(result, dict) and result.get("ok") and result.get("done") is False:
            return None, None, f"not_done: {call['name']}"
        results.append(result)
    return results, env.get_state_hash(), None


def build_gold_example(sample: dict, tools: dict, results: list,
                       state_hash: str, manifest_version: str,
                       manifest_part: str, classes: set) -> dict:
    calls = sample["label"]["tool_calls"]
    if len(calls) > CONTRACT["max_steps"]:
        return {"sample_id": sample["id"], "dropped": True,
                "reason": f"exceeds_max_steps: {len(calls)} > 12"}
    names = [c["name"] for c in calls]
    if "sys.ask_missing_info" in names and names[-1] != "sys.ask_missing_info":
        return {"sample_id": sample["id"], "dropped": True,
                "reason": "ask_not_last"}
    canon = Counter(canon_call_key(c) for c in calls)
    if canon and max(canon.values()) > CONTRACT["max_repeats"]:
        return {"sample_id": sample["id"], "dropped": True,
                "reason": "loop_guard_exceeded: identical call > 2 times"}
    base = build_base_prompt(sample, tools)
    steps = build_steps(base, calls, results)
    not_done_steps = [i for i, r in enumerate(results)
                      if isinstance(r, dict) and r.get("ok") and r.get("done") is False]
    return {
        "sample_id": sample["id"],
        "source": "gold",
        "manifest_version": manifest_version,
        "manifest_part": manifest_part,
        "classes": sorted(classes),
        "gold_kind": gold_kind(calls),
        "steps": [
            {"step": i,
             "prompt": st["prompt"],
             "target": st["target"],
             "call": st["call"],
             "prompt_chars": len(st["prompt"]),
             "target_chars": len(st["target"])}
            for i, st in enumerate(steps)
        ],
        "executed_calls": calls,
        "gold_final_state": sample["label"].get("final_state"),
        "state_hash": state_hash,
        "not_done_steps": not_done_steps,
        "dropped": False,
    }


# ---------------------------------------------------------------------------
# Tokenizer subprocess helper (venv python has transformers, no torch).
#
# FIXED 2026-10-29 (Codex repro: raw encode != runtime template ids):
# the OLD helper called tok.encode(text, add_special_tokens=False) on
# the raw prompt. That helper is DELETED, not kept as a fallback. The
# new helper tokenizes exactly like runtime llm._render: one user
# message, chat template, add_generation_prompt=True. It returns, per
# (prompt, target) pair, the rendered prompt text, the template ids,
# the runtime-path ids (encode of the rendered text, no special
# tokens) for an equality assertion, the target ids, and the
# full-conversation ids as a diagnostic only (see notes: concat is
# the correct teacher-forcing construction, full-text tokenize adds a
# trailing newline token after EOS that generation never produces).
# transformers 5.x apply_chat_template(tokenize=True) returns a
# BatchEncoding; _ids() accepts both that and a plain list.
# ---------------------------------------------------------------------------
TOKENIZER_HELPER = r'''
import json, sys
data = json.load(sys.stdin)
from transformers import AutoTokenizer
tok = AutoTokenizer.from_pretrained(data["model"], revision=data["revision"], local_files_only=True)
def _ids(out):
    return out["input_ids"] if hasattr(out, "keys") else out
results = []
for pair in data["pairs"]:
    prompt, target = pair["prompt"], pair["target"]
    rendered = tok.apply_chat_template(
        [{"role": "user", "content": prompt}], tokenize=False, add_generation_prompt=True)
    rendered_ids = _ids(tok.apply_chat_template(
        [{"role": "user", "content": prompt}], tokenize=True, add_generation_prompt=True))
    runtime_ids = tok.encode(rendered, add_special_tokens=False)
    full_ids = _ids(tok.apply_chat_template(
        [{"role": "user", "content": prompt}, {"role": "assistant", "content": target}],
        tokenize=True, add_generation_prompt=False))
    results.append({
        "rendered_prompt": rendered,
        "rendered_prompt_token_ids": rendered_ids,
        "runtime_input_ids": runtime_ids,
        "target_token_ids": tok.encode(target, add_special_tokens=False),
        "full_conversation_token_ids": full_ids,
    })
out = {"eos_token_id": tok.eos_token_id, "eos_token": tok.eos_token, "results": results}
# Flat "ids" kept ONLY so the pre-existing unit test that passes
# (prompt, target) pairs positionally keeps unpacking
# [rendered_prompt_ids, target_ids, ...] with the NEW semantics.
# It is never raw encode: every entry here is template-based.
out["ids"] = []
for r in results:
    out["ids"].append(r["rendered_prompt_token_ids"])
    out["ids"].append(r["target_token_ids"])
print(json.dumps(out))
'''


def _as_pairs(texts_or_pairs):
    """Accept pairs [(prompt, target), ...] or a flat [prompt, target,
    prompt, target, ...] list (the old test call shape). Returns a list
    of {"prompt":..., "target":...} dicts. A flat list of odd length
    is a caller bug, not something to guess at."""
    if texts_or_pairs and isinstance(texts_or_pairs[0], (list, tuple)):
        return [{"prompt": p, "target": t} for p, t in texts_or_pairs]
    if texts_or_pairs and isinstance(texts_or_pairs[0], dict):
        return texts_or_pairs
    if len(texts_or_pairs) % 2 != 0:
        raise BuilderError("batch_tokenize needs (prompt, target) pairs; odd flat list given")
    return [{"prompt": texts_or_pairs[i], "target": texts_or_pairs[i + 1]}
            for i in range(0, len(texts_or_pairs), 2)]


def batch_tokenize(tokenizer_python: str, model: str, revision: str, texts_or_pairs):
    pairs = _as_pairs(texts_or_pairs)
    proc = subprocess.run(
        [tokenizer_python, "-c", TOKENIZER_HELPER],
        input=json.dumps({"model": model, "revision": revision, "pairs": pairs}),
        capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        raise BuilderError(f"tokenizer subprocess failed: {proc.stderr[-500:]}")
    return json.loads(proc.stdout)


def attach_token_data(example: dict, token_data: dict, text_index: dict,
                      max_context_tokens: int = 16384):
    """Attach per-step token ids/counts, input_ids, labels and budget
    verdict. Production input (main) always passes token_data with a
    "results" list (one entry per (prompt, target) pair) and a
    text_index mapping ("p"/"t", sample_id, step) -> pair position.
    A legacy flat "ids" shape is still accepted ONLY for the
    pre-existing synthetic budget unit test, which feeds fake ids and
    checks budget logic, not tokenization; main() never builds that
    shape, so it is not a raw-encode fallback in production.
    Budget: rendered prompt + 512 reserved <= max_context AND full
    training sequence <= max_context; over-budget examples are
    DROPPED by the caller, never truncated. An EOS inside target ids
    is a token error (would duplicate EOS); the caller drops the
    example with reason token_error."""
    eos = token_data["eos_token_id"]
    errors = []
    for step in example["steps"]:
        pos = text_index[("p", example["sample_id"], step["step"])]
        if "results" in token_data:
            item = token_data["results"][pos]
            if text_index[("t", example["sample_id"], step["step"])] != pos:
                raise BuilderError("token index mismatch: prompt/target pair positions differ")
            r_ids = item["rendered_prompt_token_ids"]
            if r_ids != item["runtime_input_ids"]:
                raise BuilderError(
                    f"template ids != runtime ids for {example['sample_id']} step {step['step']}: "
                    "refusing to build training ids that do not match runtime")
            step["rendered_prompt"] = item["rendered_prompt"]
            t_ids = item["target_token_ids"]
            concat = r_ids + t_ids + [eos]
            step["full_conversation_match"] = (concat == item["full_conversation_token_ids"])
            step["full_conversation_extra"] = (
                item["full_conversation_token_ids"][len(concat):]
                if item["full_conversation_token_ids"][:len(concat)] == concat else None)
        else:  # legacy fake-id shape (synthetic budget test only)
            ids = token_data["ids"]
            r_ids = ids[text_index[("p", example["sample_id"], step["step"])]]
            t_ids = ids[text_index[("t", example["sample_id"], step["step"])]]
            step["rendered_prompt"] = None
            step["full_conversation_match"] = None
            step["full_conversation_extra"] = None
        if eos in t_ids:
            errors.append({"step": step["step"], "reason": "eos_in_target"})
        step["prompt_token_ids"] = r_ids  # BREAKING: rendered ids, not raw (see notes)
        step["rendered_prompt_token_ids"] = r_ids
        step["prompt_tokens"] = len(r_ids)
        step["target_token_ids"] = t_ids
        step["target_tokens"] = len(t_ids)
        step["input_ids"] = r_ids + t_ids + [eos]
        step["labels"] = [-100] * len(r_ids) + t_ids + [eos]
        step["sequence_tokens"] = len(step["input_ids"])
        step["eos_token_id"] = eos
        # Construction invariants (fail loudly, never ship bad labels):
        assert step["labels"][:len(r_ids)] == [-100] * len(r_ids), "prompt tokens must be masked"
        assert step["labels"][len(r_ids):-1] == t_ids, "target tokens must not be masked"
        assert step["labels"][-1] == eos and step["input_ids"][-1] == eos, "exactly one EOS at end"
        assert len(step["labels"]) == len(step["input_ids"]), "labels/input length mismatch"
    example["token_errors"] = errors
    over = [s["step"] for s in example["steps"]
            if s["prompt_tokens"] + CONTRACT["max_new_tokens"] > max_context_tokens
            or s["sequence_tokens"] > max_context_tokens]
    example["token_budget_over_steps"] = over
    example["budget_status"] = "over_budget" if over else "ok"


# ---------------------------------------------------------------------------
# CLI.
# ---------------------------------------------------------------------------
COVERAGE_CLASSES = ["empty_stop", "ask_only", "read_ask", "read_write",
                    "multi_step", "conditional_no_write", "direct_phone",
                    "history_dependent"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="sft_prototype_builder")
    ap.add_argument("--train-jsonl", required=True)
    ap.add_argument("--data-root", required=True)
    ap.add_argument("--zaic-tools-dir", default=None,
                    help="dir containing zaic_tools (default: <data-root>/train)")
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--part", default="inner_train")
    ap.add_argument("--manifest-version", default="unspecified")
    ap.add_argument("--ids-file", default=None)
    ap.add_argument("--select-coverage", action="store_true")
    ap.add_argument("--per-class", type=int, default=2)
    ap.add_argument("--model", default="Qwen/Qwen3-4B-Instruct-2507")
    ap.add_argument("--revision", default="cdbee75")
    ap.add_argument("--tokenizer-python", default=None)
    ap.add_argument("--max-context-tokens", type=int, default=16384,
                    help="Test hook only; default = runtime budget. Over-budget "
                         "examples are dropped, never truncated.")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    assignment, train_eligible = load_manifest(args.manifest)
    part_ids = sorted(sid for sid, part in assignment.items() if part == args.part)
    part_set = set(part_ids)
    # COORDINATOR FIX 2026-10-29: enforce train_eligible (see
    # load_manifest note). Manifests without the map treat all as
    # eligible, so v1/synthetic behaviour is unchanged.
    eligible_ids = [sid for sid in part_ids if train_eligible.get(sid, True)]
    excluded_ineligible = sorted(set(part_ids) - set(eligible_ids))
    samples = load_samples(args.train_jsonl)
    catalog = json.load(open(Path(args.data_root) / "train" / "train_tools_catalog.json",
                             encoding="utf-8"))
    kind_by_tool = {}
    for app in catalog["apps"]:
        for tool in app["tools"]:
            kind_by_tool[tool["name"]] = tool.get("kind", "")
    zaic_tools_dir = args.zaic_tools_dir or str(Path(args.data_root) / "train")

    if args.ids_file:
        wanted = [ln.strip() for ln in open(args.ids_file, encoding="utf-8") if ln.strip()]
        outside = [sid for sid in wanted if sid not in part_set]
        if outside:
            print(f"ERROR: ids outside manifest part {args.part}: {outside}; aborting, nothing built.",
                  file=sys.stderr)
            return 2
        ineligible = [sid for sid in wanted if not train_eligible.get(sid, True)]
        if ineligible:
            print(f"ERROR: ids not train-eligible in manifest: {ineligible}; aborting, nothing built.",
                  file=sys.stderr)
            return 2
        selected = wanted
        selection = {"mode": "ids", "ids": wanted}
    elif args.select_coverage:
        # Replay every part sample once for classification (CPU), then
        # greedy deterministic pick: classes in fixed order, first
        # unpicked matches in sorted-id order.
        replay_cache = {}
        classes_by_id = {}
        for sid in eligible_ids:
            results, _, reason = replay_gold(samples[sid], args.data_root, zaic_tools_dir)
            if reason is not None:
                replay_cache[sid] = (None, reason)
                classes_by_id[sid] = set()
            else:
                replay_cache[sid] = (results, None)
                classes_by_id[sid] = classify_sample(samples[sid], kind_by_tool, results)
        picked: list = []
        picked_set = set()
        per_class: dict = {}
        for cls in COVERAGE_CLASSES:
            matches = [sid for sid in eligible_ids
                       if cls in classes_by_id[sid] and sid not in picked_set]
            take = matches[:args.per_class]
            per_class[cls] = take if take else "NOT_FOUND"
            for sid in take:
                picked.append(sid)
                picked_set.add(sid)
        selected = picked
        selection = {"mode": "coverage", "per_class": args.per_class,
                     "per_class_ids": per_class,
                     "scanned_part_size": len(eligible_ids),
                     "excluded_ineligible": excluded_ineligible}
        # Stash replays so the build loop below does not replay twice.
        build_replays = {sid: replay_cache[sid] for sid in selected}
    else:
        print("ERROR: pass --ids-file or --select-coverage.", file=sys.stderr)
        return 2

    examples, dropped = [], []
    for sid in selected:
        sample = samples[sid]
        if args.select_coverage:
            results, reason = build_replays[sid]
            state_hash = None
            if reason is None:
                # Recompute hash cheaply: replay already ran; hash needs
                # a second pass only if we did not store it. Rerun once
                # (deterministic) to obtain it.
                _, state_hash, _ = replay_gold(sample, args.data_root, zaic_tools_dir)
        else:
            results, state_hash, reason = replay_gold(sample, args.data_root, zaic_tools_dir)
        if reason is not None:
            dropped.append({"sample_id": sid, "reason": reason})
            continue
        tools = sample_tools(sample, catalog)
        if args.select_coverage:
            classes = classes_by_id[sid]
        else:
            classes = classify_sample(sample, kind_by_tool, results)
        ex = build_gold_example(sample, tools, results, state_hash,
                                args.manifest_version, args.part, classes)
        if ex.get("dropped"):
            dropped.append({"sample_id": sid, "reason": ex["reason"]})
        else:
            examples.append(ex)

    token_status = "unchecked (no --tokenizer-python)"
    if args.tokenizer_python:
        pairs, index = [], {}
        for ex in examples:
            for st in ex["steps"]:
                pos = len(pairs)
                pairs.append({"prompt": st["prompt"], "target": st["target"]})
                index[("p", ex["sample_id"], st["step"])] = pos
                index[("t", ex["sample_id"], st["step"])] = pos
        token_data = batch_tokenize(args.tokenizer_python, args.model, args.revision, pairs)
        kept = []
        for ex in examples:
            attach_token_data(ex, token_data, index,
                              max_context_tokens=args.max_context_tokens)
            if ex["token_budget_over_steps"]:
                dropped.append({"sample_id": ex["sample_id"],
                                "reason": "token_budget_exceeded",
                                "steps": ex["token_budget_over_steps"]})
            elif ex.get("token_errors"):
                dropped.append({"sample_id": ex["sample_id"],
                                "reason": f"token_error: {ex['token_errors']}"})
            else:
                kept.append(ex)
        examples = kept
        token_status = f"checked with {args.tokenizer_python} ({args.model}@{args.revision})"
    else:
        for ex in examples:
            ex["budget_status"] = "unchecked"

    out = {
        "builder": "sft_prototype_builder.py",
        "contract": CONTRACT,
        "manifest": {"path": args.manifest, "version": args.manifest_version,
                     "part": args.part, "part_size": len(part_ids),
                     "eligible_part_size": len(eligible_ids)},
        "transcript_mode": "gold",
        "tokenizer": token_status,
        "selection": selection,
        "examples": examples,
        "dropped": dropped,
        "counts": {
            "selected": len(selected),
            "built": len(examples),
            "dropped": len(dropped),
            "steps": sum(len(ex["steps"]) for ex in examples),
        },
    }
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(out["counts"], ensure_ascii=False))
    print(f"selection: {json.dumps(selection, ensure_ascii=False)}")
    if dropped:
        print(f"dropped: {json.dumps(dropped, ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
