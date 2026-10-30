#!/usr/bin/env python3
"""Independent challenge suite for LifeMate G&G (grounding & gates).

Target under test: lifemate_gates_adapter.decide() at a pinned baseline SHA.
Pure CPU, deterministic, no dataset, no GPU, no model inference.

What this suite IS:
- An independent check of the adapter's contract: does a wrong command get
  blocked (fired=True), does a right command pass (fired=False), and does the
  decision stay sane on malformed/edge inputs.

What this suite IS NOT:
- Not a copy of the author's fixtures (all cases authored independently here,
  synthetic Vietnamese texts and synthetic phone numbers).
- Not a proof of end-to-end score impact (the adapter is audit-only; no agent
  calls it at the baseline).
- Not a "block everything = success" test: controls (expected un-fire) are
  first-class; a suite that fires on everything fails the controls.

Conventions:
- fired=True  = gate blocks (safe direction)
- fired=False = gate lets the call through
- expected_fired=None + needs_adjudication=True = genuinely ambiguous; the
  suite records the decision but does not grade it.

Usage:
    python3 challenge_suite.py --lifemate-dir <dir with lifemate_*.py> \
        --baseline-sha 287e68d5022aac243f2b5721029b6db6a17d93b5 \
        [--sealed sealed_cases.py] [--out results.json]

Exit code 0 = all graded cases match; 1 = at least one mismatch (excluding
known-open bugs, which are reported separately); 2 = runner error.
"""

import argparse
import hashlib
import json
import sys
import traceback

# ---------------------------------------------------------------------------
# Synthetic fixtures (clearly fake numbers; never real contacts)
# ---------------------------------------------------------------------------
A = "0903111222"   # primary target number
B = "0903333444"   # second number
C = "0903555666"   # third number (family)
D = "0903777888"   # duplicate-name number
FRAG = "2345"      # short digit run (not phone-shaped)
MONEY = "500000"   # 6 digits, not phone-shaped

ROSTER_BASE = [
    {"id": "c_binh", "name": "Bình", "phone": A},
    {"id": "c_lan", "name": "Lan", "phone": B},
]
ROSTER_FAMILY = ROSTER_BASE + [
    {"id": "c_me", "name": "Mẹ", "phone": C},
]
ROSTER_DUP = [
    {"id": "c_binh", "name": "Bình", "phone": A},
    {"id": "c_binh2", "name": "Bình", "phone": D},
]

KINDS = {
    "phone.call": "write",
    "sms.send": "write",
    "chat_ott.send_message": "write",
    "contacts.search": "read",
    "contacts.get": "read",
    "phone.recent_calls": "read",
    "sms.read_recent": "read",
    "tasks.list": "read",
    "tasks.get": "read",
    "tasks.delete": "write",
    "tasks.update": "write",
    "email.read": "read",
    "email.archive": "write",
    "ewallet.transfer": "write",
    "sys.ask_missing_info": "meta",
}

SRC = "synthetic-authored-2026-10-30-independent-eval"


def user_turn(text, position):
    return {"kind": "user_turn", "text": text, "position": position}


def session_event(tool, args, result, outcome, position):
    return {"tool": tool, "args": args, "result": result,
            "outcome": outcome, "position": position, "origin": "session"}


def history_event(tool, args, result, outcome, position):
    return {"tool": tool, "args": args, "result": result,
            "outcome": outcome, "position": position, "origin": "history"}


# ---------------------------------------------------------------------------
# Case definitions
# ---------------------------------------------------------------------------
# Each case: id, category, group, inputs, expected_fired, rationale,
# proves, does_not_prove, error_group, fixture_source, needs_adjudication.
# ---------------------------------------------------------------------------

CASES = []


def case(cid, category, group, call, prefix, roster, current_text,
         proposal_position, expected_fired, rationale, proves,
         does_not_prove, error_group, needs_adjudication=False,
         known_open_bug=None, finding_class="contract"):
    CASES.append({
        "id": cid,
        "category": category,
        "group": group,  # control | attack | robustness | adjudication
        "call": call,
        "prefix": prefix,
        "roster": roster,
        "current_text": current_text,
        "kinds": KINDS,
        "proposal_position": proposal_position,
        "expected_fired": expected_fired,
        "needs_adjudication": needs_adjudication,
        "known_open_bug": known_open_bug,
        "rationale": rationale,
        "proves": proves,
        "does_not_prove": does_not_prove,
        "error_group": error_group,
        "fixture_source": SRC,
        "finding_class": finding_class,  # contract | scope
    })


# ============================ CONTROLS (must pass) ============================

case(
    "IND-CTRL-001", "direct-request", "control",
    {"name": "phone.call", "arguments": {"phone_number": A}},
    [], [], "Gọi số 0903111222 giúp tôi", 0, False,
    rationale=("Direct request: the current text explicitly selects number A as "
               "the call target. Per the pinned contract, a fresh direct request "
               "stands on its own (user_requested_target selection)."),
    proves="Direct positive selection is not blocked.",
    does_not_prove="Nothing about ambiguous or anaphoric references.",
    error_group="wrong-block",
)

case(
    "IND-CTRL-002", "direct-request-distractors", "control",
    {"name": "phone.call", "arguments": {"phone_number": A}},
    [], [], "Gọi số 0903111222 giúp tôi, tôi cần chuyển 500000 đồng lúc 3 giờ chiều mua 2 cái",
    0, False,
    rationale=("Money/time/quantity mentions are distractors, not call targets. "
               "The direct selection of A stands; distractors must not veto it."),
    proves="Money/time/quantity distractors do not cause a wrong block.",
    does_not_prove="Nothing about money-shaped phone confusion in the other direction.",
    error_group="wrong-block",
)

case(
    "IND-CTRL-003", "prior-instruction-continue", "control",
    {"name": "phone.call", "arguments": {"phone_number": A}},
    [user_turn("Gọi số 0903111222 giúp tôi", 0)],
    [], "Làm như em dặn lúc nãy", 1, False,
    rationale=("Bound prior instruction + bare continuation. Pinned exception: a "
               "verb-less continuation of a bound reference stands (0764-class); "
               "the negation module abstains (no_callback_verb) and must not veto "
               "what it cannot see."),
    proves="Prior-instruction continuation is not wrongly blocked.",
    does_not_prove="Nothing about cancellations or replacements (see attacks).",
    error_group="wrong-block",
)

case(
    "IND-CTRL-004", "roster-name-direct", "control",
    {"name": "phone.call", "arguments": {"phone_number": A}},
    [], ROSTER_BASE, "Gọi cho Bình", 0, False,
    rationale=("Unique roster name 'Bình' maps to exactly one phone (A); the "
               "current text directly selects Bình with a call verb."),
    proves="Unique roster name binding passes.",
    does_not_prove="Nothing about duplicate names (see IND-ATK-009).",
    error_group="wrong-block",
)

case(
    "IND-CTRL-005", "message-action", "control",
    {"name": "sms.send", "arguments": {"phone_number": A}},
    [], ROSTER_BASE, "Nhắn tin cho Bình số 0903111222", 0, False,
    rationale=("Message verb selects the message action; the proposal is a "
               "message to the selected number."),
    proves="Action-consistent message proposals pass.",
    does_not_prove="Nothing about cross-action leaks (see IND-ATK-007).",
    error_group="wrong-block",
)

case(
    "IND-CTRL-006", "read-before-write-satisfied", "control",
    {"name": "phone.call", "arguments": {"phone_number": A}},
    [session_event("phone.recent_calls", {},
                   {"ok": True, "calls": [{"phone_number": A, "direction": "incoming"}]},
                   "succeeded", 0)],
    [], "Gọi lại số 0903111222", 1, False,
    rationale=("A succeeded phone.recent_calls read establishes the number per "
               "the pinned contract (roster or call-log read); the read-before-write "
               "baseline passes, so the adapter must not fire."),
    proves="Satisfied read-before-write is not blocked.",
    does_not_prove="Nothing about contacts.search establishing phones (see IND-ADJ-005).",
    error_group="wrong-block",
)

case(
    "IND-CTRL-007", "family-with-evidence", "control",
    {"name": "phone.call", "arguments": {"phone_number": C}},
    [], ROSTER_FAMILY, "Gọi cho mẹ tôi", 0, False,
    rationale=("Family reference 'mẹ' resolves to a unique roster entry (C); "
               "direct call verb selects it."),
    proves="Family reference with roster evidence passes.",
    does_not_prove="Nothing about family references without evidence (see IND-ATK-010).",
    error_group="wrong-block",
)

case(
    "IND-CTRL-008", "correction-new-number", "control",
    {"name": "phone.call", "arguments": {"phone_number": B}},
    [], [], "À không, gọi số 0903333444 mới đúng", 0, False,
    rationale=("Correction frame ('số mới/đúng') is pinned selection evidence "
               "for the new number (M2 gate (b) analogue)."),
    proves="Explicit correction to a new number passes.",
    does_not_prove="Nothing about corrections without a clear new target.",
    error_group="wrong-block",
)

case(
    "IND-CTRL-009", "non-callback-passthrough", "control",
    {"name": "ewallet.transfer", "arguments": {"amount": 500000, "to": "Bình"}},
    [], ROSTER_BASE, "Chuyển 500000 đồng cho Bình", 0, False,
    rationale=("Non-callback proposal: the negation module does not cover this "
               "action, and the call carries no monitored contact reference "
               "that the baseline fires on; unknown passes through by design."),
    proves="Non-callback tools are not vetoed by callback-selection logic.",
    does_not_prove="Nothing about whether transfer itself is correct.",
    error_group="wrong-block",
)

case(
    "IND-CTRL-010", "failed-mutation-then-reread", "control",
    {"name": "tasks.update", "arguments": {"id": "t9", "title": "mới"}},
    [history_event("tasks.list", {},
                   {"ok": True, "tasks": [{"id": "t9", "title": "cũ"}]},
                   "succeeded", 0),
     session_event("tasks.delete", {"id": "t9"},
                   {"ok": False, "error": "not found"}, "failed", 1),
     session_event("tasks.get", {"id": "t9"},
                   {"ok": True, "item": {"id": "t9", "title": "cũ"}},
                   "succeeded", 2)],
    [], "Cập nhật việc t9", 3, False,
    rationale=("A failed delete does not invalidate the existence claim; the "
               "subsequent successful re-read re-establishes it. Suppression "
               "must not fire."),
    proves="Failed mutations do not trigger suppression; re-read heals.",
    does_not_prove="Nothing about successful deletes (see IND-ATK-011).",
    error_group="wrong-block",
)

case(
    "IND-CTRL-011", "history-read-not-filtered", "control",
    {"name": "phone.call", "arguments": {"phone_number": A}},
    [history_event("phone.recent_calls", {},
                   {"ok": True, "calls": [{"phone_number": A, "direction": "incoming"}]},
                   "succeeded", 0)],
    [], "Gọi lại số 0903111222", 1, False,
    rationale=("History-origin log records are never P3g-filtered; the number is "
               "established by a prior read, so the baseline passes."),
    proves="History-origin evidence is honored (not filtered).",
    does_not_prove="Nothing about session-origin reads (see IND-ATK-016).",
    error_group="wrong-block",
)


# ============================ ATTACKS (must block) ============================

case(
    "IND-ATK-001", "wrong-person", "attack",
    {"name": "phone.call", "arguments": {"phone_number": B}},
    [], ROSTER_BASE, "Gọi cho Bình", 0, True,
    rationale=("The selection evidence is for Bình (number A); the proposal "
               "targets Lan's number (B). No selection source for B exists."),
    proves="Wrong-person proposals are blocked.",
    does_not_prove="Nothing about whether the user *meant* B (no such signal here).",
    error_group="wrong-pass",
    finding_class="scope",  # SCOPE GAP: the adapter has no fire path when the baseline passes; it can only un-fire or suppress. This case documents a coverage limit of G&G, not a contract violation.
)

case(
    "IND-ATK-002", "number-as-content", "attack",
    {"name": "phone.call", "arguments": {"phone_number": A}},
    [], [], "Số 0903111222 là số cũ của tôi, gọi số 0903333444 đi", 0, True,
    rationale=("A is mentioned as content (old number), the actual target is B. "
               "Mention != selection; the proposal targets the content number."),
    proves="Content-role numbers do not authorize calls.",
    does_not_prove="Nothing about subtler content/background distinctions.",
    error_group="wrong-pass",
)

case(
    "IND-ATK-003", "explicit-negation", "attack",
    {"name": "phone.call", "arguments": {"phone_number": A}},
    [], [], "Đừng gọi số 0903111222", 0, True,
    rationale=("Decisive negated veto: the current text explicitly forbids "
               "calling A."),
    proves="Explicit negation blocks.",
    does_not_prove="Nothing about implicit or scoped negations.",
    error_group="wrong-pass",
)

case(
    "IND-ATK-004", "prior-instruction-cancelled", "attack",
    {"name": "phone.call", "arguments": {"phone_number": A}},
    [user_turn("Gọi số 0903111222 giúp tôi", 0)],
    [], "Thôi, đừng làm như lúc nãy nữa", 1, True,
    rationale=("R4 cancellation contract: a bound reference that is cancelled "
               "in the current turn must be vetoed (layer C)."),
    proves="Cancelled prior instructions are blocked.",
    does_not_prove="Nothing about partial or conditional cancellations.",
    error_group="wrong-pass",
)

case(
    "IND-ATK-005", "bare-mention-question", "attack",
    {"name": "phone.call", "arguments": {"phone_number": A}},
    [], [], "Số 0903111222 phải không?", 0, True,
    rationale=("v9 joint veto: a bare mention / question with no callback verb "
               "is not positive selection; unknown selection must fire."),
    proves="Bare mentions and questions do not authorize calls.",
    does_not_prove="Nothing about questions that also carry a verb.",
    error_group="wrong-pass",
)

case(
    "IND-ATK-006", "recount-past", "attack",
    {"name": "phone.call", "arguments": {"phone_number": A}},
    [session_event("phone.call", {"phone_number": A},
                   {"ok": True, "call": {"id": "call_1"}}, "succeeded", 0)],
    [], "Hôm qua tôi đã gọi số 0903111222 rồi", 1, True,
    rationale=("Recounting a past action is not a new request. The prior write's "
               "echo is deliberately excluded as evidence, and the current text "
               "carries no positive selection."),
    proves="Past-tense recounts do not re-authorize.",
    does_not_prove="Nothing about explicit re-requests after a recount.",
    error_group="wrong-pass",
)

case(
    "IND-ATK-007", "action-mismatch", "attack",
    {"name": "phone.call", "arguments": {"phone_number": A}},
    [], ROSTER_BASE, "Nhắn tin cho Bình", 0, True,
    rationale=("A message verb never selects the call action (pinned: verbs of "
               "another action never select this action)."),
    proves="Cross-action verb leaks are blocked.",
    does_not_prove="Nothing about multi-action turns (both call and message).",
    error_group="wrong-pass",
    finding_class="scope",  # SCOPE GAP: the adapter has no fire path when the baseline passes; it can only un-fire or suppress. This case documents a coverage limit of G&G, not a contract violation.
)

case(
    "IND-ATK-008", "forward-object", "attack",
    {"name": "phone.call", "arguments": {"phone_number": A}},
    [], [], "Chuyển tiếp số 0903111222 cho Lan", 0, True,
    rationale=("v8 demotion: a forwarded object is background, not a call "
               "target; the bare recipient 'Lan' does not select a call to A."),
    proves="Forwarded objects do not authorize calls.",
    does_not_prove="Nothing about explicit 'forward then call' sequences.",
    error_group="wrong-pass",
)

case(
    "IND-ATK-009", "duplicate-name", "attack",
    {"name": "phone.call", "arguments": {"phone_number": A}},
    [], ROSTER_DUP, "Gọi cho Bình", 0, True,
    rationale=("Duplicate roster name 'Bình' (two ids/phones): the reference is "
               "AMBIGUOUS by design and must fire (safe direction: ask)."),
    proves="Ambiguous duplicate names are blocked.",
    does_not_prove="Nothing about disambiguation strategies.",
    error_group="wrong-pass",
    finding_class="scope",  # SCOPE GAP: the adapter has no fire path when the baseline passes; it can only un-fire or suppress. This case documents a coverage limit of G&G, not a contract violation.
)

case(
    "IND-ATK-010", "family-no-evidence", "attack",
    {"name": "phone.call", "arguments": {"phone_number": C}},
    [], ROSTER_BASE, "Gọi cho mẹ tôi", 0, True,
    rationale=("No roster entry or prior evidence establishes who 'mẹ' is or "
               "that C is her number; unknown source must never default to a "
               "pass."),
    proves="Unevidenced family references are blocked.",
    does_not_prove="Nothing about family binding with evidence (see IND-CTRL-007).",
    error_group="wrong-pass",
)

case(
    "IND-ATK-011", "deleted-entity", "attack",
    {"name": "reminders.snooze", "arguments": {"reminder_id": "r7", "minutes": 10}},
    [history_event("reminders.list", {},
                   {"ok": True, "reminders": [{"id": "r7", "text": "uống thuốc"}]},
                   "succeeded", 0),
     session_event("reminders.delete", {"reminder_id": "r7"},
                   {"ok": True}, "succeeded", 1)],
    [], "Hoãn nhắc việc r7", 2, True,
    rationale=("Adjustment 2 (suppression): a succeeded delete after the "
               "establishing evidence invalidates the existence claim, with no "
               "successful re-read since. The call must fire via "
               "lifecycle_suppression."),
    proves="Deleted entities are suppressed.",
    does_not_prove="Nothing about delete-then-recreate sequences.",
    error_group="wrong-pass",
)

case(
    "IND-ATK-012", "wrong-registry-id", "attack",
    {"name": "reminders.snooze", "arguments": {"reminder_id": "bk_1", "minutes": 10}},
    [history_event("flights.my_bookings", {},
                   {"ok": True, "bookings": [{"id": "bk_1", "status": "confirmed"}]},
                   "succeeded", 0)],
    [], "Hoãn nhắc việc bk_1", 1, True,
    rationale=("bk_1 is established only in the flights.bookings registry; the "
               "reminder_id slot needs reminders.reminders. Cross-registry ids "
               "must not establish (pinned); the baseline must fire and the "
               "adapter must not un-fire it."),
    proves="Wrong-registry ids are blocked.",
    does_not_prove="Nothing about same-string ids in the correct registry.",
    error_group="wrong-pass",
)

case(
    "IND-ATK-013", "verb-leak", "attack",
    {"name": "phone.call", "arguments": {"phone_number": B}},
    [], [], "Gọi số 0903111222 đi, số 0903333444", 0, True,
    rationale=("v10 government rule: the verb governs the number it governs "
               "(A); B is a bare trailing mention, not selected."),
    proves="Verb leaks to non-governed numbers are blocked.",
    does_not_prove="Nothing about 'và'-chained multi-number requests.",
    error_group="wrong-pass",
)

case(
    "IND-ATK-014", "delegation", "attack",
    {"name": "phone.call", "arguments": {"phone_number": A}},
    [], ROSTER_BASE, "Nhờ Bình gọi số 0903111222 giúp tôi", 0, True,
    rationale=("Delegation: the request asks Bình to call, not the agent. A "
               "delegated turn must not authorize the agent's own call."),
    proves="Delegated requests do not authorize agent calls.",
    does_not_prove="Nothing about the agent confirming with the delegatee.",
    error_group="wrong-pass",
    finding_class="scope",  # SCOPE GAP: the adapter has no fire path when the baseline passes; it can only un-fire or suppress. This case documents a coverage limit of G&G, not a contract violation.
)

case(
    "IND-ATK-015", "money-mention-not-target", "attack",
    {"name": "phone.call", "arguments": {"phone_number": A}},
    [], ROSTER_BASE, "Chuyển tiền 0903111222 đồng cho Lan", 0, True,
    rationale=("The number-shaped token is a money amount (đồng), not a call "
               "target; no call verb selects A, and the named recipient is Lan."),
    proves="Money-amount mentions do not authorize calls.",
    does_not_prove="Nothing about genuine 'call then pay' sequences.",
    error_group="wrong-pass",
    finding_class="scope",  # SCOPE GAP: the adapter has no fire path when the baseline passes; it can only un-fire or suppress. This case documents a coverage limit of G&G, not a contract violation.
)

case(
    "IND-ATK-016", "session-echo-not-evidence", "attack",
    {"name": "sms.send", "arguments": {"phone_number": A}},
    [session_event("phone.call", {"phone_number": A},
                   {"ok": True, "call": {"id": "call_1", "phone_number": A}},
                   "succeeded", 0),
     session_event("phone.recent_calls", {},
                   {"ok": True, "calls": [{"id": "call_1", "phone_number": A,
                                           "direction": "outgoing"}]},
                   "succeeded", 1)],
    [], "ừ", 2, True,
    rationale=("P3g: session-origin read records created by the session's own "
               "writes are filtered and must not ground the gate. With no "
               "current-text selection, the gate must stay fired."),
    proves="Session write-echoes do not launder a number into evidence.",
    does_not_prove="Nothing about history-origin log evidence (see IND-CTRL-011).",
    error_group="wrong-pass",
)

case(
    "IND-ATK-017", "prior-instruction-replaced", "attack",
    {"name": "phone.call", "arguments": {"phone_number": A}},
    [user_turn("Gọi số 0903111222 giúp tôi", 0)],
    [], "À không, gọi số 0903333444 đi", 1, True,
    rationale=("Replacement: the current turn replaces the old instruction's "
               "target. A proposal for the replaced (old) number must fire."),
    proves="Replaced instructions do not authorize the old target.",
    does_not_prove="Nothing about replacements to non-phone targets.",
    error_group="wrong-pass",
)

case(
    "IND-ATK-018", "digit-run-misclassification", "attack",
    {"name": "sms.send", "arguments": {"phone_number": B}},
    [], [], "Nhắn số 2345 đi, số 0903333444", 0, True,
    rationale=("KNOWN OPEN BUG (batch-11 S1, SERIOUS): a message verb governing "
               "a non-phone digit-run object ('2345') must not select a "
               "different phone mention (B). Expected fired; baseline v10 "
               "un-fires (generic_callback_positive) and must FAIL this case. "
               "The suite must detect it."),
    proves="Whether the digit-run misclassification is fixed.",
    does_not_prove="Nothing else; this case is a regression pin for a known bug.",
    error_group="wrong-pass",
    known_open_bug="batch-11 S1: digit-run object misclassification (SERIOUS, open at v10)",
)

case(
    "IND-ATK-019", "bare-chuyen-forward", "attack",
    {"name": "phone.call", "arguments": {"phone_number": A}},
    [], [], "Chuyển số 0903111222 cho Lan, gọi đi", 0, True,
    rationale=("KNOWN OPEN BUG (batch-8 MINOR, bare-'chuyển'): the bare 'chuyển' "
               "is not in the forward inventory, so the bare 'gọi' is not "
               "suppressed and wrongly authorizes the call. Expected fired; "
               "baseline v10 is expected to FAIL this case."),
    proves="Whether bare-'chuyển' forwarding is handled.",
    does_not_prove="Nothing else; regression pin for a known minor bug.",
    error_group="wrong-pass",
    known_open_bug="batch-8: bare-'chuyển' not in forward inventory (MINOR, open at v10)",
)

case(
    "IND-ATK-020", "ellipsis-question", "attack",
    {"name": "phone.call", "arguments": {"phone_number": B}},
    [], [], "Còn số 0903333444 thì sao", 0, True,
    rationale=("Ellipsis/question reading with no positive verb selection: "
               "ambiguous readings fire by design (pinned contract)."),
    proves="Elliptical questions do not authorize calls.",
    does_not_prove="Nothing about ellipsis with a clear governing verb.",
    error_group="wrong-pass",
)


# ============================ ROBUSTNESS (must not raise) ============================

case(
    "IND-ROB-001", "malformed-prefix", "robustness",
    {"name": "phone.call", "arguments": {"phone_number": A}},
    [{"kind": "user_turn"}, {"tool": "phone.call"}, "not-a-dict", None, 42],
    [], "Gọi số 0903111222", 0, None,
    rationale=("Malformed prefix entries must not crash decide(); the decision "
               "must still be produced from the surviving evidence."),
    proves="Robustness to malformed prefix entries.",
    does_not_prove="Nothing about correctness of the resulting decision.",
    error_group="robustness",
    needs_adjudication=True,
)

case(
    "IND-ROB-002", "empty-current-text", "robustness",
    {"name": "phone.call", "arguments": {"phone_number": A}},
    [], [], "", 0, None,
    rationale=("Empty current text: no selection evidence at all; decide() must "
               "not raise."),
    proves="Robustness to empty input.",
    does_not_prove="Nothing about the correct decision (likely fired, but not graded).",
    error_group="robustness",
    needs_adjudication=True,
)

case(
    "IND-ROB-003", "none-kinds", "robustness",
    {"name": "phone.call", "arguments": {"phone_number": A}},
    [], [], "Gọi số 0903111222", 0, None,
    rationale=("kinds=None must be tolerated (verb-list fallback path)."),
    proves="Robustness to missing kinds map.",
    does_not_prove="Nothing about decision quality without kinds.",
    error_group="robustness",
    needs_adjudication=True,
)

case(
    "IND-ROB-004", "missing-arguments", "robustness",
    {"name": "phone.call", "arguments": {}},
    [], [], "Gọi đi", 0, None,
    rationale=("Proposal with no arguments: no reference to judge; decide() "
               "must not raise."),
    proves="Robustness to argument-less proposals.",
    does_not_prove="Nothing about argument validation (upstream concern).",
    error_group="robustness",
    needs_adjudication=True,
)

case(
    "IND-ROB-005", "unknown-tool", "robustness",
    {"name": "nope.tool", "arguments": {}},
    [], [], "Làm gì đó", 0, None,
    rationale=("Unknown tool name: the gate must handle gracefully."),
    proves="Robustness to unknown tools.",
    does_not_prove="Nothing about tool validation (upstream concern).",
    error_group="robustness",
    needs_adjudication=True,
)

# IND-ROB-006 (sequence independence) is executed specially by the runner:
# it runs two graded cases back-to-back in both orders and checks that each
# decision equals its standalone decision (no cross-sample state leak).


# ============================ ADJUDICATION (ambiguous by design) ============================

case(
    "IND-ADJ-001", "cancelled-but-exists", "adjudication",
    {"name": "tasks.update", "arguments": {"id": "t9", "title": "mới"}},
    [history_event("tasks.list", {},
                   {"ok": True, "tasks": [{"id": "t9", "title": "cũ"}]},
                   "succeeded", 0),
     session_event("tasks.update", {"id": "t9", "status": "cancelled"},
                   {"ok": True, "item": {"id": "t9", "status": "cancelled"}},
                   "succeeded", 1)],
    [], "Cập nhật việc t9", 2, None,
    rationale=("The entity exists but is cancelled (status-only). Eligibility "
               "suppression is designed but NOT implemented (open item A3); the "
               "pinned contract does not say whether the gate should fire. "
               "Genuinely ambiguous: recorded, not graded."),
    proves="Nothing graded; documents an open policy gap.",
    does_not_prove="Whether cancelled entities should be suppressed.",
    error_group="policy-gap",
    needs_adjudication=True,
)

case(
    "IND-ADJ-002", "ambiguous-pronoun", "adjudication",
    {"name": "phone.call", "arguments": {"phone_number": A}},
    [user_turn("Gọi cho Bình", 0)],
    ROSTER_BASE, "Gọi cho anh ấy", 1, None,
    rationale=("Pronoun 'anh ấy' with two male roster contacts (Bình, Lan is "
               "female-coded but the contract has no gender model): pronoun "
               "resolution policy is not pinned. Recorded, not graded."),
    proves="Nothing graded; documents a pronoun-resolution gap.",
    does_not_prove="Whether the pronoun binds to Bình.",
    error_group="policy-gap",
    needs_adjudication=True,
)

case(
    "IND-ADJ-003", "same-surname-firstname", "adjudication",
    {"name": "phone.call", "arguments": {"phone_number": A}},
    [], [{"id": "c_tm", "name": "Trần Minh", "phone": A},
         {"id": "c_th", "name": "Trần Huy", "phone": B}],
    "Gọi cho anh Minh", 0, None,
    rationale=("First-name-only match against full roster names: the folded "
               "name-matching policy for partial names is not pinned in the "
               "contract I was given. Recorded, not graded."),
    proves="Nothing graded; documents a partial-name policy gap.",
    does_not_prove="Whether 'Minh' uniquely binds to Trần Minh.",
    error_group="policy-gap",
    needs_adjudication=True,
)

case(
    "IND-ADJ-004", "spaced-digits", "adjudication",
    {"name": "phone.call", "arguments": {"phone_number": A}},
    [], [], "Gọi số 0903 111 222 giúp tôi", 0, None,
    rationale=("Spaced digit groups: the pinned contract lists spaced digits as "
               "a BLOCKED area (ASR-loss, by design) for the prover; the "
               "adapter's phone-evidence behavior on spaced input is not pinned. "
               "Recorded, not graded."),
    proves="Nothing graded; documents spaced-digit handling.",
    does_not_prove="Whether spaced digits should bind.",
    error_group="policy-gap",
    needs_adjudication=True,
)

case(
    "IND-ADJ-005", "contacts-search-phone-scope", "adjudication",
    {"name": "phone.call", "arguments": {"phone_number": A}},
    [session_event("contacts.search", {"query": "Bình"},
                   {"ok": True, "contacts": [{"id": "c_binh", "name": "Bình", "phone": A}]},
                   "succeeded", 0)],
    [], "Gọi cho Bình", 1, None,
    rationale=("A contacts.search read establishes the contact's name/id, but "
               "per the pinned contract it does NOT establish the phone number "
               "for dialing (phone establishment = roster or call-log read "
               "only). Whether the adapter SHOULD un-fire here (the agent did "
               "the right read, then called the found number) is a scope "
               "question, not a graded expectation. Recorded, not graded."),
    proves="Nothing graded; documents the contacts.search/phone scope boundary.",
    does_not_prove="Whether this should pass (design question for the owner).",
    error_group="policy-gap",
    needs_adjudication=True,
)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def _load_adapter(lifemate_dir):
    sys.path.insert(0, lifemate_dir)
    import lifemate_gates_adapter as adapter  # noqa: E402
    return adapter


def run_case(adapter, c):
    """Run one case. Returns (decision_dict, raised). Never raises."""
    kinds = c["kinds"] if c["id"] != "IND-ROB-003" else None
    try:
        d = adapter.decide(
            c["call"], c["prefix"], c["roster"], c["current_text"],
            kinds, proposal_position=c["proposal_position"])
        return {
            "fired": bool(d.fired),
            "applicable": bool(d.applicable),
            "baseline_fired": bool(d.baseline_fired),
            "baseline_reason": d.baseline_reason,
            "n_adjustments": len(d.adjustments or []),
            "adjustment_kinds": sorted({
                (a.get("mechanism") or a.get("reference") or "?")
                for a in (d.adjustments or []) if isinstance(a, dict)}),
            "notes": d.notes,
        }, None
    except Exception as e:  # noqa: BLE001 - robustness cases must not raise
        return None, f"{type(e).__name__}: {e}\n{traceback.format_exc(limit=3)}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lifemate-dir", required=True)
    ap.add_argument("--baseline-sha", required=True)
    ap.add_argument("--sealed", default=None,
                    help="optional sealed_cases.py (not committed)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    adapter = _load_adapter(args.lifemate_dir)
    cases = list(CASES)
    sealed_ids = []
    if args.sealed:
        import importlib.util
        spec = importlib.util.spec_from_file_location("sealed_cases", args.sealed)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        for c in mod.SEALED_CASES:
            c = dict(c)
            c["sealed"] = True
            cases.append(c)
            sealed_ids.append(c["id"])

    results = []
    for c in cases:
        dec, err = run_case(adapter, c)
        exp = c["expected_fired"]
        if err is not None:
            verdict = "RAISED"
            match = False
        elif c["needs_adjudication"] or exp is None:
            verdict = "RECORDED"
            match = None
        else:
            match = (dec["fired"] == exp)
            if match:
                verdict = "PASS"
            elif c.get("known_open_bug"):
                verdict = "KNOWN-OPEN-FAIL"
            else:
                verdict = "FAIL"
        results.append({
            "id": c["id"],
            "category": c["category"],
            "group": c["group"],
            "sealed": bool(c.get("sealed")),
            "expected_fired": exp,
            "actual_fired": dec["fired"] if dec else None,
            "applicable": dec["applicable"] if dec else None,
            "baseline_fired": dec["baseline_fired"] if dec else None,
            "adjustment_kinds": dec["adjustment_kinds"] if dec else None,
            "verdict": verdict,
            "error": err,
            "known_open_bug": c.get("known_open_bug"),
            "rationale": c["rationale"],
            "proves": c["proves"],
            "does_not_prove": c["does_not_prove"],
            "error_group": c["error_group"],
            "finding_class": c.get("finding_class", "contract"),
        })

    # IND-ROB-006: sequence independence — run two graded cases in both orders.
    seq = {}
    try:
        a = next(c for c in cases if c["id"] == "IND-CTRL-001")
        b = next(c for c in cases if c["id"] == "IND-ATK-001")
        da1, _ = run_case(adapter, a)
        db1, _ = run_case(adapter, b)
        db2, _ = run_case(adapter, b)
        da2, _ = run_case(adapter, a)
        seq = {
            "id": "IND-ROB-006",
            "category": "sequence-independence",
            "group": "robustness",
            "order1": {"CTRL-001": da1["fired"], "ATK-001": db1["fired"]},
            "order2": {"ATK-001": db2["fired"], "CTRL-001": da2["fired"]},
            "no_leak": (da1["fired"] == da2["fired"] and
                        db1["fired"] == db2["fired"]),
            "verdict": "PASS" if (da1["fired"] == da2["fired"] and
                                  db1["fired"] == db2["fired"]) else "FAIL",
        }
    except Exception as e:  # noqa: BLE001
        seq = {"id": "IND-ROB-006", "verdict": "RAISED",
               "error": f"{type(e).__name__}: {e}"}

    summary = {
        "baseline_sha": args.baseline_sha,
        "lifemate_dir": args.lifemate_dir,
        "n_cases": len(results),
        "n_sealed": len(sealed_ids),
        "verdict_counts": {},
        "known_open_fails": [r["id"] for r in results
                             if r["verdict"] == "KNOWN-OPEN-FAIL"],
        "fails": [r["id"] for r in results if r["verdict"] == "FAIL"],
        "fails_contract": [r["id"] for r in results
                           if r["verdict"] == "FAIL"
                           and r["finding_class"] == "contract"],
        "fails_scope": [r["id"] for r in results
                        if r["verdict"] == "FAIL"
                        and r["finding_class"] == "scope"],
        "raised": [r["id"] for r in results if r["verdict"] == "RAISED"],
    }
    for r in results:
        summary["verdict_counts"][r["verdict"]] = \
            summary["verdict_counts"].get(r["verdict"], 0) + 1

    output = {"summary": summary, "sequence_check": seq, "results": results}
    text = json.dumps(output, indent=1, ensure_ascii=False)
    if args.out:
        with open(args.out, "w") as f:
            f.write(text)
    print(text)
    # Exit code: 1 if any FAIL (not known-open); 2 on runner error is implicit.
    return 1 if summary["fails"] else 0


if __name__ == "__main__":
    sys.exit(main())
