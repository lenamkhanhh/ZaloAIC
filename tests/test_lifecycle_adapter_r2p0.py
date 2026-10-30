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
   a phone field must norm to a complete 10-digit 0-number, a
   date/time field must be an ISO / time-only tool value.
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
from lifemate.lifemate_gates_adapter import build_ledger
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

    def test_incomplete_phone_not_active(self):
        # 9-digit missing-zero and 11-digit non-84 numbers are
        # not complete phones: neither may become active.
        for bad in ("903111222", "09031112222"):
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
