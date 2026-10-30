"""Frozen metrics for four-arm scoring (stdlib only).

Definitions are the Tier 1a frozen definitions
(analysis/tier1a/metrics.py in the tier1a-kaggle worktree), restated
here because this worktree cannot import from that worktree and
lifemate/ contains no WER/slot/bootstrap code. Changing any of these
definitions after a real run starts would invalidate comparability;
they are frozen before any model output.

WER normalisation: lowercase, strip punctuation, collapse
whitespace, KEEP Vietnamese diacritics, a digit string stays ONE
token. Slot: every [0-9]+ run in the gold current transcript;
correct iff that exact string occurs intact in the arm transcript.
Paired bootstrap: 10,000 resamples, seed 20261030, 2.5-97.5
percentiles, on per-sample paired differences.
"""
from __future__ import annotations

import random
import re
import string

_DIGIT_RE = re.compile(r"[0-9]+")
_PUNCT = str.maketrans("", "", string.punctuation + "«»“”‘’")


def normalize(text):
    if not text:
        return []
    return text.lower().translate(_PUNCT).split()


def _levenshtein_sdi(ref, hyp):
    n, m = len(ref), len(hyp)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        dp[i][0] = i
    for j in range(1, m + 1):
        dp[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost = 0 if ref[i - 1] == hyp[j - 1] else 1
            dp[i][j] = min(dp[i - 1][j] + 1, dp[i][j - 1] + 1,
                           dp[i - 1][j - 1] + cost)
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


def wer(ref_text, hyp_text):
    ref, hyp = normalize(ref_text), normalize(hyp_text)
    s, d, ins = _levenshtein_sdi(ref, hyp)
    n = len(ref)
    return {"wer": (s + d + ins) / n if n else 0.0, "S": s, "D": d,
            "I": ins, "N": n}


def slot_error(gold_text, hyp_text):
    slots = _DIGIT_RE.findall(gold_text or "")
    if not slots:
        return {"slot_error_rate": None, "n_slots": 0, "n_correct": 0}
    hyp_slots = set(_DIGIT_RE.findall(hyp_text or ""))
    correct = sum(1 for s in slots if s in hyp_slots)
    return {"slot_error_rate": 1.0 - correct / len(slots),
            "n_slots": len(slots), "n_correct": correct}


def bootstrap_paired_ci(a, b, n_resamples=10000, seed=20261030):
    """Paired bootstrap CI for mean(a) - mean(b). a and b are
    per-sample scores in the SAME sample order (paired by sample)."""
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
    return {"mean_diff": mean_diff, "ci_low": lo, "ci_high": hi,
            "ci_excludes_zero": not (lo <= 0.0 <= hi),
            "n_resamples": n_resamples, "seed": seed}
