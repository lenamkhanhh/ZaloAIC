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

    * EVERY canonical form is tagged with its type. The previous
      version returned a bare bool and a bare float, and in Python
      ``True == 1.0`` is True, so ``outputs_equal(True, 1)`` wrongly
      returned True. Now bool -> ("bool", ...), number ->
      ("number", ...), string -> ("string", ...), date -> ("date",
      isoformat): different types can never be equal, by construction.
    * numbers: int and float ARE equivalent when they hold the same
      value after rounding to 2 decimal places (DataMate answers are
      reported to 2dp in the prior portal notes; rounding here only
      decides whether two candidates "agree"). NaN/inf are kept as
      distinct special values, never equal to a number.
    * strings: NFC, lowercased, punctuation collapsed to single spaces;
    * dates/datetimes: ISO format, kept distinct from the STRING
      "2025-01-01" (a date object and a date string are different
      output types; callers must normalise types before consensus if
      they want them to match);
    * lists: order preserved (ranking questions are order-sensitive);
    * tables (list of dicts): column names normalised the same way as
      strings, rows kept as a set of JSON strings (row order is not
      treated as meaningful for tables).
    """
    from datetime import date as _date, datetime as _datetime

    if isinstance(value, bool):
        return ("bool", value)
    if isinstance(value, (int, float)):
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return ("float_special", repr(value))
        return ("number", round(float(value), 2))
    if isinstance(value, _datetime):
        return ("date", value.isoformat())
    if isinstance(value, _date):
        return ("date", value.isoformat())
    if isinstance(value, str):
        text = unicodedata.normalize("NFC", value).lower()
        text = "".join(ch if ch.isalnum() else " " for ch in text)
        return ("string", " ".join(text.split()))
    if isinstance(value, (list, tuple)):
        if value and all(isinstance(row, dict) for row in value):
            rows = {
                json.dumps(
                    {str(canonicalise_output(k)): canonicalise_output(v) for k, v in row.items()},
                    sort_keys=True,
                    ensure_ascii=False,
                    default=str,
                )
                for row in value
            }
            return ("table", tuple(sorted(rows)))
        return ("list", tuple(canonicalise_output(v) for v in value))
    if isinstance(value, dict):
        return ("dict", tuple(sorted(
            (str(canonicalise_output(k)), canonicalise_output(v)) for k, v in value.items()
        )))
    return ("other", repr(value))


def outputs_equal(a: Any, b: Any) -> bool:
    """Whether two executed outputs count as the same answer."""

    return canonicalise_output(a) == canonicalise_output(b)


# ---------------------------------------------------------------------------
# Consensus: k candidates, executed outputs, majority with audit trail
# ---------------------------------------------------------------------------


def decide_consensus(
    results: Sequence[CandidateResult],
    *,
    allow_empty_answer: bool = False,
) -> Decision:
    """Decide from executed candidates alone (before independent gates).

    Rules (companion report, section 2.3):

    * only successfully executed outputs vote. The DENOMINATOR is the
      number of successful candidates, and the reasons always state how
      many candidates were attempted and how many failed, so a "2/3"
      can never silently mean "2 of 5 attempted, 3 failed".
    * STRICT majority: the winning output must hold MORE THAN HALF of
      the successful votes (best_count * 2 > n_successful). The previous
      code used ``best_count >= 2``, which answered on 2/5 (a minority)
      and on a 2/2 tie in a 4-candidate run. "Two outputs agree" is not
      a majority; it is only a majority when k and the failure count
      make it one. For k=1 the single candidate trivially holds a
      strict majority -- that is a degenerate case, not consensus
      evidence, and the reason says so.
    * no strict majority (all differ, or a tie) -> abstain.
    * no successful output at all -> abstain (an execution failure is
      NOT evidence that the data is missing, so it is never mapped to
      ``unanswerable`` here).
    * an agreed-upon EMPTY output (None, empty list/tuple, empty
      string) is NOT an answer by default: it may be a wrong filter
      rather than genuinely empty data, so it abstains pending an
      evidence check by the caller. Pass ``allow_empty_answer=True``
      only when the caller has independently verified the filter and
      that an empty result is the expected answer type. Note the
      asymmetry this preserves: COUNT=0 is a NUMBER (0), not an empty
      output, and is answered normally -- an empty result is not
      automatically unanswerable, and 0 is not an empty result.
    """

    succeeded = [r for r in results if r.succeeded]
    n_failed = len(results) - len(succeeded)
    if not succeeded:
        return Decision(kind="abstain", reasons=(f"all {len(results)} candidates failed or timed out",))

    counts: Counter = Counter(canonicalise_output(r.output) for r in succeeded)
    best_key, best_count = counts.most_common(1)[0]
    fraction = best_count / len(succeeded)
    is_majority = best_count * 2 > len(succeeded)

    # Recover one representative raw output for the winning key.
    representative = next(r.output for r in succeeded if canonicalise_output(r.output) == best_key)

    if is_majority:
        if (representative is None
                or (isinstance(representative, (list, tuple)) and len(representative) == 0)
                or (isinstance(representative, str) and representative == "")) and not allow_empty_answer:
            return Decision(
                kind="abstain",
                consensus_fraction=fraction,
                reasons=(f"strict majority {best_count}/{len(succeeded)} successful "
                         f"({n_failed} failed) on an empty output; needs an evidence check",),
            )
        dissent = [r for r in succeeded if canonicalise_output(r.output) != best_key]
        reasons = [f"strict majority {best_count}/{len(succeeded)} successful "
                   f"({len(results)} attempted, {n_failed} failed) on executed outputs"]
        if len(succeeded) == 1:
            reasons.append("single successful candidate only; no consensus evidence")
        if dissent:
            reasons.append(f"dissenting output(s) logged: {[r.output for r in dissent]}")
        return Decision(kind="answer", value=representative, consensus_fraction=fraction, reasons=tuple(reasons))

    return Decision(
        kind="abstain",
        consensus_fraction=fraction,
        reasons=(f"no strict majority: best {best_count}/{len(succeeded)} successful "
                 f"({len(results)} attempted, {n_failed} failed)",),
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

    What "full-schema fallback" must include (attested by
    ``fallback_tried=True``, enforced by :func:`check_schema_coverage`
    when it is used): a scan of ALL available tables/columns, not just
    the planner's shortlist, AND an alias/equivalent search (a column
    the planner named one way may exist under another name, and a
    value derivable from other columns is not "missing data"). A
    missing column reported by the planner alone proves nothing about
    the data; only a full scan that also checked equivalents does.
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


def check_schema_coverage(
    required_tables: Sequence[str],
    required_columns: Sequence[str],
    available_tables: Sequence[str],
    available_columns: Sequence[str],
    *,
    aliases: dict[str, Sequence[str]] | None = None,
    required_rules: Sequence[str] = (),
    available_rules: Sequence[str] = (),
) -> SchemaCoverage:
    """Build a SchemaCoverage from a FULL schema scan, not a shortlist.

    A required item counts as found if it, or any of its aliases, is
    present in the available schema (alias matching is case-insensitive
    and ignores spaces/underscores, so "discount_amount",
    "DiscountAmount" and "discount amount" are the same column). Only
    items still missing after this scan are reported, and
    ``fallback_tried`` is True by construction -- this function IS the
    fallback. Callers must not build a SchemaCoverage by hand from a
    planner shortlist and then set ``fallback_tried=True``: that is
    exactly the mislabelling this function exists to prevent. Note
    what it does NOT prove: a column present in the schema may still
    hold no rows for the question's period, and a derivable value
    (e.g. revenue from price x quantity when no revenue column exists)
    is a modelling decision the caller must make separately -- presence
    in the schema is necessary, not sufficient, for answerability.
    """
    aliases = aliases or {}

    def _norm(name: str) -> str:
        return name.lower().replace(" ", "").replace("_", "")

    available_t_norm = {_norm(t) for t in available_tables}
    available_c_norm = {_norm(c) for c in available_columns}
    available_r_norm = {_norm(r) for r in available_rules}

    def _found(name: str, available: set[str]) -> bool:
        if _norm(name) in available:
            return True
        return any(_norm(alias) in available for alias in aliases.get(name, ()))

    missing_tables = tuple(t for t in required_tables if not _found(t, available_t_norm))
    missing_columns = tuple(c for c in required_columns if not _found(c, available_c_norm))
    missing_rules = tuple(r for r in required_rules if not _found(r, available_r_norm))
    return SchemaCoverage(
        missing_tables=missing_tables,
        missing_columns=missing_columns,
        missing_rules=missing_rules,
        fallback_tried=True,
    )


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
    allow_empty_answer: bool = False,
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
    consensus = decide_consensus(results, allow_empty_answer=allow_empty_answer)
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


# A threshold above every possible combined score (scores are in [0, 1]):
# with this threshold the system answers nothing. It is a real decision
# in the grid, not a special case bolted on afterwards.
REJECT_ALL_THRESHOLD = 1.0 + 0.05


def learn_thresholds(
    records: Sequence[CalibrationRecord],
    *,
    min_support: int = 30,
    step: float = 0.05,
) -> dict[str, float]:
    """Learn one threshold per question type on train_cal.

    Grid-searches thresholds in [0, 1] PLUS the reject-all threshold
    (1.0 + step) maximising PA for that type; ties break towards higher
    coverage (answer more when PA is equal). The reject-all option is
    what the previous version lacked: with a single calibration record
    (score=1.0, correct=False), every threshold in [0, 1] answers it
    and scores PA=-1, while rejecting everything scores PA=0 -- so
    reject-all must be in the grid, or calibration can never learn to
    abstain from a score range that is entirely wrong.

    Types with fewer than ``min_support`` records fall back to the
    global threshold (key ``"__global__"``). This is a proposed
    procedure, not a tuned result: ``min_support`` and ``step`` are
    practical choices, and the learned thresholds must be validated on
    a held-out split before any use.

    Semantics shared by ``learn_thresholds``, ``evaluate_holdout`` and
    ``decide_question`` (all three must agree, or calibration is a
    lie): a question is ANSWERED iff ``score >= threshold``. An empty
    record list cannot justify any answering policy, so it yields the
    reject-all threshold (fail closed) instead of a fabricated 0.0.
    """
    reject_all = 1.0 + step

    def best_threshold(subset: Sequence[CalibrationRecord]) -> float:
        if not subset:
            return reject_all
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
        # Reject-all candidate: answers nothing, PA = 0 by definition.
        # It wins only on strictly better PA (tie keeps higher coverage).
        if 0.0 > best_pa:
            return reject_all
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
