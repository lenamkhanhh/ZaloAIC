#!/usr/bin/env python3
"""Coordinator adapter tests (synthetic only, no gold, no sample ids).

Covers: phone un-fire via user text, no un-fire when selection is
undetermined, callback un-fire via log counterpart, P3g session-log
filtering, P3c roster-multi + log, lifecycle suppression on delete,
cancel-keeps-existence, failed-delete-no-suppression, re-read
re-establishment, no suppression for bare phone numbers, bare
mutate-verb fire standing, unknown-consumer capping.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lifemate"))
from lifemate_gates_adapter import decide, filtered_prefix_for_phone  # noqa: E402

KINDS = {
    "contacts.search": "read", "contacts.get": "read",
    "contacts.update": "write", "contacts.delete": "write",
    "phone.recent_calls": "read", "phone.call": "write",
    "sms.read_recent": "read", "sms.send": "write",
    "banking.transfer": "write", "ewallet.transfer": "write",
    "calendar.create_event": "write", "calendar.update_event": "write",
    "calendar.cancel_event": "write", "tasks.add": "write",
    "tasks.complete": "write", "reminders.delete": "write",
    "email.send": "write",
}


def call_entry(tool, args, result, pos, origin="session"):
    outcome = "succeeded" if isinstance(result, dict) \
        and result.get("ok") is True and result.get("done") is not False \
        else ("failed" if isinstance(result, dict)
              and result.get("ok") is False else "noop")
    return {"tool": tool, "args": args, "result": result,
            "outcome": outcome, "position": pos, "origin": origin}


def user_turn(text, pos):
    return {"kind": "user_turn", "text": text, "position": pos}


def search_result(contacts):
    return {"ok": True, "contacts": contacts}


def recent_calls_result(calls):
    return {"ok": True, "calls": calls}


def call_log_call(cid, phone, direction="incoming", status="missed"):
    return {"id": "call_1", "contact": {"id": cid, "name": "Vy",
                                         "phone": phone},
            "direction": direction, "status": status}


class TestAdapter(unittest.TestCase):
    def test_phone_unfire_via_user_text(self):
        # No roster, no log: baseline fires; current text directly
        # requests the number -> adapter passes.
        prefix = []
        dec = decide({"name": "phone.call",
                      "arguments": {"phone_number": "0912345678"}},
                     prefix, [], "Gọi cho tôi số 0912345678 nhé",
                     KINDS, proposal_position=0)
        self.assertTrue(dec.baseline_fired)
        self.assertFalse(dec.fired)
        self.assertTrue(any(a["mechanism"] == "phone_callback_evidence"
                            for a in dec.adjustments))

    def test_phone_no_unfire_when_selection_undetermined(self):
        # Number grounded in log, but current text selects nothing
        # (no phone mention, no callback phrase) -> still fires.
        prefix = [call_entry(
            "phone.recent_calls", {},
            recent_calls_result([call_log_call("c_9", "0912345678")]),
            0, origin="history")]
        dec = decide({"name": "phone.call",
                      "arguments": {"phone_number": "0912345678"}},
                     prefix, [], "Nhắn tin giúp tôi", KINDS,
                     proposal_position=1)
        self.assertTrue(dec.baseline_fired)
        self.assertTrue(dec.fired)

    def test_callback_unfire_via_log_counterpart(self):
        # sms.send to a log counterpart with topic selection in
        # current text -> adapter passes (consumer needs no roster).
        prefix = [call_entry(
            "sms.read_recent", {},
            {"ok": True, "messages": [
                {"id": "m_1", "contact_id": "c_7",
                 "phone_number": "0912345678", "direction": "incoming",
                 "content": "Cho mình xin lại hai trăm nghìn nhé"}]},
            0, origin="history")]
        dec = decide({"name": "sms.send",
                      "arguments": {"contact_id": "c_7",
                                    "content": "Mình gửi lại hai trăm nghìn đây"}},
                     prefix, [], "Trả lời tin nhắn xin lại hai trăm nghìn",
                     KINDS, proposal_position=1)
        self.assertTrue(dec.baseline_fired)
        self.assertFalse(dec.fired)

    def test_p3g_session_created_log_filtered(self):
        # Session dials the number, then recent_calls lists it back
        # (outgoing). The baseline gate itself must NOT see that
        # record (filtered priors), and the anaphoric second dial
        # ("số đó", digits not restated) must still fire.
        prefix = [
            call_entry("phone.call", {"phone_number": "0912345678"},
                       {"ok": True, "phone_number": "0912345678"}, 0,
                       origin="session"),
            call_entry("phone.recent_calls", {},
                       recent_calls_result([
                           call_log_call("c_9", "0912345678",
                                         direction="outgoing",
                                         status="completed")]),
                       1, origin="session"),
        ]
        filtered, n = filtered_prefix_for_phone(prefix)
        self.assertEqual(n, 1)
        dec = decide({"name": "phone.call",
                      "arguments": {"phone_number": "0912345678"}},
                     prefix, [], "Gọi lại số đó", KINDS,
                     proposal_position=2)
        self.assertTrue(dec.baseline_fired)
        self.assertTrue(dec.fired)

    def test_p3g_restated_digits_legitimately_pass(self):
        # Same setup, but the current text restates the digits: the
        # number is grounded by user text itself, not by the
        # session-created log -- passing here is legitimate, not
        # laundering, and must be distinguished from the case above.
        prefix = [
            call_entry("phone.call", {"phone_number": "0912345678"},
                       {"ok": True, "phone_number": "0912345678"}, 0,
                       origin="session"),
            call_entry("phone.recent_calls", {},
                       recent_calls_result([
                           call_log_call("c_9", "0912345678",
                                         direction="outgoing",
                                         status="completed")]),
                       1, origin="session"),
        ]
        dec = decide({"name": "phone.call",
                      "arguments": {"phone_number": "0912345678"}},
                     prefix, [], "Gọi số 0912345678", KINDS,
                     proposal_position=2)
        self.assertFalse(dec.fired)

    def test_p3c_roster_multi_plus_log_passes(self):
        # Two roster contacts share the number, but a succeeded log
        # record grounds the NUMBER itself -> adapter passes.
        roster = [{"id": "c_1", "name": "A", "phone": "0912345678"},
                  {"id": "c_2", "name": "B", "phone": "0912345678"}]
        prefix = [call_entry(
            "phone.recent_calls", {},
            recent_calls_result([call_log_call("c_1", "0912345678")]),
            0, origin="history")]
        dec = decide({"name": "phone.call",
                      "arguments": {"phone_number": "0912345678"}},
                     prefix, roster, "Gọi số 0912345678", KINDS,
                     proposal_position=1)
        self.assertTrue(dec.baseline_fired)
        self.assertFalse(dec.fired)

    def test_suppression_delete_then_use(self):
        # Read establishes event e_1; delete kills it; later update
        # passes the baseline gate (stale prior) but must fire.
        prefix = [
            call_entry("calendar.create_event", {"title": "Hop"},
                       {"ok": True, "id": "e_1",
                        "item": {"id": "e_1", "title": "Hop"}}, 0,
                       origin="session"),
            call_entry("calendar.update_event", {"event_id": "e_1"},
                       {"ok": True, "item": {"id": "e_1"}}, 1,
                       origin="session"),
        ]
        # Baseline passes via the create/update priors; now delete.
        prefix2 = prefix + [
            call_entry("calendar.cancel_event", {"event_id": "e_1"},
                       {"ok": True, "item": {"id": "e_1",
                                             "status": "cancelled"}}, 2,
                       origin="session")]
        # cancel keeps existence -> still passes (control)
        dec = decide({"name": "calendar.update_event",
                      "arguments": {"event_id": "e_1", "title": "Moi"}},
                     prefix2, [], "", KINDS, proposal_position=3)
        self.assertFalse(dec.fired)
        # True delete (reminders.delete) kills existence.
        prefix3 = [
            call_entry("tasks.add", {"title": "T"},
                       {"ok": True, "id": "t_1",
                        "item": {"id": "t_1"}}, 0, origin="session"),
            call_entry("reminders.delete", {"reminder_id": "t_1"},
                       {"ok": True}, 1, origin="session"),
        ]
        # reminders.delete registry is reminders.reminders, while
        # tasks.add is tasks.tasks: different registries must NOT
        # suppress. Use a same-registry delete instead:
        prefix4 = [
            call_entry("tasks.add", {"title": "T"},
                       {"ok": True, "id": "t_1",
                        "item": {"id": "t_1"}}, 0, origin="session"),
            call_entry("tasks.complete", {"task_id": "t_1"},
                       {"ok": True, "item": {"id": "t_1",
                                             "done": True}}, 1,
                       origin="session"),
        ]
        dec4 = decide({"name": "tasks.complete",
                       "arguments": {"task_id": "t_1"}},
                      prefix4, [], "", KINDS, proposal_position=2)
        self.assertFalse(dec4.fired)  # complete is update, not delete

    def test_suppression_same_registry_delete(self):
        # reminders.create -> reminders.delete -> reminders.complete
        # on the same id: baseline passes (stale read), adapter fires.
        prefix = [
            call_entry("reminders.create", {"title": "R"},
                       {"ok": True, "id": "r_1",
                        "item": {"id": "r_1"}}, 0, origin="session"),
            call_entry("reminders.delete", {"reminder_id": "r_1"},
                       {"ok": True}, 1, origin="session"),
        ]
        dec = decide({"name": "reminders.complete",
                      "arguments": {"reminder_id": "r_1"}},
                     prefix, [], "", KINDS, proposal_position=2)
        self.assertFalse(dec.baseline_fired)
        self.assertTrue(dec.fired)
        self.assertTrue(any(a["mechanism"] == "lifecycle_suppression"
                            for a in dec.adjustments))

    def test_failed_delete_no_suppression(self):
        prefix = [
            call_entry("reminders.create", {"title": "R"},
                       {"ok": True, "id": "r_1",
                        "item": {"id": "r_1"}}, 0, origin="session"),
            call_entry("reminders.delete", {"reminder_id": "r_1"},
                       {"ok": False, "error": "schema"}, 1,
                       origin="session"),
        ]
        dec = decide({"name": "reminders.complete",
                      "arguments": {"reminder_id": "r_1"}},
                     prefix, [], "", KINDS, proposal_position=2)
        self.assertFalse(dec.fired)

    def test_reread_reestablishes(self):
        # Delete kills, then a later read result re-establishes the
        # same id (fresh evidence record after the delete).
        prefix = [
            call_entry("reminders.create", {"title": "R"},
                       {"ok": True, "id": "r_1",
                        "item": {"id": "r_1"}}, 0, origin="session"),
            call_entry("reminders.delete", {"reminder_id": "r_1"},
                       {"ok": True}, 1, origin="session"),
            call_entry("contacts.search", {"query": "R"},
                       {"ok": True, "contacts": []}, 2,
                       origin="session"),
        ]
        # Re-read via a read result carrying the id: use a synthetic
        # read whose result contains the id in a reminders-registry
        # field is not available through real tools, so instead
        # verify the ledger directly: evidence after delete wins.
        from lifemate_evidence_lifecycle import EvidenceLedger  # noqa
        ledger = EvidenceLedger()
        ledger.apply_prefix([
            {"kind": "entity", "value": "r_1",
             "registry": "reminders.reminders", "claim": "existence",
             "field": "id", "outcome": "succeeded", "position": 0,
             "producer": "reminders.create", "source": "write_result",
             "status": "active", "counterpart": None, "reason": "t"},
            {"tool": "reminders.delete",
             "args": {"reminder_id": "r_1"}, "result": {"ok": True},
             "position": 1, "registry": "reminders.reminders",
             "entity_value": "r_1", "mutation_kind": "delete",
             "effective": True},
            {"kind": "entity", "value": "r_1",
             "registry": "reminders.reminders", "claim": "existence",
             "field": "id", "outcome": "succeeded", "position": 2,
             "producer": "reminders.get", "source": "read_result",
             "status": "active", "counterpart": None, "reason": "t"},
        ])
        status, _ev, _reason = ledger.query(
            "reminders.reminders", "r_1", "existence", position=3)
        self.assertEqual(status, "active")
        _ = prefix

    def test_no_suppression_for_bare_phone(self):
        # Phone passes via roster; the contact is deleted after;
        # the NUMBER is still dialable -> adapter still passes.
        roster = [{"id": "c_1", "name": "An", "phone": "0912345678"}]
        prefix = [
            call_entry("contacts.delete", {"contact_id": "c_1"},
                       {"ok": True}, 0, origin="session"),
        ]
        dec = decide({"name": "phone.call",
                      "arguments": {"phone_number": "0912345678"}},
                     prefix, roster, "Gọi số 0912345678", KINDS,
                     proposal_position=1)
        self.assertFalse(dec.fired)

    def test_bare_mutate_fire_stands(self):
        # contacts.delete with no id and no prior read of the
        # contacts family: baseline fires (mutate verb, no prior
        # read); nothing to un-fire.
        dec = decide({"name": "contacts.delete",
                      "arguments": {}},
                     [], [], "", KINDS, proposal_position=0)
        self.assertTrue(dec.baseline_fired)
        self.assertTrue(dec.fired)

    def test_unknown_consumer_capped(self):
        # banking.transfer is not in A's consumer map (requires
        # None): observed counterpart + selection must NOT un-fire.
        prefix = [call_entry(
            "sms.read_recent", {},
            {"ok": True, "messages": [
                {"id": "m_1", "contact_id": "c_7",
                 "phone_number": "0912345678", "direction": "incoming",
                 "content": "Chuyen khoan giup minh"}]},
            0, origin="history")]
        dec = decide({"name": "banking.transfer",
                      "arguments": {"contact_id": "c_7",
                                    "amount": 100000}},
                     prefix, [], "Chuyển khoản cho người nhắn tin",
                     KINDS, proposal_position=1)
        self.assertTrue(dec.baseline_fired)
        self.assertTrue(dec.fired)


class TestReviewerRound2Adapter(unittest.TestCase):
    """Reviewer round-2 follow-ups at adapter level: email.archive
    branch reclassification (R2-B2), callback name veto (R2-A3),
    fixed-field forwarding (R2-B1)."""

    def test_email_archive_delete_suppresses(self):
        # Prior read establishes em_1; archive-delete kills it;
        # a later archive proposal passes baseline but must fire.
        prefix = [
            call_entry("email.read", {"email_id": "em_1"},
                       {"ok": True, "email": {"id": "em_1"}}, 0,
                       origin="session"),
            call_entry("email.archive",
                       {"email_id": "em_1", "action": "delete"},
                       {"ok": True}, 1, origin="session"),
        ]
        kinds = dict(KINDS)
        kinds.update({"email.read": "read", "email.archive": "write"})
        dec = decide({"name": "email.archive",
                      "arguments": {"email_id": "em_1",
                                    "action": "archive"}},
                     prefix, [], "", kinds, proposal_position=2)
        self.assertFalse(dec.baseline_fired)
        self.assertTrue(dec.fired)
        self.assertTrue(any(a["mechanism"] == "lifecycle_suppression"
                            for a in dec.adjustments))

    def test_email_archive_folder_no_suppression(self):
        prefix = [
            call_entry("email.read", {"email_id": "em_1"},
                       {"ok": True, "item": {"id": "em_1"}}, 0,
                       origin="session"),
            call_entry("email.archive",
                       {"email_id": "em_1", "action": "archive"},
                       {"ok": True, "item": {"id": "em_1",
                                             "folder": "archive"}},
                       1, origin="session"),
        ]
        kinds = dict(KINDS)
        kinds.update({"email.read": "read", "email.archive": "write"})
        dec = decide({"name": "email.archive",
                      "arguments": {"email_id": "em_1",
                                    "action": "archive"}},
                     prefix, [], "", kinds, proposal_position=2)
        self.assertFalse(dec.fired)

    def test_callback_name_mismatch_no_unfire(self):
        # Baseline fires on c_111 (not in roster); the log has a
        # missed call from Bình, but the text names An -> the
        # veto must keep the gate fired.
        prefix = [call_entry(
            "phone.recent_calls", {},
            recent_calls_result(
                [dict(call_log_call("c_111", "0911111111"),
                      name="Bình")]),
            0, origin="history")]
        dec = decide({"name": "phone.call",
                      "arguments": {"contact_id": "c_111"}},
                     prefix, [], "gọi lại cho An giúp tôi",
                     KINDS, proposal_position=1)
        self.assertTrue(dec.baseline_fired)
        self.assertTrue(dec.fired)

    def test_fixed_field_forwarding_logged(self):
        from lifemate_gates_adapter import build_ledger
        prefix = [call_entry("tasks.complete", {"task_id": "t_1"},
                             {"ok": True, "item": {"id": "t_1",
                                                   "done": True}},
                             0, origin="session")]
        _, notes = build_ledger(prefix, [], KINDS)
        self.assertIn(("tasks.complete", ["done"]),
                      notes["mutation_fields"])


class TestIntegrationReviewFails(unittest.TestCase):
    """Fixes for the independent integration review's FAIL-1/2/3
    and C2 latent hole (name suppression)."""

    def test_p3g_real_shape_no_direction_dialing(self):
        # FAIL-1+2: real phone.recent_calls shape (flat, no
        # direction key, status dialing) from a session dial
        # must be filtered; the anaphoric redial must fire.
        prefix = [
            call_entry("phone.call", {"phone_number": "0912345678"},
                       {"ok": True, "call": {"id": "call_1",
                                             "phone_number": "0912345678",
                                             "status": "dialing"}},
                       0, origin="session"),
            call_entry("phone.recent_calls", {},
                       {"ok": True, "calls": [
                           {"id": "call_1", "contact_id": None,
                            "phone_number": "0912345678",
                            "status": "dialing"}]},
                       1, origin="session"),
        ]
        filt, n = filtered_prefix_for_phone(prefix)
        self.assertEqual(n, 1)
        dec = decide({"name": "phone.call",
                      "arguments": {"phone_number": "0912345678"}},
                     prefix, [], "gọi lại số đó đi",
                     KINDS, proposal_position=2)
        self.assertTrue(dec.fired)

    def test_p3g_presession_received_without_direction_kept(self):
        # Direction-missing + status received is pre-session
        # evidence, not laundering: never filtered.
        prefix = [call_entry(
            "phone.recent_calls", {},
            {"ok": True, "calls": [
                {"id": "call_9", "phone_number": "0988888888",
                 "status": "received"}]},
            0, origin="history")]
        _, n = filtered_prefix_for_phone(prefix)
        self.assertEqual(n, 0)

    def test_p3g_contact_id_dial_filtered(self):
        # A dial by contact_id resolves to a number the args
        # never show; the re-read record must still be filtered
        # via its contact_id.
        prefix = [
            call_entry("phone.call", {"contact_id": "c_77"},
                       {"ok": True, "call": {"id": "call_2",
                                             "contact_id": "c_77",
                                             "phone_number": "0900000001",
                                             "status": "dialing"}},
                       0, origin="session"),
            call_entry("phone.recent_calls", {},
                       {"ok": True, "calls": [
                           {"id": "call_2", "contact_id": "c_77",
                            "phone_number": "0900000001",
                            "status": "dialing"}]},
                       1, origin="session"),
        ]
        _, n = filtered_prefix_for_phone(prefix)
        self.assertEqual(n, 1)

    def test_scene_run_id_shape_emits(self):
        # FAIL-3: real scene_run results key devices by "id".
        from lifemate_gates_adapter import build_ledger
        kinds = dict(KINDS)
        kinds["smart_home.scene_run"] = "write"
        _, notes = build_ledger(
            [call_entry("smart_home.scene_run", {},
                        {"ok": True, "devices": [{"id": "d1"}]},
                        0, origin="session")],
            [], kinds)
        self.assertGreaterEqual(notes["mutation_events"], 1)
        self.assertEqual(notes["mutation_skipped"], [])

    def test_unknown_tool_skip_logged(self):
        from lifemate_gates_adapter import build_ledger
        _, notes = build_ledger(
            [call_entry("contacts.delete", {"contact_id": "c_1"},
                        {"ok": True}, 0, origin="session")],
            [], KINDS)
        self.assertTrue(any("MUTATION_TABLE" in s[2]
                            for s in notes["mutation_skipped"]))

    def test_name_resolution_helper_unique_ambiguous_missing(self):
        # C2 latent hole: the name->id resolution itself is
        # unit-testable even though no contacts.delete exists
        # today to invalidate a contact end-to-end.
        from lifemate_gates_adapter import _resolve_roster_name
        roster = [{"id": "c_1", "name": "An"},
                  {"id": "c_2", "name": "Bình"},
                  {"id": "c_3", "name": "An"}]
        self.assertEqual(_resolve_roster_name(roster, "Bình"), "c_2")
        self.assertIsNone(_resolve_roster_name(roster, "An"))
        self.assertIsNone(_resolve_roster_name(roster, "Vy"))
        self.assertIsNone(_resolve_roster_name([], "An"))

    def test_name_passes_when_contact_alive(self):
        # Control: a roster name passing baseline with no
        # invalidation must NOT be suppressed.
        roster = [{"id": "c_5", "name": "An",
                   "phone": "0912345678"}]
        kinds = dict(KINDS)
        kinds.update({"contacts.search": "read",
                      "contacts.update": "write"})
        prefix = [call_entry("contacts.search", {"query": "An"},
                             {"ok": True, "contacts": [roster[0]]},
                             0, origin="session")]
        dec = decide({"name": "contacts.update",
                      "arguments": {"contact_id": "c_5",
                                    "phone": "0999999999"}},
                     prefix, roster, "Cập nhật số cho An",
                     kinds, proposal_position=1)
        self.assertFalse(dec.fired)


if __name__ == "__main__":
    unittest.main()
