"""Reproducible context-budget + information-preservation measurement.

What this measures (read this before re-running):
  For every dev sample, replay the GOLD tool calls through the shipped
  zaic_tools package (diagnostic only, never agent input) to obtain the
  observation prefixes the branch agent would have seen, rebuild the
  prompt EXACTLY as the branch agent builds it, and tokenize it with
  the real Qwen3-4B-Instruct-2507 tokenizer at revision cdbee75.

Prompt construction ported (not copied from main) from branch
``codex/lifemate-baseline-integration`` commit
e79f972206e26282e7ebddb2c5eda095d44dcf7c:
  - lifemate/agent.py: build_base_prompt + render_observation_prompt
    (line format, observation header, config suffix lines from
    lifemate/configs/recommended.json: selective_reads=true,
    verification_read_after_write=false).
  - lifemate/llm.py _render: a single user message, the model's own
    chat template, add_generation_prompt=True,
    encode(add_special_tokens=False); budget = prompt + 512 <= 16384.
  - lifemate/loader.py: catalog_tools_for_sample (sample's installed
    tools + sys.ask_missing_info only; never the full split catalog).

Renderers compared (observation line format is identical; only the
``output=`` rendering differs):
  (a) current:  repr(result)[:300] + "..." when longer than 300 chars.
  (b) fulljson: json.dumps(result, ensure_ascii=False,
      separators=(",", ":")) with no cut. This is also the proposal.
  (c) proposed: identical to (b) BY DESIGN — the measurement shows
      full JSON fits the budget on all of dev, so no budget mechanism
      is needed. The script reports (c) as a separate column so the
      three-way comparison is explicit; (c) == (b) token-for-token.

Discipline / caveats (do not drop these when quoting numbers):
  - Only dev samples (lifemate/splits/train_dev_heldout.json) are used;
    held-out is never touched.
  - Transcripts are TRAIN GOLD transcripts (sample.audio_text). These
    numbers are a DIAGNOSTIC estimate, not a measurement of real ASR
    prompts: ASR errors change transcript length and content.
  - Gold replay creates VALID observation prefixes only. At each step
    only information that appeared before that step is used; nothing
    is selected using gold answers. The renderers themselves never see
    gold: (b)/(c) keep every field of every result, with no deletion
    list (FREE_TEXT_KEYS is never used as a deletion list) and no
    shortening of lists to id/name pairs.
  - No model weights are downloaded and no inference runs: only the
    tokenizer is loaded (AutoTokenizer). No GPU is needed.
  - Data is NOT in the repo: pass --data-root pointing at the
    extracted package directory (the one containing train/ and
    public_test/ with train.jsonl, train_tools_catalog.json and
    zaic_tools/).

Usage:
  python analysis/measure_context_budget.py --data-root <path>
      [--split-file lifemate/splits/train_dev_heldout.json]
      [--revision cdbee75] [--out summary.json]

Output: a JSON summary (token percentiles, over-budget counts,
breakdown means, preservation tables, truncation description). It
contains counts and sample ids only — no prompts, no traces, no raw
data — so it is safe to keep or share.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

BUDGET = 16384
RESERVED_OUTPUT = 512
OBS_HEADER = ("\n\nPrevious calls and their OBSERVED results "
              "(use these, do not repeat failed calls, do not guess new ids):\n")
SELECTIVE_LINE = "\nRead only to resolve a missing entity or precondition; reuse still-valid observations."
VERIFY_LINE = "\nDo not add a verification read after a write unless the next action needs its result."
PHONE_RE = re.compile(r"^(\+84|0)\d{8,10}$")


# --- prompt construction (port of branch agent.py @ e79f9722) ---

def build_base_prompt(sample: dict, transcript: str, tools: dict) -> str:
    ctx = sample["context"]
    profile = ctx.get("user_profile", {})
    lines = [
        "You are a Vietnamese voice assistant. Output exactly one JSON "
        "object per turn: {\"name\": \"<tool>\", \"arguments\": {...}} or "
        "{\"stop\": true} when done. Never invent ids: use only ids from "
        "previous tool results in this conversation.",
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


def render_output(result: dict, mode: str) -> str:
    if mode == "current":
        s = repr(result)
        return s[:300] + "..." if len(s) > 300 else s
    # "fulljson" and "proposed" are the same rendering by design.
    return json.dumps(result, ensure_ascii=False, separators=(",", ":"))


def obs_line(call: dict, result: dict, mode: str) -> str:
    outcome = "ok" if result.get("ok") else f"error: {result.get('error')}"
    return f"- {call['name']}({call['arguments']}) -> {outcome}; output={render_output(result, mode)}"


def render_prompt(base: str, executed: list, results: list, mode: str) -> str:
    if not executed:
        return base
    return base + OBS_HEADER + "\n".join(obs_line(c, r, mode) for c, r in zip(executed, results))


# --- preservation helpers ---

def leaves(value, key=None):
    if isinstance(value, dict):
        for k, v in value.items():
            yield from leaves(v, k)
    elif isinstance(value, list):
        for v in value:
            yield from leaves(v, key)
    elif isinstance(value, (str, int, float, bool)) and value is not None:
        yield (key, value if isinstance(value, str) else json.dumps(value, ensure_ascii=False))


def classify(param: str, value, enum_values: set) -> str:
    p = param.lower()
    if p.endswith("_id") or p in ("id", "chat_id"):
        return "id"
    if "phone" in p or (isinstance(value, str) and PHONE_RE.match(value.strip())):
        return "phone"
    if p in ("amount", "money") or "amount" in p:
        return "amount"
    if any(t in p for t in ("time", "date", "start", "end", "datetime", "day")):
        return "time"
    if param in enum_values:
        return "enum"
    if any(t in p for t in ("location", "pickup", "dropoff", "address", "city", "place")):
        return "location"
    if p in ("content", "body", "message", "subject", "note", "title", "text"):
        return "content"
    return "other"


def pct(sorted_vals, q):
    if not sorted_vals:
        return 0
    return sorted_vals[min(len(sorted_vals) - 1, int(q * len(sorted_vals)))]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", required=True, help="extracted package dir (contains train/ and public_test/)")
    ap.add_argument("--split-file", default=None,
                    help="default: <repo-root>/lifemate/splits/train_dev_heldout.json")
    ap.add_argument("--revision", default="cdbee75")
    ap.add_argument("--out", default=None, help="write JSON summary here (default: print only)")
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
    enums = {}
    for app in catalog["apps"]:
        for tool in app["tools"]:
            for pname, pspec in tool["parameters"].get("properties", {}).items():
                if "enum" in pspec:
                    enums[(tool["name"], pname)] = set(pspec["enum"])

    # The shipped zaic_tools package: the ONLY legal state access.
    sys.path.insert(0, str(data_root / "train"))
    import zaic_tools

    modes = ("current", "fulljson", "proposed")
    step_tokens = {m: [] for m in modes}
    sample_max = {m: [] for m in modes}
    over_steps = {m: 0 for m in modes}
    over_samples = {m: 0 for m in modes}
    seg_tot = {"instr_ctx": 0, "catalog": 0, "history": 0, "request": 0, "suffix": 0,
               "obs_current": 0, "obs_fulljson": 0}
    need_by_type = {}
    cov_by_key = {}
    trunc_obs = 0
    total_calls = 0
    trunc_repr_lens = []
    lost_top_keys = {}
    repeated = []

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
        seg_tot["instr_ctx"] += len(tok.encode("\n".join(base_lines[:tools_start]), add_special_tokens=False))
        seg_tot["catalog"] += len(tok.encode("\n".join(base_lines[tools_start:hist_start]), add_special_tokens=False))
        seg_tot["history"] += len(tok.encode("\n".join(base_lines[hist_start:req_idx]), add_special_tokens=False))
        seg_tot["request"] += len(tok.encode(base_lines[req_idx], add_special_tokens=False))
        seg_tot["suffix"] += len(tok.encode("\n".join(base_lines[req_idx + 1:]), add_special_tokens=False))

        gold = sample["label"]["tool_calls"]
        env = zaic_tools.ToolEnv("train", sid, root=str(data_root))
        results = [env.call(c["name"], c["arguments"]) for c in gold]
        executed = [{"name": c["name"], "arguments": c["arguments"]} for c in gold]
        total_calls += len(gold)

        seen = set()
        for c in gold:
            kk = json.dumps(c, sort_keys=True, ensure_ascii=False)
            if kk in seen:
                repeated.append(sid)
                break
            seen.add(kk)

        for mode in modes:
            mx = 0
            over = 0
            for k in range(len(gold) + 1):
                p = render_prompt(base, executed[:k], results[:k], mode)
                n = n_tokens(p)
                step_tokens[mode].append(n)
                mx = max(mx, n)
                if n + RESERVED_OUTPUT > BUDGET:
                    over += 1
            sample_max[mode].append(mx)
            over_steps[mode] += over
            if over:
                over_samples[mode] += 1

        if executed:
            seg_tot["obs_current"] += len(tok.encode(
                OBS_HEADER + "\n".join(obs_line(c, r, "current") for c, r in zip(executed, results)), add_special_tokens=False))
            seg_tot["obs_fulljson"] += len(tok.encode(
                OBS_HEADER + "\n".join(obs_line(c, r, "fulljson") for c, r in zip(executed, results)), add_special_tokens=False))

        # M1: observation-derived arg values, survival at decision step
        for k in range(1, len(gold)):
            for param, val in (gold[k]["arguments"] or {}).items():
                if not isinstance(val, (str, int, float, bool)):
                    continue
                vstr = val if isinstance(val, str) else json.dumps(val, ensure_ascii=False)
                holders = [j for j in range(k) if vstr in [s for _, s in leaves(results[j])]]
                if not holders:
                    continue
                ftype = classify(param, val, enums.get((gold[k]["name"], param), set()))
                entry = need_by_type.setdefault(ftype, {"total": 0, "lost_current": 0, "lost_fulljson": 0, "lost_proposed": 0})
                entry["total"] += 1
                for mode, key in (("current", "lost_current"), ("fulljson", "lost_fulljson"), ("proposed", "lost_proposed")):
                    lines = [obs_line(executed[j], results[j], mode) for j in range(k)]
                    if not any(vstr in lines[j] for j in holders):
                        entry[key] += 1
        # M2: every observation leaf scalar at final prefix
        if executed:
            lines_c = [obs_line(c, r, "current") for c, r in zip(executed, results)]
            lines_f = [obs_line(c, r, "fulljson") for c, r in zip(executed, results)]
            for j, res in enumerate(results):
                for key, vstr in leaves(res):
                    if vstr == "" or len(vstr) < 2:
                        continue
                    e = cov_by_key.setdefault(key, {"total": 0, "lost_current": 0, "lost_fulljson": 0})
                    e["total"] += 1
                    if vstr not in lines_c[j]:
                        e["lost_current"] += 1
                    if vstr not in lines_f[j]:
                        e["lost_fulljson"] += 1
        # truncation description for (a)
        for res in results:
            r = repr(res)
            if len(r) > 300:
                trunc_obs += 1
                trunc_repr_lens.append(len(r))
                if isinstance(res, dict):
                    for key in res:
                        if r.find(repr(key)) >= 300:
                            lost_top_keys[key] = lost_top_keys.get(key, 0) + 1

    n = len(dev_ids)
    summary = {
        "samples": n, "total_gold_calls": total_calls, "budget": BUDGET, "reserved_output": RESERVED_OUTPUT,
        "tokenizer": "Qwen/Qwen3-4B-Instruct-2507", "revision": args.revision,
        "per_sample_max": {m: {"p50": pct(sorted(sample_max[m]), 0.5), "p90": pct(sorted(sample_max[m]), 0.9),
                                "p99": pct(sorted(sample_max[m]), 0.99), "max": max(sample_max[m])} for m in modes},
        "per_step": {m: {"n": len(step_tokens[m]), "p50": pct(sorted(step_tokens[m]), 0.5),
                          "p90": pct(sorted(step_tokens[m]), 0.9), "p99": pct(sorted(step_tokens[m]), 0.99),
                          "max": max(step_tokens[m])} for m in modes},
        "over_budget_samples": over_samples, "over_budget_steps": over_steps,
        "breakdown_mean_final_prefix": {k: round(v / n) for k, v in seg_tot.items()},
        "preservation_M1_by_type": need_by_type,
        "preservation_M2_by_key": cov_by_key,
        "truncated_observations_current": trunc_obs,
        "truncated_repr_len": {"p50": pct(sorted(trunc_repr_lens), 0.5), "p90": pct(sorted(trunc_repr_lens), 0.9),
                               "max": max(trunc_repr_lens) if trunc_repr_lens else 0},
        "fully_lost_top_level_keys_current": lost_top_keys,
        "samples_with_repeated_gold_call": sorted(set(repeated)),
        "caveats": [
            "Transcripts are train GOLD transcripts: diagnostic estimate, not real ASR prompts.",
            "Gold replay creates valid observation prefixes only; model traces with wrong/repeated calls may differ.",
            "M2 boolean leaves measured in JSON form (true/false) do not match Python repr (True/False); exclude boolean keys before comparing against (a).",
            "A (fulljson) 'loss' on a content leaf containing a newline is a JSON-escaping artifact: the value is present escaped, not lost.",
        ],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.out:
        Path(args.out).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
