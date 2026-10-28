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
    call = {"name": "sms.send", "arguments": {"contact_id": "c_05"}}
    r = gate_read_before_write(
        call, [PriorCall("sms.send", {"contact_id": "c_05"},
                         result_scalars=[], succeeded=True)], [])
    print(f"{'PASS' if r.fired else 'FAIL'} F-prior-write-args: "
          f"expected=fired actual_fired={r.fired} :: {r.reason}")
    CASES.append(("F-prior-write-args", "fired",
                  "fired" if r.fired else "passed", r.reason, r.fired))
    # F2: a prior write whose RESULT merely echoes its own id: not proof.
    r = gate_read_before_write(
        call, [PriorCall("sms.send", {"contact_id": "c_05"},
                         result_scalars=["c_05"], succeeded=True)], [])
    print(f"{'PASS' if r.fired else 'FAIL'} F2-echo-result: "
          f"expected=fired actual_fired={r.fired} :: {r.reason}")
    CASES.append(("F2-echo-result", "fired",
                  "fired" if r.fired else "passed", r.reason, r.fired))
    # F3 (control): a prior successful READ result containing the id: pass.
    r = gate_read_before_write(
        call, [PriorCall("contacts.search", {"query": "Minh"},
                         result_scalars=["c_05"], succeeded=True)],
        [{"id": "c_05", "name": "Minh"}])
    print(f"{'PASS' if not r.fired else 'FAIL'} F3-read-result-passes: "
          f"expected=passed actual_fired={r.fired} :: {r.reason}")
    CASES.append(("F3-read-result-passes", "passed",
                  "passed" if not r.fired else "fired", r.reason,
                  not r.fired))
    # F4: a FAILED prior read must not establish.
    r = gate_read_before_write(
        call, [PriorCall("contacts.search", {"query": "Minh"},
                         result_scalars=[], succeeded=False)], [])
    print(f"{'PASS' if r.fired else 'FAIL'} F4-failed-read: "
          f"expected=fired actual_fired={r.fired} :: {r.reason}")
    CASES.append(("F4-failed-read", "fired",
                  "fired" if r.fired else "passed", r.reason, r.fired))

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

    # --- H: adversarial variants.
    # H4: cancellation disables history reference.
    ev = Evidence(
        current_text="thôi khỏi chuyển số tiền cũ",
        history_call_args=[("banking.transfer", {"amount": 500000})],
        anchor=ANCHOR)
    case("H4-cancel-blocks-history", "UNPROVEN", None,
         prove_argument("amount", 500000, "banking.transfer", ev))
    # H5: a correction supersedes a history reference.
    ev = Evidence(
        current_text="chuyển số tiền cũ à không 700000",
        history_call_args=[("banking.transfer", {"amount": 500000})],
        anchor=ANCHOR)
    case("H5-correction-beats-history", "SUPERSEDED", "supersede",
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
