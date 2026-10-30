"""R2-G3 (Group 3 lifecycle, Run 2): adapter-level validity probes.

These tests pin the two adapter bugs found by the R2-G3 probes
(workspace probe script R2G3_probes.py, 13/13 after the fix):

1. A patch-verified write's own returned fields are post-mutation
   state: they must survive the write's own mutation event.
   Before the fix, build_ledger kept evidence-before-mutation at a
   shared position, so the ledger self-killed the new field_value
   (contacts.update phone and calendar.update_event title both
   read back as invalidated instead of the new value).

2. Patch-verified tools without a PRODUCER_REGISTRY "id" mapping
   (e.g. calendar.update_event, tasks.complete, alarm.update)
   dropped their returned fields entirely. They now fall back to
   the PATCH_VERIFIED registry for a primary record (path
   None/"" / "item").

Documented residuals pinned here, not fixed by guessing:
- notes.append is neither PRODUCER_REGISTRY-listed nor
  patch-verified, so its field values stay unknown.
- Direct ledger eligibility queries return unknown by design:
  the adapter never emits eligibility records; check_eligibility
  is the API that computes eligible/ineligible/unknown.
- contacts.delete / tasks.delete / notes.delete /
  calendar.delete_event do not exist in the catalog today, so
  build_ledger correctly logs them as mutation_skipped instead
  of inventing a delete.

LifeMate only, CPU only, synthetic ids only (no gold/sample ids).
"""

import unittest

from lifemate.lifemate_evidence_lifecycle import check_eligibility
from lifemate.lifemate_gates_adapter import build_ledger

KINDS = {
    "tasks.list": "read", "tasks.add": "write", "tasks.complete": "write",
    "calendar.list_events": "read", "calendar.create_event": "write",
    "calendar.update_event": "write", "calendar.cancel_event": "write",
    "notes.list": "read", "notes.create": "write", "notes.append": "write",
    "reminders.list": "read", "reminders.delete": "write",
    "contacts.search": "read", "contacts.update": "write",
    "sms.send": "write",
}


def _entry(tool, args, result, pos):
    outcome = "succeeded"
    if result.get("ok") is False:
        outcome = "schema_rejected"
    elif result.get("ok") is True and result.get("done") is False:
        outcome = "noop"
    return {"tool": tool, "args": args, "result": result,
            "outcome": outcome, "position": pos, "origin": "session"}


class TestR2G3LifecycleAdapter(unittest.TestCase):
    def test_patch_update_new_phone_survives_own_mutation(self):
        prefix = [
            _entry("contacts.search", {},
                   {"ok": True, "contacts": [{"id": "c1",
                                              "phone": "0901111111"}]}, 0),
            _entry("contacts.update",
                   {"contact_id": "c1", "phone": "0902222222"},
                   {"ok": True, "item": {"id": "c1",
                                         "phone": "0902222222"}}, 1),
        ]
        ledger, _ = build_ledger(prefix, [], KINDS)
        self.assertEqual(
            ledger.query_field_value("contacts.contacts", "c1", "phone"),
            ("active", "0902222222", "evidence@pos1"))

    def test_patch_update_new_title_survives_via_patch_verified_fallback(self):
        prefix = [
            _entry("calendar.list_events", {},
                   {"ok": True, "events": [{"id": "e1",
                                            "title": "Old"}]}, 0),
            _entry("calendar.update_event",
                   {"event_id": "e1", "title": "New"},
                   {"ok": True, "item": {"id": "e1",
                                         "title": "New"}}, 1),
        ]
        ledger, _ = build_ledger(prefix, [], KINDS)
        self.assertEqual(
            ledger.query_field_value("calendar.events", "e1", "title"),
            ("active", "New", "evidence@pos1"))

    def test_cancel_status_is_post_mutation_active_cancelled(self):
        prefix = [
            _entry("calendar.list_events", {},
                   {"ok": True, "events": [{"id": "e1", "title": "X",
                                            "status": "scheduled"}]}, 0),
            _entry("calendar.cancel_event", {"event_id": "e1"},
                   {"ok": True, "item": {"id": "e1",
                                         "status": "cancelled"}}, 1),
        ]
        ledger, _ = build_ledger(prefix, [], KINDS)
        self.assertEqual(ledger.query("calendar.events", "e1", "existence")[0],
                         "active")
        self.assertEqual(
            ledger.query_field_value("calendar.events", "e1", "status"),
            ("active", "cancelled", "evidence@pos1"))
        self.assertEqual(
            ledger.query_field_value("calendar.events", "e1", "title"),
            ("active", "X", "evidence@pos0"))

    def test_update_without_returned_item_is_fail_closed_not_guessed(self):
        prefix = [
            _entry("calendar.list_events", {},
                   {"ok": True, "events": [{"id": "e1",
                                            "title": "Old"}]}, 0),
            _entry("calendar.update_event",
                   {"event_id": "e1", "title": "New"},
                   {"ok": True}, 1),
        ]
        ledger, _ = build_ledger(prefix, [], KINDS)
        self.assertEqual(
            ledger.query_field_value("calendar.events", "e1", "title")[0],
            "invalidated")

    def test_registry_isolation_same_id_tasks_vs_reminders(self):
        prefix = [
            _entry("tasks.list", {},
                   {"ok": True, "tasks": [{"id": "s1",
                                           "title": "A"}]}, 0),
            _entry("reminders.list", {},
                   {"ok": True, "reminders": [{"id": "s1",
                                               "title": "B"}]}, 1),
            _entry("reminders.delete", {"reminder_id": "s1"},
                   {"ok": True}, 2),
        ]
        ledger, _ = build_ledger(prefix, [], KINDS)
        self.assertEqual(ledger.query("tasks.tasks", "s1", "existence")[0],
                         "active")
        self.assertEqual(
            ledger.query("reminders.reminders", "s1", "existence")[0],
            "invalidated")
        self.assertEqual(
            check_eligibility(ledger, "tasks.complete", "s1", position=5),
            ("eligible", "entity_exists"))
        self.assertEqual(
            check_eligibility(ledger, "reminders.delete", "s1", position=5),
            ("ineligible", "entity_deleted"))

    def test_failed_read_and_write_echo_establish_nothing(self):
        prefix = [
            {"tool": "tasks.list", "args": {}, "result": {"ok": False},
             "outcome": "schema_rejected", "position": 0,
             "origin": "session"},
            _entry("sms.send", {"contact_id": "c_1"},
                   {"ok": True, "message": {"id": "m1",
                                            "contact_id": "c_1"}}, 1),
        ]
        ledger, _ = build_ledger(prefix, [], KINDS)
        self.assertEqual(ledger.query("tasks.tasks", "t1", "existence")[0],
                         "unknown")
        self.assertEqual(ledger.query("contacts.contacts", "c_1",
                                      "existence")[0], "unknown")
        self.assertEqual(ledger.query("sms.messages", "m1", "existence")[0],
                         "active")

    def test_tasks_calendar_notes_list_field_values_are_supported(self):
        for tool, key, registry, eid in [
                ("tasks.list", "tasks", "tasks.tasks", "t9"),
                ("calendar.list_events", "events", "calendar.events", "e9"),
                ("notes.list", "notes", "notes.notes", "n9")]:
            ledger, _ = build_ledger(
                [_entry(tool, {},
                        {"ok": True, key: [{"id": eid, "title": "T"}]}, 0)],
                [], KINDS)
            self.assertEqual(
                ledger.query_field_value(registry, eid, "title"),
                ("active", "T", "evidence@pos0"))

    def test_notes_append_field_value_not_established_residual(self):
        # notes.append is neither PRODUCER_REGISTRY-listed nor
        # patch-verified: its returned fields are not emitted, so
        # the new content is never established as active. The old
        # content record is killed by the update, so the query
        # returns invalidated (old value known stale), never
        # active with the new value -- fail-closed, not guessed.
        prefix = [
            _entry("notes.list", {},
                   {"ok": True, "notes": [{"id": "n1",
                                           "content": "old"}]}, 0),
            _entry("notes.append", {"note_id": "n1", "content": "new"},
                   {"ok": True, "item": {"id": "n1",
                                         "content": "old\nnew"}}, 1),
        ]
        ledger, _ = build_ledger(prefix, [], KINDS)
        self.assertEqual(
            ledger.query_field_value("notes.notes", "n1", "content"),
            ("invalidated", None, "field_updated@pos1"))


if __name__ == "__main__":
    unittest.main()
