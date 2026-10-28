#!/usr/bin/env python3
"""Reproduce Codex's Round 10 counterexamples (A-G) plus adversarial
variants (H) against the CURRENT lifemate_provenance / lifemate_gates
code, before and after the fix round.

Each case is a minimal synthetic input with an EXPECTED verdict under
the fix-round principles. Run before the fix to record the bug (actual
!= expected); run after the fix to confirm the repair. No data files,
no simulator, no network.

Usage: python3 analysis/repro_codex_counterexamples.py
Exit code 0 iff every case matches its EXPECTED verdict.
"""

import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lifemate"))
from lifemate_provenance import Evidence, prove_argument  # noqa: E402
from lifemate_gates import (  # noqa: E402
    gate_read_before_write, PriorCall)

ANCHOR = datetime(2026, 11, 18, 21, 0, tzinfo=timezone(timedelta(hours=7)))

CASES = []


def case(cid, expected_status, expected_rule_substr, actual):
    ok = actual.status == expected_status and (
        expected_rule_substr is None or expected_rule_substr in actual.rule)
    CASES.append((cid, expected_status, actual.status, actual.rule, ok))
    print(f"{'PASS' if ok else 'FAIL'} {cid}: expected={expected_status} "
          f"actual={actual.status}/{actual.rule} :: {actual.detail}")


def main():
    # --- A: substring of a bigger number must not prove a smaller amount.
    ev = Evidence(current_text="chuyển 1500000 cho Minh", anchor=ANCHOR)
    case("A-substring-number", "UNPROVEN", None,
         prove_argument("amount", 500000, "banking.transfer", ev))
    # --- A2: phone number digits must not prove an amount.
    ev = Evidence(current_text="gọi cho Minh số 0914061230 nhé",
                  anchor=ANCHOR)
    case("A2-phone-number", "UNPROVEN", None,
         prove_argument("amount", 914061230, "banking.transfer", ev))
    # --- A3: digits inside an identifier must not prove an amount.
    ev = Evidence(current_text="mã đơn c_9526 giao rồi", anchor=ANCHOR)
    case("A3-id-digits", "UNPROVEN", None,
         prove_argument("amount", 9526, "banking.transfer", ev))
    # --- A4: substring of a longer contact id must not prove a shorter one.
    ev = Evidence(current_text="nhắn cho c_100 nhé", anchor=ANCHOR,
                  rosters=[{"id": "c_10", "name": "Minh"}])
    case("A4-substring-id", "UNPROVEN", None,
         prove_argument("contact_id", "c_10", "sms.send", ev))

    # --- B: date-only must never become midnight datetime.
    ev = Evidence(current_text="Nhắc tôi sáng mai uống thuốc",
                  anchor=ANCHOR)
    case("B-date-only-midnight", "UNPROVEN", None,
         prove_argument("time", "2026-11-19T00:00:00+07:00",
                        "reminders.create", ev))

    # --- C: another task's time in history must not time a new reminder.
    ev = Evidence(
        current_text="nhắc tôi lại ngày mai nhé",
        history_user_texts=["đi công viên lúc 15 giờ hôm qua"],
        anchor=ANCHOR)
    case("C-cross-text-assembly", "UNPROVEN", None,
         prove_argument("time", "2026-11-19T15:00:00+07:00",
                        "reminders.create", ev))

    # --- D: a balance observation must not prove a transfer amount.
    ev = Evidence(
        current_text="chuyển tiền cho Minh",
        history_observations=[("banking.get_balance",
                               "balance", 500000, None)],
        anchor=ANCHOR)
    case("D-balance-not-amount", "UNPROVEN", None,
         prove_argument("amount", 500000, "banking.transfer", ev))

    # --- E: an unrelated prior alarm call must not base a calendar offset.
    ev = Evidence(
        current_text="dời lịch họp mai muộn hơn nửa tiếng nhé",
        prior_call_args=[("alarm.create",
                          {"time": "2026-11-10T10:00:00+07:00"})],
        anchor=ANCHOR)
    case("E-unrelated-offset-base", "UNPROVEN", None,
         prove_argument(
             "start", "2026-11-10T10:30:00+07:00",
             "calendar.update_event", ev,
             call_args={"event_id": "evt_99",
                        "start": "2026-11-10T10:30:00+07:00"}))

    # --- F: a prior write's args must not establish a contact.
    def gcase(cid, expected_fired, call_, priors, rosters):
        r = gate_read_before_write(call_, priors, rosters)
        ok = r.fired == expected_fired
        CASES.append((cid, "fired" if expected_fired else "passed",
                      "fired" if r.fired else "passed", r.reason, ok))
        print(f"{'PASS' if ok else 'FAIL'} {cid}: "
              f"expected={'fired' if expected_fired else 'passed'} "
              f"actual_fired={r.fired} :: {r.reason}")

    call = {"name": "sms.send", "arguments": {"contact_id": "c_05"}}
    gcase("F-prior-write-args", True, call,
          [PriorCall("sms.send", {"contact_id": "c_05"},
                     result_entries=[], succeeded=True)], [])
    # F2: a prior write whose RESULT merely echoes its own id: not proof.
    gcase("F2-echo-result", True, call,
          [PriorCall("sms.send", {"contact_id": "c_05"},
                     result_entries=[("contact_id", "c_05")],
                     succeeded=True)], [])
    # F3 (control): a prior successful contacts READ result carrying
    # the id field passes -- with NO roster, so the read is really
    # what establishes it.
    gcase("F3-read-result-passes", False, call,
          [PriorCall("contacts.search", {"query": "Minh"},
                     result_entries=[("id", "c_05"), ("name", "Minh")],
                     succeeded=True)], [])
    # F4: a FAILED prior read must not establish.
    gcase("F4-failed-read", True, call,
          [PriorCall("contacts.search", {"query": "Minh"},
                     result_entries=[], succeeded=False)], [])
    # F5 (fix round 2, Codex): a free-text scalar from another tool
    # that merely equals an id proves nothing.
    gcase("F5-flat-string-not-evidence", True,
          {"name": "phone.call", "arguments": {"contact_id": "c_fake"}},
          [PriorCall("calendar.list_events", {},
                     result_entries=[(None, "c_fake")],
                     succeeded=True)], [])
    # F6 (fix round 2, Codex, ride_hailing.get_ride): a succeeded read
    # verifies its input id by lookup -- cancel passes.
    gcase("F6-read-lookup-verifies", False,
          {"name": "ride_hailing.cancel",
           "arguments": {"ride_id": "ride_real"}},
          [PriorCall("ride_hailing.get_ride", {"ride_id": "ride_real"},
                     result_entries=[("id", "ride_real")],
                     succeeded=True)], [])
    # F7: the same read returning noop (unknown id) verifies nothing.
    gcase("F7-noop-read-verifies-nothing", True,
          {"name": "ride_hailing.cancel",
           "arguments": {"ride_id": "ride_real"}},
          [PriorCall("ride_hailing.get_ride", {"ride_id": "ride_real"},
                     result_entries=[], succeeded=False)], [])
    # F8 (CONTRACT CORRECTED in round 3, Thread 1): a succeeded
    # create returning a NEW id establishes ONLY that id's registry.
    # The round-2 form used banking.open_savings' account_id as the
    # "new id"; under registry typing that field is a FOREIGN KEY
    # inside the savings record (and in a real call an echo of
    # from_account_id), not the create's new id -- so it must FIRE,
    # not pass. The true new-id case is calendar.create_event.
    gcase("F8-create-new-id-passes", False,
          {"name": "calendar.update_event",
           "arguments": {"event_id": "evt_42"}},
          [PriorCall("calendar.create_event", {},
                     result_entries=[("id", "evt_42", "")],
                     succeeded=True)], [])
    gcase("F8b-savings-foreign-key-fires", True,
          {"name": "banking.close_account",
           "arguments": {"account_id": "acc_99"}},
          [PriorCall("banking.open_savings", {},
                     result_entries=[("account_id", "acc_99", "savings")],
                     succeeded=True)], [])
    # F9: an id inside a free-text field never establishes.
    gcase("F9-free-text-field-fires", True,
          {"name": "ride_hailing.cancel",
           "arguments": {"ride_id": "ride_real"}},
          [PriorCall("ride_hailing.get_ride", {},
                     result_entries=[("description", "ride_real")],
                     succeeded=True)], [])

    # --- G: gate must check ALL references, not stop at the contact.
    # NOTE: no tool in the real 147-tool catalog takes both a contact
    # reference and another *_id, so this case uses a synthetic schema
    # and is marked as a code-level (not real-schema) finding.
    call = {"name": "x.write",
            "arguments": {"contact_id": "c_05", "event_id": "evt_99"}}
    r = gate_read_before_write(
        call, [], [{"id": "c_05", "name": "Minh"}])
    print(f"{'PASS' if r.fired else 'FAIL'} G-early-return-synthetic: "
          f"expected=fired actual_fired={r.fired} :: {r.reason}")
    CASES.append(("G-early-return-synthetic", "fired",
                  "fired" if r.fired else "passed", r.reason, r.fired))

    # --- R3: round-3 reviewer findings (registry + prover fixes).
    # R3-1B: generic id from any app no longer establishes any *_id.
    gcase("R3-1B-calendar-id-not-ride", True,
          {"name": "ride_hailing.cancel",
           "arguments": {"ride_id": "evt_01"}},
          [PriorCall("calendar.list_events", {},
                     result_entries=[("id", "evt_01", "events")],
                     succeeded=True)], [])
    # R3-1S: smart_home.get_status mixes devices + scenes under "id".
    gcase("R3-1S-scene-id-not-device", True,
          {"name": "smart_home.light_set",
           "arguments": {"device_id": "scn_41"}},
          [PriorCall("smart_home.get_status", {},
                     result_entries=[("id", "scn_41", "scenes")],
                     succeeded=True)], [])
    gcase("R3-1S-device-path-passes", False,
          {"name": "smart_home.light_set",
           "arguments": {"device_id": "dev_01"}},
          [PriorCall("smart_home.get_status", {},
                     result_entries=[("id", "dev_01", "devices")],
                     succeeded=True)], [])
    # R3-2P: spaced phone digits are not amounts.
    ev = Evidence(
        current_text="gọi cho Minh số 0914 061 230 nhé",
        anchor=ANCHOR)
    case("R3-2P-spaced-phone-not-amount", "UNPROVEN", None,
         prove_argument("amount", 914, "banking.transfer", ev,
                        call_args={"contact_id": "c_01", "amount": 914}))
    # R3-2P-boundary (adjacent fix): amounts at text start/end prove.
    ev = Evidence(current_text="chuyển 500000", anchor=ANCHOR)
    case("R3-2P-boundary-amount-proves", "PROVEN", None,
         prove_argument("amount", 500000, "banking.transfer", ev,
                        call_args={"contact_id": "c_01",
                                   "amount": 500000}))
    # R3-2O: offset direction bound to the duration's neighbourhood.
    ev = Evidence(
        current_text="đừng để muộn nhé, dời lịch họp mai "
                     "sớm hơn một tiếng nhé",
        observation_events=[("calendar.list_events",
                             {"id": "evt_01",
                              "start": "2026-11-19T10:00:00+07:00",
                              "end": "2026-11-19T11:00:00+07:00"})],
        anchor=ANCHOR)
    case("R3-2O-nearby-direction-proves", "PROVEN", "offset",
         prove_argument("start", "2026-11-19T09:00:00+07:00",
                        "calendar.update_event", ev,
                        call_args={"event_id": "evt_01",
                                   "start": "2026-11-19T09:00:00+07:00"}))
    case("R3-2O-stray-direction-unproven", "UNPROVEN", None,
         prove_argument("start", "2026-11-19T11:00:00+07:00",
                        "calendar.update_event", ev,
                        call_args={"event_id": "evt_01",
                                   "start": "2026-11-19T11:00:00+07:00"}))
    # R3-2N: entity-less observation never proves an id-linked write.
    ev = Evidence(
        current_text="chuyển tiền cho Minh",
        history_observations=[("banking.get_balance", "amount",
                               500000, None)],
        anchor=ANCHOR)
    case("R3-2N-none-entity-observation", "UNPROVEN", None,
         prove_argument("amount", 500000, "banking.transfer", ev,
                        call_args={"contact_id": "c_01",
                                   "amount": 500000}))
    # R3-3PH: phone_number from the call log passes; unknown fires.
    gcase("R3-3PH-call-log-phone-passes", False,
          {"name": "phone.call",
           "arguments": {"phone_number": "09046612750"}},
          [PriorCall("phone.recent_calls", {},
                     result_entries=[("phone_number", "09046612750",
                                      "calls")],
                     succeeded=True)], [])
    gcase("R3-3PH-unknown-phone-fires", True,
          {"name": "phone.call",
           "arguments": {"phone_number": "0999999999"}}, [], [])
    # R3-3SL: a value under two slots needs BOTH registries.
    gcase("R3-3SL-dual-slot-fires", True,
          {"name": "banking.transfer",
           "arguments": {"from_account_id": "acc_01",
                         "beneficiary_id": "acc_01"}},
          [PriorCall("banking.get_balance", {},
                     result_entries=[("id", "acc_01", "accounts")],
                     succeeded=True)], [])
    # R3-4PV: a succeeded patch looked the entity up, so a later
    # write on the same id passes (chained writes, not echo).
    gcase("R3-4PV-patch-chain-passes", False,
          {"name": "calendar.delete_event",
           "arguments": {"event_id": "evt_99"}},
          [PriorCall("calendar.update_event", {"event_id": "evt_99"},
                     result_entries=[("id", "evt_99", "item")],
                     succeeded=True)], [])
    # R3-4EO: free-text args are not echo evidence -- a create whose
    # title coincidentally equals its new record id still counts
    # as a genuine new id (old code suppressed it because the title
    # was in the all-strings echo set), so the later write passes.
    gcase("R3-4EO-free-text-title-passes", False,
          {"name": "calendar.update_event",
           "arguments": {"event_id": "evt_99"}},
          [PriorCall("calendar.create_event", {"title": "evt_99"},
                     result_entries=[("id", "evt_99", "item")],
                     succeeded=True)], [])
    # R3-6HR: one match among several history candidates is
    # UNPROVEN, not AMBIGUOUS (AMBIGUOUS needs >= 2 supporters).
    ev = Evidence(
        current_text="chuyển số tiền cũ cho Minh",
        history_call_args=[("banking.transfer", {"amount": 500000},
                            True),
                           ("banking.transfer", {"amount": 700000},
                            True)],
        anchor=ANCHOR)
    case("R3-6HR-single-match-unproven", "UNPROVEN", None,
         prove_argument("amount", 500000, "banking.transfer", ev))

    # --- H: adversarial variants.
    # H4: cancellation disables history reference. The history call
    # MUST be succeeded=True: with a 2-tuple (unknown outcome) the
    # case would pass vacuously (no evidence at all) instead of
    # testing the cancel logic.
    ev = Evidence(
        current_text="thôi khỏi chuyển số tiền cũ",
        history_call_args=[("banking.transfer", {"amount": 500000},
                            True)],
        anchor=ANCHOR)
    case("H4-cancel-blocks-history", "UNPROVEN", None,
         prove_argument("amount", 500000, "banking.transfer", ev))
    # H5: a correction supersedes a history reference (succeeded
    # history call, so the supersede machinery is really exercised).
    ev = Evidence(
        current_text="chuyển số tiền cũ à không 700000",
        history_call_args=[("banking.transfer", {"amount": 500000},
                            True)],
        anchor=ANCHOR)
    case("H5-correction-beats-history", "SUPERSEDED", "supersede",
         prove_argument("amount", 500000, "banking.transfer", ev))
    # H5b: unknown outcome is NOT evidence. Same correction text as
    # H5, but the history call is a 2-tuple (outcome unknown): the
    # value must stay UNPROVEN, never SUPERSEDED, because there is
    # nothing proven to supersede.
    ev = Evidence(
        current_text="chuyển số tiền cũ à không 700000",
        history_call_args=[("banking.transfer", {"amount": 500000})],
        anchor=ANCHOR)
    case("H5b-unknown-outcome-no-evidence", "UNPROVEN", None,
         prove_argument("amount", 500000, "banking.transfer", ev))
    # H9: duration needs a PROVEN start, not a hallucinated one.
    event = {"id": "evt_02", "start": "2026-11-10T15:00:00+07:00",
             "end": "2026-11-10T16:00:00+07:00"}
    ev = Evidence(
        current_text="dời lịch đi",
        observation_events=[("calendar.list_events", event)],
        anchor=ANCHOR)
    case("H9-duration-needs-proven-start", "UNPROVEN", None,
         prove_argument(
             "end", "2026-11-10T16:30:00+07:00",
             "calendar.update_event", ev,
             call_args={"event_id": "evt_02",
                        "start": "2026-11-10T15:30:00+07:00",
                        "end": "2026-11-10T16:30:00+07:00"}))
    # H10: another entity's time in the same app must not prove this write.
    ev = Evidence(
        current_text="dời lịch họp",
        observation_events=[
            ("calendar.list_events",
             {"id": "evt_01", "start": "2026-11-10T15:00:00+07:00",
              "end": "2026-11-10T16:00:00+07:00"}),
            ("calendar.list_events",
             {"id": "evt_02", "start": "2026-11-10T16:00:00+07:00",
              "end": "2026-11-10T17:00:00+07:00"})],
        anchor=ANCHOR)
    case("H10-other-entity-time", "UNPROVEN", None,
         prove_argument(
             "start", "2026-11-10T16:00:00+07:00",
             "calendar.update_event", ev,
             call_args={"event_id": "evt_01",
                        "start": "2026-11-10T16:00:00+07:00"}))

    failed = [c for c in CASES if not c[4]]
    print(f"\n{len(CASES) - len(failed)}/{len(CASES)} cases match expected.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
