"""Unit tests for lifemate_gates (Round 10).

Synthetic rosters/evidence only: no data files, no simulator, no network.
Runs with plain python3 and with /tmp/rfvenv/bin/python.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lifemate"))
from lifemate_gates import (  # noqa: E402
    gate_contact_ambiguity, gate_read_before_write, gate_confirmation,
    gate_confirmation_scoped, AskBudget)

ROSTER_DUP = [{"id": "c_05", "name": "Minh"},
              {"id": "c_08", "name": "Minh"},
              {"id": "c_01", "name": "Lan"}]
ROSTER_CLEAN = [{"id": "c_05", "name": "Minh"},
                {"id": "c_01", "name": "Lan"}]


class TestGate1(unittest.TestCase):
    def test_fires_on_dup_id(self):
        r = gate_contact_ambiguity(
            {"name": "sms.send", "arguments": {"contact_id": "c_05"}},
            ROSTER_DUP)
        self.assertTrue(r.fired and r.applicable)

    def test_fires_on_dup_name(self):
        r = gate_contact_ambiguity(
            {"name": "sms.send", "arguments": {"contact_name": "Minh"}},
            ROSTER_DUP)
        self.assertTrue(r.fired)

    def test_passes_when_unique(self):
        r = gate_contact_ambiguity(
            {"name": "sms.send", "arguments": {"contact_id": "c_05"}},
            ROSTER_CLEAN)
        self.assertFalse(r.fired)
        self.assertTrue(r.applicable)

    def test_passes_when_id_not_in_dup_group(self):
        r = gate_contact_ambiguity(
            {"name": "sms.send", "arguments": {"contact_id": "c_01"}},
            ROSTER_DUP)
        self.assertFalse(r.fired)

    def test_not_applicable_without_roster_or_reference(self):
        r = gate_contact_ambiguity(
            {"name": "sms.send", "arguments": {"contact_id": "c_05"}}, [])
        self.assertFalse(r.applicable)
        r = gate_contact_ambiguity(
            {"name": "reminders.create", "arguments": {"time": "10:00"}},
            ROSTER_DUP)
        self.assertFalse(r.applicable)
        r = gate_contact_ambiguity(
            {"name": "contacts.search", "arguments": {"query": "Minh"}},
            ROSTER_DUP)
        self.assertFalse(r.applicable)

    def test_same_id_twice_is_not_a_duplicate(self):
        roster = [{"id": "c_05", "name": "Minh"},
                  {"id": "c_05", "name": "Minh"}]
        r = gate_contact_ambiguity(
            {"name": "sms.send", "arguments": {"contact_id": "c_05"}},
            roster)
        self.assertFalse(r.fired)


class TestGate2(unittest.TestCase):
    def test_contact_needs_search(self):
        call = {"name": "sms.send", "arguments": {"contact_id": "c_05"}}
        r = gate_read_before_write(call, [], [], ROSTER_CLEAN)
        self.assertFalse(r.fired)  # roster establishes the contact
        r = gate_read_before_write(call, [], [], [])
        self.assertTrue(r.fired)

    def test_entity_id_needs_observation(self):
        call = {"name": "alarm.delete",
                "arguments": {"alarm_id": "alm_01"}}
        r = gate_read_before_write(call, [], ["alm_01"], [])
        self.assertFalse(r.fired)
        r = gate_read_before_write(call, [], [], [])
        self.assertTrue(r.fired)
        # A prior call using the same id also establishes it.
        r = gate_read_before_write(
            call, [("alarm.list", {})], [], [])
        self.assertTrue(r.fired)  # list with no args does not carry the id
        r = gate_read_before_write(
            call, [("alarm.snooze", {"alarm_id": "alm_01"})], [], [])
        self.assertFalse(r.fired)

    def test_fully_specified_create_is_not_applicable(self):
        r = gate_read_before_write(
            {"name": "reminders.create",
             "arguments": {"time": "2026-11-19T08:00:00+07:00"}},
            [], [], [])
        self.assertFalse(r.applicable)

    def test_bare_mutate_verb_needs_app_read(self):
        call = {"name": "calendar.delete_event", "arguments": {}}
        r = gate_read_before_write(call, [], [], [])
        self.assertTrue(r.fired)
        r = gate_read_before_write(
            call, [("calendar.list_events", {})], [], [])
        self.assertFalse(r.fired)


class TestGate3(unittest.TestCase):
    def test_literal_fires_without_marker(self):
        call = {"name": "banking.transfer",
                "arguments": {"amount": 500000}}
        r = gate_confirmation(call, ["chuyển 500 nghìn cho Minh"])
        self.assertTrue(r.fired)
        r = gate_confirmation(call, ["đồng ý chuyển đi"])
        self.assertFalse(r.fired)
        r = gate_confirmation(call, ["ok, chuyển đi"])
        self.assertFalse(r.fired)

    def test_literal_not_applicable_to_non_transfer(self):
        r = gate_confirmation({"name": "sms.send", "arguments": {}},
                              ["chuyển 500 nghìn"])
        self.assertFalse(r.applicable)

    def test_scoped_passes_when_fully_instructed(self):
        call = {"name": "ewallet.transfer",
                "arguments": {"amount": 500000}}
        r = gate_confirmation_scoped(call, [], False, True)
        self.assertFalse(r.applicable)
        self.assertFalse(r.fired)

    def test_scoped_requires_confirmation_after_ask(self):
        call = {"name": "ewallet.transfer",
                "arguments": {"amount": 500000}}
        r = gate_confirmation_scoped(call, ["ừ, chuyển đi"], True, False)
        self.assertFalse(r.fired)
        r = gate_confirmation_scoped(call, ["để tôi nghĩ đã"], True, False)
        self.assertTrue(r.fired)


class TestAskBudget(unittest.TestCase):
    def test_cap_two(self):
        b = AskBudget(max_asks=2)
        self.assertTrue(b.record_ask("amount"))
        self.assertTrue(b.record_ask("time"))
        self.assertFalse(b.allow_ask("contact_id"))
        self.assertFalse(b.record_ask("contact_id"))
        self.assertEqual(b.remaining, 0)

    def test_same_slot_twice_is_a_loop(self):
        b = AskBudget(max_asks=2)
        self.assertTrue(b.record_ask("amount"))
        self.assertFalse(b.allow_ask("amount"))
        self.assertFalse(b.record_ask("amount"))
        # A different slot is still allowed within budget.
        self.assertTrue(b.record_ask("time"))

    def test_ask_other_blocked_when_exhausted(self):
        b = AskBudget(max_asks=2)
        b.record_ask("amount")
        b.record_ask("time")
        self.assertFalse(b.allow_ask("other"))

    def test_reset(self):
        b = AskBudget(max_asks=1)
        b.record_ask("amount")
        self.assertFalse(b.allow_ask("time"))
        b.reset()
        self.assertTrue(b.allow_ask("time"))


if __name__ == "__main__":
    unittest.main()
