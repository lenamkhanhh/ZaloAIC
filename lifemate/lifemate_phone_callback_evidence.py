"""Phone evidence + history/callback contract for the G&G round.

Standalone, pure Python (stdlib only). Deliberately does NOT import
lifemate_gates or lifemate_provenance: the coordinator wires this
module's verdicts into the gates. Nothing here changes a proposal,
submitted calls, state, retries, or termination.

Two questions are kept SEPARATE in every verdict (see the round
brief):

  (a) Which valid source does this number / counterpart come from?
  (b) Does the current request select this number / counterpart as
      the action target?

Proving (a) alone never counts as proving (b). A verdict is PROVEN
only when (a) has a valid source AND (b) is True. Sources present
with (b) undetermined give AMBIGUOUS; no valid source gives UNKNOWN.

Valid sources (verified against zaic_tools implementations, see
gg_phone_callback_notes.md):
  - roster: a contact's phone in the address book (unique match only;
    contact_ref completes a phone to a contact only on a unique
    match, and a phone matching two contacts completes nothing).
  - call_log / message_log: a phone_number field in a SUCCEEDED
    phone.recent_calls / sms.read_recent result. These are reads of
    the interaction log; the number itself is observed data.
  - user_text: a number the user states in the current request as
    the action target, in digits or in spoken Vietnamese digits.
  - history_text: a number bound from a history turn through an
    explicit anaphoric / callback / prior-instruction reference.
  - read_result: a number observed in the text content of a
    SUCCEEDED read result (e.g. a chat message), selected by an
    anaphoric reference in the current request.

Explicitly NOT sources:
  - the proposal's own arguments (a proposal never evidences itself);
  - phone.call / sms.send result fields: those are echoes of the
    call's own argument (phone/sms never validate contacts, so a
    first use would launder a hallucinated number);
  - negated, corrected-away, or background-only mentions;
  - a number merely present somewhere in history with no binding
    reference in the current request;
  - a contact_id found in free text or as a foreign key of another
    registry's record (it proves nothing about contacts membership).

Only outcome "succeeded" counts as evidence. A schema-rejected,
failed, or noop call establishes nothing.

Phone normalisation follows exactly the _norm_phone rule shared by
the gates and zaic_tools base.contact_ref: digits only, with an
11-digit "84..." prefix folded to "0...". No digit is ever added,
dropped, or changed to force a match (except the documented tail
correction, which is itself user-stated and recorded as a binding,
not as an existence claim).
"""

from __future__ import annotations

import ast
import json
import re
import unicodedata

# Delegation scope (round-7 fix S3): shared with the negation
# module so history binding judges delegated turns by exactly
# the current-text rule. No cycle: the negation module imports
# only the standard library.
from lifemate_callback_negation import (
    phone_numbers_for_action,
    turn_fully_delegated,
)

__all__ = [
    "norm_phone",
    "fold_vietnamese",
    "find_digit_runs",
    "classify_phone_context",
    "parse_phone_mentions",
    "parse_tail_correction",
    "apply_tail_correction",
    "parse_history_result",
    "extract_log_records",
    "bind_history_reference",
    "phone_evidence_for",
    "callback_reference_for",
    "CALL_LOG_TOOLS",
    "MESSAGE_LOG_TOOLS",
    "READ_RESULT_CONTENT_TOOLS",
    "CONSUMER_REQUIRES_MEMBERSHIP",
]

# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

_DIGIT_WORDS = {
    "khong": "0",
    "mot": "1",
    "hai": "2",
    "ba": "3",
    "bon": "4",
    "nam": "5",
    "sau": "6",
    "bay": "7",
    "tam": "8",
    "chin": "9",
}

# Vietnamese digit words in their diacritic form (for reference only;
# matching is done on the folded form, which is length-preserving).
_DIGIT_WORDS_DIACRITIC = {
    "không": "0", "một": "1", "hai": "2", "ba": "3", "bốn": "4",
    "năm": "5", "sáu": "6", "bảy": "7", "tám": "8", "chín": "9",
}

# Tools whose SUCCEEDED result phone_number fields are log evidence.
CALL_LOG_TOOLS = ("phone.recent_calls",)
MESSAGE_LOG_TOOLS = ("sms.read_recent",)
# Tools whose SUCCEEDED result text content may carry observed numbers.
READ_RESULT_CONTENT_TOOLS = (
    "chat_ott.read_chat",
    "sms.read_recent",
    "phone.recent_calls",
)

# Consumers whose implementation provably requires contacts membership
# for a contact_id argument (see notes). phone.call / sms.send /
# ewallet.transfer never validate a contact_id (contact_ref only
# completes on unique match, never rejects), so for them an observed
# counterpart suffices for execution -- but it still does NOT prove
# roster membership; the verdict says so explicitly.
CONSUMER_REQUIRES_MEMBERSHIP = {
    "contacts.update": True,   # patch: find-or-noop
    # NOTE: there is NO contacts.delete tool in the catalog
    # (reviewer correction): the old entry claiming it was dead.
    "contacts.get": False,     # read: returns empty when absent
    "contacts.search": False,  # read: returns empty when absent
    "phone.call": False,
    "sms.send": False,
    "ewallet.transfer": False,
    "chat_ott.send_message": False,  # validates chat_id, not contact_id
}

# A Vietnamese phone candidate: hotlines (1900xxxx, 8 digits) up to
# 11-digit +84 forms (folded to 10). Shorter digit runs are tails,
# amounts, times, or codes, never phone numbers on their own.
MIN_PHONE_DIGITS = 7
MAX_PHONE_DIGITS = 12


def fold_vietnamese(text):
    """Lowercase + strip diacritics, LENGTH-PRESERVING.

    NFD decomposition maps each precomposed Vietnamese character to
    exactly one base character plus combining marks, so stripping
    the marks keeps every character position identical to the
    original text. Spans computed on the folded text therefore apply
    to the original text as well. 'd' (đ) maps to 'd'.
    """
    if text is None:
        return ""
    decomposed = unicodedata.normalize("NFD", str(text).lower())
    folded = "".join(
        ch for ch in decomposed if unicodedata.category(ch) != "Mn"
    )
    return folded.replace("đ", "d")


def norm_phone(value):
    """Digits-only phone, +84/84 country prefix folded to 0.

    Identical rule to lifemate_gates._norm_phone and
    zaic_tools base.contact_ref. No other change is ever made.
    """
    d = "".join(ch for ch in str(value or "") if ch.isdigit())
    if d.startswith("84") and len(d) == 11:
        return "0" + d[2:]
    return d


# ---------------------------------------------------------------------------
# Digit runs: raw enumeration (phone and non-phone alike)
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_MONEY_UNITS = ("dong", "nghin", "trieu", "ty", "vnd", "d")
_TIME_UNITS = ("gio", "phut", "giay")
_DATE_UNITS = ("ngay", "thang", "nam")
_ACTION_VERBS = ("goi", "nhan", "lien", "luu", "goi lai")
_ORDER_CUES = ("ma don", "ma van don", "don hang", "ma hang")


def _tokens_with_spans(folded):
    """[(token, start, end)] for word tokens in folded text."""
    return [(m.group(0), m.start(), m.end())
            for m in _TOKEN_RE.finditer(folded)]


def find_digit_runs(text):
    """Enumerate every digit run in the text, phone or not.

    A run is either a contiguous digit string (possibly with a
    leading '+') or a maximal sequence of Vietnamese digit-word
    tokens, where commas / punctuation between digit words do NOT
    break the run but any other word does. Each run:

      {"raw": <substring of the ORIGINAL text>,
       "digits": <digit string, or "" if unresolvable>,
       "kind": "digits" | "spoken" | "mixed",
       "span": (start, end) in the original text,
       "token_span": (first_token_idx, last_token_idx),
       "ambiguous_khong": bool}

    "không" inside a run counts as digit 0, EXCEPT when it is the
    negation in "không phải" (handled by the caller: the run is
    split there; see _split_negation). A run that starts with
    "không" and has no phone cue nearby is flagged ambiguous_khong
    rather than silently read as a leading zero -- the caller
    decides, never the parser alone.
    """
    if not text:
        return []
    folded = fold_vietnamese(text)
    tokens = _tokens_with_spans(folded)
    runs = []
    i = 0
    n = len(tokens)
    while i < n:
        tok, start, end = tokens[i]
        if tok.isdigit():
            # Contiguous digit string; absorb a following digit
            # token only when joined by whitespace inside a phone
            # group (e.g. "0987 654 321" is NOT produced by this
            # dataset, so digit strings stay single tokens).
            runs.append({
                "raw": text[start:end],
                "digits": tok,
                "kind": "digits",
                "span": (start, end),
                "token_span": (i, i),
                "ambiguous_khong": False,
            })
            i += 1
            continue
        if tok in _DIGIT_WORDS:
            # Spoken run: consecutive digit words, punctuation
            # between them does not break the run.
            digits = []
            j = i
            last_end = end
            ambiguous = False
            while j < n:
                t, s, e = tokens[j]
                if t in _DIGIT_WORDS:
                    # "không phải" is negation, not digit 0: stop
                    # the run before "không".
                    if t == "khong" and j + 1 < n \
                            and tokens[j + 1][0] == "phai":
                        break
                    digits.append(_DIGIT_WORDS[t])
                    last_end = e
                    j += 1
                    continue
                break
            if digits:
                # Ambiguity flag: run starts with "không" and no
                # phone cue ("số", call verb) in the preceding
                # 4 tokens -- a bare "không" may be negation.
                window = [t for t, _, _ in tokens[max(0, i - 4):i]]
                if tokens[i][0] == "khong" and not any(
                        w in ("so", "goi", "nhan", "tong", "dai")
                        for w in window):
                    ambiguous = True
                runs.append({
                    "raw": text[start:last_end],
                    "digits": "".join(digits),
                    "kind": "spoken",
                    "span": (start, last_end),
                    "token_span": (i, j - 1),
                    "ambiguous_khong": ambiguous,
                })
                i = j
                continue
            # Empty run: the run started at a "không phải"
            # negation -- skip the "không" so we cannot loop.
            i = j + 1
            continue
        i += 1
    return runs


def classify_phone_context(text, run):
    """Classify one digit run against its surrounding context.

    Returns {"classification": ..., "reason": ...} where
    classification is one of:
      "phone"      -- plausibly a phone number
      "money"      -- an amount (currency unit / money verb nearby)
      "time"       -- a clock time (colon form or giờ/phút)
      "date"       -- a calendar date (slash/dash form or ngày/tháng)
      "order_code" -- an order / tracking code (mã đơn, đơn hàng)
      "other_number" -- a digit string that is not a phone number
        (too short, too long, or a code-like value)
      "ambiguous"  -- cannot be told apart from context

    Classification uses context cues, never digit length alone:
    length only excludes runs that cannot be phone numbers at all
    (shorter than MIN_PHONE_DIGITS or longer than MAX_PHONE_DIGITS).
    A run that is both money-adjacent and phone-adjacent is
    AMBIGUOUS, never guessed.
    """
    if not text or not run:
        return {"classification": "ambiguous",
                "reason": "empty_text_or_run"}
    folded = fold_vietnamese(text)
    tokens = _tokens_with_spans(folded)
    first, last = run["token_span"]
    window_before = [t for t, _, _ in tokens[max(0, first - 6):first]]
    window_after = [t for t, _, _ in tokens[last + 1:last + 7]]
    window = window_before + window_after
    digits = run.get("digits") or ""
    # Separator between this run and the next token ("/", ":", "-"
    # belong to dates/times, not to the number itself).
    gap = ""
    if last + 1 < len(tokens):
        gap = folded[run["span"][1]:tokens[last + 1][1]]
    after1 = window_after[0] if window_after else ""
    before1 = window_before[-1] if window_before else ""
    if ":" in gap:
        return {"classification": "time", "reason": "colon_time_form"}
    if "/" in gap or "-" in gap:
        return {"classification": "date", "reason": "slash_or_dash_date_form"}
    # Cues must be ADJACENT (first token after / before the run):
    # a money unit three tokens later usually belongs to a
    # different number in the same sentence.
    time_cue = after1 in _TIME_UNITS
    date_cue = after1 in _DATE_UNITS or before1 in ("ngay", "thang")
    order_cue = any(cue in " ".join(window_before[-4:])
                    for cue in _ORDER_CUES)
    phone_cue = any(w in ("so", "goi", "nhan", "tong", "dai", "truc")
                    for w in window)
    if order_cue and not phone_cue:
        return {"classification": "order_code", "reason": "order_cue"}
    if order_cue and phone_cue:
        return {"classification": "ambiguous",
                "reason": "order_and_phone_cues_conflict"}
    # An ADJACENT unit wins over distant cues of another kind: the
    # unit belongs to this run, while a phone cue three tokens away
    # usually belongs to a different number in the same sentence.
    if after1 in _MONEY_UNITS or after1 == "tien":
        return {"classification": "money", "reason": "money_unit_adjacent"}
    if time_cue:
        return {"classification": "time", "reason": "time_unit"}
    if date_cue:
        return {"classification": "date", "reason": "date_unit"}
    if before1 == "tien" and phone_cue:
        return {"classification": "ambiguous",
                "reason": "money_and_phone_cues_conflict"}
    if before1 == "tien":
        return {"classification": "money", "reason": "money_unit_or_verb"}
    if len(digits) < MIN_PHONE_DIGITS:
        return {"classification": "other_number",
                "reason": "too_short_for_phone"}
    if len(digits) > MAX_PHONE_DIGITS:
        return {"classification": "other_number",
                "reason": "too_long_for_phone"}
    if run.get("ambiguous_khong"):
        # Leading "không" is ambiguous only for SHORT runs
        # without a phone cue: a 7+ digit sequence cannot be a
        # negation, and a phone cue ("số", call verb) resolves it
        # (reviewer fix R2-A1).
        if len(digits) < 7 and not phone_cue:
            return {"classification": "ambiguous",
                    "reason": "leading_khong_ambiguous"}
    if phone_cue:
        return {"classification": "phone", "reason": "phone_cue"}
    # A long SPOKEN digit sequence with no conflicting cue is a
    # phone number by shape: amounts use units, dates/times are
    # short, order codes are digit strings, not spoken runs.
    if run.get("kind") == "spoken" and len(digits) >= 9:
        return {"classification": "phone", "reason": "long_spoken_shape"}
    # A bare long digit string with no cue at all: it is shaped
    # like a phone number but nothing selects it as one.
    return {"classification": "ambiguous",
            "reason": "no_context_cue"}


# ---------------------------------------------------------------------------
# Phone mentions in free text (roles)
# ---------------------------------------------------------------------------

# (Negation phrases are matched inline in parse_phone_mentions
# with an adjacency requirement; see there.)
_BACKGROUND_PATTERNS = ("so moi la", "so cua", "so anh la", "so chi la",
                        "so em la", "doi so")


def _is_retired_old_number(before, after):
    """True only when retired-number language names THIS mention.

    before: folded words before the mention; after: folded words
    after it. "số cũ" immediately before the mention (or "số cũ"
    before + "không dùng nữa" after) retires it. A bare "không
    dùng nữa" after the mention, without "số cũ" before it, refers
    to some other number and does not retire this one.

    Matching is TOKEN-based, never substring (reviewer fix
    R2-A5): "số của" folds to "so cua", which CONTAINS "so cu"
    as a prefix -- the old substring check retired every
    "Số của em là X" mention as corrected_away.
    """
    before_words = before.split()
    for i in range(len(before_words) - 1):
        if before_words[i] == "so" and before_words[i + 1] == "cu":
            return True
    return False


_SPEAKER_OWNERSHIP = ("so cua em", "so cua toi", "so cua minh",
                      "so em la", "so toi la", "so minh la")


def _is_speaker_number_called(before, after):
    """True when the mention is the speaker's own number AND the
    action is on the speaker ("Số của em là X, gọi giúp em").

    Then X IS the call target, not background information
    (reviewer fix R2-A5 follow-up). Third-party ownership
    ("số của anh A") does not qualify, and neither does a
    speaker-owned number stated without an action on the speaker.
    """
    if not any(p in before for p in _SPEAKER_OWNERSHIP):
        return False
    after_words = after.split()
    return ("goi" in after_words or "nhan" in after_words) \
        and any(w in after_words for w in ("em", "toi", "minh",
                                           "giup"))


def _is_owner_new_number_statement(before, after):
    """True for "so moi cua <Name> la" before a number run.

    before/after are folded word strings from the run's window.
    Shape: "so moi cua" + 1-3 name tokens + "la" at the end of
    before, with no request verb (goi / nhan / lien / luu) in
    before or after. The name tokens must not be digits or
    request verbs themselves. "ma so Y la so moi" (M2) does not
    match: there the run precedes "la so moi", so before ends
    with "so", not "la".
    """
    bw = before.split()
    aw = after.split()
    if len(bw) < 5 or bw[-1] != "la":
        return False
    if any(v in bw or v in aw for v in ("goi", "nhan", "lien",
                                        "luu")):
        return False
    for k in range(0, len(bw) - 4):
        if bw[k:k + 3] != ["so", "moi", "cua"]:
            continue
        middle = bw[k + 3:-1]
        if not (1 <= len(middle) <= 3):
            continue
        if any(t.isdigit() or t in ("goi", "nhan", "lien", "luu")
               for t in middle):
            continue
        return True
    return False


# Forward verb patterns (folded), mirroring the negation
# module's _FORWARD_PATTERNS. Bare "chuyển" is deliberately
# absent: transfer / unknown shapes stay under their own
# rules.
_FORWARD_WORD_PATTERNS = (("chuyen", "tiep"), ("forward",),
                          ("share",))


# Generic recipient tokens (folded), mirroring the negation
# module's _GENERIC_RAW: a forward to one of these does NOT
# count as forwarding away (round-5 F-B4-4 rule -- "cho em"
# is ambiguous, possibly the speaker/assistant, not a third
# person). The check mirrors _forwarded_target_to_other's
# parts logic exactly: only the FIRST token after
# cho/toi/den matters -- a recipient phrase STARTING with a
# generic token counts as generic, whatever follows it.
_GENERIC_TOKENS = {"em", "anh", "chi", "minh", "toi", "ban",
                   "nguoi", "ai", "co", "chu", "bac", "di",
                   "tao", "to"}


def _has_generic_recipient(tokens):
    """True when `tokens` name a generic recipient: a
    cho/toi/den marker immediately followed by a generic
    token. Only the first token after the marker matters
    (mirrors _forwarded_target_to_other)."""
    for i, t in enumerate(tokens):
        if t in ("cho", "toi", "den") \
                and i + 1 < len(tokens) \
                and tokens[i + 1] in _GENERIC_TOKENS:
            return True
    return False


def _starts_with_generic_recipient(tokens):
    """True when `tokens` START with a generic recipient
    phrase (cho/toi/den + generic token). Used for the
    after window, where only the phrase immediately
    following the mention can be this forward's recipient:
    a later "cho em" belonging to another verb ("chuyển
    tiếp Số X cho Bình, nhắn cho em đi") must not exempt
    a forward to a named recipient."""
    return len(tokens) >= 2 \
        and tokens[0] in ("cho", "toi", "den") \
        and tokens[1] in _GENERIC_TOKENS


def _is_forwarded_object(before, after):
    """True when the mention is the object of a forward verb.

    before/after: folded word strings from the mention's
    window (radius 8). Two shapes, mirroring the negation
    module's _FORWARD_PATTERNS (bare "chuyển" is NOT a
    forward pattern: transfer / unknown shapes stay under
    their own rules; only "chuyển tiếp" / "forward" /
    "share" count):
      - verb-before: the LAST forward pattern in before
        governs, provided nothing but recipient markers,
        names, and the "số" marker intervenes (no digit, no
        action verb: those belong to another verb -- e.g.
        "gọi số X rồi chuyển tiếp số Y" leaves X with
        "gọi", and "chuyển tiếp số X rồi gọi số Y" leaves
        Y with "gọi");
      - verb-after (topicalised object): only when NO verb
        precedes the mention at all ("Số X, chuyển tiếp
        cho Bình"); a mention already governed by an
        earlier verb ("Gọi số X, chuyển tiếp số Y") keeps
        its own reading, so the pattern must start the
        after window.
    """
    bw = before.split()
    aw = after.split()
    last = None
    for k in range(len(bw)):
        for pat in _FORWARD_WORD_PATTERNS:
            if bw[k:k + len(pat)] == list(pat):
                last = (k, len(pat))
    if last is not None:
        k, width = last
        between = bw[k + width:]
        if not any(t.isdigit() for t in between) \
                and not any(t in ("goi", "nhan", "lien", "luu")
                            for t in between) \
                and not any(t in ("khong", "mot", "hai", "ba",
                                  "bon", "nam", "sau", "bay",
                                  "tam", "chin") for t in between):
            # Generic recipient (round-8 fix for the 2f/4b
            # regression): forwarding to "em" / "mình" /
            # "anh" / ... does NOT count as forwarding away
            # (F-B4-4 rule, mirrored from
            # _forwarded_target_to_other). The recipient may
            # sit between the verb and the mention ("chuyển
            # tiếp cho em Số X") or immediately after the
            # mention ("chuyển tiếp Số X cho em"); only the
            # immediately-following phrase counts for the
            # after window, so a later "cho em" belonging
            # to another verb never exempts a forward to a
            # named recipient.
            if _has_generic_recipient(between) \
                    or _starts_with_generic_recipient(aw):
                return False
            return True
        return False
    if any(t in ("goi", "nhan", "lien", "luu") for t in bw):
        return False
    for pat in _FORWARD_WORD_PATTERNS:
        if aw[:len(pat)] == list(pat):
            # Same generic-recipient exemption, for the
            # topicalised shape ("Số X, chuyển tiếp cho em"):
            # only the phrase immediately after the pattern
            # can be this forward's recipient.
            if _starts_with_generic_recipient(aw[len(pat):]):
                return False
            return True
    return False


def _window_text(folded, tokens, first, last, radius=8):
    before = " ".join(t for t, _, _ in tokens[max(0, first - radius):first])
    after = " ".join(t for t, _, _ in tokens[last + 1:last + radius + 1])
    return before, after


def parse_phone_mentions(text):
    """Phone-number mentions in free text, with roles.

    Only runs that classify as "phone" are returned. Each mention:

      {"raw", "normalized" (via norm_phone, never edited to fit),
       "span", "kind": "digits"|"spoken", "role": ...,
       "reason": <machine-readable str>}

    Roles:
      requested_target -- the text asks to call / message / save /
        use this number (action verb or phone cue selects it);
      negated          -- explicitly negated ("không phải số X",
        "đừng gọi số X");
      corrected_away   -- the old value in a correction ("số cũ ...
        không dùng nữa", or the Y in "X chứ không phải Y");
      background       -- mentioned as information only ("số mới
        là X" stated without an action on X);
      ambiguous        -- role cannot be determined (incl. an
        ambiguous leading "không").

    Non-phone runs (money, time, date, order codes, short tails)
    are NOT returned here; use find_digit_runs +
    classify_phone_context to see them. A mention is never invented
    from a run the classifier rejects.
    """
    if not text:
        return []
    folded = fold_vietnamese(text)
    tokens = _tokens_with_spans(folded)
    mentions = []
    for run in find_digit_runs(text):
        cls = classify_phone_context(text, run)
        if cls["classification"] != "phone":
            continue
        first, last = run["token_span"]
        before, after = _window_text(folded, tokens, first, last)
        role, reason = "requested_target", "phone_cue"
        # Negation must attach ADJACENTLY to this mention: the
        # negation phrase plus at most a call verb / "số" between
        # it and the run. A negation eight tokens back usually
        # belongs to a different number ("Không phải số A, mà là
        # số B" must leave B affirmed).
        before_tail = " ".join(
            t for t, _, _ in tokens[max(0, first - 5):first])
        # Correction-marker guard (round-2 fix S13): a "không"
        # that belongs to the correction marker "à không" (or
        # the tail "à không, gọi/nhắn số ..." after it) is NOT
        # a negation of the verb that follows it. Without this
        # guard, "À không, gọi số B đi" reads B as negated, so
        # the correction turn never becomes a valid phone turn
        # and the OLD number keeps binding instead. The guard
        # only suppresses the negation branch; the retired /
        # speaker / background branches below still run.
        _is_correction_khong = bool(re.search(
            r"(^|\s)a\s+khong(\s+(so|goi|nhan))*\s*$",
            before_tail))
        if not _is_correction_khong and re.search(
                r"(khong phai|dung goi|dung nhan|khong goi|"
                r"khong nhan)(\s+(so|goi|nhan))*\s*$",
                before_tail):
            role, reason = "negated", "negation_before"
        elif _is_retired_old_number(before, after):
            # Only when the retired-number language attaches to
            # THIS mention ("số cũ ... không dùng nữa" naming it):
            # a following "số cũ không dùng nữa" about some OTHER
            # (often unstated) number must not retire this one --
            # e.g. "số mới của anh là X, số cũ anh không dùng
            # nữa đâu" states X as the new number, it does not
            # retire X.
            role, reason = "corrected_away", "old_number_retired"
        elif _is_speaker_number_called(before, after):
            role, reason = "requested_target", "speaker_number_called"
        elif _is_forwarded_object(before, after):
            # Forward object (round-8 fix S2): a number being
            # forwarded to someone else is CONTENT, not a
            # call/message target -- parallel to the S4
            # content rule. It must not become a requested
            # target (which would let "chuyển tiếp số X cho
            # Bình, đổi sang số 12, gọi đi" select X), nor a
            # binding candidate (a forward turn is not a
            # call/message instruction; layer C would
            # mismatch-veto it anyway, so dropping it only
            # removes a veto step, never an un-fire).
            role, reason = "background", "forwarded_object"
        elif any(pat in before for pat in _BACKGROUND_PATTERNS) \
                and not any(v in before for v in _ACTION_VERBS):
            role, reason = "background", "information_only"
        elif _is_owner_new_number_statement(before, after):
            # Owner new-number statement (round-5 fix F-B4-9):
            # "so moi cua <Name> la Y" states a fact about
            # someone else's new number, with no request verb
            # and no continuation -- it must not bind Y as a
            # direct request the way the bare "so moi la Y"
            # pattern does not. Distinguished from M2 ("ma so
            # Y la so moi": the number precedes "la so moi",
            # a correction) by shape: here the number FOLLOWS
            # "la". An action verb anywhere in the window
            # keeps the requested_target reading.
            role, reason = "background", \
                "owner_new_number_statement"
        elif after.split()[:1] == ["la"] \
                and len(after.split()) >= 3 \
                and after.split()[1] == "so" \
                and after.split()[2] in ("moi", "khac"):
            # New-number statement, NOT role information
            # (round-4 fix M2): "Mà số X là số mới" replaces
            # the previous number, so it must not be demoted
            # to background the way "Số X là số tổng đài" (a
            # role fact) is. With no action verb it keeps the
            # default requested_target reading: the number is
            # the newly selected one. Round-9 marker: this
            # correction frame IS selection evidence (it
            # explicitly selects the new number), so the
            # mention reason is marked distinctly from a
            # bare phone_cue mention; the round-9 joint
            # veto in the adapter exempts mentions with
            # this reason. Role stays requested_target, so
            # question_b / binding behaviour is unchanged.
            reason = "ma_new_number_selection"
        elif after.split()[:1] == ["la"] \
                and not any(v in (before.split() + after.split())
                            for v in _ACTION_VERBS):
            # Copula information (round-2 fix M-b): "Số X là số
            # tổng đài" / "Số X là số của em" states a fact
            # about X; with no action verb anywhere in the
            # window it is not an instruction to use X, so it
            # must not become a phone turn that hijacks a later
            # prior-instruction binding. An action verb anywhere
            # in the window keeps the requested_target reading
            # ("Gọi số X là số chính" still requests X).
            role, reason = "background", "copula_information_only"
        elif run.get("ambiguous_khong") \
                and len(run["digits"]) < 7 \
                and not any(w in (before.split() + after.split())
                            for w in ("so", "goi", "nhan", "tong",
                                      "dai", "truc")):
            # Leading-"không" ambiguity survives only for SHORT
            # runs without a phone cue: a 7+ digit sequence cannot
            # be a negation, and a phone cue resolves it
            # (reviewer fix R2-A1; mirrors classify_phone_context).
            role, reason = "ambiguous", "leading_khong_ambiguous"
        elif not any(v in before or v in after
                     for v in _ACTION_VERBS + ("so", "truc", "tong")):
            # Phone-shaped but nothing in the sentence acts on it.
            role, reason = "ambiguous", "no_action_verb"
        mentions.append({
            "raw": run["raw"],
            "normalized": norm_phone(run["digits"]),
            "span": run["span"],
            "kind": run["kind"],
            "role": role,
            "reason": reason,
        })
    return mentions


# ---------------------------------------------------------------------------
# Tail corrections ("đuôi là X chứ không phải Y")
# ---------------------------------------------------------------------------

_SPOKEN_RUN_RE = (
    r"(?:khong|mot|hai|ba|bon|nam|sau|bay|tam|chin)"
    r"(?:[\s,]+(?:khong|mot|hai|ba|bon|nam|sau|bay|tam|chin))*"
)
_DIGIT_RUN_RE = r"\d+"


def _tail_digits(fragment):
    """Digit string of a tail fragment (spoken words or digits)."""
    fragment = fragment.strip(" ,.")
    if not fragment:
        return ""
    if re.fullmatch(r"\d+", fragment):
        return fragment
    words = re.findall(
        r"khong|mot|hai|ba|bon|nam|sau|bay|tam|chin",
        fold_vietnamese(fragment))
    if not words or len(" ".join(words)) < len(fragment.strip()) - 1:
        # Fragment contains non-digit words: not a clean tail.
        return ""
    return "".join(_DIGIT_WORDS[w] for w in words)


def parse_tail_correction(text):
    """Parse an explicit tail correction, or return None.

    Recognised (folded) patterns:
      "duoi la <A> chu khong phai <B>"
      "<A> chu khong phai <B>"  (A, B digit runs)
    Returns {"old_tail": B, "new_tail": A, "reason": ...} or None.
    The correction itself proves nothing about any full number; it
    only says: take a number ending in B and replace its tail by A.
    "span" is the folded-text char span of the match (folding is
    1:1 per character, so it aligns with the raw text too).
    """
    if not text:
        return None
    folded = fold_vietnamese(text)
    m = re.search(
        r"(?:duoi la\s+)?(" + _SPOKEN_RUN_RE + r"|" + _DIGIT_RUN_RE +
        r")\s+chu khong phai\s+(" + _SPOKEN_RUN_RE + r"|" +
        _DIGIT_RUN_RE + r")",
        folded)
    if not m:
        return None
    new_tail = _tail_digits(m.group(1))
    old_tail = _tail_digits(m.group(2))
    if not new_tail or not old_tail or new_tail == old_tail:
        return None
    if len(old_tail) > 6 or len(new_tail) > 6:
        return None
    return {"old_tail": old_tail, "new_tail": new_tail,
            "reason": "explicit_tail_correction",
            "span": (m.start(), m.end())}


def parse_tail_change(text):
    """Parse a bare tail-change statement, or return None.

    Recognised (folded) patterns, with the new tail as typed
    digits or a spoken digit run:
      "duoi doi thanh <T>", "duoi thanh <T>", "duoi la <T>",
      "doi duoi thanh <T>"
    ("duoi la <A> chu khong phai <B>" is an explicit tail
    correction, handled by parse_tail_correction, not here.)
    Returns {"new_tail": T, "reason": ..., "span": ...} or None.
    A trailing politeness particle ("đi", "nhé", "giúp tôi")
    after the tail is ignored: only the leading digit run (or
    spoken run) counts. A fragment with non-digit words after
    the run is not a clean tail and returns None.
    """
    if not text:
        return None
    folded = fold_vietnamese(text)
    if "chu khong phai" in folded:
        return None
    m = re.search(
        r"(?:duoi\s+(?:doi\s+thanh|thanh|la)"
        r"|doi\s+duoi\s+thanh)\s+",
        folded)
    if not m:
        return None
    rest = folded[m.end():]
    dm = re.match(r"\d[\d\s]*", rest)
    if dm:
        tail = re.sub(r"\s+", "", dm.group(0))
        span = (m.end(), m.end() + len(dm.group(0)))
    else:
        sm = re.match(
            r"(?:khong|mot|hai|ba|bon|nam|sau|bay|tam|chin)"
            r"(?:\s+(?:khong|mot|hai|ba|bon|nam|sau|bay|tam|chin))*",
            rest)
        if not sm:
            return None
        tail = _tail_digits(sm.group(0))
        span = (m.end(), m.end() + len(sm.group(0)))
    if not tail or len(tail) > 6:
        return None
    return {"new_tail": tail, "reason": "tail_change",
            "span": span}


def apply_tail_correction(number, correction):
    """Apply a parsed tail correction to a full number, or None.

    Only the tail is replaced; every other digit must already match
    (the number must end with old_tail). No digit is invented: if
    the number does not end with old_tail, there is no correction.
    """
    if not number or not correction:
        return None
    num = norm_phone(number)
    old, new = correction["old_tail"], correction["new_tail"]
    if not num.endswith(old):
        return None
    corrected = num[:len(num) - len(old)] + new
    if len(corrected) < MIN_PHONE_DIGITS \
            or len(corrected) > MAX_PHONE_DIGITS:
        return None
    return corrected


# ---------------------------------------------------------------------------
# Safe history-result parsing (never eval, never char-wise zip)
# ---------------------------------------------------------------------------

def parse_history_result(raw):
    """Parse a history tool result safely.

    Accepts dict / list as-is; a string is tried as JSON, then as a
    Python literal (repr form: single quotes, True/False/None) via
    ast.literal_eval. Anything else -- or a string that parses to
    neither -- returns status "malformed" with a reason, never a
    crash and never a guessed value. eval is never used, and
    results are never zipped character by character.
    """
    if isinstance(raw, (dict, list)):
        return {"status": "ok", "value": raw, "reason": "native"}
    if isinstance(raw, str):
        stripped = raw.strip()
        if not stripped:
            return {"status": "malformed", "value": None,
                    "reason": "empty_string"}
        try:
            return {"status": "ok", "value": json.loads(stripped),
                    "reason": "json"}
        except (ValueError, TypeError):
            pass
        try:
            return {"status": "ok", "value": ast.literal_eval(stripped),
                    "reason": "python_repr"}
        except (ValueError, SyntaxError, TypeError, MemoryError,
                RecursionError):
            return {"status": "malformed", "value": None,
                    "reason": "unparsable_string"}
    return {"status": "malformed", "value": None,
            "reason": "unsupported_type_%s" % type(raw).__name__}


# ---------------------------------------------------------------------------
# Structured records out of read results
# ---------------------------------------------------------------------------

def extract_log_records(result, tool, position):
    """Structured counterpart records from one SUCCEEDED read result.

    Handles the shapes the simulator actually returns:
      phone.recent_calls: {"calls": [{id, contact: {id, name,
        phone} | contact_id, phone_number, direction, status, ...}]}
      sms.read_recent:    {"messages": [{id, contact_id,
        phone_number, direction, content, ...}]}
      chat_ott.read_chat: {"messages": [{from, content, ...}]}
        (no structured counterpart: content is free text, handled
        by the read_result content path, NOT as a contact record)
      contacts.search/get: {"contacts": [{id, name, phone, ...}]}
    A record is a dict with tool / position / record_id /
    contact_id / phone_number / name / relation / direction /
    status / content / time. Nested contact dicts are unpacked;
    free-text content is NEVER mined for contact_ids (only phone
    digits via the content path). "relation" is preserved from
    nested contact dicts and contacts records: it is the ONLY
    structured relation evidence the family path may use.
    Malformed results yield no records and a malformed flag via
    parse_history_result (callers check that separately).
    """
    parsed = parse_history_result(result)
    if parsed["status"] != "ok" or not isinstance(parsed["value"], dict):
        return []
    value = parsed["value"]
    records = []
    if tool in CALL_LOG_TOOLS:
        for rec in value.get("calls") or []:
            if not isinstance(rec, dict):
                continue
            contact = rec.get("contact") or {}
            records.append({
                "tool": tool, "position": position,
                "record_id": rec.get("id"),
                "contact_id": contact.get("id")
                if isinstance(contact, dict)
                else rec.get("contact_id"),
                "phone_number": norm_phone(contact.get("phone"))
                if isinstance(contact, dict) and contact.get("phone")
                else norm_phone(rec.get("phone_number")),
                "name": contact.get("name")
                if isinstance(contact, dict) else None,
                "relation": contact.get("relation")
                if isinstance(contact, dict) else None,
                "direction": rec.get("direction"),
                "status": rec.get("status"),
                "content": None,
                "time": rec.get("time"),
            })
    elif tool in MESSAGE_LOG_TOOLS:
        for rec in value.get("messages") or []:
            if not isinstance(rec, dict):
                continue
            records.append({
                "tool": tool, "position": position,
                "record_id": rec.get("id"),
                "contact_id": rec.get("contact_id"),
                "phone_number": norm_phone(rec.get("phone_number")),
                "name": None,
                "direction": rec.get("direction"),
                "status": None,
                "content": rec.get("content"),
                "time": rec.get("time"),
            })
    elif tool == "chat_ott.read_chat":
        for rec in value.get("messages") or []:
            if not isinstance(rec, dict):
                continue
            records.append({
                "tool": tool, "position": position,
                "record_id": None,
                "contact_id": None,
                "phone_number": "",
                "name": rec.get("from"),
                "direction": None,
                "status": None,
                "content": rec.get("content"),
                "time": rec.get("time"),
            })
    elif tool in ("contacts.search", "contacts.get"):
        for rec in value.get("contacts") or []:
            if not isinstance(rec, dict):
                continue
            records.append({
                "tool": tool, "position": position,
                "record_id": rec.get("id"),
                "contact_id": rec.get("id"),
                "phone_number": norm_phone(rec.get("phone")),
                "name": rec.get("name"),
                "relation": rec.get("relation"),
                "direction": None,
                "status": None,
                "content": None,
                "time": rec.get("time"),
            })
    return records


# ---------------------------------------------------------------------------
# Binding a current reference to exactly one history record
# ---------------------------------------------------------------------------

def _name_tokens(text):
    """Folded word tokens of a text, for name matching."""
    return set(_TOKEN_RE.findall(fold_vietnamese(text or "")))


def _raw_tokens(text):
    """Diacritic-sensitive lowercased word tokens of the ORIGINAL text.

    NOTE: this must NOT reuse _TOKEN_RE ([a-z0-9]+), which drops
    diacritic marks and would shred "Mạ" into {"m", "a"} -- a
    false match against "mẹ" ({"m"}). The Unicode word regex
    below keeps "mạ", "mẹ", "ăn" whole, which is exactly the
    distinction the name matcher needs.
    """
    return set(re.findall(r"[^\W_]+", (text or "").lower(),
                          flags=re.UNICODE))


def _raw_token_list(text):
    """Ordered diacritic-sensitive lowercased word tokens."""
    return re.findall(r"[^\W_]+", (text or "").lower(),
                      flags=re.UNICODE)


def _folded_token_list(text):
    """Ordered folded word tokens."""
    return _TOKEN_RE.findall(fold_vietnamese(text or ""))


def _phrase_in(phrase_tokens, text_tokens):
    """True iff phrase_tokens occur consecutively, in order."""
    n = len(phrase_tokens)
    if n == 0 or n > len(text_tokens):
        return False
    return any(text_tokens[i:i + n] == phrase_tokens
               for i in range(len(text_tokens) - n + 1))


def _name_matches(name, text):
    """True iff `name` is named in `text` (fix round: full phrase).

    CONTRACT CHANGE (callback fix round, thread A): token-set
    intersection is BANNED. The old rule matched on ANY shared
    token, so "Nguyễn An" matched a text naming "Nguyễn Bình"
    (shared surname "Nguyễn") and defeated the addressee veto.
      - single-token name: diacritic-SENSITIVE exact token
        (case-insensitive), never folded -- "An" != "ăn",
        "Bình" != "binh" (ASR diacritic loss falls back to
        AMBIGUOUS, the safe direction, as before);
      - multi-token name: the FULL PHRASE, consecutive tokens in
        order, either diacritic-sensitive or folded (a full
        phrase is distinctive enough that a folded hit is not a
        common-word collision).
    A shared surname or a shared common token NEVER matches.
    """
    if not name or not text:
        return False
    raw_name = _raw_token_list(name)
    if not raw_name:
        return False
    raw_text = _raw_token_list(text)
    if len(raw_name) == 1:
        return raw_name[0] in raw_text
    if _phrase_in(raw_name, raw_text):
        return True
    return _phrase_in(_folded_token_list(name),
                      _folded_token_list(text))


# Tokens that may sit in the addressee slot after a callback verb
# without being a name ("trả lời tin nhắn", "gọi lại cho em",
# "gọi lại cho mẹ"): they never trigger the name veto.
_ADDRESSEE_STOPLIST = {
    "toi", "em", "anh", "chi", "minh", "ban", "giup", "to",
    "nhanh", "luon", "ngay", "so", "tin", "nhan", "cuoc", "goi",
    "lai", "them", "nua", "di", "dum", "ho", "cho", "ca", "nha",
    "nhe", "oi", "ay", "do", "day", "kia", "nay", "la", "thi",
    "va", "cua", "co", "khong", "da", "dang", "se", "bi", "duoc",
    "voi", "ve", "o", "tai", "tren", "trong", "tu", "den", "neu",
    "khi", "ma", "vua", "moi", "xin", "gium", "cung",
    # Family references, not names ("gọi lại cho mẹ" must not
    # veto the single-pool fallback: the pool record may be the
    # parent under a different name form).
    "me", "ma", "bo", "ba", "vo", "chong", "con",
    # Verbs that may sit in the slot before the real addressee
    # ("nhắn lại bảo An ..."): not names, never veto.
    "bao", "noi", "hoi", "ke", "nho", "dan", "chuyen", "ghi",
    "nhac",
    # Generic person references ("gọi lại người vừa gọi",
    # "nhắn lại cho người đó"): not names, never veto.
    "nguoi",
}


_QUOTE_RE = re.compile(r'"[^"]*"|\'[^\']*\'|“[^”]*”|«[^»]*»')


def _strip_quoted_spans(text):
    """Remove quoted spans: a name inside quotes is message
    content, never the request's addressee."""
    return _QUOTE_RE.sub(" ", text or "")


# Family / relation tokens (folded). "mạ" folds to "ma" and is a
# family word in central dialect. A contact literally NAMED
# "Mạ"/"Mẹ" is still matched by the name-first exact rule in the
# callback branch before this set is consulted.
_FAMILY_TOKENS = {"me", "ma", "bo", "ba", "vo", "chong", "con"}

# Tokens that end an addressee span (clause boundary, politeness
# particle, a new verb, a generic object like "tin nhắn"/"số").
# Checked only for tokens AFTER the first addressee token.
_ADDRESSEE_BOUNDARY = {
    "giup", "gium", "dum", "de", "roi", "va", "nhe", "nha", "di",
    "nua", "luon", "ngay", "oi", "a", "cho", "voi", "ve", "o",
    "tai", "tren", "trong", "tu", "den", "neu", "khi", "ma",
    "thi", "la", "goi", "nhan", "tra", "khong", "so", "tin",
    "cuoc", "lai", "vua", "do", "nay", "day", "kia", "ay",
}

# First-token values that mean "no person addressee" (a generic
# object or a politeness verb, not a name): "trả lời tin nhắn",
# "gọi lại số đó", "gọi lại giúp tôi".
_ADDRESSEE_SKIP_FIRST = {
    "giup", "gium", "dum", "di", "nhe", "nha", "luon", "ngay",
    "oi", "a", "tin", "so", "cuoc", "nhan",
}

# Generic person references in the addressee slot: pronouns and
# "người (đó)". They impose NO name/family constraint, so the
# generic single-pool flow still applies. A bare "minh" (no
# diacritic) is NOT generic: it is the name Minh; only "mình"
# (with diacritic) is the pronoun.
_ADDRESSEE_GENERIC = {
    "em", "anh", "chi", "toi", "ban", "nguoi", "to",
}

# Title tokens dropped when they precede a name ("anh Bình" ->
# "Bình", "chị Lan" -> "Lan"). Only when more tokens follow.
_ADDRESSEE_TITLES = {"anh", "chi", "em", "co", "chu", "bac", "ong",
                     "ban"}


def _extract_addressee(text):
    """Addressee phrase of the FIRST callback clause, or None.

    The addressee is the span right after a callback verb
    ("gọi lại" / "nhắn lại" / "trả lời") plus an optional
    "cho"/"tới"/"đến", in the quote-stripped text. Returns
    (raw_tokens, folded_tokens) or None. At most 3 tokens, cut
    at clause boundaries and punctuation. A name in another
    clause, in a quote, or in message content is never returned
    here -- only the callback clause's addressee counts.
    NOTE: the FIRST callback clause is used. A later correction
    to a different person ("gọi lại cho Vy, à không, gọi cho
    An") is thread B's (negation/correction) scope, not this
    extractor's.
    """
    clean = _strip_quoted_spans(text)
    toks = [(m.group(0).lower(), m.start(), m.end())
            for m in re.finditer(r"[^\W_]+", clean, flags=re.UNICODE)]
    if not toks:
        return None
    folded = [fold_vietnamese(t) for t, _, _ in toks]
    verb_at = None
    for i in range(len(toks) - 1):
        if (folded[i], folded[i + 1]) in (
                ("goi", "lai"), ("nhan", "lai"), ("tra", "loi")):
            verb_at = i + 2
            break
    if verb_at is None:
        return None
    j = verb_at
    if j < len(toks) and folded[j] in ("cho", "toi", "den"):
        j += 1
    if j >= len(toks) or folded[j] in _ADDRESSEE_SKIP_FIRST:
        return None
    raw, fold = [], []
    for k in range(j, min(j + 3, len(toks))):
        if k > j:
            between = clean[toks[k - 1][2]:toks[k][1]]
            if any(ch in between for ch in ",.!?;:"):
                break
            if folded[k] in _ADDRESSEE_BOUNDARY:
                break
        raw.append(toks[k][0])
        fold.append(folded[k])
    if not raw:
        return None
    if len(raw) > 1 and fold[0] in _ADDRESSEE_TITLES:
        raw, fold = raw[1:], fold[1:]
    return (raw, fold) if raw else None


def _classify_addressee(phrase_raw, phrase_folded):
    """Kind of an addressee phrase: "family", "generic", or "name".

    "family": a single family/relation token ("mẹ", "mạ", "bố",
      "ba", "vợ", "chồng", "con") -- NOT a name, and it must go
      through the relation-evidence path, never the single-pool
      fallback.
    "generic": a pronoun / generic person reference ("em", "anh",
      "chị", "tôi", "bạn", "người", "mình" with diacritic).
      A bare "minh" (no diacritic) is the name Minh, not the
      pronoun, so it classifies as "name".
    "name": anything else -- a candidate name phrase, to be
      matched against the pool by _addressee_name_matches.
    """
    if not phrase_raw:
        return None
    folded_phrase = " ".join(phrase_folded)
    if len(phrase_raw) == 1 and phrase_folded[0] == "minh":
        return "generic" if phrase_raw[0] != "minh" else "name"
    if folded_phrase in _ADDRESSEE_GENERIC:
        return "generic"
    if len(phrase_raw) == 1 and phrase_folded[0] in _FAMILY_TOKENS:
        return "family"
    return "name"


def _addressee_name_matches(phrase_raw, phrase_folded, name):
    """True iff an addressee phrase identifies `name`.

    - exact full name (diacritic-sensitive, or folded for a
      multi-token phrase);
    - single-token phrase equal to the name's FINAL token (the
      given name). Uniqueness across the pool is the caller's
      job: bind only when exactly one pool record matches.
    A surname-only phrase (a non-final token) NEVER matches.
    """
    raw_name = _raw_token_list(name)
    if not raw_name:
        return False
    if phrase_raw == raw_name:
        return True
    if len(phrase_raw) >= 2 \
            and phrase_folded == _folded_token_list(name):
        return True
    if len(phrase_raw) == 1 and len(raw_name) > 1 \
            and phrase_raw[0] == raw_name[-1]:
        return True
    return False


def _relation_claims(contact_id, pool, roster):
    """Folded relation values claimed for one counterpart.

    Sources (runtime-observable only): the pool record's own
    "relation" field and roster entries with the same id
    carrying a "relation" field. Free-text names, message
    content, and assistant prose are NOT relation evidence.
    """
    vals = set()
    if contact_id is None:
        return vals
    for r in pool or []:
        if r.get("contact_id") == contact_id and r.get("relation"):
            vals.add(fold_vietnamese(r["relation"]))
    for c in roster or []:
        if str(c.get("id")) == str(contact_id) and c.get("relation"):
            vals.add(fold_vietnamese(c["relation"]))
    return vals


def _bind_by_relation(relation, pool, roster):
    """Bind a family addressee via relation evidence.

    Binds only when exactly one pool record's counterpart claims
    this relation AND no roster entry claims it for a different
    counterpart. Otherwise (None, reason):
      - callback_relation_ambiguous: several counterparts claim it;
      - callback_relation_selects_other: a non-pool counterpart
        claims it (the request selects them, not any pool record);
      - callback_relation_conflict: the single pool record's
        counterpart explicitly claims a DIFFERENT relation;
      - callback_relation_unproven: nobody claims it -- question
        (a) may hold (the caller exists) but question (b) is
        UNKNOWN/AMBIGUOUS, never True.
    """
    claimants = set()
    for r in pool or []:
        cid = r.get("contact_id")
        if cid and relation in _relation_claims(cid, pool, roster):
            claimants.add(cid)
    for c in roster or []:
        if c.get("relation") \
                and fold_vietnamese(c["relation"]) == relation \
                and c.get("id"):
            claimants.add(c["id"])
    pool_matches = [r for r in pool
                    if r.get("contact_id") in claimants]
    if len(claimants) == 1 and len(pool_matches) == 1:
        return pool_matches[0], "callback_relation_match"
    if len(claimants) > 1:
        return None, "callback_relation_ambiguous"
    if claimants:
        return None, "callback_relation_selects_other"
    if len(pool) == 1:
        vals = _relation_claims(pool[0].get("contact_id"),
                                pool, roster)
        if vals:
            return None, "callback_relation_conflict"
    return None, "callback_relation_unproven"


def _explicit_addressee(text):
    """First folded token of a name addressee, or None.

    Compatibility wrapper around _extract_addressee: only a
    name-kind phrase yields a token; family, generic, and
    absent addressees yield None (family references are handled
    by the relation path, not by this veto token).
    """
    addr = _extract_addressee(text)
    if addr is None:
        return None
    raw, folded = addr
    if _classify_addressee(raw, folded) != "name":
        return None
    return folded[0]


def _select_by_topic_amount(current_text, cands):
    """Disambiguate log-record candidates by content overlap.

    Topic: same-language content-token overlap (function words
    removed). Amount: a simple amount in the current text that
    appears in exactly one candidate's content. Returns
    (record, reason) or (None, reason). Equality-based only: it
    never creates a record, only selects among existing ones.
    """
    top = [(r, _topic_overlap(current_text, r.get("content") or ""))
           for r in cands]
    winners = [r for r, o in top if o > 0]
    if len(winners) == 1:
        return winners[0], "topic_unique"
    amounts = _content_amounts(current_text)
    if amounts:
        amt = [r for r in cands
               if _content_amounts(r.get("content") or "") & amounts]
        if len(amt) == 1:
            return amt[0], "amount_unique"
    return None, "topic_amount_ambiguous"


def _content_amounts(text):
    """Simple amounts in a text: comma-grouped digit strings and
    single-unit spoken amounts ("hai trăm nghìn" -> 200000,
    "ba triệu" -> 3000000, "năm nghìn" -> 5000). Compound amounts
    ("sáu trăm hai mươi nghìn", "một triệu tám") are NOT parsed:
    they yield nothing rather than a guessed value.
    """
    if not text:
        return set()
    folded = fold_vietnamese(text)
    amounts = set()
    for m in re.finditer(r"\d{1,3}(?:,\d{3})+|\d{4,}", folded):
        try:
            amounts.add(int(m.group(0).replace(",", "")))
        except ValueError:
            pass
    tokens = [t for t, _, _ in _tokens_with_spans(folded)]
    i = 0
    while i < len(tokens):
        if tokens[i] in _DIGIT_WORDS and i + 1 < len(tokens):
            num = int(_DIGIT_WORDS[tokens[i]])
            if tokens[i + 1] == "tram" and i + 2 < len(tokens) \
                    and tokens[i + 2] == "nghin":
                amounts.add(num * 100000)
                i += 3
                continue
            if tokens[i + 1] == "nghin":
                amounts.add(num * 1000)
                i += 2
                continue
            if tokens[i + 1] == "trieu":
                amounts.add(num * 1000000)
                i += 2
                continue
            if tokens[i + 1] == "dong":
                amounts.add(num)
                i += 2
                continue
        i += 1
    return amounts


_TOPIC_STOPWORDS = {
    "la", "thi", "va", "cho", "cua", "em", "anh", "chi", "toi",
    "co", "khong", "da", "dang", "se", "bi", "duoc", "voi", "ve",
    "o", "tai", "tren", "trong", "tu", "den", "neu", "khi", "ma",
    "nay", "do", "day", "kia", "ay", "oi", "nhe", "nha", "gium",
    "dum", "giup", "xin", "moi", "ca", "cung", "ma", "vua",
}


def _topic_overlap(current_text, content):
    """Content-token overlap between current text and a record's
    content, ignoring function words. Returns the overlap count."""
    if not current_text or not content:
        return 0
    cur = _name_tokens(current_text) - _TOPIC_STOPWORDS
    con = _name_tokens(content) - _TOPIC_STOPWORDS
    return len(cur & con)


def _instruction_addressee(text):
    """Addressee phrase of a plain instruction turn (cho-form).

    Unlike _extract_addressee (which needs a callback verb
    "gọi lại" / "nhắn lại"), this reads the first "cho" /
    "tới" / "đến" + 1-2 name tokens in any instruction turn:
    "Gọi cho Vy số X", "Nhắn cho Nguyễn Bình số X". Generic
    first tokens (pronouns) and family single tokens are NOT
    returned: pronouns name nobody, and family words go
    through the relation path, never a name map. Folded
    "minh" is ambiguous (pronoun "mình" vs the name Minh)
    and is conservatively excluded. Returns the folded phrase
    string, or None.
    """
    if not text:
        return None
    toks = re.findall(r"[^\W_]+", fold_vietnamese(text))
    _generic = {"em", "anh", "chi", "minh", "toi", "ban", "nguoi",
                "ai", "co", "chu", "bac", "di", "tao", "to"}
    _family = {"me", "ma", "bo", "ba", "vo", "chong", "con"}
    _stops = {"so", "nhu", "luc", "nay", "lam", "goi", "nhan",
              "dien", "gui", "tra", "dan", "noi", "bao", "da",
              "la", "thi", "ma", "nua", "di", "nhe", "nha",
              "giup", "dum", "voi", "de"}
    for k, tok in enumerate(toks):
        if tok not in ("cho", "toi", "den"):
            continue
        parts = []
        for cand in toks[k + 1:k + 3]:
            if cand in _stops or cand.isdigit():
                break
            parts.append(cand)
            if len(parts) == 1 \
                    and (parts[0] in _generic
                         or parts[0] in _family):
                parts = []
                break
        if parts:
            return " ".join(parts)
    return None


def _instruction_turn_action(text):
    """call / message / None for an instruction turn.

    Folded token scan: "gọi" / "điện" -> call; "nhắn" / "sms" /
    "trả lời" / "gửi tin" -> message. Bare "gửi" is None:
    without "tin nhắn" / "sms" it does not positively classify
    as a message (same rule as instruction_action's inventory).
    Both verbs present -> None (ambiguous action).
    """
    if not text:
        return None
    toks = re.findall(r"[^\W_]+", fold_vietnamese(text))
    is_call = any(t in ("goi", "dien") for t in toks)
    is_msg = any(t in ("nhan", "sms") for t in toks) \
        or any(toks[i] == "tra" and toks[i + 1] == "loi"
               for i in range(len(toks) - 1)) \
        or any(toks[i] == "gui" and toks[i + 1] == "tin"
               for i in range(len(toks) - 1))
    if is_call and is_msg:
        return None
    if is_call:
        return "call"
    if is_msg:
        return "message"
    return None


def _instruction_name_map(turns):
    """name phrase -> [(phone, position, action)] from user
    turns pairing an addressee with a requested-target phone
    mention ("Gọi cho Vy số X"). Turns without an addressee,
    without a requested-target mention, or with several
    distinct numbers contribute nothing. Family / generic
    addressees never enter the map."""
    mapping = {}
    for t in turns or []:
        text = t.get("text") or ""
        addr = _instruction_addressee(text)
        if addr is None:
            continue
        mentions = [m for m in parse_phone_mentions(text)
                    if m["role"] == "requested_target"]
        nums = {m["normalized"] for m in mentions}
        if len(nums) != 1:
            continue
        action = _instruction_turn_action(text)
        if action is None:
            continue
        mapping.setdefault(addr, []).append(
            (next(iter(nums)), t.get("position", -1), action))
    return mapping


def bind_history_reference(current_text, history_records, roster=None,
                           action=None):
    """Bind a current reference to exactly one history record.

    history_records: list of record dicts (from
    extract_log_records) and/or user-turn dicts
    {"kind": "user_turn", "text": ..., "position": ...}.
    roster: optional [{id, name, phone, relation}] -- only used
    for relation evidence (family addressees) and never as a
    fallback source for names.

    Reference patterns recognised in the current text (folded):
      - callback / reply: "goi lai", "nhan lai", "tra loi" (+ name)
      - missed caller: "goi nho", "nguoi vua goi", "nguoi vua nhan",
        "ai goi"
      - anaphoric number: "so do", "so nay", "so moi nhat"
      - prior instruction: "luc nay", "nhu ... dan", "nhu da noi",
        "lam nhu" + a past marker

    Callback-branch contract (fix round, thread A):
    selection reads ONLY the callback clause's addressee span
    (quote-stripped, see _extract_addressee). A name addressee
    binds only on an exact full-name or unique given-name match;
    a non-matching name addressee VETOES (callback_name_mismatch)
    -- the old whole-text token-intersection rule let a shared
    surname ("Nguyễn") bind the wrong person. A family addressee
    binds only on relation evidence (callback_relation_match);
    without it the branch returns a relation_* reason and NEVER
    falls back to the single pool record. A generic addressee
    ("em", "người", "mình") or no addressee keeps the old
    generic flow (topic -> single pool -> single missed).

    Returns (record, reason). record is the bound record dict (for
    user turns, a synthetic {"kind": "user_turn", "phone_number",
    "position"} record), or None. Binding requires EXACTLY ONE
    candidate after name/topic filtering; "a number exists
    somewhere in history" is never enough. No pattern in the
    current text -> (None, "no_reference_pattern").

    NOTE (R4, layer C): binding resolves WHICH instruction or
    record is referred to; it never proves the user wants to
    CONTINUE performing it. A cancellation wrapper around the
    reference ("đừng / khỏi / không cần làm như lúc nãy nữa"),
    a question about it, a recount of it, a quote of it, a
    later history turn revoking it, or a bound instruction
    whose action differs from the proposal's action must all
    refuse an un-fire. That judgement lives in the adapter
    (layer C, lifemate_callback_negation), NOT here: this
    function must stay a pure reference resolver, so its
    reasons keep meaning "this record is the referent" and
    nothing more.

    action (round-7 fix S3, optional "call" / "message"): the
    proposal's action, used ONLY by the prior-instruction
    branch to exclude fully-delegated turns from binding
    candidates. Without it no exclusion applies (old
    behaviour, kept for the contact path and direct callers).
    """
    if not current_text:
        return None, "empty_current_text"
    folded = fold_vietnamese(current_text)
    records = history_records or []

    def log_records():
        return [r for r in records if r.get("tool") in
                CALL_LOG_TOOLS + MESSAGE_LOG_TOOLS]

    def user_turns():
        return [r for r in records if r.get("kind") == "user_turn"]

    def most_recent(cands):
        return max(cands, key=lambda r: r.get("position", -1)) \
            if cands else None

    def name_filter(cands, text):
        """Keep records named in the text. Never falls back: an
        empty result means the text names nobody in the pool
        (reviewer fix R2-A3: the old `kept or cands` fallback
        bound a wrong person when exactly one candidate existed)."""
        return [r for r in cands
                if r.get("name") and _name_matches(r["name"], text)]

    # -- missed caller / callback -------------------------------------
    is_callback = any(p in folded for p in
                      ("goi lai", "nhan lai", "tra loi"))
    is_missed = any(p in folded for p in
                    ("goi nho", "nguoi vua goi", "nguoi vua nhan",
                     "ai goi", "co ai goi"))
    if is_callback or is_missed:
        incoming = [r for r in log_records()
                    if r.get("direction") == "incoming"]
        missed = [r for r in incoming if r.get("status") == "missed"]
        pool = missed or incoming
        if not pool:
            return None, "callback_no_incoming_record"
        # Addressee-first selection (fix round, thread A): only
        # the callback clause's addressee span selects. Names in
        # other clauses, quotes, or message content do not count.
        addr = _extract_addressee(current_text)
        if addr is not None:
            phrase_raw, phrase_folded = addr
            named = [r for r in pool
                     if r.get("name") and _addressee_name_matches(
                         phrase_raw, phrase_folded, r["name"])]
            if len(named) == 1:
                return named[0], "callback_unique_match"
            if len(named) > 1:
                return None, "callback_name_ambiguous"
            kind = _classify_addressee(phrase_raw, phrase_folded)
            if kind == "family":
                return _bind_by_relation(phrase_folded[0],
                                         pool, roster)
            if kind == "name":
                # A name addressee matching NOBODY in the pool:
                # the request selects someone else -- veto, never
                # fall through to the single-pool fallback.
                return None, "callback_name_mismatch"
            # Generic addressee: fall through to the generic flow.
        # Generic flow (no addressee, or a generic addressee):
        # topic / amount disambiguation among the candidates.
        # NOTE: no recency shortcut here: "người vừa gọi" with two
        # missed calls does not identify one of them -- recency
        # alone is not a binding (only the explicit "số mới nhất"
        # + time field in the chat-content path binds by recency).
        selected, sel_reason = _select_by_topic_amount(
            current_text, pool)
        if selected is not None:
            return selected, "callback_" + sel_reason
        if len(pool) == 1:
            return pool[0], "callback_single_incoming"
        if missed and len(missed) == 1:
            return missed[0], "callback_single_missed"
        return None, "callback_multiple_incoming_candidates"

    # -- anaphoric number ("số đó", "số mới nhất") --------------------
    if any(p in folded for p in ("so do", "so nay", "so moi nhat")):
        logs = log_records()
        if not logs:
            # Fall back to chat content records (read_result path):
            # numbers in the messages of the most recent chat read.
            # Several messages share one result position, so all
            # messages of the latest read are considered together.
            chats = [r for r in records
                     if r.get("tool") == "chat_ott.read_chat"
                     and r.get("content")]
            if not chats:
                return None, "anaphoric_no_log_or_chat_record"
            latest_pos = max(r.get("position", -1) for r in chats)
            latest = [r for r in chats
                      if r.get("position") == latest_pos]
            num_to_rec = {}
            for r in latest:
                for m in parse_phone_mentions(r["content"] or ""):
                    if m["role"] not in ("negated", "corrected_away"):
                        num_to_rec.setdefault(m["normalized"], r)
            if len(num_to_rec) == 1:
                num, rec = next(iter(num_to_rec.items()))
                out = dict(rec)
                out["phone_number"] = num
                return out, "anaphoric_chat_content_unique"
            # Several numbers: "số mới nhất" selects the latest
            # message by its time field; otherwise a topic overlap
            # that narrows to one message's numbers selects it.
            # Anything else stays ambiguous -- "a number exists
            # somewhere in the chat" is never enough.
            if "moi nhat" in folded:
                timed = [r for r in latest if r.get("time")]
                if timed:
                    latest_time = max(r["time"] for r in timed)
                    tnums = {}
                    for r in timed:
                        if r["time"] != latest_time:
                            continue
                        for m in parse_phone_mentions(
                                r["content"] or ""):
                            if m["role"] not in (
                                    "negated", "corrected_away"):
                                tnums.setdefault(m["normalized"], r)
                    if len(tnums) == 1:
                        num, rec = next(iter(tnums.items()))
                        out = dict(rec)
                        out["phone_number"] = num
                        return out, "anaphoric_chat_latest_time"
            topic_recs = {}
            for r in latest:
                if _topic_overlap(current_text, r["content"] or "") > 0:
                    for m in parse_phone_mentions(r["content"] or ""):
                        if m["role"] not in (
                                "negated", "corrected_away"):
                            topic_recs.setdefault(m["normalized"], r)
            if len(topic_recs) == 1:
                num, rec = next(iter(topic_recs.items()))
                out = dict(rec)
                out["phone_number"] = num
                return out, "anaphoric_chat_topic_unique"
            return None, "anaphoric_chat_content_ambiguous"
        latest_pos = max(r.get("position", -1) for r in logs)
        latest = [r for r in logs if r.get("position") == latest_pos]
        nums = {r.get("phone_number") for r in latest
                if r.get("phone_number")}
        named = name_filter(latest, current_text)
        if len(named) == 1 and named[0].get("phone_number"):
            return named[0], "anaphoric_named_unique"
        if len(nums) == 1:
            rec = dict(latest[0])
            rec["phone_number"] = next(iter(nums))
            return rec, "anaphoric_latest_unique"
        return None, "anaphoric_multiple_numbers"

    # -- prior instruction ("làm như em dặn lúc nãy") ------------------
    if any(p in folded for p in ("luc nay", "nhu da", "lam nhu",
                                 "theo nhu", "nhu em dan", "nhu anh dan",
                                 "nhu chi dan")):
        turns = []
        for t in user_turns():
            mentions = [m for m in parse_phone_mentions(t.get("text") or "")
                        if m["role"] == "requested_target"]
            if mentions:
                turns.append((t, mentions))
        if not turns:
            return None, "prior_instruction_no_phone_turn"
        # Delegation exclusion (round-7 fix S3): a turn whose
        # queried-action verbs are ALL delegation-governed is
        # another actor's instruction, never the user's own,
        # so it must not bind as a prior instruction. Generic
        # "nho em" is not delegation (same rule as the
        # current-text gate) and still binds. Without an
        # action the caller cannot judge delegation, so the
        # old behaviour stands (no exclusion).
        if action in ("call", "message"):
            live = [(t, m) for (t, m) in turns
                    if not turn_fully_delegated(
                        t.get("text") or "", action)]
            if not live:
                return None, "prior_instruction_all_delegated"
            turns = live
        turn, mentions = turns[-1]
        nums = {m["normalized"] for m in mentions}
        if len(nums) == 1:
            return {"kind": "user_turn", "tool": None,
                    "position": turn.get("position"),
                    "phone_number": next(iter(nums)),
                    "contact_id": None, "name": None,
                    "text": turn.get("text")}, \
                "prior_instruction_unique"
        # Multi-number turn (round-8 fix M1): partition the
        # turn's numbers by governing verb action and
        # require uniqueness WITHIN the proposal action's
        # partition. Only when the proposal action is known;
        # without it the turn stays unbound (safe). NO
        # fallback to earlier turns (latest-turn model,
        # batch-7 NOTE N1): a later turn with a different
        # action/value must not be silently replaced by an
        # earlier one. Single-number turns never reach
        # this branch, so the heuristic cannot affect them;
        # same-verb two numbers ("Nhắn số X và số Y")
        # stay unbound: the turn is genuinely ambiguous
        # about which number the action takes.
        if action in ("call", "message"):
            governed = {norm_phone(d)
                        for d in phone_numbers_for_action(
                            turn.get("text") or "")
                        .get(action, set())}
            cands = nums & governed
            if len(cands) == 1:
                return {"kind": "user_turn", "tool": None,
                        "position": turn.get("position"),
                        "phone_number": next(iter(cands)),
                        "contact_id": None, "name": None,
                        "text": turn.get("text")}, \
                    "prior_instruction_unique"
        return None, "prior_instruction_multiple_numbers"

    return None, "no_reference_pattern"


# ---------------------------------------------------------------------------
# Shared verdict schema
# ---------------------------------------------------------------------------

def _evidence(kind, value, source, producer, field, outcome,
              counterpart, position, claim, status, reason):
    return {
        "kind": kind, "value": value, "source": source,
        "producer": producer, "field": field, "outcome": outcome,
        "counterpart": counterpart, "position": position,
        "claim": claim, "status": status, "reason": reason,
    }


def _verdict(established, basis, sources, b_selected, b_reason):
    if established:
        decision = "PROVEN"
    elif sources:
        decision = "AMBIGUOUS"
    else:
        decision = "UNKNOWN"
    return {
        "established": established,
        "basis": basis,
        "question_a_sources": sources,
        "question_b_target_selected": b_selected,
        "question_b_reason": b_reason,
        "decision": decision,
    }


def _entry_outcome(entry):
    """Normalise a prefix entry's outcome to the shared vocabulary."""
    if isinstance(entry, dict):
        outcome = entry.get("outcome")
        if outcome in ("succeeded", "failed", "schema_rejected", "noop"):
            return outcome
        if entry.get("succeeded") is True:
            return "succeeded"
        if entry.get("succeeded") is False:
            return "failed"
    return "unknown"


def _prefix_records(session_prefix):
    """Split a session prefix into log records + user turns + roster.

    session_prefix entries are dicts; recognised shapes:
      {"tool", "args", "result", "outcome"|"succeeded", "position"}
        -- a prior call (current session or history turn's call);
      {"kind": "user_turn", "text", "position"}
        -- a history user turn's text;
      {"kind": "roster", "contacts": [...]}
        -- handled by the roster argument instead; ignored here.
    Call ARGS are never read as evidence (a proposal's arguments
    prove nothing); only succeeded RESULTS and turn texts are.
    """
    logs = []
    turns = []
    for entry in session_prefix or []:
        if not isinstance(entry, dict):
            continue
        if entry.get("kind") == "user_turn":
            turns.append(entry)
            continue
        tool = entry.get("tool")
        if not tool:
            continue
        if _entry_outcome(entry) != "succeeded":
            continue
        logs.extend(extract_log_records(
            entry.get("result"), tool, entry.get("position", -1)))
    return logs, turns


def _question_b_for_phone(value, current_text, roster, bound):
    """Decide question (b) for a phone value from the current text.

    True  -- the text selects this value (direct mention, roster
             contact name, or a bound reference to it);
    False -- the text selects a DIFFERENT number / correction
             replacing this value, or negates it;
    None  -- the text carries no phone-selection signal at all.
    """
    if not current_text:
        return None, "current_text_not_provided"
    mentions = parse_phone_mentions(current_text)
    for m in mentions:
        if m["normalized"] == value and m["role"] == "negated":
            return False, "value_negated_in_current_text"
        if m["normalized"] == value \
                and m["role"] == "corrected_away":
            return False, "value_corrected_away_in_current_text"
    target_mentions = [m for m in mentions
                       if m["normalized"] == value
                       and m["role"] == "requested_target"]
    if target_mentions:
        # Explicit redirect supersedes (round-8 backstop for
        # S2, extended round 9 to the switch family): a
        # switch verb ("đổi sang" / "đổi thành" / "đổi
        # lại" / "chuyển sang") + a DIFFERENT number after
        # the last target mention re-selects away from this
        # value (last-decisive-wins for selections). A
        # redirect TO the same value confirms it and does
        # not supersede; a target mention after the
        # redirect re-selects it. The run may be any length
        # ("12" counts as "a different number" even though
        # it is not a phone mention). Folding is
        # length-preserving, so folded verb positions
        # compare directly with run spans in raw text.
        folded = fold_vietnamese(current_text)
        last_target_pos = max(m["span"][0]
                              for m in target_mentions)
        for mdoi in re.finditer(
                r"doi\s+sang|doi\s+thanh|doi\s+lai|"
                r"chuyen\s+sang", folded):
            for run in find_digit_runs(current_text):
                rstart = run["span"][0]
                if rstart < mdoi.end():
                    continue
                if rstart - mdoi.end() > 40:
                    break
                rnorm = norm_phone(run["digits"])
                if rnorm and rnorm != value \
                        and rstart > last_target_pos:
                    return False, "explicit_redirect_supersedes"
                break
    for m in mentions:
        if m["normalized"] == value \
                and m["role"] == "requested_target":
            return True, "value_directly_requested"
    if bound is not None and bound.get("phone_number") == value:
        return True, "bound_reference_selects_value"
    # Roster contact named in the current text.
    for contact in roster or []:
        name = contact.get("name")
        if name and norm_phone(contact.get("phone")) == value \
                and _name_matches(name, current_text):
            return True, "roster_contact_named"
    # The text selects a different number for the action.
    for m in mentions:
        if m["role"] == "requested_target":
            return False, "different_number_requested"
    folded = fold_vietnamese(current_text)
    if any(p in folded for p in ("goi lai", "nhan lai", "tra loi",
                                 "so do", "so nay", "so moi nhat",
                                 "luc nay")):
        return None, "reference_present_but_unbound"
    return None, "no_phone_selection_signal"


def phone_evidence_for(value, session_prefix, roster, current_text=None,
                       action=None):
    """Verdict for one phone_number proposal value.

    value: the proposed phone_number (any format; normalised by
      norm_phone, never edited to fit).
    session_prefix: prior-call / history-turn entries (see
      _prefix_records). The CURRENT proposal must not be in the
      prefix; its arguments are never evidence.
    roster: [{id, name, phone}] address-book entries (may be []).
    current_text: the current request text (optional; without it,
      question (b) is None and nothing can be PROVEN).

    Sources are checked in authority order (roster, log fields,
    user text, bound history, read-result content); write echoes
    (phone.call / sms.send results) are skipped explicitly even
    when succeeded.
    """
    target = norm_phone(value)
    sources = []
    basis = None
    if not target:
        return _verdict(False, None, [], None, "empty_value")

    roster = roster or []
    roster_matches = [c for c in roster
                      if norm_phone(c.get("phone")) == target]
    if len(roster_matches) == 1:
        c = roster_matches[0]
        sources.append(_evidence(
            "phone", target, "roster", "contacts", "phone",
            "succeeded", {"contact_id": c.get("id")}, -1,
            "existence", "active", "roster_unique_match"))
    elif len(roster_matches) > 1:
        sources.append(_evidence(
            "phone", target, "roster", "contacts", "phone",
            "succeeded", None, -1, "existence", "ambiguous",
            "roster_multiple_match"))
        # Number existence is separate from contact identity
        # (reviewer fix R2-A2): >=1 roster entry carries this
        # number, so for a NUMBER-target consumer (phone.call /
        # sms.send) the number is established even though WHICH
        # contact it is stays ambiguous. This active evidence must
        # never be read as contact identity (counterpart None,
        # ambiguous identity evidence alongside).
        sources.append(_evidence(
            "phone", target, "roster", "contacts", "phone",
            "succeeded", None, -1, "existence", "active",
            "roster_number_present_multiple_contacts"))

    # Prefix: succeeded log fields first, then read-result content.
    # Write echoes are excluded by construction: only the tools
    # below are read as sources, never phone.call / sms.send.
    logs, turns = _prefix_records(session_prefix)
    history_records = list(logs) + [
        {"kind": "user_turn", "text": t.get("text"),
         "position": t.get("position", -1)} for t in turns]
    for rec in logs:
        if rec["tool"] in CALL_LOG_TOOLS + MESSAGE_LOG_TOOLS \
                and rec.get("phone_number") == target:
            src = "call_log" if rec["tool"] in CALL_LOG_TOOLS \
                else "message_log"
            sources.append(_evidence(
                "phone", target, src, rec["tool"],
                "result.phone_number", "succeeded",
                {"tool": rec["tool"], "position": rec["position"],
                 "record_id": rec.get("record_id"),
                 "contact_id": rec.get("contact_id")},
                rec["position"], "existence", "active",
                "log_phone_number_field"))

    # User text: direct requested target, or tail correction.
    corrected_from = None
    if current_text:
        for m in parse_phone_mentions(current_text):
            if m["normalized"] == target \
                    and m["role"] == "requested_target":
                sources.append(_evidence(
                    "phone", target, "user_text", "user",
                    "current_text", "succeeded", None, -1,
                    "binding", "active", "user_requested_target"))
        corr = parse_tail_correction(current_text)
        if corr:
            hist_numbers = set()
            for t in turns:
                for m in parse_phone_mentions(t.get("text") or ""):
                    hist_numbers.add(m["normalized"])
            for rec in logs:
                if rec.get("phone_number"):
                    hist_numbers.add(rec["phone_number"])
            cands = [n for n in hist_numbers
                     if n.endswith(corr["old_tail"])]
            if len(cands) == 1:
                corrected = apply_tail_correction(cands[0], corr)
                if corrected == target:
                    corrected_from = cands[0]
                    sources.append(_evidence(
                        "phone", target, "user_text", "user",
                        "current_text_tail_correction", "succeeded",
                        {"history_number": cands[0],
                         "old_tail": corr["old_tail"],
                         "new_tail": corr["new_tail"]}, -1,
                        "binding", "active",
                        "tail_correction_of_history_number"))
            elif len(cands) > 1:
                sources.append(_evidence(
                    "phone", target, "user_text", "user",
                    "current_text_tail_correction", "succeeded",
                    None, -1, "binding", "ambiguous",
                    "tail_correction_multiple_history_matches"))

    # Bound history reference (anaphoric / callback / prior turn).
    bound, bind_reason = (None, "no_current_text")
    resolution = None
    if current_text:
        bound, bind_reason = bind_history_reference(
            current_text, history_records, roster=roster,
            action=action)
        if bound is not None and bound.get("phone_number") == target:
            if bound.get("kind") == "user_turn":
                src = "history_text"
            elif bound.get("tool") in CALL_LOG_TOOLS:
                src = "call_log"
            elif bound.get("tool") in MESSAGE_LOG_TOOLS:
                src = "message_log"
            else:
                src = "read_result"
            sources.append(_evidence(
                "phone", target, src,
                bound.get("tool") or "user",
                "bound_history_record", "succeeded",
                {"tool": bound.get("tool"),
                 "position": bound.get("position"),
                 "record_id": bound.get("record_id"),
                 "contact_id": bound.get("contact_id")},
                bound.get("position", -1), "binding", "active",
                "bound_reference:" + bind_reason))

    # Instruction-turn name resolution (round-4 fix M3): the
    # current text names a person ("Gọi cho Vy nhé") and the
    # instruction turns map that name to exactly one number
    # with a matching action. Guards: the name must map to a
    # single number (== target) across ALL instruction turns,
    # and the current action must match the instruction action.
    # Competition is judged in the name -> phone direction
    # only: another name mapping to the same number does not
    # make a specific name request ambiguous. Family / generic
    # addressees never resolve here. Revocation of the mapping
    # instruction is checked by the adapter (layer C), not here.
    if current_text:
        curr_addr = _instruction_addressee(current_text)
        curr_action = _instruction_turn_action(current_text)
        if curr_addr is not None and curr_action is not None:
            name_map = _instruction_name_map(turns)
            cands = []
            for key, entries in name_map.items():
                if key == curr_addr or (
                        len(curr_addr.split()) == 1
                        and key.split()[-1] == curr_addr) or (
                        len(key.split()) == 1
                        and curr_addr.split()[-1] == key):
                    cands.extend(entries)
            phones = {p for (p, _pos, _act) in cands}
            if len(phones) == 1 and target in phones:
                matched = [e for e in cands
                           if e[0] == target
                           and e[2] == curr_action]
                if matched:
                    resolution = max(matched,
                                     key=lambda e: e[1])
        if resolution is not None:
            _rphone, _rpos, _raction = resolution
            sources.append(_evidence(
                "phone", target, "history_text", "user",
                "instruction_name_resolution", "succeeded",
                {"position": _rpos, "name": curr_addr},
                _rpos, "binding", "active",
                "instruction_name_resolution"))

    # Read-result content numbers (chat messages etc.), selected
    # only when the current text anaphorically selects them or the
    # number is the unique content number of the latest read.
    if current_text:
        folded = fold_vietnamese(current_text)
        anaphoric = any(p in folded for p in
                        ("so do", "so nay", "so moi nhat"))
        for rec in logs:
            if rec["tool"] not in READ_RESULT_CONTENT_TOOLS:
                continue
            content = rec.get("content")
            if not content:
                continue
            content_numbers = set()
            for m in parse_phone_mentions(content):
                if m["role"] in ("requested_target", "background"):
                    content_numbers.add(m["normalized"])
            for run in find_digit_runs(content):
                if classify_phone_context(content, run)["classification"] \
                        == "phone":
                    content_numbers.add(norm_phone(run["digits"]))
            content_numbers.discard("")
            if target in content_numbers and (anaphoric
                                              or len(content_numbers) == 1):
                sources.append(_evidence(
                    "phone", target, "read_result", rec["tool"],
                    "result.messages[].content", "succeeded",
                    {"tool": rec["tool"], "position": rec["position"],
                     "record_id": rec.get("record_id")},
                    rec["position"], "existence", "active",
                    "observed_in_read_content"))

    valid = [s for s in sources if s["status"] == "active"]
    b_selected, b_reason = _question_b_for_phone(
        target, current_text, roster, bound)
    if corrected_from is not None and b_selected is None:
        b_selected, b_reason = True, "tail_correction_selects_value"
    if resolution is not None and b_selected is None:
        b_selected, b_reason = True, \
            "instruction_name_resolution_selects_value"
    if valid and b_selected is True:
        # "source" when establishment does not depend on binding:
        # roster, log, read-result, or a direct user-text target.
        # "binding" only when it rests on a bound history
        # reference or a tail correction.
        direct = any(
            s["status"] == "active" and (
                s["source"] in ("roster", "call_log", "message_log",
                                "read_result")
                or (s["source"] == "user_text"
                    and s["reason"] == "user_requested_target"))
            for s in valid)
        basis = "source" if direct else "binding"
        return _verdict(True, basis, sources, b_selected, b_reason)
    if valid and b_selected is False:
        return _verdict(False, None, sources, b_selected, b_reason)
    # (b) undetermined: sources exist but selection is not shown.
    return _verdict(False, None, sources, b_selected, b_reason)


def callback_reference_for(call_args, session_prefix, roster=None,
                           current_text=None, consumer_tool=None):
    """Verdict for one contact reference in a call's arguments.

    call_args: the proposal's arguments (contact_id / contact_name /
      to / phone_number). The proposal's own values are the
      QUESTION, never evidence.
    consumer_tool: the tool consuming the reference (e.g.
      "phone.call", "contacts.update"). It decides whether roster
      membership is required: phone/sms/ewallet never validate a
      contact, contacts writes are patch-verified. Unknown
      consumers are reported as unknown, never assumed.

    The verdict distinguishes three facts, and never conflates them:
      - roster_member: the id/name/phone is in the address book
        (contacts.contacts records from a search/get also count);
      - observed_counterpart: the id/phone appears in a SUCCEEDED
        call/message log record (sufficient for execution by a
        non-validating consumer, but NOT roster membership);
      - consumer_accepted: whether the consumer's implementation
        accepts the reference (validation rules above).
    A contact_id found only in free text or as another registry's
    foreign key is never a source for any of the three.
    """
    args = call_args or {}
    ref_id = args.get("contact_id")
    ref_name = args.get("contact_name")
    to = args.get("to")
    if not ref_id and isinstance(to, str) and to and "@" not in to:
        if to.startswith("c_"):
            ref_id = to
        else:
            ref_name = to
    ref_phone = norm_phone(args.get("phone_number"))
    roster = roster or []
    logs, _turns = _prefix_records(session_prefix)

    sources = []
    roster_member = False
    observed = False
    if ref_id:
        if any(str(c.get("id")) == str(ref_id) for c in roster):
            roster_member = True
            sources.append(_evidence(
                "contact", str(ref_id), "roster", "contacts", "id",
                "succeeded", {"contact_id": ref_id}, -1,
                "existence", "active", "roster_id_match"))
        for rec in logs:
            if rec["tool"] in CALL_LOG_TOOLS + MESSAGE_LOG_TOOLS \
                    and rec.get("contact_id") == ref_id:
                observed = True
                sources.append(_evidence(
                    "contact", str(ref_id),
                    "call_log" if rec["tool"] in CALL_LOG_TOOLS
                    else "message_log", rec["tool"],
                    "result.contact_id", "succeeded",
                    {"tool": rec["tool"], "position": rec["position"],
                     "record_id": rec.get("record_id")},
                    rec["position"], "binding", "active",
                    "observed_log_counterpart"))
            if rec["tool"] in ("contacts.search", "contacts.get") \
                    and rec.get("contact_id") == ref_id:
                roster_member = True
                sources.append(_evidence(
                    "contact", str(ref_id), "roster", rec["tool"],
                    "result.id", "succeeded",
                    {"tool": rec["tool"], "position": rec["position"]},
                    rec["position"], "existence", "active",
                    "contacts_record"))
    if ref_name:
        folded_name = fold_vietnamese(ref_name)
        matches = [c for c in roster
                   if c.get("name")
                   and fold_vietnamese(c["name"]) == folded_name]
        if len(matches) == 1:
            roster_member = True
            sources.append(_evidence(
                "contact", fold_vietnamese(ref_name), "roster",
                "contacts", "name", "succeeded",
                {"contact_id": matches[0].get("id")}, -1,
                "existence", "active", "roster_name_unique_match"))
        elif len(matches) > 1:
            sources.append(_evidence(
                "contact", fold_vietnamese(ref_name), "roster",
                "contacts", "name", "succeeded", None, -1,
                "existence", "ambiguous", "roster_name_multiple_match"))
    if ref_phone:
        phone_matches = [c for c in roster
                         if norm_phone(c.get("phone")) == ref_phone]
        if len(phone_matches) == 1:
            roster_member = True
            sources.append(_evidence(
                "contact", ref_phone, "roster", "contacts", "phone",
                "succeeded", None, -1, "existence", "active",
                "roster_phone_match"))
        elif len(phone_matches) > 1:
            # Number present, identity ambiguous: never claim
            # roster membership for a shared number (R2-A2).
            sources.append(_evidence(
                "contact", ref_phone, "roster", "contacts", "phone",
                "succeeded", None, -1, "existence", "ambiguous",
                "roster_phone_multiple_match"))
        for rec in logs:
            if rec["tool"] in CALL_LOG_TOOLS + MESSAGE_LOG_TOOLS \
                    and rec.get("phone_number") == ref_phone:
                observed = True
                sources.append(_evidence(
                    "contact", ref_phone,
                    "call_log" if rec["tool"] in CALL_LOG_TOOLS
                    else "message_log", rec["tool"],
                    "result.phone_number", "succeeded",
                    {"tool": rec["tool"], "position": rec["position"],
                     "record_id": rec.get("record_id")},
                    rec["position"], "binding", "active",
                    "observed_log_counterpart"))

    requires = CONSUMER_REQUIRES_MEMBERSHIP.get(consumer_tool) \
        if consumer_tool else None
    if consumer_tool is None:
        consumer_note = "consumer_unknown"
    elif requires is True:
        consumer_note = "consumer_requires_membership"
    else:
        consumer_note = "consumer_no_membership_validation"

    # Question (b): does the current text select this counterpart?
    b_selected, b_reason = None, "current_text_not_provided"
    if current_text:
        folded = fold_vietnamese(current_text)
        if ref_name and fold_vietnamese(ref_name) in folded:
            b_selected, b_reason = True, "counterpart_named"
        elif ref_phone:
            b_sel, b_r = _question_b_for_phone(
                ref_phone, current_text, roster, None)
            b_selected, b_reason = b_sel, b_r
        elif ref_id:
            history_records = list(logs)
            bound, bind_reason = bind_history_reference(
                current_text, history_records, roster=roster)
            if bound is not None \
                    and bound.get("contact_id") == ref_id:
                b_selected, b_reason = True, \
                    "bound_reference_selects_counterpart"
            elif bind_reason in (
                    "callback_name_mismatch",
                    "callback_name_ambiguous",
                    "callback_relation_unproven",
                    "callback_relation_conflict",
                    "callback_relation_ambiguous",
                    "callback_relation_selects_other"):
                # Explicit addressee/relation mismatch: the
                # request selects someone else (or an unproven
                # relation). Topic/roster fallbacks must NOT
                # override it -- a topic word does not rescue a
                # contradicted addressee (fix round, thread A).
                b_selected, b_reason = None, bind_reason
            else:
                # The text may name the roster contact directly
                # ("Cập nhật số cho An" where An's id is ref_id).
                named_contact = next(
                    (c for c in roster
                     if str(c.get("id")) == str(ref_id)
                     and c.get("name")), None)
                if named_contact and _name_matches(
                        named_contact["name"], current_text):
                    b_selected, b_reason = True, "roster_contact_named"
                else:
                    # Topic / amount selection among incoming log
                    # records: if the uniquely selected record's
                    # contact_id equals ref_id, the text selects
                    # this counterpart (e.g. "hoàn lại hai trăm
                    # nghìn cho Emily" selects the message whose
                    # content carries that amount / name).
                    incoming = [r for r in logs
                                if r.get("direction") == "incoming"]
                    selected, _sel = _select_by_topic_amount(
                        current_text, incoming or logs)
                    if selected is not None \
                            and selected.get("contact_id") == ref_id:
                        b_selected, b_reason = True, \
                            "topic_amount_selects_counterpart"
                    elif any(p in folded for p in
                             ("goi lai", "nhan lai", "tra loi")):
                        b_selected, b_reason = None, \
                            "callback_reference_unbound"
                    else:
                        b_selected, b_reason = None, \
                            "no_counterpart_selection_signal"

    valid = [s for s in sources if s["status"] == "active"]
    if not valid:
        return _verdict(False, None, sources, b_selected,
                        b_reason + ";" + consumer_note)
    if requires is True and not roster_member:
        # Observed counterpart alone does not satisfy a consumer
        # that requires membership: report AMBIGUOUS with both
        # facts visible, never PROVEN.
        return _verdict(False, None, sources, b_selected,
                        "observed_counterpart_not_roster_membership;"
                        + consumer_note)
    if requires is None:
        # Consumer acceptance is unknown: binding may be shown,
        # but acceptance cannot be claimed. Cap at AMBIGUOUS.
        return _verdict(False, None, sources, b_selected,
                        b_reason + ";" + consumer_note)
    if b_selected is True:
        basis = "source" if roster_member else "binding"
        return _verdict(True, basis, sources, b_selected,
                        b_reason + ";" + consumer_note)
    return _verdict(False, None, sources, b_selected,
                    b_reason + ";" + consumer_note)
