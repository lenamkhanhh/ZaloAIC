"""R2-P0 (P0 lifecycle fix, Run 2): root-cause tests for the two
open findings from independent Check-A on the R2-G3 lifecycle
branch (ef7ae70). Companion to tests/test_lifecycle_adapter_r2g3.py
(8 tests, untouched): these tests pin the FIX, they do not replace
the old tests.

1. L-N3 patch-id mismatch (Check-A §3): on ef7ae70,
   calendar.update_event event_id=e1 returning item id=e2
   title=New made e2.title ACTIVE while e2 existence stayed
   unknown. Root cause: build_ledger's existence branch enforced
   patch id-arg == item id, but _field_value_events (which had
   no access to the call args) did not enforce it on the
   field-value path, including the PATCH_VERIFIED fallback.
   Fix: thread the call args through and require the equality
   for a primary record of a patch-verified tool, on BOTH the
   fallback and the PRODUCER_REGISTRY path (a contacts.update
   returning a different contact's record is the same
   over-establishment). A missing id-arg is a mismatch.

2. NEEDS_ASK bypass (Check-A §4, X7): a raw tail fed past a
   NEEDS_ASK gate became an active phone field, because the
   ledger never re-checked value validity. Fix: a validity
   shape gate in _field_value_events (see _valid_field_value):
   a phone field must norm to a complete 0-led number, a
   date/time field must be an ISO / time-only tool value.

R3-P0-PHONE correction to the R2-P0 phone rule (LifeMate only,
Chat 3 Run 3): the R2-P0 "10-digit only" rule was wrong. The
in-tree contract is NOT "every valid number is a 10-digit
mobile": norm_phone only folds 11-digit "84..." forms to 10
digits and otherwise preserves length; the gates accept a phone
by source (unique roster match or a succeeded log field) with
no length check; and 11-digit 0-led forms are attested as real
roster/log phones in-tree (09883322117, 09125430868, 09046612750)
and as routinely requested call numbers (09870001117,
09870011220, 09024180240, ...), plus the hotline 19001234 as a
dialable number. The corrected gate therefore accepts, after
norm_phone: phone = 0-led 10 or 11 digits; phone_number = the
same, plus the 1900xxxx hotline (8 digits). It still rejects
tails, short strings, missing-zero numbers, 9-digit 0-led
strings (no field example attests them; indistinguishable from
a truncated 10/11-digit number), and 12-digit strings. The old
test_incomplete_phone_not_active expectation that the 11-digit
form 09031112222 is incomplete is RETIRED by this correction:
that form is now a positive control (see
test_eleven_digit_contact_phone_active), not a regression.
A 12-digit "84..." form and an 1800xxxx hotline are NOT
attested in-tree and remain rejected (fail-closed residuals,
not claimed invalid in the real world).
   The gate never guesses, never completes a tail from the
   roster, never fills an hour from context or the clock, and
   never normalizes the stored value -- an invalid value is
   simply not established (invalidated if a mutation killed
   an older value, unknown if there was none), so the caller
   must ask, as grounding NEEDS_ASK already requires upstream.

LifeMate only, CPU only, synthetic ids only (no gold/sample ids).
Grounding cases here use the in-tree lifemate_grounding module
only (no grounding-branch import): in-tree grounding returns
NEEDS_ASK(hour) for a word-hour time with no digit hour, which
is the demonstrable NEEDS_ASK case in this tree; the phone-tail
case pins the ledger validity layer itself, which is the layer
that must hold whatever grounding version said NEEDS_ASK /
incomplete upstream.
"""

import unittest
from datetime import datetime

from lifemate.lifemate_evidence_lifecycle import (
    check_eligibility,
    make_prover_validity,
)
from lifemate.lifemate_gates_adapter import (
    _valid_field_value,
    build_ledger,
)
from lifemate.lifemate_grounding import ground_tool_call

KINDS = {
    "tasks.list": "read", "tasks.add": "write", "tasks.complete": "write",
    "calendar.list_events": "read", "calendar.create_event": "write",
    "calendar.update_event": "write", "calendar.cancel_event": "write",
    "notes.list": "read", "notes.create": "write", "notes.append": "write",
    "reminders.list": "read", "reminders.delete": "write",
    "contacts.search": "read", "contacts.update": "write",
    "alarm.list": "read", "alarm.update": "write", "sms.send": "write",
}


def _entry(tool, args, result, pos):
    outcome = "succeeded"
    if result.get("ok") is False:
        outcome = "schema_rejected"
    elif result.get("ok") is True and result.get("done") is False:
        outcome = "noop"
    return {"tool": tool, "args": args, "result": result,
            "outcome": outcome, "position": pos, "origin": "session"}


class TestR2P0LifecycleFix(unittest.TestCase):
    def test_patch_id_mismatch_calendar_title_unknown(self):
        prefix = [
            _entry("calendar.list_events", {},
                   {"ok": True, "events": [{"id": "e1",
                                            "title": "Old"}]}, 0),
            _entry("calendar.update_event",
                   {"event_id": "e1", "title": "New"},
                   {"ok": True, "item": {"id": "e2",
                                         "title": "New"}}, 1),
        ]
        ledger, _ = build_ledger(prefix, [], KINDS)
        self.assertEqual(
            ledger.query_field_value("calendar.events", "e2", "title"),
            ("unknown", None, "no_evidence"))
        self.assertEqual(
            ledger.query_field_value("calendar.events", "e1", "title"),
            ("invalidated", None, "field_updated@pos1"))
        self.assertEqual(
            ledger.query("calendar.events", "e2", "existence")[0],
            "unknown")

    def test_patch_id_mismatch_contacts_phone_unknown(self):
        # Same over-establishment via the PRODUCER_REGISTRY path
        # (contacts.update has a registry mapping, so the old
        # fallback-only fix would not have caught this one).
        prefix = [
            _entry("contacts.search", {},
                   {"ok": True, "contacts": [{"id": "c1",
                                              "phone": "0901111111"}]}, 0),
            _entry("contacts.update",
                   {"contact_id": "c1", "phone": "0902222222"},
                   {"ok": True, "item": {"id": "c2",
                                         "phone": "0902222222"}}, 1),
        ]
        ledger, _ = build_ledger(prefix, [], KINDS)
        self.assertEqual(
            ledger.query_field_value("contacts.contacts", "c2", "phone")[0],
            "unknown")
        self.assertEqual(
            ledger.query_field_value("contacts.contacts", "c1", "phone")[0],
            "invalidated")

    def test_patch_id_mismatch_tasks_done_unknown(self):
        # Fallback path again (tasks.complete has no
        # PRODUCER_REGISTRY "id" mapping), with a different tool.
        prefix = [
            _entry("tasks.list", {},
                   {"ok": True, "tasks": [{"id": "t1", "title": "Old",
                                           "done": False}]}, 0),
            _entry("tasks.complete", {"task_id": "t1"},
                   {"ok": True, "item": {"id": "t2", "title": "Old",
                                         "done": True}}, 1),
        ]
        ledger, _ = build_ledger(prefix, [], KINDS)
        self.assertEqual(
            ledger.query_field_value("tasks.tasks", "t2", "done")[0],
            "unknown")

    def test_patch_id_missing_arg_is_mismatch_not_pass(self):
        # No id-arg at all: the returned "New" must not become
        # the field value. No mutation event is emitted either
        # (no id_arg value), so the old value stays active --
        # fail-closed on both sides, never the new value.
        prefix = [
            _entry("calendar.list_events", {},
                   {"ok": True, "events": [{"id": "e1",
                                            "title": "Old"}]}, 0),
            _entry("calendar.update_event", {},
                   {"ok": True, "item": {"id": "e1",
                                         "title": "New"}}, 1),
        ]
        ledger, _ = build_ledger(prefix, [], KINDS)
        self.assertEqual(
            ledger.query_field_value("calendar.events", "e1", "title"),
            ("active", "Old", "evidence@pos0"))

    def test_raw_phone_tail_not_active_and_validity_not_active(self):
        prefix = [
            _entry("contacts.search", {},
                   {"ok": True, "contacts": [{"id": "c1",
                                              "phone": "0901111111"}]}, 0),
            _entry("contacts.update",
                   {"contact_id": "c1", "phone": "đuôi 222"},
                   {"ok": True, "item": {"id": "c1",
                                         "phone": "đuôi 222"}}, 1),
        ]
        ledger, _ = build_ledger(prefix, [], KINDS)
        self.assertEqual(
            ledger.query_field_value("contacts.contacts", "c1", "phone"),
            ("invalidated", None, "field_updated@pos1"))
        valid = make_prover_validity(ledger, 5)
        self.assertEqual(
            valid("contacts.update", "phone", "đuôi 222", "c1")[0],
            "invalidated")

    def test_train_0063_like_eleven_digit_search_phone_active(self):
        # R3-P0-PHONE, the reported regression: contacts.search
        # returning c_10.phone="09631116692" (11 digits) must
        # NOT read unknown/no_evidence merely for its length.
        # A second attested 11-digit roster form rides along.
        prefix = [
            _entry("contacts.search", {},
                   {"ok": True, "contacts": [
                       {"id": "c_10", "phone": "09631116692"},
                       {"id": "c_11", "phone": "09883322117"}]}, 0),
        ]
        ledger, _ = build_ledger(prefix, [], KINDS)
        self.assertEqual(
            ledger.query_field_value("contacts.contacts", "c_10",
                                     "phone"),
            ("active", "09631116692", "evidence@pos0"))
        self.assertEqual(
            ledger.query_field_value("contacts.contacts", "c_11",
                                     "phone"),
            ("active", "09883322117", "evidence@pos0"))

    def test_eleven_digit_contact_phone_update_active(self):
        # Same 11-digit acceptance on the patch path: a
        # patch-verified contacts.update to an attested
        # 11-digit form (09125430868, in-tree roster/proposal
        # form) becomes the active phone, and the old 10-digit
        # value is invalidated by the mutation, not kept.
        prefix = [
            _entry("contacts.search", {},
                   {"ok": True, "contacts": [{"id": "c1",
                                              "phone": "0901111111"}]},
                   0),
            _entry("contacts.update",
                   {"contact_id": "c1", "phone": "09125430868"},
                   {"ok": True, "item": {"id": "c1",
                                         "phone": "09125430868"}}, 1),
        ]
        ledger, _ = build_ledger(prefix, [], KINDS)
        self.assertEqual(
            ledger.query_field_value("contacts.contacts", "c1",
                                     "phone"),
            ("active", "09125430868", "evidence@pos1"))
        # The old R2-P0 "incomplete" 11-digit form is a
        # positive control now, not a negative one.
        prefix2 = [
            _entry("contacts.search", {},
                   {"ok": True, "contacts": [{"id": "c1",
                                              "phone": "0901111111"}]},
                   0),
            _entry("contacts.update",
                   {"contact_id": "c1", "phone": "09031112222"},
                   {"ok": True, "item": {"id": "c1",
                                         "phone": "09031112222"}}, 1),
        ]
        ledger2, _ = build_ledger(prefix2, [], KINDS)
        self.assertEqual(
            ledger2.query_field_value("contacts.contacts", "c1",
                                      "phone")[0], "active")

    def test_phone_number_shapes_direct_gate(self):
        # Direct gate controls for shapes with no registry
        # path in this file's KINDS (dial/log field): the
        # +84 fold, an attested 11-digit log form, and the
        # hotline pass; tails, short and overlong forms fail.
        # "phone" (contact record) does NOT take the hotline.
        for good in ("09046612750", "+84914061230", "19001234"):
            self.assertTrue(
                _valid_field_value("phone_number", good), good)
        self.assertTrue(_valid_field_value("phone", "09631116692"))
        self.assertTrue(_valid_field_value("phone", "0903111222"))
        self.assertFalse(_valid_field_value("phone", "19001234"))
        for bad in ("đuôi 222", "0903", "903111222", "1900123"):
            self.assertFalse(
                _valid_field_value("phone_number", bad), bad)
            self.assertFalse(_valid_field_value("phone", bad), bad)

    def test_incomplete_phone_not_active(self):
        # R3-P0-PHONE revision: missing-zero, 9-digit 0-led
        # truncated, short, and 12-digit forms are not
        # complete phones: none may become active. The old
        # list's 11-digit entry (09031112222) was WRONG
        # under the attested contract and moved to the
        # positive tests above; it is deliberately absent
        # here, not forgotten.
        for bad in ("903111222", "090311122", "0903",
                    "090311122222"):
            prefix = [
                _entry("contacts.search", {},
                       {"ok": True, "contacts": [{"id": "c1",
                                                  "phone": "0901111111"}]},
                       0),
                _entry("contacts.update",
                       {"contact_id": "c1", "phone": bad},
                       {"ok": True, "item": {"id": "c1",
                                             "phone": bad}}, 1),
            ]
            ledger, _ = build_ledger(prefix, [], KINDS)
            self.assertEqual(
                ledger.query_field_value(
                    "contacts.contacts", "c1", "phone")[0],
                "invalidated", bad)

    def test_hourless_time_needs_ask_and_raw_not_active(self):
        # In-tree grounding: word hour, no digit hour.
        g = ground_tool_call(
            {"name": "calendar.create_event",
             "arguments": {"title": "Hop",
                           "time": "ngày mai lúc tám giờ"}},
            {"current_time": datetime(2026, 10, 30, 9, 0)})
        self.assertEqual(g.status, "NEEDS_ASK")
        self.assertIn("time:hour", g.needs)
        # The raw string fed past that gate must not be active.
        prefix = [
            _entry("calendar.create_event",
                   {"title": "Hop", "time": "ngày mai lúc tám giờ"},
                   {"ok": True, "item": {"id": "e9", "title": "Hop",
                                         "time": "ngày mai lúc tám giờ"}},
                   0),
        ]
        ledger, _ = build_ledger(prefix, [], KINDS)
        self.assertEqual(
            ledger.query_field_value("calendar.events", "e9", "time"),
            ("unknown", None, "no_evidence"))
        valid = make_prover_validity(ledger, 5)
        self.assertEqual(
            valid("calendar.create_event", "time",
                  "ngày mai lúc tám giờ", "e9")[0],
            "unknown")

    def test_invalid_time_values_not_active(self):
        for bad in ("2026-02-30T08:00:00", "25:00"):
            prefix = [
                _entry("calendar.create_event",
                       {"title": "Hop", "time": bad},
                       {"ok": True, "item": {"id": "e9", "title": "Hop",
                                             "time": bad}}, 0),
            ]
            ledger, _ = build_ledger(prefix, [], KINDS)
            self.assertEqual(
                ledger.query_field_value(
                    "calendar.events", "e9", "time")[0],
                "unknown", bad)

    def test_valid_values_still_active(self):
        # No false_block: normalized phone, ISO time, and
        # time-only values (the values grounding passes through)
        # must stay active with exactly the new value.
        prefix = [
            _entry("contacts.search", {},
                   {"ok": True, "contacts": [{"id": "c1",
                                              "phone": "0901111111"}]}, 0),
            _entry("contacts.update",
                   {"contact_id": "c1", "phone": "0902222222"},
                   {"ok": True, "item": {"id": "c1",
                                         "phone": "0902222222"}}, 1),
            _entry("calendar.create_event",
                   {"title": "Hop", "time": "2026-10-31T08:00:00"},
                   {"ok": True, "item": {"id": "e9", "title": "Hop",
                                         "time": "2026-10-31T08:00:00"}},
                   2),
            _entry("alarm.update", {"alarm_id": "a1"},
                   {"ok": True, "item": {"id": "a1",
                                         "time": "08:00"}}, 3),
        ]
        ledger, _ = build_ledger(prefix, [], KINDS)
        self.assertEqual(
            ledger.query_field_value("contacts.contacts", "c1", "phone"),
            ("active", "0902222222", "evidence@pos1"))
        self.assertEqual(
            ledger.query_field_value("calendar.events", "e9", "time"),
            ("active", "2026-10-31T08:00:00", "evidence@pos2"))
        self.assertEqual(
            ledger.query_field_value("alarm.alarms", "a1", "time")[0],
            "active")
        self.assertEqual(
            check_eligibility(ledger, "contacts.update", "c1",
                              position=5),
            ("eligible", "entity_exists"))


if __name__ == "__main__":
    unittest.main()
