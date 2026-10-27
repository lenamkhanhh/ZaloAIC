"""Typed grounding for LifeMate slots (rule-based, zero model params).

Design source: deep-dives/02 (typed parsing, clause-scoped negation
guard live there). This module is the pipeline implementation; the
deep-dive remains the research prototype. Behavioural contract:

- Money / date / id are NEVER fuzzy-guessed. Money keeps sign (minus
  and accounting parentheses) and units (triệu/nghìn/k); a single
  separator with exactly 3 digits is AMBIGUOUS (1.500 = 1500 or 1.5),
  never silently resolved. Dates must be calendar-valid. Ids strip
  only separators (space/-/.) and keep leading zeros and letters.
- Names / free text: NFC exact first, then fuzzy with a named backend
  (RapidFuzz when installed, difflib fallback — thresholds are NOT
  interchangeable, so the backend is reported on every fuzzy result).
- CORRECTION (2026-10-27 review): a candidate returned by a read is
  a read-verified entity, NOT proof that it is the entity the user
  meant. Existence does not prove intent. Concretely: a span that
  matches exactly one read candidate is GROUNDED only as "this span
  refers to a real entity"; when two candidates match the same span,
  or when history/context points at a different candidate than the
  span match, the result is AMBIGUOUS and the agent must use a
  distinguishing slot, history, or sys.ask_missing_info — never pick
  the first candidate and call it intent. Grounding supplies verified
  ids; intent is decided by the agent from transcript + history +
  context, and grounding never overrides it.
"""
from __future__ import annotations

import re
import copy
import math
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

try:
    from rapidfuzz.fuzz import ratio as _rf_ratio

    FUZZY_BACKEND = "rapidfuzz"
except ImportError:  # pragma: no cover - fallback path
    from difflib import SequenceMatcher as _SM

    def _rf_ratio(a: str, b: str) -> float:
        return _SM(None, a, b).ratio() * 100

    FUZZY_BACKEND = "difflib-fallback"

FUZZY_THRESHOLD = 88.0
FUZZY_MARGIN = 8.0


@dataclass
class GroundingResult:
    status: str  # EXACT | FUZZY_GROUNDED | AMBIGUOUS | UNKNOWN
    candidate: object = None
    evidence: str = ""
    backend: str = ""


def _nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text.strip())


_MONEY_UNITS = {"triệu": 1_000_000, "trieu": 1_000_000, "nghìn": 1_000,
                "nghin": 1_000, "k": 1_000, "đ": 1, "vnd": 1}


def parse_money(raw: str) -> Decimal | None:
    """Parse a Vietnamese money span to Decimal, or None if ambiguous/
    unparseable. Keeps sign; accounting parentheses mean negative."""
    text = _nfc(raw).lower().replace("đồng", "").strip()
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative, text = True, text[1:-1].strip()
    if text.startswith("-"):
        negative, text = True, text[1:].strip()
    scale = 1
    for unit, factor in _MONEY_UNITS.items():
        if text.endswith(unit):
            scale, text = factor, text[: -len(unit)].strip()
            break
    text = text.replace(" ", "")
    if not re.fullmatch(r"\d+(?:[.,]\d+)*", text):
        return None
    seps = [c for c in text if c in ".,"]
    if len(seps) == 1:
        sep = seps[0]
        head, tail = text.split(sep)
        if len(tail) == 3 and len(head) <= 3:
            return None  # ambiguous: 1.500 = 1500 or 1.5
        text = text.replace(sep, ".")
    elif len(seps) >= 2:
        if len(seps) == 2 and text.count(seps[0]) == 1 and text.count(seps[1]) == 1:
            # 1.000,50 or 1,000.50: last separator is decimal
            last = text.rfind(seps[-1])
            text = text[:last].replace(".", "").replace(",", "") + "." + text[last + 1:]
        else:
            # thousands groups only, e.g. 1.000.000
            if any(len(g) != 3 for g in re.split(r"[.,]", text)[1:]):
                return None
            text = text.replace(".", "").replace(",", "")
    try:
        value = Decimal(text) * scale
    except InvalidOperation:
        return None
    return -value if negative else value


def parse_date(raw: str, year_hint: int | None = None) -> str | None:
    """Parse a date span to ISO yyyy-mm-dd (or yyyy-mm for partial),
    or None. Calendar-invalid dates are never guessed."""
    import datetime

    text = _nfc(raw).strip().lower()
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", text)
    if m:
        try:
            datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            return text
        except ValueError:
            return None
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})(?:/(\d{4}))?", text)
    if m:
        day, month = int(m.group(1)), int(m.group(2))
        year = int(m.group(3)) if m.group(3) else year_hint
        if year is None:
            return None  # partial date without a year hint is not resolved
        try:
            datetime.date(year, month, day)
            return f"{year:04d}-{month:02d}-{day:02d}"
        except ValueError:
            return None
    m = re.fullmatch(r"ngày\s+(\d{1,2})\s+tháng\s+(\d{1,2})(?:\s+năm\s+(\d{4}))?", text)
    if m:
        day, month = int(m.group(1)), int(m.group(2))
        year = int(m.group(3)) if m.group(3) else year_hint
        if year is None:
            return None
        try:
            datetime.date(year, month, day)
            return f"{year:04d}-{month:02d}-{day:02d}"
        except ValueError:
            return None
    return None


def normalise_id(raw: str) -> str:
    """Strip separators only; keep leading zeros and letters."""
    return re.sub(r"[\s\-.]", "", _nfc(raw)).upper()


def ground_name(span: str, candidates: list) -> GroundingResult:
    """Ground a name span against read candidates (objects with a
    display string: pass strings, or (key, display) pairs)."""
    span_n = _nfc(span)
    displays = []
    for c in candidates:
        if isinstance(c, (list, tuple)):
            displays.append((c[0], _nfc(str(c[1]))))
        else:
            displays.append((c, _nfc(str(c))))
    exact = [key for key, disp in displays if disp == span_n]
    if len(exact) == 1:
        return GroundingResult("EXACT", exact[0], "exact NFC match")
    if len(exact) > 1:
        # Same display, different entities: existence does not resolve
        # intent. See module docstring correction.
        return GroundingResult("AMBIGUOUS", None,
                               "multiple entities share this display name")
    scored = sorted(
        ((key, _rf_ratio(span_n, disp)) for key, disp in displays),
        key=lambda kv: kv[1], reverse=True,
    )
    if not scored:
        return GroundingResult("UNKNOWN", None, "no candidates")
    (best, best_score), second = scored[0], (scored[1] if len(scored) > 1 else (None, 0.0))
    if best_score >= FUZZY_THRESHOLD and best_score - second[1] >= FUZZY_MARGIN:
        return GroundingResult("FUZZY_GROUNDED", best,
                               f"score {best_score:.1f} via {FUZZY_BACKEND}",
                               backend=FUZZY_BACKEND)
    if best_score >= FUZZY_THRESHOLD:
        return GroundingResult("AMBIGUOUS", None,
                               f"fuzzy margin too small ({best_score:.1f} vs {second[1]:.1f})",
                               backend=FUZZY_BACKEND)
    return GroundingResult("UNKNOWN", None,
                           f"best score {best_score:.1f} below threshold",
                           backend=FUZZY_BACKEND)


def ground_arguments(call: dict, tools: dict, executed: list[dict], results: list[dict],
                     *, history=(), transcript="", context=None):
    """Normalize only supplied slots; never invent a missing argument.

    Names for x-ref slots resolve against successful observed entities in the
    referenced collection (including history and newly created entities).
    Unknown IDs/phones are rejected before call, with no hidden state lookup.
    Keep the exact id from the observation;
    never apply punctuation/case normalization to a tool-internal identifier.
    Ambiguity goes back to the model as a validation error, not an auto-ask.
    """
    call = copy.deepcopy(call)
    args = call.get("arguments")
    if not isinstance(args, dict):
        return call, ["arguments must be an object"]
    properties = tools.get(call.get("name"), {}).get("parameters", {}).get("properties", {})
    errors = []

    from .evidence import EvidenceLedger
    evidence = EvidenceLedger(tools, executed, results, history, transcript, context)

    for name, value in list(args.items()):
        schema = properties.get(name, {})
        kind = schema.get("type")
        if kind in ("integer", "number") and isinstance(value, str):
            if re.search(r"amount|price|cost|fee|balance|total", name, re.I):
                number = parse_money(value)
            else:
                try:
                    number = Decimal(value) if re.fullmatch(r"[+-]?\d+(?:\.\d+)?", value) else None
                except InvalidOperation:
                    number = None
            if number is None or not number.is_finite():
                errors.append(f"{name}: ambiguous or invalid numeric value; use the schema's numeric type")
            elif kind == "integer" and number != number.to_integral_value():
                errors.append(f"{name}: integer required, not a fractional value")
            else:
                numeric = int(number) if number == number.to_integral_value() else float(number)
                if isinstance(numeric, float) and not math.isfinite(numeric):
                    errors.append(f"{name}: numeric value is out of range")
                else:
                    args[name] = numeric
        elif isinstance(value, str) and schema.get("format") == "date":
            date = parse_date(value)
            if date is None:
                errors.append(f"{name}: unresolved date; supply an explicit calendar-valid date")
            else:
                args[name] = date
        elif isinstance(value, str) and schema.get("x-ref"):
            ref = schema["x-ref"]
            candidates = evidence.entities.get(ref, {})
            if value in candidates or evidence.user_supplied(value, name):
                continue
            named = [(key, display) for key, display in candidates.items() if display is not None]
            grounded = ground_name(value, named)
            if grounded.status in ("EXACT", "FUZZY_GROUNDED"):
                args[name] = grounded.candidate
            else:
                app = str(ref).split(".")[0]
                reads = [key for key, spec in tools.items() if key.startswith(app + ".") and spec.get("kind") == "read"]
                errors.append(f"{name}: no supported ID for {ref}; use observed evidence or read via {reads}; "
                              "ask only if the user must supply missing/disambiguating information")
        elif name in ("phone", "phone_number") and isinstance(value, str):
            if not evidence.supports_phone(value):
                errors.append(f"{name}: no supporting phone in user input/context or successful tool results; "
                              "resolve the person through contacts.search or ask for the missing phone")
    return call, errors
