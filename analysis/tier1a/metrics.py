"""Tier 1a metrics — stdlib only, frozen normalisation (stream-C §6).

WER normalisation, frozen before any model run:
  lowercase; strip punctuation; collapse whitespace;
  KEEP Vietnamese diacritics (no accent stripping, no tone normalisation);
  a digit string stays ONE token (e.g. 0901234567 = 1 token).

Slot: every [0-9]+ run in the gold current transcript. A slot is correct
iff that exact string occurs intact in the ASR transcript.
"""
from __future__ import annotations

import random
import re
import string

_DIGIT_RE = re.compile(r"[0-9]+")
_PUNCT = str.maketrans("", "", string.punctuation + "«»“”‘’")


def normalize(text: str) -> list[str]:
    """Frozen tokenisation for WER. Digit runs are already single tokens
    because tokenisation splits on whitespace only after punctuation removal."""
    if not text:
        return []
    cleaned = text.lower().translate(_PUNCT)
    return cleaned.split()


def _levenshtein_sdi(ref: list[str], hyp: list[str]) -> tuple[int, int, int]:
    """Token-level edit distance returning (substitutions, deletions, insertions)."""
    n, m = len(ref), len(hyp)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        dp[i][0] = i
    for j in range(1, m + 1):
        dp[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost = 0 if ref[i - 1] == hyp[j - 1] else 1
            dp[i][j] = min(dp[i - 1][j] + 1, dp[i][j - 1] + 1, dp[i - 1][j - 1] + cost)
    # Backtrack to split S/D/I.
    s = d = ins = 0
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0 and ref[i - 1] == hyp[j - 1]:
            i -= 1
            j -= 1
        elif i > 0 and j > 0 and dp[i][j] == dp[i - 1][j - 1] + 1:
            s += 1
            i -= 1
            j -= 1
        elif i > 0 and dp[i][j] == dp[i - 1][j] + 1:
            d += 1
            i -= 1
        else:
            ins += 1
            j -= 1
    return s, d, ins


def wer(ref_text: str, hyp_text: str) -> dict:
    """Return {wer, S, D, I, N} over the current turn only."""
    ref, hyp = normalize(ref_text), normalize(hyp_text)
    s, d, ins = _levenshtein_sdi(ref, hyp)
    n = len(ref)
    return {"wer": (s + d + ins) / n if n else 0.0, "S": s, "D": d, "I": ins, "N": n}


def slot_error(gold_text: str, hyp_text: str) -> dict:
    """Slot = each [0-9]+ run in gold. Correct iff intact in hyp text."""
    slots = _DIGIT_RE.findall(gold_text or "")
    if not slots:
        return {"slot_error_rate": None, "n_slots": 0, "n_correct": 0}
    # Compare against the raw hyp string (digit runs are punctuation-free).
    hyp_slots = set(_DIGIT_RE.findall(hyp_text or ""))
    correct = sum(1 for s in slots if s in hyp_slots)
    return {
        "slot_error_rate": 1.0 - correct / len(slots),
        "n_slots": len(slots),
        "n_correct": correct,
    }


def attribution_bool(gold_ok: list[bool], asr_ok: list[bool]) -> dict:
    """Per-sample attribution (stream-C §6.3). Correctness here is
    score == 1.0 (fully correct: hash matches AND tool F1 = 1.0).
    Raw per-sample scores are always reported alongside, so this
    binarisation never hides partial credit."""
    """gold_ok = correct with gold transcript; asr_ok = correct with ASR."""
    assert len(gold_ok) == len(asr_ok)
    both = sum(1 for g, a in zip(gold_ok, asr_ok) if g and a)
    gold_only = sum(1 for g, a in zip(gold_ok, asr_ok) if g and not a)
    asr_only = sum(1 for g, a in zip(gold_ok, asr_ok) if not g and a)
    neither = sum(1 for g, a in zip(gold_ok, asr_ok) if not g and not a)
    n_gold_ok = sum(gold_ok)
    return {
        "n": len(gold_ok),
        "correct_both": both,
        "correct_gold_only_asr_error_propagated": gold_only,
        "correct_asr_only": asr_only,
        "wrong_both_llm_agent": neither,
        # propagation_rate = P(wrong with ASR | right with gold)
        "propagation_rate": (gold_only / n_gold_ok) if n_gold_ok else None,
        "wrong_both_share_of_all_wrong": (
            neither / (gold_only + asr_only + neither)
            if (gold_only + asr_only + neither)
            else None
        ),
    }


def bootstrap_paired_ci(
    a: list[float], b: list[float], n_resamples: int = 10000, seed: int = 20261030
) -> dict:
    """Paired bootstrap CI for mean(a) - mean(b), percentile 2.5-97.5."""
    assert len(a) == len(b) and a
    rng = random.Random(seed)
    n = len(a)
    diffs = [x - y for x, y in zip(a, b)]
    mean_diff = sum(diffs) / n
    boots = []
    for _ in range(n_resamples):
        boots.append(sum(rng.choice(diffs) for _ in range(n)) / n)
    boots.sort()
    lo = boots[int(0.025 * n_resamples)]
    hi = boots[int(0.975 * n_resamples)]
    return {
        "mean_diff": mean_diff,
        "ci_low": lo,
        "ci_high": hi,
        "ci_excludes_zero": not (lo <= 0.0 <= hi),
        "n_resamples": n_resamples,
        "seed": seed,
    }
