"""Official-style scorer for train labels — NOT the organiser evaluator.

The package ships no evaluator code (verified: no eval/score file in
the zip), so this scorer implements the portal description exactly as
written and labels everything beyond it UNVERIFIED:

- Per sample: score = tool-call F1 if the submitted state_hash equals
  the gold state_hash, else 0. Gold hash is obtained by REPLAYING the
  label tool_calls in a fresh diagnostic zaic_tools session (gold
  labels carry final_state, not a hash); that replay session is
  evaluation-only and never mixed into a submission.
- Tool-call F1: calls match when tool names are equal; non-fuzzy params
  must be exactly equal; fuzzy params (catalog x-match: fuzzy) match
  when token-F1 > 0.6 after lowercase + Unicode NFC; order is ignored;
  each call matches at most one call (greedy by match quality).
  Token-F1 here means F1 over whitespace tokens of the two strings.
- Empty gold scores 1 ONLY if the submitted list is also empty.
- Final score = mean over samples. Per-class breakdowns (empty /
  ask_only / ask_after / normal) are reported alongside, because a
  single mean hides ask/refuse behaviour.

UNVERIFIED (portal text does not settle these; do not present scorer
output as the official score): whether sys.ask_missing_info calls are
scored by the same F1 rule or by a special ask rule; whether read
calls count in F1 at all (this scorer counts every submitted call,
including reads and schema-rejected calls, because they are all in
the submission trace — if the evaluator excludes reads, F1 here is
pessimistic); whether a wrong `[]` vs a wrong ask differ in score.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter

from .loader import Sample, fuzzy_params


def _tokens(text: str) -> list[str]:
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


def calls_match(sub: dict, gold: dict, fuzzy: set[str]) -> bool:
    if sub.get("name") != gold.get("name"):
        return False
    s_args, g_args = sub.get("arguments") or {}, gold.get("arguments") or {}
    if set(s_args.keys()) != set(g_args.keys()):
        return False
    for key, g_val in g_args.items():
        s_val = s_args[key]
        if key in fuzzy:
            if token_f1(str(s_val), str(g_val)) <= 0.6:
                return False
        elif s_val != g_val:
            return False
    return True


def tool_f1(submitted: list[dict], gold: list[dict], fuzzy_by_tool: dict[str, set[str]]) -> float:
    """Order-ignored, one-to-one F1 over tool calls."""
    if not gold and not submitted:
        return 1.0
    if not gold or not submitted:
        return 0.0
    used = set()
    matched = 0
    for s in submitted:
        for i, g in enumerate(gold):
            if i in used:
                continue
            if calls_match(s, g, fuzzy_by_tool.get(g["name"], set())):
                used.add(i)
                matched += 1
                break
    precision = matched / len(submitted)
    recall = matched / len(gold)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def score_sample(submitted_line: dict, sample: Sample, gold_hash: str, fuzzy_by_tool: dict) -> dict:
    """Return {score, hash_correct, f1, n_submitted, n_gold}."""
    sub_calls = submitted_line["tool_calls"]
    gold_calls = sample.label["tool_calls"] if sample.label else []
    hash_correct = submitted_line["state_hash"] == gold_hash
    if not gold_calls:
        f1 = 1.0 if not sub_calls else 0.0
    else:
        f1 = tool_f1(sub_calls, gold_calls, fuzzy_by_tool)
    return {
        "score": f1 if hash_correct else 0.0,
        "hash_correct": hash_correct,
        "f1": f1,
        "n_submitted": len(sub_calls),
        "n_gold": len(gold_calls),
    }


def summarise(results: list[dict], classes: list[str]) -> dict:
    out: dict = {"n": len(results), "mean_score": 0.0, "hash_rate": 0.0, "mean_f1": 0.0}
    if not results:
        return out
    out["mean_score"] = sum(r["score"] for r in results) / len(results)
    out["hash_rate"] = sum(1 for r in results if r["hash_correct"]) / len(results)
    out["mean_f1"] = sum(r["f1"] for r in results) / len(results)
    by_class: dict[str, list[dict]] = {}
    for r, c in zip(results, classes):
        by_class.setdefault(c, []).append(r)
    out["by_class"] = {
        c: {"n": len(rs), "mean_score": sum(r["score"] for r in rs) / len(rs)}
        for c, rs in sorted(by_class.items())
    }
    return out
