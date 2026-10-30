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
  8. Round-5 additions (thread A, batch-4 MINOR fixes):
     - Lookup-governed mentions are never message content
       (F-B4-3): tim / lay / tra cuu / kiem tra / xem govern
       the number as information to retrieve; a later positive
       callback verb in the same clause makes the lookup
       preparatory to that verb, not a competing foreign
       action.
     - Channel prepositions (F-B4-7): qua / bang / o / theo /
       vao before "so X" make X the channel, not content;
       "tu" stays sender-side, never a channel.
     - Delegation (F-B4-6): a callback verb under "nho / bao
       + person + verb" (same clause) is the delegatee's
       action: blocked, never the user's positive selection.
       Generic pronouns as the "person" do not delegate
       ("nho em goi" is a direct request to the assistant);
       a generic title + a real name ("anh Nam") does.
     - Forward + bare callback (F-B4-4, discourse scope, not
       verb scope): a bare positive callback verb (empty
       object) after the same clause forwarded the TARGET
       number to a named recipient other than the target is
       not a positive selection -- its elided target is
       undetermined. An explicit object after the verb, a
       forward of a different number, a generic recipient, or
       a forward to the target herself are all unaffected.

LAYER C -- INSTRUCTION SELECTION (R4 fix, thread A).
  analyze_action_selection judges a callback VERB. It is blind
  to an anaphoric instruction reference ("lam nhu em dan luc
  nay", "so do", "nguoi vua goi") whose continuation is carried
  by the generic verb "lam" (deliberately NOT a callback verb:
  "lam" alone must never select a call) or by no verb at all.
  That blindness is exactly the R4 hole: module A resolves the
  reference to an old instruction, B returns unknown /
  no_callback_verb, and the adapter's abstain exception lets
  the binding through -- for a continuation ("lam nhu em dan
  luc nay") AND for a cancellation ("dung / khoi / khong can
  lam nhu em dan luc nay nua"), a question about the old
  instruction, a recount of having done it, and a reference
  that exists only inside a quote. Reference resolution proves
  WHICH instruction is meant; it never proves the user wants
  to CONTINUE performing it. analyze_instruction_selection
  judges that second question, clause-scoped, with LAST
  DECISIVE WINS across the whole text (round 2): every clause
  is classified (cancelled / replaced / blocked / continue /
  unknown / none) and the last decisive clause governs, so a
  recount clause followed by a continuation clause reads as a
  continuation, a continuation followed by a later-clause
  cancellation reads as a cancellation, and a distractor clause
  with no signal changes nothing. A cancellation clause that
  names a KNOWN-DIFFERENT target ("đừng gọi cho An nữa" when
  the counterpart is Vy) is not decisive for this instruction
  and is skipped -- cancelling someone else never cancels this
  instruction -- while a generic cancellation ("đừng làm nữa")
  or one naming the counterpart governs. Signals:
    - "cancelled": a cancellation marker governs the reference
      in its clause (đừng / chớ / khỏi / hủy / bỏ / dừng /
      ngừng, "không cần", "không phải" + "làm" or + the
      reference manner itself, a bare-"thôi" withdrawal clause
      after a reference clause, or a generic cancellation in a
      later clause). A later clause positively selecting a
      DIFFERENT target reports "replaced" instead (same veto
      effect; the distinction is reporting only).
    - "replaced": a later (or same) clause explicitly selects a
      different target -- a full number with a callback verb, a
      change verb ("đổi"/"thành"), or a correction marker, a
      known-different name the same way, a tail change
      ("đuôi đổi/thành/là" + a digit run adjacent to the
      change verb and different from the bound number's tail
      -- any length in explicit context, round-3 fix F4), an
      explicit new-number statement ("số mới là X", round-3
      fix F3), or a bare adversative fragment ("mà (+ số) X"
      with no verb or predicate, round-3 fix F3). A bare
      number mention with no selection cue (information, "là
      số tổng đài") is NOT a replacement.
    - "blocked": the operative clause is a question frame
      (opens "có"/"nên"/a verb and ends "không"/"hả"/"chứ", or
      ends "có được không"), a past recount ("đã / vừa / mới"
      + "làm", or "rồi"/"xong rồi" AFTER the reference), a
      "chưa" status, a conditional ("nếu", "giá như", "khi
      nào", "chừng nào", "hễ" -- round-3 fix F7) scoping the
      reference, a wait-then deferral ("đợi/chờ + condition +
      rồi (+mới) làm", round-3 fix F7 -- a particle-only gap
      such as "đợi đã rồi làm" is a short pause, not a
      condition), a bare only-then ("rồi mới làm", round-3
      fix F7 trail -- previously misread as a recount), a
      deferral ("khoan" governing the reference/"làm" in the
      same clause, round-3 fix F8 -- "khoan đã rồi làm" does
      NOT govern: the "rồi" marks wait-then-do), reported
      speech (a non-pronoun name + "bảo/ nhắn/dặn/nói/kêu"
      attributing the reference), or the reference occurs
      only inside quotes. A condition on the ACTION (whether
      to perform it) blocks; a condition on a VALUE (whether
      a number is correct, P4b) is out of scope and untouched.
    - "continue": a positive continuation in the operative
      clause -- "làm" + a prior-instruction reference, or a
      positive callback verb + an anaphoric/generic reference.
    - "unknown": a bare reference with no polarity signal
      (e.g. "như em dặn lúc nãy" with no verb). The adapter
      keeps abstaining here -- that is the honest 0764-class
      case, now RECORDED as unknown rather than mistaken for
      a proven continuation.
  The function is VETO-ONLY like B: "continue" never proves a
  binding on its own; the adapter runs it only after module A
  established a bound-reference selection, and only a
  cancelled / replaced / blocked result refuses an un-fire.
  instruction_action reports which action class a text's verbs
  belong to ("call" / "message" / "both" / "other" / "contact"
  / "unknown"); "other" covers recognised non-communication
  verbs (lưu, tra cứu, xóa, kiểm tra, xem, tìm, ghi) AND
  callback verbs governed by a scheduling / reminder wrapper
  (đặt lịch, đặt hẹn, nhắc -- round-3 fix F6); "contact"
  covers generic contact only ("liên hệ" -- round-3 fix F5
  inventory); a bound instruction whose action is "other" or
  "unknown" is NOT a continuation of a call / message
  proposal. A verb outside every inventory still yields
  "unknown": never guessed.

LIMITATIONS (honest, not bugs to paper over):
  - Past-tense statements ("hom qua khong co goi cho Vy") are not
    modelled: "khong co" is not treated as a negation marker, so
    the verb reads positive. Thread A is expected not to bind a
    callback from a past-tense statement.
  - Interrogatives other than the frames in the layer-C
    docstring (opens "có"/"nên"/a verb, ends "không"/"hả"/
    "chứ", or a "có được không" tail) are not modelled; a
    question containing a callback phrase reads positive (veto
    gate only blocks explicit negation/correction).
  - Single "tu" for digit 4, compound spoken amounts, and
    space-separated digit strings shorter than a full number are
    out of scope (same BLOCKED list as the phone module).
  - A bare new target after a correction marker without a verb
    ("goi cho Vy, a khong, An") yields "cancelled", not
    "replaced": both refuse un-fire, so the gate outcome is the
    same; only the reported reason differs.
  - A bare "thôi" clause is read as withdrawal only when it
    is the LAST clause ("làm như lúc nãy đi, nhưng thôi");
    a mid-text "thôi" introducing a new topic ("Thôi,
    chuyện kia để sau đi") is discourse, not a withdrawal,
    and a leading "thôi" before a continuation is overridden
    by last-decisive-wins anyway.
  - "mẹ" vs "mạ" are treated as different addressee strings
    (dialect equivalence is not claimed); a mismatch vetoes,
    which is the safe direction.
  - Multi-amount texts are out of scope for the topic branch:
    within a topic-bound verdict, an amount mention in a marked
    clause is read as the bound topic (single-topic
    assumption).
"""

import re
import unicodedata

__all__ = ["analyze_action_selection",
           "analyze_instruction_selection",
           "analyze_topic_selection",
           "instruction_action"]


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
                ["gui", "sms"], ["sms"], ["tra", "loi"],
                # Bare "gui" (round-10 fix M1): "Gửi Vy số X"
                # is a message to Vy at X (double-object +
                # owner tie). A bare "gui" whose object is
                # money / goods / mail is NOT a message verb:
                # _find_verbs rejects those shapes (see the
                # _GUI_NONMESSAGE_HEADS guard there), so
                # "gửi tiền" stays an other verb via
                # _OTHER_VERB_PATTERNS, never a message.
                ["gui"]],
}
# Object heads after a bare "gui" that make it a transfer /
# shipment / parking / mail verb, never a message verb
# (round-10 fix M1 guard, applied in _find_verbs so every
# consumer -- layer B, instruction_action,
# binding_action_class, phone_numbers_for_action -- agrees):
# tien (money), hang / do (goods), xe (parking), email /
# thu / buu / kien (mail / parcel). Longer "gui" patterns
# ("gui tin nhan", "gui sms") are unambiguous messages and
# never reach this guard: longest match wins.
_GUI_NONMESSAGE_HEADS = {"tien", "hang", "do", "xe", "email",
                         "thu", "buu", "kien"}
# Number words and amount words (folded) for the word-amount
# guard: "gửi một trăm nghìn" / "gửi hai trăm nghìn" are
# money transfers, while "gửi một tin nhắn" is a message
# (the second token decides: amount word vs "tin"/"sms").
_GUI_NUMBER_WORDS = {"mot", "hai", "ba", "bon", "nam", "sau",
                     "bay", "tam", "chin", "khong"}
_GUI_AMOUNT_SUFFIX = {"tram", "nghin", "ngan", "trieu", "ty",
                      "dong"}

# Negation markers, matched on ORIGINAL tokens (casefolded, WITH
# diacritics): folded matching would confuse "cho" (preposition
# "for") with "chớ" (the negation marker), both folding to "cho".
_NEG_MARKERS = {"đừng", "chớ", "khỏi", "không"}
# Particles allowed between a marker and its verb.
# Particles skippable between a negation marker and its verb (polarity
# lookback only -- this set is used nowhere else). "mà" joins it for
# the emphatic-negation frame "đừng (có) mà + verb" (SEAL-003): the
# skip is consecutive-only, so "mà" bridges ONLY a directly
# preceding negation frame; it never reaches across another word
# ("Nhưng mà gọi" stays positive: the skip stops at "nhưng",
# which is not a marker; "mà nhớ gọi" stays positive: the skip
# stops at "nhớ").
_PARTICLES = {"có", "cần", "lại", "phải", "là", "mà"}
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
                matched = (j, action, pat)
                break
        if matched is not None and matched[2] == ["gui"]:
            # Bare "gui" transfer guard (round-10 fix M1): a
            # bare "gửi" whose object is money / goods /
            # mail / a bare amount is a transfer, not a
            # message -- it must never bind as a message
            # instruction ("Gửi tiền tới số X" + CONT +
            # sms X is a money transfer, not a message).
            # Longer "gui" patterns never reach here
            # (longest match wins above).
            end = matched[0]
            reject = False
            if end < n:
                nxt = folds[end]
                if nxt in _GUI_NONMESSAGE_HEADS:
                    reject = True
                elif nxt.isdigit() and len(nxt) < 9:
                    reject = True
                elif nxt in _GUI_NUMBER_WORDS and end + 1 < n \
                        and folds[end + 1] in _GUI_AMOUNT_SUFFIX:
                    reject = True
            if reject:
                matched = None
        if matched is not None:
            verbs.append({"start": i, "end": matched[0],
                          "action": matched[1],
                          "pattern": matched[2]})
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
    taken = 0
    while j <= last and taken < 3:
        if folds[j] in _OBJECT_STOPS or folds[j] in _VERB_HEADS:
            break
        # Qualifier skip (selection round, RT-07): "moi" /
        # "cu" between "so" and a digit run do not consume
        # span budget -- "so moi X" is one phone mention,
        # so X must stay inside the governed span instead
        # of falling past the 3-token cap. The skip applies
        # ONLY when a digit run follows immediately, so a
        # bare adjective ("Binh moi") changes nothing.
        if folds[j] in ("moi", "cu") and j + 1 <= last \
                and (raws[j + 1].isdigit()
                     or folds[j + 1] in _DIGIT_WORDS):
            j += 1
            continue
        j += 1
        taken += 1
    return (start, j)


def _classify_object(span, folds, target_spans,
                     all_phone_spans=(), all_digit_spans=()):
    """general | specific | target for an object span.

    A span containing a phone mention of ANY number is
    specific, never general (round-10 fix S1): "gọi số X"
    governs X specifically, so for proposal Y it must not
    count as a general callback -- the old generic-head
    rule ("số" starts the span) leaked every verb + other
    number into a positive selection for this number.
    A span containing ANY digit run (typed or spoken,
    phone-like or not) is likewise specific, never general
    (R5 fix for R4 batch-11 S1): "gọi số 2345" governs the
    short run specifically, so the verb is NOT bare -- the
    old rule classified it general via the "số" head and
    the bare verb then selected an unrelated phone mention
    elsewhere in the text. Only a verb whose object span
    contains NO digit run at all can be general/bare.
    all_phone_spans / all_digit_spans default to () for
    callers that do not need the distinction (their
    object_kind is unused downstream).
    """
    start, end = span
    if start >= end:
        return "general"
    for (ms, me) in target_spans:
        if ms < end and start < me:
            return "target"
    for (ms, me) in all_phone_spans:
        if ms < end and start < me:
            return "specific"
    for (ds, de) in all_digit_spans:
        if ds < end and start < de:
            return "specific"
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


# ---------------------------------------------------------------- layer C
# Instruction selection (R4): does the current text CONTINUE an
# anaphoric instruction reference, or cancel / replace / question
# / recount it? See the module docstring, LAYER C section.
#
# Reference patterns are folded token sequences, aligned with
# module A's bind_history_reference triggers (prior-instruction
# phrases) plus its anaphoric / generic patterns. A pattern the
# phone module does not bind on is never judged here: layer C
# only ever narrows a binding module A already made.

_INSTRUCTION_REF_PATTERNS = [
    (["luc", "nay"], "prior"),
    (["nhu", "da"], "prior"),
    (["lam", "nhu"], "prior"),
    (["theo", "nhu"], "prior"),
    (["nhu", "em", "dan"], "prior"),
    (["nhu", "anh", "dan"], "prior"),
    (["nhu", "chi", "dan"], "prior"),
    (["so", "do"], "anaphoric"),
    (["so", "nay"], "anaphoric"),
    (["so", "moi", "nhat"], "anaphoric"),
    (["nguoi", "vua", "goi"], "anaphoric"),
    (["nguoi", "vua", "nhan"], "anaphoric"),
]

# Cancellation markers, matched on ORIGINAL tokens (casefolded,
# WITH diacritics): folded matching would confuse "cho"
# (preposition "for") with "chớ" (negation), both folding to
# "cho". A bare "thôi" is deliberately NOT a marker here: as a
# discourse particle ("thôi, làm như lúc nãy đi") it does not
# cancel; a bare-"thôi" clause is judged separately as a
# withdrawal only when it follows a reference clause.
_CANCEL_RAW_TOKENS = {"đừng", "chớ", "khỏi", "hủy", "bỏ",
                      "dừng", "ngừng"}
# Particles allowed between "không" and "làm". FOLDED forms:
# the comparison runs on folds, so the set must be folded too
# (round-2 fix S1: the old diacritic forms never matched).
_CANCEL_PARTICLES = {"can", "phai", "lai", "la"}
_PAST_BEFORE_LAM = {"da", "vua", "moi"}
# Conditional markers scoping an action (folded sequences):
# a condition on WHETHER to perform the action blocks. "khi"
# alone is excluded (too broad: "khi nãy", "khi đó").
# "hễ" is inherently a whenever-conditional ("hễ rảnh thì ...",
# "hễ rảnh ..."): it needs no "thì" to scope the action, so it
# stands alone here (round-3 fix F7).
_CONDITIONAL_PATTERNS = [["neu"], ["neu", "nhu"], ["gia", "nhu"],
                         ["khi", "nao"], ["chung", "nao"], ["he"]]
# Attribution verbs (folded) for reported speech: a non-pronoun
# subject + one of these attributing the reference means the
# reference is someone else's words, not the user's request.
_ATTRIBUTION_VERBS = {"bao", "nhan", "dan", "noi", "keu"}
# First-person / speaker subjects (folded): "em bảo ..." is the
# user reporting their own words, not reported speech.
_PRONOUN_SUBJECTS = {"em", "toi", "minh", "tao", "to"}
# Recognised non-communication verbs (folded patterns) for
# instruction_action's "other" class: an instruction to save /
# look up / delete / check / view / find / note a number is
# not a call or message instruction. Forwarding / sharing /
# money-transfer verbs are foreign actions too: "chuyển tiếp
# số X cho Vy" selects a forward of X, never a call or message
# to X (round-4 fix S3) -- they join "other" so both
# instruction_action and the action-selection fallback read
# them as a different action, not as no action at all.
_OTHER_VERB_PATTERNS = [["luu"], ["luu", "tru"], ["tra", "cuu"],
                        ["xoa"], ["kiem", "tra"], ["xem"],
                        ["tim"], ["ghi"], ["chuyen", "tiep"],
                        ["forward"], ["share"], ["chuyen", "tien"],
                        ["gui", "tien"], ["chuyen", "khoan"],
                        # Bare "chuyển" (selection round, ATK-019):
                        # longest-match keeps the 2-token forms
                        # winning, so this only fires when
                        # "chuyển" is not followed by tiếp /
                        # tiền / khoản.
                        ["chuyen"]]
# Words (FOLDED) that cannot continue a name in a "cho X"
# span: with these, "cho Vy số ..." and "cho Vy như lúc nãy"
# both read as just "Vy" instead of the false names "vy so"
# / "vy nhu".
_NAME_SECOND_STOPS = {"so", "nhu", "luc", "nay", "lam", "goi",
                      "nhan", "dien", "gui", "tra", "dan",
                      "noi", "bao", "da"}
_AMOUNT_WORDS = {"mot", "hai", "ba", "bon", "nam", "sau", "bay",
                 "tam", "chin", "khong", "tram", "nghin", "ngan",
                 "trieu", "ty", "dong"}


def _find_ref_occurrences(folds, clause_ids):
    """All reference-pattern occurrences: (start, end, kind, cid).

    Longest patterns win at the same start ("nhu em dan" beats
    "nhu da" only where both start; overlapping occurrences at
    different starts are all kept -- the caller takes the LAST
    one as operative, so a recount clause followed by a
    continuation clause reads as a continuation.
    """
    occurrences = []
    patterns = sorted(_INSTRUCTION_REF_PATTERNS,
                      key=lambda p: -len(p[0]))
    i = 0
    n = len(folds)
    while i < n:
        matched = None
        for pat, kind in patterns:
            width = len(pat)
            if folds[i:i + width] == pat:
                matched = (i + width, kind)
                break
        if matched is not None:
            end, kind = matched
            occurrences.append((i, end, kind, clause_ids[i]))
            i = end
        else:
            i += 1
    return occurrences


def _clause_cancelled(raws, folds, first, last, has_ref=False):
    """True iff a cancellation marker governs this clause.

    A raw marker token anywhere in the clause, the folded
    bigram "khong can", "khong" followed within two tokens
    by "lam" with only particles between ("khong lam",
    "khong can lam", "khong phai lam"), or "khong phai" in a
    clause that itself carries the reference manner ("khong
    phai nhu luc nay" -- a manner negation needs no "lam").
    A marker in ANOTHER clause never cancels this clause's
    reference.
    """
    for k in range(first, last + 1):
        if raws[k] in _CANCEL_RAW_TOKENS:
            return True
        if folds[k] == "khong" and k + 1 <= last \
                and folds[k + 1] == "can":
            return True
        if folds[k] == "khong":
            if has_ref and k + 1 <= last \
                    and folds[k + 1] == "phai":
                # "không phải" + the reference manner itself
                # ("không phải như lúc nãy") cancels even with
                # no "làm" after it.
                return True
            j = k + 1
            steps = 0
            while j <= last and steps < 2 \
                    and folds[j] in _CANCEL_PARTICLES:
                j += 1
                steps += 1
            if j <= last and folds[j] == "lam":
                return True
    return False


def _clause_is_question(raws, folds, first, last):
    """Question frames for a clause (round-2 widened).

    The v1 frame (opens "có", ends "không") plus: opens "nên"
    and ends "không"; opens with a verb and ends "không" /
    "hả" / "chứ"; or a "có được không" tail anywhere. An
    affirmative request never ends in one of these tails, so
    widening does not block positive requests.

    Selection round: the confirmation particle "nhỉ" (SEAL-004).
    With tone marks it is unambiguous -- "nhỉ" is never a name,
    so a clause ending in it is a question regardless of what
    opens the clause ("Lúc nãy em bảo gọi số X nhỉ?" echoes a
    prior instruction as a question, it does not re-issue it).
    Toneless "nhi" is form-ambiguous with the name Nhi, so it
    counts only with two guards: the clause must contain a
    digit run (a name never follows a number in this position)
    and the token before it must not be "cho" (the canonical
    name-target form "Gọi cho Nhi" stays a request).
    """
    if last <= first:
        return False
    if raws[first] == "có" and raws[last] == "không":
        return True
    if folds[first] == "nen" and raws[last] == "không":
        return True
    if raws[last] in ("không", "hả", "chứ") and (
            folds[first] in _VERB_HEADS or folds[first] == "lam"):
        # Scope guard (selection round): a tail particle
        # questions the opening verb ONLY when nothing
        # re-scopes it. A purpose marker ("để") or a second
        # verb head between the verb and the tail means the
        # particle belongs to the purpose clause ("gọi ...
        # để hỏi xem có rảnh không" is a request to call,
        # pinned positive), not to the opening verb. A
        # question particle scopes to the nearest verb
        # phrase, never to a distant opener across a purpose
        # boundary.
        between = folds[first + 1:last]
        breakers = _VERB_HEADS | {
            "hoi", "xem", "lam", "bao", "nho", "de"}
        if not any(t in breakers for t in between):
            return True
    if raws[last] == "nhỉ":
        return True
    if folds[last] == "nhi" and folds[last - 1] != "cho" and any(
            folds[k].isdigit() or folds[k] in _DIGIT_WORDS
            for k in range(first, last + 1)):
        return True
    for k in range(first, last - 1):
        if folds[k:k + 3] == ["co", "duoc", "khong"]:
            return True
    return False


def _clause_past_before_lam(folds, first, last):
    """Past marker immediately before "làm": a recount, not a
    request ("đã làm như lúc nãy rồi"). A past marker inside
    the reference phrase itself ("như em đã dặn") does not
    count: only a marker governing "làm" blocks."""
    for k in range(first + 1, last + 1):
        if folds[k] == "lam" and folds[k - 1] in _PAST_BEFORE_LAM:
            return True
    return False


def _clause_past_after_ref(folds, first, last, ref_end):
    """"rồi" / "xong rồi" AFTER the reference: also a recount
    ("làm như lúc nãy rồi", "làm như lúc nãy xong rồi"). A
    "rồi" BEFORE the reference is sequential ("rồi, làm như
    lúc nãy đi") and does not count, and neither does a
    conjunction "rồi" followed by another verb ("làm như lúc
    nãy rồi gọi cho Vy" = do it, THEN call Vy). Only a
    clause-final "rồi" (or one followed only by discourse
    particles) or a "xong" closed by "rồi" counts."""
    _particles = {"di", "nhe", "nha", "dau", "nua", "a", "oi",
                  "ne"}
    for k in range(ref_end, last + 1):
        if folds[k] == "roi" and all(
                folds[j] in _particles for j in range(k + 1, last + 1)):
            return True
        if folds[k] == "xong" and (k == last
                                   or folds[k + 1] == "roi"):
            return True
    return False


def _clause_conditional(folds, first, last):
    """A conditional marker anywhere in the clause scopes the
    action in it ("nếu rảnh thì làm như lúc nãy", "nếu Vy
    đồng ý thì làm như lúc nãy")."""
    for pat in _CONDITIONAL_PATTERNS:
        width = len(pat)
        for k in range(first, last - width + 2):
            if folds[k:k + width] == pat:
                return True
    return False


def _clause_reported(raws, folds, first, last):
    """Attribution of the clause's content to someone else:
    a non-pronoun subject token immediately before an
    attribution verb ("Vy bảo ...", "An nhắn ..."). The
    subject must be a name-like token, not a speaker pronoun
    ("em bảo ..." is the user themselves). "bạn em bảo" counts
    too (possessive + pronoun subject)."""
    for k in range(first + 1, last + 1):
        if folds[k] in _ATTRIBUTION_VERBS:
            if folds[k - 1] not in _PRONOUN_SUBJECTS \
                    and folds[k - 1] not in _VERB_HEADS \
                    and folds[k - 1] != "lam":
                return True
            if k - 2 >= first and folds[k - 2] == "ban" \
                    and folds[k - 1] in _PRONOUN_SUBJECTS:
                return True
    return False


def _target_name_folds(target_names):
    """Folded full names + folded last tokens, for comparison."""
    out = set()
    for name in target_names or ():
        parts = [_fold(p) for p in _nfc(name).split() if p]
        if not parts:
            continue
        out.add(" ".join(parts))
        out.add(parts[-1])
    return out


def _clause_cancel_target(raws, folds, clause_ids, bounds, cid,
                           target_names, target_phones):
    """The cancel target of a clause, or None.

    Returns ("different", ...) iff the clause cancels a target
    KNOWN to differ from the bound targets (a full number
    different from every bound phone, or a "cho/tới/đến X" name
    matching no bound name/last-token); ("same", ...) iff it
    cancels a bound target; None iff no cancel target can be
    read (generic cancellation). Only a KNOWN-different target
    is skipped by the clause scan: when the targets are unknown,
    a named cancellation attaches (safe direction).
    """
    first, last = bounds[cid]
    targets_norm = {_norm_phone(p) for p in (target_phones or ())}
    targets_norm = {t for t in targets_norm if t}
    name_folds = _target_name_folds(target_names)
    for (rs, re_, digits, kind) in _digit_runs(raws, folds,
                                               clause_ids):
        if clause_ids[rs] != cid or kind != "digits":
            continue
        if len(digits) < 9:
            continue
        norm = _norm_phone(digits)
        if norm in targets_norm:
            return "same"
        if targets_norm:
            return "different"
    for k in range(first, last):
        if raws[k] not in ("cho", "tới", "đến"):
            continue
        j = k + 1
        parts = []
        while j <= last and len(parts) < 2 \
                and folds[j] not in _OBJECT_STOPS \
                and folds[j] not in _VERB_HEADS \
                and not (parts and folds[j] in _NAME_SECOND_STOPS):
            parts.append(folds[j])
            j += 1
        if not parts:
            continue
        cand = " ".join(parts)
        if cand in name_folds or parts[-1] in name_folds:
            return "same"
        if name_folds:
            return "different"
        return None
    return None


def _clause_has_new_number_cue(folds, first, last):
    """'số mới là X' / 'mới là X': an explicit new-number
    statement selects the new number (round-3 fix F3). 'số mới
    nhất' (the newest number, an anaphoric phrase) is
    excluded: it does not by itself state a change."""
    for k in range(first, last):
        if folds[k] == "moi" and folds[k + 1] == "la":
            return True
        if folds[k] == "so" and folds[k + 1] == "moi":
            if k + 2 <= last and folds[k + 2] == "nhat":
                continue
            return True
    return False


def _clause_ma_fragment(raws, folds, clause_ids, bounds, cid,
                        target_phones):
    """Bare adversative fragment 'mà (+ số) <full different
    number> (+ particles)': a correction to that number
    (round-3 fix F3, weak variant S7a). The fragment must be
    EXACTLY that shape -- no verb, no predicate ('là'), no
    question ('sao', 'thì'), no negation, no 'cũng' (also)
    -- so 'mà số X là số tổng đài' (informational), 'mà số X
    thì sao' (asking), and 'mà nhớ gọi số X' (a further verb)
    are all excluded. Returns True iff such a fragment with a
    number different from every bound phone is present."""
    first, last = bounds[cid]
    if folds[first] != "ma":
        return False
    if any(t in folds[first:last + 1]
           for t in ("la", "sao", "thi", "khong", "cung")):
        return False
    targets_norm = {_norm_phone(p) for p in (target_phones or ())}
    targets_norm = {t for t in targets_norm if t}
    rest = folds[first + 1:last + 1]
    while rest and rest[0] in ("so", "dien", "thoai"):
        rest = rest[1:]
    while rest and rest[-1] in ("di", "nhe", "nha", "a", "oi",
                                "ne"):
        rest = rest[:-1]
    if not rest:
        return False
    digits = "".join(
        t for t in rest if t.isdigit())
    if digits != "".join(rest) or len(digits) < 9:
        return False
    if targets_norm and _norm_phone(digits) in targets_norm:
        return False
    return bool(targets_norm)


def _clause_has_selection_cue(folds, first, last):
    """A cue that a number/name in this clause is SELECTED, not
    merely mentioned: a positive callback verb, a change verb
    ("đổi"/"thành"), or a correction marker ("à không"/"ý là").
    A bare copula mention ("là số tổng đài") has no cue."""
    if any(folds[k] in ("doi", "thanh") for k in range(first, last + 1)):
        return True
    if _find_correction_markers(folds[first:last + 1]):
        return True
    return False


def _clause_replacement(raws, folds, clause_ids, bounds, cid,
                        target_names, target_phones):
    """True iff this clause explicitly selects a DIFFERENT target
    than the bound one: a full number (with a selection cue),
    a known-different name (with a selection cue), a tail
    change ("đuôi đổi/thành/là" + a digit run adjacent to the
    change verb and different from the bound phone's tail --
    any length in explicit context), an explicit new-number
    statement ("số mới là X"), or a bare adversative fragment
    ("mà (+ số) X"). Digit runs are context-gated: a bare
    number mention with no cue ("là số tổng đài") is NOT a
    replacement."""
    first, last = bounds[cid]
    targets_norm = {_norm_phone(p) for p in (target_phones or ())}
    targets_norm = {t for t in targets_norm if t}
    name_folds = _target_name_folds(target_names)
    verbs = _find_verbs(folds, ("call", "message"))
    # A positive verb selects a new target ONLY when the clause
    # is not a sequential continuation: "rồi" before the verb
    # ("làm như lúc nãy rồi gọi cho Vy") sequences a second
    # action after the old instruction, it does not replace it.
    # Change verbs and correction markers still replace.
    positive_verb = False
    for v in verbs:
        if clause_ids[v["start"]] != cid:
            continue
        if _verb_polarity(v, raws, folds, clause_ids, bounds) \
                != "positive":
            continue
        if any(folds[j] == "roi"
               for j in range(first, v["start"])):
            continue
        positive_verb = True
    cue = positive_verb or _clause_has_selection_cue(
        folds, first, last)
    if not cue:
        cue = _clause_has_new_number_cue(folds, first, last)
    # Tail change: "duoi" + change verb + a digit run whose
    # digits differ from the bound phone's tail. The run must
    # sit right after the change verb (at most one token away,
    # covering "thành số X"): without that adjacency, an
    # unrelated digit elsewhere in the clause ("đuôi tóc đổi
    # thành màu khác, 2 người") would falsely read as a tail
    # change. In explicit tail-change context ANY digit run
    # (round-3 fix F4) counts -- the old 3-4 digit window
    # wrongly excluded 2- and 5-digit tails; length is
    # meaningless when the cue is explicit.
    for k in range(first, last + 1):
        if folds[k] != "duoi":
            continue
        for j in range(k + 1, last + 1):
            if folds[j] not in ("doi", "thanh", "la"):
                continue
            for (rs, re_, digits, kind) in _digit_runs(
                    raws, folds, clause_ids):
                if clause_ids[rs] != cid or kind != "digits":
                    continue
                if not (j + 1 <= rs <= j + 2):
                    continue
                if any(t.endswith(digits) for t in targets_norm):
                    continue
                if targets_norm:
                    return True
    if _clause_ma_fragment(raws, folds, clause_ids, bounds, cid,
                           target_phones):
        return True
    if not cue or not (targets_norm or name_folds):
        return False
    for (rs, re_, digits, kind) in _digit_runs(raws, folds,
                                               clause_ids):
        if clause_ids[rs] != cid or kind != "digits":
            continue
        if len(digits) >= 9 and _norm_phone(digits) not in targets_norm:
            return True
    for k in range(first, last):
        if raws[k] not in ("cho", "tới", "đến"):
            continue
        j = k + 1
        parts = []
        while j <= last and len(parts) < 2 \
                and folds[j] not in _OBJECT_STOPS \
                and folds[j] not in _VERB_HEADS \
                and not (parts and folds[j] in _NAME_SECOND_STOPS):
            parts.append(folds[j])
            j += 1
        if not parts:
            continue
        cand = " ".join(parts)
        # A name counts as "different" only when some bound
        # name is actually known: with no known names, a name
        # in the clause may well be the counterpart (unknown,
        # not different).
        if name_folds and cand not in name_folds \
                and parts[-1] not in name_folds:
            return True
    return False


def _clause_has_lam_cancel(raws, folds, first, last):
    """A generic "làm"-cancellation inside this clause: a cancel
    marker followed by "làm" ("đừng làm nữa"). A lam-cancel
    governs the instruction itself, so it attaches even when
    the same clause also cancels a different named target."""
    for k in range(first, last + 1):
        if raws[k] in _CANCEL_RAW_TOKENS \
                and "lam" in folds[k + 1:last + 1]:
            return True
    return False


def _clause_bare_withdrawal(folds, first, last):
    """A clause that is only a withdrawal: {"thôi"} or {"à",
    "không", "thôi"}. The caller gates this on the clause
    being LAST: a mid-text "thôi" introducing a new topic
    ("Thôi, chuyện kia để sau đi") is discourse, not a
    withdrawal of the previous request."""
    toks = [f for f in folds[first:last + 1]]
    return toks in (["thoi"], ["nhung", "thoi"],
                    ["a", "khong", "thoi"])


# Particles that carry no condition content between a wait verb
# and "rồi": "đợi đã rồi làm" is a short pause, not a condition.
_WAIT_PARTICLES = {"da", "di", "nhe", "nha", "a", "oi", "ne"}
# Gap tokens allowed between a reference phrase and a trailing
# "khoan": discourse particles plus the reference phrase's own
# tail ("lúc nãy"). Anything else ("rồi" included) breaks the
# trailing-khoan scope.
_KHOAN_TAIL_TOKENS = {"da", "di", "nhe", "nha", "a", "oi", "ne",
                      "luc", "nay"}


def _clause_wait_then(folds, first, last):
    """Đợi/chờ + condition + rồi (+mới) làm: the action is
    deferred until a condition holds (round-3 fix F7). A wait
    verb followed, after at least one NON-particle token (the
    condition: "rảnh", "Vy trả lời"), by "rồi" and then "làm"
    (with only "mới" between) counts. "Đợi đã rồi làm" has
    only the particle "đã" in the gap: a short pause, not a
    condition, so it does NOT count (S15d7 stays continue).
    A duration gap ("đợi một lúc rồi làm") also defers: the
    action is not requested NOW, so blocking is the safe
    direction for it too."""
    for k in range(first, last + 1):
        if folds[k] not in ("doi", "cho"):
            continue
        for r in range(k + 1, last + 1):
            if folds[r] != "roi":
                continue
            gap = folds[k + 1:r]
            if not gap or all(t in _WAIT_PARTICLES
                              for t in gap):
                continue
            j = r + 1
            if j <= last and folds[j] == "moi":
                j += 1
            if j <= last and folds[j] == "lam":
                return True
    return False


def _clause_only_then(folds, first, last):
    """Bare "rồi mới làm": only-then, not a recount (round-3
    fix F7 trail). A "rồi" earlier in the clause before a
    "mới làm" pair means the action happens ONLY after
    something else: conditional, not past. Without a preceding
    "rồi", "mới làm" stays a recount ("mới làm như lúc nãy
    xong" = just did it) and is judged by past_before_lam.
    Outcome is blocked either way; only the reason differs,
    so a recount phrased with an earlier "rồi" mislabels as
    only-then without changing the gate outcome."""
    for k in range(first, last):
        if folds[k] == "moi" and folds[k + 1] == "lam":
            if any(folds[j] == "roi"
                   for j in range(first, k)):
                return True
    return False


def _clause_khoan_governs(folds, first, last, occs_in_clause):
    """True iff a "khoan" in this clause defers the referenced
    action itself (round-3 fix F8): khoan BEFORE a reference
    start or a "làm" with no "rồi" between ("Khoan làm như lúc
    nãy đã"), or khoan trailing the reference / "làm" with
    only particles or reference-phrase tail tokens between
    ("Làm như lúc nãy khoan đã"). "Khoan đã rồi làm như lúc
    nãy" does NOT govern: the "rồi" marks wait-then-do, so the
    khoan scopes the waiting, not the action (Md7 stays
    continue). A khoan in its OWN clause is judged by the
    trailing check in _clause_signal (Md6 stays blocked)."""
    ref_bounds = [(s, e) for (s, e, _k, _c) in occs_in_clause]
    lam_positions = [k for k in range(first, last + 1)
                     if folds[k] == "lam"]
    for k in range(first, last + 1):
        if folds[k] != "khoan":
            continue
        for (s, e) in ref_bounds:
            if k < s and "roi" not in folds[k + 1:s]:
                return True
            if k > e and all(t in _KHOAN_TAIL_TOKENS
                             for t in folds[e:k]):
                return True
        for p in lam_positions:
            if k < p and "roi" not in folds[k + 1:p]:
                return True
            if k > p and all(t in _KHOAN_TAIL_TOKENS
                             for t in folds[p + 1:k]):
                return True
    return False


def _clause_signal(raws, folds, clause_ids, bounds, cid, occs,
                   target_names, target_phones, is_last=False):
    """One clause's instruction signal: (signal, reason).

    signal in {"cancelled", "replaced", "blocked", "continue",
    "unknown", "none"}. "none" means the clause carries no
    instruction signal at all (distractor / noise); "unknown"
    means it carries a bare reference with no polarity. Only
    decisive signals (not "none"/"unknown") participate in
    last-decisive-wins."""
    first, last = bounds[cid]
    clause_occs = [o for o in occs if o[3] == cid]
    has_ref = bool(clause_occs)
    if has_ref and _clause_reported(raws, folds, first, last):
        return "blocked", "instruction_reported_speech"
    if _clause_cancelled(raws, folds, first, last, has_ref):
        tgt = _clause_cancel_target(raws, folds, clause_ids,
                                    bounds, cid, target_names,
                                    target_phones)
        if tgt == "different" and not _clause_has_lam_cancel(
                raws, folds, first, last):
            return "none", "cancel_other_target"
        return "cancelled", "instruction_cancelled"
    if _clause_replacement(raws, folds, clause_ids, bounds, cid,
                           target_names, target_phones):
        return "replaced", "instruction_replaced_by_new_target"
    if _clause_conditional(folds, first, last):
        return "blocked", "instruction_conditional_blocked"
    if _clause_is_question(raws, folds, first, last):
        return "blocked", "instruction_question_blocked"
    if "chua" in folds[first:last + 1]:
        return "blocked", "instruction_not_yet_blocked"
    if _clause_wait_then(folds, first, last):
        return "blocked", "instruction_wait_then_blocked"
    if _clause_only_then(folds, first, last):
        return "blocked", "instruction_only_then_blocked"
    if _clause_past_before_lam(folds, first, last):
        return "blocked", "instruction_recount_blocked"
    if has_ref and _clause_past_after_ref(
            folds, first, last, clause_occs[0][1]):
        return "blocked", "instruction_recount_blocked"
    if has_ref and _clause_khoan_governs(
            folds, first, last, clause_occs):
        return "blocked", "instruction_deferred_blocked"
    if has_ref:
        kind = clause_occs[0][2]
        if kind == "prior":
            if "lam" in folds[first:last + 1]:
                return "continue", "instruction_continuation"
        else:
            for verb in _find_verbs(folds, ("call", "message")):
                if clause_ids[verb["start"]] == cid \
                        and _verb_polarity(verb, raws, folds,
                                           clause_ids,
                                           bounds) == "positive":
                    return "continue", "instruction_continuation"
        return "unknown", "instruction_reference_no_signal"
    if is_last and _clause_bare_withdrawal(folds, first, last):
        return "cancelled", "instruction_withdrawn"
    if "khoan" in folds[first:last + 1]:
        return "blocked", "instruction_deferred_blocked"
    return "none", "no_signal"


def analyze_instruction_selection(text, target_names=(),
                                  target_phones=()):
    """Judge continuation of an anaphoric instruction reference.

    Returns {"instruction_selection": "continue"|"cancelled"|
    "replaced"|"blocked"|"unknown", "reason": str,
    "reference_present": bool}. VETO-ONLY: "continue" never
    proves a binding; only cancelled / replaced / blocked
    refuse an un-fire, and only in the adapter, after module A
    established a bound-reference selection.
    """
    if not isinstance(text, str) or not text.strip():
        return {"instruction_selection": "unknown",
                "reason": "no_current_text",
                "reference_present": False}
    # Quote check first (rule 1 analogue): a reference that
    # exists only inside quotes is reported speech, not a
    # request -- but it still counts as reference_present so
    # the adapter records WHY it refused.
    full_raws, full_folds, full_cids = _tokenize(_nfc(text))
    full_occs = _find_ref_occurrences(full_folds, full_cids) \
        if full_raws else []
    if not full_occs:
        return {"instruction_selection": "unknown",
                "reason": "no_instruction_reference",
                "reference_present": False}
    clean = _strip_quoted(_nfc(text))
    raws, folds, clause_ids = _tokenize(clean)
    occs = _find_ref_occurrences(folds, clause_ids) if raws else []
    if not occs:
        return {"instruction_selection": "blocked",
                "reason": "instruction_quoted_only",
                "reference_present": True}
    bounds = _clause_bounds(clause_ids)
    # LAST DECISIVE WINS: scan clauses in order; the last clause
    # carrying a decisive signal (cancelled / replaced /
    # blocked / continue) governs. "unknown" (bare reference)
    # and "none" (distractor / noise) clauses never override an
    # earlier decision: they carry no polarity of their own.
    operative = None
    last_cid = max(bounds) if bounds else None
    for cid in sorted(bounds):
        sig, reason = _clause_signal(raws, folds, clause_ids,
                                     bounds, cid, occs,
                                     target_names, target_phones,
                                     is_last=(cid == last_cid))
        if sig in ("cancelled", "replaced", "blocked",
                   "continue"):
            operative = (sig, reason)
    if operative is not None:
        return {"instruction_selection": operative[0],
                "reason": operative[1],
                "reference_present": True}
    return {"instruction_selection": "unknown",
            "reason": "instruction_reference_no_signal",
            "reference_present": True}


def analyze_topic_selection(text):
    """Judge a topic/amount-bound non-callback proposal's
    current text (S14): does it cancel / question / recount /
    condition / defer the bound topic, or positively continue
    it? VETO-ONLY, like layer C.

    A clause vetoes iff it BOTH mentions the topic (a prior
    -instruction reference, a "tin nhắn" reference, or an
    amount mention: a typed digit run or a number-word +
    money-unit phrase) AND carries a cancelled / question /
    conditional / "chưa" / recount / deferral signal. A
    positive clause with no such signal never vetoes. The
    single-topic assumption is documented in the module
    limitations: within a topic-bound verdict, an amount
    mention in a marked clause is read as the bound topic.
    Returns {"topic_selection": "cancelled"|"blocked"|
    "unknown", "reason": str, "topic_present": bool}.
    """
    if not isinstance(text, str) or not text.strip():
        return {"topic_selection": "unknown",
                "reason": "no_current_text", "topic_present": False}
    clean = _strip_quoted(_nfc(text))
    raws, folds, clause_ids = _tokenize(clean)
    if not raws:
        return {"topic_selection": "unknown",
                "reason": "no_current_text", "topic_present": False}
    bounds = _clause_bounds(clause_ids)
    occs = _find_ref_occurrences(folds, clause_ids)
    topic_present = bool(occs)
    operative = None
    for cid in sorted(bounds):
        first, last = bounds[cid]
        clause_folds = folds[first:last + 1]
        mentions = bool([o for o in occs if o[3] == cid])
        if not mentions:
            if any(f in ("tin", "nhan") for f in clause_folds):
                mentions = True
            if any(r[0] >= first and r[0] <= last
                   for r in _digit_runs(raws, folds, clause_ids)
                   if r[3] == "digits"):
                mentions = True
            if any(clause_folds[j] in _AMOUNT_WORDS
                   and clause_folds[j + 1] in _AMOUNT_WORDS
                   for j in range(len(clause_folds) - 1)):
                mentions = True
        if not mentions:
            continue
        topic_present = True
        if _clause_cancelled(raws, folds, first, last, False):
            operative = ("cancelled", "topic_cancelled")
        elif _clause_conditional(folds, first, last):
            operative = ("blocked", "topic_conditional_blocked")
        elif _clause_is_question(raws, folds, first, last):
            operative = ("blocked", "topic_question_blocked")
        elif "chua" in clause_folds:
            operative = ("blocked", "topic_not_yet_blocked")
        elif "khoan" in clause_folds:
            operative = ("blocked", "topic_deferred_blocked")
        elif _clause_past_before_lam(folds, first, last) \
                or _clause_past_after_ref(folds, first, last,
                                          first):
            operative = ("blocked", "topic_recount_blocked")
    if operative is not None:
        return {"topic_selection": operative[0],
                "reason": operative[1], "topic_present": True}
    return {"topic_selection": "unknown",
            "reason": "topic_no_signal",
            "topic_present": topic_present}


# Scheduling / reminder wrappers (folded patterns): a callback
# verb governed by one of these is NOT a call/message performed
# now -- it is a scheduled or reminded action (round-3 fix F6).
# "đặt lịch gọi", "đặt hẹn gọi", "nhắc ... gọi" all classify
# as "other". Only the three named patterns count: bare "hẹn"
# ("hẹn Vy" = meet) is not a wrapper.
_WRAPPER_PATTERNS = [["dat", "lich"], ["dat", "hen"], ["nhac"]]
# Generic-contact verb (folded pattern): "liên hệ" names
# contact without specifying call vs message. instruction_action
# reports it as "contact": compatible with, but not proof of,
# a call/message proposal (round-3 fix F5 inventory). Bare
# "liên lạc" is NOT in the inventory and stays "unknown".
_CONTACT_PATTERNS = [["lien", "he"]]


def _wrapped_verb_starts(folds, clause_ids, verbs):
    """Start indices of callback verbs governed by a wrapper in
    the same clause: a wrapper pattern precedes the verb with
    no "rồi" (sequence) between. "Gọi số X rồi đặt lịch họp"
    leaves the call unwrapped (it precedes the wrapper);
    "Đặt lịch họp rồi gọi số X" leaves it unwrapped too (the
    "rồi" sequences a separate later call)."""
    bounds = _clause_bounds(clause_ids)
    wrapped = set()
    for cid, (first, last) in bounds.items():
        ends = []
        for pat in _WRAPPER_PATTERNS:
            width = len(pat)
            for k in range(first, last - width + 2):
                if folds[k:k + width] == pat:
                    ends.append(k + width)
        if not ends:
            continue
        for verb in verbs:
            if clause_ids[verb["start"]] != cid:
                continue
            for wend in ends:
                if wend <= verb["start"] and "roi" not in \
                        folds[wend:verb["start"]]:
                    wrapped.add(verb["start"])
                    break
    return wrapped


# Lookup verb patterns (folded): verbs whose object is information
# to be retrieved, not a person to contact and not message
# content. "tra" alone is NOT included: it is also "trả" (give
# back), which is a transfer, not a lookup; only "tra cuu"
# (look up) is unambiguous.
_LOOKUP_PATTERNS = [["tim"], ["lay"], ["tra", "cuu"],
                    ["kiem", "tra"], ["xem"]]


def _find_lookup_verbs(folds):
    """Longest-match scan for lookup verb patterns."""
    patterns = sorted(_LOOKUP_PATTERNS, key=lambda p: -len(p[0]))
    verbs = []
    i = 0
    n = len(folds)
    while i < n:
        matched = None
        for pat in patterns:
            if folds[i:i + len(pat)] == pat:
                matched = len(pat)
                break
        if matched is not None:
            verbs.append((i, i + matched))
            i += matched
        else:
            i += 1
    return verbs


def _lookup_governor(folds, clause_ids, ms, blocker_starts):
    """Start of the lookup verb governing the mention at ms.

    The nearest lookup verb in the same clause before the
    mention, with no callback verb between it and the mention.
    A callback verb between lookup and mention breaks
    governance: the mention then belongs to the callback.
    Returns None when no lookup verb governs the mention.
    """
    cid = clause_ids[ms]
    gov = None
    for (s, _e) in _find_lookup_verbs(folds):
        if clause_ids[s] != cid or s >= ms:
            continue
        if any(s < b < ms for b in blocker_starts):
            continue
        if gov is None or s > gov:
            gov = s
    return gov


# Delegation matrix verbs (folded): "nho" (ask) / "bao" (tell).
# A callback verb governed by "nhờ / bảo + person + verb" in the
# same clause is the DELEGATEE's action, not the user's own
# positive selection (round-5 fix F-B4-6). Generic pronouns
# (em / anh / chi / minh ...) as the "person" do NOT count:
# "nhờ em gọi" asks the assistant itself, which is a direct
# request, not third-party delegation. A generic title followed
# by a real name ("anh Nam") does count. "bảo là / bảo sao /
# bảo rằng" never count: the token after the matrix verb must
# be a person, not a complementiser.
_DELEGATE_GENERIC = {"em", "anh", "chi", "minh", "ban", "toi",
                     "no", "nguoi", "ai", "co", "chu", "bac",
                     "di", "tao", "to"}
_DELEGATE_PERSON_STOPS = {
    "goi", "dien", "nhan", "gui", "sms", "la", "sao", "rang",
    "nhu", "the", "nay", "do", "day", "so", "di", "nhe", "nha",
    "a", "oi", "ma", "de", "thi", "ne", "voi", "cho", "toi",
    "den", "lam", "nua", "khong", "dung", "khoi", "chua",
    "da", "vua", "moi", "lai", "giup", "dum", "ho",
}


def _delegated_verb_starts(folds, clause_ids, verbs):
    """Start indices of callback verbs under delegation.

    A verb start is delegated when the same clause contains,
    before it, a matrix verb (nho / bao) + a person span (an
    optional generic title + a name, or 1-2 name tokens) +
    optional politeness (giup / dum / ho), with nothing else
    between the person span and the verb. "Nhờ Vy" with no
    following callback verb is unrelated and never matches.
    """
    bounds = _clause_bounds(clause_ids)
    verb_starts = {v["start"] for v in verbs}
    delegated = set()
    for cid, (first, last) in bounds.items():
        for i in range(first, last + 1):
            if folds[i] not in ("nho", "bao"):
                continue
            j = i + 1
            # "va" filler (round-6 fix M1): "nho va" is the
            # fixed phrase "ask a favour", not "nho" + a
            # person named "Va". Skip it BEFORE scanning the
            # person, so "nho va Vy goi" still delegates via
            # Vy while "nho va goi" (no person) does not
            # delegate at all. Merely adding "va" to the stops
            # would break the first case, so it must be a
            # skip, never a stop.
            if j <= last and folds[j] == "va":
                j += 1
            person = []
            if j <= last and folds[j] in _DELEGATE_GENERIC \
                    and j + 1 <= last \
                    and folds[j + 1] not in _DELEGATE_PERSON_STOPS \
                    and folds[j + 1] not in _DELEGATE_GENERIC \
                    and not folds[j + 1].isdigit():
                person = [j, j + 1]
                j += 2
            else:
                while j <= last and len(person) < 2 \
                        and folds[j] not in _DELEGATE_PERSON_STOPS \
                        and folds[j] not in _DELEGATE_GENERIC \
                        and not folds[j].isdigit():
                    person.append(j)
                    j += 1
            if not person:
                continue
            while j <= last and folds[j] in ("giup", "dum", "ho"):
                j += 1
            if j <= last and j in verb_starts:
                delegated.add(j)
    return delegated


def turn_fully_delegated(text, action):
    """True iff every queried-action verb in `text` is
    delegation-governed (round-7 fix S3).

    Same scope as the current-text delegation rule (nho / bao
    + person + verb, same clause; generic "nho em" is NOT
    delegation -- the person-span absorption eats the verb,
    so no delegated verb is found). A text with NO
    queried-action verb is NOT fully delegated: vacuous
    exclusion would wrongly drop turns that merely mention a
    number. Module A binding selection and the adapter fold
    use this: a delegated turn is another actor's
    instruction, never the user's own, so it must neither bind
    as a prior instruction nor revive a cancelled one.
    """
    if action not in ("call", "message") \
            or not isinstance(text, str) or not text.strip():
        return False
    _raws, folds, cids = _tokenize(_strip_quoted(_nfc(text)))
    if not folds:
        return False
    verbs = _find_verbs(folds, (action,))
    if not verbs:
        return False
    delegated = _delegated_verb_starts(folds, cids, verbs)
    return all(v["start"] in delegated for v in verbs)


# Forward / share verb patterns (folded) for the forward+bare
# rule (round-5 fix F-B4-4).
# Selection round: bare ["chuyen"] joins (ATK-019, the batch-8
# MINOR gap). The existing guards in _forwarded_target_to_other
# already enforce the recorded fix direction -- the forwarded
# object must be a target mention and the recipient must be
# cho/toi/den + a non-generic, non-target name -- so a bare
# "chuyển" without those (money transfers, "chuyển sang")
# does not suppress anything. The 2-token patterns still win
# on longest match in _find_other_verbs.
_FORWARD_PATTERNS = [["chuyen", "tiep"], ["chuyen"], ["forward"],
                     ["share"]]


def _forwarded_target_to_other(raws, folds, clause_ids, bounds,
                               verb_start, target_names,
                               targets_norm):
    """True iff the TARGET number was forwarded to a named
    recipient other than the target before verb_start.

    Discourse scope, not verb scope: a bare callback verb after
    such a forward has an elided target (the forwarded-to
    person? the number's owner? someone else?) and must never
    be read as a positive selection toward the proposal. Only
    a forward of the TARGET number counts (forwarding another
    number leaves the bare verb alone), only a NAMED
    non-generic recipient counts, and a recipient that IS one
    of the target names does not count (forwarding to the
    target herself is not forwarding away).
    Clause scope (round-6 fix S4): the forward may sit in the
    verb's own clause OR the immediately preceding clause of
    the SAME text -- punctuation must not flip one discourse
    unit ("... roi, goi di" / "... roi. Goi di" are the same
    unit as "... roi goi di"). Scope never crosses into
    another turn: a forward in a history turn is judged by
    the history mechanisms, not here.
    Forward recognition (round-7 fix S1+S2, one path):
      - backward scan skips CONTENT-LESS clauses: a clause
        with no verb, no digit run of length >= 2, and no
        other content ("tuy nhien", "thuc ra", bare "roi").
        The scan stops at the first content clause, which
        still breaks the unit (a content clause in between,
        e.g. a message clause, is NOT a hole). Names alone
        do not make a clause content: a bare vocative
        ("Vy oi") carries no proposition, and skipping it
        errs toward fire (the safe direction) for the bare
        verb that follows.
      - elided forward object: when the forward verb has no
        explicit target mention after it in its clause, its
        object resolves to the most recent TARGET mention
        before it in the SAME text ("tim so X roi chuyen
        tiep cho Binh" forwards X). Resolution is from TEXT,
        never from the proposal: forwarding another number
        ("tim so Y roi chuyen tiep cho Binh" for proposal X)
        does not suppress. If the most recent mention before
        the verb is not a target mention there is no
        resolution (recency wins; no fallback to an earlier
        target mention -- the forward is about the newer
        number, and the bare verb after it is judged by the
        other mechanisms, not by this suppression).
    """
    if not targets_norm:
        return False
    cid = clause_ids[verb_start]
    name_spans = _find_name_mentions(raws, folds,
                                     target_names or ())
    phone_mentions = _find_phone_mentions(
        raws, folds, clause_ids, bounds, targets_norm)
    # Eligible forward clauses: the verb's own clause, plus
    # the first content clause scanning backward, skipping
    # content-less clauses in between.
    verb_starts = {v["start"]
                   for v in _find_verbs(folds, ("call", "message"))}
    verb_starts.update(s for (s, _e) in _find_other_verbs(folds))
    digit_starts = {s for (s, _e, d, _k) in
                    _digit_runs(raws, folds, clause_ids)
                    if len(d) >= 2}

    def _contentless(c):
        # Bare number fragment (round-8 fix M2): a clause of
        # nothing but a digit run and the "số" marker
        # ("Số 12", "0912") carries no proposition -- like a
        # vocative, not like content -- so it must not break
        # the backward scan. A fragment WITH an assertion
        # ("số 12 là số mới") keeps its content status: any
        # token outside digit runs / spoken digit words /
        # "số" makes the clause content. This also removes
        # the 1-digit vs 2-digit inconsistency (a 1-digit
        # "Số 1" was already skipped by the digit-length
        # rule while "Số 12" was not).
        toks = [(raws[i], folds[i]) for i in range(len(folds))
                if clause_ids[i] == c]
        if toks and all(r.isdigit() or f in _DIGIT_WORDS
                        or f == "so" for (r, f) in toks):
            return True
        for idx in range(len(folds)):
            if clause_ids[idx] != c:
                continue
            if idx in verb_starts or idx in digit_starts:
                return False
        return True

    eligible = {cid}
    back = cid - 1
    while back >= 0 and _contentless(back):
        back -= 1
    if back >= 0:
        eligible.add(back)
    _GENERIC_RAW = {"mình", "em", "anh", "chị", "tôi", "bạn",
                    "người", "ai", "cô", "chú", "bác", "dì",
                    "tao", "tớ"}
    for (fs, fe) in _find_other_verbs(folds):
        fcid = clause_ids[fs]
        if fcid not in eligible or fs >= verb_start:
            continue
        # The forward verb must be a forward pattern, not any
        # other verb (luu / tim / ... are not forwards).
        matched_forward = False
        for pat in _FORWARD_PATTERNS:
            if folds[fs:fs + len(pat)] == pat:
                matched_forward = True
                break
        if not matched_forward:
            continue
        _ffirst, flast = bounds[fcid]
        # Object: an explicit target mention after the verb
        # in the forward clause, else the elided object =
        # the most recent target mention before the verb
        # anywhere earlier in the same text.
        has_object = False
        for (ms, me, _d) in phone_mentions:
            if clause_ids[ms] == fcid and fs < ms < verb_start:
                has_object = True
                break
        if not has_object:
            prior = [(ms, me) for (ms, me, _d) in phone_mentions
                     if ms < fs]
            if not prior:
                continue
        # Recipient: cho / toi / den + name after the forward
        # verb up to the end of the forward clause. Scanning
        # from the verb (not from the mention) also catches
        # "chuyen tiep cho Binh so X", where the recipient
        # precedes the number.
        for k in range(fe, flast + 1):
            if folds[k] not in ("cho", "toi", "den"):
                continue
            parts = []
            for cand in range(k + 1,
                              min(k + 3, flast + 1)):
                if folds[cand] in _NAME_SECOND_STOPS \
                        or folds[cand].isdigit():
                    break
                parts.append(cand)
                if len(parts) == 1 \
                        and raws[cand] in _GENERIC_RAW:
                    parts = []
                    break
            if not parts:
                continue
            rs, re_ = parts[0], parts[-1] + 1
            if any(ns < re_ and rs < ne
                   for (ns, ne) in name_spans):
                continue
            return True
    return False


def _find_other_verbs(folds):
    """Longest-match scan for non-communication verb patterns."""
    patterns = sorted(_OTHER_VERB_PATTERNS, key=lambda p: -len(p[0]))
    verbs = []
    i = 0
    n = len(folds)
    while i < n:
        matched = None
        for pat in patterns:
            if folds[i:i + len(pat)] == pat:
                matched = len(pat)
                break
        if matched is not None:
            verbs.append((i, i + matched))
            i += matched
        else:
            i += 1
    return verbs


def instruction_action(text):
    """Action class of a text's verbs.

    "call" (goi / dien only), "message" (nhan / gui / sms /
    tra loi only), "other" (recognised non-communication verbs
    only: luu / tra cuu / xoa / kiem tra / xem / tim / ghi --
    plus callback verbs governed by a scheduling / reminder
    wrapper: dat lich / dat hen / nhac), "contact" (generic
    contact only: "lien he" -- compatible with, but not proof
    of, a call/message), "both" (a mix of callback and other
    verbs, or call + message), or "unknown" (no recognised verb
    at all). Used by the adapter to compare a bound
    instruction's action with the proposal's action. A verb
    outside every inventory is "unknown": never guessed.
    """
    if not isinstance(text, str) or not text.strip():
        return "unknown"
    _raws, folds, cids = _tokenize(_strip_quoted(_nfc(text)))
    if not folds:
        return "unknown"
    verbs = _find_verbs(folds, ("call", "message"))
    wrapped = _wrapped_verb_starts(folds, cids, verbs)
    actions = {v["action"] for v in verbs
               if v["start"] not in wrapped}
    other = bool(_find_other_verbs(folds)) or bool(wrapped)
    if actions and other:
        return "both"
    if actions == {"call"}:
        return "call"
    if actions == {"message"}:
        return "message"
    if len(actions) > 1:
        return "both"
    if other:
        return "other"
    for pat in _CONTACT_PATTERNS:
        width = len(pat)
        for k in range(0, len(folds) - width + 1):
            if folds[k:k + width] == pat:
                return "contact"
    return "unknown"


def binding_action_class(text, target_names=(), target_phones=()):
    """Action class of a history turn FOR BINDING purposes
    (round-8 fix S1+M1, unified "binding action class").

    Like instruction_action, except the verb set is filtered
    to the turn's OWN immediate actions:
      - wrapper-governed verbs are excluded (as in
        instruction_action);
      - delegation-governed verbs are excluded: a delegated
        verb is another actor's action, never the user's own
        instruction, so it must not make the turn bind for
        that action;
      - forward-suppressed bare verbs are excluded: a bare
        callback verb after a forward of the target to another
        recipient has an undetermined target (round-7 S1+S2
        suppression), so it must not make the turn a
        call/message instruction when the turn later becomes
        history -- otherwise the S4 ambiguity is merely
        deferred one turn (round-7 batch S1).
    A verb with an explicit object is never suppressed: only
    bare verbs (empty object span) are checked against the
    forward rule, exactly as in analyze_action_selection.
    Suppression is target-relative: without target phones no
    forward can be recognised, so the check is skipped and
    the result degrades to instruction_action minus
    delegation. Labels match instruction_action's vocabulary
    ("call" / "message" / "other" / "both" / "contact" /
    "unknown"), with one deliberate narrowing: "both"
    means ONLY both callback actions (call AND message).
    A single callback action plus other verbs returns that
    callback action, NOT "both" -- unlike
    instruction_action, which returns "both" for any
    callback+other mix. The narrowing is required by the
    adapter's action-match check, which passes "both" for
    any callback proposal on the grounds that "both
    includes the proposal action": that ground holds only
    when the turn genuinely contains both callback
    actions. A message+forward turn must be "message"
    (mismatch-veto for a call proposal), not "both"
    (which would let the forward's bare verb smuggle a
    call instruction through layer C). Callers must pass
    the target names WITHOUT
    the bound turn's own addressee: the forward recipient
    must not be mistaken for the number's owner, or a
    forward to that recipient would wrongly escape
    suppression.
    """
    if not isinstance(text, str) or not text.strip():
        return "unknown"
    raws, folds, cids = _tokenize(_strip_quoted(_nfc(text)))
    if not folds:
        return "unknown"
    bounds = _clause_bounds(cids)
    verbs = _find_verbs(folds, ("call", "message"))
    wrapped = _wrapped_verb_starts(folds, cids, verbs)
    delegated = _delegated_verb_starts(folds, cids, verbs)
    targets_norm = [_norm_phone(p) for p in (target_phones or ())]
    targets_norm = [t for t in targets_norm if t]
    suppressed = set()
    for verb in verbs:
        if verb["start"] in wrapped or verb["start"] in delegated:
            continue
        span = _extract_object(verb, raws, folds, cids, bounds)
        if span[0] >= span[1] and _forwarded_target_to_other(
                raws, folds, cids, bounds, verb["start"],
                target_names or (), targets_norm):
            suppressed.add(verb["start"])
    actions = {v["action"] for v in verbs
               if v["start"] not in wrapped
               and v["start"] not in delegated
               and v["start"] not in suppressed}
    other = bool(_find_other_verbs(folds)) or bool(wrapped)
    # Narrowed "both" (see docstring): only call AND
    # message together count as "both". A single callback
    # action plus other verbs returns that action, so the
    # adapter's mismatch veto fires when the proposal
    # action differs -- the other verbs are not callback
    # actions and must not make the turn pass for the
    # other callback action.
    if actions == {"call"}:
        return "call"
    if actions == {"message"}:
        return "message"
    if len(actions) > 1:
        return "both"
    if other:
        return "other"
    for pat in _CONTACT_PATTERNS:
        width = len(pat)
        for k in range(0, len(folds) - width + 1):
            if folds[k:k + width] == pat:
                return "contact"
    return "unknown"


def phone_numbers_for_action(text):
    """{action: set(raw digit strings)} for digit mentions in
    `text`, associating each mention with its governing
    callback verb (round-8 fix M1).

    Association: a mention takes its nearest PRECEDING
    callback verb (verbs govern forward in Vietnamese).
    If that verb is delegated or wrapped, the mention
    belongs to another actor's action or a scheduled scope
    and is EXCLUDED -- it must not fall through to a later
    governing verb ("Nhờ Vy gọi số X giúp, nhắn cho Bình
    số Y đi": X's nearest preceding verb is the delegated
    "gọi", so X is not a message number, even though
    "nhắn" follows it). Only when NO callback verb
    precedes the mention does the nearest FOLLOWING
    governing verb apply (leading numbers, e.g. "Số X,
    gọi đi"). A "và"-chain of governing verbs shares one
    object ("gọi và nhắn số X" assigns X to both call and
    message, so a shared-object multi-number turn degrades
    to multiple / unbound instead of binding the wrong
    number); "rồi" is a sequence marker, not a conjunction,
    and never chains. Digit strings are returned raw
    (callers normalize with their own rule); they come
    from _digit_runs, so typed runs joined across spaces
    within a clause and spoken runs of >= 2 words are both
    covered. Only used for multi-number history turns:
    single-number turns bind through the old path
    unchanged, so this helper's heuristics never affect
    them.
    """
    if not isinstance(text, str) or not text.strip():
        return {}
    raws, folds, cids = _tokenize(_strip_quoted(_nfc(text)))
    if not folds:
        return {}
    verbs = _find_verbs(folds, ("call", "message"))
    if not verbs:
        return {}
    wrapped = _wrapped_verb_starts(folds, cids, verbs)
    delegated = _delegated_verb_starts(folds, cids, verbs)
    governing = [v for v in verbs
                 if v["start"] not in wrapped
                 and v["start"] not in delegated]
    if not governing:
        return {}
    gov_starts = {v["start"]: v for v in governing}

    def _chain(start):
        cur = gov_starts[start]
        acts = {cur["action"]}
        j = cur["start"] - 1
        while j >= 1 and folds[j] == "va":
            prev_v = gov_starts.get(j - 1)
            if prev_v is None:
                break
            acts.add(prev_v["action"])
            j = prev_v["start"] - 1
        j = cur["end"]
        while j + 1 < len(folds) and folds[j] == "va":
            nxt = gov_starts.get(j + 1)
            if nxt is None:
                break
            acts.add(nxt["action"])
            j = nxt["end"]
        return acts

    out = {}
    for (s, _e, digits, _kind) in _digit_runs(raws, folds, cids):
        if not digits:
            continue
        prev = [v for v in verbs if v["start"] < s]
        if prev:
            nearest = max(prev, key=lambda v: v["start"])
            if nearest["start"] not in gov_starts:
                continue
            acts = _chain(nearest["start"])
        else:
            gov_after = [v for v in governing if v["start"] > s]
            if not gov_after:
                continue
            nearest = min(gov_after, key=lambda v: v["start"])
            acts = _chain(nearest["start"])
        for act in acts:
            out.setdefault(act, set()).add(digits)
    return out


def phone_mentions_all_content(text, target_names=(),
                               target_phones=()):
    """True iff the text mentions target phones ONLY as message
    content for another recipient (round-4 fix S4, layer-C
    defense in depth). False when there is no target phone
    mention at all, or when any mention is a genuine
    recipient / channel mention. The adapter calls this for
    prior-instruction bindings so the content rule holds on
    both the B gate and the layer-C path; the B gate alone
    already refuses these cases for callback proposals.
    """
    if not isinstance(text, str) or not text.strip():
        return False
    targets_norm = [_norm_phone(p) for p in (target_phones or ())]
    targets_norm = [t for t in targets_norm if t]
    if not targets_norm:
        return False
    clean = _strip_quoted(_nfc(text))
    raws, folds, clause_ids = _tokenize(clean)
    if not raws:
        return False
    bounds = _clause_bounds(clause_ids)
    phone_mentions = _find_phone_mentions(
        raws, folds, clause_ids, bounds, targets_norm)
    if not phone_mentions:
        return False
    name_mentions = _find_name_mentions(raws, folds,
                                        target_names or ())
    mention_spans = [(s, e) for (s, e) in name_mentions] \
        + [(s, e) for (s, e, _d) in phone_mentions]
    verbs = _find_verbs(folds, ("call", "message"))
    wrapped = _wrapped_verb_starts(folds, clause_ids, verbs)
    verb_info = []
    for verb in verbs:
        polarity = "blocked" if verb["start"] in wrapped \
            else _verb_polarity(verb, raws, folds, clause_ids,
                                bounds)
        span = _extract_object(verb, raws, folds, clause_ids,
                               bounds)
        kind = _classify_object(span, folds, mention_spans)
        verb_info.append({**verb, "polarity": polarity,
                          "object_span": span,
                          "object_kind": kind})
    content = _content_phone_spans(
        raws, folds, clause_ids, bounds, target_names or (),
        phone_mentions, verb_info)
    all_spans = {(s, e) for (s, e, _d) in phone_mentions}
    return bool(content) and content == all_spans


# ---------------------------------------------------------------- main

def _sender_possessive_after(folds, clause_ids, ms, me):
    """True when a phone mention ending at `me` is immediately
    followed by a sender possessive ("cua toi / em / minh") in
    the same clause. Only unambiguous speaker pronouns count;
    "anh" / "chi" can also be a third person, so they keep
    the non-possessive reading."""
    cid = clause_ids[ms]
    return (me < len(folds) and clause_ids[me] == cid
            and folds[me] == "cua"
            and me + 1 < len(folds)
            and clause_ids[me + 1] == cid
            and folds[me + 1] in ("toi", "em", "minh"))


def _content_phone_spans(raws, folds, clause_ids, bounds,
                         target_names, phone_mentions, verb_info):
    """Phone mentions used as message CONTENT, not as recipient.

    A target phone mention is content when its clause names a
    different recipient (cho / tới / đến + a non-generic name
    that is not one of the target names, or a message verb whose
    object starts with such a name: "nhắn Vy số X") and the
    mention is not a channel ("nhắn cho Vy qua số X": "qua"
    makes X the channel, not content). A call verb governing
    the mention protects it: "gọi cho Vy số X" is the canonical
    call form (Vy is the callee, X her number), never content.
    A negated / blocked governing verb is left to the negation
    / blocking logic; content only refines positive readings.
    The owner exception: a recipient span overlapping a target
    name mention means the named person IS the bound
    counterpart, so the recipient reading stands -- EXCEPT when
    the mention carries a sender possessive (round-6 delta):
    "bang so X cua toi" asserts the number belongs to the
    sender, contradicting the roster-based owner reading, and
    current wins (N4 philosophy), so the owner exception does
    not rescue the mention and it stays content.
    Lookup-governed mentions (round-5 fix F-B4-3) are never
    content: a number governed by a lookup verb (tim / lay /
    tra cuu / kiem tra / xem) is the object of a lookup, not
    message content, even when a later clause names another
    recipient ("tim so X roi goi cho Vy"). The channel
    exception covers the prepositions qua / bang / o / theo /
    vao (round-5 fix F-B4-7); "tu" stays sender-side, never a
    channel ("nhan cho Vy tu so X" is still content).
    Sender-possessive carve-out (round-6 fix N5): "bang so X
    cua toi / em / minh" -- the number belongs to the sender
    (instrument), not to the recipient as an address, so the
    channel exception must not apply and the mention stays
    content. Only unambiguous speaker pronouns count here;
    "anh" / "chi" can also be a third person, so they keep
    the channel reading. Pinned reading (i) for bare-number
    channels: without a sender possessive, "nhan cho Binh
    bang so X" reads the number as the recipient's address,
    so the channel exception stands.
    Generic recipients ("cho em / anh / chị / mình") are NOT
    named recipients: the speaker-reference ambiguity is out of
    scope, and the existing contract treats them as generic.
    The generic check runs on RAW tokens so "mình" (pronoun)
    and "minh" (the name Minh, no diacritic) stay distinct.
    Returns a set of (start, end) phone-mention spans.
    """
    if not phone_mentions:
        return set()
    _GENERIC_RAW = {"mình", "em", "anh", "chị", "tôi", "bạn",
                    "người", "ai", "cô", "chú", "bác", "dì",
                    "tao", "tớ"}
    name_spans = _find_name_mentions(raws, folds,
                                     target_names or ())
    # Whole-text sender possessive (round-8 fix M3): the set
    # of numbers the text itself assigns to the sender
    # ("số X của tôi"), anywhere in the text. The owner
    # exception below is a roster FACT about a number's
    # owner; a sender possessive anywhere contradicts that
    # fact globally (current wins, N4 philosophy), so it
    # breaks the exception for every mention of that number,
    # not just the mention in the possessive's own clause.
    # Only a possessive OF THE SAME number breaks it: a
    # possessive of another number leaves the exception
    # standing. (The channel exception above keeps its
    # same-clause scope: the channel construction is local,
    # while the ownership fact is global.)
    possessive_phones = set()
    for (ps, pe, pd) in phone_mentions:
        if _sender_possessive_after(folds, clause_ids, ps, pe):
            possessive_phones.add(pd)
    content = set()
    for (ms, me, _d) in phone_mentions:
        cid = clause_ids[ms]
        first, last = bounds[cid]
        governing = None
        for info in verb_info:
            if clause_ids[info["start"]] == cid \
                    and info["start"] < ms:
                if governing is None \
                        or info["start"] > governing["start"]:
                    governing = info
        if governing is not None \
                and governing["action"] == "call":
            continue
        if governing is not None \
                and governing["polarity"] in ("negated", "blocked"):
            continue
        # Lookup-governed (F-B4-3): the number is the object of
        # a lookup verb, never message content.
        blocker_starts = [info["start"] for info in verb_info]
        if _lookup_governor(folds, clause_ids, ms,
                            blocker_starts) is not None:
            continue
        # Sender possessive immediately after the mention
        # ("so X cua toi / em / minh") reassigns the number
        # to the sender, so it cannot be the recipient's
        # channel address -- the channel exception below
        # must not apply (round-6 fix N5).
        sender_possessive = _sender_possessive_after(
            folds, clause_ids, ms, me)
        if not sender_possessive and any(
                p in folds[max(first, ms - 3):ms]
                for p in ("qua", "bang", "o", "theo", "vao")):
            continue
        recipient = None
        for k in range(first, last + 1):
            if folds[k] not in ("cho", "toi", "den"):
                continue
            parts = []
            for cand in range(k + 1, min(k + 3, last + 1)):
                if folds[cand] in _NAME_SECOND_STOPS \
                        or folds[cand].isdigit():
                    break
                parts.append(cand)
                if len(parts) == 1 \
                        and raws[cand] in _GENERIC_RAW:
                    parts = []
                    break
            if parts:
                recipient = (parts[0], parts[-1] + 1)
                break
        if recipient is None and governing is not None \
                and governing["action"] == "message":
            os_, oe = governing["object_span"]
            if os_ < oe and os_ < ms \
                    and folds[os_] not in _GENERIC_OBJECT_HEADS \
                    and folds[os_] != "so" \
                    and not raws[os_].isdigit() \
                    and folds[os_] not in _OBJECT_STOPS \
                    and raws[os_] not in _GENERIC_RAW:
                recipient = (os_, os_ + 1)
        if recipient is None:
            continue
        rs, re_ = recipient
        # Sender-possessive beats the owner exception (round-6
        # delta, whole-text scope round-8 fix M3): the current
        # text asserts the number belongs to the sender
        # ("bang so X cua toi"), which contradicts the
        # roster-based owner reading. Current wins (N4
        # philosophy): the owner exception must not rescue a
        # mention the text itself assigns to the sender, so
        # the mention stays content. Whole-text: a possessive
        # in another clause breaks the exception for every
        # mention of the SAME number (same tail-match rule
        # as the name-event break); a possessive of another
        # number does not.
        if not any(_d == p or _d.endswith(p)
                   for p in possessive_phones) and any(
                ns < re_ and rs < ne for (ns, ne) in name_spans):
            continue
        content.add((ms, me))
    return content


def _has_other_number(all_phone_runs, targets_norm, rejected_runs):
    """Competitor check + proper-substring exclusions (0676 fallback).

    Returns (has_other, substring_excluded). has_other is the
    exact inline predicate formerly computed inside
    analyze_action_selection: True when a phone-like run is
    neither rejected nor a substring (exact or proper) of a
    target phone. substring_excluded lists the phone-like runs
    excluded ONLY because they are PROPER substrings of a
    target (fragment groups such as a spoken prefix / middle /
    suffix group of the target) -- the 0676 mechanism. Exact
    target matches are excluded from has_other but are NOT
    listed: they are the target itself, not fallback evidence.
    With no target phones there is nothing to compete with
    (the pinned no-target generic test keeps its positive).
    Unit-testable in isolation: the end-to-end marker for
    this path is the reason
    "generic_callback_positive_substring_excluded" (see the
    general-events return in analyze_action_selection).
    """
    if not targets_norm:
        return False, []
    has_other = any(
        (s, e) not in rejected_runs
        and not any(d and d in t for t in targets_norm)
        for (s, e, d) in all_phone_runs)
    substring_excluded = [
        (s, e, d) for (s, e, d) in all_phone_runs
        if (s, e) not in rejected_runs and d
        and any(d in t and d != t for t in targets_norm)]
    return has_other, substring_excluded


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

    # All phone-like runs in the text, target or not
    # (round-10 fix S1): per-number government needs to
    # know about OTHER numbers, not just the target's.
    # Phone-like = the correction scan's predicate: typed
    # runs >= 9 digits, or spoken runs >= 7 digits / with
    # phone context in their clause. Short runs ("12",
    # "56") are tails / fragments, never competing numbers.
    # All digit runs (phone-like or not) are kept separately
    # for object classification (R5 fix S1): a verb whose
    # object span contains ANY digit run is specific, never
    # general -- the span, not the whole sentence, is the
    # object (government machinery, _extract_object).
    all_digit_runs = _digit_runs(raws, folds, clause_ids)
    all_digit_spans = [(s, e) for (s, e, _d, _k) in all_digit_runs]
    all_phone_runs = []
    for (rs, re_, rdigits, rkind) in all_digit_runs:
        if rkind == "digits":
            phone_like = len(rdigits) >= 9
        else:
            ccid = clause_ids[rs]
            cfirst, clast = bounds[ccid]
            phone_like = (len(rdigits) >= 7 or any(
                folds[k] in _PHONE_CONTEXT
                for k in range(cfirst, clast + 1)))
        if phone_like:
            all_phone_runs.append((rs, re_, _norm_phone(rdigits)))
    all_phone_spans = [(s, e) for (s, e, _d) in all_phone_runs]
    # A run after "không phải" in its clause is the
    # REJECTED value of a correction frame ("đuôi là 68
    # chứ không phải 86"), not a competing candidate: the
    # old tail must not make a bare verb ambiguous (gold
    # train_1677: tail correction + "gọi lại" re-calls
    # the NEW number). Only the first phone-like run
    # after the marker counts as rejected.
    rejected_runs = set()
    for (rs, re_, _d) in all_phone_runs:
        ccid = clause_ids[rs]
        cfirst, _clast = bounds[ccid]
        for k in range(cfirst, rs - 1):
            if folds[k] == "khong" and folds[k + 1] == "phai":
                if not any(s > k + 1 and s < rs
                           for (s, _e2, _d2) in all_phone_runs):
                    rejected_runs.add((rs, re_))
                break
    # A competing number exists when a phone-like run is
    # neither the target, nor a contiguous fragment of it
    # (a spoken number arrives in comma-separated groups:
    # gold train_0676 "không chín tám tám, sáu sáu năm,
    # năm bốn bốn năm" IS the target 09886655445, so its
    # prefix group 0988 is not a competitor), nor a
    # rejected correction value. With no target phones
    # there is nothing to compete with (the pinned
    # no-target generic test keeps its positive).
    # Extracted as _has_other_number (R5) so the fallback
    # is unit-testable in isolation; substring_excluded is
    # the proper-substring fragment groups only.
    has_other_number, substring_excluded = _has_other_number(
        all_phone_runs, targets_norm, rejected_runs)

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
    # Wrapper scope (round-4 fix S6): a callback verb governed
    # by a scheduling / reminder wrapper in the same clause
    # ("đặt lịch / đặt hẹn / nhắc ... gọi") with no "rồi"
    # between is not an immediate request -- it is blocked,
    # like a question-mood or past verb. "Gọi số X rồi đặt
    # lịch họp" leaves the call unwrapped (it precedes the
    # wrapper) and stays positive through the correct
    # mechanism, not through wrapper blindness.
    wrapped = _wrapped_verb_starts(folds, clause_ids, verbs)
    # Delegation scope (round-5 fix F-B4-6): a callback verb
    # governed by "nho / bao + person + verb" is the
    # delegatee's action, not the user's own selection -- it is
    # blocked exactly like a wrapper-governed verb.
    delegated = _delegated_verb_starts(folds, clause_ids, verbs)
    # Question scope (selection round, SEAL-004): a callback verb
    # inside a question clause is not a request at all -- an
    # echo-question ("Lúc nãy em bảo gọi số X nhỉ?") must not
    # read as positive selection, any more than a "có...không"
    # question-mood verb does (that frame was already blocked
    # inside _verb_polarity; the clause-level question frames
    # were not). Blocked exactly like a wrapper/delegated verb.
    questioned = {v["start"] for v in verbs
                  if _clause_is_question(
                      raws, folds,
                      *bounds[clause_ids[v["start"]]])}
    # Polarity + object classification per verb occurrence.
    verb_info = []
    for verb in verbs:
        polarity = "blocked" if verb["start"] in wrapped \
            or verb["start"] in delegated \
            or verb["start"] in questioned \
            else _verb_polarity(verb, raws, folds, clause_ids,
                                bounds)
        span = _extract_object(verb, raws, folds, clause_ids, bounds)
        kind = _classify_object(span, folds, mention_spans,
                                all_phone_spans, all_digit_spans)
        verb_info.append({**verb, "polarity": polarity,
                          "object_span": span, "object_kind": kind})

    # Forward-suppressed bare verbs (round-7 fix S1+S2) are
    # marked blocked HERE, not only in the general-events
    # block below: a bare verb after a forward of the target
    # to another recipient has an undetermined target, so it
    # is not a positive verb anywhere downstream -- not as a
    # mention governor, not as the lookup exception's
    # "later positive verb" (a suppressed verb must not
    # rescue its own lookup: "tim so X roi chuyen tiep cho
    # Binh goi di"), and not in the positive-verb fallback
    # (a suppressed verb is not "a positive verb for another
    # person" either: it has no determinable target at all).
    # The general-events block keeps its own forward check as
    # a backstop for the same condition.
    for info in verb_info:
        if info["polarity"] == "positive" \
                and info["object_span"][0] \
                >= info["object_span"][1] \
                and _forwarded_target_to_other(
                    raws, folds, clause_ids, bounds,
                    info["start"], target_names or (),
                    targets_norm):
            info["polarity"] = "blocked"

    # Number-as-content (round-4 fix S4): a phone mention that
    # is message content for another recipient never selects
    # the proposal's action toward that number. Content
    # mentions are removed from the event mentions only; the
    # mention itself stays recorded (mention_present).
    content_spans = _content_phone_spans(
        raws, folds, clause_ids, bounds, target_names or (),
        phone_mentions, verb_info)
    mentions = [(s, e, k) for (s, e, k) in mentions
                if (s, e) not in content_spans]

    # --- target-specific mention events: the nearest preceding
    # same-clause verb of the queried action governs the mention.
    # (start, kind, reason) with kind in positive/negated.
    events = []
    for (ms, me, _kind) in mentions:
        cid = clause_ids[ms]
        if _kind == "name":
            # Sender-possessive break (round-6 delta, whole-text
            # scope round-7 fix M1): the text asserts a target
            # phone belongs to the sender ("bang so X cua
            # toi"), breaking the name == number equivalence
            # the owner exception relies on. A name mention
            # must not generate a positive event toward that
            # number: the action targets the named person, not
            # the sender's number. Only a possessive mention OF
            # A TARGET phone breaks the equivalence; a
            # possessive mention of another number leaves the
            # name event standing. Scope is the WHOLE text:
            # "Nhan cho Vy di, so X cua toi la so moi" breaks
            # the equivalence just as the same-clause form
            # does -- the possessive phrase's own locality is
            # still checked by _sender_possessive_after (the
            # "cua toi / em / minh" must immediately follow
            # the mention in its clause).
            broke = False
            for (ps, pe, pdigits) in phone_mentions:
                if not any(pdigits == t or t.endswith(pdigits)
                           for t in targets_norm):
                    continue
                if _sender_possessive_after(folds, clause_ids,
                                            ps, pe):
                    broke = True
                    break
            if broke:
                continue
        governing = None
        for info in verb_info:
            if clause_ids[info["start"]] == cid \
                    and info["start"] < ms:
                if governing is None \
                        or info["start"] > governing["start"]:
                    governing = info
        if governing is None or governing["polarity"] == "blocked":
            continue
        # Per-number government (round-10 fix S1): a verb
        # does not govern a mention past an intervening
        # phone mention of a DIFFERENT number in the same
        # clause -- the verb governs the intervening number,
        # not this one. Exception: a "và"-chain shares one
        # object ("gọi số X và số Y" governs both); "rồi"
        # never chains, and mere juxtaposition does not
        # chain either. A re-mention (or tail) of the
        # target itself never blocks. Applies to negated
        # events too: a negation aimed past another number
        # is not target-attached to this one. Skipped when
        # the target has no known phones (name-only
        # proposals without roster/log): with nothing to
        # compare against, "different" is unjudgeable and
        # the old nearest-verb behaviour stands.
        if targets_norm:
            intervening = None
            for (ps, pe, pd) in all_phone_runs:
                if clause_ids[ps] == cid \
                        and governing["end"] <= ps and pe <= ms \
                        and not any(pd == t or t.endswith(pd)
                                    for t in targets_norm):
                    if intervening is None \
                            or ps > intervening[0]:
                        intervening = (ps, pe)
            if intervening is not None:
                chained = any(folds[k] == "va"
                              for k in range(intervening[1], ms))
                if not chained:
                    continue
        if governing["polarity"] == "negated":
            events.append((ms, "negated", "negated_selection"))
            continue
        # Bare "gui" phone rule (round-10 fix M1): "gửi"
        # is a transfer verb, so a bare number object with
        # no named recipient in the clause is ambiguous
        # (thing sent vs recipient) and does not select the
        # number ("Gửi số X đi" + sms X stays fired). A
        # named target owner in the same clause resolves
        # it: "Gửi Vy số X" (Vy owns X) is a message to Vy
        # at X. Longer "gui" patterns ("gui tin nhan",
        # "gui sms") are unambiguous messages and are
        # exempt. Name mentions are unaffected: a name
        # event stands on its own.
        if governing.get("pattern") == ["gui"] \
                and _kind == "phone":
            clause_names = [ns for (ns, _ne) in name_mentions
                            if clause_ids[ns] == cid]
            if not clause_names:
                continue
        events.append((ms, "positive", "positive_selection"))

    # Bare-verb ambiguity (round-10 fix S1, narrowed): a
    # bare / general verb is ambiguous only when the
    # proposal target itself is mentioned AND another
    # number exists. A bare verb in a text where the
    # target is NOT mentioned (e.g. a different number's
    # forward + bare call) stays a general positive: the
    # forward-suppression rule, not this rule, governs
    # that shape, and the bare verb may continue a prior
    # instruction. (Boundary: a forwarded number still
    # counts as "another number" here, so a forwarded +
    # bare-mention turn safe-fires; forward-object
    # detection would be needed to exempt it.)
    bare_verb_ambiguous = bool(phone_mentions) \
        and has_other_number

    # --- general events: object-less / generic-object verbs.
    general_events = []
    for info in verb_info:
        if info["polarity"] == "blocked":
            continue
        if info["object_kind"] == "general":
            # Bare/general verb in a bare-verb-ambiguous
            # turn (round-10 fix S1): a bare verb does not
            # select among competing numbers ("Gọi đi, số
            # X, số Y" authorises neither X nor Y alone --
            # ambiguous, so fire). Negated general verbs
            # still veto: a veto is safe direction even
            # when its target is undetermined.
            if info["polarity"] == "positive" \
                    and bare_verb_ambiguous:
                continue
            # Forward + bare callback (round-5 fix F-B4-4,
            # discourse scope): a BARE positive verb (empty
            # object) after the same clause forwarded the
            # target number to a named other recipient is not
            # a positive selection -- its elided target is
            # undetermined. Negated bare verbs still veto, and
            # verbs with an explicit object are unaffected.
            if info["polarity"] == "positive" \
                    and info["object_span"][0] \
                    >= info["object_span"][1] \
                    and _forwarded_target_to_other(
                        raws, folds, clause_ids, bounds,
                        info["start"], target_names or (),
                        targets_norm):
                continue
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
        # Fallback-path marker (R5, 0676 mechanism): this
        # bare-verb positive stands ONLY because proper-
        # substring fragment groups were excluded from the
        # competitor set -- without the exclusion,
        # bare_verb_ambiguous would have been True (target
        # mentioned + a competitor) and the general positive
        # would have been skipped. The marker fires only on
        # that decisive shape: substring fragments present,
        # no true competitor left, target mentioned. It is
        # a distinct reason (not a new selection value), so
        # adapter branching on selection / on
        # "generic_callback_negated" is untouched.
        if gkind == "negated":
            greason = "generic_callback_negated"
        elif substring_excluded and not has_other_number \
                and phone_mentions:
            greason = "generic_callback_positive_substring_excluded"
        else:
            greason = "generic_callback_positive"
        return {"selection": gkind, "reason": greason,
                "mention_present": mention_present}
    # Number-as-content (round-4 fix S4): every target mention
    # in the text is content for another recipient, and no
    # genuine selection event exists -- the request never
    # selects this action toward the number.
    if content_spans:
        return {"selection": "unknown",
                "reason": "number_as_content_for_other_recipient",
                "mention_present": mention_present}
    # Foreign action governing a genuine target mention
    # (round-4 fix S3): "chuyển tiếp / forward / share số X"
    # selects a different action for X, never a call/message
    # to X. Only when no queried-verb event exists for the
    # target: a genuine call/message event already governs
    # (events above), and a later generic queried verb
    # rescues via the general-events block above.
    # Lookup exception (round-5 fix F-B4-3, narrowed round-6
    # fix S3): a lookup-governed mention followed in the same
    # clause by a later positive queried verb is preparatory
    # to that verb, not a competing foreign action ("tim so X
    # roi goi cho Vy") -- but ONLY when that later verb
    # targets the proposal (object_kind "target": "goi cho
    # Vy" where Vy owns X) or is bare ("general": "tim so X
    # roi goi"). A later verb targeting a specific OTHER
    # person ("tim so X roi nhan cho Binh") never makes the
    # lookup preparatory to this proposal: the current text
    # selects a message to Binh, not to X, so the foreign
    # fallback below must veto.
    lookup_blockers = [v["start"] for v in verbs]
    for (ms, me, mkind) in mentions:
        if mkind != "phone":
            continue
        cid = clause_ids[ms]
        if _lookup_governor(folds, clause_ids, ms,
                            lookup_blockers) is not None \
                and any(info["start"] > ms
                        and clause_ids[info["start"]] == cid
                        and info["polarity"] == "positive"
                        and info["object_kind"] in ("target",
                                                    "general")
                        for info in verb_info):
            continue
        gov = None
        for (os_, _oe) in _find_other_verbs(folds):
            if clause_ids[os_] == cid and os_ < ms:
                if gov is None or os_ > gov:
                    gov = os_
        if gov is not None and not any(
                clause_ids[v["start"]] == cid
                and gov < v["start"] < ms for v in verbs):
            return {"selection": "unknown",
                    "reason": "other_action_verb_only",
                    "mention_present": mention_present}
    # No target event and no general event (round-10 fix S1,
    # narrowed after test failures): a positive verb is
    # "no veto" (the pinned veto-gate contract) EXCEPT when
    # it affirmatively selects something OTHER than this
    # target in a way that competes with a current-text
    # authorisation:
    # (F-a) the verb governs a DIFFERENT NUMBER (its object
    # span contains a phone-like run that is neither the
    # target nor a tail of it): the verb selects that
    # number, never this one;
    # (F-b) the target itself is mentioned BARE (no verb
    # of any action precedes the mention in its clause)
    # while a positive verb selects another entity: the
    # verb does not select the bare target;
    # (F-c) a bare "gui" verb whose phone event was skipped
    # by the M1 phone rule (bare number, no target name in
    # the clause): the verb does not select the number;
    # (F-d) a positive GENERAL verb in a bare-verb-ambiguous
    # turn (target mentioned + another number exists):
    # the bare verb selects neither number.
    # Otherwise a positive verb for another name (or a
    # general verb with no competition) is "no veto": the
    # pinned cases ("gọi Nguyễn Bình" for An, "gọi lại
    # cho An" for Vy, "gọi cho mẹ" for mom's number, M3
    # name-only "Gọi cho Vy nhé") keep their positive,
    # because the adapter -- never this module alone --
    # decides binding, and a new instruction for another
    # person does not cancel a prior instruction.
    positive_verbs = [info for info in verb_info
                      if info["polarity"] == "positive"]
    if positive_verbs:
        number_governed = any(
            any(ms < info["object_span"][1]
                and info["object_span"][0] < me
                for (ms, me, d) in all_phone_runs
                if not any(d and d in t
                           for t in targets_norm))
            for info in positive_verbs)
        all_verb_starts = [
            (v["start"], clause_ids[v["start"]])
            for v in _find_verbs(folds, ("call", "message"))]
        target_bare = False
        for (ms, _me) in ([(s, e) for (s, e) in name_mentions]
                          + [(s, e) for (s, e, _d)
                             in phone_mentions]):
            cid = clause_ids[ms]
            if not any(vs < ms and vc == cid
                       for (vs, vc) in all_verb_starts):
                target_bare = True
                break
        gui_skipped = False
        for info in positive_verbs:
            if info.get("pattern") != ["gui"]:
                continue
            vcid = clause_ids[info["start"]]
            clause_phones = [
                (ms, me) for (ms, me, _d) in phone_mentions
                if clause_ids[ms] == vcid
                and ms > info["start"]]
            clause_names = [
                ns for (ns, _ne) in name_mentions
                if clause_ids[ns] == vcid]
            if clause_phones and not clause_names:
                gui_skipped = True
                break
        bare_general = any(
            info["object_kind"] == "general"
            for info in positive_verbs) and bare_verb_ambiguous
        if number_governed or target_bare or gui_skipped \
                or bare_general:
            return {"selection": "unknown",
                    "reason": "positive_verb_not_governing_target",
                    "mention_present": mention_present}
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
    wrapped_all = _wrapped_verb_starts(folds, clause_ids,
                                       all_verbs)
    delegated_all = _delegated_verb_starts(folds, clause_ids,
                                           all_verbs)
    questioned_all = {v["start"] for v in all_verbs
                      if _clause_is_question(
                          raws, folds,
                          *bounds[clause_ids[v["start"]]])}
    all_pols = ["blocked" if v["start"] in wrapped_all
                or v["start"] in delegated_all
                or v["start"] in questioned_all
                else _verb_polarity(v, raws, folds, clause_ids,
                                    bounds)
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


def analyze_selection_consistency(text, action, target_names=(),
                                  target_phones=(), roster=(),
                                  history_texts=()):
    """Selection-consistency check for KNOWN references
    (selection round).

    The adapter calls this ONLY when the baseline gate PASSED
    (see the pin boundary in the adapter): a passed proposal
    previously received NO selection check at all, because
    adjustment 1 runs only on the fired path. The gap was that
    a confirmed number / ID was waved through before anyone
    checked the right person, the right action, or the right
    role for that number.

    Returns {"consistent": True} or {"consistent": False,
    "mismatch": kind, "detail": str}. Structured decision
    fields (H2-S11 only, check 5 blocked_verb_only with a
    direct past-governing verb): a question-clause past
    govern over a still-pending history positive returns
    decision "unknown_pending", unknown_kind
    "question_after_positive", active_status
    "pending_unproven", blocked_subtype "question" and
    mismatch "unknown_pending" -- still consistent False,
    so a binary caller still fires. A declarative past
    govern, or a question over a discharged / cancelled /
    absent history positive, returns decision "mismatch"
    with active_status "discharged" / "cancelled" /
    "replaced" / "none" and blocked_subtype "completion" /
    "question". Other mismatch kinds keep the old shape in
    this round; their statuses are not invented here.
    Abstention is
    "consistent": an unresolvable text is NOT a contradiction
    -- but an explicit contradiction (a different person, a
    different action, a delegated action, an undistinguished
    duplicate name, a money/content role for the number, or a
    bare/question-only mention) IS a mismatch. There is no
    "permitted" verdict here: the caller turns a mismatch
    into a shadow fire, and a consistent result leaves the
    baseline pass alone.

    History (history_texts: prior user-turn texts from the
    adapter's prefix) fills exactly two gaps, and no others:
    a duplicate name the conversation previously QUALIFIED
    for a SPECIFIC entry (see _history_qualified_entries:
    a history turn naming the person with that entry's phone
    qualifies that entry alone, and only when the phone is
    governed by a positive verb of the proposal action or
    is a standalone identity reference -- a phone governed
    by another action's positive verb qualifies nothing
    (including a long appositive governed across clauses,
    round 4); a noun descriptor adjacent to the name
    qualifies NOTHING in round 4 (G5 R1 KNOWN-OPEN-FAIL,
    NOT FOR RUNTIME USE: descriptor-only evidence must
    not pass all duplicates, and the old pinned "Minh
    khach hang" pass is therefore intentionally broken
    until re-pinned) is not an ambiguity the current
    text creates,
    and a BLOCKED current verb (past / question / status:
    no current request signal) does not cancel a prior turn
    that positively selected this proposal -- but only while
    that history-positive state is still ACTIVE (a later
    negated / replaced / cancelled history turn revokes it),
    and never when the current turn itself directly states
    the proposal as completed (a past verb directly
    governing the proposal phone/name). Active current
    vetoes (negated / replaced / cancelled, a different
    action, a different person) always win over history:
    the current turn is the latest instruction.

    Checks, in order (first mismatch wins):
    1. delegation -- the whole action is another actor's job
       (turn_fully_delegated);
    2. duplicate_name -- a positively governed name maps to
       >= 2 roster entries (R4-PHONE-GUARD: entries, not
       distinct known phones, so an UNKNOWN/empty phone
       does not collapse the guard), the proposal is to
       one of them, no digit run equal to any duplicate
       phone appears in the text, and history does not
       qualify the PROPOSAL entry (see
       _history_qualified_entries);
    3. B decisive vetoes -- negated / replaced / cancelled;
    4. early matched-pass -- the positive selection set
       (including correction re-scoping, below) contains
       the proposal;
    5. B unknown-mismatch mapping -- other_action_verb_only
       -> action_mismatch, blocked_verb_only ->
       blocked_request (unless history-positive is still
       ACTIVE for the proposal and no current past verb
       directly governs the proposal), negated_other_object
       -> negated,
       number_as_content_for_other_recipient ->
       money_or_content_role. positive_verb_not_governing_
       target is DELIBERATELY NOT mapped: when a verb
       governs an explicit non-target, check 6 fires with
       the better kind; when no verb governs anything
       explicit (bare "goi lai", a pronoun object like
       "anh ay" / "han"), there is no contradiction to
       report -- an anaphoric or bare verb is not a wrong
       selection;
    6. positive-selection-set mismatch -- the set of
       (action, person) pairs governed by positive callback
       verbs (plus correction re-scoping) is non-empty and
       contains no pair matching the proposal. The
       action_mismatch branch abstains when a verb of the
       proposal action exists in the text AND the proposal
       person is mentioned: a bare verb with a discourse
       recipient ("nhan tin" after naming the teacher) is
       an implicit selection, not a mismatch;
    7. money_or_content_role -- every digit run equal to a
       proposal phone is in a money role ("tien X" /
       "X dong/nghin/trieu/ty/vnd") or an old-number role
       ("so cu/truoc X" / "X la so cu");
    8. bare_or_question_mention -- the proposal target is
       mentioned, but every mention sits in a question clause,
       or the text contains no verb of any action at all.

    Correction re-scoping (check 4/6): a bare recipient
    clause ("cho Tuan") immediately following a correction
    clause ("a khong") rebinds the nearest preceding
    positive callback verb's recipient to that clause's
    person -- "nhan ti so cho ong Ba, a khong, cho Tuan"
    selects Tuan for the message, it does not leave the
    message recipient ungoverned.

    Person identity is a roster-entry index when a name or
    phone resolves to exactly one roster entry, else the raw
    folded name / normalized digits -- so a name and a phone
    belonging to the same entry (with or without an id)
    resolve to the same key. A number glued to a unit
    ("100d") is NOT a digit run anywhere in this module
    (see _WORD_RE / _digit_runs), so step 7 only sees
    spaced forms; a glued money amount next to a selection
    is left to the selection set.
    """
    if action not in ("call", "message") \
            or not isinstance(text, str) or not text.strip():
        return {"consistent": True}
    targets_norm = [_norm_phone(p) for p in (target_phones or ())]
    targets_norm = [t for t in targets_norm if t]
    if not targets_norm and not target_names:
        return {"consistent": True}
    clean = _strip_quoted(_nfc(text))
    raws, folds, clause_ids = _tokenize(clean)
    if not raws:
        return {"consistent": True}
    bounds = _clause_bounds(clause_ids)
    roster = [e for e in (roster or ()) if isinstance(e, dict)]

    def _entries_for_name(fold):
        out = []
        for idx, e in enumerate(roster):
            parts = _fold(str(e.get("name") or "")).split()
            if parts and (_fold(str(e.get("name") or "")) == fold
                          or parts[-1] == fold):
                out.append(idx)
        return out

    def _entries_for_phone(norm):
        return [idx for idx, e in enumerate(roster)
                if _norm_phone(e.get("phone") or "") == norm]

    def _name_key(fold):
        idxs = _entries_for_name(fold)
        if len(idxs) == 1:
            return ("entry", idxs[0])
        return ("name", fold)

    def _phone_key(norm):
        idxs = _entries_for_phone(norm)
        if len(idxs) == 1:
            return ("entry", idxs[0])
        return ("phone", norm)

    proposal_key = None
    for t in targets_norm:
        proposal_key = _phone_key(t)
        break
    if proposal_key is None:
        for nm in (target_names or ()):
            proposal_key = _name_key(_fold(str(nm)))
            break
    if proposal_key is None:
        return {"consistent": True}

    def _mismatch(kind, detail):
        return {"consistent": False, "mismatch": kind,
                "detail": detail}

    def _s11_result(decision, active_status, blocked_subtype,
                    mismatch, detail, last_kind=None,
                    last_index=None):
        # H2-S11 structured result. consistent stays False
        # in every case: the execution tier never passes on
        # a question/status turn. last_event.turn_position
        # is the index inside history_texts (the order the
        # adapter passes user turns), not a global prefix
        # position -- the adapter can enrich it later.
        out = {"consistent": False, "decision": decision,
               "active_status": active_status,
               "blocked_subtype": blocked_subtype,
               "mismatch": mismatch, "detail": detail}
        if decision == "unknown_pending":
            out["unknown_kind"] = "question_after_positive"
            out["reason"] = \
                "history_positive_pending_but_no_current_positive"
        if last_kind is not None:
            out["last_event"] = {
                "kind": last_kind, "turn_position": last_index,
                "evidence": "history_text"}
        return out

    def _clause_is_s11_question(q_raws, q_folds, q_first,
                                q_last):
        # Question mood for a past-govern clause. The
        # shared _clause_is_question covers co/khong, verb
        # + khong/ha/chu and nhi frames, but NOT the
        # "... da <verb> ... chua?" frame: the tokenizer
        # drops "?", leaving a final "chua" (not-yet)
        # token. A clause ending in "chua" is a question
        # about completion, not a completion statement;
        # "roi" (or no particle) is declarative completion.
        # This is a mood test on any clause, not a match
        # on any particular sentence.
        return _clause_is_question(q_raws, q_folds, q_first,
                                   q_last) \
            or q_folds[q_last] == "chua"

    # 1. Delegation.
    if turn_fully_delegated(text, action):
        return _mismatch("delegation",
                         "action delegated to another person")

    # Positive verb inventory (shared by checks 2 and 4).
    verbs = _find_verbs(folds, ("call", "message"))
    wrapped = _wrapped_verb_starts(folds, clause_ids, verbs)
    delegated = _delegated_verb_starts(folds, clause_ids, verbs)
    questioned = {v["start"] for v in verbs
                  if _clause_is_question(
                      raws, folds,
                      *bounds[clause_ids[v["start"]]])}
    # RAW roster names (full + last token) for mention search:
    # _find_name_mentions matches single-token names
    # diacritic-SENSITIVELY on raw tokens, so folded names
    # ("binh") never match raw text ("bình") -- passing folds
    # here silently drops every diacritic name from the
    # selection set (selection-round fix for ATK-001/009).
    # The fold is taken from the MATCHED span's folds below,
    # not from this list.
    roster_names_raw = set()
    for e in roster:
        parts = _nfc(str(e.get("name") or "")).split()
        if parts:
            roster_names_raw.add(_nfc(str(e.get("name") or "")))
            roster_names_raw.add(parts[-1])
    all_runs = _digit_runs(raws, folds, clause_ids)
    # Positive selections: (action, person_key) per verb, plus
    # the governed names of proposal-action verbs (check 2).
    selections = set()
    governed_names = []
    positive_verbs = []
    for v in verbs:
        if v["start"] in wrapped or v["start"] in delegated \
                or v["start"] in questioned:
            continue
        if _verb_polarity(v, raws, folds, clause_ids,
                          bounds) != "positive":
            continue
        positive_verbs.append(v)
        span = _extract_object(v, raws, folds, clause_ids,
                               bounds)
        if span[0] >= span[1]:
            continue
        for (ns, ne) in _find_name_mentions(
                raws, folds, sorted(roster_names_raw)):
            if span[0] <= ns and ne <= span[1]:
                fold = folds[ns] if ne - ns == 1 \
                    else " ".join(folds[ns:ne])
                selections.add((v["action"], _name_key(fold)))
                if v["action"] == action:
                    governed_names.append(fold)
        for (rs, re_, digits, _kind) in all_runs:
            if span[0] <= rs and re_ <= span[1]:
                selections.add((v["action"],
                                _phone_key(_norm_phone(digits))))
    # Correction re-scoping: a bare recipient clause
    # ("cho Tuan") immediately after a correction clause
    # ("a khong", comma-separated) rebinds the nearest
    # preceding positive callback verb's recipient.
    ordered_clauses = sorted(bounds)
    for ci in range(1, len(ordered_clauses)):
        first, last = bounds[ordered_clauses[ci]]
        if folds[first] not in ("cho", "toi", "den"):
            continue
        prev_first, prev_last = bounds[ordered_clauses[ci - 1]]
        prev = folds[prev_first:prev_last + 1]
        if prev not in (["a", "khong"], ["khong"]):
            continue
        recip = None
        for (ns, ne) in _find_name_mentions(
                raws, folds, sorted(roster_names_raw)):
            if first <= ns and ne <= last + 1:
                fold = folds[ns] if ne - ns == 1 \
                    else " ".join(folds[ns:ne])
                recip = _name_key(fold)
                break
        if recip is None:
            for (rs, re_, digits, _k) in all_runs:
                if first <= rs and re_ <= last + 1:
                    recip = _phone_key(_norm_phone(digits))
                    break
        if recip is None:
            continue
        before = [v for v in positive_verbs
                  if v["start"] < first]
        if before:
            selections.add((before[-1]["action"], recip))

    # History qualification for duplicates (H1 fix,
    # C3-G3-01): the old boolean _history_qualifies said
    # only "some history turn qualified the NAME", which
    # let one entry's evidence pass every duplicate. The
    # replacement returns the SET of roster entries history
    # actually qualifies, scanned in order:
    # (1) PHONE: a history turn that mentions the name AND
    # contains a digit run equal to exactly one duplicate
    # phone qualifies that entry ALONE -- "Goi cho Binh so
    # 0903111222" qualifies A, never B. A later phone turn
    # for another duplicate replaces the set (a correction
    # to the newer number wins); a later negated /
    # replaced / cancelled turn for the qualified phone
    # revokes it, and phone evidence, once seen, supersedes
    # descriptor evidence (a descriptor turn never widens
    # a phone-qualified set back to all duplicates). A turn
    # matching two duplicate phones qualifies neither: it
    # does not disambiguate. ACTION-SCOPING (round 3, L5
    # adjudication, matching the blocked_verb_only branch
    # and G1 R1): the phone qualifies only when it is
    # governed by a positive verb of the SAME action as
    # the proposal, or when it is a standalone identity
    # reference governed by no positive callback verb at
    # all. A phone governed by a positive verb of a
    # DIFFERENT action only ("Nhan tin cho Binh so A" for
    # a call proposal) qualifies NOTHING -- both arms
    # block.
    # GOVERNMENT, ROUND 4 (Run 2, G5 FIX_REQUIRED): the
    # round-3 test -- phone run inside the verb's
    # _extract_object span (at most 3 tokens) -- is too
    # narrow for a LONG APPOSITIVE: in "Nhan tin cho
    # Binh, <long description>, so A" the phone sits in
    # a bare fragment clause AFTER the verb's clause, so
    # round 3 fell back to standalone and wrongly
    # qualified A for a call proposal. A phone is now
    # governed by a positive verb when ANY of these hold:
    # (a) the phone run is inside the verb's object span
    # (round 3); (b) the phone run is in the SAME clause
    # as the verb, AFTER the verb, and the verb's object
    # span contains a mention of the duplicate name (the
    # verb governs the person, the phone is that
    # person's number stated later in the clause); (c)
    # the phone run is in a LATER bare-fragment clause
    # (no callback verb, no roster-name mention in that
    # clause, only this phone run in it), an earlier
    # clause's positive verb governs the duplicate name,
    # and every clause between them is CLEAN in the
    # round-5 sense: no roster-name mention (an
    # intervening person), no ROSTER-PHONE run (other
    # digit runs -- ages, years, rooms, counts -- are
    # not phones and do not break), and no truly
    # governing callback verb (its object span must
    # contain a roster name or a roster phone; a
    # verb-like token inside a noun phrase governs
    # nothing and does not break). A phone whose own
    # clause
    # names the person ("So cua Binh la A") is an
    # identity clause, not a bare fragment, so (c)
    # never fires on it: it stays standalone. No name,
    # phone, number or sentence is hardcoded here:
    # matching is by roster phone equality, name mention
    # and verb government only.
    # (2) DESCRIPTOR, ROUND 4 (Run 2, G5 R1
    # KNOWN-OPEN-FAIL, NOT FOR RUNTIME USE): a noun
    # descriptor immediately adjacent to the name ("Minh
    # khach hang") qualifies NOTHING. A descriptor does
    # not prove which entry it is, so descriptor-only
    # evidence must not pass all duplicates -- round 3
    # returned all duplicates here and that was the
    # false-pass residual. This deliberately changes the
    # old pinned "Minh khach hang" pass: that repo test
    # now FAILS until L5/G5 re-pin it, and that failure
    # is reported, not hidden by editing the test (only
    # this file may change in round 4).
    # R4 VERB-COLLISION (Run 4, this branch): the D1
    # unique-structured-match rule below is unchanged,
    # but a post-name descriptor whose FIRST folded token
    # is in _GENERAL_VERBS no longer loses its phrase
    # entirely: when the ordinary scan collects nothing
    # after the name, a same-clause run of >= 2 tokens
    # that EXACTLY equals a duplicate's structured
    # attribute is collected as the descriptor phrase
    # (see the rescue in the mention loop). A verb
    # clause still collects nothing, because its run is
    # not an attribute and a single verb token is never
    # accepted. No word, name or sentence is whitelisted:
    # the only vocabulary is the roster's own attributes.
    # (3) NOT QUALIFYING: adjacent prepositions / particles
    # / discourse tokens in _QUALIFIER_STOP ("cho Minh",
    # "Minh nhe"), any adjacent VERB (the name is the
    # subject of a declarative clause, not a referring
    # expression: "Binh an com roi" -- "an" is a verb, so
    # the turn qualifies nothing), phone introducers
    # ("so") and name words ("ten") -- none of these is a
    # noun descriptor. The verb test uses a general list
    # of frequent Vietnamese verbs, not a per-sentence
    # list: any other verb in that position is excluded
    # the same way.
    _QUALIFIER_STOP = {"cho", "toi", "den", "la", "cua", "va",
                       "thi", "ma", "a", "oi", "nhe", "nha", "di",
                       "roi", "nay", "do", "ay", "de", "o", "tu",
                       "voi", "giup"}
    _GENERAL_VERBS = {
        "an", "uong", "ngu", "thuc", "day", "di", "den", "ve",
        "sang", "lam", "noi", "bao", "hoi", "dap", "nghe",
        "nhin", "doc", "viet", "hoc", "choi", "mua", "ban",
        "tra", "lay", "dua", "mo", "dong", "bat", "tat",
        "rua", "nau", "don", "gap", "doi", "song", "o", "co",
        "can", "muon", "thich", "nho", "quen", "biet",
        "hieu", "nghi", "tuong", "so", "ghet", "yeu",
        "cuoi", "khoc", "chay", "nhay", "boi", "hat", "goi",
        "dien", "nhan", "gui", "tim", "xem", "kiem", "song",
        "chet", "benh", "kho", "met", "vui", "buon"}
    # Function words that are never a noun descriptor, even
    # though they are not in _QUALIFIER_STOP: time words
    # ("hom qua Lan ..." -- "qua" is the tail of "hom qua",
    # not a role noun), aspect markers ("Binh da ..."),
    # and adverbs ("Binh rat ...", "Lan cung ...").
    _DESCRIPTOR_EXCLUDE = {
        "hom", "qua", "sang", "trua", "chieu", "dem", "mai",
        "ngay", "thang", "tuan", "gio", "phut", "giay",
        "truoc", "sau", "luc", "khi", "hien",
        "da", "moi", "vua", "dang", "se", "chua",
        "rat", "kha", "cung", "lai", "con", "thoi", "nua",
        "van", "chi", "ngay"}

    def _is_noun_descriptor(tok):
        if tok is None:
            return False
        if tok in _QUALIFIER_STOP or tok in _GENERAL_VERBS \
                or tok in _VERB_HEADS \
                or tok in _DESCRIPTOR_EXCLUDE:
            return False
        if tok.isdigit() or tok in _DIGIT_WORDS:
            return False
        # Phone introducer / name word: not a role noun.
        if tok in ("so", "ten", "nguoi", "rang"):
            return False
        return True

    def _history_qualified_entries(idxs):
        dup_phones = {}
        for i in idxs:
            phone = _norm_phone(roster[i].get("phone") or "")
            if phone:
                dup_phones.setdefault(phone, []).append(i)
        if not dup_phones:
            return set()
        raw_names = set()
        for i in idxs:
            parts = _nfc(str(roster[i].get("name") or "")).split()
            if parts:
                raw_names.add(_nfc(str(roster[i].get("name")
                                     or "")))
                raw_names.add(parts[-1])
        if not raw_names:
            return set()
        # All roster names (full + last token), for the
        # round-4 discourse check: a bare-fragment clause
        # or an intervening clause must mention NO roster
        # person at all, not just no duplicate, or the
        # appositive link is broken by another person.
        all_roster_names = set()
        all_roster_phones = set()
        for e in roster:
            parts = _nfc(str(e.get("name") or "")).split()
            if parts:
                all_roster_names.add(_nfc(str(e.get("name")
                                            or "")))
                all_roster_names.add(parts[-1])
            ph = _norm_phone(e.get("phone") or "")
            if ph:
                all_roster_phones.add(ph)
        phone_qualified = None
        phone_seen = False
        descriptor_phrases = []
        # R4 verb-collision anchor: the structured attribute
        # token sequences of the duplicate entries only
        # (every roster field other than id/name/phone,
        # folded the same way as the D1 check below).
        # These sequences -- never a name, word or sentence
        # list -- are the ONLY vocabulary the post-name
        # rescue below may use, so a rescue can fire only
        # for an attribute the roster itself carries.
        dup_attr_seqs = []
        for _i in idxs:
            for _key, _val in (roster[_i] or {}).items():
                if _key in ("id", "name", "phone"):
                    continue
                if not isinstance(_val, str) or not _val.strip():
                    continue
                _seq = [_fold(_t) for _t in
                        re.findall(r"[^\W_]+", _nfc(_val))]
                if _seq:
                    dup_attr_seqs.append(_seq)
        for htext in (history_texts or ()):
            if not isinstance(htext, str) or not htext.strip():
                continue
            hraws, hfolds, hcids = _tokenize(
                _strip_quoted(_nfc(htext)))
            mentions = _find_name_mentions(
                hraws, hfolds, sorted(raw_names))
            if not mentions:
                continue
            matched = {_norm_phone(d)
                       for (_s, _e, d, _k)
                       in _digit_runs(hraws, hfolds, hcids)
                       if _norm_phone(d) in dup_phones}
            if len(matched) == 1:
                phone = next(iter(matched))
                # A phone turn is decided by its phone, not
                # by any descriptor in the same turn -- even
                # when the phone itself is shared by several
                # entries and therefore qualifies none.
                phone_seen = True
                if len(dup_phones[phone]) == 1:
                    entry = dup_phones[phone][0]
                    # Action-scoping (round 3): which
                    # positive callback verbs govern this
                    # phone run, in the module's own
                    # _extract_object sense? Governed by
                    # another action only -> qualifies
                    # nothing (S05). Governed by the
                    # proposal action (alone or also by
                    # another action) or by no positive
                    # callback verb (standalone identity
                    # reference) -> may qualify, subject
                    # to the veto check below.
                    hruns = _digit_runs(hraws, hfolds, hcids)
                    hbounds = _clause_bounds(hcids)
                    hverbs = _find_verbs(hfolds,
                                         ("call", "message"))
                    hwrapped = _wrapped_verb_starts(
                        hfolds, hcids, hverbs)
                    hdelegated = _delegated_verb_starts(
                        hfolds, hcids, hverbs)
                    hquestioned = {
                        v["start"] for v in hverbs
                        if _clause_is_question(
                            hraws, hfolds,
                            *hbounds[hcids[v["start"]]])}
                    phone_spans = [
                        (rs, re_) for (rs, re_, d, _k)
                        in hruns
                        if _norm_phone(d) == phone]
                    all_mentions = _find_name_mentions(
                        hraws, hfolds, sorted(all_roster_names))
                    clause_order = sorted(set(hcids))
                    gov_actions = set()
                    for hv in hverbs:
                        if hv["start"] in hwrapped \
                                or hv["start"] in hdelegated \
                                or hv["start"] in hquestioned:
                            continue
                        if _verb_polarity(
                                hv, hraws, hfolds, hcids,
                                hbounds) != "positive":
                            continue
                        hspan = _extract_object(
                            hv, hraws, hfolds, hcids, hbounds)
                        hcid = hcids[hv["start"]]
                        # (a) round 3: phone inside the
                        # object span.
                        if any(hspan[0] <= rs
                               and re_ <= hspan[1]
                               for (rs, re_) in phone_spans):
                            gov_actions.add(hv["action"])
                            continue
                        span_has_dup_name = any(
                            hspan[0] <= ns and ne <= hspan[1]
                            for (ns, ne) in mentions)
                        if not span_has_dup_name:
                            continue
                        # (b) same clause, phone after the
                        # verb, verb governs the duplicate
                        # name: the phone is that person's
                        # number stated later in the
                        # clause, past the 3-token span.
                        if any(hcids[rs] == hcid
                               and rs > hv["start"]
                               for (rs, _re) in phone_spans):
                            gov_actions.add(hv["action"])
                            continue
                        # (c) discourse fragment: an
                        # earlier verb governs the
                        # duplicate name, the phone sits
                        # in a later bare-fragment clause,
                        # and no clause between them
                        # mentions a person, a callback
                        # verb or another phone run.
                        for (rs, re_) in phone_spans:
                            pcid = hcids[rs]
                            if pcid not in clause_order \
                                    or clause_order.index(pcid) \
                                    <= clause_order.index(hcid):
                                continue
                            if any(hcids[v2["start"]] == pcid
                                   for v2 in hverbs):
                                continue
                            if any(hcids[ns] == pcid
                                   for (ns, _ne)
                                   in all_mentions):
                                continue
                            clause_phones = {
                                _norm_phone(d)
                                for (s2, _e2, d, _k2)
                                in hruns
                                if hcids[s2] == pcid}
                            if clause_phones != {phone}:
                                continue
                            between = clause_order[
                                clause_order.index(hcid) + 1:
                                clause_order.index(pcid)]
                            # ROUND 5 (L5 decision): a
                            # between-clause breaks the
                            # chain ONLY when it really
                            # intervenes on a person or a
                            # phone, by structure, never
                            # by phrase list:
                            # - a roster-name mention
                            #   still breaks (an
                            #   intervening person);
                            # - a digit run breaks ONLY
                            #   when its normalised value
                            #   is a roster phone -- an
                            #   age, year, room or count
                            #   is not a phone, so it
                            #   does not break;
                            # - a callback verb breaks
                            #   ONLY when it truly
                            #   governs: its
                            #   _extract_object span
                            #   contains a roster-name
                            #   mention or a roster-phone
                            #   run. A verb-like token
                            #   inside a noun phrase
                            #   governs nothing, so it
                            #   does not break.
                            clean = True
                            for mid in between:
                                if any(
                                        hcids[ns] == mid
                                        for (ns, _ne)
                                        in all_mentions):
                                    clean = False
                                    break
                                if any(
                                        hcids[s2] == mid
                                        and _norm_phone(d2)
                                        in all_roster_phones
                                        for (s2, _e2, d2,
                                         _k2) in hruns):
                                    clean = False
                                    break
                                for v2 in hverbs:
                                    if hcids[v2["start"]] \
                                            != mid:
                                        continue
                                    vspan = _extract_object(
                                        v2, hraws, hfolds,
                                        hcids, hbounds)
                                    if any(
                                            vspan[0] <= ns
                                            and ne <= vspan[1]
                                            for (ns, ne)
                                            in all_mentions) \
                                            or any(
                                                vspan[0] <= s2
                                                and e2 <= vspan[1]
                                                and _norm_phone(d2)
                                                in all_roster_phones
                                                for (s2, e2, d2,
                                                 _k2) in hruns):
                                        clean = False
                                        break
                                if not clean:
                                    break
                            if clean:
                                gov_actions.add(hv["action"])
                                break
                    if gov_actions \
                            and action not in gov_actions:
                        continue
                    hsel = analyze_action_selection(
                        htext, target_names=target_names,
                        target_phones=(phone,), action=action)
                    if hsel["selection"] in ("negated",
                                             "replaced",
                                             "cancelled"):
                        if phone_qualified == {entry}:
                            phone_qualified = None
                    else:
                        phone_qualified = {entry}
                continue
            for (ns, ne) in mentions:
                # Collect the noun-descriptor phrase adjacent
                # to this name mention (before and after),
                # for the D1 structured-attribute check at
                # the end. Tokens are folded, contiguous,
                # capped at 4 so a following clause cannot
                # bleed into the phrase.
                after_seq = []
                j = ne
                while j < len(hfolds) \
                        and len(after_seq) < 4 \
                        and _is_noun_descriptor(hfolds[j]):
                    after_seq.append(hfolds[j])
                    j += 1
                if after_seq:
                    descriptor_phrases.append(after_seq)
                elif dup_attr_seqs and ne < len(hfolds):
                    # R4 VERB-COLLISION RESCUE (post-name
                    # only): the ordinary scan above stops
                    # at the FIRST token it rejects, so a
                    # descriptor whose first folded token
                    # collides with a general verb (the
                    # reported case: a relation word
                    # folding to a verb form) collects
                    # NOTHING, even though the full phrase
                    # after the name is a noun phrase, not
                    # a verb phrase. Do NOT drop the verb
                    # list, and do NOT whitelist any word:
                    # instead, read the contiguous run
                    # immediately after the name, in the
                    # SAME clause, and accept a prefix of
                    # it ONLY when that prefix, whole,
                    # EXACTLY equals a structured
                    # attribute sequence of a duplicate
                    # entry. Length >= 2 is required: a
                    # single verb-fold token alone is
                    # never a noun phrase, so a genuine
                    # verb clause ("name + verb + object")
                    # cannot rescue -- its run is not an
                    # attribute, and a truncated single
                    # token is not an attribute either.
                    # If no prefix matches, nothing is
                    # appended: the turn still qualifies
                    # nothing, exactly as before. The
                    # appended phrase then goes through
                    # the unchanged D1 rule below, which
                    # qualifies an entry ONLY when exactly
                    # one duplicate carries the match --
                    # a missing, duplicated or mismatched
                    # attribute still blocks both arms.
                    _name_cid = hcids[ne - 1]
                    _run = []
                    _j = ne
                    while _j < len(hfolds) \
                            and len(_run) < 4 \
                            and hcids[_j] == _name_cid:
                        _run.append(hfolds[_j])
                        _j += 1
                    for _ln in range(2, len(_run) + 1):
                        _cand = _run[:_ln]
                        if _cand in dup_attr_seqs:
                            descriptor_phrases.append(_cand)
                before_seq = []
                j = ns - 1
                while j >= 0 and len(before_seq) < 4 \
                        and _is_noun_descriptor(hfolds[j]):
                    before_seq.insert(0, hfolds[j])
                    j -= 1
                if before_seq:
                    descriptor_phrases.append(before_seq)
        if phone_qualified is not None:
            return set(phone_qualified)
        if phone_seen:
            return set()
        if descriptor_phrases:
            # D1 (paired-dev regressions train_0063 /
            # train_0225): a descriptor qualifies an entry
            # ONLY when it matches a STRUCTURED roster
            # attribute of exactly one duplicate. The
            # qualifier phrase is matched against every
            # roster field other than id/name/phone
            # (e.g. relation), folded, as a contiguous
            # subsequence in either direction -- so
            # "khach hang" matches a relation "khach
            # hang" and also a longer relation containing
            # it, but a trailing politeness word cannot
            # create a match by itself. If the attribute
            # is missing for all duplicates, matches
            # several duplicates, or matches none, the
            # descriptor qualifies NOTHING (round-4 rule
            # preserved; the re-pinned Minh fixture has
            # no structured attribute and still blocks
            # both arms). This never restores the old
            # shortcut "descriptor => all duplicates
            # pass": at most one entry is qualified, and
            # only by an explicit structured match.
            def _is_subseq(short, long_):
                if not short or len(short) > len(long_):
                    return False
                return any(
                    long_[k:k + len(short)] == short
                    for k in range(len(long_) - len(short) + 1))

            matched_entries = set()
            for i in idxs:
                attr_seqs = []
                for key, val in (roster[i] or {}).items():
                    if key in ("id", "name", "phone"):
                        continue
                    if not isinstance(val, str) or not val.strip():
                        continue
                    seq = [_fold(t) for t in
                           re.findall(r"[^\W_]+", _nfc(val))]
                    if seq:
                        attr_seqs.append(seq)
                for phrase in descriptor_phrases:
                    if any(_is_subseq(phrase, seq)
                           or _is_subseq(seq, phrase)
                           for seq in attr_seqs):
                        matched_entries.add(i)
                        break
            if len(matched_entries) == 1:
                return set(matched_entries)
            # ROUND 4 fallback: descriptor-only with no
            # unique structured match qualifies NOTHING.
            return set()
        return set()

    # 2. Duplicate name (proposal-action verbs only): the
    # name is ambiguous AND the text carries no number at
    # all to pick between the duplicates AND history does
    # not qualify the PROPOSAL entry. If a number IS
    # present (the proposal's, or another duplicate's),
    # check 6 decides honestly (matched pass /
    # wrong_person) -- check 2 must not relabel that as
    # ambiguity.
    # R4-PHONE-GUARD (F-0): the guard counts duplicate
    # ENTRIES by name, not distinct non-empty phones. The
    # old phone count let one entry's phone dropping to
    # "" (barrier contradiction / intra-read conflict, or
    # a naturally missing phone) collapse the guard: with
    # only one known phone left, an unqualified proposal
    # fell through to a pass for BOTH duplicates. An entry
    # whose phone is UNKNOWN is still a duplicate member:
    # it cannot be used to choose a person via that phone,
    # and it must not silently remove the ambiguity for
    # the other entry. The phone set below is still used
    # for the two phone tests (proposal-is-duplicate and
    # the digit-run test); only the guard threshold moves
    # from phones to entries.
    for fold in governed_names:
        idxs = _entries_for_name(fold)
        phones = {_norm_phone(roster[i].get("phone") or "")
                  for i in idxs}
        phones.discard("")
        if len(idxs) < 2:
            continue
        qualified = _history_qualified_entries(idxs)
        # Name-key proposals: an id proposal to an entry
        # whose phone is "" reaches this function with no
        # phone target, so its key is the bare name, not
        # the entry -- the entry test above would miss it
        # entirely (R3-h1). Such a proposal is a duplicate
        # proposal when its name key maps to exactly this
        # duplicate set AND history qualifies nobody: with
        # no qualified entry there is no referent the bare
        # name could be presumed to mean. When history
        # qualifies exactly one entry, the name-key
        # proposal still passes (the R1 correct arm is
        # itself a name-key proposal to the qualified
        # entry, and at this layer a phone-less id cannot
        # be distinguished from that entry) -- the
        # asymmetry is inherent to the name/phone-only
        # signature here, and the entry-key arms still
        # block the wrong person in that case.
        proposal_is_name_dup = (
            proposal_key[0] == "name" and not qualified
            and set(_entries_for_name(proposal_key[1]))
            == set(idxs))
        proposal_is_duplicate = (
            proposal_key in [("entry", i) for i in idxs]
            or any(t in phones for t in targets_norm)
            or proposal_is_name_dup)
        if not proposal_is_duplicate:
            continue
        proposal_qualified = any(
            proposal_key == ("entry", i)
            or _norm_phone(roster[i].get("phone") or "")
            in targets_norm
            for i in qualified)
        if proposal_qualified:
            continue
        if not any(_norm_phone(d) in phones
                   for (_rs, _re, d, _k) in all_runs):
            return _mismatch(
                "duplicate_name",
                "name %r maps to %d roster entries "
                "(%d known phones) and "
                "neither the text nor history qualifies "
                "this proposal with any number or qualifier"
                % (fold, len(idxs), len(phones)))

    # 3. B decisive vetoes (active cancellations override
    # history and selections alike).
    sel = analyze_action_selection(text,
                                   target_names=target_names,
                                   target_phones=target_phones,
                                   action=action)
    if sel["selection"] == "negated":
        return _mismatch("negated",
                         "B: action selection negated")
    if sel["selection"] in ("replaced", "cancelled"):
        return _mismatch("target_replaced_or_cancelled",
                         "B: selection %s" % sel["selection"])
    # Person-key compatibility: an ambiguous name key
    # ("name", fold) mapping to several roster entries is
    # COMPATIBLE with a proposal to any one of them -- the
    # name could refer to that person; it is an
    # underspecification, not a contradiction. An explicit
    # entry/phone key that differs from the proposal IS a
    # contradiction. (Step 2 already fires the unqualified
    # duplicate case before this point; this rule only
    # rescues the history-qualified / otherwise abstained
    # shapes from a spurious step-6 wrong_person.)
    def _selection_compatible(k):
        if k == proposal_key:
            return True
        if k[0] == "name":
            return proposal_key in [
                ("entry", i) for i in _entries_for_name(k[1])]
        return False

    # 4. Early matched-pass (correction-aware). An exact
    # same-action match passes (multi-person selections:
    # calling one of several selected people is a match).
    # Without an exact match, an ambiguous-name-only
    # same-action set passes when every same-action
    # selection is compatible -- there is no explicit
    # contradiction, only underspecification. An explicit
    # entry/phone selection that differs from the proposal
    # blocks the pass: the explicit number wins over an
    # ambiguous name ("Goi cho Binh so D" + call(A) still
    # fires wrong_person via check 6).
    same_action = [p for (a, p) in selections if a == action]
    if same_action:
        if any(p == proposal_key for p in same_action):
            return {"consistent": True}
        explicit = [p for p in same_action
                    if p[0] in ("entry", "phone")]
        if not explicit and any(_selection_compatible(p)
                                for p in same_action):
            return {"consistent": True}
    # H2 helper (C3-G3-01, narrowed round 3 per L5
    # adjudication): True iff the CURRENT turn directly
    # states this proposal as completed -- a past verb
    # ("da" / "moi" / "vua" before the verb, the past
    # markers of _verb_polarity) of the proposal action
    # whose object span contains the proposal phone or a
    # name of the proposal person (target names, plus
    # roster names of entries carrying a proposal phone).
    # "Directly" is structural, not a sentence list. The
    # ONLY exception is a past verb inside the content
    # clause of a NOTE-TAKING verb in the same clause:
    # the clause's content introducer ("la" / "rang")
    # must be governed by ghi / ghi chu / ghi chep / chep
    # / luu / luu tru -- i.e. the note verb's span ends
    # at the introducer (allowing a trailing "lai": "ghi
    # lai la ..."). "Ghi chu thi cu ghi la da goi ..."
    # is excepted (its "da goi" is note content, which is
    # what keeps the pinned train_0672 shape passing).
    # Copular "la nguoi da goi" has no verb governing its
    # "la" at all, and reporting "noi la da goi" is
    # governed by "noi", not a note verb -- neither is
    # excepted, so both are direct completions and block.
    # Question / "chua" / wrapper blocked verbs are not
    # past completions and are deliberately excluded: a
    # "chua goi" (not yet called) or a question about a
    # call leaves a history request pending, not done.
    _NOTE_PATTERNS = [["ghi", "chu"], ["ghi", "chep"],
                      ["luu", "tru"], ["ghi"], ["chep"],
                      ["luu"]]

    def _in_note_content_clause(first, verb_start):
        for k in range(first, verb_start):
            if folds[k] not in ("la", "rang"):
                continue
            i = first
            while i < k:
                matched = None
                for pat in _NOTE_PATTERNS:
                    if folds[i:i + len(pat)] == pat \
                            and i + len(pat) <= k:
                        matched = len(pat)
                        break
                if matched is not None:
                    if i + matched == k or all(
                            folds[t] == "lai"
                            for t in range(i + matched, k)):
                        return True
                    i += matched
                else:
                    i += 1
        return False

    def _current_past_govern_kind():
        # Returns None (no direct past govern), "question"
        # (the governing past verb sits in a question
        # clause -- an S11 question about completion, NOT
        # proof of completion) or "declarative" (a direct
        # completion statement). Internal only; the old
        # boolean conflated the two, which is exactly the
        # H2-S11 epistemic error: a question was labelled
        # "(completed)".
        gov_names = set(target_names or ())
        for e in roster:
            if _norm_phone(e.get("phone") or "") in targets_norm:
                parts = _nfc(str(e.get("name") or "")).split()
                if parts:
                    gov_names.add(_nfc(str(e.get("name")
                                         or "")))
                    gov_names.add(parts[-1])
        for v in verbs:
            if v["action"] != action:
                continue
            if _verb_polarity(v, raws, folds, clause_ids,
                              bounds) != "blocked":
                continue
            cid = clause_ids[v["start"]]
            first, _last = bounds[cid]
            prev = v["start"] - 1
            if prev < first or folds[prev] not in ("da",
                                                   "moi",
                                                   "vua"):
                continue
            if folds[prev] == "vua" and sum(
                    1 for k in range(first, _last + 1)
                    if folds[k] == "vua") >= 2:
                continue
            if _in_note_content_clause(first, v["start"]):
                continue
            span = _extract_object(v, raws, folds, clause_ids,
                                   bounds)
            governed = any(span[0] <= ns and ne <= span[1]
                           for (ns, ne) in _find_name_mentions(
                               raws, folds, sorted(gov_names))) \
                or any(span[0] <= rs and re_ <= span[1]
                       and _norm_phone(d) in targets_norm
                       for (rs, re_, d, _k) in all_runs)
            if governed:
                if _clause_is_s11_question(raws, folds, first,
                                           _last):
                    return "question"
                return "declarative"
        return None

    def _history_turn_is_declarative_completion(htext):
        # A single history turn that, as a standalone
        # statement, directly states the proposal as
        # completed: a blocked past verb of the proposal
        # action governing the proposal name/phone in a
        # NON-question clause. A question turn ("... chua?")
        # is not a completion, and a note-content clause
        # is not either (same exclusions as the current
        # turn). Mirrors _current_past_govern_kind over
        # the history turn's own tokenisation.
        if not isinstance(htext, str) or not htext.strip():
            return False
        h_clean = _strip_quoted(_nfc(htext))
        h_raws, h_folds, h_cids = _tokenize(h_clean)
        if not h_raws:
            return False
        h_bounds = _clause_bounds(h_cids)
        h_verbs = _find_verbs(h_folds, ("call", "message"))
        h_runs = _digit_runs(h_raws, h_folds, h_cids)
        h_gov = set(target_names or ())
        for e in roster:
            if _norm_phone(e.get("phone") or "") in targets_norm:
                parts = _nfc(str(e.get("name") or "")).split()
                if parts:
                    h_gov.add(_nfc(str(e.get("name") or "")))
                    h_gov.add(parts[-1])
        for v in h_verbs:
            if v["action"] != action:
                continue
            if _verb_polarity(v, h_raws, h_folds, h_cids,
                              h_bounds) != "blocked":
                continue
            h_cid = h_cids[v["start"]]
            h_first, h_last = h_bounds[h_cid]
            prev = v["start"] - 1
            if prev < h_first or h_folds[prev] not in (
                    "da", "moi", "vua"):
                continue
            if h_folds[prev] == "vua" and sum(
                    1 for k in range(h_first, h_last + 1)
                    if h_folds[k] == "vua") >= 2:
                continue
            if _in_note_content_clause(h_first, v["start"]):
                continue
            if _clause_is_s11_question(h_raws, h_folds,
                                       h_first, h_last):
                continue
            span = _extract_object(v, h_raws, h_folds, h_cids,
                                   h_bounds)
            if any(span[0] <= ns and ne <= span[1]
                   for (ns, ne) in _find_name_mentions(
                       h_raws, h_folds, sorted(h_gov))):
                return True
            if any(span[0] <= rs and re_ <= span[1]
                   and _norm_phone(d) in targets_norm
                   for (rs, re_, d, _k) in h_runs):
                return True
        return False

    def _history_last_event(count_completion=True):
        # Last decisive event for (action, target) over
        # history_texts in order. Positive sets a pending
        # request; negated / replaced / cancelled are
        # terminals; a declarative completion turn is a
        # discharged terminal (it returns blocked_verb_only
        # from analyze_action_selection, so it would
        # otherwise leave a pending state untouched -- the
        # Q-AFTER-COMPLETION trap). Unknown turns leave
        # the state alone. Returns (kind, index) with kind
        # in {"positive_request", "cancelled", "replaced",
        # "discharged"} or (None, None). count_completion
        # is False ONLY for the no-direct-past-govern
        # fallthrough path, where round-5 binary behaviour
        # must be preserved exactly: there, a completion
        # turn in history is an unknown turn that leaves
        # the state alone, as in round 5.
        last_kind, last_index = None, None
        for idx, htext in enumerate(history_texts or ()):
            if not isinstance(htext, str):
                continue
            if count_completion \
                    and _history_turn_is_declarative_completion(
                        htext):
                last_kind, last_index = "discharged", idx
                continue
            hsel = analyze_action_selection(
                htext, target_names=target_names,
                target_phones=target_phones, action=action)
            if hsel["selection"] == "positive":
                last_kind, last_index = "positive_request", idx
            elif hsel["selection"] == "negated":
                last_kind, last_index = "cancelled", idx
            elif hsel["selection"] == "replaced":
                last_kind, last_index = "replaced", idx
            elif hsel["selection"] == "cancelled":
                last_kind, last_index = "cancelled", idx
        return last_kind, last_index

    # 5. B unknown-mismatch mapping. Blocked is "no current
    # signal", not a cancellation: a history turn that
    # positively selected this proposal stands (the B pin
    # for prior-instruction bindings, extended to the passed
    # path for blocked verdicts only) -- but only while
    # that history-positive state is ACTIVE, and never
    # when the current turn directly states the proposal
    # as completed (H2 fix, C3-G3-01).
    if sel["selection"] == "unknown":
        mapping = {
            "other_action_verb_only": "action_mismatch",
            "blocked_verb_only": "blocked_request",
            "negated_other_object": "negated",
            "number_as_content_for_other_recipient":
                "money_or_content_role",
        }
        if sel["reason"] == "blocked_verb_only":
            # H2-S11 structured split (round H2S11, additive
            # on the execution tier: every branch below is
            # still consistent False). The old code returned
            # blocked_request here for BOTH a declarative
            # completion and a question about completion,
            # and ignored history entirely on this branch.
            past_kind = _current_past_govern_kind()
            if past_kind is not None:
                last_kind, last_index = _history_last_event()
                if past_kind == "declarative":
                    # Direct completion statement: the
                    # instruction is discharged, whatever
                    # history said (H2 fix, C3-G3-01).
                    return _s11_result(
                        "mismatch", "discharged", "completion",
                        "blocked_request",
                        "B: blocked_verb_only; current past "
                        "verb directly governs the proposal "
                        "(completed), history cannot revive "
                        "it", last_kind, last_index)
                # past_kind == "question": a question about
                # completion proves nothing about whether
                # the call happened.
                if last_kind == "positive_request":
                    # S11 proper: pending positive, no
                    # terminal after it, current gives no
                    # new positive. Active is UNPROVEN --
                    # neither active nor discharged.
                    return _s11_result(
                        "unknown_pending", "pending_unproven",
                        "question", "unknown_pending",
                        "B: blocked_verb_only; current "
                        "question past-governs the proposal, "
                        "history positive still pending, no "
                        "current positive -- active "
                        "unproven", "positive_request",
                        last_index)
                # Question over a discharged / cancelled /
                # replaced / absent positive: still a block,
                # but NOT unknown_pending -- there is no
                # pending instruction to be unknown about.
                return _s11_result(
                    "mismatch", last_kind or "none",
                    "question", "blocked_request",
                    "B: blocked_verb_only; current question "
                    "past-governs the proposal, last event "
                    "is %s, not a pending positive"
                    % (last_kind or "none"),
                    last_kind, last_index)
            # No direct past govern: ACTIVE history scan, in
            # order: a positive turn sets active, a later
            # negated / replaced / cancelled turn clears
            # it; unknown turns leave the state alone.
            # Only a finally-active state falls through --
            # an old request revoked by a later cancellation
            # does not revive. (This path keeps the old
            # plain shape; the S11 taxonomy above covers
            # only the direct-past-govern branch.)
            last_kind, _ = _history_last_event(
                count_completion=False)
            if last_kind != "positive_request":
                return _mismatch("blocked_request",
                                 "B: blocked_verb_only")
        elif sel["reason"] in mapping:
            return _mismatch(mapping[sel["reason"]],
                             "B: %s" % sel["reason"])
        # Abstain reasons (no_callback_verb,
        # quoted_mention_only) and an ACTIVE history-positive
        # blocked verdict with no direct current completion
        # fall through.

    # 6. Positive-selection-set mismatch.
    if selections:
        if any(a == action for (a, _p) in selections):
            return _mismatch(
                "wrong_person",
                "positive %s selections %r do not include "
                "the proposal person" % (action,
                                         sorted(selections)))
        if any(_selection_compatible(p)
               for (_a, p) in selections):
            # Abstain: a verb of the proposal action exists
            # AND the proposal person is mentioned -- a bare
            # verb with a discourse recipient ("nhan tin"
            # after naming the teacher) is an implicit
            # selection, not a mismatch. Otherwise (no verb
            # of the proposal action at all) the person was
            # selected for another action only: fire.
            has_action_verb = any(
                v["action"] == action for v in positive_verbs)
            mentioned = bool(_find_name_mentions(
                raws, folds, target_names or ())) \
                or any(_norm_phone(d) in targets_norm
                       for (_rs, _re, d, _k) in all_runs)
            if not (has_action_verb and mentioned):
                return _mismatch(
                    "action_mismatch",
                    "proposal person selected, but only for "
                    "another action: %r" % sorted(selections))
        else:
            return _mismatch(
                "selection_mismatch",
                "positive selections %r match neither the "
                "proposal action nor person"
                % sorted(selections))

    # 5. Money / old-number role for every proposal-phone run.
    if targets_norm:
        runs = [(rs, re_) for (rs, re_, d, _k) in all_runs
                if _norm_phone(d) in targets_norm]

        def _money_or_old(rs, re_):
            if rs > 0 and folds[rs - 1] == "tien":
                return True
            if re_ < len(folds) and folds[re_] in (
                    "dong", "nghin", "trieu", "ty", "vnd"):
                return True
            if rs >= 2 and folds[rs - 2:rs] in (
                    ["so", "cu"], ["so", "truoc"]):
                return True
            if folds[re_:re_ + 3] == ["la", "so", "cu"]:
                return True
            return False

        if runs and all(_money_or_old(rs, re_)
                        for (rs, re_) in runs):
            return _mismatch(
                "money_or_content_role",
                "every proposal-phone run is a money or "
                "old-number mention, not a call target")

    # 6. Bare / question-only mentions.
    mention_starts = []
    for (ns, _ne) in _find_name_mentions(raws, folds,
                                         target_names or ()):
        mention_starts.append(ns)
    for (rs, _re, d, _k) in all_runs:
        if _norm_phone(d) in targets_norm:
            mention_starts.append(rs)
    if mention_starts:
        all_question = all(
            _clause_is_question(
                raws, folds, *bounds[clause_ids[ms]])
            for ms in mention_starts)
        no_verbs = not verbs and not _find_other_verbs(folds)
        if all_question or no_verbs:
            return _mismatch(
                "bare_or_question_mention",
                "target mentioned only in question clauses "
                "or in a verb-less text")
    return {"consistent": True}
