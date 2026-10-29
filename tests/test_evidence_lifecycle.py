"""Synthetic-only tests for lifemate_evidence_lifecycle.

No gold fixtures, no sample ids, no dataset reads: every case is
constructed from the module's own schemas. Run from the repo root:

    python3 tests/test_evidence_lifecycle.py
    ~/workspace/zaic-test-venv/bin/python tests/test_evidence_lifecycle.py
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lifemate.lifemate_evidence_lifecycle import (
    MUTATION_TABLE, classify_outcome, classify_tool,
    cancel_tools_are_status_only, result_succeeded, EvidenceLedger,
)


def ev(value, claim, position, registry="synth.items", field=None,
       kind="entity", source="read_result", producer="synth.read",
       outcome="succeeded", status="active", counterpart=None,
       derived_from=None):
    rec = {"kind": kind, "value": value, "source": source,
           "producer": producer, "field": field, "outcome": outcome,
           "counterpart": counterpart, "position": position,
           "claim": claim, "status": status, "reason": "test"}
    if registry is not None:
        rec["registry"] = registry
    if derived_from is not None:
        rec["derived_from"] = derived_from
    return rec


def mut(tool, entity, position, kind, registry="synth.items",
        result=None, args=None, effective=True, fields=None):
    e = {"tool": tool, "args": args if args is not None else {},
         "result": {"ok": True} if result is None else result,
         "position": position, "registry": registry,
         "entity_value": entity, "mutation_kind": kind,
         "effective": effective}
    if fields is not None:
        e["fields"] = fields
    return e


class TestOutcomeSemantics(unittest.TestCase):
    def test_succeeded_rule(self):
        self.assertTrue(result_succeeded({"ok": True}))
        self.assertTrue(result_succeeded({"ok": True, "item": {"id": "x"}}))
        self.assertTrue(result_succeeded({"ok": True, "done": True}))
        self.assertFalse(result_succeeded({"ok": True, "done": False}))
        self.assertFalse(result_succeeded({"ok": False, "error": "schema"}))
        self.assertFalse(result_succeeded({"ok": True, "done": False,
                                           "message": "not found"}))
        self.assertFalse(result_succeeded("ok"))
        self.assertFalse(result_succeeded(None))

    def test_classify_outcome(self):
        self.assertEqual(classify_outcome({"ok": False, "error": "e"}),
                         "schema_rejected")
        self.assertEqual(classify_outcome({"ok": True, "done": False}),
                         "noop")
        self.assertEqual(classify_outcome({"ok": True}), "succeeded")
        self.assertEqual(classify_outcome({"ok": True, "item": {}}),
                         "succeeded")
        self.assertEqual(classify_outcome({}), "failed")
        self.assertEqual(classify_outcome(None), "failed")

    def test_delete_branch_result_counts_as_succeeded(self):
        # email.archive action=delete returns {"ok": True} with NO
        # item and NO done key -- that is a real delete, not a noop.
        self.assertTrue(result_succeeded({"ok": True}))


class TestDelete(unittest.TestCase):
    def test_delete_kills_all_three_claims(self):
        led = EvidenceLedger()
        led.apply_prefix([
            ev("evt_01", "existence", 1, registry="calendar.events"),
            ev("evt_01", "field_value", 2, registry="calendar.events",
               field="title", counterpart={"registry": "calendar.events",
                                           "id": "evt_01"}),
            ev("evt_01", "eligibility", 3, registry="calendar.events"),
            mut("reminders.delete", "evt_01", 4, "delete",
                registry="calendar.events"),
        ])
        self.assertEqual(led.query("calendar.events", "evt_01", "existence")[0],
                         "invalidated")
        self.assertEqual(led.query("calendar.events", "evt_01", "field_value",
                                   field="title")[0], "invalidated")
        self.assertEqual(led.query("calendar.events", "evt_01", "eligibility")[0],
                         "invalidated")

    def test_delete_of_other_entity_touches_nothing(self):
        led = EvidenceLedger()
        led.apply_prefix([
            ev("evt_01", "existence", 1, registry="calendar.events"),
            mut("reminders.delete", "evt_02", 2, "delete",
                registry="calendar.events"),
        ])
        self.assertEqual(led.query("calendar.events", "evt_01", "existence")[0],
                         "active")


class TestCancelStatusOnly(unittest.TestCase):
    def test_cancel_keeps_existence_kills_eligibility_and_status(self):
        # Verified status-only cancel: calendar.cancel_event patches
        # status=cancelled; the event record remains in state.
        led = EvidenceLedger()
        led.apply_prefix([
            ev("evt_01", "existence", 1, registry="calendar.events"),
            ev("evt_01", "field_value", 2, registry="calendar.events",
               field="title", counterpart={"registry": "calendar.events",
                                           "id": "evt_01"}),
            ev("evt_01", "field_value", 3, registry="calendar.events",
               field="status", counterpart={"registry": "calendar.events",
                                            "id": "evt_01"}),
            ev("evt_01", "eligibility", 4, registry="calendar.events"),
            mut("calendar.cancel_event", "evt_01", 5, "cancel",
                registry="calendar.events",
                args={"event_id": "evt_01"}),
        ])
        self.assertEqual(led.query("calendar.events", "evt_01", "existence")[0],
                         "active")
        self.assertEqual(led.query("calendar.events", "evt_01", "field_value",
                                   field="title")[0], "active")
        self.assertEqual(led.query("calendar.events", "evt_01", "field_value",
                                   field="status")[0], "invalidated")
        self.assertEqual(led.query("calendar.events", "evt_01", "eligibility")[0],
                         "invalidated")

    def test_no_cancel_tool_in_table_deletes(self):
        # Honest negative: across all apps, no cancel tool truly
        # deletes. If a future implementation adds one, this test
        # forces the table (and the notes) to say so explicitly.
        self.assertTrue(cancel_tools_are_status_only())
        cancels = [t for t, e in MUTATION_TABLE.items()
                   if e["mutation_kind"] == "cancel"]
        self.assertGreater(len(cancels), 0)
        for tool in cancels:
            self.assertIn("status=cancelled",
                          MUTATION_TABLE[tool].get("notes", ""))

    def test_email_archive_branches(self):
        # archive without action: folder update, existence survives.
        led = EvidenceLedger()
        led.apply_prefix([
            ev("em_01", "existence", 1, registry="email.emails"),
            mut("email.archive", "em_01", 2, "update",
                registry="email.emails", args={"email_id": "em_01"},
                fields=["folder"]),
        ])
        self.assertEqual(led.query("email.emails", "em_01", "existence")[0],
                         "active")
        # archive with action=delete: real delete (ok True, NO item),
        # existence dies. Classification needs the action arg.
        led2 = EvidenceLedger()
        led2.apply_prefix([
            ev("em_01", "existence", 1, registry="email.emails"),
            mut("email.archive", "em_01", 2, "delete",
                registry="email.emails",
                args={"email_id": "em_01", "action": "delete"},
                result={"ok": True}),
        ])
        self.assertEqual(led2.query("email.emails", "em_01", "existence")[0],
                         "invalidated")


class TestUpdate(unittest.TestCase):
    def test_update_kills_only_touched_field(self):
        led = EvidenceLedger()
        led.apply_prefix([
            ev("c_01", "existence", 1, registry="contacts.contacts"),
            ev("c_01", "field_value", 2, registry="contacts.contacts",
               field="phone", counterpart={"registry": "contacts.contacts",
                                           "id": "c_01"}),
            ev("c_01", "field_value", 3, registry="contacts.contacts",
               field="email", counterpart={"registry": "contacts.contacts",
                                           "id": "c_01"}),
            mut("contacts.update", "c_01", 4, "update",
                registry="contacts.contacts",
                args={"contact_id": "c_01", "phone": "0999999999"}),
        ])
        self.assertEqual(led.query("contacts.contacts", "c_01", "existence")[0],
                         "active")
        self.assertEqual(led.query("contacts.contacts", "c_01", "field_value",
                                   field="phone")[0], "invalidated")
        self.assertEqual(led.query("contacts.contacts", "c_01", "field_value",
                                   field="email")[0], "active")

    def test_update_kills_field_grounded_existence(self):
        # A phone-number existence record grounded in a contact's
        # phone field dies when that phone changes; the contact's
        # own existence record (field None) does not.
        led = EvidenceLedger()
        led.apply_prefix([
            ev("0901112222", "existence", 1, kind="phone",
               registry="contacts.contacts", field="phone",
               counterpart={"registry": "contacts.contacts", "id": "c_01"}),
            ev("c_01", "existence", 2, registry="contacts.contacts"),
            mut("contacts.update", "c_01", 3, "update",
                registry="contacts.contacts",
                args={"contact_id": "c_01", "phone": "0909998888"}),
        ])
        self.assertEqual(led.query("contacts.contacts", "0901112222",
                                   "existence")[0], "invalidated")
        self.assertEqual(led.query("contacts.contacts", "c_01",
                                   "existence")[0], "active")

    def test_update_unknown_fields_is_conservative(self):
        # An update that does not declare touched fields kills ALL
        # field claims for that entity (cannot prove survival).
        # NOTE: this needs an event with NO args key at all -- an
        # update with args={} touches nothing by construction
        # (App.patch applies only non-None fields), so it kills
        # nothing, correctly.
        led = EvidenceLedger()
        led.apply_prefix([
            ev("d_01", "field_value", 1, registry="smart_home.devices",
               field="state.power",
               counterpart={"registry": "smart_home.devices", "id": "d_01"}),
            ev("d_01", "existence", 2, registry="smart_home.devices"),
        ])
        no_args = {"tool": "smart_home.switch_set",
                   "result": {"ok": True}, "position": 3,
                   "registry": "smart_home.devices",
                   "entity_value": "d_01", "mutation_kind": "update",
                   "effective": True}
        led.apply_mutation(no_args)
        self.assertEqual(led.query("smart_home.devices", "d_01", "field_value",
                                   field="state.power")[0], "invalidated")
        self.assertEqual(led.query("smart_home.devices", "d_01",
                                   "existence")[0], "active")

    def test_nested_state_field_matching(self):
        led = EvidenceLedger()
        led.apply_prefix([
            ev("d_01", "field_value", 1, registry="smart_home.devices",
               field="state.power",
               counterpart={"registry": "smart_home.devices", "id": "d_01"}),
            mut("smart_home.light_set", "d_01", 2, "update",
                registry="smart_home.devices",
                args={"device_id": "d_01", "power": "off"},
                fields=["state.power"]),
        ])
        self.assertEqual(led.query("smart_home.devices", "d_01", "field_value",
                                   field="state.power")[0], "invalidated")

    def test_disable_kills_eligibility(self):
        led = EvidenceLedger()
        led.apply_prefix([
            ev("alm_01", "existence", 1, registry="alarm.alarms"),
            ev("alm_01", "eligibility", 2, registry="alarm.alarms"),
            mut("alarm.update", "alm_01", 3, "update",
                registry="alarm.alarms",
                args={"alarm_id": "alm_01", "enabled": False}),
        ])
        self.assertEqual(led.query("alarm.alarms", "alm_01", "existence")[0],
                         "active")
        self.assertEqual(led.query("alarm.alarms", "alm_01", "eligibility")[0],
                         "invalidated")


class TestFailedMutations(unittest.TestCase):
    def test_schema_reject_noop_and_ineffective_kill_nothing(self):
        for result, effective, label in [
                ({"ok": False, "error": "schema"}, True, "schema_rejected"),
                ({"ok": True, "done": False, "message": "not found"}, True, "noop"),
                ({"ok": True}, False, "ineffective_flag"),
                ("not-a-dict", True, "non_dict")]:
            with self.subTest(case=label):
                led = EvidenceLedger()
                led.apply_prefix([
                    ev("r_01", "existence", 1, registry="reminders.reminders"),
                    mut("reminders.delete", "r_01", 2, "delete",
                        registry="reminders.reminders", result=result,
                        effective=effective),
                ])
                self.assertEqual(
                    led.query("reminders.reminders", "r_01", "existence")[0],
                    "active")

    def test_failed_evidence_is_never_active(self):
        led = EvidenceLedger()
        led.add_evidence(ev("x_01", "existence", 1, outcome="noop",
                             status="active"))
        self.assertEqual(led.query("synth.items", "x_01", "existence")[0],
                         "unknown")
        led2 = EvidenceLedger()
        led2.add_evidence(ev("x_01", "existence", 1, outcome="succeeded",
                              status="ambiguous"))
        self.assertEqual(led2.query("synth.items", "x_01", "existence")[0],
                         "unknown")


class TestReread(unittest.TestCase):
    def test_reread_after_delete_reestablishes(self):
        led = EvidenceLedger()
        led.apply_prefix([
            ev("r_01", "existence", 1, registry="reminders.reminders"),
            mut("reminders.delete", "r_01", 2, "delete",
                registry="reminders.reminders"),
        ])
        self.assertEqual(led.query("reminders.reminders", "r_01",
                                   "existence")[0], "invalidated")
        # A later SUCCEEDED read returning the entity is new evidence.
        led.add_evidence(ev("r_01", "existence", 3,
                             registry="reminders.reminders"))
        st, rec, _ = led.query("reminders.reminders", "r_01", "existence")
        self.assertEqual(st, "active")
        self.assertEqual(rec["position"], 3)

    def test_reread_new_value_supersedes_for_field_query(self):
        led = EvidenceLedger()
        cp = {"registry": "contacts.contacts", "id": "c_01"}
        led.apply_prefix([
            ev("0901112222", "field_value", 1, registry="contacts.contacts",
               field="phone", counterpart=cp),
            mut("contacts.update", "c_01", 2, "update",
                registry="contacts.contacts",
                args={"contact_id": "c_01", "phone": "0909998888"}),
            ev("0909998888", "field_value", 3, registry="contacts.contacts",
               field="phone", counterpart=cp),
        ])
        st, rec, _ = led.query("contacts.contacts", "c_01", "field_value",
                               field="phone")
        self.assertEqual(st, "active")
        self.assertEqual(rec["value"], "0909998888")

    def test_noop_read_after_delete_does_not_revive(self):
        led = EvidenceLedger()
        led.apply_prefix([
            ev("r_01", "existence", 1, registry="reminders.reminders"),
            mut("reminders.delete", "r_01", 2, "delete",
                registry="reminders.reminders"),
            # A read of the deleted id returns noop (empty) -- outcome
            # noop is not evidence, so nothing revives.
            ev("r_01", "existence", 3, registry="reminders.reminders",
               outcome="noop", status="active"),
        ])
        self.assertEqual(led.query("reminders.reminders", "r_01",
                                   "existence")[0], "invalidated")


class TestDerived(unittest.TestCase):
    def test_derived_goes_unknown_when_source_dies(self):
        # Guest-code style: code derived from lock existence +
        # valid_until field. The lock's valid_until field changes
        # (synthetic update standing in for any source mutation).
        led = EvidenceLedger()
        led.apply_prefix([
            ev("lock_01", "existence", 1, registry="door_lock.locks"),
            ev("lock_01", "field_value", 2, registry="door_lock.locks",
               field="valid_until",
               counterpart={"registry": "door_lock.locks", "id": "lock_01"}),
            ev("123456", "existence", 3, kind="entity",
               registry="door_lock.guest_codes", field="code",
               derived_from=[{"registry": "door_lock.locks",
                              "value": "lock_01", "claim": "existence"},
                             {"registry": "door_lock.locks",
                              "value": "lock_01", "claim": "field_value",
                              "field": "valid_until"}]),
            mut("door_lock.set_lock", "lock_01", 4, "update",
                registry="door_lock.locks",
                args={"lock_id": "lock_01", "locked": True},
                fields=["locked"]),
        ])
        # locked update does not touch valid_until: derived stays.
        self.assertEqual(led.query("door_lock.guest_codes", "123456",
                                   "existence")[0], "active")
        led.apply_mutation(mut("door_lock.set_lock", "lock_01", 5, "update",
                                registry="door_lock.locks",
                                args={"lock_id": "lock_01"},
                                fields=["valid_until"]))
        st, _, reason = led.query("door_lock.guest_codes", "123456",
                                  "existence")
        self.assertEqual(st, "unknown")
        self.assertIn("derived_source_invalidated", reason)

    def test_derived_survives_unrelated_update(self):
        led = EvidenceLedger()
        led.apply_prefix([
            ev("src_01", "existence", 1, registry="synth.items"),
            ev("der_01", "existence", 2, registry="synth.derived",
               derived_from=[{"registry": "synth.items", "value": "src_01",
                              "claim": "existence"}]),
            mut("synth.update", "other_01", 3, "update",
                registry="synth.items", args={"x": 1}, fields=["x"]),
        ])
        self.assertEqual(led.query("synth.derived", "der_01",
                                   "existence")[0], "active")

    def test_derived_cycle_is_unknown_not_crash(self):
        led = EvidenceLedger()
        led.apply_prefix([
            ev("a_01", "existence", 1, registry="synth.derived",
               derived_from=[{"registry": "synth.derived", "value": "b_01",
                              "claim": "existence"}]),
            ev("b_01", "existence", 2, registry="synth.derived",
               derived_from=[{"registry": "synth.derived", "value": "a_01",
                              "claim": "existence"}]),
        ])
        st, _, reason = led.query("synth.derived", "a_01", "existence")
        self.assertEqual(st, "unknown")
        self.assertIn("derived_cycle", reason)


class TestRegistryIsolation(unittest.TestCase):
    def test_same_id_string_in_two_registries(self):
        led = EvidenceLedger()
        led.apply_prefix([
            ev("item_01", "existence", 1, registry="shopping_list.items"),
            ev("item_01", "existence", 2, registry="smart_home.devices"),
            mut("shopping_list.remove", "item_01", 3, "delete",
                registry="shopping_list.items"),
        ])
        self.assertEqual(led.query("shopping_list.items", "item_01",
                                   "existence")[0], "invalidated")
        self.assertEqual(led.query("smart_home.devices", "item_01",
                                   "existence")[0], "active")


class TestPrefixOrder(unittest.TestCase):
    def test_future_mutation_invisible_to_prefix_query(self):
        led = EvidenceLedger()
        led.apply_prefix([
            ev("r_01", "existence", 1, registry="reminders.reminders"),
            mut("reminders.delete", "r_01", 5, "delete",
                registry="reminders.reminders"),
        ])
        self.assertEqual(led.query("reminders.reminders", "r_01", "existence",
                                   position=3)[0], "active")
        self.assertEqual(led.query("reminders.reminders", "r_01", "existence",
                                   position=5)[0], "invalidated")
        self.assertEqual(led.query("reminders.reminders", "r_01",
                                   "existence")[0], "invalidated")

    def test_apply_prefix_sorts_by_position(self):
        led = EvidenceLedger()
        led.apply_prefix([
            mut("reminders.delete", "r_01", 2, "delete",
                registry="reminders.reminders"),
            ev("r_01", "existence", 1, registry="reminders.reminders"),
        ])
        # Journal order is position order, so the delete (pos 2)
        # still kills the earlier evidence (pos 1).
        self.assertEqual(led.query("reminders.reminders", "r_01",
                                   "existence")[0], "invalidated")

    def test_any_surviving_record_keeps_key_active(self):
        # Two independent evidences; a mutation linked to only one
        # (via counterpart) leaves the other standing.
        led = EvidenceLedger()
        led.apply_prefix([
            ev("0901112222", "existence", 1, kind="phone",
               registry="phone.calls", field=None,
               counterpart={"registry": "phone.calls", "id": "call_01"}),
            ev("0901112222", "existence", 2, kind="phone",
               registry="phone.calls", field=None,
               counterpart={"registry": "phone.calls", "id": "call_02"}),
            mut("phone.call", "call_01", 3, "delete",
                registry="phone.calls"),
        ])
        self.assertEqual(led.query("phone.calls", "0901112222",
                                   "existence")[0], "active")


class TestMultiEffectAndGuards(unittest.TestCase):
    def test_transfer_kills_balance_only(self):
        led = EvidenceLedger()
        led.apply_prefix([
            ev("acc_01", "existence", 1, registry="banking.accounts"),
            ev("acc_01", "field_value", 2, registry="banking.accounts",
               field="balance",
               counterpart={"registry": "banking.accounts", "id": "acc_01"}),
            ev("acc_01", "field_value", 3, registry="banking.accounts",
               field="owner",
               counterpart={"registry": "banking.accounts", "id": "acc_01"}),
            # Adapter emits the side-effect event for the account.
            mut("banking.transfer", "acc_01", 4, "update",
                registry="banking.accounts",
                args={"from_account_id": "acc_01"},
                fields=["balance"]),
        ])
        self.assertEqual(led.query("banking.accounts", "acc_01",
                                   "existence")[0], "active")
        self.assertEqual(led.query("banking.accounts", "acc_01", "field_value",
                                   field="balance")[0], "invalidated")
        self.assertEqual(led.query("banking.accounts", "acc_01", "field_value",
                                   field="owner")[0], "active")

    def test_scene_run_per_device(self):
        # scene_run touches only its action devices; the adapter
        # emits one event per device (multi-entity rule).
        led = EvidenceLedger()
        led.apply_prefix([
            ev("dev_a", "field_value", 1, registry="smart_home.devices",
               field="state.power",
               counterpart={"registry": "smart_home.devices", "id": "dev_a"}),
            ev("dev_b", "field_value", 2, registry="smart_home.devices",
               field="state.power",
               counterpart={"registry": "smart_home.devices", "id": "dev_b"}),
            mut("smart_home.scene_run", "dev_a", 3, "update",
                registry="smart_home.devices", fields=["state.power"]),
        ])
        self.assertEqual(led.query("smart_home.devices", "dev_a", "field_value",
                                   field="state.power")[0], "invalidated")
        self.assertEqual(led.query("smart_home.devices", "dev_b", "field_value",
                                   field="state.power")[0], "active")

    def test_guarded_noop_check_in_changes_nothing(self):
        # flights.check_in on a cancelled booking is a noop: it
        # neither revives eligibility nor kills anything new.
        led = EvidenceLedger()
        led.apply_prefix([
            ev("bk_01", "existence", 1, registry="flights.bookings"),
            ev("bk_01", "eligibility", 2, registry="flights.bookings"),
            mut("flights.cancel", "bk_01", 3, "cancel",
                registry="flights.bookings"),
            mut("flights.check_in", "bk_01", 4, "update",
                registry="flights.bookings",
                result={"ok": True, "done": False,
                        "message": "vé đã huỷ"},
                args={"booking_id": "bk_01"}, fields=["checked_in"]),
        ])
        self.assertEqual(led.query("flights.bookings", "bk_01",
                                   "existence")[0], "active")
        self.assertEqual(led.query("flights.bookings", "bk_01",
                                   "eligibility")[0], "invalidated")

    def test_create_kills_nothing(self):
        led = EvidenceLedger()
        led.apply_prefix([
            ev("ord_01", "existence", 1, registry="food_delivery.orders"),
            mut("food_delivery.place_order", "ord_02", 2, "create",
                registry="food_delivery.orders"),
        ])
        self.assertEqual(led.query("food_delivery.orders", "ord_01",
                                   "existence")[0], "active")

    def test_id_reuse_after_delete_needs_fresh_evidence(self):
        # App.new_id can reuse an id after a delete shrinks the
        # collection. The killed record stays killed; only a NEW
        # create-result record (later position) re-establishes it.
        led = EvidenceLedger()
        led.apply_prefix([
            ev("item_02", "existence", 1, registry="shopping_list.items"),
            mut("shopping_list.remove", "item_02", 2, "delete",
                registry="shopping_list.items"),
        ])
        self.assertEqual(led.query("shopping_list.items", "item_02",
                                   "existence")[0], "invalidated")
        led.add_evidence(ev("item_02", "existence", 3,
                             registry="shopping_list.items",
                             source="write_result", producer="shopping_list.add"))
        self.assertEqual(led.query("shopping_list.items", "item_02",
                                   "existence")[0], "active")

    def test_field_value_query_requires_field_when_ambiguous(self):
        led = EvidenceLedger()
        cp = {"registry": "contacts.contacts", "id": "c_01"}
        led.apply_prefix([
            ev("c_01", "field_value", 1, registry="contacts.contacts",
               field="phone", counterpart=cp),
            ev("c_01", "field_value", 2, registry="contacts.contacts",
               field="email", counterpart=cp),
        ])
        st, _, reason = led.query("contacts.contacts", "c_01", "field_value")
        self.assertEqual(st, "unknown")
        self.assertIn("field_value_query_requires_field", reason)


class TestTableSanity(unittest.TestCase):
    def test_every_entry_has_registry_id_arg_kind(self):
        for tool, entry in MUTATION_TABLE.items():
            self.assertIn("registry", entry, tool)
            self.assertIn("id_arg", entry, tool)
            self.assertIn(entry["mutation_kind"],
                          ("delete", "cancel", "update", "create", "none"),
                          tool)

    def test_classify_tool(self):
        self.assertEqual(classify_tool("calendar.cancel_event")["mutation_kind"],
                         "cancel")
        self.assertEqual(classify_tool("reminders.delete")["mutation_kind"],
                         "delete")
        self.assertIsNone(classify_tool("calendar.list_events"))
        self.assertIsNone(classify_tool("no.such_tool"))

    def test_real_delete_tools_exist_and_are_not_cancels(self):
        deletes = [t for t, e in MUTATION_TABLE.items()
                   if e["mutation_kind"] == "delete"]
        # True deletes found in implementation (App.delete calls).
        for expected in ("reminders.delete", "alarm.delete",
                         "shopping_list.remove", "home_automation.delete_rule",
                         "medication.remove"):
            self.assertIn(expected, deletes)



class TestReviewerRound2FixedFields(unittest.TestCase):
    """R2-B1: fixed-field updates must kill the field claim via
    table 'fields' (args alone carry only the id)."""

    FIXED = [
        ("tasks.complete", "tasks.tasks", "t1", "done"),
        ("reminders.complete", "reminders.reminders", "r1", "done"),
        ("shopping_list.check", "shopping_list.items", "i1", "checked"),
        ("flights.check_in", "flights.bookings", "b1", "checked_in"),
        ("video_meeting.join", "video_meeting.meetings", "m1", "status"),
        ("music.add_to_playlist", "music.playlists", "p1", "track_ids"),
        ("bill_payment.pay", "bill_payment.bills", "bl1", "paid"),
    ]

    def test_fixed_field_updates_kill_via_table_fields(self):
        for tool, reg, ent, field in self.FIXED:
            entry = classify_tool(tool)
            self.assertIsNotNone(entry, tool)
            self.assertIn(field, entry.get("fields") or [], tool)
            led = EvidenceLedger()
            led.add_evidence({
                "kind": "entity", "value": ent, "registry": reg,
                "source": "read_result", "producer": "read",
                "field": field, "outcome": "succeeded",
                "counterpart": None, "position": 1,
                "claim": "field_value", "status": "active",
                "reason": "t"})
            ev = {"tool": tool,
                  "args": {entry["id_arg"]: ent},
                  "result": {"ok": True}, "position": 2,
                  "registry": reg, "entity_value": ent,
                  "mutation_kind": "update", "effective": True,
                  "fields": entry["fields"]}
            led.apply_mutation(ev)
            status, _, _ = led.query(reg, ent, "field_value",
                                     position=3, field=field)
            self.assertEqual(status, "invalidated", tool)

    def test_email_archive_table_documents_branch(self):
        # R2-B2: the table alone cannot decide delete-vs-update;
        # kind_arg + fields document the branch for the adapter.
        entry = classify_tool("email.archive")
        self.assertEqual(entry["kind_arg"], "action")
        self.assertEqual(entry["fields"], ["folder"])

if __name__ == "__main__":
    unittest.main(verbosity=1)
