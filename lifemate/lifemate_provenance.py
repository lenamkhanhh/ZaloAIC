"""Typed-evidence rule engine for LifeMate provenance (Round 10, fixed).

Standalone module: standard library only, no model, no network, no simulator
access. It answers one question per tool argument: can CPU code re-derive
this exact value from evidence the agent legitimately observed (current
request, history, prior observations, declared defaults) -- or not?

HONEST NAMING (fix round): this is a RULE ENGINE returning Verdicts
with rule + detail attribution, not a graph DAG. Derivations are not
stored as nodes with edges, and invalidation is by rule order
(supersede/cancel) and by re-proof, not by graph propagation. A real DAG
would need explicit parent pointers per value plus invalidation when a
parent is superseded, cancelled, or shown failed; that structure is not
built here, so the report calls this a rule engine.

Design rules (applied literally):
- Total-or-reject: every parser returns a value or None. It never guesses.
- Whole spans only: a number must equal a whole parsed span (never a
  substring of a bigger number, phone number, identifier, date or time);
  a string must match as a whole phrase with identifier boundaries.
- Typed time: DATE, TIME and DATETIME are distinct. A date-only span
  never proves a datetime (hour_missing must not become 00:00).
- History needs a link: values from earlier turns prove a current-turn
  write only through an explicit reference phrase plus a unique
  candidate, never by silent reuse across tasks.
- Observations are typed: (tool, field, value, entity). Same app alone
  is not enough; the field must equal the slot, the entity must match
  (when the write names one), and a create may use only same-turn
  observations.
- A proposal is not evidence: prior-call arguments never prove a later
  value unless the base value itself is independently PROVEN (offset /
  duration parents), and failed calls contribute nothing.
- Token-level taint through the LLM is NOT attempted: paraphrase destroys
  token provenance. Derivations are built OUTSIDE the model from spans
  and observation values plus deterministic derivation functions.
- Names are compared by NFC + lowercase exact equality. Tone folding is
  LOSSY (Huong == Huong-with-different-tone) and is never used here.

Public API:
- parse_number_words(text) -> int | float | None
- find_number_spans(text) -> list[(span_text, value)]
- parse_relative_datetime(anchor, span) -> RelativeResult | None
- find_datetime_spans(text, anchor) -> list[(span_text, RelativeResult)]
- split_correction_segments(text) -> list[str]
- extract_slot_values(text, anchor) -> dict with 'numbers' and 'datetimes'
- Evidence dataclass + prove_argument(slot, value, evidence) -> Verdict
- prove_call(call, evidence) -> dict slot -> Verdict

Verdict statuses: PROVEN, UNPROVEN, AMBIGUOUS, SUPERSEDED.
SUPERSEDED means the value matches ONLY a superseded (corrected-away)
segment: a proven error, not a proof. It counts as would-block, never PROVEN.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta, date, timezone

__all__ = [
    "parse_number_words",
    "find_number_spans",
    "parse_relative_datetime",
    "find_datetime_spans",
    "split_correction_segments",
    "extract_slot_values",
    "Evidence",
    "Verdict",
    "prove_argument",
    "prove_call",
    "HISTORY_REF_PHRASES",
    "CORRECTION_MARKERS",
    "CANCEL_MARKERS",
]


def nfc_lower(s):
    return unicodedata.normalize("NFC", s or "").lower().strip()


# --------------------------------------------------------------------------
# Vietnamese number words: total-or-reject parser
# --------------------------------------------------------------------------

_DIGITS = {
    "không": 0, "một": 1, "hai": 2, "ba": 3, "bốn": 4, "năm": 5,
    "sáu": 6, "bảy": 7, "tám": 8, "chín": 9, "mười": 10,
}
# Contextual variants: "mốt" = 1 and "lăm" = 5 only after a tens component;
# "tư" = 4 (southern). They are accepted inside a segment, never standalone.
_VARIANT_DIGITS = {"mốt": 1, "lăm": 5, "tư": 4}
_BIG_UNITS = {"nghìn": 1000, "ngàn": 1000, "triệu": 1000000,
              "tỷ": 1000000000, "tỉ": 1000000000}
_NUM_WORD_TOKENS = (
    set(_DIGITS) | set(_VARIANT_DIGITS) | set(_BIG_UNITS)
    | {"trăm", "mươi", "chục", "rưỡi", "nửa", "lẻ", "linh", "kém"}
)


def _parse_segment(tokens):
    """Parse one <1000 segment (tokens between big units).

    Grammar: [HUNDRED] [TEN] [UNIT]
      HUNDRED = digit + "trăm"
      TEN     = "mười" | digit + "mươi" | digit + "chục" | "chục"
      UNIT    = digit | "mốt" | "lăm" | "tư"   (variants need TEN)
    A single all-digit token is accepted as the whole segment value.
    Returns (value, last_scale) or None. last_scale is the scale of the
    last component (100/10/1), used by the "rưỡi" rule.
    """
    if not tokens:
        return None
    if len(tokens) == 1 and tokens[0].isdigit():
        return int(tokens[0]), 1
    if any(t.isdigit() for t in tokens):
        return None  # mixed digit/word segments are rejected here
    if any(t not in _NUM_WORD_TOKENS for t in tokens):
        return None
    value = 0
    last_scale = 1
    i = 0
    n = len(tokens)
    # HUNDRED
    if n >= 2 and tokens[0] in _DIGITS and tokens[1] == "trăm":
        d = _DIGITS[tokens[0]]
        if d == 0:
            return None
        value += d * 100
        last_scale = 100
        i = 2
    elif tokens[0] == "trăm":
        return None
    # TEN
    if i < n:
        if tokens[i] == "mười":
            value += 10
            last_scale = 10
            i += 1
        elif (i + 1 < n and tokens[i] in _DIGITS and tokens[i + 1] == "mươi"):
            d = _DIGITS[tokens[i]]
            if d == 0:
                return None
            value += d * 10
            last_scale = 10
            i += 2
        elif (i + 1 < n and tokens[i] in _DIGITS and tokens[i + 1] == "chục"):
            d = _DIGITS[tokens[i]]
            if d == 0:
                return None
            value += d * 10
            last_scale = 10
            i += 2
        elif tokens[i] == "chục":
            value += 10
            last_scale = 10
            i += 1
    # Optional "lẻ"/"linh" separator before the unit.
    if i < n and tokens[i] in ("lẻ", "linh"):
        if value == 0:
            return None
        i += 1
    # UNIT
    if i < n:
        t = tokens[i]
        if t in _DIGITS:
            if t == "không":
                return None  # bare zero word is rejected (see module docstring)
            value += _DIGITS[t]
            last_scale = 1
            i += 1
        elif t in _VARIANT_DIGITS:
            # Variants are only valid after a tens component.
            if last_scale != 10:
                return None
            value += _VARIANT_DIGITS[t]
            last_scale = 1
            i += 1
        else:
            return None
    if i != n or value <= 0 or value >= 1000:
        return None
    return value, last_scale


def parse_number_words(text):
    """Parse Vietnamese number words to int/float, or None (reject).

    Handles: trăm/mươi/chục, nghìn/ngàn/triệu/tỷ/tỉ with STRICTLY
    descending big units (this is what makes double-scaling impossible:
    "hai triệu tám trăm nghìn" -> 2,800,000, never 2,000,800,000),
    "rưỡi" (X + half of X's scale), "nửa" (half of a unit, or "một nửa"
    = 0.5), "lẻ/linh" separators, "mốt/lăm/tư" variants, and
    "X kém Y" subtraction (both sides must parse, result must be > 0).
    Single all-digit tokens are accepted as segment values.
    Anything else -- unknown token, bare big unit, ascending/repeated big
    unit, bare "không" -- is rejected with None, never guessed.
    """
    if text is None:
        return None
    tokens = [nfc_lower(t) for t in re.findall(r"[^\W_]+", text, flags=re.UNICODE)]
    if not tokens:
        return None
    # "X kém Y" subtraction, exactly one "kém", both sides parseable.
    if "kém" in tokens:
        if tokens.count("kém") != 1:
            return None
        k = tokens.index("kém")
        left = parse_number_words(" ".join(tokens[:k]))
        right = parse_number_words(" ".join(tokens[k + 1:]))
        if left is None or right is None:
            return None
        result = left - right
        return result if result > 0 else None
    # "rưỡi" must be the final token: X rưỡi = X + 0.5 * scale(X).
    if tokens[-1] == "rưỡi":
        if len(tokens) < 2 or "rưỡi" in tokens[:-1] or "nửa" in tokens[:-1]:
            return None
        base = _parse_number_words_no_ruoi(tokens[:-1])
        if base is None:
            return None
        value, last_scale = base
        result = value + 0.5 * last_scale
        return int(result) if float(result).is_integer() else result
    parsed = _parse_number_words_no_ruoi(tokens)
    if parsed is None:
        return None
    value, _ = parsed
    return value


def _parse_number_words_no_ruoi(tokens):
    """Core parser without the rưỡi rule. Returns (value, last_scale)."""
    if not tokens or "rưỡi" in tokens or "nửa" in tokens:
        # "nửa" is handled by the caller-level special cases below.
        if tokens == ["nửa"]:
            return None
        if len(tokens) == 2 and tokens[0] == "nửa" and tokens[1] in _BIG_UNITS:
            return _BIG_UNITS[tokens[1]] // 2, _BIG_UNITS[tokens[1]]
        if tokens == ["một", "nửa"]:
            return 0.5, 1
        if len(tokens) >= 2 and tokens[0] == "nửa" and tokens[1] in _BIG_UNITS:
            return None  # "nửa triệu ..." with extra tokens is rejected
        return None
    # Split by big units, enforcing strictly descending units.
    total = 0
    last_big = None
    last_scale = 1
    current = []
    for tok in tokens:
        if tok in _BIG_UNITS:
            unit = _BIG_UNITS[tok]
            if last_big is not None and unit >= last_big:
                return None  # ascending or repeated big unit: reject
            if not current:
                return None  # bare big unit: reject
            seg = _parse_segment(current)
            if seg is None:
                return None
            seg_value, _ = seg
            total += seg_value * unit
            last_big = unit
            last_scale = unit
            current = []
        else:
            current.append(tok)
    if current:
        seg = _parse_segment(current)
        if seg is None:
            return None
        seg_value, seg_scale = seg
        total += seg_value
        last_scale = seg_scale
    elif last_big is None:
        return None
    return total, last_scale


# --------------------------------------------------------------------------
# Number spans in free text
# --------------------------------------------------------------------------

_DIGIT_FORM_RE = re.compile(
    r"(?<![A-Za-z0-9_])"
    r"(\d{1,3}(?:[.,]\d{3})+|\d+)"
    r"(?:\s*(k|tr))?"
    r"(?![.,]?\d)",
)
# Phone-like digit sequences: 0-led, 9-11 digits total, groups
# separated only by single spaces or dashes ("0914 061 230",
# "0914-061-230", "0914061230"). Used to suppress amount spans
# inside phone numbers (finding 2-P). The lookarounds keep the
# match from starting/ending inside a longer digit run.
_PHONE_SEQ_RE = re.compile(r"(?<!\d)0(?:[ -]?\d){8,10}(?!\d)")
_INT_UNIT_RE = re.compile(
    r"(?<![A-Za-z0-9_])(\d+)\s*(trăm\s+)?(nghìn|ngàn|triệu|tỷ|tỉ)\b")
_DECIMAL_UNIT_RE = re.compile(
    r"(?<![A-Za-z0-9_])(\d+)[.,](\d{1,2})\s*(nghìn|ngàn|triệu|tỷ|tỉ)\b")
_WORD_RUN_RE = re.compile(r"[^\W_]+", flags=re.UNICODE)


def _digit_form_value(num_str, suffix):
    num_str = num_str.replace(".", "").replace(",", "")
    try:
        value = int(num_str)
    except ValueError:
        return None
    if suffix == "k":
        value *= 1000
    elif suffix == "tr":
        value *= 1000000
    return value


def find_number_spans(text):
    """Find number values expressed in text.

    Returns a list of (span_text, value) covering: digit forms (plain,
    separator-grouped, "Nk"/"Ntr" suffix), decimal+unit forms ("1,5 triệu"),
    and maximal runs of number-word tokens parsed by parse_number_words.
    ISO dates and times are NOT matched as numbers (the digit regex refuses
    digits adjacent to '-' or ':').
    Phone numbers are NEVER amounts, including space/dash-grouped
    forms ("0914 061 230"): digit groups whose concatenation is a
    9-11 digit run starting with 0 are claimed up front as phone
    ranges, so neither the digit loop nor the word-run loop can
    resurrect their parts as amounts (reviewer finding 2-P).
    """
    if not text:
        return []
    found = []
    covered = []  # (start, end) character ranges already claimed
    # Phone-like sequences first: a 0-led run of 9-11 digits whose
    # groups are separated only by single spaces/dashes. Claiming
    # these ranges up front blocks every sub-span.
    phone_ranges = [(m.start(), m.end())
                    for m in _PHONE_SEQ_RE.finditer(text)]
    covered.extend(phone_ranges)

    def _claimed(start, end):
        return any(s <= start < e or s < end <= e for s, e in covered)

    for m in _DECIMAL_UNIT_RE.finditer(text):
        whole, frac, unit = m.group(1), m.group(2), m.group(3)
        value = float(whole + "." + frac) * _BIG_UNITS[unit]
        if float(value).is_integer():
            value = int(value)
        found.append((m.group(0), value))
        covered.append((m.start(), m.end()))
    # Integer digit + unit ("50 nghìn", "5 trăm nghìn"): must run BEFORE
    # the plain digit regex, or "50" would claim the span alone.
    for m in _INT_UNIT_RE.finditer(text):
        value = int(m.group(1))
        if m.group(2):
            value *= 100
        value *= _BIG_UNITS[m.group(3)]
        found.append((m.group(0), value))
        covered.append((m.start(), m.end()))
    for m in _DIGIT_FORM_RE.finditer(text):
        start, end = m.start(), m.end()
        if _claimed(start, end):
            continue
        # Skip digits that are part of a date/time (adjacent - or :).
        # NOTE: the boundary sentinel "" must NOT count as adjacent:
        # "" in "-:" is True in Python, so the old check silently
        # dropped every amount at the start/end of a text (found
        # while fixing 2-P; verified against frozen 3838d99f).
        before = text[start - 1] if start > 0 else ""
        after = text[end] if end < len(text) else ""
        if (before and before in "-:") or (after and after in "-:"):
            continue
        # Skip phone-like digit runs: a 9-11 digit run starting with 0
        # is a Vietnamese phone number, never an amount. (Grouped forms
        # are amounts unless their digits look exactly like a phone.)
        raw_digits = re.sub(r"[.,]", "", m.group(1))
        if m.group(2) is None and len(raw_digits) in (9, 10, 11) \
                and raw_digits.startswith("0") and raw_digits.isdigit():
            continue
        value = _digit_form_value(m.group(1), m.group(2))
        if value is None:
            continue
        found.append((m.group(0), value))
        covered.append((start, end))
    # Word runs: maximal consecutive number-word tokens. A run that is
    # a SINGLE pure-digit token is skipped here: pure-digit spans
    # belong to the digit-form regex above, with its phone / identifier
    # / date-time filters. Letting the word run re-add them would
    # resurrect exactly the spans those filters removed ("0914061230"
    # as an amount, "9526" out of "c_9526").
    tokens = [(m.group(0), m.start(), m.end())
              for m in _WORD_RUN_RE.finditer(text)]
    i = 0
    while i < len(tokens):
        word = nfc_lower(tokens[i][0])
        if word in _NUM_WORD_TOKENS or word.isdigit():
            j = i
            while (j < len(tokens)
                   and (nfc_lower(tokens[j][0]) in _NUM_WORD_TOKENS
                        or tokens[j][0].isdigit())):
                j += 1
            run = tokens[i:j]
            if len(run) == 1 and run[0][0].isdigit():
                i = j
                continue
            span_text = text[run[0][1]:run[-1][2]]
            if not _claimed(run[0][1], run[-1][2]):
                value = parse_number_words(" ".join(t[0] for t in run))
                if value is not None:
                    found.append((span_text, value))
                    covered.append((run[0][1], run[-1][2]))
            i = j
        else:
            i += 1
    return found

# --------------------------------------------------------------------------
# Vietnamese relative dates/times: total-or-reject, anchored to simulator
# --------------------------------------------------------------------------

@dataclass
class RelativeResult:
    """Result of parsing one date/time span.

    kind: 'datetime' (full date+time), 'date' (date only, hour missing),
          'time' (time only, on the anchor date), 'week_only'/'month_only'
          (a week/month reference with no day: never a day, never PROVEN).
    value: datetime (for 'datetime'/'time') or date (for 'date'), else None.
    hour_missing: True when the span gives a date but no hour.
    """
    kind: str
    value: object = None
    hour_missing: bool = False


_WEEKDAY_FORMS = [
    (r"thứ\s+2\b", 0), (r"thứ\s+hai\b", 0),
    (r"thứ\s+3\b", 1), (r"thứ\s+ba\b", 1),
    (r"thứ\s+4\b", 2), (r"thứ\s+tư\b", 2),
    (r"thứ\s+5\b", 3), (r"thứ\s+năm\b", 3),
    (r"thứ\s+6\b", 4), (r"thứ\s+sáu\b", 4),
    (r"thứ\s+7\b", 5), (r"thứ\s+bảy\b", 5),
    (r"chủ\s+nhật\b", 6),
]
_DAYPARTS = {"sáng", "trưa", "chiều", "tối", "đêm"}
# daypart + day combos that yield a date with no hour.
_DAYPART_DAY = {
    "sáng nay": 0, "chiều nay": 0, "tối nay": 0, "trưa nay": 0, "đêm nay": 0,
    "sáng mai": 1, "chiều mai": 1, "tối mai": 1, "trưa mai": 1,
    "sáng hôm qua": -1, "chiều hôm qua": -1, "tối hôm qua": -1,
    "sáng ngày mai": 1, "chiều ngày mai": 1, "tối ngày mai": 1,
    "sáng ngày kia": 2, "chiều ngày kia": 2, "tối ngày kia": 2,
}
_DAY_OFFSETS = {
    "hôm nay": 0, "hôm qua": -1, "hôm kia": -2,
    "ngày mai": 1, "ngày kia": 2, "ngày mốt": 2, "mai": 1,
}
_HOUR_WORDS = {"một": 1, "hai": 2, "ba": 3, "bốn": 4, "năm": 5, "sáu": 6,
               "bảy": 7, "tám": 8, "chín": 9, "mười": 10,
               "mười một": 11, "mười hai": 12}
_MINUTE_WORDS = {"năm": 5, "mười": 10, "mười lăm": 15,
                 "hai mươi": 20, "ba mươi": 30}


def _word_to_int(tok, table):
    tok = nfc_lower(tok)
    if tok.isdigit():
        return int(tok)
    return table.get(tok)


def _adjust_hour_for_daypart(hour, daypart):
    """Apply a Vietnamese daypart to a 1..12 hour, or None if ambiguous.

    sáng: 1..11 as-is, 12 rejected (midnight/noon ambiguity).
    trưa: only 12 -> 12, anything else rejected.
    chiều/tối: 1..11 -> +12, 12 rejected.
    đêm: 12 -> 0, 1..5 as-is (early morning), 6..11 -> +12.
    Hours already in 0..23 (explicit "15 giờ", "22:00") pass through.
    """
    if hour is None:
        return None
    if hour >= 13:
        return hour  # already 24h-style; daypart must not shift it
    if daypart is None:
        return hour
    if daypart == "sáng":
        return hour if 1 <= hour <= 11 else None
    if daypart == "trưa":
        return 12 if hour == 12 else None
    if daypart in ("chiều", "tối"):
        return hour + 12 if 1 <= hour <= 11 else None
    if daypart == "đêm":
        if hour == 12:
            return 0
        if 1 <= hour <= 5:
            return hour
        if 6 <= hour <= 11:
            return hour + 12
        return None
    return None


def _parse_time_part(span):
    """Parse the time component of a span.

    Returns (hour, minute) or None. Handles "X giờ", "X giờ Y",
    "X giờ Y phút", "X giờ kém Y" (= X-1 : 60-Y), "X rưỡi" (= X:30),
    "X giờ rưỡi", "X:Y", "XhY". Daypart adjustment is applied by the
    caller, which knows the daypart (if any) in the same span.
    """
    s = nfc_lower(span)
    m = re.search(r"(\d{1,2})[:h](\d{2})\b", s)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return hour, minute
        return None
    m = re.search(
        r"(\d{1,2}|một|hai|ba|bốn|năm|sáu|bảy|tám|chín|mười|mười một|mười hai)"
        r"\s*giờ\s*kém\s*(\d{1,2}|năm|mười|mười lăm|hai mươi|ba mươi)\b", s)
    if m:
        hour = _word_to_int(m.group(1), _HOUR_WORDS)
        sub = _word_to_int(m.group(2), _MINUTE_WORDS)
        if hour is None or sub is None or not (1 <= sub <= 59):
            return None
        if hour == 0:
            return None
        return hour - 1, 60 - sub
    m = re.search(
        r"(\d{1,2}|một|hai|ba|bốn|năm|sáu|bảy|tám|chín|mười|mười một|mười hai)"
        r"\s*giờ(?:\s+(\d{1,2}|năm|mười|mười lăm|hai mươi|ba mươi))?"
        r"(?:\s*phút)?\s*rưỡi\b", s)
    if m:
        hour = _word_to_int(m.group(1), _HOUR_WORDS)
        if hour is None:
            return None
        return hour, 30
    m = re.search(
        r"(\d{1,2}|một|hai|ba|bốn|năm|sáu|bảy|tám|chín|mười|mười một|mười hai)"
        r"\s*giờ(?:\s+(\d{1,2}|năm|mười|mười lăm|hai mươi|ba mươi))?"
        r"(?:\s*phút)?\b", s)
    if m:
        hour = _word_to_int(m.group(1), _HOUR_WORDS)
        minute = 0
        if m.group(2):
            minute = _word_to_int(m.group(2), _MINUTE_WORDS)
            if minute is None:
                return None
        if hour is None:
            return None
        return hour, minute
    m = re.search(
        r"\b(\d{1,2}|một|hai|ba|bốn|năm|sáu|bảy|tám|chín|mười|mười một|mười hai)"
        r"\s*rưỡi\b", s)
    if m:
        hour = _word_to_int(m.group(1), _HOUR_WORDS)
        if hour is None:
            return None
        return hour, 30
    return None


def _parse_word_date(s, anchor):
    """Parse a word-form absolute date: "ngày mười bảy tháng mười",
    "hôm hai mươi hai tháng mười", "mùng năm tháng giêng".

    Returns (date, "date"), (None, "invalid") for an impossible date, or
    (None, None) when no word date is present (caller falls through).
    Day/month are parsed by parse_number_words, so only genuine number
    words count; "tháng giêng" is January.
    """
    for m in re.finditer(r"\btháng\b", s):
        before = s[:m.start()].strip().split()
        after = s[m.end():].strip().split()
        for k in range(min(4, len(before)), 0, -1):
            cand = before[-k:]
            if cand and cand[0] in ("ngày", "hôm", "mùng"):
                cand = cand[1:]
            if not cand:
                continue
            day = parse_number_words(" ".join(cand))
            if day is None or not float(day).is_integer() \
                    or not (1 <= day <= 31):
                continue
            for j in range(min(3, len(after)), 0, -1):
                if after[0] == "giêng":
                    month, used = 1, 1
                else:
                    month = parse_number_words(" ".join(after[:j]))
                    used = j
                    if month is None or not float(month).is_integer() \
                            or not (1 <= month <= 12):
                        continue
                rest = after[used:]
                year = anchor.year
                if len(rest) >= 2 and rest[0] == "năm" \
                        and rest[1].isdigit():
                    year = int(rest[1])
                try:
                    return date(year, int(month), int(day)), "date"
                except ValueError:
                    return None, "invalid"
    return None, None


def _parse_day_part(span, anchor):
    """Parse the day component of a span against the anchor date.

    Returns (date | None, kind) where kind is 'date', 'week_only' or
    'month_only'. A (None, 'date') result means the span carries no day
    information (time-only spans resolve to the anchor date upstream).
    """
    s = nfc_lower(span)
    s = re.sub(r"\s+", " ", s).strip()
    # Absolute dates first.
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1))), "date"
        except ValueError:
            return None, "invalid"
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3))), "date"
        except ValueError:
            return None, "invalid"
    m = re.search(r"ngày\s+(\d{1,2})\s+tháng\s+(\d{1,2})"
                  r"(?:\s+năm\s+(\d{4}))?", s)
    if m:
        year = int(m.group(3)) if m.group(3) else anchor.year
        try:
            return date(year, int(m.group(2)), int(m.group(1))), "date"
        except ValueError:
            return None, "invalid"
    m = re.search(r"(\d{1,2})/(\d{1,2})\b", s)
    if m:
        try:
            return date(anchor.year, int(m.group(2)), int(m.group(1))), "date"
        except ValueError:
            return None, "invalid"
    # Word-form absolute dates ("ngày mười bảy tháng mười").
    word_date, word_kind = _parse_word_date(s, anchor)
    if word_kind == "invalid":
        return None, "invalid"
    if word_date is not None:
        return word_date, "date"
    # Daypart + day combos ("sáng mai", "tối nay", ...).
    for phrase, offset in sorted(_DAYPART_DAY.items(), key=lambda kv: -len(kv[0])):
        if phrase in s:
            return anchor.date() + timedelta(days=offset), "date"
    # Bare day offsets ("ngày mai", "hôm qua", ...). Longest first so
    # "ngày mai" wins over bare "mai".
    for phrase, offset in sorted(_DAY_OFFSETS.items(), key=lambda kv: -len(kv[0])):
        if re.search(r"\b" + re.escape(phrase) + r"\b", s):
            return anchor.date() + timedelta(days=offset), "date"
    # "N ngày nữa / trước / sau".
    m = re.search(r"(\d+|một|hai|ba|bốn|năm|sáu|bảy|tám|chín|mười)\s+ngày\s+"
                  r"(nữa|trước|sau)\b", s)
    if m:
        n = _word_to_int(m.group(1), _DIGITS)
        if n is None:
            return None, "invalid"
        delta = n if m.group(2) in ("nữa", "sau") else -n
        return anchor.date() + timedelta(days=delta), "date"
    # Weekdays, digit or word form, with optional "tuần này / tuần sau /
    # tuần tới".
    for pattern, wd in _WEEKDAY_FORMS:
        if re.search(pattern, s):
            anchor_date = anchor.date()
            monday = anchor_date - timedelta(days=anchor_date.weekday())
            if "tuần sau" in s or "tuần tới" in s:
                return monday + timedelta(days=7 + wd), "date"
            if "tuần này" in s:
                candidate = monday + timedelta(days=wd)
                if candidate < anchor_date:
                    return None, "invalid"
                return candidate, "date"
            # Bare weekday: strict next occurrence (1..7 days ahead).
            delta = (wd - anchor_date.weekday()) % 7
            if delta == 0:
                delta = 7
            return anchor_date + timedelta(days=delta), "date"
    # Week/month-only references: never a day, never PROVEN.
    if re.search(r"\btuần\s+(sau|tới|này)\b", s):
        return None, "week_only"
    if re.search(r"\btháng\s+(sau|tới|này)\b", s):
        return None, "month_only"
    return None, "date"


def _coerce_anchor(anchor):
    if isinstance(anchor, datetime):
        return anchor
    if isinstance(anchor, str):
        try:
            dt = datetime.fromisoformat(anchor)
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    return None


def parse_relative_datetime(anchor, span):
    """Parse ONE Vietnamese date/time span against an anchor timestamp.

    anchor: datetime or ISO string (the simulator turn timestamp -- never
    a model-invented "today"). span: the raw text span to parse.
    Returns a RelativeResult or None (reject). A span that yields only a
    daypart+day or a bare day returns kind 'date' with hour_missing=True;
    a span with an explicit hour returns kind 'datetime' (day resolved) or
    'time' (no day in the span: time on the anchor date).
    """
    dt_anchor = _coerce_anchor(anchor)
    if dt_anchor is None or not span:
        return None
    s = nfc_lower(span)
    s = re.sub(r"\s+", " ", s).strip()
    # Strip leading "lúc"/"vào lúc" for the day parse (time parse tolerates it).
    daypart = None
    for dp in ("sáng", "trưa", "chiều", "tối", "đêm"):
        if re.search(r"\b" + dp + r"\b", s):
            daypart = dp
            break
    day, day_kind = _parse_day_part(s, dt_anchor)
    if day_kind == "invalid":
        return None
    if day_kind in ("week_only", "month_only"):
        return RelativeResult(kind=day_kind, value=None, hour_missing=True)
    time_part = _parse_time_part(s)
    if time_part is not None:
        hour, minute = time_part
        if daypart is not None:
            hour = _adjust_hour_for_daypart(hour, daypart)
            if hour is None:
                return None
        if day is None:
            day = dt_anchor.date()
            kind = "time"
        else:
            kind = "datetime"
        try:
            value = datetime(day.year, day.month, day.day, hour, minute,
                             tzinfo=dt_anchor.tzinfo)
        except ValueError:
            return None
        return RelativeResult(kind=kind, value=value, hour_missing=False)
    if day is not None:
        return RelativeResult(kind="date", value=day, hour_missing=True)
    if daypart is not None:
        # Bare daypart ("sáng", "chiều") with no day: anchor date, no hour.
        return RelativeResult(kind="date", value=dt_anchor.date(),
                              hour_missing=True)
    return None


# Span finding: day/time patterns, longest first, non-overlapping.
_DATETIME_PATTERNS = [
    r"ngày\s+\d{1,2}\s+tháng\s+\d{1,2}(?:\s+năm\s+\d{4})?",
    r"\d{1,2}/\d{1,2}/\d{4}",
    r"\d{4}-\d{1,2}-\d{1,2}",
    r"\d{1,2}/\d{1,2}\b",
    # Word-form absolute dates ("ngày mười bảy tháng mười"): the parse
    # step validates the words, so the span pattern may be permissive.
    r"(?:ngày\s+|hôm\s+|mùng\s+)?(?:\w+\s+){1,3}tháng\s+\w+(?:\s+\w+)?",
    r"(?:sáng|chiều|tối|trưa|đêm)\s+(?:ngày\s+)?(?:mai|kia|mốt|nay|hôm qua)",
    r"thứ\s+[2-7]\s+tuần\s+(?:sau|tới|này)",
    r"thứ\s+(?:hai|ba|tư|năm|sáu|bảy)\s+tuần\s+(?:sau|tới|này)",
    r"(?:chủ\s+nhật|thứ\s+[2-7]|thứ\s+(?:hai|ba|tư|năm|sáu|bảy))",
    r"(?:ngày\s+)?(?:mai|kia|mốt)",
    r"hôm\s+(?:nay|qua|kia)",
    r"(?:\d+|một|hai|ba|bốn|năm|sáu|bảy|tám|chín|mười)\s+ngày\s+(?:nữa|trước|sau)",
    r"tuần\s+(?:sau|tới|này)",
    r"tháng\s+(?:sau|tới|này)",
    r"(?:lúc\s+|vào\s+lúc\s+)?(?:\d{1,2}|một|hai|ba|bốn|năm|sáu|bảy|tám|chín|mười|mười một|mười hai)\s*giờ\s*kém\s*(?:\d{1,2}|năm|mười|mười lăm|hai mươi|ba mươi)",
    r"(?:lúc\s+|vào\s+lúc\s+)?(?:\d{1,2}|một|hai|ba|bốn|năm|sáu|bảy|tám|chín|mười|mười một|mười hai)\s*giờ(?:\s+(?:\d{1,2}|năm|mười|mười lăm|hai mươi|ba mươi))?(?:\s*phút)?(?:\s*rưỡi)?",
    r"(?:lúc\s+|vào\s+lúc\s+)?(?:\d{1,2}|một|hai|ba|bốn|năm|sáu|bảy|tám|chín|mười|mười một|mười hai)\s*rưỡi(?:\s+(?:sáng|trưa|chiều|tối|đêm))?",
    r"\d{1,2}[:h]\d{2}\b",
    r"\b(?:sáng|trưa|chiều|tối|đêm)\b",
]
_DATETIME_RE = re.compile("|".join("(%s)" % p for p in _DATETIME_PATTERNS))


def find_datetime_spans(text, anchor):
    """Find date/time spans in text, each parsed against the anchor.

    A day-only match is extended with a following time expression (within
    ~25 characters, optionally after "lúc") so "ngày mai lúc 8 giờ" yields
    one datetime span, not two. Unparseable matches are dropped (reject).
    """
    dt_anchor = _coerce_anchor(anchor)
    if dt_anchor is None or not text:
        return []
    matches = [(m.start(), m.end()) for m in _DATETIME_RE.finditer(text)]
    out = []
    used_end = -1
    for start, end in matches:
        if start < used_end:
            continue
        span = text[start:end]
        parsed = parse_relative_datetime(dt_anchor, span)
        if parsed is None:
            continue
        # Daypart association for time-only spans, WITHOUT consuming the
        # daypart: Vietnamese puts the daypart after the hour ("bốn giờ
        # chiều", "9 giờ kém 15 tối") and the same daypart word may also
        # belong to a neighbouring day phrase ("tối mai"), which must
        # survive as its own span. Only whitespace may intervene; any
        # punctuation blocks the association.
        if parsed.kind == "time":
            before = text[max(0, start - 15):start]
            after = text[end:end + 15]
            mb = re.search(r"(sáng|trưa|chiều|tối|đêm)\s*$", before)
            ma = re.match(r"\s*(sáng|trưa|chiều|tối|đêm)\b", after)
            if mb or ma:
                probe = ((mb.group(1) + " ") if mb else "") + span \
                    + ((" " + ma.group(1)) if ma else "")
                reprobe = parse_relative_datetime(dt_anchor, probe)
                if reprobe is not None and reprobe.kind in ("time",
                                                            "datetime"):
                    parsed = reprobe
        # Extend a date-only span with a following time expression.
        if parsed.kind == "date" and parsed.hour_missing:
            tail = text[end:end + 30]
            tm = re.search(
                r"^(?:\s*(?:lúc|vào lúc)\s+)?"
                r"(?:\d{1,2}|một|hai|ba|bốn|năm|sáu|bảy|tám|chín|mười|"
                r"mười một|mười hai)\s*giờ", tail)
            if tm:
                merged = text[start:end + tm.end()]
                merged_parsed = parse_relative_datetime(dt_anchor, merged)
                if merged_parsed is not None and merged_parsed.kind in (
                        "datetime", "time"):
                    span, parsed = merged, merged_parsed
                    end = end + tm.end()
        out.append((span, parsed))
        used_end = end
    return out


# --------------------------------------------------------------------------
# Self-correction (supersede) and slot-value extraction
# --------------------------------------------------------------------------

CORRECTION_MARKERS = [
    "à không", "không phải", "ý là", "ý em là", "ý tôi là", "ý mình là",
    "sửa lại", "sửa thành", "đổi thành", "đổi lại", "thay bằng",
    "thay đổi thành", "mà là", "thôi lấy", "thôi, lấy",
]
HISTORY_REF_PHRASES = [
    "như lần trước", "như cũ", "số tiền cũ", "giờ cũ", "ngày cũ",
    "người cũ", "lần trước", "hôm trước", "như hôm trước", "giờ đó",
    "số đó", "ngày đó", "người đó", "như trước", "giống lần trước",
    "giống như lần trước", "như mọi khi",
]


def split_correction_segments(text):
    """Split a transcript on self-correction markers, in order.

    Returns one segment when no marker is present. The LAST segment holds
    the speaker's final intent; earlier segments are superseded.
    """
    if not text:
        return [""]
    s = nfc_lower(text)
    cuts = [0]
    for marker in CORRECTION_MARKERS:
        idx = 0
        while True:
            pos = s.find(marker, idx)
            if pos < 0:
                break
            cuts.append(pos + len(marker))
            idx = pos + len(marker)
    cuts = sorted(set(cuts))
    segments = []
    for a, b in zip(cuts, cuts[1:] + [len(s)]):
        segments.append(s[a:b].strip())
    return [seg for seg in segments if seg]


def extract_slot_values(text, anchor):
    """Extract candidate slot values from one text.

    Returns {'numbers': [values], 'datetimes': [RelativeResult],
    'has_correction': bool}. Numbers include digit forms and word forms;
    datetimes include date-only (hour_missing) and full results.
    """
    if not text:
        return {"numbers": [], "datetimes": [], "has_correction": False}
    numbers = [v for _, v in find_number_spans(text)]
    datetimes = [r for _, r in find_datetime_spans(text, anchor)]
    has_correction = any(m in nfc_lower(text) for m in CORRECTION_MARKERS)
    return {"numbers": numbers, "datetimes": datetimes,
            "has_correction": has_correction}

# --------------------------------------------------------------------------
# Evidence, verdicts, and the DAG prover
# --------------------------------------------------------------------------

@dataclass
class Verdict:
    status: str  # PROVEN | UNPROVEN | AMBIGUOUS | SUPERSEDED
    rule: str
    detail: str = ""


CANCEL_MARKERS = [
    "hủy", "huỷ", "không cần", "thôi khỏi", "bỏ qua", "đừng",
    "thôi đừng", "không chuyển nữa", "hủy bỏ", "huỷ bỏ",
]


@dataclass
class Evidence:
    """Everything the prover may use, assembled OUTSIDE the model.

    current_text: the current request transcript. Span rules
        (verbatim/number/relative_date) read ONLY this text: a value
        stated in an earlier turn proves a current-turn write only
        through the history_reference rule (explicit reference phrase +
        unique candidate), never by silent reuse.
    history_user_texts: prior user turns' transcripts, in order.
    history_observations: values seen in PRIOR TURNS' tool results, as
        (tool, field, value, entity) quadruples. Legacy (tool, scalar)
        pairs and plain scalars are accepted but NEVER prove anything:
        without a field they cannot satisfy the field rule, and without
        a tool they cannot satisfy the same-app rule. UNKNOWN source is
        never defaulted to same-app/PROVEN.
    turn_observations: values seen in THIS TURN's prefix reads, same
        quadruple form. Only turn observations may prove a create
        (a write with no entity id): a prior turn's observation belongs
        to another task unless an entity link says otherwise.
    history_call_args: [(tool, arguments)] or [(tool, arguments,
        succeeded)] of prior turns' assistant calls. Entries with
        succeeded=False are excluded from history candidates: a failed
        call's arguments are proposals, not facts.
    rosters: [{id, name}] contacts observed via search before the write.
    observation_events: [(tool, event_dict)] event-like dicts from prior
        results (same-sample prefix reads + history results), used by
        the offset/duration/assembly rules. Events prove only through
        an entity link (see those rules).
    prior_call_args: [(tool, arguments)] or [(tool, arguments,
        succeeded)] of same-sample calls BEFORE the write. Used only
        as offset bases, and only when the base value itself is
        independently PROVEN (see the offset rule).
    anchor: datetime or ISO string for relative-date resolution.
    defaults: {slot: value} ONLY for catalog/policy-declared defaults.
    """
    current_text: str = ""
    history_user_texts: list = field(default_factory=list)
    history_observations: list = field(default_factory=list)
    turn_observations: list = field(default_factory=list)
    history_call_args: list = field(default_factory=list)
    rosters: list = field(default_factory=list)
    observation_events: list = field(default_factory=list)
    prior_call_args: list = field(default_factory=list)
    anchor: object = None
    defaults: dict = field(default_factory=dict)


def _text_contains_phrase(form, text):
    """Whole-phrase match: form must occur with identifier boundaries on
    both sides, so "500000" never matches inside "1500000" and "c_10"
    never matches inside "c_100". Substring matching is the bug this
    replaces (Codex counterexample A)."""
    if not form or not text:
        return False
    hay = nfc_lower(text)
    form = nfc_lower(form)
    return re.search(r"(?<![A-Za-z0-9_])" + re.escape(form)
                     + r"(?![A-Za-z0-9_])", hay) is not None


def _value_matches_text(value, text):
    """Verbatim check for STRING values only (whole-phrase match).

    Numbers must never go through verbatim: they are proven only by
    find_number_spans, where a value must equal a whole parsed span.
    A numeric verbatim check is what let "500000" match inside
    "1500000", a phone number, or an identifier's digits.
    """
    if not text or not isinstance(value, str):
        return False
    return _text_contains_phrase(value, text)


def _gold_temporal_kind(value):
    """Classify a gold temporal value: 'datetime' | 'date' | 'time'."""
    if isinstance(value, datetime):
        return "datetime"
    if isinstance(value, date):
        return "date"
    if isinstance(value, str):
        v = value.strip()
        if re.fullmatch(r"\d{2}:\d{2}(:\d{2})?", v):
            return "time"
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
            return "date"
        if re.fullmatch(r"\d{4}-\d{2}", v):
            return "date"
        try:
            datetime.fromisoformat(v)
            return "datetime"
        except ValueError:
            return "date"
    return None


def _value_matches_datetime(value, parsed):
    """Typed comparison of a gold temporal value against a parsed span.

    DATE gold compares date parts only; TIME gold compares time parts
    only; DATETIME gold requires both. A date-only span therefore NEVER
    proves a datetime value -- not even a midnight one (Codex
    counterexample B: hour_missing must not become 00:00). A datetime
    span proves a date gold by its date part, and a time span proves a
    time gold by its time part.
    """
    if parsed is None or parsed.kind in ("week_only", "month_only"):
        return False
    kind = _gold_temporal_kind(value)
    if kind is None:
        return False
    try:
        if isinstance(value, datetime):
            gold_dt = value
        elif isinstance(value, str):
            v = value.strip()
            if kind == "time":
                if parsed.kind in ("datetime", "time") and parsed.value:
                    return parsed.value.strftime("%H:%M") == v[:5]
                return False
            if re.fullmatch(r"\d{4}-\d{2}", v):
                if parsed.value is None:
                    return False
                pv = parsed.value
                return (pv.year, pv.month) == (int(v[0:4]), int(v[5:7]))
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
                gold_dt = datetime(int(v[0:4]), int(v[5:7]), int(v[8:10]))
            else:
                gold_dt = datetime.fromisoformat(v)
        elif isinstance(value, date):
            gold_dt = datetime(value.year, value.month, value.day)
        else:
            return False
    except (ValueError, TypeError):
        return False
    if parsed.value is None:
        return False
    pv = parsed.value
    if kind == "date":
        if isinstance(pv, datetime):
            return (pv.year, pv.month, pv.day) == (
                gold_dt.year, gold_dt.month, gold_dt.day)
        return (pv.year, pv.month, pv.day) == (
            gold_dt.year, gold_dt.month, gold_dt.day)
    if parsed.kind == "date":
        # Date-only span, datetime gold: hour missing, never PROVEN.
        return False
    if isinstance(pv, datetime):
        return (pv.year, pv.month, pv.day, pv.hour, pv.minute) == (
            gold_dt.year, gold_dt.month, gold_dt.day, gold_dt.hour,
            gold_dt.minute)
    return False


def _scalar_equal(a, b):
    if a == b:
        return True
    if isinstance(a, str) and isinstance(b, str):
        if nfc_lower(a) == nfc_lower(b):
            return True
        # ISO datetimes compared to the minute (format variants).
        try:
            da = datetime.fromisoformat(a)
            db = datetime.fromisoformat(b)
            return (da.year, da.month, da.day, da.hour, da.minute) == \
                   (db.year, db.month, db.day, db.hour, db.minute)
        except (ValueError, TypeError):
            return False
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) \
            and not isinstance(a, bool) and not isinstance(b, bool):
        try:
            return float(a) == float(b)
        except (TypeError, ValueError):
            return False
    return False


def _norm_obs_entry(entry):
    """Normalise one observation entry to (tool, field, value, entity).

    Canonical form is a (tool, field, value, entity) quadruple, where
    field is the result dict's leaf key (e.g. "amount", "balance",
    "start") and entity is the enclosing object's id-ish value or None.
    Legacy (tool, scalar) pairs yield field=None (unknown field: can
    never satisfy the field rule) and plain scalars yield tool=None
    (unknown app: can never satisfy the same-app rule). Both are kept
    visible for diagnostics but prove nothing.
    """
    if isinstance(entry, tuple) and len(entry) == 4:
        return entry
    if isinstance(entry, tuple) and len(entry) == 2:
        return entry[0], None, entry[1], None
    return None, None, entry, None


def _observation_candidates(value, turn_obs, history_obs, tool, slot,
                            call_args):
    """Match a value against structured observations.

    Returns (status, rule, detail) where status is "proven",
    "ambiguous", "cross_app", "unknown" or None (no match at all).
    A match must satisfy ALL of:
      * same app family as the write tool;
      * field == slot exactly (a "balance" field never proves an
        "amount" -- Codex counterexample D);
      * entity: when the write references entity ids, the
        observation's entity MUST be one of the write's ids. An
        entity-less (None) observation does NOT prove an id-linked
        write (reviewer finding 2-N): a prior turn's unattributed
        value belongs to another task unless an entity link ties
        it here; the old None allowance let a bare result dict
        prove an id-linked write with no reference phrase at all.
        (For creates, which reference no ids, the rule below
        still allows same-turn unattributed observations only.)
      * source: a write with no entity id (a create) may use only
        same-turn observations; a prior turn's observation belongs to
        another task unless an entity link says otherwise.
    Uniqueness: >1 distinct entities among eligible matches is
    AMBIGUOUS, not proof (two tasks with the same value are not one
    source of truth).
    """
    app = (tool or "").split(".", 1)[0] if "." in (tool or "") else ""
    call_ids = set()
    if call_args:
        for key, val in call_args.items():
            if key.endswith("_id") and isinstance(val, str):
                call_ids.add(val)
    eligible = []   # (entity, source)
    cross = False
    unknown = False
    for source, obs_list in (("turn", turn_obs), ("history", history_obs)):
        for entry in obs_list or []:
            obs_tool, field, obs_value, entity = _norm_obs_entry(entry)
            if not _scalar_equal(obs_value, value):
                continue
            obs_app = (obs_tool or "").split(".", 1)[0] \
                if "." in (obs_tool or "") else ""
            if obs_tool is None or field is None:
                unknown = True
                continue
            if obs_app != app:
                cross = True
                continue
            if field != slot:
                continue
            if call_ids:
                if entity not in call_ids:
                    continue
            else:
                if source != "turn":
                    continue
            eligible.append((entity, source))
    if eligible:
        entities = {e for e, _ in eligible if e is not None}
        if len(entities) > 1:
            return ("ambiguous", "observation_ambiguous",
                    "%d distinct observation entities match" % len(entities))
        return ("proven", "observation",
                "unique %s observation %s=%r"
                % (eligible[0][1], slot, value))
    if cross:
        return ("cross_app", "observation_cross_app",
                "value seen only in a different app's result")
    if unknown:
        return ("unknown", "observation_unknown_source",
                "value seen only in untyped (field/app unknown) entries")
    return (None, None, None)


def _roster_intent(entry, rosters, current_text):
    """Does the current request identify this roster entry, and only it?

    Returns "proven" (an exclusive mention), "ambiguous" (the mention is
    shared with another entry, e.g. a duplicate name), or "none" (no
    mention). A roster proves a contact EXISTS; picking the right
    person needs a distinguishing mention IN THE USER'S OWN TEXT: the
    entry's full name as a phrase, or a name token no other entry
    shares. Token-level matching prevents "Minh" from claiming "Minh Ha"
    (a full-name phrase match is void when it extends into another
    entry's full name at the same position).

    Deliberately NOT a mention source: the proposal's own contact_name
    argument. That value comes from the model, not the user -- a model
    that invents contact_name="Minh" must not thereby prove the user
    chose Minh. (Fix round 2: the contact_name clause was removed
    after this self-generation loophole was found.)
    """
    target_id = entry.get("id")
    target_name = nfc_lower(entry.get("name"))
    if not target_name:
        return "none"
    target_tokens = target_name.split()
    text_tokens = [nfc_lower(t) for t in
                   re.findall(r"[^\W_]+", current_text or "",
                              flags=re.UNICODE)]
    # Mentions come from the user text only.
    shared = False
    found = False
    # Full-name phrase occurrences (token level).
    n = len(target_tokens)
    for pos in range(len(text_tokens) - n + 1):
        if text_tokens[pos:pos + n] != target_tokens:
            continue
        extends = False
        for other in rosters or []:
            if other.get("id") == target_id:
                continue
            other_tokens = nfc_lower(other.get("name")).split()
            if len(other_tokens) > n and \
                    text_tokens[pos:pos + len(other_tokens)] == other_tokens:
                extends = True
        if extends:
            continue
        found = True
        for other in rosters or []:
            if other.get("id") != target_id \
                    and nfc_lower(other.get("name")) == target_name:
                shared = True
    # Single-token mentions, only when the token is exclusive to target.
    other_token_sets = []
    for other in rosters or []:
        if other.get("id") != target_id:
            other_token_sets.append(set(nfc_lower(other.get("name")).split()))
    for tok in target_tokens:
        if tok in text_tokens and not any(tok in s
                                          for s in other_token_sets):
            found = True
    if not found:
        return "none"
    return "ambiguous" if shared else "proven"


def _parse_gold_datetime(value):
    try:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            return datetime.fromisoformat(value)
    except ValueError:
        return None
    return None


def _find_offset_cues(text):
    """Find (timedelta, direction) pairs: a duration span plus a nearby
    direction word. direction -1 = earlier ("trước", "sớm"), +1 = later
    ("sau", "muộn", "thêm", "lùi"). A bare "X giờ" counts as a duration
    only when a direction word precedes it within 15 characters, so clock
    times ("8 giờ") are never mistaken for durations.
    Direction words are bound to their duration span BY PROXIMITY
    (reviewer finding 2-O): the old code searched the whole string
    ("or word in s"), so a text stating one direction could prove
    the opposite direction from a stray word elsewhere in the text.
    """
    s = nfc_lower(text or "")
    cues = []
    minus = ("trước", "sớm")
    plus = ("sau", "muộn", "thêm", "lùi")
    for m in re.finditer(r"nửa tiếng", s):
        window = s[max(0, m.start() - 20):m.end() + 20]
        for word, direction in (("trước", -1), ("sớm", -1), ("sau", 1),
                                ("muộn", 1), ("thêm", 1), ("lùi", 1)):
            if word in window:
                cues.append((timedelta(minutes=30), direction))
    for m in re.finditer(
            r"(\d+|một|hai|ba|bốn|năm|sáu|bảy|tám|chín|mười)\s*(tiếng|phút)",
            s):
        n = _word_to_int(m.group(1), _DIGITS)
        if n is None:
            continue
        delta = timedelta(hours=n) if m.group(2) == "tiếng" \
            else timedelta(minutes=n)
        window = s[max(0, m.start() - 20):m.start()]
        for word in minus:
            if word in window:
                cues.append((delta, -1))
        for word in plus:
            if word in window:
                cues.append((delta, 1))
    for m in re.finditer(
            r"(\d+|một|hai|ba|bốn|năm|sáu|bảy|tám|chín|mười)\s*giờ\b", s):
        window = s[max(0, m.start() - 15):m.start()]
        if not any(w in window for w in minus + plus):
            continue
        n = _word_to_int(m.group(1), _DIGITS)
        if n is None:
            continue
        for word in minus:
            if word in window:
                cues.append((timedelta(hours=n), -1))
        for word in plus:
            if word in window:
                cues.append((timedelta(hours=n), 1))
    # Deduplicate.
    return sorted(set(cues))


def _call_entry_succeeded(entry):
    """History/prior call entries may be (tool, args) or
    (tool, args, succeeded). Two-tuples carry NO outcome information
    and are treated as unknown -- i.e. not evidence. Only an explicit
    succeeded=True flag counts: a proposal, a failed write, and an
    outcome nobody recorded are all equally not facts."""
    if len(entry) >= 3:
        return bool(entry[2])
    return False


def _history_candidates(slot, tool, evidence):
    """Distinct prior values for the same tool+slot in history calls.

    Only calls recorded as succeeded contribute: a failed call's
    arguments are proposals, not facts, and a call whose outcome is
    unknown (two-tuple) is not evidence either. Callers must pass
    succeeded flags where they know them (the audit does).
    """
    seen = []
    for entry in evidence.history_call_args:
        if not _call_entry_succeeded(entry):
            continue
        t, args = entry[0], entry[1]
        if t == tool and isinstance(args, dict) and slot in args:
            v = args[slot]
            if v not in seen:
                seen.append(v)
    return seen


def _history_text_candidates(slot, evidence):
    """Values for a slot stated in history user turns (span-derived).

    A history turn's own words can be the referenced value ("số tiền
    cũ" pointing at a number the user said earlier). Only span-parsed
    values count: substrings never do.
    """
    seen = []
    for text in evidence.history_user_texts or []:
        if slot == "amount":
            for _, v in find_number_spans(text):
                if v not in seen:
                    seen.append(v)
        elif slot in ("time", "date", "start", "end"):
            for _, parsed in find_datetime_spans(text, evidence.anchor):
                if parsed.kind in ("datetime", "time", "date") \
                        and parsed.value is not None:
                    v = parsed.value
                    if isinstance(v, datetime):
                        v = v.isoformat()
                    elif isinstance(v, date):
                        v = v.isoformat()
                    if v not in seen:
                        seen.append(v)
    return seen


def _segment_refers_to_history_value(slot, value, segment, tool,
                                     evidence):
    """True when a segment references history and the value is the
    unique history candidate for the slot (typed match). Used by the
    supersede check so a corrected-away history reference reports
    SUPERSEDED (a proven error) instead of silently UNPROVEN."""
    if not any(p in nfc_lower(segment) for p in HISTORY_REF_PHRASES):
        return False
    candidates = _history_candidates(slot, tool, evidence)
    for cand in _history_text_candidates(slot, evidence):
        if cand not in candidates:
            candidates.append(cand)
    return len(candidates) == 1 and _history_value_matches(
        candidates[0], value, slot)


def _history_value_matches(candidate, value, slot):
    """Typed equality for history candidates vs the proposed value."""
    if candidate == value:
        return True
    if isinstance(candidate, (int, float)) and isinstance(value, (int, float)) \
            and not isinstance(candidate, bool) \
            and not isinstance(value, bool):
        try:
            return float(candidate) == float(value)
        except (TypeError, ValueError):
            return False
    if slot in ("time", "date", "start", "end") \
            and isinstance(candidate, str) and isinstance(value, str):
        kind = _gold_temporal_kind(value)
        if kind == "time":
            try:
                return datetime.fromisoformat(candidate).strftime("%H:%M") \
                    == value.strip()[:5]
            except ValueError:
                return False
        if kind == "date":
            try:
                cdt = datetime.fromisoformat(candidate)
                vdt = datetime.fromisoformat(value.strip())
                return (cdt.year, cdt.month, cdt.day) == (
                    vdt.year, vdt.month, vdt.day)
            except ValueError:
                return False
        return _scalar_equal(candidate, value)
    return False


def prove_argument(slot, value, tool, evidence, rules=None, call_args=None,
                   _depth=0):
    """Prove one tool argument against evidence.

    This is a typed-evidence RULE ENGINE, not a graph DAG: each verdict
    cites the rule and evidence that derived it, but derivations are not
    stored as nodes with edges, and invalidation is by rule order
    (supersede/cancel), not by graph propagation. Calling it a DAG
    would overclaim; the report says so explicitly.

    Rule order (first success wins; attribution is auditable):
      supersede-check (only when correction markers exist),
      verbatim (strings only, whole-phrase; numbers go via spans),
      number spans (whole parsed spans, current text only),
      relative_date (typed date/time/datetime, current text only),
      observation (same app + exact field + entity + source + unique),
      roster (existence + exclusive intent mention),
      history_reference (explicit phrase in the latest segment +
        unique candidate, cancel-gated),
      datetime_assembly (same-text unique pairing, or text side +
        id-linked event primary field; no cross-text linker),
      offset (id-linked event bases; prior-call bases only at depth 0,
        entity-linked or anaphoric, and only when the base value itself
        is independently PROVEN),
      duration (id-linked event duration, and only when the call's own
        start is independently PROVEN -- a hallucinated start is never
        a parent),
      default.
    rules: optional subset to run (used for the verbatim-only baseline).
    call_args: the full arguments of the call (enables id-linking, the
    duration rule, and roster intent).
    _depth: internal recursion guard for base/start proofs (callers
    leave it at 0).
    """
    all_rules = ["supersede", "verbatim", "number_words", "relative_date",
                 "observation", "roster", "history_reference",
                 "datetime_assembly", "offset", "duration", "default"]
    wanted = set(rules) if rules else set(all_rules)
    texts_current = evidence.current_text or ""
    cross_app_candidate = False
    unknown_candidate = False
    roster_no_intent = False

    # --- supersede: correction markers change what counts as evidence.
    if "supersede" in wanted and any(
            m in nfc_lower(texts_current) for m in CORRECTION_MARKERS):
        segments = split_correction_segments(texts_current)
        if len(segments) >= 2:
            latest = segments[-1]
            earlier = " ".join(segments[:-1])
            in_latest = _slot_value_in_text(slot, value, latest,
                                             evidence.anchor) or \
                _segment_refers_to_history_value(slot, value, latest,
                                                 tool, evidence)
            in_earlier = _slot_value_in_text(slot, value, earlier,
                                              evidence.anchor) or \
                _segment_refers_to_history_value(slot, value, earlier,
                                                 tool, evidence)
            if in_latest and not in_earlier:
                return Verdict("PROVEN", "supersede",
                               "value from latest correction segment only")
            if in_earlier and not in_latest:
                return Verdict("SUPERSEDED", "supersede",
                               "value matches only a corrected-away segment")

    # --- verbatim: a string value occurs as a whole phrase in the
    # current request. Numbers never use this rule (see
    # _value_matches_text): they must equal a whole parsed span.
    if "verbatim" in wanted and isinstance(value, str):
        if _value_matches_text(value, texts_current):
            return Verdict("PROVEN", "verbatim",
                           "string form found as a whole phrase")

    # --- number spans: a digit or word span parses exactly to the value.
    if "number_words" in wanted and isinstance(value, (int, float)) \
            and not isinstance(value, bool):
        for span_text, v in find_number_spans(texts_current):
            if float(v) == float(value):
                rule = "number_digits" if re.search(r"\d", span_text) \
                    else "number_words"
                return Verdict("PROVEN", rule,
                               "number span parses to value")

    # --- relative_date: a date/time span parses exactly to the value
    # (typed: date-only never proves datetime, even midnight).
    if "relative_date" in wanted and slot in (
            "time", "date", "start", "end"):
        for _, parsed in find_datetime_spans(texts_current,
                                             evidence.anchor):
            if _value_matches_datetime(value, parsed):
                return Verdict("PROVEN", "relative_date",
                               "span %s parses to value" % parsed.kind)

    # --- observation: structured, field-exact, entity-bound, source-
    # aware, unique. Contact slots are not proven by observations:
    # contacts come from rosters (existence + intent) and history.
    if "observation" in wanted and slot not in ("contact_id", "to"):
        status, rule, detail = _observation_candidates(
            value, evidence.turn_observations, evidence.history_observations,
            tool, slot, call_args)
        if status == "proven":
            return Verdict("PROVEN", rule, detail)
        if status == "ambiguous":
            return Verdict("AMBIGUOUS", rule, detail)
        if status == "cross_app":
            cross_app_candidate = True
        elif status == "unknown":
            unknown_candidate = True

    # --- roster: a contact_id observed via search before the write,
    # plus an exclusive intent mention of that contact.
    if "roster" in wanted and slot in ("contact_id", "to"):
        for entry in evidence.rosters:
            if isinstance(entry, dict) and entry.get("id") == value:
                intent = _roster_intent(entry, evidence.rosters,
                                        texts_current)
                if intent == "proven":
                    return Verdict("PROVEN", "roster",
                                   "contact_id in roster + exclusive "
                                   "intent mention")
                if intent == "ambiguous":
                    return Verdict("AMBIGUOUS", "roster_ambiguous",
                                   "intent mention is shared with another "
                                   "roster entry")
                roster_no_intent = True
                break

    # --- history_reference: the current request explicitly points at
    # history ("số tiền cũ", ...). The trigger must be in the LATEST
    # segment when a correction exists (the latest intent governs), and
    # a cancellation anywhere in the current request disables it.
    if "history_reference" in wanted:
        cancelled = any(m in nfc_lower(texts_current)
                        for m in CANCEL_MARKERS)
        if not cancelled:
            trigger_text = texts_current
            if any(m in nfc_lower(texts_current)
                   for m in CORRECTION_MARKERS):
                segments = split_correction_segments(texts_current)
                if segments:
                    trigger_text = segments[-1]
            if any(p in nfc_lower(trigger_text)
                   for p in HISTORY_REF_PHRASES):
                candidates = _history_candidates(slot, tool, evidence)
                for cand in _history_text_candidates(slot, evidence):
                    if cand not in candidates:
                        candidates.append(cand)
                matches = [c for c in candidates
                           if _history_value_matches(c, value, slot)]
                if len(candidates) == 1 and matches:
                    return Verdict("PROVEN", "history_reference",
                                   "unique history candidate for slot")
                # AMBIGUOUS only when >= 2 candidates actually MATCH
                # the value (reviewer finding 6-HR): a value no
                # candidate supports is UNPROVEN, not ambiguous,
                # and a single match among several candidates falls
                # through to the later rules (conservative: the
                # trigger phrase alone does not disambiguate which
                # history value the user meant).
                if len(matches) >= 2:
                    return Verdict("AMBIGUOUS", "history_reference",
                                   "%d history candidates match"
                                   % len(matches))

    # --- datetime_assembly: an incomplete date span + an incomplete
    # time span combine to the gold datetime. Two legitimate pairings
    # only: (a) same current text, unique date and unique time in that
    # text (a forced pairing -- multi-date/time texts are ambiguous);
    # (b) one side from the current text (unique in the text) and the
    # other from the PRIMARY time field (start, else time) of an
    # id-linked observation event. Cross-text pairing via a bare
    # linker ("lại") is NOT a task link and is removed: it let one
    # task's time prove another task's reminder (counterexample C).
    # Parts of complete datetime spans are never recycled.
    if "datetime_assembly" in wanted and slot in ("time", "start", "end"):
        gold_dt = _parse_gold_datetime(value)
        if gold_dt is not None:
            text_dates = set()
            text_times = set()
            for _, parsed in find_datetime_spans(texts_current,
                                                 evidence.anchor):
                if parsed.kind == "date" and parsed.value is not None:
                    pv = parsed.value
                    text_dates.add((pv.year, pv.month, pv.day))
                if parsed.kind == "time" and parsed.value is not None:
                    pv = parsed.value
                    text_times.add((pv.hour, pv.minute))
            want_date = (gold_dt.year, gold_dt.month, gold_dt.day)
            want_time = (gold_dt.hour, gold_dt.minute)
            if want_date in text_dates and want_time in text_times \
                    and len(text_dates) == 1 and len(text_times) == 1:
                return Verdict("PROVEN", "datetime_assembly",
                               "unique date + unique time in current text")
            call_ids = set()
            if call_args:
                for key, val in call_args.items():
                    if key.endswith("_id") and isinstance(val, str):
                        call_ids.add(val)
            if call_ids:
                for obs_tool, event in evidence.observation_events or []:
                    if not isinstance(event, dict):
                        continue
                    ev_ids = {str(event.get(k)) for k in
                              ("id", "event_id", "alarm_id", "reminder_id")
                              if event.get(k)}
                    if not (ev_ids & call_ids):
                        continue
                    primary = event.get("start") or event.get("time")
                    base = _parse_gold_datetime(primary) \
                        if isinstance(primary, str) else None
                    if base is None:
                        continue
                    if want_date in text_dates and len(text_dates) == 1 \
                            and (base.hour, base.minute) == want_time:
                        return Verdict("PROVEN", "datetime_assembly",
                                       "text date + id-linked event time")
                    if want_time in text_times and len(text_times) == 1 \
                            and (base.year, base.month, base.day) \
                            == want_date:
                        return Verdict("PROVEN", "datetime_assembly",
                                       "id-linked event date + text time")

    # --- offset: an observation event (id-linked) or a prior trajectory
    # call, shifted by a duration the text states with a direction word
    # ("muộn hơn nửa tiếng", "trước đó một tiếng").
    # Prior-call bases are allowed ONLY at depth 0, and each base value
    # must itself be PROVEN at depth 1 (offset there uses event bases
    # only, so no chains of guesses). A prior-call base additionally
    # needs a link: shared entity id with the write, or -- for creates
    # -- an anaphoric cue ("đó") tying it to the current instruction.
    # An unrelated prior alarm's time never bases a calendar move
    # (counterexample E).
    if "offset" in wanted and slot in ("time", "start", "end"):
        gold_dt = _parse_gold_datetime(value)
        if gold_dt is not None:
            cues = _find_offset_cues(texts_current)
            if cues:
                app = (tool or "").split(".", 1)[0] \
                    if "." in (tool or "") else ""
                id_args = set()
                if call_args:
                    for key, val in call_args.items():
                        if key.endswith("_id") and isinstance(val, str):
                            id_args.add(val)
                bases = []
                for obs_tool, event in evidence.observation_events or []:
                    if not isinstance(event, dict):
                        continue
                    if (obs_tool or "").split(".", 1)[0] != app:
                        continue
                    ev_ids = {str(event.get(k)) for k in
                              ("id", "event_id", "alarm_id", "reminder_id")
                              if event.get(k)}
                    if not id_args or not (ev_ids & id_args):
                        continue
                    for key in ("start", "time"):
                        if isinstance(event.get(key), str):
                            base = _parse_gold_datetime(event[key])
                            if base is not None:
                                bases.append(base)
                if _depth == 0:
                    anaphoric = re.search(r"\bđó\b",
                                          nfc_lower(texts_current)) \
                        is not None
                    for entry in evidence.prior_call_args or []:
                        if not _call_entry_succeeded(entry):
                            continue
                        ptool, pargs = entry[0], entry[1]
                        parg_ids = set()
                        if isinstance(pargs, dict):
                            for key, val in pargs.items():
                                if key.endswith("_id") \
                                        and isinstance(val, str):
                                    parg_ids.add(val)
                        linked = bool(parg_ids & id_args) \
                            or (not id_args and anaphoric)
                        if not linked:
                            continue
                        if isinstance(pargs, dict):
                            for pk in ("time", "start", "end"):
                                if isinstance(pargs.get(pk), str):
                                    base = _parse_gold_datetime(pargs[pk])
                                    if base is None:
                                        continue
                                    check = prove_argument(
                                        pk, pargs[pk], ptool, evidence,
                                        call_args=pargs, _depth=_depth + 1)
                                    if check.status == "PROVEN":
                                        bases.append(base)
                for delta, direction in cues:
                    for base in bases:
                        cand = base + direction * delta
                        if (cand.year, cand.month, cand.day, cand.hour,
                                cand.minute) == (gold_dt.year, gold_dt.month,
                                                 gold_dt.day, gold_dt.hour,
                                                 gold_dt.minute):
                            return Verdict("PROVEN", "offset",
                                           "linked base %s direction"
                                           % ("+" if direction > 0 else "-"))

    # --- duration: an end implied by a PROVEN start plus the original
    # event duration. The call's own start must first be PROVEN at
    # depth 1: a hallucinated start is never a parent (counterexample
    # class: "không coi start bịa là parent đã PROVEN").
    if "duration" in wanted and slot == "end" and call_args \
            and "start" in call_args:
        gold_dt = _parse_gold_datetime(value)
        start_dt = _parse_gold_datetime(call_args["start"])
        if gold_dt is not None and start_dt is not None:
            start_check = prove_argument(
                "start", call_args["start"], tool, evidence,
                call_args=call_args, _depth=_depth + 1)
            if start_check.status == "PROVEN":
                app = (tool or "").split(".", 1)[0] \
                    if "." in (tool or "") else ""
                id_args = set()
                for key, val in call_args.items():
                    if key.endswith("_id") and isinstance(val, str):
                        id_args.add(val)
                for obs_tool, event in evidence.observation_events or []:
                    if not isinstance(event, dict):
                        continue
                    if (obs_tool or "").split(".", 1)[0] != app:
                        continue
                    ev_ids = {str(event.get(k)) for k in
                              ("id", "event_id", "alarm_id", "reminder_id")
                              if event.get(k)}
                    if not id_args or not (ev_ids & id_args):
                        continue
                    try:
                        obs_start = _parse_gold_datetime(event["start"])
                        obs_end = _parse_gold_datetime(event["end"])
                    except (KeyError, TypeError):
                        continue
                    if obs_start is None or obs_end is None:
                        continue
                    cand = start_dt + (obs_end - obs_start)
                    if (cand.year, cand.month, cand.day, cand.hour,
                            cand.minute) == (gold_dt.year, gold_dt.month,
                                             gold_dt.day, gold_dt.hour,
                                             gold_dt.minute):
                        return Verdict("PROVEN", "duration",
                                       "proven start + original duration")

    # --- default: only a caller-declared default counts, never invention.
    if "default" in wanted and slot in evidence.defaults:
        if evidence.defaults[slot] == value:
            return Verdict("PROVEN", "default",
                           "value equals a declared default")

    if cross_app_candidate:
        return Verdict("UNPROVEN", "observation_cross_app",
                       "value seen only in a different app's result")
    if unknown_candidate:
        return Verdict("UNPROVEN", "observation_unknown_source",
                       "value seen only in untyped entries")
    if roster_no_intent:
        return Verdict("UNPROVEN", "roster_no_intent",
                       "contact in roster but no exclusive intent mention")
    return Verdict("UNPROVEN", "none", "no rule re-derived the value")


def _slot_value_in_text(slot, value, text, anchor):
    """True if a span in text parses/matches the value (for supersede)."""
    if not text:
        return False
    if _value_matches_text(value, text):
        return True
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        for _, v in find_number_spans(text):
            if float(v) == float(value):
                return True
    if slot in ("time", "date", "start", "end"):
        for _, parsed in find_datetime_spans(text, anchor):
            if _value_matches_datetime(value, parsed):
                return True
    return False


def prove_call(call, evidence, rules=None):
    """Prove every monitored argument of one gold/proposed call.

    Monitored slots: time, date, start, end, amount, contact_id, plus
    'to' when it holds a contact id. Returns {slot: Verdict}.
    """
    monitored = ("time", "date", "start", "end", "amount", "contact_id")
    name = call.get("name", "")
    args = call.get("arguments") or {}
    out = {}
    for slot in monitored:
        if slot in args:
            out[slot] = prove_argument(slot, args[slot], name, evidence,
                                       rules=rules, call_args=args)
    if "to" in args and isinstance(args["to"], str) \
            and "@" not in args["to"]:
        # 'to' holding a contact id (not an email) is monitored too.
        out["to"] = prove_argument("to", args["to"], name, evidence,
                                   rules=rules, call_args=args)
    return out
