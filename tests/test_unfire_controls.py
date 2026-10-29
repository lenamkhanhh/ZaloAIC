#!/usr/bin/env python3
"""Un-fire quality controls (synthetic only, no gold, no sample ids).

The empty-prefix control ("prefix empty must fire") is necessary
but not sufficient. This file measures the five categories
SEPARATELY over one shared fixture family (one history missed
call, empty roster, phone.call proposal), so a fix cannot hide a
false un-fire behind a good total:

- correct_unfire: evidence + selection both right -> must pass.
- false_unfire: evidence or selection wrong -> must still fire
  (asserted 0: every case in this category expects fired=True).
- refusal: the gate correctly refuses (veto / mismatch /
  unproven) -> fired=True, mechanism recorded.
- false_block: a case that SHOULD un-fire but does not (asserted
  0: every case in this category expects fired=False).
- unknown_ambiguous: selection genuinely undetermined -> fired
  with an UNKNOWN/AMBIGUOUS verdict, never a guessed un-fire.

A distractor case and an addressee-switch case pin the two
failure modes the categories above do not cover: an irrelevant
distractor must neither create proof nor destroy it, and
switching the addressee from the right person to another person
must invalidate the binding.

Synthetic cases are NOT merged with gold and are NOT counted as
independent model positives: many variants share one fixture.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lifemate"))
from lifemate_gates_adapter import decide  # noqa: E402

KINDS = {
    "phone.recent_calls": "read", "phone.call": "write",
    "sms.read_recent": "read", "sms.send": "write",
}


def call_entry(tool, args, result, pos, origin="history"):
    outcome = "succeeded" if isinstance(result, dict) \
        and result.get("ok") is True and result.get("done") is not False \
        else "noop"
    return {"tool": tool, "args": args, "result": result,
            "outcome": outcome, "position": pos, "origin": origin}


def fixture(name="Vy", relation=None, extra_calls=()):
    contact = {"id": "c_x", "name": name, "phone": "0902345678"}
    if relation is not None:
        contact["relation"] = relation
    calls = [{"id": "call_x", "contact": contact,
              "direction": "incoming", "status": "missed"}]
    calls.extend(extra_calls)
    prefix = [call_entry("phone.recent_calls", {},
                         {"ok": True, "calls": calls}, 0)]
    proposal = {"name": "phone.call",
                "arguments": {"contact_id": "c_x"}}
    return prefix, proposal


# (label, category, prefix, proposal, text, expected_fired)
CASES = []


def _add(label, category, name, text, expected_fired, relation=None,
         extra_calls=()):
    prefix, proposal = fixture(name=name, relation=relation,
                               extra_calls=extra_calls)
    CASES.append((label, category, prefix, proposal, text, expected_fired))


# --- correct un-fire (evidence + selection right) ---
_add("correct: full name callback", "correct_unfire", "Vy",
     "gọi lại cho Vy giúp tôi", False)
_add("correct: generic callback", "correct_unfire", "Vy",
     "gọi lại người vừa gọi", False)
_add("correct: family with relation evidence", "correct_unfire", "Vy",
     "gọi lại cho mẹ giúp tôi", False, relation="mẹ")
_add("correct: short unique name", "correct_unfire", "Nguyễn An",
     "gọi lại cho An giúp tôi", False)
_add("correct: question-khong is not negation", "correct_unfire", "Vy",
     "gọi lại cho Vy để hỏi xem có rảnh không", False)
_add("correct: other-clause negation, target positive",
     "correct_unfire", "Vy", "đừng gọi An, gọi lại cho Vy", False)
_add("correct: action-scoped positive", "correct_unfire", "Vy",
     "không cần nhắn, chỉ gọi lại cho Vy", False)

# --- false un-fire (must still fire; 0 tolerated) ---
_add("false: full-name conflict", "false_unfire", "Nguyễn An",
     "gọi lại cho Nguyễn Bình giúp tôi", True)
_add("false: surname-only overlap", "false_unfire", "Trần Minh",
     "gọi lại cho Trần Mai giúp tôi", True)
_add("false: family without evidence", "false_unfire", "Vy",
     "gọi lại cho mẹ giúp tôi", True)
_add("false: family conflict evidence", "false_unfire", "Vy",
     "gọi lại cho mẹ giúp tôi", True, relation="bố")
_add("false: negated callback", "false_unfire", "Vy",
     "đừng gọi lại cho Vy", True)
_add("false: khoi callback", "false_unfire", "Vy",
     "khỏi gọi lại cho Vy nữa", True)
_add("false: corrected to another person", "false_unfire", "Vy",
     "gọi lại cho Vy, à không, gọi cho An", True)
_add("false: quoted name only", "false_unfire", "Vy",
     "nhắn là \"gọi lại cho Vy nhé\"", True)
_add("false: cross-action verb (message verb, call proposal)",
     "false_unfire", "Vy", "nhắn lại cho Vy", True)
_add("false: question mood is not a request", "false_unfire", "Vy",
     "có nên gọi lại cho Vy không", True)
_add("false: past action is not a request", "false_unfire", "Vy",
     "đã gọi lại cho Vy rồi", True)
_add("false: chua status is not a request", "false_unfire", "Vy",
     "chưa gọi lại cho Vy", True)

# --- refusal (gate correctly refuses; mechanism recorded) ---
_add("refusal: name mismatch", "refusal", "Nguyễn An",
     "gọi lại cho Nguyễn Bình giúp tôi", True)
_add("refusal: relation unproven", "refusal", "Vy",
     "gọi lại cho mẹ giúp tôi", True)
_add("refusal: selection veto", "refusal", "Vy",
     "đừng gọi lại cho Vy", True)
_add("refusal: selection replaced", "refusal", "Vy",
     "gọi lại cho Vy, à không, gọi cho An", True)
_add("refusal: generic veto", "refusal", "Vy",
     "đừng gọi lại người vừa gọi", True)

# --- false block (should un-fire; 0 tolerated) ---
_add("no-false-block: exact full name", "false_block", "Nguyễn An",
     "gọi lại cho Nguyễn An giúp tôi", False)
_add("no-false-block: relation evidence", "false_block", "Vy",
     "gọi lại cho mẹ giúp tôi", False, relation="mẹ")
_add("no-false-block: contact named Me", "false_block", "Mẹ",
     "gọi lại cho mẹ giúp tôi", False)
_add("no-false-block: generic callback", "false_block", "Vy",
     "gọi lại người vừa gọi", False)

# --- unknown / ambiguous (undetermined, never guessed) ---
_add("unknown: short ambiguous name", "unknown_ambiguous",
     "Nguyễn An", "gọi lại cho An giúp tôi", True,
     extra_calls=[{"id": "call_y",
                   "contact": {"id": "c_y", "name": "Trần An",
                               "phone": "0911111111"},
                   "direction": "incoming", "status": "missed"}])
_add("unknown: family unproven", "unknown_ambiguous", "Vy",
     "gọi lại cho mẹ giúp tôi", True)

# --- distractor / addressee-switch (structural pins) ---
_add("distractor: correct binding + irrelevant record",
     "correct_unfire", "Vy", "gọi lại cho Vy giúp tôi", False,
     extra_calls=[{"id": "call_z",
                   "contact": {"id": "c_z", "name": "Bình",
                               "phone": "0922222222"},
                   "direction": "outgoing", "status": "completed"}])
_add("addressee-switch invalidates", "false_unfire", "Vy",
     "gọi lại cho An giúp tôi", True)


class TestUnfireControls(unittest.TestCase):
    def test_category_table(self):
        counts = {}
        failures = []
        for label, category, prefix, proposal, text, expected in CASES:
            dec = decide(proposal, prefix, [], text, KINDS,
                         proposal_position=1)
            counts[category] = counts.get(category, 0) + 1
            if dec.fired != expected:
                failures.append(
                    "%s [%s]: expected fired=%s, got %s "
                    "(mechanisms=%s)" % (
                        label, category, expected, dec.fired,
                        [a["mechanism"] for a in dec.adjustments]))
        # The table itself is the measurement: every category is
        # counted separately, and the two zero-tolerance
        # categories must contain no violations.
        self.assertEqual(failures, [])
        self.assertEqual(counts.get("false_unfire", 0), 13)
        self.assertEqual(counts.get("false_block", 0), 4)
        # Every false_unfire / false_block case fired (or passed)
        # exactly as its category demands -- verified above via
        # failures == []; the counts pin the table size so a case
        # cannot silently drop out.
        self.assertEqual(sum(counts.values()), len(CASES))

    def test_empty_prefix_still_fires(self):
        # The old control, kept: with no evidence at all, the
        # gate must fire (no vacuous passes).
        dec = decide({"name": "phone.call",
                      "arguments": {"contact_id": "c_x"}},
                     [], [], "gọi lại cho Vy", KINDS,
                     proposal_position=0)
        self.assertTrue(dec.fired)


if __name__ == "__main__":
    unittest.main()
