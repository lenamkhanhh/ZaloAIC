#!/usr/bin/env python3
"""Callback action-selection analysis (negation / correction gate).

Standalone module for the G&G callback fix round (thread B).
Stdlib only. It does NOT import gates, provenance, or the
phone_callback_evidence module; every small matching helper below
is written inline, with a comment stating what it does and why.

FIXED INTERFACE (the coordinator wires this into the adapter
verbatim; do not rename the function, its parameters, or the
return keys):

    analyze_action_selection(text, target_names=(), target_phones=(),
                             action="call")
        -> {"selection": "positive"|"negated"|"replaced"|"cancelled"
                         |"unknown",
            "reason": str,               # short machine-readable code
            "mention_present": bool}     # target named anywhere, quotes
                                         # included

    action="call"    covers goi / dien (call, call back).
    action="message" covers nhan / gui tin nhan / sms (message back).
    action="any"     covers both. A negation of a DIFFERENT action
                     never blocks the action under test.

VETO-GATE CONTRACT (read before using the result):
  "positive" here means "no veto found and the queried action is
  invoked positively" -- it is NOT proof that the target is the
  selected counterpart. Binding (who the request selects) belongs
  to the callback module (thread A). The adapter must un-fire
  only when thread A proves binding AND this module returns
  "positive". Every other selection ("negated", "replaced",
  "cancelled", "unknown") makes the adapter REFUSE to un-fire:
  that is the safe direction.

  In particular, a positive verb for ANOTHER person ("goi lai cho
  An") with no veto against the target still yields "positive"
  for the target: the veto gate answers "is the action toward
  this target negated/replaced/cancelled?", not "is this target
  the one chosen?". Short-name resolution (bare "An" vs full
  "Nguyen An") is thread A's job: this module matches ONLY the
  name forms it is given, so a bare-short-name negation is
  invisible here when only the full form is passed.

RULES IMPLEMENTED (numbered as in the task):
  1. Quoted spans ("...", '...', "...", '...') are stripped
     before selection scanning: a name mentioned only inside a
     quote is message content, not a selection. Such a mention
     still sets mention_present=True, but selection="unknown".
  2. Clause-scoped: clauses split on punctuation and on "nhung"
     (but). A negation binds only to the (action, target) pair
     in its own clause.
  3. Action negation needs a marker adjacent to a callback verb
     (particles co/can/lai/phai may sit between): dung / cho /
     khoi / khong (+ verb), khong can (+ verb), khong phai (+
     verb). A "khong" elsewhere is NOT an action negation:
     question tails ("co ... khong"), message content, or a
     lone "khong" not governing a verb.
  4. Correction: "a khong" / "y la" after a positive selection,
     followed by a different named/phone target -> "replaced";
     followed by no new target -> "cancelled". The LAST
     decision wins ("dung goi An, goi lai cho Vy" -> Vy
     positive; "goi lai cho Vy, a khong, goi cho An" -> Vy
     replaced). "khong phai <target> ma (la) <new>" -> replaced;
     "khong phai <target>" with no "ma" and no verb -> negated
     (explicit exclusion).
  5. Action scoping: "khong can nhan, chi goi lai cho Vy" is
     negated for action="message" but positive for action="call";
     "dung nhan cho Vy" yields "unknown" for call, never
     "negated" (a message veto is not a call veto at the
     selection level) -- but the ADAPTER treats that unknown
     as a veto for callback proposals (reason
     "other_action_verb_only"): the queried action was never
     selected, so a cross-action binding must not un-fire.
  6. Value correction is NOT target replacement: "duoi la sau
     tam chu khong phai tam sau" affirms the new tail and
     negates the old tail value. For target_phones = the
     CORRECTED number the selection stays positive; for the OLD
     number it becomes "replaced" (the number was corrected away).
  7. Uncertain -> "unknown", never a guessed semantic. The
     fallback SPLITS the old single "no_action_evidence" into
     machine-distinguishable reasons, because the adapter must
     treat them differently (coordinator delta-2 fix):
     "no_callback_verb" (no verb head of any action in the
     text -- the adapter abstains, so a history-grounded
     binding stands); "blocked_verb_only" (question mood
     "co nen goi lai cho Vy khong", past "da goi", "chua" +
     verb -- a blocked verb is not a request, and the adapter
     vetoes for callback proposals); "other_action_verb_only"
     (only verbs of another action -- the adapter vetoes for
     callback proposals); "negated_other_object" (a negated verb
     of the queried action aimed at someone else -- the adapter
     vetoes for callback proposals); "quoted_mention_only"
     (mention only inside quotes -- the adapter vetoes for
     callback proposals). "tra loi" (reply) is a message verb:
     "tra loi Vy" is positive for action="message" and
     "other_action_verb_only" for action="call".

LIMITATIONS (honest, not bugs to paper over):
  - Past-tense statements ("hom qua khong co goi cho Vy") are not
    modelled: "khong co" is not treated as a negation marker, so
    the verb reads positive. Thread A is expected not to bind a
    callback from a past-tense statement.
  - Interrogatives other than the narrow "co (nen) <verb> ...
    khong" frame are not modelled; a question containing a
    callback phrase reads positive (veto gate only blocks
    explicit negation/correction).
  - Single "tu" for digit 4, compound spoken amounts, and
    space-separated digit strings shorter than a full number are
    out of scope (same BLOCKED list as the phone module).
  - A bare new target after a correction marker without a verb
    ("goi cho Vy, a khong, An") yields "cancelled", not
    "replaced": both refuse un-fire, so the gate outcome is the
    same; only the reported reason differs.
"""

import re
import unicodedata

__all__ = ["analyze_action_selection"]


# ---------------------------------------------------------------- helpers

def _nfc(text):
    # Normalise to composed form so one Vietnamese letter is one
    # code point (matters for the diacritic-sensitive name match).
    return unicodedata.normalize("NFC", text or "")


def _fold(text):
    # Diacritic-stripped, case-folded form, used for verbs,
    # markers, particles and multi-token names. "d" needs a manual
    # map: NFD does not decompose it.
    decomposed = unicodedata.normalize("NFD", text or "")
    stripped = "".join(
        ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return stripped.replace("đ", "d").replace("Đ", "D").casefold()


# Vietnamese digit words (folded forms). "tu" for 4 is NOT included:
# same BLOCKED list as the phone module -- only the 10 standard words.
_DIGIT_WORDS = {
    "khong": "0", "mot": "1", "hai": "2", "ba": "3", "bon": "4",
    "nam": "5", "sau": "6", "bay": "7", "tam": "8", "chin": "9",
}

# Callback verb patterns, as folded token lists. "lai" may appear
# inside/after a pattern ("goi lai", "nhan lai tin") and is skipped
# while matching, because for action scoping "goi" and "goi lai"
# are the same action.
_VERB_PATTERNS = {
    "call": [["goi"], ["dien"], ["goi", "dien"]],
    "message": [["nhan"], ["nhan", "tin"], ["gui", "tin", "nhan"],
                ["gui", "sms"], ["sms"], ["tra", "loi"]],
}

# Negation markers, matched on ORIGINAL tokens (casefolded, WITH
# diacritics): folded matching would confuse "cho" (preposition
# "for") with "chớ" (the negation marker), both folding to "cho".
_NEG_MARKERS = {"đừng", "chớ", "khỏi", "không"}
# Particles allowed between a marker and its verb.
_PARTICLES = {"có", "cần", "lại", "phải", "là"}
# "chưa" + verb is a status ("not yet"), not a request and not a
# veto: it blocks a positive reading without creating a negation.
_BLOCKER = "chưa"

# First object token (folded) that marks a generic, not a person:
# "nguoi vua goi", "so do", "so nay", bare "do/day/nay/ai".
_GENERIC_OBJECT_HEADS = {"nguoi", "so", "do", "day", "nay", "ai"}
# Object-scan stopwords (folded): clause glue, politeness
# particles, and words that start a new phrase, not a name.
_OBJECT_STOPS = {
    "nua", "di", "nhe", "nha", "giup", "dum", "ho", "voi", "a",
    "oi", "ma", "de", "la", "thi", "ne", "ak",
}
# Tokens that start a callback verb (folded), used to stop an
# object scan at the next verb instead of swallowing it.
_VERB_HEADS = {"goi", "dien", "nhan", "gui", "sms"}
# Clause phone context (folded): a spoken digit run only counts
# as a phone mention when its clause carries one of these, unless
# the run is long (>= 7 digits, i.e. near-full number).
_PHONE_CONTEXT = {"so", "duoi", "may", "hotline", "thoai"}
# Correction markers (folded token sequences).
_CORRECTION_MARKERS = [["a", "khong"], ["y", "la"]]

_WORD_RE = re.compile(r"[^\W_]+|[,.!?;:]", re.UNICODE)
_QUOTE_RE = re.compile(r'"[^"]*"|“[^”]*”|‘[^’]*’|\'[^\']*\'')


def _norm_phone(value):
    # Digits only; +84/84 folded to a leading 0. Same rule as the
    # gates module's _norm_phone: never add, drop, or edit digits.
    digits = re.sub(r"\D", "", value or "")
    if len(digits) >= 11 and digits.startswith("84"):
        digits = "0" + digits[2:]
    return digits


def _strip_quoted(text):
    # Rule 1: quoted spans are message content, not selection.
    # Replace each span with a single space (keeps word separation).
    return _QUOTE_RE.sub(" ", text)


def _tokenize(text):
    """Split text into word tokens with clause ids.

    Returns (raws, folds, clause_ids): raw words are NFC + casefold
    for diacritic-sensitive matching; folds are diacritic-stripped.
    A new clause starts after punctuation and after "nhung".
    """
    raws, folds, clause_ids = [], [], []
    clause = 0
    for match in _WORD_RE.finditer(text):
        tok = match.group(0)
        if tok in ",.!?;:":
            clause += 1
            continue
        raws.append(tok.casefold())
        folds.append(_fold(tok))
        clause_ids.append(clause)
        if folds[-1] == "nhung":
            clause += 1
    return raws, folds, clause_ids


def _clause_bounds(clause_ids):
    """Map clause id -> (first word index, last word index)."""
    bounds = {}
    for idx, cid in enumerate(clause_ids):
        if cid not in bounds:
            bounds[cid] = [idx, idx]
        else:
            bounds[cid][1] = idx
    return bounds


def _find_verbs(folds, actions):
    """Greedy longest-match verb scan for the queried actions.

    At each position the longest pattern wins ("goi dien" beats
    "goi"); "lai" tokens are skipped inside a pattern and one
    trailing "lai" is absorbed into the span.
    Returns [{start, end, action}] with end exclusive.
    """
    patterns = []
    for action in actions:
        for pat in _VERB_PATTERNS[action]:
            patterns.append((pat, action))
    # Longest first so "goi dien" wins over "goi" at the same start.
    patterns.sort(key=lambda p: -len(p[0]))
    verbs = []
    i = 0
    n = len(folds)
    while i < n:
        matched = None
        for pat, action in patterns:
            j = i
            ok = True
            for p_tok in pat:
                while j < n and folds[j] == "lai":
                    j += 1
                if j >= n or folds[j] != p_tok:
                    ok = False
                    break
                j += 1
            if ok:
                while j < n and folds[j] == "lai":
                    j += 1
                matched = (j, action)
                break
        if matched is not None:
            verbs.append({"start": i, "end": matched[0],
                          "action": matched[1]})
            i = matched[0]
        else:
            i += 1
    return verbs


def _verb_polarity(verb, raws, folds, clause_ids, bounds):
    """Negated / blocked / positive for one verb occurrence.

    Look back inside the same clause, skipping particles, for a
    negation marker (negated), for "chua" (blocked), or for a
    question-mood clause "co (nen) <verb> ... khong" (blocked).
    Anything else is positive: a trailing "khong" (question tail,
    message content) never negates, because polarity is decided
    only by what PRECEDES the verb.
    """
    cid = clause_ids[verb["start"]]
    first, last = bounds[cid]
    # Question mood: the clause opens with "co" and closes with
    # "khong" ("co goi lai cho Vy khong", "co nen goi ... khong").
    # A purpose tail ("... de hoi xem co ranh khong") does NOT
    # trigger this: its clause opens with the verb, not "co".
    if last > first and raws[first] == "có" and raws[last] == "không":
        return "blocked"
    # Past markers: a verb immediately preceded (same clause)
    # by "vua" / "da" / "moi" reports a past action, not a
    # request ("nguoi vua goi", "Vy vua goi", "da goi cho Vy").
    # The correlative "vua ... vua ..." ("vua goi vua nhan" =
    # both calling and messaging) is NOT past: a clause with
    # two or more "vua" tokens exempts "vua" from this rule.
    prev = verb["start"] - 1
    if prev >= first:
        prev_fold = folds[prev]
        if prev_fold in ("da", "moi"):
            return "blocked"
        if prev_fold == "vua" and sum(
                1 for k in range(first, last + 1)
                if folds[k] == "vua") < 2:
            return "blocked"
    k = verb["start"] - 1
    steps = 0
    while k >= first and steps < 3 and raws[k] in _PARTICLES:
        k -= 1
        steps += 1
    if k >= first and raws[k] in _NEG_MARKERS:
        return "negated"
    if k >= first and raws[k] == _BLOCKER:
        return "blocked"
    return "positive"


def _extract_object(verb, raws, folds, clause_ids, bounds):
    """Object span after a verb: (start, end) word indices.

    Skips "lai" (and "thoai" after "dien", the noun half of
    "dien thoai"), then the prepositions cho/toi/den. Stops at a
    clause end, an object stopword, or the next verb head. Empty
    span means the verb has no object (generic callback).
    """
    cid = clause_ids[verb["start"]]
    _first, last = bounds[cid]
    j = verb["end"]
    while j <= last and folds[j] == "lai":
        j += 1
    if verb["start"] < len(folds) and folds[verb["start"]] == "dien":
        while j <= last and folds[j] == "thoai":
            j += 1
    while j <= last and folds[j] in ("cho", "toi", "den"):
        j += 1
    start = j
    while j <= last and (j - start) < 3:
        if folds[j] in _OBJECT_STOPS or folds[j] in _VERB_HEADS:
            break
        j += 1
    return (start, j)


def _classify_object(span, folds, target_spans):
    """general | specific | target for an object span."""
    start, end = span
    if start >= end:
        return "general"
    for (ms, me) in target_spans:
        if ms < end and start < me:
            return "target"
    if folds[start] in _GENERIC_OBJECT_HEADS:
        return "general"
    return "specific"


def _find_name_mentions(raws, folds, target_names):
    """Target-name mentions: (start, end) word spans.

    Single-token names match diacritic-SENSITIVELY on raw tokens
    ("An" never matches "an" with a different diacritic, e.g.
    "an" as in "an com" is a different word shape only when the
    diacritic differs -- "An" vs "ăn" do NOT match). Multi-token
    names match the full phrase only: folded tokens in order,
    consecutive. Token intersection is NEVER a match (this is
    the R1 fix: "Nguyen An" must not match "Nguyen Binh" via the
    shared "Nguyen").
    """
    mentions = []
    for name in target_names:
        parts = _nfc(name).split()
        if not parts:
            continue
        if len(parts) == 1:
            wanted = parts[0].casefold()
            for i, raw in enumerate(raws):
                if raw == wanted:
                    mentions.append((i, i + 1))
        else:
            folded_parts = [_fold(p) for p in parts]
            width = len(folded_parts)
            for i in range(0, len(folds) - width + 1):
                if folds[i:i + width] == folded_parts:
                    mentions.append((i, i + width))
    return mentions


def _digit_runs(raws, folds, clause_ids):
    """All digit runs: (start, end, digits, kind) for digit tokens
    and spoken digit-word runs. kind is "digits" for typed runs
    (joined across spaces, e.g. "0902 418 0240") and "spoken"
    for digit-word runs of >= 2 words. Callers decide which runs
    count as phone mentions; this helper only enumerates runs."""
    runs = []
    i = 0
    n = len(raws)
    while i < n:
        if raws[i].isdigit():
            j = i
            digits = ""
            while j < n and raws[j].isdigit() \
                    and clause_ids[j] == clause_ids[i]:
                digits += raws[j]
                j += 1
            runs.append((i, j, digits, "digits"))
            i = j
        elif folds[i] in _DIGIT_WORDS:
            j = i
            digits = ""
            while j < n and folds[j] in _DIGIT_WORDS \
                    and clause_ids[j] == clause_ids[i]:
                digits += _DIGIT_WORDS[folds[j]]
                j += 1
            if j - i >= 2:
                runs.append((i, j, digits, "spoken"))
            i = j
        else:
            i += 1
    return runs


def _find_phone_mentions(raws, folds, clause_ids, bounds,
                         target_phones):
    """Phone mentions of the given targets: (start, end, digits).

    Digit runs match on full equality after normalisation.
    Spoken runs match on equality or on being a tail (suffix) of
    the target -- the correction context ("duoi la ...") talks
    about tails -- and only when the clause carries phone context
    ("so", "duoi", "may", "hotline", "thoai") or the run is long
    (>= 7 digits). The context rule blocks false runs such as
    "nam sau" (next year) parsing as the digits 56.
    """
    if not target_phones:
        return []
    targets = {_norm_phone(p) for p in target_phones}
    targets = {t for t in targets if t}
    if not targets:
        return []
    mentions = []
    for (s, e, digits, kind) in _digit_runs(raws, folds, clause_ids):
        if kind == "digits":
            if len(digits) >= 9 and _norm_phone(digits) in targets:
                mentions.append((s, e, _norm_phone(digits)))
        else:
            cid = clause_ids[s]
            first, last = bounds[cid]
            context = any(folds[k] in _PHONE_CONTEXT
                          for k in range(first, last + 1))
            if context or len(digits) >= 7:
                for t in targets:
                    if digits == t or t.endswith(digits):
                        mentions.append((s, e, digits))
                        break
    return mentions


def _find_correction_markers(folds):
    """Positions (word index of the first token) of "a khong"
    and "y la" markers."""
    positions = []
    for marker in _CORRECTION_MARKERS:
        width = len(marker)
        for i in range(0, len(folds) - width + 1):
            if folds[i:i + width] == marker:
                positions.append(i)
    return sorted(positions)


def _khong_phai_positions(raws):
    """Word indices of "khong" immediately followed by "phai"."""
    return [i for i in range(len(raws) - 1)
            if raws[i] == "không" and raws[i + 1] == "phải"]


# ---------------------------------------------------------------- main

def analyze_action_selection(text, target_names=(), target_phones=(),
                             action="call"):
    """Judge the action selection toward the target in `text`.

    See the module docstring for the fixed interface and the
    veto-gate contract. Returns {"selection", "reason",
    "mention_present"}.
    """
    if action not in ("call", "message", "any"):
        return {"selection": "unknown", "reason": "invalid_action",
                "mention_present": False}
    actions = ("call", "message") if action == "any" else (action,)
    targets_norm = [_norm_phone(p) for p in (target_phones or ())]
    targets_norm = [t for t in targets_norm if t]

    # mention_present counts quotes too (rule 1): run mention
    # detection on the FULL text, quotes included.
    full_raws, full_folds, _full_cids = _tokenize(_nfc(text))
    full_names = _find_name_mentions(full_raws, full_folds,
                                     target_names or ())
    _full_bounds = _clause_bounds(_full_cids) if _full_cids else {}
    full_phones = _find_phone_mentions(
        full_raws, full_folds, _full_cids, _full_bounds,
        targets_norm) if targets_norm else []
    mention_present = bool(full_names or full_phones)

    # Selection scanning works on the quote-stripped text.
    clean = _strip_quoted(_nfc(text))
    raws, folds, clause_ids = _tokenize(clean)
    if not raws:
        if mention_present:
            return {"selection": "unknown",
                    "reason": "quoted_mention_only",
                    "mention_present": True}
        return {"selection": "unknown", "reason": "no_action_evidence",
                "mention_present": False}
    bounds = _clause_bounds(clause_ids)

    name_mentions = _find_name_mentions(raws, folds,
                                        target_names or ())
    phone_mentions = _find_phone_mentions(
        raws, folds, clause_ids, bounds, targets_norm) \
        if targets_norm else []
    # Unified target mentions: (start, end, kind).
    mentions = ([(s, e, "name") for (s, e) in name_mentions]
                + [(s, e, "phone") for (s, e, _d) in phone_mentions])
    mention_spans = [(s, e) for (s, e, _k) in mentions]

    verbs = _find_verbs(folds, actions)
    # Polarity + object classification per verb occurrence.
    verb_info = []
    for verb in verbs:
        polarity = _verb_polarity(verb, raws, folds, clause_ids,
                                  bounds)
        span = _extract_object(verb, raws, folds, clause_ids, bounds)
        kind = _classify_object(span, folds, mention_spans)
        verb_info.append({**verb, "polarity": polarity,
                          "object_span": span, "object_kind": kind})

    # --- target-specific mention events: the nearest preceding
    # same-clause verb of the queried action governs the mention.
    # (start, kind, reason) with kind in positive/negated.
    events = []
    for (ms, me, _kind) in mentions:
        cid = clause_ids[ms]
        governing = None
        for info in verb_info:
            if clause_ids[info["start"]] == cid \
                    and info["start"] < ms:
                if governing is None \
                        or info["start"] > governing["start"]:
                    governing = info
        if governing is None or governing["polarity"] == "blocked":
            continue
        if governing["polarity"] == "negated":
            events.append((ms, "negated", "negated_selection"))
        else:
            events.append((ms, "positive", "positive_selection"))

    # --- general events: object-less / generic-object verbs.
    general_events = []
    for info in verb_info:
        if info["polarity"] == "blocked":
            continue
        if info["object_kind"] == "general":
            general_events.append(
                (info["start"],
                 "negated" if info["polarity"] == "negated"
                 else "positive"))

    # --- "khong phai" constructions (rule 4 + rule 6 for names).
    for kp in _khong_phai_positions(raws):
        # Case A: "khong phai <verb>" is verb negation, already
        # handled by _verb_polarity (phai is a particle). Skip.
        after = kp + 2
        if after < len(raws) and folds[after] in _VERB_HEADS:
            continue
        # Case B: "khong phai <target> ma (la) <new>" -> replaced.
        # NAME mentions only: a phone run after "khong phai" is
        # a VALUE correction (rule 6), handled by the digit-run
        # scan below -- it must never trigger the name
        # exclusion/replacement logic (that was a real bug: the
        # old tail "tam sau" was read as an excluded name).
        target_here = None
        for (ms, me, mkind) in mentions:
            if mkind != "name":
                continue
            if ms == after or (after < ms <= after + 1):
                target_here = (ms, me)
                break
        if target_here is not None:
            ms, me = target_here
            cid = clause_ids[ms]
            first, last = bounds[cid]
            ma_pos = None
            for k in range(me, last + 1):
                if raws[k] == "mà":
                    ma_pos = k
                    break
                if folds[k] in _VERB_HEADS:
                    break
            if ma_pos is not None:
                # Object after "ma" (+ optional "la"): a new
                # target if it is a name/phone mention that is
                # NOT this target, or any name-ish span.
                j = ma_pos + 1
                while j <= last and raws[j] == "là":
                    j += 1
                new_target = False
                if j <= last:
                    for (ns, ne, _k) in mentions:
                        if ns == j and (ns, ne) != (ms, me):
                            new_target = True
                    if not new_target and folds[j] not in _OBJECT_STOPS:
                        new_target = True
                if new_target:
                    events.append((ma_pos, "replaced",
                                   "replaced_by_new_target"))
                continue
            # Case C: "khong phai <target>" with no "ma" and no
            # verb after it in the clause -> explicit exclusion.
            # (Name mentions only, as in case B.)
            has_verb_after = any(
                clause_ids[v["start"]] == cid
                and v["start"] > me for v in verbs)
            if not has_verb_after:
                events.append((ms, "negated",
                               "negated_explicit_exclusion"))
        # Case D: "khong phai" + digits is a VALUE correction
        # (rule 6), handled by the digit-run scan below, not here.

    # --- phone value correction (rule 6): "<new run> (chu)
    # khong phai <old run>" in one clause. Old-tail target ->
    # replaced; new-tail target -> no event (positive stands).
    if targets_norm:
        all_runs = _digit_runs(raws, folds, clause_ids)
        for kp in _khong_phai_positions(raws):
            cid = clause_ids[kp]
            before = [r for r in all_runs
                      if clause_ids[r[0]] == cid and r[1] <= kp]
            after = [r for r in all_runs
                     if clause_ids[r[0]] == cid and r[0] > kp + 1]
            if not before or not after:
                continue
            new_digits = before[-1][2]
            old_digits = after[0][2]
            if new_digits == old_digits or len(old_digits) < 2:
                continue
            for t in targets_norm:
                old_matches = (old_digits == t
                               or t.endswith(old_digits))
                new_matches = (new_digits == t
                               or t.endswith(new_digits))
                if old_matches and not new_matches:
                    # Position at the END of the old run, not at
                    # the marker: the old value is mentioned
                    # after the marker, so the replacement must
                    # sort after that mention event, or the
                    # mention would wrongly win as "last".
                    events.append((after[0][1], "replaced",
                                   "replaced_by_value_correction"))
                    break

    # --- "a khong" / "y la" correction markers (rule 4).
    # Processed in order; each marker looks at the last target
    # event before it and at what follows it.
    events.sort(key=lambda e: e[0])
    for marker_pos in _find_correction_markers(folds):
        prior = [e for e in events if e[0] < marker_pos]
        if not prior or prior[-1][1] != "positive":
            continue
        # Earliest new target after the marker: a positive verb
        # with a specific non-target object, or a phone mention
        # that is not one of the target phones.
        new_pos = None
        for info in verb_info:
            if info["start"] > marker_pos \
                    and info["polarity"] == "positive" \
                    and info["object_kind"] == "specific":
                new_pos = info["start"]
                break
        # Phone runs after the marker that are phone-like (typed
        # runs of >= 9 digits, or spoken runs with phone context
        # / >= 7 digits) and match NO target phone: a new number.
        # Short context-less spoken runs ("nam sau" -> 56) are
        # not phone-like and must not fake a new target.
        for (rs, re_, digits, kind) in _digit_runs(raws, folds,
                                                   clause_ids):
            if rs <= marker_pos:
                continue
            if kind == "digits":
                phone_like = len(digits) >= 9
            else:
                cid = clause_ids[rs]
                first, last = bounds[cid]
                phone_like = (len(digits) >= 7 or any(
                    folds[k] in _PHONE_CONTEXT
                    for k in range(first, last + 1)))
            if not phone_like:
                continue
            norm = _norm_phone(digits)
            matches_target = norm in targets_norm or any(
                t.endswith(digits) or digits == t
                for t in targets_norm)
            if not matches_target:
                if new_pos is None or rs < new_pos:
                    new_pos = rs
                break
        # Earliest positive re-mention of the target after marker.
        re_pos = None
        for (pos, kind, _r) in events:
            if pos > marker_pos and kind == "positive":
                re_pos = pos
                break
        if new_pos is not None and (re_pos is None
                                    or new_pos < re_pos):
            events.append((marker_pos, "replaced",
                           "replaced_by_new_target"))
        elif re_pos is not None:
            pass  # re-selection wins; the later positive event
            # already stands as the last decision.
        else:
            events.append((marker_pos, "cancelled",
                           "cancelled_no_new_target"))
        events.sort(key=lambda e: e[0])

    # --- final decision.
    if events:
        last_pos, last_kind, last_reason = events[-1]
        if last_kind == "positive":
            # A later general veto cancels a selection ("goi lai
            # cho Vy, dung goi nua"); a later general positive
            # never rescues a vetoed target (handled by the
            # last-event rule itself).
            for (gpos, gkind) in general_events:
                if gpos > last_pos and gkind == "negated":
                    return {"selection": "negated",
                            "reason": "general_veto_after_selection",
                            "mention_present": mention_present}
            return {"selection": "positive", "reason": last_reason,
                    "mention_present": mention_present}
        return {"selection": last_kind, "reason": last_reason,
                "mention_present": mention_present}
    if general_events:
        gpos, gkind = general_events[-1]
        return {"selection": gkind,
                "reason": ("generic_callback_negated"
                           if gkind == "negated"
                           else "generic_callback_positive"),
                "mention_present": mention_present}
    # No target event and no general event: a positive verb for
    # another person still means "no veto against this target"
    # (veto-gate contract); without any positive verb, unknown.
    for info in verb_info:
        if info["polarity"] == "positive":
            return {"selection": "positive",
                    "reason": "positive_action_no_target_veto",
                    "mention_present": mention_present}
    if mention_present and not name_mentions and not phone_mentions:
        return {"selection": "unknown",
                "reason": "quoted_mention_only",
                "mention_present": True}
    # Fallback split (coordinator delta-2 fix for the reviewer's
    # abstention hole): the old "no_action_evidence" conflated
    # three situations the adapter must treat differently:
    # - no verb head of ANY action in the text -> no_callback_verb
    #   (the adapter abstains; a history-grounded binding stands);
    # - a negated verb of the queried action aimed at someone else
    #   -> negated_other_object (veto: this action's selection
    #   toward the target is not positive);
    # - only blocked verbs (question mood / past / "chưa") ->
    #   blocked_verb_only (veto: a blocked verb is not a request);
    # - otherwise, only verbs of another action ->
    #   other_action_verb_only (veto: the queried action was
    #   never selected; cross-action binding must not un-fire).
    all_verbs = _find_verbs(folds, ("call", "message"))
    all_pols = [_verb_polarity(v, raws, folds, clause_ids, bounds)
                for v in all_verbs]
    if not all_verbs:
        reason = "no_callback_verb"
    elif any(v["action"] in actions and p == "negated"
             for v, p in zip(all_verbs, all_pols)):
        reason = "negated_other_object"
    elif all(p == "blocked" for p in all_pols):
        reason = "blocked_verb_only"
    else:
        reason = "other_action_verb_only"
    return {"selection": "unknown", "reason": reason,
            "mention_present": mention_present}
