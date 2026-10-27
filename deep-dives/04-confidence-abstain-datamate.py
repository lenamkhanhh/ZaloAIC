"""Confidence measurement and abstention for DataMate (Zalo AI Challenge 2026).

Topic 4 companion code: self-consistency consensus, calibration on a
train-derived calibration split, and the code-level separation between
``unanswerable`` (deterministic lack of data) and ``abstain`` (probabilistic
lack of confidence).

Design constraints honoured by this module:

* Standard library only. No API calls, no model, no GPU, no network.
  The caller supplies an ``executor`` callable that runs one generated
  program (SQL or Python) and returns its output. That keeps this module
  testable offline and keeps the deployment stack (vLLM, DuckDB, ...)
  out of the decision logic.
* The decision (answer / unanswerable / abstain) is kept separate from
  the submission encoding. How ``unanswerable`` is scored by the official
  evaluator is UNVERIFIED at the time of writing (see the companion
  report, section 5.3); the encoder therefore takes its mapping as an
  explicit argument instead of burying an assumption in the code.
* No accuracy numbers are invented here. The ``__main__`` demo uses
  hand-written fake executors purely to show the three decision paths.

Usage outline (deployment, not executed here)::

    decision = decide_question(
        question=...,
        required_tables=..., required_columns=..., rulebook=...,
        candidates=[code_1, code_2, code_3],
        executor=run_one_program,
        thresholds=locked_thresholds,  # learned on train_cal, never on public test
    )
    line = encode_decision(decision, unanswerable_encoding="UNANSWERABLE")
"""

from __future__ import annotations

import json
import math
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Optional, Sequence

DecisionKind = Literal["answer", "unanswerable", "abstain"]

# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CandidateResult:
    """Outcome of executing one generated program.

    ``output`` is the program's executed value (number, string, list,
    table-as-list-of-dicts, ...). ``error`` is None on success. A timed-out
    or failed candidate carries ``output=None`` and a non-empty ``error``;
    it never participates in consensus counting.
    """

    code: str
    output: Any = None
    error: Optional[str] = None

    @property
    def succeeded(self) -> bool:
        return self.error is None


@dataclass(frozen=True)
class Decision:
    """One final decision for one question.

    ``kind`` is the decision itself; ``value`` is only meaningful when
    ``kind == "answer"``. ``reasons`` is an audit trail for the Docker
    rerun reconciliation (which candidates agreed, which gates passed or
    failed, which threshold applied). It is never empty for abstain /
    unanswerable decisions: a silent "no answer" is a bug, not a policy.
    """

    kind: DecisionKind
    value: Any = None
    reasons: tuple[str, ...] = ()
    consensus_fraction: Optional[float] = None


@dataclass(frozen=True)
class SchemaCoverage:
    """Deterministic result of the schema/rulebook check (section 5).

    ``missing_tables`` / ``missing_columns`` / ``missing_rules`` are the
    required items that could not be found in the business data or in
    the split's rulebook. ``fallback_tried`` records whether a full-schema
    fallback was attempted before concluding anything is missing: a
    missing conclusion drawn from a single failed shortlist lookup is
    not trusted (see ``decide_unanswerable``).
    """

    missing_tables: tuple[str, ...] = ()
    missing_columns: tuple[str, ...] = ()
    missing_rules: tuple[str, ...] = ()
    fallback_tried: bool = False

    @property
    def is_complete(self) -> bool:
        return not (self.missing_tables or self.missing_columns or self.missing_rules)


@dataclass(frozen=True)
class CalibrationRecord:
    """One question with a known outcome, used only on train splits.

    ``score`` is the calibrated-score input (see ``combined_score``).
    ``question_type`` is the answer type (number, percent, string, date,
    boolean, list, table, ...). ``correct`` is known only on train_cal /
    train_holdout; it is never available for public test in this design.
    """

    score: float
    question_type: str
    correct: bool
    answered: bool = True  # False means the system abstained on this item.


# ---------------------------------------------------------------------------
# Output canonicalisation: compare execution outputs, not code text
# ---------------------------------------------------------------------------


def canonicalise_output(value: Any) -> Any:
    """Return a hashable, normalised form of an executed output.

    Normalisation rules (comparison heuristic for consensus only -- NOT
    a claim about the official evaluator's normalisation, which is
    unverified):

    * numbers: rounded to 2 decimal places (DataMate answers are
      reported to 2dp in the prior portal notes; rounding here only
      decides whether two candidates "agree");
    * strings: NFC, lowercased, punctuation collapsed to single spaces;
    * lists: order preserved (ranking questions are order-sensitive);
    * tables (list of dicts): column names normalised the same way as
      strings, rows kept as a set of JSON strings (row order is not
      treated as meaningful for tables).
    """

    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return repr(value)
        return round(float(value), 2)
    if isinstance(value, str):
        text = unicodedata.normalize("NFC", value).lower()
        text = "".join(ch if ch.isalnum() else " " for ch in text)
        return " ".join(text.split())
    if isinstance(value, (list, tuple)):
        if value and all(isinstance(row, dict) for row in value):
            rows = {
                json.dumps(
                    {canonicalise_output(k): canonicalise_output(v) for k, v in row.items()},
                    sort_keys=True,
                    ensure_ascii=False,
                )
                for row in value
            }
            return ("table", tuple(sorted(rows)))
        return ("list", tuple(canonicalise_output(v) for v in value))
    if isinstance(value, dict):
        return ("dict", tuple(sorted((canonicalise_output(k), canonicalise_output(v)) for k, v in value.items())))
    return ("other", repr(value))


def outputs_equal(a: Any, b: Any) -> bool:
    """Whether two executed outputs count as the same answer."""

    return canonicalise_output(a) == canonicalise_output(b)


# ---------------------------------------------------------------------------
# Consensus: k candidates, executed outputs, majority with audit trail
# ---------------------------------------------------------------------------


def decide_consensus(results: Sequence[CandidateResult]) -> Decision:
    """Decide from executed candidates alone (before independent gates).

    Rules (companion report, section 2.3):

    * only successfully executed outputs vote;
    * 3/3 or 2/3 agreement on the canonicalised output -> provisional answer;
    * all outputs different, or no output at all -> abstain (an execution
      failure is NOT evidence that the data is missing, so it is never
      mapped to ``unanswerable`` here);
    * an agreed-upon empty output (no rows / empty value) is NOT an
      answer: it may be a wrong filter rather than genuinely empty data,
      so it abstains pending an evidence check by the caller.
    """

    succeeded = [r for r in results if r.succeeded]
    if not succeeded:
        return Decision(kind="abstain", reasons=("all candidates failed or timed out",))

    counts: Counter = Counter(canonicalise_output(r.output) for r in succeeded)
    best_key, best_count = counts.most_common(1)[0]
    fraction = best_count / len(succeeded)

    # Recover one representative raw output for the winning key.
    representative = next(r.output for r in succeeded if canonicalise_output(r.output) == best_key)

    if best_count >= 2 and len(succeeded) >= 2:
        if representative is None or (isinstance(representative, (list, tuple)) and len(representative) == 0):
            return Decision(
                kind="abstain",
                consensus_fraction=fraction,
                reasons=(f"consensus {best_count}/{len(succeeded)} on an empty output; needs an evidence check",),
            )
        dissent = [r for r in succeeded if canonicalise_output(r.output) != best_key]
        reasons = [f"consensus {best_count}/{len(succeeded)} on executed outputs"]
        if dissent:
            reasons.append(f"dissenting output(s) logged: {[r.output for r in dissent]}")
        return Decision(kind="answer", value=representative, consensus_fraction=fraction, reasons=tuple(reasons))

    return Decision(
        kind="abstain",
        consensus_fraction=fraction,
        reasons=(f"no majority: {len(succeeded)} successful outputs all differ",),
    )


# ---------------------------------------------------------------------------
# Independent gates (hard gates: a failure abstains regardless of score)
# ---------------------------------------------------------------------------


@dataclass
class GateReport:
    """Result of the independent checks (report section 2.4)."""

    rule_assertions_pass: bool = True
    evidence_coverage: float = 1.0  # 0..1, deterministic, from the profiler
    second_path_agrees: Optional[bool] = None  # None = no second path run
    failed_rules: tuple[str, ...] = ()

    @property
    def passes(self) -> bool:
        """Hard gates: rule assertions must pass. Evidence coverage is a
        score input, not a hard gate, because its threshold is learned
        per question type in calibration (section 3)."""

        return self.rule_assertions_pass


def combined_score(
    consensus_fraction: float,
    evidence_coverage: float,
    second_path_agrees: Optional[bool],
    *,
    w_consensus: float = 0.5,
    w_second_path: float = 0.3,
    w_evidence: float = 0.2,
) -> float:
    """Composite confidence score (starting proposal, NOT a tuned result).

    Weights are a starting point to be validated on train_cal; if the
    simpler "consensus fraction per question type" variant performs as
    well on train_holdout, prefer the simpler variant. A failed rule
    assertion must never reach this function: it abstains earlier.
    """

    second = 0.5 if second_path_agrees is None else (1.0 if second_path_agrees else 0.0)
    return (
        w_consensus * consensus_fraction
        + w_second_path * second
        + w_evidence * min(max(evidence_coverage, 0.0), 1.0)
    )


# ---------------------------------------------------------------------------
# Unanswerable vs abstain: the deterministic check comes first
# ---------------------------------------------------------------------------


def decide_unanswerable(coverage: SchemaCoverage) -> Optional[Decision]:
    """Return an ``unanswerable`` decision, or None to continue.

    A missing conclusion is only trusted after a full-schema fallback
    has been tried: a shortlist lookup that returns empty may itself be
    the bug. Callers that cannot run a fallback must pass
    ``fallback_tried=True`` only if their check already covered the full
    schema -- otherwise this function refuses to conclude and returns
    None, forcing the caller to abstain-or-continue explicitly instead
    of silently mislabelling an answerable question.
    """

    if coverage.is_complete:
        return None
    if not coverage.fallback_tried:
        return None
    missing = []
    if coverage.missing_tables:
        missing.append(f"tables={list(coverage.missing_tables)}")
    if coverage.missing_columns:
        missing.append(f"columns={list(coverage.missing_columns)}")
    if coverage.missing_rules:
        missing.append(f"rules={list(coverage.missing_rules)}")
    return Decision(kind="unanswerable", reasons=(f"required data/rule absent after full-schema fallback: {'; '.join(missing)}",))


# ---------------------------------------------------------------------------
# Full per-question decision (schema -> consensus -> gates -> threshold)
# ---------------------------------------------------------------------------


def decide_question(
    *,
    coverage: SchemaCoverage,
    candidates: Sequence[str],
    executor: Callable[[str], CandidateResult],
    thresholds: dict[str, float],
    default_threshold: float = 0.5,
    gates: Optional[GateReport] = None,
    question_type: Optional[str] = None,
) -> Decision:
    """Run the full decision pipeline for one question.

    Order matters (report section 5.2): schema check first, then
    generation + execution, then gates, then the locked calibrated
    threshold. ``thresholds`` must have been learned on train_cal and
    locked; this function never learns or adjusts them.
    """

    unanswerable = decide_unanswerable(coverage)
    if unanswerable is not None:
        return unanswerable

    results = [executor(code) for code in candidates]
    consensus = decide_consensus(results)
    if consensus.kind != "answer":
        return consensus

    gate_report = gates or GateReport()
    if not gate_report.passes:
        return Decision(
            kind="abstain",
            consensus_fraction=consensus.consensus_fraction,
            reasons=(f"rule assertion(s) failed: {list(gate_report.failed_rules)}",),
        )

    # Per-type threshold when the caller supplies a question type, else
    # the locked global threshold. The threshold actually applied is
    # recorded in the reasons, so a threshold choice is auditable.
    if question_type is not None:
        threshold = thresholds.get(question_type, thresholds.get("__global__", default_threshold))
    else:
        threshold = thresholds.get("__global__", default_threshold)
    score = combined_score(
        consensus.consensus_fraction or 0.0,
        gate_report.evidence_coverage,
        gate_report.second_path_agrees,
    )
    if score < threshold:
        return Decision(
            kind="abstain",
            consensus_fraction=consensus.consensus_fraction,
            reasons=(f"calibrated score {score:.3f} below locked threshold {threshold:.3f}",),
        )
    return Decision(
        kind="answer",
        value=consensus.value,
        consensus_fraction=consensus.consensus_fraction,
        reasons=consensus.reasons + (f"score {score:.3f} >= threshold {threshold:.3f}",),
    )


# ---------------------------------------------------------------------------
# Calibration: learn thresholds on train_cal, evaluate once on holdout
# ---------------------------------------------------------------------------


def penalized_accuracy(records: Sequence[CalibrationRecord]) -> float:
    """PA over all records: correct answers +1, wrong answers -1, abstentions 0.

    ``records`` here are the system's decisions on a split where gold is
    known (train_cal / train_holdout). Abstained records contribute 0
    regardless of whether they would have been right.
    """

    if not records:
        return 0.0
    total = 0
    for r in records:
        if not r.answered:
            continue
        total += 1 if r.correct else -1
    return total / len(records)


def learn_thresholds(
    records: Sequence[CalibrationRecord],
    *,
    min_support: int = 30,
    step: float = 0.05,
) -> dict[str, float]:
    """Learn one threshold per question type on train_cal.

    Grid-searches thresholds in [0, 1] maximising PA for that type;
    ties break towards higher coverage (answer more when PA is equal).
    Types with fewer than ``min_support`` records fall back to the
    global threshold (key ``"__global__"``). This is a proposed
    procedure, not a tuned result: ``min_support`` and ``step`` are
    practical choices, and the learned thresholds must be validated on
    a held-out split before any use.
    """

    def best_threshold(subset: Sequence[CalibrationRecord]) -> float:
        best_t, best_pa, best_cov = 0.0, float("-inf"), -1.0
        t = 0.0
        while t <= 1.0 + 1e-9:
            answered = [r for r in subset if r.score >= t]
            pa = penalized_accuracy(
                [CalibrationRecord(score=r.score, question_type=r.question_type, correct=r.correct, answered=True) for r in answered]
                + [CalibrationRecord(score=r.score, question_type=r.question_type, correct=False, answered=False) for r in subset if r.score < t]
            )
            cov = len(answered) / len(subset) if subset else 0.0
            if pa > best_pa or (pa == best_pa and cov > best_cov):
                best_t, best_pa, best_cov = t, pa, cov
            t = round(t + step, 10)
        return best_t

    thresholds: dict[str, float] = {"__global__": best_threshold(list(records))}
    by_type: dict[str, list[CalibrationRecord]] = {}
    for r in records:
        by_type.setdefault(r.question_type, []).append(r)
    for qtype, subset in by_type.items():
        thresholds[qtype] = best_threshold(subset) if len(subset) >= min_support else thresholds["__global__"]
    return thresholds


def evaluate_holdout(
    records: Sequence[CalibrationRecord],
    thresholds: dict[str, float],
) -> dict[str, Any]:
    """Evaluate locked thresholds once on train_holdout.

    Returns PA, coverage, selective accuracy (accuracy on answered),
    selective risk, and counts. Callers must not tune thresholds from
    this output and then report the same numbers again.
    """

    decided: list[CalibrationRecord] = []
    for r in records:
        t = thresholds.get(r.question_type, thresholds.get("__global__", 0.5))
        decided.append(
            CalibrationRecord(score=r.score, question_type=r.question_type, correct=r.correct, answered=r.score >= t)
        )
    answered = [r for r in decided if r.answered]
    correct = sum(1 for r in answered if r.correct)
    return {
        "n": len(decided),
        "pa": penalized_accuracy(decided),
        "coverage": len(answered) / len(decided) if decided else 0.0,
        "selective_accuracy": correct / len(answered) if answered else 0.0,
        "selective_risk": 1.0 - (correct / len(answered)) if answered else 0.0,
        "answered": len(answered),
        "correct": correct,
        "wrong": len(answered) - correct,
        "abstained": len(decided) - len(answered),
    }


def risk_coverage_curve(
    records: Sequence[CalibrationRecord],
    *,
    step: float = 0.05,
) -> list[dict[str, float]]:
    """Risk-coverage points for thresholds swept from high to low.

    Each point reports the threshold, the coverage at that threshold,
    and the selective risk (wrong / answered) at that threshold.
    """

    points: list[dict[str, float]] = []
    t = 1.0
    while t >= -1e-9:
        answered = [r for r in records if r.score >= t]
        risk = (sum(1 for r in answered if not r.correct) / len(answered)) if answered else 0.0
        points.append(
            {"threshold": round(t, 2), "coverage": len(answered) / len(records) if records else 0.0, "selective_risk": risk}
        )
        t = round(t - step, 10)
    return points


# ---------------------------------------------------------------------------
# Time budget: first-principles scenarios (estimates, never measurements)
# ---------------------------------------------------------------------------


def time_budget(
    n_questions: int,
    *,
    k: int = 3,
    n_gpus: int = 2,
    budget_hours: float = 6.0,
    per_candidate_seconds: float,
    exec_seconds_per_question: float = 0.0,
    overhead_seconds: float = 0.0,
) -> dict[str, float]:
    """Sequential-model time budget for a k-candidate design.

    All inputs are assumptions supplied by the caller; all outputs are
    ESTIMATES. The sequential model is pessimistic under vLLM
    continuous batching (see the companion report, section 4.3): use it
    as a safety ceiling, and replace it with measured batch throughput
    before finalising the architecture.
    """

    gen = n_questions * k * per_candidate_seconds / n_gpus
    total = gen + n_questions * exec_seconds_per_question + overhead_seconds
    return {
        "generation_seconds": gen,
        "execution_seconds": n_questions * exec_seconds_per_question,
        "overhead_seconds": overhead_seconds,
        "total_seconds": total,
        "total_hours": total / 3600.0,
        "budget_hours": budget_hours,
        "within_budget": total <= budget_hours * 3600.0,
        "break_even_per_candidate_seconds": budget_hours * 3600.0 * n_gpus / (n_questions * k) if n_questions and k else float("inf"),
    }


def scenario_table(
    n_questions: int = 600,
    *,
    k: int = 3,
    n_gpus: int = 2,
    exec_seconds_per_question: float = 0.0,
) -> list[dict[str, Any]]:
    """Break-even scenario table for the companion report (section 4.2)."""

    rows = []
    for t_gen in (2.0, 5.0, 10.0, 15.0, 20.0, 24.0, 30.0):
        budget = time_budget(
            n_questions, k=k, n_gpus=n_gpus, per_candidate_seconds=t_gen, exec_seconds_per_question=exec_seconds_per_question
        )
        rows.append({"per_candidate_seconds": t_gen, "total_hours": round(budget["total_hours"], 2), "within_budget": budget["within_budget"]})
    return rows


# ---------------------------------------------------------------------------
# Submission encoding: deliberately separate from the decision
# ---------------------------------------------------------------------------


def encode_decision(decision: Decision, *, unanswerable_encoding: str) -> dict[str, Any]:
    """Encode a decision as one submission record (mapping supplied by caller).

    ``unanswerable_encoding`` is the exact value the official submission
    format requires for an unanswerable question. It is a parameter
    precisely because the evaluator's treatment of ``unanswerable`` is
    UNVERIFIED at the time of writing: do not hard-code a guess here and
    forget it. Pass the value only after reading the evaluator/README
    of the split.
    """

    if decision.kind == "answer":
        return {"decision": "answer", "value": decision.value, "reasons": list(decision.reasons)}
    if decision.kind == "unanswerable":
        return {"decision": "unanswerable", "value": unanswerable_encoding, "reasons": list(decision.reasons)}
    return {"decision": "abstain", "value": None, "reasons": list(decision.reasons)}


# ---------------------------------------------------------------------------
# Demo: three decision paths with fake executors (no model, no API)
# ---------------------------------------------------------------------------


def _fake_executor(outputs: Sequence[Any]) -> Callable[[str], CandidateResult]:
    """Build an executor that returns pre-written outputs in order."""

    state = {"i": 0}

    def run(code: str) -> CandidateResult:
        idx = state["i"]
        state["i"] += 1
        if idx >= len(outputs):
            return CandidateResult(code=code, error="no more fake outputs")
        out = outputs[idx]
        if isinstance(out, Exception):
            return CandidateResult(code=code, error=str(out))
        return CandidateResult(code=code, output=out)

    return run


def main() -> None:
    """Demonstrate the three decision paths end to end."""

    full = SchemaCoverage(fallback_tried=True)

    # Path 1: 3/3 agree -> answer (gates pass, score above threshold).
    d1 = decide_question(
        coverage=full,
        candidates=["code_a", "code_b", "code_c"],
        executor=_fake_executor([1250000, 1250000, 1250000]),
        thresholds={"__global__": 0.5},
        gates=GateReport(rule_assertions_pass=True, evidence_coverage=1.0, second_path_agrees=True),
    )
    print("3/3 agree      ->", d1.kind, d1.value, list(d1.reasons))

    # Path 2: all three differ -> abstain.
    d2 = decide_question(
        coverage=full,
        candidates=["code_a", "code_b", "code_c"],
        executor=_fake_executor([100, 200, 300]),
        thresholds={"__global__": 0.5},
    )
    print("all differ     ->", d2.kind, list(d2.reasons))

    # Path 3: required column absent after full-schema fallback -> unanswerable.
    d3 = decide_question(
        coverage=SchemaCoverage(missing_columns=("discount_amount",), fallback_tried=True),
        candidates=["code_a"],
        executor=_fake_executor([42]),
        thresholds={"__global__": 0.5},
    )
    print("missing column ->", d3.kind, list(d3.reasons))

    # Path 4: same missing column but WITHOUT a fallback -> no conclusion.
    # The pipeline therefore runs the candidates instead of mislabelling
    # the question; here the candidates agree, so it answers.
    d4 = decide_question(
        coverage=SchemaCoverage(missing_columns=("discount_amount",), fallback_tried=False),
        candidates=["code_a", "code_b", "code_c"],
        executor=_fake_executor([42, 42, 42]),
        thresholds={"__global__": 0.5},
        gates=GateReport(rule_assertions_pass=True, evidence_coverage=1.0, second_path_agrees=True),
    )
    print("no fallback    ->", d4.kind, d4.value, list(d4.reasons))

    # Calibration demo on invented toy records (NOT measurements).
    toy = [
        CalibrationRecord(score=0.95, question_type="number", correct=True),
        CalibrationRecord(score=0.90, question_type="number", correct=True),
        CalibrationRecord(score=0.60, question_type="number", correct=False),
        CalibrationRecord(score=0.40, question_type="number", correct=False),
    ]
    thresholds = learn_thresholds(toy, min_support=1)
    print("toy thresholds ->", thresholds)
    print("toy holdout    ->", evaluate_holdout(toy, thresholds))

    # Time-budget demo (ESTIMATES from the report's scenario table).
    for row in scenario_table(n_questions=600, exec_seconds_per_question=0.0):
        print("budget         ->", row)


if __name__ == "__main__":
    main()
