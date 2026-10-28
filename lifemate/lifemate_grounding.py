"""Deterministic grounding and normalization for LifeMate (round 5).

Pure CPU, no model, no network, no wall-clock reads. Three components plus one
pipeline guard:

1. ``NumberMoneyParser`` -- group-based Vietnamese number-word parsing
   (validated 13/13 on synthetic cases in round 4) and VND/digit parsing.
2. ``RelativeDateResolver`` -- relative date/time expressions resolved ONLY
   against a caller-supplied ``context_time``. This module NEVER calls
   ``datetime.now()``, ``date.today()`` or ``time.time()``: the anchor must
   come from the sample's context, or resolution raises.
3. ``ContactFilter`` -- candidate ranking with text similarity (RapidFuzz when
   installed, difflib fallback) plus a SEPARATE tone-digit channel. Tone is
   never folded into the text score: same segmental string with a different
   tone (Binh/Binh with different tones) must NOT auto-ground.
4. ``validate_submission`` -- pipeline guard: flags read-after-write (which
   dilutes tool-call F1) before a submission is proposed.

All examples in docstrings are synthetic. No probe IDs, amounts, or answers
from any dataset are hardcoded here.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal

try:  # RapidFuzz is preferred; difflib is the offline fallback.
    from rapidfuzz import fuzz as _rf_fuzz

    BACKEND = "rapidfuzz"
except Exception:  # pragma: no cover - exercised by the fallback test run
    import difflib as _difflib

    BACKEND = "difflib"

__all__ = [
    "BACKEND",
    "ContactCandidate",
    "ContactDecision",
    "ContactFilter",
    "DateResolution",
    "MoneyResult",
    "NumberMoneyParser",
    "RelativeDateResolver",
    "tone_digit",
    "tone_sequence",
    "validate_submission",
]


# --------------------------------------------------------------------------
# Shared text helpers
# --------------------------------------------------------------------------

def _nfc_lower(text: str) -> str:
    return unicodedata.normalize("NFC", text or "").lower().strip()


def _tokens(text: str) -> list[str]:
    return re.findall(r"[^\W_]+", _nfc_lower(text), flags=re.UNICODE)


_TONE_MAP = {
    "\u0301": 2,  # acute  -> sac
    "\u0300": 3,  # grave  -> huyen
    "\u0309": 4,  # hook   -> hoi
    "\u0303": 5,  # tilde  -> nga
    "\u0323": 6,  # dot    -> nang
}


def tone_digit(word: str) -> int:
    """Tone digit (1-6) of one Vietnamese word from its diacritic.

    1 = ngang (no mark), 2 = sac, 3 = huyen, 4 = hoi, 5 = nga, 6 = nang.
    The first tone mark found in NFD order wins; a word without a tone mark
    is ngang. Note: 'd' vs 'dd' is an onset difference, not a tone.
    """
    for ch in unicodedata.normalize("NFD", word or ""):
        if ch in _TONE_MAP:
            return _TONE_MAP[ch]
    return 1


def tone_sequence(name: str) -> tuple[int, ...]:
    """Per-word tone digits, e.g. ('Binh' with tone 3) -> (3,)."""
    return tuple(tone_digit(w) for w in _tokens(name))


def _text_score(a: str, b: str) -> float:
    """0-100 text similarity. RapidFuzz ratio, or difflib ratio * 100."""
    if BACKEND == "rapidfuzz":
        return float(_rf_fuzz.ratio(a, b))
    return float(_difflib.SequenceMatcher(None, a, b).ratio() * 100)


# --------------------------------------------------------------------------
# 1. Numbers and money (group-based)
# --------------------------------------------------------------------------

_DIGIT_WORDS = {
    "không": 0, "một": 1, "hai": 2, "ba": 3, "bốn": 4, "năm": 5,
    "sáu": 6, "bảy": 7, "tám": 8, "chín": 9,
}
# Positional variants used after "muoi" or "muoi" (and after "muoi" in
# "muoi lam" style): mot=1, tu=4, lam=5.
_VARIANT_WORDS = {"mốt": 1, "tư": 4, "lăm": 5}
_BIG_UNITS = {"nghìn": 1000, "ngàn": 1000, "triệu": 1_000_000,
              "tỷ": 1_000_000_000, "tỉ": 1_000_000_000}
_NUMBER_TOKENS = set(_DIGIT_WORDS) | set(_VARIANT_WORDS) | {
    "mười", "mươi", "trăm", "linh", "lẻ", "rưỡi", "nửa",
} | set(_BIG_UNITS)


def _unit_value(tok: str, variant: bool = False) -> int | None:
    if variant and tok in _VARIANT_WORDS:
        return _VARIANT_WORDS[tok]
    if tok in _DIGIT_WORDS:
        return _DIGIT_WORDS[tok]
    return None


def _parse_small(toks: list[str]) -> Decimal | None:
    """Parse a <10000 group without big units (trăm/mươi/mười/linh/lẻ).

    Returns None for unstructured token sequences (caller treats that as
    "not a number expression", never as zero).
    """
    if not toks:
        return Decimal(0)
    if toks[0] in ("linh", "lẻ"):
        return _parse_small(toks[1:])
    if toks == ["rưỡi"] or toks == ["nửa"] or toks == ["một", "nửa"]:
        return Decimal("0.5")
    if toks[-1] == "rưỡi" and len(toks) > 1:
        base = _parse_small(toks[:-1])
        if base is None:
            return None
        scale = 100 if "trăm" in toks[:-1] else (10 if "mươi" in toks[:-1] else 1)
        return base + Decimal("0.5") * scale
    if "trăm" in toks:
        i = toks.index("trăm")
        left, right = toks[:i], toks[i + 1:]
        h = _parse_small(left) if left else Decimal(1)
        r = _parse_small(right) if right else Decimal(0)
        if h is None or r is None:
            return None
        return h * 100 + r
    if "mươi" in toks:
        i = toks.index("mươi")
        left, right = toks[:i], toks[i + 1:]
        t = _parse_small(left) if left else Decimal(1)
        if len(right) == 1:
            u = _unit_value(right[0], variant=True)
            if u is None:
                return None
            r = Decimal(u)
        elif not right:
            r = Decimal(0)
        else:
            return None
        return t * 10 + r
    if toks[0] == "mười":
        if len(toks) == 1:
            return Decimal(10)
        if len(toks) == 2:
            u = _unit_value(toks[1], variant=True)
            return Decimal(10 + u) if u is not None else None
        return None
    if len(toks) == 1:
        u = _unit_value(toks[0], variant=True)
        return Decimal(u) if u is not None else None
    return None


@dataclass
class MoneyResult:
    value: Decimal | None
    unit: str = ""          # e.g. "VND" when a currency suffix was present
    ambiguous: bool = False
    reason: str = ""


class NumberMoneyParser:
    """Group-based Vietnamese number/money parsing (stdlib + Decimal).

    ``parse_number_words`` handles word-only spans ("mot tram nam muoi
    nghin" -> 150000). ``parse_money`` additionally handles digit amounts
    ("50 nghin", "1.234.567,89", "1,5 trieu") with the round-4 separator
    rules. Both return None / ambiguous instead of guessing on unstructured
    input.
    """

    def extract_number_span(self, text: str) -> list[str] | None:
        """Longest contiguous span of number-related tokens, or None.

        Guards (same exclusions as the E-asr-1 audit): a number token right
        after "thang" is a month name ("thang mot" = January); right after
        "thu" it is a weekday ("thu hai" = Monday); "nam" before
        "nay"/"sau"/"truoc" is the word "year", not five.
        """
        toks = _tokens(text)
        best: list[str] = []
        cur: list[str] = []
        for i, tok in enumerate(toks):
            prev = toks[i - 1] if i > 0 else ""
            nxt = toks[i + 1] if i + 1 < len(toks) else ""
            if tok == "năm" and nxt in ("nay", "sau", "trước"):
                tok = ""  # year reading, not the number five
            if prev in ("tháng", "thứ"):
                tok = ""
            if tok and tok in _NUMBER_TOKENS:
                cur.append(tok)
            else:
                if len(cur) > len(best):
                    best = cur
                cur = []
        if len(cur) > len(best):
            best = cur
        # A span of only "mot" as an article ("mot tin") is not a number;
        # require either a structural token or more than one token.
        if best and (len(best) > 1 or best[0] not in ("một",)):
            return best
        return None

    def parse_number_words(self, text: str) -> Decimal | None:
        span = self.extract_number_span(text)
        if span is None:
            return None
        return self._parse_grouped(span)

    def _parse_grouped(self, toks: list[str]) -> Decimal | None:
        """Split at big units, parse each group, scale and sum."""
        total = Decimal(0)
        cur: list[str] = []
        last_big_scale: int | None = None
        for tok in toks:
            if tok in _BIG_UNITS:
                scale = _BIG_UNITS[tok]
                g = _parse_small(cur) if cur else Decimal(1)
                if g is None:
                    return None
                total += g * scale
                last_big_scale = scale
                cur = []
            else:
                cur.append(tok)
        if cur:
            if cur == ["rưỡi"] and last_big_scale is not None:
                total += Decimal("0.5") * last_big_scale
            elif cur == ["nửa"] and last_big_scale is not None:
                total += Decimal("0.5") * last_big_scale
            else:
                g = _parse_small(cur)
                if g is None:
                    return None
                total += g
        return total

    def parse_money(self, text: str) -> MoneyResult:
        """Parse a money/amount string. Order matters (round-4 rules).

        1. Currency and multiplier suffixes, stripped order-safely
           ("50kđ" and "1,5 trieu dong" both work; the multiplier strip
           always happens before separator resolution, so "1,5 trieu" keeps
           its decimal comma).
        2. Space/NBSP/underscore group separators.
        4. Separator resolution: both '.' and ',' -> last-occurring is the
           decimal separator; multiple of one kind -> all thousands; one
           separator + exactly 3 digits after -> thousands, else decimal.
        5. Word-number fallback for word-only amounts.
        """
        s = _nfc_lower(text)
        if not s:
            return MoneyResult(None, reason="empty")
        # Accounting parentheses: (1.234) = -1234, only if inner parses.
        neg = False
        if s.startswith("(") and s.endswith(")"):
            inner = self.parse_money(s[1:-1])
            if inner.value is None:
                return MoneyResult(None, ambiguous=True,
                                   reason="paren_non_numeric")
            return MoneyResult(-inner.value, inner.unit)
        if s.endswith("-") and not s.startswith("-"):
            inner = self.parse_money(s[:-1])
            if inner.value is None:
                return MoneyResult(None, ambiguous=True,
                                   reason="trailing_minus_non_numeric")
            return MoneyResult(-inner.value, inner.unit)
        s = s.replace("\u2212", "-").replace("\u2013", "-").replace("\u2014", "-")

        # Suffix stripping, order-safe: currency, multiplier, currency again
        # (so "50kđ" -> "50k" -> "50", and "1,5 trieu dong" -> "1,5 trieu"
        # -> "1,5"). Multiplier first for the decimal-comma case is preserved
        # because the multiplier strip happens before separator resolution.
        unit = ""

        def _strip_currency(x: str):
            y = re.sub(r"\s*(đ|vnd|vnđ|đồng|₫)\s*$", "", x, flags=re.IGNORECASE)
            return y, ("VND" if y != x else "")

        s, u = _strip_currency(s)
        unit = unit or u
        mult = 1
        for suffix, m in (("tỷ", 10 ** 9), ("triệu", 10 ** 6),
                          ("nghìn", 10 ** 3), ("ngàn", 10 ** 3)):
            if s.endswith(suffix):
                mult = m
                s = s[: -len(suffix)].strip()
                break
        else:
            if re.fullmatch(r"\d+k", s):
                mult = 10 ** 3
                s = s[:-1]
        s, u = _strip_currency(s)
        unit = unit or u
        # Word-number fallback BEFORE spaces are stripped: "mot tram nam
        # muoi nghin" must still parse after the "nghin" suffix is removed.
        # (Stripping spaces first would fuse it into one unrecognizable token.)
        if re.search(r"[^\d.,\s\-]", s):
            val = self.parse_number_words(s)
            if val is not None:
                return MoneyResult(val * mult, unit)
        s = re.sub(r"[\s\u00a0_]", "", s)
        if re.fullmatch(r"-?\d+", s):
            return MoneyResult(Decimal(s) * mult, unit)
        if re.fullmatch(r"-?[\d.,]+", s or ""):
            val = self._parse_separated(s)
            if val is not None:
                return MoneyResult(val * mult, unit)
            return MoneyResult(None, ambiguous=True, reason="bad_separators")
        # Word-number fallback (e.g. "mot tram nam muoi nghin") already ran
        # before space stripping above; anything reaching here is digit-only
        # or unparseable.
        return MoneyResult(None, ambiguous=True, reason="unparseable")

    @staticmethod
    def _parse_separated(s: str) -> Decimal | None:
        neg = s.startswith("-")
        if neg:
            s = s[1:]
        if "." in s and "," in s:
            dec = "." if s.rfind(".") > s.rfind(",") else ","
        elif s.count(".") > 1 or s.count(",") > 1:
            dec = None
        elif "." in s or "," in s:
            sep = "." if "." in s else ","
            after = s.split(sep)[1]
            dec = None if len(after) == 3 else sep
        else:
            dec = None
        try:
            if dec is None:
                out = Decimal(s.replace(".", "").replace(",", ""))
            else:
                ip, fp = s.rsplit(dec, 1)
                out = Decimal(ip.replace(".", "").replace(",", "") + "." + fp)
        except Exception:
            return None
        return -out if neg else out


# --------------------------------------------------------------------------
# 2. Relative dates anchored to context_time (never wall-clock)
# --------------------------------------------------------------------------

@dataclass
class DateResolution:
    date: date | None
    kind: str = ""            # absolute | day_offset | weekday | daypart |
                              # week_only | month_only | none
    hour_missing: bool = False
    daypart: str = ""         # sang | chieu | toi (only for kind == daypart)
    raw: str = ""


_WEEKDAYS = {
    "thứ hai": 0, "thứ ba": 1, "thứ tư": 2, "thứ năm": 3,
    "thứ sáu": 4, "thứ bảy": 5, "chủ nhật": 6,
}
_DAYPARTS = {"sáng": "sang", "chiều": "chieu", "tối": "toi"}


class RelativeDateResolver:
    """Resolve Vietnamese relative dates against a caller-supplied anchor.

    ``context_time`` is REQUIRED (datetime or ISO string). If it is None,
    resolution raises ValueError -- the resolver must never fall back to
    the machine clock, because the private-test run date differs from the
    sample's recorded date and repeated runs must be reproducible.
    """

    def __init__(self, context_time: datetime | str | None):
        if context_time is None:
            raise ValueError("context_time is required; wall-clock fallback "
                             "is forbidden")
        if isinstance(context_time, str):
            context_time = datetime.fromisoformat(context_time)
        if not isinstance(context_time, datetime):
            raise TypeError("context_time must be datetime or ISO string")
        self.anchor: datetime = context_time
        self.anchor_date: date = context_time.date()

    # -- helpers -----------------------------------------------------------
    def _next_weekday(self, target: int, *, strict_after: bool = True) -> date:
        """Next occurrence of weekday `target` (Mon=0) after the anchor date.

        With strict_after=True, an anchor already on `target` resolves to
        +7 days ("thu hai toi" said on a Monday means NEXT Monday).
        """
        delta = (target - self.anchor_date.weekday()) % 7
        if strict_after and delta == 0:
            delta = 7
        return self.anchor_date + timedelta(days=delta)

    # -- main entry --------------------------------------------------------
    def resolve(self, text: str) -> DateResolution:
        """Resolve the FIRST time expression found in `text`."""
        raw = text or ""
        s = _nfc_lower(raw)
        toks = _tokens(raw)

        # Absolute ISO first (unambiguous).
        m = re.search(r"\d{4}-\d{2}-\d{2}", s)
        if m:
            try:
                return DateResolution(date.fromisoformat(m.group(0)),
                                      kind="absolute", raw=m.group(0))
            except ValueError:
                pass
        # Absolute dd/mm/yyyy and dd/mm (year = anchor year).
        m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
        if m:
            d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            try:
                return DateResolution(date(y, mo, d), kind="absolute",
                                      raw=m.group(0))
            except ValueError:
                pass
        m = re.search(r"(\d{1,2})/(\d{1,2})(?!\d)", s)
        if m:
            d, mo = int(m.group(1)), int(m.group(2))
            try:
                return DateResolution(date(self.anchor_date.year, mo, d),
                                      kind="absolute", raw=m.group(0))
            except ValueError:
                pass
        # "ngay 15 thang 11" (year = anchor year).
        m = re.search(r"ngày\s+(\d{1,2})\s+tháng\s+(\d{1,2})", s)
        if m:
            d, mo = int(m.group(1)), int(m.group(2))
            try:
                return DateResolution(date(self.anchor_date.year, mo, d),
                                      kind="absolute", raw=m.group(0))
            except ValueError:
                pass
        # Digit offsets: "2 ngay nua", "3 ngay truoc".
        m = re.search(r"(\d+)\s+ngày\s+(nữa|trước)", s)
        if m:
            n = int(m.group(1))
            delta = n if m.group(2) == "nữa" else -n
            return DateResolution(self.anchor_date + timedelta(days=delta),
                                  kind="day_offset", raw=m.group(0))
        # Weekday phrases (longest first): "thu hai tuan sau" beats "thu hai".
        # "X tuan sau" = the weekday of NEXT week: Monday of the anchor's
        # week + 7 days + weekday offset (NOT next-occurrence + 7, which
        # overshoots by a week for weekdays after the anchor's weekday).
        for name, wd in _WEEKDAYS.items():
            if f"{name} tuần sau" in s:
                monday = self.anchor_date - timedelta(
                    days=self.anchor_date.weekday())
                return DateResolution(monday + timedelta(days=7 + wd),
                                      kind="weekday",
                                      raw=f"{name} tuần sau")
            if f"{name} tới" in s or name in s:
                return DateResolution(self._next_weekday(wd), kind="weekday",
                                      raw=name)
        # Vague dayparts: DATE only, hour is still missing -> ask for hour.
        for vn, code in _DAYPARTS.items():
            for suffix in ("mai", "nay"):
                if f"{vn} {suffix}" in s:
                    base = self.anchor_date + (timedelta(days=1)
                                               if suffix == "mai"
                                               else timedelta(0))
                    return DateResolution(base, kind="daypart",
                                          hour_missing=True, daypart=code,
                                          raw=f"{vn} {suffix}")
        # Day offsets.
        day_map = {
            "hôm nay": 0, "hôm qua": -1, "hôm kia": -2,
            "ngày mai": 1, "ngày kia": 2, "ngày mốt": 3,
            "mai": 1, "mốt": 3,
        }
        for phrase in sorted(day_map, key=len, reverse=True):
            if re.search(rf"(?<![\wÀ-ỹ]){re.escape(phrase)}(?![\wÀ-ỹ])", s):
                return DateResolution(
                    self.anchor_date + timedelta(days=day_map[phrase]),
                    kind="day_offset", raw=phrase)
        # Week/month references without a day are NOT dates: never invent one.
        if re.search(r"tuần (này|sau|trước)|cuối tuần|đầu tuần", s):
            return DateResolution(None, kind="week_only", raw="week_ref")
        if re.search(r"tháng (này|sau|trước)|cuối tháng|đầu tháng", s):
            return DateResolution(None, kind="month_only", raw="month_ref")
        return DateResolution(None, kind="none", raw="")


# --------------------------------------------------------------------------
# 3. Contact filtering: text similarity + separate tone channel
# --------------------------------------------------------------------------

@dataclass
class ContactCandidate:
    id: str
    name: str


@dataclass
class ContactDecision:
    status: str               # EXACT | FUZZY_GROUNDED | AMBIGUOUS | UNKNOWN
    candidate: ContactCandidate | None = None
    method: str = ""          # exact | fuzzy | abbreviation | none
    reason: str = ""
    backend: str = BACKEND
    scored: list = field(default_factory=list)  # top candidates with scores


FUZZY_THRESHOLD = 88.0
FUZZY_MARGIN = 8.0


class ContactFilter:
    """Rank contact candidates for a spoken query.

    Rules (mirror the branch grounding thresholds, plus the round-4 tone rule):
    - Duplicate normalized names with different ids -> AMBIGUOUS, always
      (text cannot distinguish them; only a distinguishing slot or history
      recency or ask can).
    - Exact normalized equality -> EXACT.
    - Best text score >= 88 with margin >= 8 AND tone sequences equal ->
      FUZZY_GROUNDED.
    - Best text score >= 88 but tone sequences differ -> AMBIGUOUS
      (tone conflict: same segmental string, different person is possible;
      needs acoustic rescoring or ask, never silent grounding).
    - Best text score >= 88 but margin < 8 -> AMBIGUOUS.
    - Best text score < 88 -> UNKNOWN, unless the abbreviation rule fires.
    - Abbreviation rule (only when nothing above fired): query equals the
      initials of a candidate's words, or query is exactly one word of a
      candidate's name, AND exactly one candidate matches that way ->
      FUZZY_GROUNDED (method=abbreviation). Two or more -> AMBIGUOUS.
    """

    def filter_contacts(self, query: str,
                        candidates: list[ContactCandidate]) -> ContactDecision:
        q = _nfc_lower(query)
        if not q or not candidates:
            return ContactDecision("UNKNOWN", reason="empty_query_or_roster")
        q_tones = tone_sequence(q)

        # Duplicate normalized names with different ids: text cannot decide.
        by_name: dict[str, set[str]] = {}
        for cand in candidates:
            by_name.setdefault(_nfc_lower(cand.name), set()).add(cand.id)
        if q in by_name and len(by_name[q]) > 1:
            return ContactDecision("AMBIGUOUS", reason="duplicate_name")

        scored = []
        for cand in candidates:
            cname = _nfc_lower(cand.name)
            scored.append({
                "candidate": cand,
                "text_score": _text_score(q, cname),
                "tone_match": tone_sequence(cname) == q_tones,
                "exact": cname == q,
            })
        scored.sort(key=lambda d: d["text_score"], reverse=True)
        top = scored[0]

        if top["exact"]:
            return ContactDecision("EXACT", top["candidate"], method="exact",
                                   scored=scored[:3])
        best = top["text_score"]
        second = scored[1]["text_score"] if len(scored) > 1 else 0.0
        margin = best - second
        if best >= FUZZY_THRESHOLD:
            if not top["tone_match"]:
                return ContactDecision(
                    "AMBIGUOUS", reason="tone_conflict",
                    scored=scored[:3])
            if margin < FUZZY_MARGIN:
                return ContactDecision("AMBIGUOUS", reason="small_margin",
                                       scored=scored[:3])
            return ContactDecision("FUZZY_GROUNDED", top["candidate"],
                                   method="fuzzy", scored=scored[:3])

        # Abbreviation rule (only when fuzzy did not fire).
        abbr_hits = []
        for cand in candidates:
            words = _tokens(cand.name)
            initials = "".join(w[0] for w in words if w)
            if q.replace(" ", "") == initials:
                abbr_hits.append(cand)
            elif len(_tokens(q)) == 1 and _tokens(q)[0] in words:
                abbr_hits.append(cand)
        if len(abbr_hits) == 1:
            return ContactDecision("FUZZY_GROUNDED", abbr_hits[0],
                                   method="abbreviation", scored=scored[:3])
        if len(abbr_hits) > 1:
            return ContactDecision("AMBIGUOUS", reason="ambiguous_abbreviation",
                                   scored=scored[:3])
        return ContactDecision("UNKNOWN", reason="no_candidate",
                               scored=scored[:3])


# --------------------------------------------------------------------------
# 4. Pipeline guard: no read-after-write
# --------------------------------------------------------------------------

def validate_submission(calls: list[dict], read_tool_names: set[str]) -> list[str]:
    """Flag submission-rule violations BEFORE a submission is proposed.

    ``calls`` are {"name": ..., "arguments": {...}} dicts in submission order.
    ``read_tool_names`` must be supplied by the pipeline from its catalog
    (tools with no state effect); this module never guesses which tools are
    reads. Violations:
    - "read_after_write": a read tool submitted after the first write tool
      (dilutes tool-call F1: a verify read after a perfect write costs
      0.333 F1 on a 1-gold-call sample, and buys nothing for the hash
      because the write result already echoes the created item).
    - "empty_submission": no calls at all (caller must decide ask vs stop).
    An empty violation list means the submission is clean under these rules.
    """
    violations: list[str] = []
    if not calls:
        return ["empty_submission"]
    seen_write = False
    for i, call in enumerate(calls):
        name = call.get("name", "")
        if name in read_tool_names:
            if seen_write:
                violations.append(f"read_after_write at index {i}: {name}")
        elif name != "sys.ask_missing_info":
            seen_write = True
    return violations
