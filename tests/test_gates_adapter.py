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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lifemate.lifemate_gates_adapter import (  # noqa: E402
    _vetoed_by_selection,
    build_ledger,
    decide,
    filtered_prefix_for_phone,
)
from lifemate.lifemate_evidence_lifecycle import check_eligibility  # noqa: E402

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
        from lifemate.lifemate_evidence_lifecycle import EvidenceLedger  # noqa
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
        from lifemate.lifemate_gates_adapter import build_ledger
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
        from lifemate.lifemate_gates_adapter import build_ledger
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
        from lifemate.lifemate_gates_adapter import build_ledger
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
        from lifemate.lifemate_gates_adapter import _resolve_roster_name
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


class TestCallbackFixR1R2R3(unittest.TestCase):
    """Coordinator integration tests: R1/R2/R3 via decide().

    Fixture mirrors the user's repro: one history missed call
    with a nested contact record, empty roster, phone.call
    proposal for the logged contact id.
    """

    def _fixture(self, name, relation=None):
        contact = {"id": "c_x", "name": name, "phone": "0902345678"}
        if relation is not None:
            contact["relation"] = relation
        prefix = [call_entry(
            "phone.recent_calls", {},
            recent_calls_result([{
                "id": "call_x", "contact": contact,
                "direction": "incoming", "status": "missed"}]),
            0, origin="history")]
        proposal = {"name": "phone.call",
                    "arguments": {"contact_id": "c_x"}}
        return prefix, proposal

    def _decide(self, prefix, proposal, text):
        return decide(proposal, prefix, [], text, KINDS,
                      proposal_position=1)

    def _mechanisms(self, dec):
        return [a["mechanism"] for a in dec.adjustments]

    def test_r1_full_name_conflict_no_unfire(self):
        prefix, proposal = self._fixture("Nguyễn An")
        dec = self._decide(prefix, proposal,
                           "gọi lại cho Nguyễn Bình giúp tôi")
        self.assertTrue(dec.baseline_fired)
        self.assertTrue(dec.fired)
        self.assertTrue(any(
            "callback_name_mismatch" in (a.get("question_b_reason") or "")
            for a in dec.adjustments))

    def test_r1_full_name_correct_still_unfires(self):
        # Control: the R1 fix must not block a correct binding.
        prefix, proposal = self._fixture("Nguyễn An")
        dec = self._decide(prefix, proposal,
                           "gọi lại cho Nguyễn An giúp tôi")
        self.assertTrue(dec.baseline_fired)
        self.assertFalse(dec.fired)

    def test_r2_family_no_evidence_no_unfire(self):
        prefix, proposal = self._fixture("Vy")
        dec = self._decide(prefix, proposal,
                           "gọi lại cho mẹ giúp tôi")
        self.assertTrue(dec.baseline_fired)
        self.assertTrue(dec.fired)
        self.assertTrue(any(
            "callback_relation_unproven" in
            (a.get("question_b_reason") or "")
            for a in dec.adjustments))

    def test_r2_family_with_log_relation_unfires(self):
        # Relation evidence from the log record's relation field
        # (structured source), not from prose: binds.
        prefix, proposal = self._fixture("Vy", relation="mẹ")
        dec = self._decide(prefix, proposal,
                           "gọi lại cho mẹ giúp tôi")
        self.assertTrue(dec.baseline_fired)
        self.assertFalse(dec.fired)

    def test_r2_family_conflict_no_unfire(self):
        prefix, proposal = self._fixture("Vy", relation="bố")
        dec = self._decide(prefix, proposal,
                           "gọi lại cho mẹ giúp tôi")
        self.assertTrue(dec.fired)

    def test_r2_contact_named_me_binds_by_name(self):
        # A contact literally named "Mẹ" binds by NAME rules
        # (single-token exact), not by the relation path.
        prefix, proposal = self._fixture("Mẹ")
        dec = self._decide(prefix, proposal,
                           "gọi lại cho mẹ giúp tôi")
        self.assertFalse(dec.fired)

    def test_r3_negated_no_unfire_veto_recorded(self):
        prefix, proposal = self._fixture("Vy")
        dec = self._decide(prefix, proposal, "đừng gọi lại cho Vy")
        self.assertTrue(dec.baseline_fired)
        self.assertTrue(dec.fired)
        vetoes = [a for a in dec.adjustments
                  if a["mechanism"] == "callback_selection_veto"]
        self.assertEqual(len(vetoes), 1)
        self.assertEqual(vetoes[0]["selection"], "negated")
        self.assertTrue(vetoes[0]["mention_present"])

    def test_r3_correction_replaced_no_unfire(self):
        prefix, proposal = self._fixture("Vy")
        dec = self._decide(prefix, proposal,
                           "gọi lại cho Vy, à không, gọi cho An")
        self.assertTrue(dec.fired)
        vetoes = [a for a in dec.adjustments
                  if a["mechanism"] == "callback_selection_veto"]
        self.assertEqual(vetoes[0]["selection"], "replaced")

    def test_r3_negated_other_clause_positive_still_unfires(self):
        prefix, proposal = self._fixture("Vy")
        dec = self._decide(prefix, proposal,
                           "đừng gọi An, gọi lại cho Vy")
        self.assertFalse(dec.fired)

    def test_r3_action_scoping_positive_still_unfires(self):
        prefix, proposal = self._fixture("Vy")
        dec = self._decide(prefix, proposal,
                           "không cần nhắn, chỉ gọi lại cho Vy")
        self.assertFalse(dec.fired)

    def test_r3_question_khong_positive_still_unfires(self):
        prefix, proposal = self._fixture("Vy")
        dec = self._decide(
            prefix, proposal,
            "gọi lại cho Vy để hỏi xem có rảnh không")
        self.assertFalse(dec.fired)

    def test_r3_phone_correction_vetoed(self):
        # A establishes the first number (value directly
        # requested) but B sees the correction to another number:
        # the veto layer refuses the un-fire.
        prefix, _proposal = self._fixture("Vy")
        dec = decide({"name": "phone.call",
                      "arguments": {"phone_number": "0902345678"}},
                     prefix, [],
                     "gọi số 0902345678, à không, gọi số 0911111111",
                     KINDS, proposal_position=1)
        self.assertTrue(dec.baseline_fired)
        self.assertTrue(dec.fired)
        vetoes = [a for a in dec.adjustments
                  if a["mechanism"] == "callback_selection_veto"]
        self.assertEqual(len(vetoes), 1)
        self.assertEqual(vetoes[0]["selection"], "replaced")

    def test_phone_direct_negation_refused_by_module_a(self):
        # Pre-existing A layer (not this round's veto): a directly
        # negated number never reaches PROVEN, so the outcome is
        # a refusal at A, not a B veto. Both layers refuse; the
        # test pins which one, so a future change is visible.
        dec = decide({"name": "phone.call",
                      "arguments": {"phone_number": "0902345678"}},
                     [], [], "đừng gọi số 0902345678",
                     KINDS, proposal_position=0)
        self.assertTrue(dec.baseline_fired)
        self.assertTrue(dec.fired)
        self.assertTrue(any(
            a["mechanism"] == "phone_callback_evidence_insufficient"
            and "value_negated_in_current_text" in
            (a.get("question_b_reason") or "")
            for a in dec.adjustments))
        self.assertFalse(any(
            a["mechanism"] == "callback_selection_veto"
            for a in dec.adjustments))

    def test_r3_generic_negated_blocks(self):
        prefix, proposal = self._fixture("Vy")
        dec = self._decide(prefix, proposal,
                           "đừng gọi lại người vừa gọi")
        self.assertTrue(dec.fired)

    def test_r3_quoted_name_is_not_selection(self):
        # Name only inside quoted message content: not an
        # addressee, so no binding and no un-fire.
        prefix, proposal = self._fixture("Vy")
        dec = self._decide(prefix, proposal,
                           "nhắn là \"gọi lại cho Vy nhé\"")
        self.assertTrue(dec.fired)

    def test_noncallback_target_veto_blocks(self):
        # Hole found by coordinator probe (P4b): a negated
        # callback sentence used to un-fire a NON-callback
        # proposal (ewallet.transfer) via callback binding. The
        # refined veto gate closes it: a decisive,
        # target-attached veto blocks regardless of proposal tool.
        prefix, _proposal = self._fixture("Vy")
        dec = decide({"name": "ewallet.transfer",
                      "arguments": {"contact_id": "c_x",
                                    "amount": 200000}},
                     prefix, [], "đừng gọi lại cho Vy",
                     KINDS, proposal_position=1)
        self.assertTrue(dec.baseline_fired)
        self.assertTrue(dec.fired)
        vetoes = [a for a in dec.adjustments
                  if a["mechanism"] == "callback_selection_veto"]
        self.assertEqual(len(vetoes), 1)
        self.assertEqual(vetoes[0]["selection"], "negated")

    def test_veto_rule_helper(self):
        # Callback proposals: decisive vetoes always veto; unknown
        # vetoes except no_callback_verb (B abstains when the
        # current text has no verb head of any action, so a
        # history-grounded binding stands). Delta-2: the old
        # no_action_evidence conflated "no verb at all" with
        # "other-action verb" and "blocked verb"; all three new
        # reasons veto for callback proposals.
        self.assertTrue(_vetoed_by_selection("negated", "x", True))
        self.assertTrue(_vetoed_by_selection(
            "unknown", "quoted_mention_only", True))
        self.assertTrue(_vetoed_by_selection(
            "unknown", "no_current_text", True))
        self.assertTrue(_vetoed_by_selection(
            "unknown", "blocked_verb_only", True))
        self.assertTrue(_vetoed_by_selection(
            "unknown", "other_action_verb_only", True))
        self.assertTrue(_vetoed_by_selection(
            "unknown", "negated_other_object", True))
        self.assertFalse(_vetoed_by_selection(
            "unknown", "no_callback_verb", True))
        self.assertFalse(_vetoed_by_selection("positive", "x", True))
        # Non-callback proposals: decisive target-attached vetoes
        # count; unknown and standalone generic vetoes do not.
        self.assertTrue(_vetoed_by_selection(
            "negated", "negated_selection", False))
        self.assertTrue(_vetoed_by_selection(
            "replaced", "replaced_by_new_target", False))
        self.assertTrue(_vetoed_by_selection(
            "cancelled", "cancelled_no_new_target", False))
        self.assertFalse(_vetoed_by_selection(
            "unknown", "no_callback_verb", False))
        self.assertFalse(_vetoed_by_selection(
            "negated", "generic_callback_negated", False))
        self.assertFalse(_vetoed_by_selection(
            "positive", "positive_selection", False))

    def test_history_grounded_binding_survives_verb_less_text(self):
        # 0764 class (synthetic): the number comes from a prior
        # instruction in history; the current text invokes it
        # without any callback verb. B returns unknown /
        # no_callback_verb and must abstain, not veto.
        prefix = [user_turn("gọi cho số 0902345678 nhé", 0)]
        dec = decide({"name": "phone.call",
                      "arguments": {"phone_number": "0902345678"}},
                     prefix, [], "làm như em dặn lúc nãy",
                     KINDS, proposal_position=1)
        self.assertTrue(dec.baseline_fired)
        self.assertFalse(dec.fired)
        self.assertFalse(any(
            a["mechanism"] == "callback_selection_veto"
            for a in dec.adjustments))

    def test_cross_action_verb_does_not_unfire_call(self):
        # Reviewer delta-2 X1: a positive MESSAGE verb must not
        # un-fire a CALL proposal. A binds via the message verb;
        # B (action=call) sees only another action's verb and
        # vetoes with other_action_verb_only.
        prefix, proposal = self._fixture("Vy")
        dec = self._decide(prefix, proposal, "nhắn lại cho Vy")
        self.assertTrue(dec.baseline_fired)
        self.assertTrue(dec.fired)
        vetoes = [a for a in dec.adjustments
                  if a["mechanism"] == "callback_selection_veto"]
        self.assertEqual(len(vetoes), 1)
        self.assertEqual(vetoes[0]["selection"], "unknown")
        self.assertEqual(vetoes[0]["selection_reason"],
                         "other_action_verb_only")

    def test_cross_action_verb_does_not_unfire_message(self):
        # Reviewer delta-2 X2, reverse direction: a positive CALL
        # verb must not un-fire an SMS proposal.
        prefix, _proposal = self._fixture("Vy")
        dec = decide({"name": "sms.send",
                      "arguments": {"contact_id": "c_x",
                                    "content": "hello"}},
                     prefix, [], "gọi lại cho Vy",
                     KINDS, proposal_position=1)
        self.assertTrue(dec.baseline_fired)
        self.assertTrue(dec.fired)
        vetoes = [a for a in dec.adjustments
                  if a["mechanism"] == "callback_selection_veto"]
        self.assertEqual(len(vetoes), 1)
        self.assertEqual(vetoes[0]["selection_reason"],
                         "other_action_verb_only")

    def test_blocked_verbs_do_not_unfire(self):
        # Reviewer delta-2 G9/G10/G11: question mood, past, and
        # "chưa" status are blocked verbs, not requests. Each
        # must veto (blocked_verb_only), not abstain.
        prefix, proposal = self._fixture("Vy")
        for text in ["có nên gọi lại cho Vy không",
                     "đã gọi lại cho Vy rồi",
                     "chưa gọi lại cho Vy"]:
            dec = self._decide(prefix, proposal, text)
            self.assertTrue(dec.fired, text)
            vetoes = [a for a in dec.adjustments
                      if a["mechanism"] == "callback_selection_veto"]
            self.assertEqual(len(vetoes), 1, text)
            self.assertEqual(vetoes[0]["selection_reason"],
                             "blocked_verb_only", text)

    def test_reply_verb_is_message_action(self):
        # "trả lời" is a message verb: it selects for sms.send
        # but must not un-fire a phone.call proposal.
        prefix, proposal = self._fixture("Vy")
        dec = self._decide(prefix, proposal, "trả lời Vy giúp tôi")
        self.assertTrue(dec.fired)
        dec = decide({"name": "sms.send",
                      "arguments": {"contact_id": "c_x",
                                    "content": "hello"}},
                     prefix, [], "trả lời Vy giúp tôi",
                     KINDS, proposal_position=1)
        self.assertFalse(dec.fired)


class TestLayerCR4(unittest.TestCase):
    """Layer C adapter tests (thread A, R4): bound-reference
    selections must also prove continuation.

    Fixture: history user turns only (no log records, no
    roster), phone.call proposal for the instructed number.
    Baseline fires because the number has no roster/log source;
    module A binds it via the prior-instruction reference, so
    every outcome below is decided by layer B + layer C, not
    by the baseline gate.
    """

    OLD = "0902345678"
    NEW = "0912345678"

    def _prefix(self, *texts):
        return [user_turn(t, i) for i, t in enumerate(texts)]

    def _decide(self, prefix, text, number=None, tool="phone.call"):
        proposal = {"name": tool,
                    "arguments": {"phone_number": number or self.OLD}}
        return decide(proposal, prefix, [], text, KINDS)

    def _instr(self, dec):
        adjs = [a for a in dec.adjustments
                if a.get("instruction_selection") is not None]
        return adjs[0] if adjs else None

    def test_r4_control_unfires_with_continuation_basis(self):
        prefix = self._prefix("Gọi số 0902345678 giúp tôi")
        dec = self._decide(prefix, "Làm như em dặn lúc nãy")
        self.assertTrue(dec.baseline_fired)
        self.assertFalse(dec.fired)
        adj = self._instr(dec)
        self.assertIsNotNone(adj)
        self.assertEqual(adj["instruction_selection"], "continue")
        self.assertEqual(adj["instruction_reason"],
                         "instruction_continuation")

    def test_r4_cancellations_fire(self):
        prefix = self._prefix("Gọi số 0902345678 giúp tôi")
        for text in ["Thôi, không cần làm như em dặn lúc nãy nữa",
                     "Khỏi làm như lúc nãy nữa",
                     "Đừng làm như em dặn lúc nãy"]:
            dec = self._decide(prefix, text)
            self.assertTrue(dec.fired, text)
            vetoes = [a for a in dec.adjustments if a["mechanism"]
                      == "prior_instruction_selection_veto"]
            self.assertEqual(len(vetoes), 1, text)
            self.assertEqual(vetoes[0]["instruction_selection"],
                             "cancelled", text)
            self.assertFalse(vetoes[0]["question_b"], text)
            # The raw A verdict is preserved, so the layer that
            # refused stays visible (question_b_a True, final
            # question_b False).
            self.assertTrue(vetoes[0]["question_b_a"], text)

    def test_question_recount_quote_fire(self):
        prefix = self._prefix("Gọi số 0902345678 giúp tôi")
        for text, reason in [
                ("Có nên làm như em dặn lúc nãy không?",
                 "instruction_question_blocked"),
                ("Hôm qua em đã làm như em dặn lúc nãy rồi",
                 "instruction_recount_blocked"),
                ('Anh ấy bảo "làm như em dặn lúc nãy"',
                 "instruction_quoted_only")]:
            dec = self._decide(prefix, text)
            self.assertTrue(dec.fired, text)
            vetoes = [a for a in dec.adjustments if a["mechanism"]
                      == "prior_instruction_selection_veto"]
            self.assertEqual(len(vetoes), 1, text)
            self.assertEqual(vetoes[0]["instruction_selection"],
                             "blocked", text)
            self.assertEqual(vetoes[0]["instruction_reason"],
                             reason, text)
            # Blocked is undetermined for this proposal, never
            # a disproof: question_b None, not False.
            self.assertIsNone(vetoes[0]["question_b"], text)

    def test_replacement_fires_but_same_number_rerequest_unfires(self):
        prefix = self._prefix("Gọi số 0902345678 giúp tôi")
        dec = self._decide(prefix,
                           "Đừng làm như lúc nãy nữa, "
                           "gọi số 0912345678 đi")
        self.assertTrue(dec.fired)
        # Round-10 fix S1 citation: B now also refuses here
        # -- the current text's verb governs Y, not X, so
        # B's selection is unknown/not-governing. First-
        # refusal-wins therefore records B's veto, not
        # layer C's; layer C's replacement detection is
        # still visible in the trail's instruction_selection
        # (the outcome -- fired -- and the detection are
        # unchanged, only the attribution moved to the
        # first refusal).
        vetoes = [a for a in dec.adjustments if a["mechanism"]
                  == "callback_selection_veto"]
        self.assertEqual(len(vetoes), 1)
        self.assertEqual(vetoes[0]["instruction_selection"],
                         "replaced")
        # Same-number fresh request: the current text directly
        # selects the value, so layer C must not veto it even
        # though it also cancels the old instruction.
        dec = self._decide(prefix,
                           "Đừng làm như lúc nãy nữa, "
                           "gọi số 0902345678 đi")
        self.assertFalse(dec.fired)

    def test_new_request_after_recount_unfires(self):
        prefix = self._prefix("Gọi số 0902345678 giúp tôi")
        dec = self._decide(
            prefix,
            "Em đã kể là hôm qua em dặn rồi. "
            "Bây giờ làm như em dặn lúc nãy giúp tôi.")
        self.assertFalse(dec.fired)
        adj = self._instr(dec)
        self.assertEqual(adj["instruction_selection"], "continue")

    def test_other_clause_distractor_does_not_veto(self):
        prefix = self._prefix("Gọi số 0902345678 giúp tôi")
        dec = self._decide(
            prefix,
            "Làm như em dặn lúc nãy giúp tôi. "
            "Thôi, chuyện kia để sau đi.")
        self.assertFalse(dec.fired)

    def test_named_other_clause_cancel_stays_conservative(self):
        # DOCUMENTED BOUNDARY, not a layer-C decision: a named
        # cancellation in another clause ("đừng gọi cho An
        # nữa") is vetoed by B's negated_other_object rule,
        # because the name could denote the same counterpart
        # (a phone-only instruction carries no identity). This
        # test pins that conservative behaviour; it must not
        # be "fixed" by letting layer C override B here.
        prefix = self._prefix("Gọi số 0902345678 giúp tôi")
        dec = self._decide(
            prefix,
            "Làm như em dặn lúc nãy giúp tôi, đừng gọi cho An nữa")
        self.assertTrue(dec.fired)
        vetoes = [a for a in dec.adjustments if a["mechanism"]
                  == "callback_selection_veto"]
        self.assertEqual(len(vetoes), 1)
        self.assertEqual(vetoes[0]["selection_reason"],
                         "negated_other_object")

    def test_bare_reference_abstain_preserved(self):
        # 0764-class: a bare reference with no verb and no
        # marker still un-fires (abstain), but the trail now
        # records instruction_selection unknown -- honestly an
        # abstain, not a proven continuation.
        prefix = self._prefix("Gọi số 0902345678 giúp tôi")
        dec = self._decide(prefix, "Như em dặn lúc nãy")
        self.assertFalse(dec.fired)
        adj = self._instr(dec)
        self.assertEqual(adj["instruction_selection"], "unknown")

    def test_history_revocation_and_revival(self):
        # Intervening number cancellation revokes the bound
        # instruction.
        prefix = self._prefix("Gọi số 0902345678 giúp tôi",
                              "Đừng gọi số 0902345678 nữa")
        dec = self._decide(prefix, "Làm như em dặn lúc nãy")
        self.assertTrue(dec.fired)
        vetoes = [a for a in dec.adjustments if a["mechanism"]
                  == "prior_instruction_revoked"]
        self.assertEqual(len(vetoes), 1)
        # Intervening instruction cancellation revokes it too.
        prefix = self._prefix("Gọi số 0902345678 giúp tôi",
                              "Thôi, khỏi làm như lúc nãy nữa")
        dec = self._decide(prefix, "Làm như em dặn lúc nãy")
        self.assertTrue(dec.fired)
        # Cancel-then-new-instruction revives it.
        prefix = self._prefix("Gọi số 0902345678 giúp tôi",
                              "Thôi, khỏi làm như lúc nãy nữa",
                              "Gọi số 0902345678 giúp tôi")
        dec = self._decide(prefix, "Làm như em dặn lúc nãy")
        self.assertFalse(dec.fired)

    def test_cancel_one_of_two_instructions(self):
        # Two instructions; the second is cancelled in a later
        # turn. "Làm như lúc nãy" refers to the latest live
        # instruction (the second), which is revoked, so the
        # second number's proposal fires...
        prefix = self._prefix("Gọi số 0902345678 giúp tôi",
                              "Gọi số 0912345678 giúp tôi",
                              "Đừng gọi số 0912345678 nữa")
        dec = self._decide(prefix, "Làm như em dặn lúc nãy",
                           number=self.NEW)
        self.assertTrue(dec.fired)
        # ...while the first number's proposal fires for a
        # different reason (A binds the latest instruction,
        # not the first), unchanged by layer C.
        dec = self._decide(prefix, "Làm như em dặn lúc nãy",
                           number=self.OLD)
        self.assertTrue(dec.fired)

    def test_bound_instruction_action_must_match(self):
        # A message instruction repeated as a call is not a
        # continuation of that instruction.
        prefix = self._prefix("Nhắn số 0902345678 giúp tôi")
        dec = self._decide(prefix, "Làm như em dặn lúc nãy")
        self.assertTrue(dec.fired)
        vetoes = [a for a in dec.adjustments if a["mechanism"]
                  == "prior_instruction_action_mismatch"]
        self.assertEqual(len(vetoes), 1)
        # Same action still un-fires.
        dec = self._decide(prefix, "Làm như em dặn lúc nãy",
                           tool="sms.send")
        self.assertFalse(dec.fired)
        # And a call instruction repeated as a call un-fires.
        prefix = self._prefix("Gọi số 0902345678 giúp tôi")
        dec = self._decide(prefix, "Làm như em dặn lúc nãy")
        self.assertFalse(dec.fired)

    def test_non_prior_bound_reference_untouched(self):
        # Generic callback via a log counterpart still un-fires
        # exactly as before (layer C agrees: positive verb in
        # the reference clause). No layer-C veto may appear.
        contact = {"id": "c_x", "name": "Vy",
                   "phone": "0902345678"}
        prefix = [call_entry(
            "phone.recent_calls", {},
            recent_calls_result([{
                "id": "call_x", "contact": contact,
                "direction": "incoming", "status": "missed"}]),
            0, origin="history")]
        proposal = {"name": "phone.call",
                    "arguments": {"contact_id": "c_x"}}
        dec = decide(proposal, prefix, [],
                     "Gọi lại người vừa gọi giúp tôi", KINDS,
                     proposal_position=1)
        self.assertTrue(dec.baseline_fired)
        self.assertFalse(dec.fired)
        vetoes = [a for a in dec.adjustments
                  if a["mechanism"].startswith("prior_instruction")]
        self.assertEqual(len(vetoes), 0)


class TestLayerCRound2(unittest.TestCase):
    """Layer C round 2 at the adapter level (S10-S14, M-a, M-b).

    Same fixture style as TestLayerCR4: history user turns
    only, baseline fires, module A binds via the prior
    -instruction reference, so outcomes are decided by layer
    B + layer C. Topic cases use a history sms.read_recent
    entry whose incoming message carries the amount.
    """

    OLD = "0902345678"
    NEW = "0911111111"

    def _prefix(self, *texts):
        return [user_turn(t, i) for i, t in enumerate(texts)]

    def _decide(self, prefix, text, number=None, tool="phone.call",
                args=None):
        proposal = {"name": tool,
                    "arguments": args or {"phone_number":
                                          number or self.OLD}}
        return decide(proposal, prefix, [], text, KINDS)

    def _veto(self, dec, mechanism):
        return [a for a in dec.adjustments
                if a.get("mechanism") == mechanism]

    def test_s10_addressee_change_fires_same_unfires(self):
        prefix = self._prefix("Gọi cho Vy số 0902345678 giúp tôi")
        for text in ["Gọi cho An như lúc nãy",
                     "Làm như em dặn lúc nãy cho An",
                     "Làm như lúc nãy nhưng gọi cho An"]:
            dec = self._decide(prefix, text)
            self.assertTrue(dec.fired, text)
            self.assertEqual(
                len(self._veto(
                    dec, "prior_instruction_addressee_mismatch")),
                1, text)
        dec = self._decide(prefix, "Gọi cho Vy như lúc nãy")
        self.assertFalse(dec.fired)
        prefix_f = self._prefix("Gọi cho mẹ số 0902345678 giúp tôi")
        dec = self._decide(prefix_f, "Gọi cho bố như lúc nãy")
        self.assertTrue(dec.fired)
        dec = self._decide(prefix_f, "Làm như em dặn lúc nãy cho mẹ")
        self.assertFalse(dec.fired)
        # One side missing a name: unknown, never a veto.
        prefix_bare = self._prefix("Gọi số 0902345678 giúp tôi")
        dec = self._decide(prefix_bare, "Gọi cho An như lúc nãy")
        self.assertFalse(dec.fired)

    def test_s11_other_action_instruction_fires(self):
        for turn in ["Lưu số 0902345678 giúp tôi",
                     "Tra cứu số 0902345678 giúp tôi",
                     "Xóa số 0902345678 giúp tôi"]:
            prefix = self._prefix(turn)
            for tool in ["phone.call", "sms.send"]:
                dec = self._decide(prefix, "Làm như em dặn lúc nãy",
                                   tool=tool)
                self.assertTrue(dec.fired, (turn, tool))
                self.assertEqual(len(self._veto(
                    dec, "prior_instruction_action_mismatch")),
                    1, (turn, tool))

    def test_s12_generic_intermediate_cancel_revokes(self):
        for mid in ["Đừng gọi nữa", "Khỏi gọi nữa", "Hủy đi"]:
            prefix = self._prefix("Gọi số 0902345678 giúp tôi", mid)
            dec = self._decide(prefix, "Như lúc nãy")
            self.assertTrue(dec.fired, mid)
            self.assertEqual(len(self._veto(
                dec, "prior_instruction_revoked")), 1, mid)
        # No intermediate cancel: the bare anaphor still un-fires
        # (0764-class, unchanged).
        dec = self._decide(self._prefix("Gọi số 0902345678 giúp tôi"),
                           "Như lúc nãy")
        self.assertFalse(dec.fired)
        # Current re-invocation supersedes the history cancel.
        prefix = self._prefix("Gọi số 0902345678 giúp tôi",
                              "Đừng gọi nữa")
        dec = self._decide(prefix, "Làm như lúc nãy đi")
        self.assertFalse(dec.fired)
        # A target-attached cancel of someone else does NOT
        # revoke this instruction.
        prefix = self._prefix("Gọi số 0902345678 giúp tôi",
                              "Đừng gọi cho An nữa")
        dec = self._decide(prefix, "Như lúc nãy")
        self.assertFalse(dec.fired)

    def test_ma_anaphoric_reissue_revives(self):
        # Explicit re-issue already revived in v1; an anaphoric
        # continuation after a cancellation revives too
        # (last-decisive-wins across history).
        prefix = self._prefix("Gọi số 0902345678 giúp tôi",
                              "Đừng làm như em dặn lúc nãy nữa",
                              "Làm như lúc nãy đi")
        dec = self._decide(prefix, "Làm như lúc nãy")
        self.assertFalse(dec.fired)

    def test_s13_correction_turn_becomes_valid_phone_turn(self):
        prefix = self._prefix("Gọi số 0902345678 giúp tôi",
                              "À không, gọi số 0911111111 đi")
        dec = self._decide(prefix, "Làm như em dặn lúc nãy",
                           number=self.NEW)
        self.assertFalse(dec.fired)
        dec = self._decide(prefix, "Làm như em dặn lúc nãy",
                           number=self.OLD)
        self.assertTrue(dec.fired)
        # "ý là" correction behaves the same way.
        prefix = self._prefix("Gọi số 0902345678 giúp tôi",
                              "Ý là, gọi số 0911111111 đi")
        dec = self._decide(prefix, "Làm như em dặn lúc nãy",
                           number=self.NEW)
        self.assertFalse(dec.fired)
        dec = self._decide(prefix, "Làm như em dặn lúc nãy",
                           number=self.OLD)
        self.assertTrue(dec.fired)

    def test_s14_topic_cancel_question_fire_direct_unfires(self):
        prefix = [call_entry(
            "sms.read_recent", {},
            {"ok": True, "messages": [
                {"id": "m_1", "contact_id": "c_x",
                 "phone_number": "0902345678",
                 "direction": "incoming",
                 "content": "Cho mình xin lại hai trăm nghìn nhé"}]},
            0, origin="history")]
        proposal_args = {"contact_id": "c_x", "amount": 200000}
        for text in ["Đừng làm như lúc nãy nữa, vụ hai trăm nghìn ấy",
                     "Đừng hoàn lại hai trăm nghìn như tin nhắn lúc nãy nữa",
                     "Có nên hoàn lại hai trăm nghìn không?"]:
            dec = self._decide(prefix, text, tool="ewallet.transfer",
                               args=proposal_args)
            self.assertTrue(dec.fired, text)
            self.assertEqual(len(self._veto(dec,
                                            "topic_selection_veto")),
                             1, text)
        dec = self._decide(prefix, "Hoàn lại hai trăm nghìn cho Vy đi",
                           tool="ewallet.transfer",
                           args=proposal_args)
        self.assertFalse(dec.fired)

    def test_mb_copula_number_does_not_hijack_binding(self):
        prefix = self._prefix("Gọi số 0902345678 giúp tôi",
                              "Số 0911111111 là số tổng đài")
        dec = self._decide(prefix, "Làm như em dặn lúc nãy")
        self.assertFalse(dec.fired)


class TestLayerCRound3(unittest.TestCase):
    """Layer C round 3 at the adapter level (F1/F2/F5/F6).

    Same fixture style as TestLayerCRound2: history user turns
    only, baseline fires, module A binds via the prior
    -instruction reference, so outcomes are decided by layer C
    (plus the revocation state machine).
    """

    OLD = "0902345678"

    def _prefix(self, *texts):
        return [user_turn(t, i) for i, t in enumerate(texts)]

    def _decide(self, prefix, text, number=None, tool="phone.call"):
        proposal = {"name": tool,
                    "arguments": {"phone_number":
                                  number or self.OLD}}
        return decide(proposal, prefix, [], text, KINDS)

    def _veto(self, dec, mechanism):
        return [a for a in dec.adjustments
                if a.get("mechanism") == mechanism]

    def test_f1_revocation_state_machine(self):
        # F1: specific-cancel wins over a later generic cancel
        # (no downgrade), in both orders.
        for history in [
                ["Gọi số 0902345678 giúp tôi",
                 "Đừng gọi số 0902345678 nữa", "Đừng gọi nữa"],
                ["Gọi số 0902345678 giúp tôi",
                 "Đừng gọi nữa", "Đừng gọi số 0902345678 nữa"]]:
            dec = self._decide(self._prefix(*history),
                               "Làm như lúc nãy đi")
            self.assertTrue(dec.fired, history)
            self.assertEqual(len(self._veto(
                dec, "prior_instruction_revoked")), 1, history)
        # Generic-only revocation is still superseded by a
        # current continuation (C2c).
        dec = self._decide(self._prefix(
            "Gọi số 0902345678 giúp tôi", "Đừng gọi nữa"),
            "Làm như lúc nãy đi")
        self.assertFalse(dec.fired)
        # A reference-carrying stop followed by a settled
        # history continuation revives (7f: history-internal
        # last-decisive-wins -- the settled continuation
        # re-decides, whatever the state was).
        dec = self._decide(self._prefix(
            "Gọi số 0902345678 giúp tôi",
            "Đừng làm như em dặn lúc nãy nữa",
            "Làm như lúc nãy đi"),
            "Làm như em dặn lúc nãy")
        self.assertFalse(dec.fired)

    def test_f2_addressee_last_token(self):
        # F2: bound full name vs current last token = same.
        prefix = self._prefix(
            "Gọi cho Nguyễn An số 0902345678 giúp tôi")
        dec = self._decide(prefix, "Làm như lúc nãy cho An đi")
        self.assertFalse(dec.fired)
        # ... and the reverse direction.
        prefix = self._prefix("Gọi cho An số 0902345678 giúp tôi")
        dec = self._decide(prefix,
                           "Làm như lúc nãy cho Nguyễn An đi")
        self.assertFalse(dec.fired)
        # A genuinely different name still mismatches.
        prefix = self._prefix(
            "Gọi cho Nguyễn An số 0902345678 giúp tôi")
        dec = self._decide(prefix, "Làm như lúc nãy cho Bình đi")
        self.assertTrue(dec.fired)
        self.assertEqual(len(self._veto(
            dec, "prior_instruction_addressee_mismatch")), 1)

    def test_f5_unknown_action_veto(self):
        # F5: an unclassified bound instruction never passes
        # the action match as if it were a call.
        for turn in ["Chuyển số 0902345678 cho Vy giúp tôi",
                     "Gửi tiền tới số 0902345678 giúp tôi",
                     "Báo số 0902345678 cho Vy giúp tôi"]:
            dec = self._decide(self._prefix(turn),
                               "Làm như lúc nãy đi")
            self.assertTrue(dec.fired, turn)
            self.assertEqual(len(self._veto(
                dec, "prior_instruction_action_mismatch")), 1,
                turn)
        # A generic-contact instruction ("liên hệ") is
        # compatible: it does not contradict a call.
        dec = self._decide(
            self._prefix("Liên hệ số 0902345678 giúp tôi"),
            "Làm như lúc nãy đi")
        self.assertFalse(dec.fired)

    def test_f6_wrapper_instruction_fires(self):
        # F6: scheduling / reminding a call is not a call now.
        for turn in ["Đặt lịch gọi số 0902345678 giúp tôi",
                     "Nhắc tôi gọi số 0902345678 giúp tôi"]:
            dec = self._decide(self._prefix(turn),
                               "Làm như lúc nãy đi")
            self.assertTrue(dec.fired, turn)
            self.assertEqual(len(self._veto(
                dec, "prior_instruction_action_mismatch")), 1,
                turn)


class TestRound4Batch3(unittest.TestCase):
    """Round-4 batch-3 findings at the adapter level (S1-S6, M1-M3).

    Fixture style mirrors TestLayerCRound3: history user turns
    only, phone proposal, baseline fires, module A binds, so
    outcomes are decided by B + layer C. Every case states the
    mechanism it pins; controls prove the fix does not
    over-fire.
    """

    OLD = "0902345678"
    NEW = "0911111111"

    def _prefix(self, *texts):
        return [user_turn(t, i) for i, t in enumerate(texts)]

    def _decide(self, prefix, text, number=None, tool="phone.call",
                roster=None):
        proposal = {"name": tool,
                    "arguments": {"phone_number":
                                  number or self.OLD}}
        return decide(proposal, prefix, roster or [], text, KINDS)

    def _veto(self, dec, mechanism):
        return [a for a in dec.adjustments
                if a.get("mechanism") == mechanism]

    # --- S1: named-cancel revoke -------------------------------
    def test_s1_named_cancel_revokes(self):
        dec = self._decide(self._prefix(
            "Gọi cho Vy số 0902345678 giúp tôi",
            "Đừng gọi cho Vy nữa"), "Làm như lúc nãy đi")
        self.assertTrue(dec.fired)
        self.assertTrue(self._veto(dec, "prior_instruction_revoked"))

    def test_s1_controls_do_not_revoke(self):
        # Other person / number-only instruction / other action:
        # none of these revokes the call instruction.
        cases = [
            (["Gọi cho Vy số 0902345678 giúp tôi",
              "Đừng gọi cho Bình nữa"], None),
            (["Gọi số 0902345678 giúp tôi",
              "Đừng gọi cho Vy nữa"], None),
            (["Gọi cho Vy số 0902345678 giúp tôi",
              "Đừng nhắn cho Vy nữa"], None),
        ]
        for prefix, _ in cases:
            dec = self._decide(self._prefix(*prefix),
                               "Làm như lúc nãy đi")
            self.assertFalse(dec.fired, prefix)

    def test_s1_roster_tie_in_known_names(self):
        # Condition (a), second arm, at the unit level: the
        # number is tied to Vy via the roster even though the
        # instruction named nobody, so Vy joins the known
        # names for the named-cancel check. At decide() level
        # this arm is NOT observable for a phone proposal: a
        # roster tie establishes the number, so the baseline
        # passes ("references established") before the adapter
        # ever runs -- existence vs selection split, out of
        # this round's scope. The arm is implemented so the
        # revocation engages if that baseline rule ever
        # changes, and it already matters for B's target names
        # on other bindings.
        from lifemate.lifemate_gates_adapter import _known_names_for_number
        names = _known_names_for_number(
            "0902345678", None,
            [{"id": "c_vy", "name": "Vy", "phone": "0902345678"}],
            [])
        self.assertIn("Vy", names)
        self.assertNotIn("Bình", names)

    # --- S2: history tail-change -------------------------------
    def test_s2_tail_change_forms_revoke(self):
        for turn in ["Đuôi đổi thành 1234",
                     "Đuôi đổi thành một hai ba bốn",
                     "Đuôi là năm sáu",
                     "Đuôi thành 1234",
                     "Đuôi là 1234",
                     "Đổi đuôi thành 1234",
                     "Đuôi là 1234 chứ không phải 5678"]:
            dec = self._decide(self._prefix(
                "Gọi số 0902345678 giúp tôi", turn),
                "Làm như lúc nãy đi")
            self.assertTrue(dec.fired, turn)

    def test_s2_same_tail_and_misattribution_keep_live(self):
        # Same tail: no change, no revoke.
        dec = self._decide(self._prefix(
            "Gọi số 0902345678 giúp tôi",
            "Đuôi đổi thành 5678"), "Làm như lúc nãy đi")
        self.assertFalse(dec.fired)
        # Misattribution guard: a background mention of another
        # number intervenes, so the tail change is about that
        # number, not the bound one.
        dec = self._decide(self._prefix(
            "Gọi số 0902345678 giúp tôi",
            "Số 0911111111 là số tổng đài",
            "Đuôi đổi thành 1234"), "Làm như lúc nãy đi")
        self.assertFalse(dec.fired)

    # --- S3: foreign action ------------------------------------
    def test_s3_foreign_action_fires(self):
        for text in ["Chuyển tiếp số 0902345678 cho Vy",
                     "Chuyển tiếp số 0902345678 đi",
                     "Forward số 0902345678 cho Vy"]:
            dec = self._decide(
                self._prefix("Gọi số 0902345678 giúp tôi"), text)
            self.assertTrue(dec.fired, text)

    # --- S4: number-as-content ---------------------------------
    def test_s4_content_fires_both_paths(self):
        # Direct-request basis (B gate) and prior-instruction
        # basis (layer-C defense): both must refuse.
        dec = self._decide(
            self._prefix("Gọi số 0902345678 giúp tôi"),
            "Gửi số 0902345678 cho Vy", tool="sms.send")
        self.assertTrue(dec.fired)
        dec = self._decide(
            self._prefix("Gọi số 0902345678 giúp tôi"),
            "Nhắn cho Vy số 0902345678", tool="sms.send")
        self.assertTrue(dec.fired)
        dec = self._decide(
            self._prefix("Nhắn số 0902345678 giúp tôi"),
            "Nhắn cho Vy số 0902345678", tool="sms.send")
        self.assertTrue(dec.fired)

    def test_s4_controls_stay_live(self):
        dec = self._decide(
            self._prefix("Gọi số 0902345678 giúp tôi"),
            "Nhắn cho Vy qua số 0902345678", tool="sms.send")
        self.assertFalse(dec.fired)
        dec = self._decide(
            self._prefix("Gọi số 0902345678 giúp tôi"),
            "Gọi cho Vy số 0902345678")
        self.assertFalse(dec.fired)
        dec = self._decide(
            self._prefix("Gọi số 0902345678 giúp tôi"),
            "Nhắn số 0902345678", tool="sms.send")
        self.assertFalse(dec.fired)

    def test_s4_sender_possessive_beats_roster_owner(self):
        # Round-6 delta: the current text asserts the number
        # belongs to the sender ("bang so X cua toi"),
        # contradicting the roster claim that X is Vy's.
        # Current wins (N4 philosophy): the owner exception
        # must not rescue the mention, so sms X fires.
        # The shared _decide passes no roster, so call decide
        # directly here.
        prefix = self._prefix("Nhắn số 0902345678 giúp tôi")
        roster = [{"name": "Vy", "phone": "0902345678"}]
        proposal = {"name": "sms.send",
                    "arguments": {"phone_number": "0902345678"}}
        dec = decide(proposal, prefix, roster,
                     "Nhắn cho Vy bằng số 0902345678 của tôi",
                     KINDS)
        self.assertTrue(dec.fired)
        # Controls: owner exception stands without a possessive;
        # carve-out stands without a roster; N4 "qua" stands.
        dec = decide(proposal, prefix, roster,
                     "Nhắn cho Vy bằng số 0902345678", KINDS)
        self.assertFalse(dec.fired)
        dec = decide(proposal, prefix, [],
                     "Nhắn cho Vy bằng số 0902345678 của tôi",
                     KINDS)
        self.assertTrue(dec.fired)
        dec = decide(proposal, prefix,
                     [{"name": "Bình", "phone": "0902345678"}],
                     "Nhắn cho Vy qua số 0902345678", KINDS)
        self.assertFalse(dec.fired)

    # --- S5: same-turn cancel ----------------------------------
    def test_s5_same_turn_cancel_after_reissue_fires(self):
        # The bound turn itself ends in a cancel: its own
        # last-decisive state revokes (bound-turn self-check).
        dec = self._decide(self._prefix(
            "Gọi số 0902345678 giúp tôi",
            "Gọi số 0902345678 đi, đừng gọi nữa"), "Như lúc nãy")
        self.assertTrue(dec.fired)

    def test_s5_cancel_first_still_revives(self):
        # Control 2a: cancel first, re-issue last in the same
        # turn -- last-decisive is the re-issue, so it lives.
        dec = self._decide(self._prefix(
            "Gọi số 0902345678 giúp tôi",
            "Đừng gọi nữa, gọi số 0902345678 đi"), "Như lúc nãy")
        self.assertFalse(dec.fired)

    def test_s5_no_comma_sequence_orders_by_position(self):
        # Position ordering, not comma splitting: a "rồi"
        # sequence without punctuation still orders re-issue
        # before cancel.
        dec = self._decide(self._prefix(
            "Gọi số 0902345678 giúp tôi",
            "Gọi số 0902345678 đi rồi đừng gọi nữa"),
            "Như lúc nãy")
        self.assertTrue(dec.fired)

    # --- S6: wrapper in current text ----------------------------
    def test_s6_wrapper_current_text_fires(self):
        for text in ["Đặt lịch gọi số 0902345678",
                     "Nhắc tôi đặt lịch gọi số 0902345678",
                     "Nhắc gọi số 0902345678 rồi đặt lịch họp",
                     "Đặt hẹn gọi số 0902345678"]:
            dec = self._decide(
                self._prefix("Gọi số 0902345678 giúp tôi"), text)
            self.assertTrue(dec.fired, text)

    def test_s6_sequenced_control_stays_live(self):
        dec = self._decide(
            self._prefix("Gọi số 0902345678 giúp tôi"),
            "Gọi số 0902345678 rồi đặt lịch họp")
        self.assertFalse(dec.fired)

    # --- M1: fragment inherits action ---------------------------
    def test_m1_fragment_inherits_call(self):
        dec = self._decide(self._prefix(
            "Gọi số 0902345678 giúp tôi",
            "Mà số 0911111111"), "Làm như lúc nãy đi",
            number=self.NEW)
        self.assertFalse(dec.fired)

    def test_m1_fragment_after_save_still_fires(self):
        # Control: inheriting "other" still mismatches a call.
        dec = self._decide(self._prefix(
            "Lưu số 0902345678 giúp tôi",
            "Mà số 0911111111"), "Làm như lúc nãy đi",
            number=self.NEW)
        self.assertTrue(dec.fired)

    # --- M2: ma-initial new-number binds ------------------------
    def test_m2_ma_new_number_binds(self):
        dec = self._decide(
            self._prefix("Gọi số 0902345678 giúp tôi"),
            "Mà số 0911111111 là số mới", number=self.NEW)
        self.assertFalse(dec.fired)

    def test_m2_role_copula_stays_background(self):
        # Control: the M-b copula rule is untouched -- a role
        # statement about a number is not a selection of it.
        dec = self._decide(
            self._prefix("Gọi số 0902345678 giúp tôi"),
            "Số 0911111111 là số tổng đài", number=self.NEW)
        self.assertTrue(dec.fired)

    # --- M3: name resolution via instruction --------------------
    def test_m3_name_only_request_binds(self):
        dec = self._decide(
            self._prefix("Gọi cho Vy số 0902345678 giúp tôi"),
            "Gọi cho Vy nhé")
        self.assertFalse(dec.fired)

    def test_m3_message_variant_binds(self):
        dec = self._decide(
            self._prefix("Nhắn cho Vy số 0902345678 giúp tôi"),
            "Nhắn cho Vy nhé", tool="sms.send")
        self.assertFalse(dec.fired)

    def test_m3_guards(self):
        # Competing number for the same name: ambiguous.
        dec = self._decide(self._prefix(
            "Gọi cho Vy số 0902345678 giúp tôi",
            "Gọi cho Vy số 0911111111 giúp tôi"),
            "Gọi cho Vy nhé")
        self.assertTrue(dec.fired)
        # Action mismatch: a message request does not resolve
        # a call instruction's name.
        dec = self._decide(
            self._prefix("Gọi cho Vy số 0902345678 giúp tôi"),
            "Nhắn cho Vy nhé")
        self.assertTrue(dec.fired)
        # Revoked mapping: a later named cancel refuses it.
        dec = self._decide(self._prefix(
            "Gọi cho Vy số 0902345678 giúp tôi",
            "Đừng gọi cho Vy nữa"),
            "Gọi cho Vy nhé")
        self.assertTrue(dec.fired)


class TestRound5Batch4Adapter(unittest.TestCase):
    """Round-5 batch-4 MINOR fixes via decide().

    Synthetic only. Prefixes are user turns; the proposal is a
    phone.call / sms.send for the bound number unless noted.
    """

    X = "0902345678"
    Y = "0911111111"

    def _ut(self, text, pos):
        return {"kind": "user_turn", "text": text, "position": pos}

    def _dec(self, prefix, proposal, text, roster=None):
        return decide(proposal, prefix, roster or [], text, KINDS)

    def _call(self, number):
        return {"name": "phone.call",
                "arguments": {"phone_number": number}}

    def _sms(self, number):
        return {"name": "sms.send",
                "arguments": {"phone_number": number}}

    def test_b4_1_name_only_reissue_revives(self):
        # F-B4-1: a re-request naming only the cancelled person
        # revives the instruction.
        prefix = [self._ut("Gọi cho Vy số %s giúp tôi" % self.X, 0),
                  self._ut("Đừng gọi cho Vy nữa", 1),
                  self._ut("Gọi lại cho Vy đi", 2)]
        dec = self._dec(prefix, self._call(self.X),
                        "Làm như lúc nãy đi")
        self.assertFalse(dec.fired)
        # Control: a number re-issue still revives.
        prefix = [self._ut("Gọi cho Vy số %s giúp tôi" % self.X, 0),
                  self._ut("Đừng gọi cho Vy nữa", 1),
                  self._ut("Gọi số %s đi" % self.X, 2)]
        dec = self._dec(prefix, self._call(self.X),
                        "Làm như lúc nãy đi")
        self.assertFalse(dec.fired)

    def test_b4_1_wrong_person_does_not_revive(self):
        # F-B4-1: the reviving name must be the cancelled
        # person, not any known name (Binh is roster-known for
        # the same number but was never cancelled).
        prefix = [self._ut("Gọi cho Vy số %s giúp tôi" % self.X, 0),
                  self._ut("Đừng gọi cho Vy nữa", 1),
                  self._ut("Gọi lại cho Bình đi", 2)]
        dec = self._dec(prefix, self._call(self.X),
                        "Làm như lúc nãy đi",
                        roster=[{"name": "Bình", "phone": self.X}])
        self.assertTrue(dec.fired)

    def test_b4_1_other_number_blocks_revival(self):
        # A re-request for another number is a new instruction,
        # not a revival of the cancelled one.
        prefix = [self._ut("Gọi cho Vy số %s giúp tôi" % self.X, 0),
                  self._ut("Đừng gọi cho Vy nữa", 1),
                  self._ut("Gọi cho Vy số %s đi" % self.Y, 2)]
        dec = self._dec(prefix, self._call(self.X),
                        "Làm như lúc nãy đi")
        self.assertTrue(dec.fired)

    def test_b4_1_ambiguous_name_does_not_revive(self):
        # M3 uniqueness: Vy tied to another number (even by a
        # background statement, not an instruction) never
        # revives the cancelled instruction.
        prefix = [self._ut("Gọi cho Vy số %s giúp tôi" % self.X, 0),
                  self._ut("Số của Vy là %s" % self.Y, 1),
                  self._ut("Đừng gọi cho Vy nữa", 2),
                  self._ut("Gọi lại cho Vy đi", 3)]
        dec = self._dec(prefix, self._call(self.X),
                        "Làm như lúc nãy đi")
        self.assertTrue(dec.fired)

    def test_b4_2_tail_restore_revives(self):
        # F-B4-2: two tail-changes back to the bound tail
        # restore the number.
        prefix = [self._ut("Gọi số %s giúp tôi" % self.X, 0),
                  self._ut("Đuôi đổi thành 1234", 1),
                  self._ut("Đuôi đổi thành 5678", 2)]
        dec = self._dec(prefix, self._call(self.X),
                        "Làm như lúc nãy đi")
        self.assertFalse(dec.fired)
        # Control: two different tail-changes stay fired.
        prefix = [self._ut("Gọi số %s giúp tôi" % self.X, 0),
                  self._ut("Đuôi đổi thành 1234", 1),
                  self._ut("Đuôi đổi thành 9999", 2)]
        dec = self._dec(prefix, self._call(self.X),
                        "Làm như lúc nãy đi")
        self.assertTrue(dec.fired)

    def test_b4_2_short_suffix_does_not_restore(self):
        # A shorter suffix (678 after a 4-digit change) does
        # not cover the changed tail, so it does not restore.
        prefix = [self._ut("Gọi số %s giúp tôi" % self.X, 0),
                  self._ut("Đuôi đổi thành 1234", 1),
                  self._ut("Đuôi đổi thành 678", 2)]
        dec = self._dec(prefix, self._call(self.X),
                        "Làm như lúc nãy đi")
        self.assertTrue(dec.fired)

    def test_b4_2_restore_does_not_revive_named_cancel(self):
        # A tail restatement never revives a named
        # cancellation: the restore only clears tail-changed
        # states, not other specific states.
        prefix = [self._ut("Gọi cho Vy số %s giúp tôi" % self.X, 0),
                  self._ut("Đừng gọi cho Vy nữa", 1),
                  self._ut("Đuôi đổi thành 5678", 2)]
        dec = self._dec(prefix, self._call(self.X),
                        "Làm như lúc nãy đi")
        self.assertTrue(dec.fired)

    def test_b4_8_roster_owner_unfires(self):
        # F-B4-8: a no-id roster entry carrying the number
        # names its owner, so the owner exception applies.
        prefix = [self._ut("Nhắn số %s giúp tôi" % self.X, 0)]
        dec = self._dec(prefix, self._sms(self.X),
                        "Nhắn cho Vy số %s" % self.X,
                        roster=[{"name": "Vy", "phone": self.X}])
        self.assertFalse(dec.fired)
        # Flip: the roster owner is Binh, so Vy is another
        # recipient and the content rule still fires.
        dec = self._dec(prefix, self._sms(self.X),
                        "Nhắn cho Vy số %s" % self.X,
                        roster=[{"name": "Bình", "phone": self.X}])
        self.assertTrue(dec.fired)
        dec = self._dec(prefix, self._sms(self.X),
                        "Nhắn cho Bình số %s" % self.X,
                        roster=[{"name": "Bình", "phone": self.X}])
        self.assertFalse(dec.fired)

    def test_b4_5_real_ewallet_args_never_reach_phone_gate(self):
        # F-B4-5 (boundary, NOT a fix): a real ewallet.transfer
        # carries "phone", never "phone_number", and the gate
        # reads only "phone_number" (plus id/name refs). A
        # phone-only real transfer therefore never reaches the
        # phone-evidence path: the gate is not applicable and
        # nothing un-fires or fires on the number.
        prefix = [self._ut("Gọi số %s giúp tôi" % self.X, 0)]
        real = {"name": "ewallet.transfer",
                "arguments": {"phone": self.X, "amount": 100000}}
        dec = self._dec(prefix, real, "Nhắn cho Vy số %s" % self.X)
        self.assertFalse(dec.applicable)
        self.assertFalse(dec.fired)
        self.assertEqual(dec.adjustments, [])
        # A real transfer request naming the number is likewise
        # not gated on the number at all (it passes, it does
        # not "un-fire" -- there is no fire to undo).
        dec = self._dec(prefix, real,
                        "Gửi tiền cho Vy số %s" % self.X)
        self.assertFalse(dec.applicable)
        self.assertFalse(dec.fired)


class TestRound6Batch5Adapter(unittest.TestCase):
    """Round-6 batch-5 SERIOUS/MINOR fixes via decide().

    Synthetic only. Prefixes are user turns; the proposal is a
    phone.call / sms.send for the bound number unless noted.
    """

    X = "0902345678"
    Y = "0911111111"

    def _ut(self, text, pos):
        return {"kind": "user_turn", "text": text, "position": pos}

    def _dec(self, prefix, proposal, text, roster=None):
        return decide(proposal, prefix, roster or [], text, KINDS)

    def _call(self, number):
        return {"name": "phone.call",
                "arguments": {"phone_number": number}}

    def _sms(self, number):
        return {"name": "sms.send",
                "arguments": {"phone_number": number}}

    def test_b5_s1_name_revive_blocked_by_tail_change(self):
        # S1: a name-only re-issue cannot revive across a tail
        # change -- after "duoi doi thanh 1234", Vy's number
        # is no longer X, so "Goi lai cho Vy" does not revive
        # the call to X.
        prefix = [self._ut("Gọi cho Vy số %s giúp tôi" % self.X, 0),
                  self._ut("Đừng gọi cho Vy nữa", 1),
                  self._ut("Đuôi đổi thành 1234", 2),
                  self._ut("Gọi lại cho Vy đi", 3)]
        dec = self._dec(prefix, self._call(self.X),
                        "Làm như lúc nãy đi")
        self.assertTrue(dec.fired)
        # Order variant: tail change, then cancel, then
        # name-only re-issue -- the tail is still changed at
        # re-issue time, so the name still does not map to X.
        prefix = [self._ut("Gọi cho Vy số %s giúp tôi" % self.X, 0),
                  self._ut("Đuôi đổi thành 1234", 1),
                  self._ut("Đừng gọi cho Vy nữa", 2),
                  self._ut("Gọi lại cho Vy đi", 3)]
        dec = self._dec(prefix, self._call(self.X),
                        "Làm như lúc nãy đi")
        self.assertTrue(dec.fired)
        # Control: plain name-only revival (no tail change)
        # still revives (round-5 F-B4-1).
        prefix = [self._ut("Gọi cho Vy số %s giúp tôi" % self.X, 0),
                  self._ut("Đừng gọi cho Vy nữa", 1),
                  self._ut("Gọi lại cho Vy đi", 2)]
        dec = self._dec(prefix, self._call(self.X),
                        "Làm như lúc nãy đi")
        self.assertFalse(dec.fired)

    def test_b5_s2_cancel_survives_tail_change_and_restore(self):
        # S2: cancel and tail are independent slots. A tail
        # change must not overwrite a named cancel, and a
        # later restore must not erase it either -- the user
        # never lifted the cancel.
        prefix = [self._ut("Gọi cho Vy số %s giúp tôi" % self.X, 0),
                  self._ut("Đừng gọi cho Vy nữa", 1),
                  self._ut("Đuôi đổi thành 1234", 2),
                  self._ut("Đuôi đổi thành 5678", 3)]
        dec = self._dec(prefix, self._call(self.X),
                        "Làm như lúc nãy đi")
        self.assertTrue(dec.fired)
        # Same, plus a name-only re-issue after the restore:
        # the mapping went through a competing number state
        # while cancelled (dirty), so the bare name cannot
        # revive the frozen instruction -- only an explicit
        # full-number re-issue can (next control).
        prefix = [self._ut("Gọi cho Vy số %s giúp tôi" % self.X, 0),
                  self._ut("Đừng gọi cho Vy nữa", 1),
                  self._ut("Đuôi đổi thành 1234", 2),
                  self._ut("Đuôi đổi thành 5678", 3),
                  self._ut("Gọi lại cho Vy đi", 4)]
        dec = self._dec(prefix, self._call(self.X),
                        "Làm như lúc nãy đi")
        self.assertTrue(dec.fired)
        prefix = [self._ut("Gọi cho Vy số %s giúp tôi" % self.X, 0),
                  self._ut("Đừng gọi cho Vy nữa", 1),
                  self._ut("Đuôi đổi thành 1234", 2),
                  self._ut("Đuôi đổi thành 5678", 3),
                  self._ut("Gọi số %s đi" % self.X, 4)]
        dec = self._dec(prefix, self._call(self.X),
                        "Làm như lúc nãy đi")
        self.assertFalse(dec.fired)

    def test_b5_n6_owner_new_number_revokes_old(self):
        # N6 (coordinator decision): stating that the bound
        # person's number changed revokes the old number for
        # that person, without binding the new one.
        prefix = [self._ut("Gọi cho Vy số %s giúp tôi" % self.X, 0),
                  self._ut("Số mới của Vy là %s" % self.Y, 1)]
        dec = self._dec(prefix, self._call(self.X),
                        "Làm như lúc nãy đi")
        self.assertTrue(dec.fired)
        dec = self._dec(prefix, self._call(self.Y),
                        "Làm như lúc nãy đi")
        self.assertTrue(dec.fired)
        # Person-scoped only: no person in the bound
        # instruction, or a statement about someone else,
        # never revokes.
        prefix = [self._ut("Gọi số %s giúp tôi" % self.X, 0),
                  self._ut("Số mới của Vy là %s" % self.Y, 1)]
        dec = self._dec(prefix, self._call(self.X),
                        "Làm như lúc nãy đi")
        self.assertFalse(dec.fired)
        prefix = [self._ut("Gọi cho Vy số %s giúp tôi" % self.X, 0),
                  self._ut("Số mới của Bình là %s" % self.Y, 1)]
        dec = self._dec(prefix, self._call(self.X),
                        "Làm như lúc nãy đi")
        self.assertFalse(dec.fired)
        # M2 still binds: "Ma so Y la so moi" is a correction,
        # not a background statement.
        prefix = [self._ut("Gọi số %s giúp tôi" % self.X, 0),
                  self._ut("Mà số %s là số mới" % self.Y, 1)]
        dec = self._dec(prefix, self._call(self.Y),
                        "Làm như lúc nãy đi")
        self.assertFalse(dec.fired)


class TestRound7Batch6Adapter(unittest.TestCase):
    """Round-7 batch-6 SERIOUS + MINOR fixes via decide().

    Synthetic only. Prefixes are user turns; the proposal is a
    phone.call / sms.send for the bound number unless noted.
    """

    X = "0902345678"
    Y = "0911111111"

    def _ut(self, text, pos):
        return {"kind": "user_turn", "text": text, "position": pos}

    def _dec(self, prefix, proposal, text, roster=None):
        return decide(proposal, prefix, roster or [], text, KINDS)

    def _call(self, number):
        return {"name": "phone.call",
                "arguments": {"phone_number": number}}

    def _sms(self, number):
        return {"name": "sms.send",
                "arguments": {"phone_number": number}}

    def test_b6_s3_delegated_turn_never_binds(self):
        # S3: a delegated history turn is another actor's
        # instruction, never the user's own. Binding must skip
        # it (falling back to the earlier own instruction, whose
        # cancel then stands), and a delegated-only history
        # binds nothing at all.
        prefix = [self._ut("Gọi cho Vy số %s giúp tôi" % self.X, 0),
                  self._ut("Đừng gọi cho Vy nữa", 1),
                  self._ut("Nhờ Vy gọi số %s giúp" % self.X, 2)]
        dec = self._dec(prefix, self._call(self.X),
                        "Làm như lúc nãy đi")
        self.assertTrue(dec.fired)
        # No cancel needed: a lone delegated turn binds nothing.
        prefix = [self._ut("Nhờ Vy gọi số %s giúp" % self.X, 0)]
        dec = self._dec(prefix, self._call(self.X),
                        "Làm như lúc nãy đi")
        self.assertTrue(dec.fired)
        prefix = [self._ut("Bảo Vy gọi số %s giúp tôi" % self.X, 0)]
        dec = self._dec(prefix, self._call(self.X),
                        "Làm như lúc nãy đi")
        self.assertTrue(dec.fired)
        # Controls: delegation then an OWN re-issue still
        # un-fires (binding falls through to the own turn),
        # and generic "nho em" is not delegation at all.
        prefix = [self._ut("Nhờ Vy gọi số %s giúp" % self.X, 0),
                  self._ut("Gọi số %s giúp tôi" % self.X, 1)]
        dec = self._dec(prefix, self._call(self.X),
                        "Làm như lúc nãy đi")
        self.assertFalse(dec.fired)
        prefix = [self._ut("Nhờ em gọi số %s giúp" % self.X, 0)]
        dec = self._dec(prefix, self._call(self.X),
                        "Làm như lúc nãy đi")
        self.assertFalse(dec.fired)

    def test_b6_s3_delegated_turn_never_revives(self):
        # S3, fold side: the binding fix alone is not enough
        # -- a delegated turn's explicit re-issue must not
        # revive the earlier cancel either (a "revive" clears
        # all fold slots). Without the fold suppression, this
        # case would un-fire via revival even after binding
        # correctly falls back to turn 0.
        prefix = [self._ut("Gọi cho Vy số %s giúp tôi" % self.X, 0),
                  self._ut("Đừng gọi cho Vy nữa", 1),
                  self._ut("Nhờ Vy gọi số %s giúp" % self.X, 2)]
        dec = self._dec(prefix, self._call(self.X),
                        "Làm như lúc nãy đi")
        self.assertTrue(dec.fired)
        # Control: the same shape with an OWN re-issue DOES
        # revive (explicit full-number re-issue clears a
        # specific cancel).
        prefix = [self._ut("Gọi cho Vy số %s giúp tôi" % self.X, 0),
                  self._ut("Đừng gọi cho Vy nữa", 1),
                  self._ut("Gọi số %s giúp tôi" % self.X, 2)]
        dec = self._dec(prefix, self._call(self.X),
                        "Làm như lúc nãy đi")
        self.assertFalse(dec.fired)

    def test_b6_m1_possessive_whole_text(self):
        # M1: a sender possessive anywhere in the text breaks
        # the roster-backed name event, in both orders.
        roster = [{"name": "Vy", "phone": self.X}]
        prefix = [self._ut("Nhắn số %s giúp tôi" % self.X, 0)]
        dec = self._dec(prefix, self._sms(self.X),
                        "Nhắn cho Vy đi, số %s của tôi là số mới"
                        % self.X, roster)
        self.assertTrue(dec.fired)
        dec = self._dec(prefix, self._sms(self.X),
                        "Số %s của tôi là số mới, nhắn cho Vy đi"
                        % self.X, roster)
        self.assertTrue(dec.fired)
        # Control: a possessive of ANOTHER number leaves the
        # name event for this proposal standing.
        roster_y = [{"name": "Vy", "phone": self.Y}]
        prefix_y = [self._ut("Nhắn số %s giúp tôi" % self.Y, 0)]
        dec = self._dec(prefix_y, self._sms(self.Y),
                        "Nhắn cho Vy số %s đi, số %s của tôi "
                        "là số mới" % (self.Y, self.X), roster_y)
        self.assertFalse(dec.fired)


class TestRound8Batch7Adapter(unittest.TestCase):
    """Round-8 batch-7 SERIOUS + MINOR fixes via decide().

    Synthetic only. Prefixes are user turns; the proposal is a
    phone.call / sms.send for the bound number unless noted.
    CONT = "Làm như lúc nãy đi".
    """

    X = "0902345678"
    Y = "0911111111"
    CONT = "Làm như lúc nãy đi"

    def _ut(self, text, pos):
        return {"kind": "user_turn", "text": text, "position": pos}

    def _dec(self, prefix, proposal, text, roster=None):
        return decide(proposal, prefix, roster or [], text, KINDS)

    def _call(self, number):
        return {"name": "phone.call",
                "arguments": {"phone_number": number}}

    def _sms(self, number):
        return {"name": "sms.send",
                "arguments": {"phone_number": number}}

    def test_b7_s1_forward_bare_turn_does_not_bind(self):
        # S1: the forward+bare turn must not become a call
        # (or sms) instruction for CONT -- the S4 ambiguity
        # must not merely be deferred one turn.
        for text in (
                "Chuyển tiếp số %s cho Bình, gọi đi" % self.X,
                "Tìm số %s rồi chuyển tiếp cho Bình, gọi đi"
                % self.X):
            prefix = [self._ut(text, 0)]
            dec = self._dec(prefix, self._call(self.X), self.CONT)
            self.assertTrue(dec.fired)
        # Cross-action: the same turn must not un-fire sms.
        prefix = [self._ut(
            "Chuyển tiếp số %s cho Bình, gọi đi" % self.X, 0)]
        dec = self._dec(prefix, self._sms(self.X), self.CONT)
        self.assertTrue(dec.fired)

    def test_b7_s1_layer_c_message_turn_not_call(self):
        # The bound number is a genuine message target in one
        # clause AND a forward object + bare verb in another:
        # binding action class "message" mismatch-vetoes a
        # call proposal but passes sms.
        prefix = [self._ut(
            "Nhắn cho Bình số %s đi, chuyển tiếp số %s "
            "cho Lan, gọi đi" % (self.Y, self.Y), 0)]
        dec = self._dec(prefix, self._call(self.Y), self.CONT)
        self.assertTrue(dec.fired)
        dec = self._dec(prefix, self._sms(self.Y), self.CONT)
        self.assertFalse(dec.fired)

    def test_b7_s1_controls(self):
        # Pure forward / pure message mismatch controls (F1)
        # still fire for call; an explicit-object bare verb
        # is never suppressed, so it still un-fires.
        prefix = [self._ut(
            "Chuyển tiếp số %s cho Bình" % self.X, 0)]
        self.assertTrue(self._dec(
            prefix, self._call(self.X), self.CONT).fired)
        prefix = [self._ut("Nhắn số %s giúp tôi" % self.X, 0)]
        self.assertTrue(self._dec(
            prefix, self._call(self.X), self.CONT).fired)
        prefix = [self._ut(
            "Chuyển tiếp số %s cho Bình, gọi số %s đi"
            % (self.X, self.X), 0)]
        self.assertFalse(self._dec(
            prefix, self._call(self.X), self.CONT).fired)

    def test_b7_m1_per_action_partition(self):
        # M1: a multi-number history turn binds per action:
        # the delegated call number never enters the message
        # partition, and vice versa.
        for text in (
                "Nhờ Vy gọi số %s giúp, nhắn cho Bình số %s đi"
                % (self.X, self.Y),
                "Nhắn cho Bình số %s đi, nhờ Vy gọi số %s giúp"
                % (self.Y, self.X),
                "Nhắn cho Bình số %s đi. Nhờ Vy gọi số %s giúp."
                % (self.Y, self.X)):
            prefix = [self._ut(text, 0)]
            dec = self._dec(prefix, self._sms(self.Y), self.CONT)
            self.assertFalse(dec.fired)
        # The delegated call number never binds for call.
        prefix = [self._ut(
            "Nhờ Vy gọi số %s giúp, nhắn cho Bình số %s đi"
            % (self.X, self.Y), 0)]
        self.assertTrue(self._dec(
            prefix, self._call(self.X), self.CONT).fired)
        # Same verb, two numbers: genuinely ambiguous, stays
        # unbound. Single-number turns are untouched.
        prefix = [self._ut(
            "Nhắn số %s và số %s" % (self.X, self.Y), 0)]
        self.assertTrue(self._dec(
            prefix, self._sms(self.Y), self.CONT).fired)
        prefix = [self._ut(
            "Gọi cho Vy số %s giúp tôi" % self.X, 0)]
        self.assertFalse(self._dec(
            prefix, self._call(self.X), self.CONT).fired)
        # Shared-object "và" degrades to multiple (safe):
        # call X must not bind Y's number nor X's through
        # the shared construction when another number shares
        # the call action.
        prefix = [self._ut(
            "Gọi và nhắn số %s đi, gọi số %s đi"
            % (self.X, self.Y), 0)]
        self.assertTrue(self._dec(
            prefix, self._call(self.X), self.CONT).fired)

    def test_b7_s2_forward_object_and_redirect(self):
        # S2: a forward-object mention never selects X, and
        # an explicit redirect supersedes an earlier mention.
        prefix = [self._ut("Gọi số %s giúp tôi" % self.X, 0)]
        dec = self._dec(prefix, self._call(self.X),
                        "Chuyển tiếp số %s cho Bình. "
                        "Tôi đổi sang số 12, gọi đi" % self.X)
        self.assertTrue(dec.fired)
        # C3/C4 redirect controls stand.
        dec = self._dec(prefix, self._call(self.X),
                        "Tôi đổi sang số %s rồi gọi đi" % self.Y)
        self.assertTrue(dec.fired)
        dec = self._dec(prefix, self._call(self.X),
                        "Tôi đổi sang số %s rồi gọi số %s đi"
                        % (self.Y, self.Y))
        self.assertTrue(dec.fired)
        dec = self._dec(prefix, self._call(self.Y),
                        "Tôi đổi sang số %s rồi gọi số %s đi"
                        % (self.Y, self.Y))
        self.assertFalse(dec.fired)
        # Mentioned then redirected: the redirect wins.
        dec = self._dec(prefix, self._call(self.X),
                        "Gọi số %s đi, tôi đổi sang số %s, "
                        "gọi đi" % (self.X, self.Y))
        self.assertTrue(dec.fired)
        # Re-selection after a redirect wins back.
        dec = self._dec(prefix, self._call(self.X),
                        "Tôi đổi sang số %s, rồi gọi số %s đi"
                        % (self.Y, self.X))
        self.assertFalse(dec.fired)
        # Full-number redirect after a forward also fires.
        dec = self._dec(prefix, self._call(self.X),
                        "Chuyển tiếp số %s cho Bình. "
                        "Tôi đổi sang số %s, gọi đi"
                        % (self.X, self.Y))
        self.assertTrue(dec.fired)

    def test_b7_m2_bare_fragment(self):
        # M2: a bare number fragment is content-less for the
        # backward scan, so suppression applies and the bare
        # call does not un-fire X.
        prefix = [self._ut("Gọi số %s giúp tôi" % self.X, 0)]
        dec = self._dec(prefix, self._call(self.X),
                        "Chuyển tiếp số %s cho Bình. "
                        "Số 12, gọi đi" % self.X)
        self.assertTrue(dec.fired)
        dec = self._dec(prefix, self._call(self.X),
                        "Chuyển tiếp số %s cho Bình. "
                        "0912, gọi đi" % self.X)
        self.assertTrue(dec.fired)
        # Assertion variant: fired too, but via demotion +
        # no selection signal (the bare call after
        # forwarding X away and asserting 12 is new never
        # clearly selects X) -- NOT via suppression, since
        # the assertion clause stays content (pinned at
        # analyze level in the negation tests).
        dec = self._dec(prefix, self._call(self.X),
                        "Chuyển tiếp số %s cho Bình. "
                        "Số 12 là số mới, gọi đi" % self.X)
        self.assertTrue(dec.fired)

    def test_b7_m3_cross_clause_possessive(self):
        # M3: a sender possessive in another clause breaks
        # the content-layer owner exception (whole-text).
        prefix = [self._ut("Nhắn số %s giúp tôi" % self.X, 0)]
        roster = [{"name": "Vy", "phone": self.X}]
        text = ("Nhắn cho Vy số %s đi, số %s của tôi là số mới"
                % (self.X, self.X))
        self.assertTrue(self._dec(
            prefix, self._sms(self.X), text, roster).fired)
        # No-roster control fires via the content veto.
        self.assertTrue(self._dec(
            prefix, self._sms(self.X), text, []).fired)
        # A possessive of ANOTHER number leaves the owner
        # exception standing for this number.
        roster_y = [{"name": "Vy", "phone": self.Y}]
        text = ("Nhắn cho Vy số %s đi, số %s của tôi là số mới"
                % (self.Y, self.X))
        self.assertFalse(self._dec(
            prefix, self._sms(self.Y), text, roster_y).fired)
        # Owner exception without any possessive still stands.
        self.assertFalse(self._dec(
            prefix, self._sms(self.X),
            "Nhắn cho Vy số %s đi" % self.X, roster).fired)



class TestRound9Batch9Adapter(unittest.TestCase):
    """Round-9 batch-9 fix S1: a bare mention is not selection
    evidence. Synthetic only. Prefixes are user turns; CONT =
    "Làm như lúc nãy đi". Batch 9 ran on v8 (second
    clean-batch attempt on the unchanged freeze)."""

    X = "0902345678"
    Y = "0911111111"
    CONT = "Làm như lúc nãy đi"

    def _ut(self, text, pos):
        return {"kind": "user_turn", "text": text, "position": pos}

    def _dec(self, prefix, proposal, text, roster=None):
        return decide(proposal, prefix, roster or [], text, KINDS)

    def _call(self, number):
        return {"name": "phone.call",
                "arguments": {"phone_number": number}}

    def _sms(self, number):
        return {"name": "sms.send",
                "arguments": {"phone_number": number}}

    def test_b9_s1_bare_mention_fires_both_actions(self):
        # S1: a bare number mention (filler / question /
        # evaluation) with NO history at all must not
        # authorize a call or an sms.
        for text in ("À, số %s" % self.X,
                     "Số %s phải không?" % self.X,
                     "Số %s đẹp quá" % self.X):
            self.assertTrue(
                self._dec([], self._call(self.X), text).fired)
            self.assertTrue(
                self._dec([], self._sms(self.X), text).fired)

    def test_b9_s1_transfer_to_agent_fires(self):
        # S1 path (b): handing a number to the agent is not
        # a request to call it. The generic exemption from
        # demotion stands (the mention is not forwarded
        # away), but a non-selecting mention must not
        # authorize -- demotion role and selection evidence
        # are separate layers.
        for text in ("Chuyển số %s cho em đi" % self.X,
                     "Số %s, chuyển cho em đi" % self.X):
            self.assertTrue(
                self._dec([], self._call(self.X), text).fired)
            self.assertTrue(
                self._dec([], self._sms(self.X), text).fired)

    def test_b9_s1_joint_veto_needs_no_history(self):
        # The joint veto also fires a bare mention that
        # follows an unrelated turn or a prior instruction
        # for the same number: a bare restatement is not a
        # continuation (ambiguous -> fire).
        prefix = [self._ut(
            "Nhắn cho Bình số %s đi" % self.Y, 0)]
        self.assertTrue(self._dec(
            prefix, self._call(self.X),
            "Số %s đẹp quá" % self.X).fired)
        prefix = [self._ut("Gọi số %s giúp tôi" % self.X, 0)]
        self.assertTrue(self._dec(
            prefix, self._call(self.X),
            "Số %s đẹp quá" % self.X).fired)

    def test_b9_s1_genuine_continuation_still_unfires(self):
        # Guard: the joint veto must NOT break genuine
        # continuations. CONT alone (0764 shape) and CONT
        # with the number restated both un-fire: layer C
        # confirms "continue" in the first case, and an
        # explicit continuation phrase counts in the
        # layer-C-not-applicable case in the second.
        prefix = [self._ut("Gọi số %s giúp tôi" % self.X, 0)]
        self.assertFalse(self._dec(
            prefix, self._call(self.X), self.CONT).fired)
        self.assertFalse(self._dec(
            prefix, self._call(self.X),
            "Làm như lúc nãy đi, số %s" % self.X).fired)
        # An explicit callback verb still selects.
        self.assertFalse(self._dec(
            [], self._call(self.X),
            "Gọi số %s đi" % self.X).fired)

    def test_b9_narrowing_bare_anaphor_still_unfires(self):
        # Narrowing gate (a): the veto fires only when
        # the current text DIRECTLY mentions the value.
        # A bare anaphor ("Như lúc nãy", "Như em dặn lúc
        # nãy") mentions no number -- it refers to the
        # prior instruction itself, so the v1 pinned
        # abstain-preserved un-fire stands. These cases
        # are also covered by the old tests
        # (test_bare_reference_abstain_preserved,
        # test_s12_generic_intermediate_cancel_revokes,
        # test_s5_cancel_first_still_revives); this test
        # pins the gate that keeps the veto off them.
        prefix = [self._ut("Gọi số %s giúp tôi" % self.X, 0)]
        self.assertFalse(self._dec(
            prefix, self._call(self.X),
            "Như lúc nãy").fired)
        self.assertFalse(self._dec(
            prefix, self._call(self.X),
            "Như em dặn lúc nãy").fired)

    def test_b9_narrowing_ma_new_number_still_unfires(self):
        # Narrowing gate (b): an M2 correction frame
        # ("Mà số Y là số mới") explicitly selects the
        # new number, so it is selection evidence, not
        # a bare mention, and the veto must not fire.
        # Also covered by the old test
        # test_m2_ma_new_number_binds; this test pins
        # the ma_new_number_selection marker gate.
        prefix = [self._ut("Gọi số %s giúp tôi" % self.X, 0)]
        self.assertFalse(self._dec(
            prefix, self._call(self.Y),
            "Mà số %s là số mới" % self.Y).fired)
        # The bare "là số mới" shape (no "mà") is the
        # same M2 frame in the parser and selects too.
        self.assertFalse(self._dec(
            prefix, self._call(self.Y),
            "Số %s là số mới" % self.Y).fired)

    def test_b9_m1_switch_family_backstop(self):
        # M1: the redirect backstop covers the whole
        # switch family ("đổi sang", "đổi thành",
        # "đổi lại", "chuyển sang") with the same
        # constraints: a different number after the last
        # target mention, then a bare call. An explicit
        # redirect to the new number still un-fires
        # via direct mention (no backstop needed).
        prefix = [self._ut("Gọi số %s giúp tôi" % self.X, 0)]
        for verb in ("đổi sang", "đổi thành", "đổi lại",
                     "chuyển sang"):
            self.assertTrue(self._dec(
                prefix, self._call(self.X),
                "Gọi số %s đi. Tôi %s số 12, gọi đi"
                % (self.X, verb)).fired)
        self.assertFalse(self._dec(
            prefix, self._call(self.Y),
            "Tôi đổi thành số %s rồi gọi số %s đi"
            % (self.Y, self.Y)).fired)
        self.assertTrue(self._dec(
            prefix, self._call(self.X),
            "Tôi đổi thành số %s rồi gọi số %s đi"
            % (self.Y, self.Y)).fired)

    def test_b9_narrowing_owner_recipient_still_unfires(self):
        # Narrowing gate (c), N1 pin: when the current
        # text addresses the number to its roster owner
        # ("Gửi số X cho Vy", Vy owns X), the owner-tie
        # beats forward suppression, so the abstention
        # stands. Distinct from S1 transfer-to-agent
        # ("cho em"): a generic addressee is not the
        # owner, and a bare mention with no roster owner
        # still fires. Batch-5 7b shape.
        prefix = [self._ut("Nhắn số %s giúp tôi" % self.X, 0)]
        roster = [{"name": "Vy", "phone": self.X}]
        self.assertFalse(self._dec(
            prefix, self._sms(self.X),
            "Gửi số %s cho Vy" % self.X,
            roster=roster).fired)
        # Controls: same text without the roster owner
        # tie fires (transfer shape, no owner), and a
        # transfer to a generic addressee fires even
        # with the roster present.
        self.assertTrue(self._dec(
            prefix, self._sms(self.X),
            "Gửi số %s cho Vy" % self.X).fired)
        self.assertTrue(self._dec(
            prefix, self._sms(self.X),
            "Gửi số %s cho em" % self.X,
            roster=roster).fired)


class TestRound10Batch10Adapter(unittest.TestCase):
    """Round-10 batch-10 fix S1 (verb leak) + M1 (gửi) at
    decide level. Synthetic only. Prefixes are user turns;
    CONT = "Làm như lúc nãy đi". Batch 10 ran on v9."""

    X = "0902345678"
    Y = "0911111111"
    CONT = "Làm như lúc nãy đi"

    def _ut(self, text, pos):
        return {"kind": "user_turn", "text": text, "position": pos}

    def _dec(self, prefix, proposal, text, roster=None):
        return decide(proposal, prefix, roster or [], text, KINDS)

    def _call(self, number):
        return {"name": "phone.call",
                "arguments": {"phone_number": number}}

    def _sms(self, number):
        return {"name": "sms.send",
                "arguments": {"phone_number": number}}

    def test_b10_s1_verb_leak_fires(self):
        # 1c + F1a/F1c/F1d/F5a/F5b, empty prefix: a verb
        # governing X plus a bare mention of Y must not
        # authorize a call/sms to Y.
        cases = [
            (self._call(self.Y),
             "Gọi số %s đi, số %s" % (self.X, self.Y)),
            (self._sms(self.Y),
             "Nhắn số %s đi, số %s" % (self.X, self.Y)),
            (self._call(self.Y),
             "Số %s, gọi số %s đi" % (self.Y, self.X)),
            (self._call(self.Y),
             "Gọi số %s đi, số %s là số mới"
             % (self.X, self.Y)),
            (self._call(self.Y),
             "Số %s. Gọi số %s đi" % (self.Y, self.X)),
            (self._call(self.Y),
             "Gọi số %s đi. Số %s" % (self.X, self.Y)),
        ]
        for proposal, text in cases:
            self.assertTrue(self._dec([], proposal, text).fired,
                            text)
        # Controls: the verb-selected number still un-fires,
        # and cross-action still fires (F1b).
        self.assertFalse(self._dec(
            [], self._call(self.X),
            "Gọi số %s đi, số %s" % (self.X, self.Y)).fired)
        self.assertFalse(self._dec(
            [], self._call(self.X),
            "Số %s. Gọi số %s đi" % (self.Y, self.X)).fired)
        self.assertTrue(self._dec(
            [], self._call(self.Y),
            "Nhắn số %s đi, số %s" % (self.X, self.Y)).fired)

    def test_b10_s1_same_clause_and_bare_verb(self):
        # Same-clause juxtaposition / "rồi": fired. "và"
        # chain: un-fire. Bare verb + 2 numbers: fired.
        # Bare verb + 1 number: un-fire.
        self.assertTrue(self._dec(
            [], self._call(self.Y),
            "Gọi số %s số %s đi" % (self.X, self.Y)).fired)
        self.assertTrue(self._dec(
            [], self._call(self.Y),
            "Gọi số %s rồi số %s" % (self.X, self.Y)).fired)
        self.assertFalse(self._dec(
            [], self._call(self.Y),
            "Gọi số %s và số %s đi" % (self.X, self.Y)).fired)
        self.assertTrue(self._dec(
            [], self._call(self.Y),
            "Gọi đi, số %s, số %s" % (self.X, self.Y)).fired)
        self.assertFalse(self._dec(
            [], self._call(self.Y),
            "Số %s, gọi đi" % self.Y).fired)

    def test_b10_m1_gui_double_object(self):
        # 2a: double-object + roster owner un-fires for sms.
        # F2a (bare gửi, no recipient): fired. S4 control
        # (named non-owner): fired. Call direction: fired.
        roster = [{"name": "Vy", "phone": self.X}]
        self.assertFalse(self._dec(
            [], self._sms(self.X), "Gửi Vy số %s" % self.X,
            roster=roster).fired)
        self.assertTrue(self._dec(
            [], self._sms(self.X),
            "Gửi số %s đi" % self.X).fired)
        self.assertTrue(self._dec(
            [], self._sms(self.X),
            "Gửi số %s cho Bình" % self.X).fired)
        self.assertTrue(self._dec(
            [], self._call(self.X), "Gửi Vy số %s" % self.X,
            roster=roster).fired)
        # 8b-generic is B's own expectation error, not a
        # finding: generic "cho em" deliberately does not
        # trigger the S4 content rule, and the benefactive
        # reading ("nhắn cho em" = message on my behalf,
        # X the destination) makes un-fire correct.
        self.assertFalse(self._dec(
            [], self._sms(self.X),
            "Nhắn cho em số %s đi" % self.X).fired)

    def test_b10_m1_money_binding_fires(self):
        # A money-transfer history turn must not bind as a
        # message instruction, even with CONT.
        prefix = [self._ut("Gửi tiền tới số %s" % self.X, 0)]
        self.assertTrue(self._dec(
            prefix, self._sms(self.X), self.CONT).fired)

    def test_b10_f1d_and_m2_original(self):
        # F1d: verb + assertion frame about Y, no prior
        # instruction, fires for Y. M2 original (prior
        # instruction + correction frame) still un-fires.
        self.assertTrue(self._dec(
            [], self._call(self.Y),
            "Gọi số %s đi, số %s là số mới"
            % (self.X, self.Y)).fired)
        prefix = [self._ut("Gọi số %s giúp tôi" % self.X, 0)]
        self.assertFalse(self._dec(
            prefix, self._call(self.Y),
            "Mà số %s là số mới" % self.Y).fired)


class TestR5EligibilityReport(unittest.TestCase):
    """Coordinator integration (R5): build_ledger emits counterpart
    field_value records; decide(eligibility=True) reports eligibility
    WITHOUT changing fired/applicable/adjustments."""

    KINDS5 = {
        "contacts.search": "read", "contacts.update": "write",
        "phone.call": "write", "reminders.create": "write",
        "reminders.delete": "write",
    }
    ROSTER = [{"id": "c_1", "name": "Bình", "phone": "0911111111"}]

    def test_fired_identical_and_unknown_for_unsupported(self):
        d0 = decide({"name": "phone.call",
                     "arguments": {"phone_number": "0911111111"}},
                    [], self.ROSTER, "Gọi cho Bình đi",
                    self.KINDS5, proposal_position=0)
        d1 = decide({"name": "phone.call",
                     "arguments": {"phone_number": "0911111111"}},
                    [], self.ROSTER, "Gọi cho Bình đi",
                    self.KINDS5, proposal_position=0, eligibility=True)
        self.assertEqual(d0.fired, d1.fired)
        self.assertEqual(d0.applicable, d1.applicable)
        self.assertEqual(d0.adjustments, d1.adjustments)
        self.assertEqual(d1.notes["eligibility"]["status"], "unknown")
        self.assertTrue(d1.notes["eligibility"]["reason"].startswith(
            "consumer_not_supported"))

    def test_field_value_emission_and_eligible(self):
        prefix = [call_entry(
            "contacts.search", {},
            {"ok": True, "contacts": [{"id": "c_1", "name": "Bình",
                                       "phone": "0911111111"}]}, 0)]
        ledger, _ = build_ledger(prefix, self.ROSTER, self.KINDS5)
        status, observed, _ = ledger.query_field_value(
            "contacts.contacts", "c_1", "phone")
        self.assertEqual((status, observed), ("active", "0911111111"))
        self.assertEqual(
            check_eligibility(ledger, "contacts.update", "c_1",
                              position=5),
            ("eligible", "entity_exists"))

    def test_ineligible_after_delete_and_unknown_missing(self):
        prefix = [
            call_entry("reminders.create", {},
                       {"ok": True,
                        "item": {"id": "r_1", "title": "x"}}, 0),
            call_entry("reminders.delete", {"reminder_id": "r_1"},
                       {"ok": True}, 1)]
        ledger, _ = build_ledger(prefix, [], self.KINDS5)
        self.assertEqual(
            check_eligibility(ledger, "reminders.delete", "r_1",
                              position=5),
            ("ineligible", "entity_deleted"))
        status, reason = check_eligibility(
            ledger, "contacts.update", "c_missing", position=5)
        self.assertEqual(status, "unknown")
        self.assertTrue(reason)


if __name__ == "__main__":
    unittest.main()
