"""Reproducible prompt measurement for the NEW agent (a2e832b).

This script measures the ACTUAL prompt of branch
``codex/lifemate-baseline-integration`` commit
a2e832b9bdbef63d6d7b5d1573a8d303a48f2664 — it does not simulate an
older agent, and its numbers are reported SEPARATELY from the e79f9722
control measurement (see CONTEXT_BUDGET_2026-10-28.md). The two
measurements are never pooled or averaged together.

What changed in a2e832b relative to e79f9722 (prompt-relevant only):
  - lifemate/agent.py render_observation_prompt now renders every
    result as complete compact JSON (json.dumps, ensure_ascii=False,
    separators=(",", ":")); the repr[:300] clipping is gone.
  - Outcome labels: "not_done" when ok:true but done:false, else
    ok / error as before.
  - build_base_prompt inserts ACTION_POLICY (verbatim below) after the
    instruction line, and the instruction line ends with "...or
    explicit user input."
  - Config suffix lines (selective reads, no-verification-read) and
    the chat-template wrapping are UNCHANGED: a single user message,
    the model's own chat template, add_generation_prompt=True,
    encode(add_special_tokens=False); budget = prompt + 512 <= 16384.
  - Grounding/evidence, ask early-return and stop-signal changes
    affect call validation and trace termination, not the prompt text
    of a gold-replay prefix, so they do not appear in this measurement.

Discipline / caveats (do not drop these when quoting numbers):
  - Only dev samples (lifemate/splits/train_dev_heldout.json) are used;
    held-out is never touched.
  - Transcripts are TRAIN GOLD transcripts: DIAGNOSTIC estimate, not
    real ASR prompts.
  - Gold replay creates VALID observation prefixes only. This does NOT
    cover observations from model wrong/repeated calls: a live trace
    can produce longer or more numerous observations than any gold
    trace, and can therefore exceed the budget even though gold replay
    does not.
  - Only the tokenizer is loaded (AutoTokenizer); no model weights,
    no inference, no GPU needed.
  - Data is NOT in the repo: pass --data-root pointing at the
    extracted package directory (containing train/ and public_test/).

Usage:
  python analysis/measure_context_budget_a2e832b.py --data-root <path>
      [--split-file lifemate/splits/train_dev_heldout.json]
      [--revision cdbee75] [--out summary.json]

Output: a JSON summary (token percentiles, over-budget counts with the
exceeding sample ids, breakdown means). Counts and ids only — no
prompts, no traces, no raw data.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BUDGET = 16384
RESERVED_OUTPUT = 512
OBS_HEADER = ("\n\nPrevious calls and their OBSERVED results "
              "(use these, do not repeat failed calls, do not guess new ids):\n")
SELECTIVE_LINE = "\nRead only to resolve a missing entity or precondition; reuse still-valid observations."
VERIFY_LINE = "\nDo not add a verification read after a write unless the next action needs its result."

ACTION_POLICY = """Action policy (apply to the CURRENT request, not old requests in history):
1. Identify the user's final intent, corrections, cancellations and each requested action. Do not add follow-up actions the user did not request. A cancelled sole request, chat, or an unavailable capability needs no tool call; output {"stop":true}.
2. Evaluate conditions BEFORE their dependent writes. Resolve the target date/location using current_time and context. Reuse a still-valid matching observation in history; otherwise read the needed fact first. Do not execute both branches. If the selected branch requests no action, stop.
3. Resolve entities BEFORE acting. Use catalog x-ref IDs from matching observed collections or an ID explicitly provided by the user. Names are not IDs. Read/search when an entity is not yet resolved. One returned entity is not proof of user intent: check name/relation/room and the request. Several candidates require a unique explicit discriminator or sys.ask_missing_info; do not pick the first.
4. Every argument needs evidence: the user's request/context, applicable history, a tool result, a schema default, or a calculation from those facts. Never invent phone numbers, amounts or dates/times. Read a bill/balance/event when the request refers to its value. Missing required information that cannot be obtained by a relevant read must be asked using sys.ask_missing_info with the exact tool_name and missing params. Do not assume the current time is a requested reminder time.
5. Tool results with done:false did NOT complete the requested action even if ok:true. Change the plan using evidence; do not repeat the same failed call. A created reminder is not a completed reminder: do not mark it done unless the user requested completion. A condition written into a label does not make an immediate write conditional.
6. After all requested actions of the selected branch succeed, output {"stop":true}. Do not undo, mark complete, recreate or verify writes without a separate need in this request. Repeat an identical action only if the user explicitly requested multiple instances; otherwise avoid duplicate calls. sys.ask_missing_info ends this turn while waiting for the user.
Output exactly one tool-call JSON or {"stop":true}; no invented tool named stop, no narrative, no list of calls."""


# --- prompt construction (port of branch agent.py @ a2e832b) ---

def build_base_prompt(sample: dict, transcript: str, tools: dict) -> str:
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
                                 "returns": spec.get("returns", "")}, ensure_ascii=False))
    lines.append("Conversation history:")
    for turn in sample.get("history", []):
        if turn["role"] == "user":
            text = turn.get("audio_text") if turn.get("audio_text") is not None else "[audio, no transcript available]"
            lines.append(f"user: {text}")
        else:
            lines.append(f"assistant: {turn.get('text') or ''} calls={json.dumps(turn.get('tool_calls', []), ensure_ascii=False)} "
                         f"results={turn.get('tool_results')!r}")
    lines.append(f"Current user request (transcript): {transcript}")
    return "\n".join(lines)


def obs_line(call: dict, result: dict) -> str:
    outcome = ("not_done" if result.get("ok") and result.get("done") is False else
               "ok" if result.get("ok") else f"error: {result.get('error')}")
    output = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
    return f"- {call['name']}({call['arguments']}) -> {outcome}; output={output}"


def render_prompt(base: str, executed: list, results: list) -> str:
    if not executed:
        return base
    return base + OBS_HEADER + "\n".join(obs_line(c, r) for c, r in zip(executed, results))


def pct(sorted_vals, q):
    if not sorted_vals:
        return 0
    return sorted_vals[min(len(sorted_vals) - 1, int(q * len(sorted_vals)))]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", required=True)
    ap.add_argument("--split-file", default=None)
    ap.add_argument("--revision", default="cdbee75")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained("Qwen/Qwen3-4B-Instruct-2507", revision=args.revision)

    def n_tokens(text: str) -> int:
        rendered = tok.apply_chat_template([{"role": "user", "content": text}],
                                           tokenize=False, add_generation_prompt=True)
        return len(tok.encode(rendered, add_special_tokens=False))

    data_root = Path(args.data_root)
    split_file = Path(args.split_file) if args.split_file else Path(__file__).resolve().parent.parent / "lifemate/splits/train_dev_heldout.json"
    split = json.loads(split_file.read_text(encoding="utf-8"))
    dev_ids = sorted(i for i, v in split.items() if v == "dev")

    with open(data_root / "train" / "train_tools_catalog.json", encoding="utf-8") as f:
        catalog = json.load(f)
    samples = {}
    with open(data_root / "train" / "train.jsonl", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                raw = json.loads(line)
                samples[raw["id"]] = raw

    sys.path.insert(0, str(data_root / "train"))
    import zaic_tools

    policy_tokens = len(tok.encode(ACTION_POLICY, add_special_tokens=False))
    step_tokens, sample_max = [], []
    over_samples, over_steps = [], 0
    seg_tot = {"instr_policy_ctx": 0, "catalog": 0, "history": 0, "request": 0, "suffix": 0}
    obs_final = []
    for sid in dev_ids:
        sample = samples[sid]
        installed = []
        for app in sample["context"]["installed_apps"].values():
            installed.extend(app.get("tools", []))
        if "sys.ask_missing_info" not in installed:
            installed.append("sys.ask_missing_info")
        wanted = set(installed)
        tools = {}
        for app in catalog["apps"]:
            for tool in app["tools"]:
                if tool["name"] in wanted:
                    tools[tool["name"]] = tool
        base = build_base_prompt(sample, sample.get("audio_text"), tools) + SELECTIVE_LINE + VERIFY_LINE
        base_lines = base.split("\n")
        tools_start = next(i for i, ln in enumerate(base_lines) if ln.startswith("Tools you may call"))
        hist_start = next(i for i, ln in enumerate(base_lines) if ln == "Conversation history:")
        # Corrected 2026-10-28: the request line is NOT the last line — the
        # two config suffix lines follow it. The old slicing
        # (history = lines[hist_start:-1], request = lines[-1]) put the
        # request + selective lines inside "history" and reported the
        # verify line as "request". The partition below reconstructs
        # base exactly ("\n".join of the segments == base); full-prompt
        # token counts are unaffected by this fix.
        req_idx = next(i for i, ln in enumerate(base_lines) if ln.startswith("Current user request (transcript):"))
        seg_tot["instr_policy_ctx"] += len(tok.encode("\n".join(base_lines[:tools_start]), add_special_tokens=False))
        seg_tot["catalog"] += len(tok.encode("\n".join(base_lines[tools_start:hist_start]), add_special_tokens=False))
        seg_tot["history"] += len(tok.encode("\n".join(base_lines[hist_start:req_idx]), add_special_tokens=False))
        seg_tot["request"] += len(tok.encode(base_lines[req_idx], add_special_tokens=False))
        seg_tot["suffix"] += len(tok.encode("\n".join(base_lines[req_idx + 1:]), add_special_tokens=False))

        gold = sample["label"]["tool_calls"]
        env = zaic_tools.ToolEnv("train", sid, root=str(data_root))
        results = [env.call(c["name"], c["arguments"]) for c in gold]
        executed = [{"name": c["name"], "arguments": c["arguments"]} for c in gold]
        mx, over = 0, 0
        steps = []
        for k in range(len(gold) + 1):
            n = n_tokens(render_prompt(base, executed[:k], results[:k]))
            steps.append(n)
            step_tokens.append(n)
            mx = max(mx, n)
            if n + RESERVED_OUTPUT > BUDGET:
                over += 1
        sample_max.append(mx)
        over_steps += over
        if over:
            over_samples.append(sid)
        # final-prefix observation section = final prompt minus base prompt
        obs_final.append(steps[-1] - steps[0])

    n = len(dev_ids)
    summary = {
        "agent_commit": "a2e832b9bdbef63d6d7b5d1573a8d303a48f2664",
        "samples": n, "budget": BUDGET, "reserved_output": RESERVED_OUTPUT,
        "tokenizer": "Qwen/Qwen3-4B-Instruct-2507", "revision": args.revision,
        "action_policy_standalone_tokens": policy_tokens,
        "per_sample_max": {"p50": pct(sorted(sample_max), 0.5), "p90": pct(sorted(sample_max), 0.9),
                           "p99": pct(sorted(sample_max), 0.99), "max": max(sample_max)},
        "per_step": {"n": len(step_tokens), "p50": pct(sorted(step_tokens), 0.5),
                     "p90": pct(sorted(step_tokens), 0.9), "p99": pct(sorted(step_tokens), 0.99),
                     "max": max(step_tokens)},
        "over_budget_samples": over_samples, "over_budget_steps": over_steps,
        "breakdown_mean_final_prefix": {k: round(v / n) for k, v in seg_tot.items()},
        "observation_section_mean_final_prefix": round(sum(x for x in obs_final if x is not None) / n),
        "caveats": [
            "Transcripts are train GOLD transcripts: diagnostic estimate, not real ASR prompts.",
            "Gold replay creates valid observation prefixes only; it does NOT cover observations from model wrong/repeated calls.",
        ],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.out:
        Path(args.out).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
