"""Deterministic train dev/held-out split.

Design (per the task brief: split by real task structure, NOT by a
DataMate-style business_id — LifeMate samples have no business_id):

- Stratify by ``Sample.label_class()`` (empty / ask_only / ask_after /
  normal), because the three decision modes behave differently and a
  random split could starve the small classes (empty 111, ask_only 60
  of 1545). Within each stratum, rank samples by
  sha256(f"{seed}:{sample_id}") and take the top ``heldout_frac`` as
  held-out. No RNG, no dependence on file order: the same seed always
  gives the same split, and the split file (ids only) is committed so
  anyone can reproduce it without re-running code.
- History length is reported per subset (not a stratum) so a skew is
  visible instead of hidden.
- KNOWN LIMITATION, stated not hidden: tool-call sequences repeat
  across samples (695 distinct sequences for 1545 samples), so the
  same sequence family can appear in both dev and held-out. Held-out
  therefore measures within-family generalisation, NOT unseen-template
  generalisation. Private test also adds unseen apps (public catalog
  already shows apps absent from train), so held-out scores are an
  upper-bound-style estimate, not a private-test prediction.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

from .loader import Sample


def _rank_key(seed: int, sample_id: str) -> str:
    return hashlib.sha256(f"{seed}:{sample_id}".encode()).hexdigest()


def make_split(
    samples: list[Sample], seed: int = 42, heldout_frac: float = 0.2
) -> dict[str, str]:
    """Return {sample_id: 'dev' | 'heldout'}."""
    by_class: dict[str, list[Sample]] = {}
    for s in samples:
        by_class.setdefault(s.label_class(), []).append(s)
    out: dict[str, str] = {}
    for cls, members in by_class.items():
        members.sort(key=lambda s: _rank_key(seed, s.id))
        n_hold = round(len(members) * heldout_frac)
        for s in members[:n_hold]:
            out[s.id] = "heldout"
        for s in members[n_hold:]:
            out[s.id] = "dev"
    return out


def split_report(samples: list[Sample], assignment: dict[str, str]) -> dict:
    report: dict = {}
    for subset in ("dev", "heldout"):
        members = [s for s in samples if assignment[s.id] == subset]
        report[subset] = {
            "n": len(members),
            "by_class": dict(Counter(s.label_class() for s in members)),
            "history_turns_mean": round(
                sum(len(s.history) for s in members) / max(len(members), 1), 2
            ),
        }
    return report


def write_split(path: str | Path, assignment: dict[str, str]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(assignment, indent=1, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )


def load_split_assignment(path: str | Path) -> dict[str, str]:
    return json.loads(Path(path).read_text(encoding="utf-8"))
