"""Entity grounding & Vietnamese ASR-error correction for LifeMate (ZAIC 2026).

Offline-only, standard-library-first module. RapidFuzz is used only when
installed; otherwise the code falls back to :mod:`difflib` so the module
still runs inside a minimal Docker image.

Design rules implemented here (see the companion report
``deep-dive-2-asr-grounding.md``):

* Diacritics are NEVER stripped for a matching decision. Tone-stripped
  forms are auxiliary keys only, used to *detect* a tone mismatch, not
  to erase it.
* Candidates come only from tool ``read`` results inside the same sample
  (contacts, devices, accounts). No external entity database is used.
* Money, dates and IDs/account numbers are never fuzzy-guessed: only an
  exact (digit-normalised) match grounds them. Any digit difference
  yields ``UNKNOWN``.
* A detected negation that covers a proposed write blocks that write.
  The guard never silently inverts the action; it returns
  ``ask_missing_info`` (or an explicit confirmation requirement).

This module is a research prototype. It has not been measured on ZAIC
data; thresholds below are proposed starting points, not measured
optima.
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date as _date
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Iterable, Optional, Sequence

try:  # Optional, offline, MIT-licensed dependency (see report §7).
    from rapidfuzz import fuzz as _rf_fuzz
except Exception:  # pragma: no cover - fallback path
    _rf_fuzz = None

__all__ = [
    "Candidate",
    "ConfidenceTier",
    "GroundedSlot",
    "GuardDecision",
    "NegationFinding",
    "NegationKind",
    "SlotKind",
    "detect_negation",
    "fuse_nbest",
    "ground_slot",
    "guard_tool_call",
    "normalize_vietnamese",
    "score_tone_aware",
    "tone_stripped_key",
    "PROMPT_ASSERTION_VI",
]

# ---------------------------------------------------------------------------
# Normalisation (diacritics preserved)
# ---------------------------------------------------------------------------

_TONE_MARKS = {
    "\u0300",  # grave: huyền
    "\u0301",  # acute: sắc
    "\u0303",  # tilde: ngã
    "\u0309",  # hook above: hỏi
    "\u0323",  # dot below: nặng
}


def normalize_vietnamese(text: str) -> str:
    """Return NFC-normalised, lower-cased, whitespace-collapsed text.

    NFC is the canonical composed form for Vietnamese: a vowel plus its
    tone mark becomes one precomposed code point (e.g. ``ế``). This step
    only unifies *equivalent* encodings of the same character; it never
    removes a tone or a vowel mark. ``đ``/``Đ`` are kept as-is.
    """
    text = unicodedata.normalize("NFC", text or "")
    text = text.lower()
    text = re.sub(r"\s+", " ", text).strip()
    return text


def tone_stripped_key(text: str) -> str:
    """Return an auxiliary key with tones (and ``đ``) flattened.

    This key is used ONLY to detect that two strings differ *only* by
    tone, so that such a pair can be downgraded instead of being treated
    as an exact match. It must never be used as the value written into a
    tool call.
    """
    decomposed = unicodedata.normalize("NFD", normalize_vietnamese(text))
    stripped = "".join(ch for ch in decomposed if ch not in _TONE_MARKS)
    stripped = stripped.replace("đ", "d")
    return unicodedata.normalize("NFC", stripped)


def _similarity(a: str, b: str) -> float:
    """Return a 0–100 string similarity score (RapidFuzz if present)."""
    if _rf_fuzz is not None:
        return float(_rf_fuzz.WRatio(a, b))
    return difflib.SequenceMatcher(None, a, b).ratio() * 100.0


def score_tone_aware(raw: str, candidate: str) -> float:
    """Score ``raw`` against ``candidate`` with a tone-mismatch penalty.

    * Identical NFC forms score 100.
    * Forms identical after tone stripping but different in NFC (i.e.
      they differ only by tone, e.g. ``bàn`` vs ``bán``) are capped at
      85: close enough to be a *candidate*, never enough to auto-ground
      a sensitive slot, because in Vietnamese a tone change can change
      the word entirely.
    * Everything else uses the plain fuzzy score.
    """
    raw_n = normalize_vietnamese(raw)
    cand_n = normalize_vietnamese(candidate)
    if raw_n == cand_n:
        return 100.0
    score = _similarity(raw_n, cand_n)
    if tone_stripped_key(raw_n) == tone_stripped_key(cand_n):
        score = min(score, 85.0)
    return score


# ---------------------------------------------------------------------------
# Candidate grounding
# ---------------------------------------------------------------------------


class SlotKind(str, Enum):
    """Kind of slot being grounded; sensitive kinds forbid fuzzy matches."""

    NAME = "name"  # person / device / app name
    MONEY = "money"
    DATE = "date"
    ACCOUNT_ID = "account_id"  # account numbers, phone numbers, IDs
    OTHER = "other"


class ConfidenceTier(str, Enum):
    """Evidence tier of a grounding decision."""

    EXACT = "exact"  # NFC-identical to a candidate from this sample
    FUZZY_GROUNDED = "fuzzy_grounded"  # above threshold, clear margin
    AMBIGUOUS = "ambiguous"  # several candidates close, or tone-only match
    UNKNOWN = "unknown"  # no candidate passes; do not guess


@dataclass(frozen=True)
class Candidate:
    """One candidate value obtained from a ``read`` tool in this sample."""

    value: str  # canonical value exactly as returned by the tool
    source: str  # e.g. "contacts", "devices", "accounts"
    key: str = ""  # optional tool-internal id, if the tool returned one


@dataclass
class GroundedSlot:
    """Result of grounding one raw ASR span against a candidate list."""

    raw_span: str
    value: Optional[str]  # canonical candidate value, or None if unknown
    tier: ConfidenceTier
    evidence: str  # human-readable reason, for logs / the LLM prompt
    score: float = 0.0
    runner_up_score: float = 0.0
    alternatives: list[str] = field(default_factory=list)


# Proposed starting thresholds (NOT measured on ZAIC data).
FUZZY_THRESHOLD = 88.0
FUZZY_MARGIN = 8.0

_SENSITIVE_KINDS = frozenset(
    {SlotKind.MONEY, SlotKind.DATE, SlotKind.ACCOUNT_ID}
)


# ---------------------------------------------------------------------------
# Typed normalisation for sensitive slots.
#
# The previous version normalised EVERY sensitive slot with one
# "digits only" rule. That collapsed distinct values onto each other:
# "1,5" (one point five) matched candidate "15", and "-100" matched
# "100", because the decimal separator, the sign and the unit were all
# thrown away. Each kind below keeps exactly the information that kind
# needs, and nothing else.
# ---------------------------------------------------------------------------

_MONEY_UNITS = {
    "triệu": Decimal(1_000_000), "trieu": Decimal(1_000_000),
    "nghìn": Decimal(1_000), "ngàn": Decimal(1_000), "nghin": Decimal(1_000),
    "k": Decimal(1_000),
    "đồng": Decimal(1), "dong": Decimal(1), "đ": Decimal(1),
    "vnd": Decimal(1), "vnđ": Decimal(1),
}


def _parse_money_value(text: str) -> Decimal | None:
    """Parse a money span to a base-unit Decimal, or None if ambiguous.

    Rules: currency symbols stripped; accounting parentheses and a
    leading ``-`` both mean negative (and are KEPT, never dropped);
    a trailing unit word (triệu/nghìn/đồng/...) scales the value; with
    both separators present the LAST one is the decimal separator; a
    single separator with exactly 3 digits after it is AMBIGUOUS
    (1500 vs 1.5) and returns None; a single separator with 1-2 digits
    after it is decimal. Returns None, never a guess, on ambiguity.
    """
    raw = normalize_vietnamese(text or "")
    if not raw:
        return None
    raw = re.sub(r"^(vnd|vnđ|₫|đ)\s*|\s*(vnd|vnđ|₫|đ)$", "", raw).strip()
    negative = False
    if raw.startswith("(") and raw.endswith(")"):
        negative, raw = True, raw[1:-1].strip()
    if raw.startswith("-"):
        negative, raw = True, raw[1:].strip()
    multiplier = Decimal(1)
    for unit, factor in sorted(_MONEY_UNITS.items(), key=lambda kv: -len(kv[0])):
        if raw.endswith(" " + unit) or raw == unit:
            multiplier = factor
            raw = raw[: -len(unit)].strip()
            break
    raw = raw.replace("\u00a0", "").replace(" ", "")
    if not re.fullmatch(r"\d+(?:[.,]\d+)*", raw):
        return None
    has_dot, has_comma = "." in raw, "," in raw
    if has_dot and has_comma:
        body = raw.replace(",", "") if raw.rfind(".") > raw.rfind(",") else raw.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(?:[.,]\d{3}){2,}", raw):
        # At least TWO repeated 3-digit groups: thousands separator,
        # unambiguous (e.g. 1.000.000). ONE group ("1.500") is handled
        # by the ambiguous branch below and must NOT reach here.
        body = raw.replace(".", "").replace(",", "")
    elif re.fullmatch(r"\d+[.,]\d{3}", raw):
        return None  # single separator + 3 digits: ambiguous, do not guess
    elif has_dot or has_comma:
        body = raw.replace(",", ".")
    else:
        body = raw
    try:
        value = Decimal(body) * multiplier
    except InvalidOperation:
        return None
    return -value if negative else value


def _parse_date_value(text: str) -> tuple[int | None, int, int] | None:
    """Parse a date span to (year|None, month, day), or None if invalid.

    Accepted: ISO yyyy-mm-dd; dd/mm/yyyy and dd-mm-yyyy; dd/mm and
    dd-mm (year unknown); "ngày D tháng M" with optional "năm Y".
    A calendar-invalid date (31/02, month 13) returns None, never a
    coerced neighbour date. Partial dates only match a candidate when
    month and day agree and the years agree whenever both are known.
    """
    raw = normalize_vietnamese(text or "").strip()
    match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", raw)
    if match:
        year, month, day = (int(g) for g in match.groups())
    else:
        match = re.fullmatch(r"ngày\s+(\d{1,2})\s+tháng\s+(\d{1,2})(?:\s+năm\s+(\d{4}))?", raw)
        if match:
            day, month = int(match.group(1)), int(match.group(2))
            year = int(match.group(3)) if match.group(3) else None
        else:
            match = re.fullmatch(r"(\d{1,2})[/\-](\d{1,2})(?:[/\-](\d{4}))?", raw)
            if not match:
                return None
            day, month = int(match.group(1)), int(match.group(2))
            year = int(match.group(3)) if match.group(3) else None
    if year is not None:
        try:
            _date(year, month, day)
        except ValueError:
            return None
    else:
        if not (1 <= month <= 12 and 1 <= day <= 31):
            return None
    return (year, month, day)


def _dates_match(a: tuple[int | None, int, int], b: tuple[int | None, int, int]) -> bool:
    """Date equality with the partial-year rule described above."""
    if a[1] != b[1] or a[2] != b[2]:
        return False
    if a[0] is not None and b[0] is not None and a[0] != b[0]:
        return False
    return True


def _normalize_id_value(text: str) -> str:
    """Normalise an id/account number for exact comparison.

    Only separators (space, hyphen, dot) are removed. Digits are kept
    verbatim, INCLUDING leading zeros ("090..." stays "090...", it is
    not an integer), and letters are upper-cased. Nothing else is
    dropped: unlike the old digits-only rule, this never turns an
    alphanumeric id into a digit string, and it never merges two ids
    that differ only in a letter.
    """
    raw = normalize_vietnamese(text or "")
    return re.sub(r"[\s\-.]", "", raw).upper()


def ground_slot(
    raw_span: str,
    candidates: Sequence[Candidate],
    slot_kind: SlotKind,
    *,
    fuzzy_threshold: float = FUZZY_THRESHOLD,
    fuzzy_margin: float = FUZZY_MARGIN,
) -> GroundedSlot:
    """Ground ``raw_span`` against ``candidates`` from this sample only.

    Decision order:

    1. Sensitive kinds (money/date/ID): TYPED exact match only, with
       the normalisation of that kind (money keeps sign, decimal value
       and unit; dates keep calendar meaning; ids keep leading zeros
       and letters). Any difference, or any ambiguity in the raw span,
       -> ``UNKNOWN``; fuzzy matching is forbidden for these kinds.
    2. Other kinds: exact NFC match -> :attr:`ConfidenceTier.EXACT`.
    3. Other kinds: best fuzzy score >= ``fuzzy_threshold`` and at
       least ``fuzzy_margin`` above the runner-up -> ``FUZZY_GROUNDED``.
    4. Otherwise ``AMBIGUOUS`` (a close rival exists or the best match
       is tone-only) or ``UNKNOWN`` (nothing close).

    The returned ``value`` is always a candidate's canonical value, never
    the raw ASR string, so a corrected slot can be traced to evidence.
    """
    raw = normalize_vietnamese(raw_span)
    if not raw or not candidates:
        return GroundedSlot(raw_span, None, ConfidenceTier.UNKNOWN,
                            "empty span or empty candidate list")

    # 1. Sensitive slots: typed exact match, never a shared digits rule.
    if slot_kind in _SENSITIVE_KINDS:
        if slot_kind == SlotKind.MONEY:
            raw_value = _parse_money_value(raw_span)
            if raw_value is None:
                return GroundedSlot(raw_span, None, ConfidenceTier.UNKNOWN,
                                    "money: raw span ambiguous or unparseable; not guessed")
            for cand in candidates:
                if _parse_money_value(cand.value) == raw_value:
                    return GroundedSlot(raw_span, cand.value, ConfidenceTier.EXACT,
                                        f"exact money match in {cand.source}", 100.0)
        elif slot_kind == SlotKind.DATE:
            raw_value = _parse_date_value(raw_span)
            if raw_value is None:
                return GroundedSlot(raw_span, None, ConfidenceTier.UNKNOWN,
                                    "date: raw span invalid or unparseable; not guessed")
            for cand in candidates:
                cand_value = _parse_date_value(cand.value)
                if cand_value is not None and _dates_match(raw_value, cand_value):
                    return GroundedSlot(raw_span, cand.value, ConfidenceTier.EXACT,
                                        f"exact date match in {cand.source}", 100.0)
        else:  # ACCOUNT_ID
            raw_value = _normalize_id_value(raw_span)
            if not raw_value:
                return GroundedSlot(raw_span, None, ConfidenceTier.UNKNOWN,
                                    "account id: empty after normalisation")
            for cand in candidates:
                if _normalize_id_value(cand.value) == raw_value:
                    return GroundedSlot(raw_span, cand.value, ConfidenceTier.EXACT,
                                        f"exact id match in {cand.source}", 100.0)
        return GroundedSlot(
            raw_span, None, ConfidenceTier.UNKNOWN,
            f"{slot_kind.value}: no exact typed match; fuzzy guessing "
            "is forbidden for this slot kind")

    # 2. Exact match on the preserved-diacritic form (names etc. only).
    for cand in candidates:
        if normalize_vietnamese(cand.value) == raw:
            return GroundedSlot(raw_span, cand.value, ConfidenceTier.EXACT,
                                f"exact NFC match in {cand.source}", 100.0)

    # 3. Fuzzy matching for names / devices / apps.
    scored = sorted(
        ((score_tone_aware(raw, cand.value), cand) for cand in candidates),
        key=lambda pair: pair[0], reverse=True)
    best_score, best = scored[0]
    runner_up = scored[1][0] if len(scored) > 1 else 0.0
    alternatives = [c.value for _, c in scored[1:3]]

    tone_only = tone_stripped_key(raw) == tone_stripped_key(best.value)
    if tone_only and best_score >= 70.0:
        # Tone-only agreement is not enough to auto-ground: the
        # words may be different words (bàn/bán/bạn/bận). Report it as
        # ambiguous (not unknown) so the caller can ask, and so the
        # tone-mismatch cap (85) cannot accidentally pass the fuzzy
        # threshold for a different word.
        return GroundedSlot(raw_span, None, ConfidenceTier.AMBIGUOUS,
                            "tone-only match; tone changes meaning, "
                            "needs confirmation", best_score, runner_up,
                            alternatives)
    if best_score >= fuzzy_threshold and (best_score - runner_up) >= fuzzy_margin:
        # Backend note: RapidFuzz WRatio and difflib ratios are NOT on
        # the same scale, so a threshold tuned for one is not valid
        # for the other. The evidence records which backend scored this,
        # so a difflib-fallback score is never silently reported as a
        # RapidFuzz score.
        backend = "rapidfuzz" if _rf_fuzz is not None else "difflib-fallback"
        return GroundedSlot(raw_span, best.value,
                            ConfidenceTier.FUZZY_GROUNDED,
                            f"fuzzy score {best_score:.1f} ({backend}) in {best.source}, "
                            f"margin {best_score - runner_up:.1f}",
                            best_score, runner_up, alternatives)
    if best_score >= fuzzy_threshold:
        return GroundedSlot(raw_span, None, ConfidenceTier.AMBIGUOUS,
                            "close rival exists; cannot choose safely",
                            best_score, runner_up, alternatives)
    return GroundedSlot(raw_span, None, ConfidenceTier.UNKNOWN,
                        f"best score {best_score:.1f} below threshold "
                        f"{fuzzy_threshold}", best_score, runner_up,
                        alternatives)


def fuse_nbest(hypotheses: Sequence[str],
               candidates: Sequence[Candidate]) -> str:
    """Fuse N-best ASR hypotheses by candidate-hit voting (RECOVER-style).

    The hypothesis containing the most *exact* candidate substrings
    wins; ties keep the first hypothesis. This is a cheap, deterministic
    fusion: it recovers an entity that is correct in one hypothesis and
    corrupted in another, without any LLM call. It never invents text.
    """
    if not hypotheses:
        return ""
    if len(hypotheses) == 1:
        return hypotheses[0]

    def _hits(hyp: str) -> int:
        hyp_n = normalize_vietnamese(hyp)
        return sum(1 for c in candidates
                   if normalize_vietnamese(c.value) in hyp_n)

    return max(hypotheses, key=_hits)


# ---------------------------------------------------------------------------
# Vietnamese negation guard
# ---------------------------------------------------------------------------


class NegationKind(str, Enum):
    """Kind of negation/cancellation found in the transcript."""

    PROHIBITION = "prohibition"  # đừng / chớ / cấm: do NOT do X
    NEGATION = "negation"  # không + verb: not doing X
    CONTRAST = "contrast"  # không phải A mà là B: A negated, B affirmed
    NOT_YET = "not_yet"  # chưa: not yet — NOT a refusal of X


@dataclass
class NegationFinding:
    """One negation cue and the text it scopes over."""

    cue: str
    kind: NegationKind
    scope: str  # words following the cue up to a clause boundary
    negated_target: Optional[str] = None  # for CONTRAST: the rejected A
    affirmed_target: Optional[str] = None  # for CONTRAST: the chosen B


# Verbs that map to LifeMate write actions. Kept deliberately small and
# explicit: an unknown verb never silently maps to a tool.
_ACTION_VERBS = {
    "chuyển": "transfer",
    "gửi": "send",
    "bật": "turn_on",
    "tắt": "turn_off",
    "đặt": "order",
    "mua": "buy",
    "hủy": "cancel",
    "huỷ": "cancel",
    "xóa": "delete",
    "xoá": "delete",
    "thanh toán": "pay",
    "trả": "pay",
}

_CLAUSE_END = re.compile(r"[,.;!?]| và | rồi | nhưng | tuy nhiên ")


def _scope_after(text: str, start: int, max_words: int = 8) -> str:
    """Return the clause following ``start``, capped at ``max_words``."""
    tail = text[start:]
    match = _CLAUSE_END.search(tail)
    if match:
        tail = tail[:match.start()]
    return " ".join(tail.split()[:max_words])


def detect_negation(transcript: str) -> list[NegationFinding]:
    """Detect Vietnamese negation cues in ``transcript``.

    Returns findings in transcript order. Notes on the hard cases:

    * ``chưa`` is NOT a refusal: "chưa chuyển" means "has not
      transferred yet", so it is reported as ``NOT_YET`` and the guard
      below does not treat it as a prohibition.
    * ``hủy``/``huỷ`` alone is a *cancel action*, not a negation: "hủy
      đơn" means "cancel the order" and is itself a write. It is only a
      negation when explicitly negated ("không hủy").
    * ``không phải A mà là B`` is a contrast: A is negated, B is
      affirmed. A proposed write targeting A must be blocked, while a
      write targeting B is consistent with the utterance.
    """
    text = normalize_vietnamese(transcript)
    findings: list[NegationFinding] = []

    # Contrast first: "không phải A mà là B".
    contrast = re.search(
        r"không phải\s+(.+?)\s+mà là\s+(.+)", text)
    if contrast:
        findings.append(NegationFinding(
            cue="không phải ... mà là",
            kind=NegationKind.CONTRAST,
            scope=contrast.group(0),
            negated_target=contrast.group(1).strip(),
            affirmed_target=contrast.group(2).strip()))
        # Continue scanning: other cues may still matter.

    for match in re.finditer(r"\b(đừng|chớ|cấm)\b\s+(\S+)?", text):
        findings.append(NegationFinding(
            cue=match.group(1), kind=NegationKind.PROHIBITION,
            scope=_scope_after(text, match.start())))

    for match in re.finditer(r"\bkhông\b\s+(\S+)?", text):
        # Skip the "không phải" already handled as contrast.
        if (match.group(1) or "") == "phải":
            continue
        findings.append(NegationFinding(
            cue="không", kind=NegationKind.NEGATION,
            scope=_scope_after(text, match.start())))

    for match in re.finditer(r"\bchưa\b", text):
        findings.append(NegationFinding(
            cue="chưa", kind=NegationKind.NOT_YET,
            scope=_scope_after(text, match.start())))

    return findings


@dataclass
class GuardDecision:
    """Outcome of checking a proposed write against negation findings."""

    allowed: bool
    action: str  # "proceed" | "ask_missing_info" | "confirm"
    reason: str
    findings: list[NegationFinding] = field(default_factory=list)


def _phrase_in_text(phrase: str, text: str) -> bool:
    """True if ``phrase`` occurs in ``text`` as whole words.

    Word-set membership was the old bug: the two-word verb "thanh
    toán" was split into {"thanh", "toán"} and never matched the verb
    string, so "Không thanh toán hóa đơn" passed the guard. Phrase
    matching with word boundaries fixes multi-word verbs.
    """
    pattern = r"(?<!\w)" + re.escape(normalize_vietnamese(phrase)) + r"(?!\w)"
    return re.search(pattern, normalize_vietnamese(text)) is not None


def _verb_in_scope(scope: str, action: str) -> bool:
    """Check whether ``action``'s Vietnamese verb phrases appear in ``scope``."""
    return any(_phrase_in_text(verb, scope)
               for verb, act in _ACTION_VERBS.items() if act == action)


_STOPWORDS = frozenset({"của", "cho", "tới", "đến", "vào", "là", "một", "cái", "này"})


def _target_matches_text(target: str, text: str) -> bool:
    """True if ``target`` is mentioned in ``text``.

    A mention is the full normalised target as a substring, or every
    content token of the target appearing in the text. Token-ANY
    matching is deliberately NOT used: in "không bật đèn phòng khách,
    bật đèn phòng ngủ", the target "đèn phòng ngủ" shares tokens
    ("đèn", "phòng") with the negated clause, but it is not mentioned
    there -- only the all-tokens rule keeps the affirmed side allowed.
    """
    target_n = normalize_vietnamese(target)
    text_n = normalize_vietnamese(text)
    if not target_n:
        return False
    if target_n in text_n:
        return True
    tokens = [t for t in target_n.split() if t not in _STOPWORDS]
    if not tokens:
        return False
    text_tokens = set(text_n.split())
    return all(token in text_tokens for token in tokens)


def _split_clauses(text: str) -> list[str]:
    """Split normalised text into clauses on punctuation / conjunctions."""
    parts = re.split(r"[,.;!?]|\s+nhưng\s+|\s+tuy nhiên\s+", text)
    return [part.strip() for part in parts if part.strip()]


def guard_tool_call(
    proposed_action: str,
    proposed_target: str,
    transcript: str,
    hypotheses: Sequence[str] = (),
) -> GuardDecision:
    """Block a write that contradicts a detected negation.

    Rules (clause-scoped: a negation blocks only the action + target
    it actually covers in its own clause):

    * If the N-best hypotheses *disagree* on the presence of a negation
      cue (``không``/``đừng``/``chớ``), the negation is ambiguous:
      block the write and ask, never guess which hypothesis is right.
    * A prohibition/negation in a clause whose verb phrase matches the
      proposed action blocks the write when the proposed target is
      mentioned in that same clause, OR when the target is mentioned
      in no clause at all (a generic negation such as "không chuyển
      tiền" with no target named). It does NOT block when the target
      is mentioned only in a different, non-negated clause -- that is
      the "không bật đèn phòng khách, bật đèn phòng ngủ" case, where
      the old verb-only rule over-blocked the affirmed side.
    * A contrast blocks a write targeting the *negated* side only; a
      write targeting the *affirmed* side is allowed.
    * ``NOT_YET`` (``chưa``) never blocks by itself.
    * A cancel action (``hủy``) proposed on its own is not blocked by
      this guard; it is only blocked when explicitly negated.

    The guard never rewrites the proposed action into its opposite.

    Limits (heuristic, not a parser): double negation ("không phải
    không chuyển"), pronoun targets ("cái đó", "nó"), ellipsis, and
    verbs separated from their object by a long distance are NOT
    reliably resolved. When the target cannot be matched to any clause
    the guard fails closed (blocks, above) rather than guessing; a
    pronoun target that resolves to a negated action in context may
    still slip through, so the prompt assertion remains a second layer.
    """
    findings = detect_negation(transcript)

    # Dropped-negation risk across hypotheses.
    if hypotheses:
        cue_sets = []
        for hyp in hypotheses:
            cues = {f.cue for f in detect_negation(hyp)
                    if f.kind in (NegationKind.NEGATION,
                                  NegationKind.PROHIBITION)}
            cue_sets.append(cues)
        if len({frozenset(s) for s in cue_sets}) > 1:
            return GuardDecision(
                False, "ask_missing_info",
                "N-best hypotheses disagree on negation presence; "
                "negation is ambiguous, write blocked",
                findings)

    # Contrast first: it decides by target side, not by verb alone.
    for finding in findings:
        if finding.kind != NegationKind.CONTRAST:
            continue
        if (finding.negated_target
                and _target_matches_text(proposed_target, finding.negated_target)):
            return GuardDecision(
                False, "ask_missing_info",
                "contrast negates the proposed target "
                f"({finding.negated_target!r}); affirmed side is "
                f"{finding.affirmed_target!r}", [finding])
        # Affirmed side (or an unrelated target) is consistent with
        # this finding; other clauses may still block, so keep checking.

    # Clause-scoped negation: split the transcript and decide per clause.
    text_n = normalize_vietnamese(transcript)
    clauses = _split_clauses(text_n)
    # Clauses containing a contrast are already decided above; do not
    # let their "không" re-trigger a verb-only block.
    clauses = [c for c in clauses if "không phải" not in c]
    target_clauses = [i for i, c in enumerate(clauses)
                      if _target_matches_text(proposed_target, c)]
    for index, clause in enumerate(clauses):
        has_cue = bool(re.search(r"\b(đừng|chớ|cấm|không)\b", clause))
        if not has_cue:
            continue
        if not _verb_in_scope(clause, proposed_action):
            continue
        if index in target_clauses or not target_clauses:
            cue = next(w for w in ("đừng", "chớ", "cấm", "không") if re.search(rf"\b{w}\b", clause))
            return GuardDecision(
                False, "ask_missing_info",
                f"negation cue {cue!r} in clause {clause!r} scopes over "
                f"the proposed action {proposed_action!r} and target "
                f"{proposed_target!r}; write blocked, ask the user",
                findings)
    return GuardDecision(True, "proceed",
                         "no negation contradicts the proposed write",
                         findings)


PROMPT_ASSERTION_VI = """\
KHẲNG ĐỊNH PHỦ ĐỊNH (bắt buộc, kiểm tra trước mọi tool write):
1. Nếu yêu cầu chứa "không", "đừng", "chớ" bao phủ động từ của hành động
   (ví dụ "không chuyển", "đừng bật"), KHÔNG được gọi tool write đó.
2. "không phải A mà là B" chỉ phủ định A; chỉ được thực hiện B, không
   được thực hiện A.
3. "chưa" (chưa chuyển) KHÔNG phải là từ chối; "hủy đơn" tự nó là một
   hành động hủy, không phải phủ định của hành động khác.
4. Khi không chắc chắn về phủ định (các bản ASR mâu thuẫn nhau về
   "không"/"đừng"), gọi sys.ask_missing_info thay vì đoán và thay vì
   tự ý thực hiện hoặc tự ý đảo ngược hành động.
5. Slot đã đánh dấu UNKNOWN không được tự điền bằng giá trị đoán;
   thiếu slot thì hỏi lại, không gọi write với tham số đoán.
"""


# ---------------------------------------------------------------------------
# Demo (synthetic candidates only — not ZAIC data)
# ---------------------------------------------------------------------------

def _demo() -> None:
    """Run a small synthetic demo of grounding + negation guard."""
    contacts = [
        Candidate("Nguyễn Văn An", "contacts"),
        Candidate("Trần Thị Bình", "contacts"),
        Candidate("Lê Hoàng Nam", "contacts"),
    ]
    devices = [
        Candidate("Đèn phòng khách", "devices"),
        Candidate("Điều hòa phòng ngủ", "devices"),
    ]
    print("== Grounding ==")
    for raw, kind, cands in [
        ("Nguyễn Văn An", SlotKind.NAME, contacts),
        ("Nguyen Van An", SlotKind.NAME, contacts),  # diacritic-free input:
        # vowel marks (ê) are lost too, so this is NOT a tone-only match
        # and must not auto-ground; the correct behaviour is UNKNOWN.
        ("Trần Thị Bính", SlotKind.NAME, contacts),  # near-miss
        ("0901234567", SlotKind.ACCOUNT_ID,
         [Candidate("0901234567", "accounts")]),
        ("0901234568", SlotKind.ACCOUNT_ID,  # one digit differs: NEVER guess
         [Candidate("0901234567", "accounts")]),
        ("090 123 4567", SlotKind.ACCOUNT_ID,  # separators only: same id
         [Candidate("0901234567", "accounts")]),
        ("1,5", SlotKind.MONEY,  # 1.5, NOT 15: decimal separator kept
         [Candidate("15", "accounts")]),
        ("-100", SlotKind.MONEY,  # sign kept: -100 != 100
         [Candidate("100", "accounts")]),
        ("(100)", SlotKind.MONEY,  # accounting negative: -100 != 100
         [Candidate("100", "accounts")]),
        ("1,5 triệu", SlotKind.MONEY,  # unit scaling: 1.5m == 1500000
         [Candidate("1500000", "accounts")]),
        ("15/7", SlotKind.DATE,
         [Candidate("2025-07-15", "accounts")]),
        ("31/02/2025", SlotKind.DATE,  # invalid calendar date: UNKNOWN
         [Candidate("2025-02-28", "accounts")]),
    ]:
        result = ground_slot(raw, cands, kind)
        print(f"  {raw!r} -> {result.value!r} [{result.tier.value}] "
              f"({result.evidence})")

    print("== N-best fusion ==")
    fused = fuse_nbest(
        ["Chuyển tiền cho Trần Thị Bính", "Chuyển tiền cho Trần Thị Bình"],
        contacts)
    print(f"  fused: {fused!r}")

    print("== Negation guard ==")
    for action, target, text in [
        ("transfer", "Trần Thị Bình", "Chuyển tiền cho Trần Thị Bình"),
        ("transfer", "Trần Thị Bình", "Không chuyển tiền cho Trần Thị Bình"),
        ("turn_on", "Đèn phòng khách", "Đừng bật đèn phòng khách"),
        ("turn_on", "Đèn phòng ngủ",
         "Không phải đèn phòng khách mà là đèn phòng ngủ, bật lên"),
        ("turn_on", "Đèn phòng khách",
         "Không phải đèn phòng khách mà là đèn phòng ngủ, bật lên"),
        ("turn_on", "Đèn phòng ngủ",
         "Không bật đèn phòng khách, bật đèn phòng ngủ"),
        ("pay", "hóa đơn", "Không thanh toán hóa đơn"),
        ("transfer", "Trần Thị Bình", "Chưa chuyển tiền cho Trần Thị Bình"),
    ]:
        decision = guard_tool_call(action, target, text)
        print(f"  {action} / {target!r} / {text!r} -> "
              f"allowed={decision.allowed} action={decision.action} "
              f"({decision.reason})")
    print("== Ambiguous negation across N-best ==")
    decision = guard_tool_call(
        "transfer", "Trần Thị Bình", "Chuyển tiền cho Trần Thị Bình",
        hypotheses=["Chuyển tiền cho Trần Thị Bình",
                    "Không chuyển tiền cho Trần Thị Bình"])
    print(f"  allowed={decision.allowed} action={decision.action} "
          f"({decision.reason})")


if __name__ == "__main__":
    _demo()
