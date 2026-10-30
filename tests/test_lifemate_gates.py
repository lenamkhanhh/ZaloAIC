"""Unit tests for lifemate_gates (Round 10).

Synthetic rosters/evidence only: no data files, no simulator, no network.
Runs with plain python3 and with /tmp/rfvenv/bin/python.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lifemate.lifemate_gates import (  # noqa: E402
    gate_contact_ambiguity, gate_read_before_write, gate_confirmation,
    gate_confirmation_scoped, AskBudget, PriorCall)

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
        r = gate_read_before_write(call, [], ROSTER_CLEAN)
        self.assertFalse(r.fired)  # roster establishes the contact
        r = gate_read_before_write(call, [], [])
        self.assertTrue(r.fired)

    def test_entity_id_needs_succeeded_result(self):
        call = {"name": "alarm.delete",
                "arguments": {"alarm_id": "alm_01"}}
        # A succeeded read whose result carries the id field: pass.
        r = gate_read_before_write(
            call, [PriorCall("alarm.list", {},
                             result_entries=[("id", "alm_01")],
                             succeeded=True)],
            [])
        self.assertFalse(r.fired)
        # No evidence at all: fires.
        r = gate_read_before_write(call, [], [])
        self.assertTrue(r.fired)
        # Fix round F: a prior WRITE's arguments never establish the id,
        # even when that write succeeded.
        r = gate_read_before_write(
            call, [PriorCall("alarm.snooze", {"alarm_id": "alm_01"},
                             succeeded=True)],
            [])
        self.assertTrue(r.fired)
        # Fix round F2: a result echoing the call's own argument proves
        # nothing (sms/phone never validate contacts).
        r = gate_read_before_write(
            {"name": "sms.send", "arguments": {"contact_id": "c_05"}},
            [PriorCall("sms.send", {"contact_id": "c_05"},
                       result_entries=[("contact_id", "c_05")],
                       succeeded=True)],
            [])
        self.assertTrue(r.fired)
        # A failed read establishes nothing.
        r = gate_read_before_write(
            call, [PriorCall("alarm.list", {},
                             result_entries=[], succeeded=False)],
            [])
        self.assertTrue(r.fired)

    def test_flat_string_is_not_entity_evidence(self):
        # Fix round 2 (Codex): a free-text scalar from another tool
        # that merely equals an id proves nothing.
        r = gate_read_before_write(
            {"name": "phone.call", "arguments": {"contact_id": "c_fake"}},
            [PriorCall("calendar.list_events", {},
                       result_entries=[(None, "c_fake")],
                       succeeded=True)],
            [])
        self.assertTrue(r.fired)
        r = gate_read_before_write(
            {"name": "phone.call", "arguments": {"contact_id": "c_fake"}},
            [PriorCall("calendar.list_events", {},
                       result_entries=[("description", "c_fake")],
                       succeeded=True)],
            [])
        self.assertTrue(r.fired)
        # Even a same-app id field of the WRONG entity type does not
        # establish a contact: contacts come from contacts-app only.
        r = gate_read_before_write(
            {"name": "phone.call", "arguments": {"contact_id": "c_fake"}},
            [PriorCall("calendar.list_events", {},
                       result_entries=[("id", "c_fake")],
                       succeeded=True)],
            [])
        self.assertTrue(r.fired)

    def test_shared_registry_read_passes_message_history_contact_fires(self):
        # Fix round 2: smart_home.get_status lists device ids that
        # home_automation.create_rule references -- one shared
        # registry (create_rule's docstring: device_id "must exist in
        # smart_home.devices"), so the cross-app read passes.
        # THREAD 1 round: the evidence must carry its PATH. A legacy
        # 2-tuple ("id", ...) from get_status is ambiguous (devices
        # vs scenes) and establishes NOTHING; the path-aware triple
        # ("id", ..., "devices") passes, and a scene path does NOT
        # establish a device_id.
        r = gate_read_before_write(
            {"name": "home_automation.create_rule",
             "arguments": {"device_id": "fan_bedroom"}},
            [PriorCall("smart_home.get_status", {},
                       result_entries=[("id", "fan_bedroom", "devices")],
                       succeeded=True)],
            [])
        self.assertFalse(r.fired)
        # Legacy ambiguous entry: fires (unknown, not same-registry).
        r = gate_read_before_write(
            {"name": "home_automation.create_rule",
             "arguments": {"device_id": "fan_bedroom"}},
            [PriorCall("smart_home.get_status", {},
                       result_entries=[("id", "fan_bedroom")],
                       succeeded=True)],
            [])
        self.assertTrue(r.fired)
        # Scene path establishes a scene, not a device.
        r = gate_read_before_write(
            {"name": "home_automation.create_rule",
             "arguments": {"device_id": "scene_01"}},
            [PriorCall("smart_home.get_status", {},
                       result_entries=[("id", "scene_01", "scenes")],
                       succeeded=True)],
            [])
        self.assertTrue(r.fired)
        r = gate_read_before_write(
            {"name": "smart_home.scene_run",
             "arguments": {"scene_id": "scene_01"}},
            [PriorCall("smart_home.get_status", {},
                       result_entries=[("id", "scene_01", "scenes")],
                       succeeded=True)],
            [])
        self.assertFalse(r.fired)
        # But a message-history contact reference does NOT prove
        # address-book membership (sms/phone never validate contacts):
        # only contacts-app results establish contacts.
        r = gate_read_before_write(
            {"name": "sms.send", "arguments": {"contact_id": "c_778"}},
            [PriorCall("sms.read_recent", {"contact_id": "c_778"},
                       result_entries=[("contact_id", "c_778")],
                       succeeded=True)],
            [])
        self.assertTrue(r.fired)

    def test_read_lookup_verifies_but_noop_does_not(self):
        # Fix round 2 (Codex, ride_hailing.get_ride): a succeeded read
        # verifies its input id by lookup (find or noop); a noop read
        # (unknown id -> done False) verifies nothing.
        call = {"name": "ride_hailing.cancel",
                "arguments": {"ride_id": "ride_real"}}
        r = gate_read_before_write(
            call, [PriorCall("ride_hailing.get_ride",
                             {"ride_id": "ride_real"},
                             result_entries=[("id", "ride_real")],
                             succeeded=True)],
            [])
        self.assertFalse(r.fired)
        r = gate_read_before_write(
            call, [PriorCall("ride_hailing.get_ride",
                             {"ride_id": "ride_real"},
                             result_entries=[], succeeded=False)],
            [])
        self.assertTrue(r.fired)

    def test_write_non_echo_id_passes_patch_echo_fires(self):
        # THREAD 1 round: a succeeded create returning a NEW id
        # establishes ONLY that id's registry (calendar.create_event
        # -> calendar.events, so a later update_event passes).
        r = gate_read_before_write(
            {"name": "calendar.update_event",
             "arguments": {"event_id": "evt_42"}},
            [PriorCall("calendar.create_event", {},
                       result_entries=[("id", "evt_42", "")],
                       succeeded=True)],
            [])
        self.assertFalse(r.fired)
        # The same new id does NOT establish a different registry.
        r = gate_read_before_write(
            {"name": "ride_hailing.cancel",
             "arguments": {"ride_id": "evt_42"}},
            [PriorCall("calendar.create_event", {},
                       result_entries=[("id", "evt_42", "")],
                       succeeded=True)],
            [])
        self.assertTrue(r.fired)
        # A foreign-key field inside a created record establishes
        # nothing about the referenced registry: a savings record's
        # account_id (which in a real call would also be an echo of
        # from_account_id) does not establish banking.accounts for
        # a later write. (The round-2 form of this test used
        # account_id as the "new id" example; under registry typing
        # that was a foreign key, not a primary id, and it no
        # longer passes -- this is the intended correction, not a
        # regression to hide.)
        r = gate_read_before_write(
            {"name": "banking.get_balance",
             "arguments": {"account_id": "acc_99"}},
            [PriorCall("banking.open_savings", {},
                       result_entries=[("account_id", "acc_99",
                                        "savings")],
                       succeeded=True)],
            [])
        # get_balance is a read: gate does not apply at all.
        self.assertFalse(r.applicable)
        # Conservative residual: a patch-style write returning the full
        # record of the id it looked up is still treated as echo when
        # the id equals its argument (shape cannot distinguish it from
        # a non-validating echo).
        r = gate_read_before_write(
            {"name": "ride_hailing.get_ride",
             "arguments": {"ride_id": "ride_real"}},
            [PriorCall("ride_hailing.cancel", {"ride_id": "ride_real"},
                       result_entries=[("id", "ride_real")],
                       succeeded=True)],
            [])
        self.assertFalse(r.applicable)  # get_ride is a read
        r = gate_read_before_write(
            {"name": "ride_hailing.book",
             "arguments": {"ride_id": "ride_real"}},
            [PriorCall("ride_hailing.cancel", {"ride_id": "ride_real"},
                       result_entries=[("id", "ride_real")],
                       succeeded=True)],
            [])
        self.assertTrue(r.fired)

    def test_all_references_checked(self):
        # Fix round G: an established contact must not mask an
        # unestablished entity id in the same call (synthetic schema:
        # no real tool combines both -- defence in depth).
        call = {"name": "x.transfer",
                "arguments": {"contact_id": "c_05",
                              "event_id": "evt_99"}}
        r = gate_read_before_write(call, [], ROSTER_CLEAN)
        self.assertTrue(r.fired)
        self.assertIn("evt_99", r.reason)

    def test_fully_specified_create_is_not_applicable(self):
        r = gate_read_before_write(
            {"name": "reminders.create",
             "arguments": {"time": "2026-11-19T08:00:00+07:00"}},
            [], [])
        self.assertFalse(r.applicable)

    def test_bare_mutate_verb_needs_succeeded_app_read(self):
        call = {"name": "calendar.delete_event", "arguments": {}}
        r = gate_read_before_write(call, [], [])
        self.assertTrue(r.fired)
        r = gate_read_before_write(
            call, [PriorCall("calendar.list_events", {},
                             result_entries=[], succeeded=True)],
            [])
        self.assertFalse(r.fired)
        # A failed read does not count as a read.
        r = gate_read_before_write(
            call, [PriorCall("calendar.list_events", {},
                             result_entries=[], succeeded=False)],
            [])
        self.assertTrue(r.fired)


class TestRegistryMapping(unittest.TestCase):
    """THREAD 1 round: the 8 mandatory registry verifications, plus
    the ambiguous-producer cases that forced the path extension.
    Every case states its registry reasoning; none relies on id
    prefixes or on gold statistics."""

    def test_1_calendar_event_id_does_not_establish_ride_id(self):
        evt = [PriorCall("calendar.list_events", {},
                         result_entries=[("id", "same_01", "events")],
                         succeeded=True)]
        r = gate_read_before_write(
            {"name": "ride_hailing.cancel",
             "arguments": {"ride_id": "same_01"}}, evt, [])
        self.assertTrue(r.fired)
        # Control: the same evidence DOES establish its own registry.
        r = gate_read_before_write(
            {"name": "calendar.update_event",
             "arguments": {"event_id": "same_01"}}, evt, [])
        self.assertFalse(r.fired)

    def test_2_message_reference_does_not_establish_contact(self):
        # A message record's contact_id is a foreign key in
        # sms.messages, not a contacts.contacts record; sms/phone
        # never validate contacts (base.py contact_ref returns an
        # unknown contact_id unchanged).
        priors = [PriorCall("sms.read_recent", {"contact_id": "c_99"},
                            result_entries=[("contact_id", "c_99",
                                             "messages"),
                                            ("id", "msg_01",
                                             "messages")],
                            succeeded=True)]
        r = gate_read_before_write(
            {"name": "sms.send", "arguments": {"contact_id": "c_99"}},
            priors, [])
        self.assertTrue(r.fired)
        # A message's own id does not establish a contact either.
        r = gate_read_before_write(
            {"name": "phone.call",
             "arguments": {"contact_id": "msg_01"}},
            [PriorCall("sms.send", {"contact_id": "c_99"},
                       result_entries=[("id", "msg_01", "message")],
                       succeeded=True)],
            [])
        self.assertTrue(r.fired)

    def test_3_free_text_id_does_not_establish_entity(self):
        r = gate_read_before_write(
            {"name": "calendar.update_event",
             "arguments": {"event_id": "evt_99"}},
            [PriorCall("calendar.list_events", {},
                       result_entries=[("description", "evt_99",
                                        "events")],
                       succeeded=True)],
            [])
        self.assertTrue(r.fired)
        r = gate_read_before_write(
            {"name": "calendar.update_event",
             "arguments": {"event_id": "evt_99"}},
            [PriorCall("calendar.list_events", {},
                       result_entries=[(None, "evt_99", "events")],
                       succeeded=True)],
            [])
        self.assertTrue(r.fired)

    def test_4_smart_home_device_to_home_automation_stays_valid(self):
        # The ONE shared-registry relation with implementation
        # evidence: home_automation.create_rule checks
        # session.states["smart_home"]["devices"] (and its catalog
        # x-ref is smart_home.devices).
        r = gate_read_before_write(
            {"name": "home_automation.create_rule",
             "arguments": {"device_id": "fan_bedroom"}},
            [PriorCall("smart_home.get_status", {},
                       result_entries=[("id", "fan_bedroom",
                                        "devices")],
                       succeeded=True)],
            [])
        self.assertFalse(r.fired)
        r = gate_read_before_write(
            {"name": "smart_home.light_set",
             "arguments": {"device_id": "fan_bedroom"}},
            [PriorCall("smart_home.get_status", {},
                       result_entries=[("id", "fan_bedroom",
                                        "devices")],
                       succeeded=True)],
            [])
        self.assertFalse(r.fired)

    def test_5_get_ride_lookup_to_cancel_passes(self):
        r = gate_read_before_write(
            {"name": "ride_hailing.cancel",
             "arguments": {"ride_id": "ride_real"}},
            [PriorCall("ride_hailing.get_ride",
                       {"ride_id": "ride_real"},
                       result_entries=[("id", "ride_real", "ride")],
                       succeeded=True)],
            [])
        self.assertFalse(r.fired)

    def test_6_failed_noop_empty_reads_establish_nothing(self):
        call = {"name": "alarm.delete",
                "arguments": {"alarm_id": "alm_01"}}
        # Failed read (ok False) with entries present anyway.
        r = gate_read_before_write(
            call, [PriorCall("alarm.list", {},
                             result_entries=[("id", "alm_01",
                                              "alarms")],
                             succeeded=False)],
            [])
        self.assertTrue(r.fired)
        # Succeeded read with no entries (empty list / noop shape).
        r = gate_read_before_write(
            call, [PriorCall("alarm.list", {},
                             result_entries=[], succeeded=True)],
            [])
        self.assertTrue(r.fired)
        # Succeeded read of the WRONG registry.
        r = gate_read_before_write(
            call, [PriorCall("calendar.list_events", {},
                             result_entries=[("id", "alm_01",
                                              "events")],
                             succeeded=True)],
            [])
        self.assertTrue(r.fired)

    def test_7_create_new_id_establishes_only_its_type(self):
        booking = [PriorCall("flights.book", {"flight_id": "fl_01"},
                             result_entries=[("id", "bk_01",
                                              "booking"),
                                             ("flight_id", "fl_01",
                                              "booking")],
                             succeeded=True)]
        # New booking id establishes flights.bookings...
        r = gate_read_before_write(
            {"name": "flights.check_in",
             "arguments": {"booking_id": "bk_01"}}, booking, [])
        self.assertFalse(r.fired)
        # ...but the booking record's flight_id foreign key does
        # NOT establish flights.flights.
        r = gate_read_before_write(
            {"name": "flights.book",
             "arguments": {"flight_id": "fl_01"}}, booking, [])
        self.assertTrue(r.fired)

    def test_8_write_echo_never_self_establishes(self):
        # sms/phone echoes (never validated) and transfer echoes
        # (foreign keys in the transaction record) all fire.
        r = gate_read_before_write(
            {"name": "phone.call", "arguments": {"contact_id": "c_05"}},
            [PriorCall("phone.call", {"contact_id": "c_05"},
                       result_entries=[("contact_id", "c_05",
                                        "call")],
                       succeeded=True)],
            [])
        self.assertTrue(r.fired)
        r = gate_read_before_write(
            {"name": "banking.transfer",
             "arguments": {"from_account_id": "acc_01",
                           "beneficiary_id": "ben_01"}},
            [PriorCall("banking.transfer",
                       {"from_account_id": "acc_01",
                        "beneficiary_id": "ben_01"},
                       result_entries=[("beneficiary_id", "ben_01",
                                        "transaction")],
                       succeeded=True)],
            [])
        self.assertTrue(r.fired)

    def test_music_track_vs_playlist_paths(self):
        tracks = [PriorCall("music.list_tracks", {},
                            result_entries=[("id", "tr_01", "tracks")],
                            succeeded=True)]
        r = gate_read_before_write(
            {"name": "music.play", "arguments": {"track_id": "tr_01"}},
            tracks, [])
        self.assertFalse(r.fired)
        r = gate_read_before_write(
            {"name": "music.play",
             "arguments": {"playlist_id": "tr_01"}}, tracks, [])
        self.assertTrue(r.fired)
        # Legacy 2-tuple from list_tracks is ambiguous: fires both.
        legacy = [PriorCall("music.list_tracks", {},
                            result_entries=[("id", "tr_01")],
                            succeeded=True)]
        r = gate_read_before_write(
            {"name": "music.play", "arguments": {"track_id": "tr_01"}},
            legacy, [])
        self.assertTrue(r.fired)

    def test_podcast_show_episode_station_paths(self):
        eps = [PriorCall("podcast_radio.search", {},
                         result_entries=[("id", "ep_01", "episodes")],
                         succeeded=True)]
        r = gate_read_before_write(
            {"name": "podcast_radio.queue",
             "arguments": {"episode_id": "ep_01"}}, eps, [])
        self.assertFalse(r.fired)
        r = gate_read_before_write(
            {"name": "podcast_radio.subscribe",
             "arguments": {"show_id": "ep_01"}}, eps, [])
        self.assertTrue(r.fired)

    def test_loyalty_nested_reward_path(self):
        nested = [PriorCall("loyalty.get_points", {},
                            result_entries=[("id", "rw_01",
                                             "programs.rewards")],
                            succeeded=True)]
        r = gate_read_before_write(
            {"name": "loyalty.redeem",
             "arguments": {"reward_id": "rw_01"}}, nested, [])
        self.assertFalse(r.fired)
        # The program-level id at the same tool does NOT establish
        # a reward (rewards are nested inside programs).
        program = [PriorCall("loyalty.get_points", {},
                             result_entries=[("id", "rw_01",
                                              "programs")],
                             succeeded=True)]
        r = gate_read_before_write(
            {"name": "loyalty.redeem",
             "arguments": {"reward_id": "rw_01"}}, program, [])
        self.assertTrue(r.fired)
        # Legacy 2-tuple is ambiguous (programs vs rewards): fires.
        legacy = [PriorCall("loyalty.get_points", {},
                            result_entries=[("id", "rw_01")],
                            succeeded=True)]
        r = gate_read_before_write(
            {"name": "loyalty.redeem",
             "arguments": {"reward_id": "rw_01"}}, legacy, [])
        self.assertTrue(r.fired)

    def test_merchant_id_is_field_scoped_not_restaurant_id(self):
        rests = [PriorCall("food_delivery.list_restaurants", {},
                           result_entries=[("id", "rest_01",
                                            "restaurants"),
                                           ("merchant_id", "m_01",
                                            "restaurants")],
                           succeeded=True)]
        r = gate_read_before_write(
            {"name": "ewallet.pay_qr",
             "arguments": {"merchant_id": "m_01"}}, rests, [])
        self.assertFalse(r.fired)
        r = gate_read_before_write(
            {"name": "ewallet.pay_qr",
             "arguments": {"merchant_id": "rest_01"}}, rests, [])
        self.assertTrue(r.fired)

    def test_merchant_id_field_scoped_across_record_types(self):
        # Merchant identity IS the merchant_id field: it rides on
        # restaurant, place, course and program records alike, and
        # no tool validates merchants by lookup, so the field --
        # not the record type -- types the evidence. A plain id
        # from the same records still does not establish a merchant.
        for tool, path in (("food_delivery.list_restaurants",
                            "restaurants"),
                           ("maps.search_place", "places"),
                           ("learning.list_courses", "courses"),
                           ("loyalty.get_points", "programs")):
            r = gate_read_before_write(
                {"name": "ewallet.pay_qr",
                 "arguments": {"merchant_id": "mch_01"}},
                [PriorCall(tool, {},
                           result_entries=[("merchant_id", "mch_01",
                                            path)],
                           succeeded=True)],
                [])
            self.assertFalse(r.fired, tool)
        r = gate_read_before_write(
            {"name": "ewallet.pay_qr",
             "arguments": {"merchant_id": "rest_01"}},
            [PriorCall("food_delivery.list_restaurants", {},
                       result_entries=[("id", "rest_01", "restaurants")],
                       succeeded=True)],
            [])
        self.assertTrue(r.fired)

    def test_tracking_id_dual_key(self):
        # package_tracking._shipment matches by state id OR by
        # tracking_id, so both producer fields establish shipments.
        by_code = [PriorCall("package_tracking.track", {},
                             result_entries=[("tracking_id", "GST001",
                                              "shipments")],
                             succeeded=True)]
        r = gate_read_before_write(
            {"name": "package_tracking.reschedule_delivery",
             "arguments": {"tracking_id": "GST001"}}, by_code, [])
        self.assertFalse(r.fired)
        by_id = [PriorCall("package_tracking.track", {},
                           result_entries=[("id", "shp_01",
                                            "shipments")],
                           succeeded=True)]
        r = gate_read_before_write(
            {"name": "package_tracking.reschedule_delivery",
             "arguments": {"tracking_id": "shp_01"}}, by_id, [])
        self.assertFalse(r.fired)

    def test_unknown_slot_never_establishes(self):
        r = gate_read_before_write(
            {"name": "x.do", "arguments": {"widget_id": "w_01"}},
            [PriorCall("calendar.list_events", {},
                       result_entries=[("id", "w_01", "events")],
                       succeeded=True)],
            [])
        self.assertTrue(r.fired)

    def test_flattener_paths(self):
        from lifemate.lifemate_gates import flatten_result_entries
        entries = flatten_result_entries(
            {"ok": True,
             "devices": [{"id": "fan_bedroom"}],
             "scenes": [{"id": "scene_01"}]})
        self.assertIn(("id", "fan_bedroom", "devices"), entries)
        self.assertIn(("id", "scene_01", "scenes"), entries)
        entries = flatten_result_entries(
            {"programs": [{"id": "prog_01",
                           "rewards": [{"id": "rw_01"}]}]})
        self.assertIn(("id", "prog_01", "programs"), entries)
        self.assertIn(("id", "rw_01", "programs.rewards"), entries)
        entries = flatten_result_entries(
            {"ok": True, "id": "evt_42",
             "item": {"id": "evt_42"}})
        self.assertIn(("id", "evt_42", ""), entries)
        self.assertIn(("id", "evt_42", "item"), entries)
        # Phones are dropped, bools are dropped.
        entries = flatten_result_entries(
            {"contacts": [{"id": "c_05", "phone": "0914000000",
                           "name": "Minh"}],
             "ok": True})
        self.assertNotIn(("phone", "0914000000", "contacts"),
                         entries)
        self.assertIn(("name", "Minh", "contacts"), entries)


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


class TestRound3MainFixes(unittest.TestCase):
    """Main-thread round-3 fixes on top of Thread 1's registry map:
    phone_number references (3-PH), all-slots checking (3-SL),
    patch-verified writes (4-PV), reference-only echo set (4-EO),
    catalog-kind classification (8-V)."""

    def test_phone_number_only_call_is_applicable_and_fires(self):
        # Reviewer 3-PH repro: previously not-applicable (no *_id
        # arg, call/send not a mutate verb) -> passed unconditionally.
        r = gate_read_before_write(
            {"name": "phone.call",
             "arguments": {"phone_number": "0999999999"}}, [], [])
        self.assertTrue(r.applicable)
        self.assertTrue(r.fired)

    def test_phone_number_matches_unique_roster_phone(self):
        roster = [{"id": "c_01", "name": "Minh",
                   "phone": "0914 061 230"}]
        # Digits-normalized: spaced roster phone matches plain arg.
        r = gate_read_before_write(
            {"name": "sms.send",
             "arguments": {"phone_number": "0914061230"}}, [], roster)
        self.assertTrue(r.applicable)
        self.assertFalse(r.fired)

    def test_phone_number_ambiguous_or_unknown_fires(self):
        dup = [{"id": "c_01", "name": "Minh", "phone": "0914061230"},
               {"id": "c_02", "name": "Lan", "phone": "0914061230"}]
        r = gate_read_before_write(
            {"name": "sms.send",
             "arguments": {"phone_number": "0914061230"}}, [], dup)
        self.assertTrue(r.fired)
        # +84 folds to 0: unique match -> passes (control for the
        # normalization, not an ambiguity case).
        r = gate_read_before_write(
            {"name": "sms.send",
             "arguments": {"phone_number": "+84914061230"}},
            [], [{"id": "c_01", "name": "Minh", "phone": "0914061230"}])
        self.assertFalse(r.fired)

    def test_phone_number_from_call_log_passes(self):
        # Callback pattern (round-3 gold finding): a number from a
        # succeeded phone.recent_calls / sms.read_recent result is
        # grounded even with no roster entry (empty books, hotlines).
        priors = [PriorCall(
            "phone.recent_calls", {},
            result_entries=[("phone_number", "09046612750", "calls")],
            succeeded=True)]
        r = gate_read_before_write(
            {"name": "phone.call",
             "arguments": {"phone_number": "09046612750"}},
            priors, [])
        self.assertTrue(r.applicable)
        self.assertFalse(r.fired)

    def test_phone_number_from_write_echo_does_not_pass(self):
        # phone.call / sms.send results echo their own argument;
        # counting them would launder a hallucinated number through
        # its own first use.
        priors = [PriorCall(
            "phone.call", {"phone_number": "09046612750"},
            result_entries=[("phone_number", "09046612750", "call")],
            succeeded=True)]
        r = gate_read_before_write(
            {"name": "phone.call",
             "arguments": {"phone_number": "09046612750"}},
            priors, [])
        self.assertTrue(r.fired)

    def test_all_slots_checked_for_shared_value(self):
        # Reviewer 3-SL: transfer with the same value under two
        # slots mapping to DIFFERENT registries. Accounts evidence
        # alone must NOT pass it (beneficiary registry unestablished);
        # the old first-slot-only code passed it.
        priors = [PriorCall("banking.get_balance", {},
                            result_entries=[("id", "acc_01",
                                             "accounts")],
                            succeeded=True)]
        r = gate_read_before_write(
            {"name": "banking.transfer",
             "arguments": {"from_account_id": "acc_01",
                           "beneficiary_id": "acc_01",
                           "amount": 1000}},
            priors, [])
        self.assertTrue(r.fired)
        # Both registries established -> passes.
        priors2 = priors + [PriorCall(
            "banking.list_beneficiaries", {},
            result_entries=[("id", "acc_01", "beneficiaries")],
            succeeded=True)]
        r = gate_read_before_write(
            {"name": "banking.transfer",
             "arguments": {"from_account_id": "acc_01",
                           "beneficiary_id": "acc_01",
                           "amount": 1000}},
            priors2, [])
        self.assertFalse(r.fired)

    def test_patch_verified_chain_passes_but_delete_does_not(self):
        # Reviewer 4-PV: a succeeded calendar.update_event patch
        # provably looked evt_01 up (App.patch find-or-noop), so a
        # later delete of the same event passes.
        priors = [PriorCall(
            "calendar.update_event", {"event_id": "evt_01"},
            result_entries=[("id", "evt_01", "item")], succeeded=True)]
        r = gate_read_before_write(
            {"name": "calendar.delete_event",
             "arguments": {"event_id": "evt_01"}}, priors, [])
        self.assertFalse(r.fired)
        # A succeeded DELETE returns no item: nothing to establish
        # a later reference (the entity is gone).
        priors_del = [PriorCall(
            "calendar.delete_event", {"event_id": "evt_01"},
            result_entries=[], succeeded=True)]
        r = gate_read_before_write(
            {"name": "calendar.update_event",
             "arguments": {"event_id": "evt_01"}}, priors_del, [])
        self.assertTrue(r.fired)

    def test_echo_set_is_reference_only(self):
        # Reviewer 4-EO mechanism case: a create whose free-text
        # title coincidentally equals its created record id. The
        # title is not a reference, so the result id must count
        # (old code suppressed it because the title was in the
        # all-strings echo set).
        priors = [PriorCall(
            "calendar.create_event", {"title": "evt_99"},
            result_entries=[("id", "evt_99", "item")], succeeded=True)]
        r = gate_read_before_write(
            {"name": "calendar.delete_event",
             "arguments": {"event_id": "evt_99"}}, priors, [])
        self.assertFalse(r.fired)

    def test_catalog_kind_overrides_verb_list(self):
        # Reviewer 8-V: email.read is kind=read in the catalog but
        # fails the verb list ("read" not in READ_VERBS). With a
        # kind map the gate treats it as a read (not applicable);
        # without one it falls back to the verb list.
        call = {"name": "email.read", "arguments": {"email_id": "m_1"}}
        r = gate_read_before_write(call, [], [], {"email.read": "read"})
        self.assertFalse(r.applicable)
        r = gate_read_before_write(call, [], [])
        self.assertTrue(r.applicable)


if __name__ == "__main__":
    unittest.main()
