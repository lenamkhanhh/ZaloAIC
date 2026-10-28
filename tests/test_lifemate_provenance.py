"""Unit + integration tests for lifemate_provenance (Round 10).

Loads the module by file path (same pattern as test_lifemate_grounding.py)
so the tests run with plain python3 and with /tmp/rfvenv/bin/python.
No data files, no simulator, no network: all evidence is synthetic.
"""

import sys
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lifemate"))
from lifemate_provenance import (  # noqa: E402
    parse_number_words, find_number_spans, parse_relative_datetime,
    find_datetime_spans, split_correction_segments, Evidence, Verdict,
    prove_argument, prove_call)

ANCHOR = datetime(2026, 11, 18, 21, 0,
                  tzinfo=timezone(timedelta(hours=7)))


class TestNumberWords(unittest.TestCase):
    def test_groups(self):
        self.assertEqual(parse_number_words("hai triệu tám trăm nghìn"),
                         2800000)
        self.assertEqual(parse_number_words("một tỷ hai trăm triệu"),
                         1200000000)
        self.assertEqual(parse_number_words("hai mươi ba nghìn năm trăm"),
                         23500)
        self.assertEqual(parse_number_words("một trăm năm mươi nghìn"),
                         150000)
        self.assertEqual(parse_number_words("một nghìn"), 1000)
        self.assertEqual(parse_number_words("mười nghìn"), 10000)
        self.assertEqual(parse_number_words("chục nghìn"), 10000)

    def test_double_scaling_regression(self):
        # The Round 7 bug: naive suffix stripping gave 2,000,800,000.
        self.assertEqual(parse_number_words("hai triệu tám trăm nghìn"),
                         2800000)
        self.assertNotEqual(parse_number_words("hai triệu tám trăm nghìn"),
                            2000800000)
        # Currency words are NOT number tokens: the span finder strips
        # them before calling the parser, so the raw parser rejects them.
        self.assertIsNone(
            parse_number_words("hai triệu tám trăm nghìn đồng"))

    def test_ruoi_nua(self):
        self.assertEqual(parse_number_words("hai triệu rưỡi"), 2500000)
        self.assertEqual(parse_number_words("năm rưỡi"), 5.5)
        self.assertEqual(parse_number_words("một trăm rưỡi"), 150)
        self.assertEqual(parse_number_words("một nghìn năm trăm rưỡi"), 1550)
        self.assertEqual(parse_number_words("nửa triệu"), 500000)
        self.assertEqual(parse_number_words("một nửa"), 0.5)

    def test_variants(self):
        self.assertEqual(parse_number_words("mười lăm"), 15)
        self.assertEqual(parse_number_words("hai mươi mốt"), 21)
        self.assertEqual(parse_number_words("hai mươi tư"), 24)
        self.assertEqual(parse_number_words("một trăm lẻ năm"), 105)
        self.assertEqual(parse_number_words("năm chục"), 50)
        self.assertEqual(parse_number_words("một chục"), 10)

    def test_kem(self):
        self.assertEqual(parse_number_words("mười kém năm"), 5)
        self.assertEqual(parse_number_words("mười nghìn kém năm trăm"), 9500)

    def test_rejects(self):
        for bad in ["", "tỷ", "một triệu một triệu", "một nghìn một triệu",
                    "xyz", "một con mèo", "không", "tư", "nghìn",
                    "một trăm rưỡi rưỡi", "nửa triệu rưỡi", "mười kém",
                    "kém năm", "trăm", "mươi"]:
            self.assertIsNone(parse_number_words(bad), bad)

    def test_digit_forms_in_spans(self):
        spans = dict(find_number_spans("chuyển 1.500.000 và 50k cho Minh"))
        self.assertIn(1500000, spans.values())
        self.assertIn(50000, spans.values())
        spans = dict(find_number_spans("gửi 1,5 triệu nhé"))
        self.assertIn(1500000, spans.values())
        spans = dict(find_number_spans("nạp 50 nghìn tiền điện thoại"))
        self.assertIn(50000, spans.values())
        spans = dict(find_number_spans("chuyển 5 trăm nghìn nhé"))
        self.assertIn(500000, spans.values())
        # ISO dates must not be mistaken for numbers.
        spans = find_number_spans("ngày 2026-11-14")
        self.assertEqual([v for _, v in spans], [])
        # Fix round: phone numbers and identifier digits are not amounts.
        spans = find_number_spans("gọi cho Minh số 0914061230 nhé")
        self.assertNotIn(914061230, [v for _, v in spans])
        spans = find_number_spans("mã đơn c_9526 giao rồi")
        self.assertNotIn(9526, [v for _, v in spans])


class TestRelativeDate(unittest.TestCase):
    def _dt(self, span):
        r = parse_relative_datetime(ANCHOR, span)
        self.assertIsNotNone(r, span)
        return r

    def test_day_offsets(self):
        self.assertEqual(self._dt("ngày mai").value.strftime("%Y-%m-%d"),
                         "2026-11-19")
        self.assertEqual(self._dt("3 ngày nữa").value.strftime("%Y-%m-%d"),
                         "2026-11-21")
        self.assertEqual(self._dt("hôm qua").value.strftime("%Y-%m-%d"),
                         "2026-11-17")
        self.assertEqual(self._dt("sáng mai").value.strftime("%Y-%m-%d"),
                         "2026-11-19")
        self.assertTrue(self._dt("sáng mai").hour_missing)

    def test_combined(self):
        r = self._dt("ngày mai lúc 8 giờ")
        self.assertEqual(r.value.strftime("%Y-%m-%dT%H:%M"), "2026-11-19T08:00")
        r = self._dt("thứ 2 tuần sau 10 rưỡi sáng")
        self.assertEqual(r.value.strftime("%Y-%m-%dT%H:%M"), "2026-11-23T10:30")
        r = self._dt("10 giờ kém 10")
        self.assertEqual(r.value.strftime("%H:%M"), "09:50")
        r = self._dt("3 giờ chiều")
        self.assertEqual(r.value.strftime("%H:%M"), "15:00")
        r = self._dt("12 giờ trưa")
        self.assertEqual(r.value.strftime("%H:%M"), "12:00")

    def test_weekday_words_and_word_dates(self):
        # Anchor is Wednesday 2026-11-18: next Saturday is 11-21.
        r = self._dt("năm giờ chiều thứ bảy này")
        self.assertEqual(r.value.strftime("%Y-%m-%dT%H:%M"), "2026-11-21T17:00")
        r = self._dt("thứ ba tuần sau")
        self.assertEqual(r.value.strftime("%Y-%m-%d"), "2026-11-24")
        r = self._dt("ba giờ chiều hôm hai mươi hai tháng mười")
        self.assertEqual(r.value.strftime("%Y-%m-%dT%H:%M"), "2026-10-22T15:00")
        r = self._dt("mười giờ sáng ngày mười bảy tháng mười")
        self.assertEqual(r.value.strftime("%Y-%m-%dT%H:%M"), "2026-10-17T10:00")

    def test_daypart_after_hour(self):
        # "bốn giờ chiều": the daypart follows the hour and must adjust it
        # to 16:00 (not 04:00); "mai" supplies the date via assembly.
        spans = find_datetime_spans("hẹn bốn giờ chiều mai đi", ANCHOR)
        times = [p.value.strftime("%H:%M") for _, p in spans
                 if p.kind in ("time", "datetime") and p.value]
        self.assertIn("16:00", times)
        self.assertNotIn("04:00", times)
        ev = Evidence(current_text="hẹn bốn giờ chiều mai đi", anchor=ANCHOR)
        v = prove_argument("time", "2026-11-19T16:00:00+07:00",
                           "package_tracking.reschedule_delivery", ev)
        self.assertEqual(v.status, "PROVEN")

    def test_week_month_only_never_a_day(self):
        r = self._dt("tuần sau")
        self.assertEqual(r.kind, "week_only")
        self.assertIsNone(r.value)
        r = self._dt("tháng sau")
        self.assertEqual(r.kind, "month_only")

    def test_daypart_only_is_date_only(self):
        r = self._dt("ngày mai sáng")
        self.assertEqual(r.kind, "date")
        self.assertTrue(r.hour_missing)

    def test_span_extension(self):
        spans = find_datetime_spans("nhắc tôi ngày mai lúc 8 giờ", ANCHOR)
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0][1].kind, "datetime")

    def test_anchor_is_never_invented(self):
        # No anchor -> no parse, even for "ngày mai".
        self.assertIsNone(parse_relative_datetime(None, "ngày mai"))
        self.assertIsNone(parse_relative_datetime("not-a-date", "ngày mai"))


class TestSupersede(unittest.TestCase):
    def test_segments(self):
        segs = split_correction_segments("nhắc tôi 9 giờ — à không, 10 giờ")
        self.assertEqual(len(segs), 2)
        self.assertIn("10 giờ", segs[-1])
        self.assertEqual(split_correction_segments("nhắc tôi 10 giờ"),
                         ["nhắc tôi 10 giờ"])

    def test_latest_wins(self):
        ev = Evidence(current_text="nhắc tôi 9 giờ — à không, 10 giờ",
                      anchor=ANCHOR)
        v = prove_argument("time", "2026-11-18T10:00:00+07:00",
                           "reminders.create", ev)
        self.assertEqual(v.status, "PROVEN")
        self.assertEqual(v.rule, "supersede")
        v = prove_argument("time", "2026-11-18T09:00:00+07:00",
                           "reminders.create", ev)
        self.assertEqual(v.status, "SUPERSEDED")


class TestProver(unittest.TestCase):
    def test_verbatim_and_words(self):
        ev = Evidence(current_text="chuyển hai triệu tám trăm nghìn cho Minh",
                      anchor=ANCHOR)
        v = prove_argument("amount", 2800000, "banking.transfer", ev)
        self.assertEqual(v.status, "PROVEN")
        self.assertEqual(v.rule, "number_words")
        v = prove_argument("amount", 999999, "banking.transfer", ev)
        self.assertEqual(v.status, "UNPROVEN")

    def test_relative_date_proves(self):
        ev = Evidence(current_text="nhắc tôi ngày mai lúc 8 giờ uống thuốc",
                      anchor=ANCHOR)
        v = prove_argument("time", "2026-11-19T08:00:00+07:00",
                           "reminders.create", ev)
        self.assertEqual(v.status, "PROVEN")
        self.assertEqual(v.rule, "relative_date")

    def test_time_only_gold(self):
        ev = Evidence(current_text="báo thức 7 giờ sáng", anchor=ANCHOR)
        v = prove_argument("time", "07:00", "alarm.create", ev)
        self.assertEqual(v.status, "PROVEN")

    def test_observation_same_app_vs_cross_app(self):
        # Same-app observation proves; cross-app is UNPROVEN (flagged).
        # Observations are (tool, field, value, entity) quadruples.
        ev = Evidence(
            current_text="dời lịch",
            turn_observations=[("calendar.list_events", "start",
                                "2026-11-10T15:00:00+07:00", "evt_02")],
            anchor=ANCHOR)
        v = prove_argument("start", "2026-11-10T15:00:00+07:00",
                           "calendar.update_event", ev,
                           call_args={"event_id": "evt_02"})
        self.assertEqual(v.status, "PROVEN")
        self.assertEqual(v.rule, "observation")
        v = prove_argument("time", "2026-11-10T15:00:00+07:00",
                           "alarm.create", ev)
        self.assertEqual(v.status, "UNPROVEN")
        self.assertEqual(v.rule, "observation_cross_app")

    def test_observation_field_must_match_slot(self):
        # Fix round D: a balance field never proves an amount.
        ev = Evidence(
            current_text="chuyển tiền cho Minh",
            turn_observations=[("banking.get_balance", "balance",
                                500000, None)],
            anchor=ANCHOR)
        v = prove_argument("amount", 500000, "banking.transfer", ev)
        self.assertEqual(v.status, "UNPROVEN")
        ev2 = Evidence(
            current_text="chuyển tiền cho Minh",
            turn_observations=[("banking.get_balance", "amount",
                                500000, None)],
            anchor=ANCHOR)
        v = prove_argument("amount", 500000, "banking.transfer", ev2)
        self.assertEqual(v.status, "PROVEN")

    def test_observation_untyped_entries_never_prove(self):
        # Legacy (tool, scalar) pairs and plain scalars carry no field
        # (and plain scalars no app): UNKNOWN source, never PROVEN.
        ev = Evidence(
            current_text="dời lịch",
            turn_observations=[("calendar.list_events",
                                "2026-11-10T15:00:00+07:00")],
            anchor=ANCHOR)
        v = prove_argument("start", "2026-11-10T15:00:00+07:00",
                           "calendar.update_event", ev,
                           call_args={"event_id": "evt_02"})
        self.assertEqual(v.status, "UNPROVEN")
        ev2 = Evidence(
            current_text="dời lịch",
            turn_observations=["2026-11-10T15:00:00+07:00"],
            anchor=ANCHOR)
        v = prove_argument("start", "2026-11-10T15:00:00+07:00",
                           "calendar.update_event", ev2,
                           call_args={"event_id": "evt_02"})
        self.assertEqual(v.status, "UNPROVEN")

    def test_offset_and_duration(self):
        # "dời muộn hơn nửa tiếng": obs event 15:00-16:00 -> 15:30-16:30.
        event = {"id": "evt_02", "start": "2026-11-10T15:00:00+07:00",
                 "end": "2026-11-10T16:00:00+07:00"}
        ev = Evidence(
            current_text="dời lịch cà phê mai muộn hơn nửa tiếng nhé",
            observation_events=[("calendar.list_events", event)],
            anchor=ANCHOR)
        call_args = {"event_id": "evt_02",
                     "start": "2026-11-10T15:30:00+07:00",
                     "end": "2026-11-10T16:30:00+07:00"}
        v = prove_argument("start", "2026-11-10T15:30:00+07:00",
                           "calendar.update_event", ev, call_args=call_args)
        self.assertEqual(v.status, "PROVEN")
        self.assertEqual(v.rule, "offset")
        v = prove_argument("end", "2026-11-10T16:30:00+07:00",
                           "calendar.update_event", ev, call_args=call_args)
        self.assertEqual(v.status, "PROVEN")
        self.assertIn(v.rule, ("offset", "duration"))
        # Without the id link, the offset rule must not fire.
        ev2 = Evidence(
            current_text="dời lịch cà phê mai muộn hơn nửa tiếng nhé",
            observation_events=[("calendar.list_events", event)],
            anchor=ANCHOR)
        v = prove_argument("start", "2026-11-10T15:30:00+07:00",
                           "calendar.update_event", ev2, call_args={})
        self.assertEqual(v.status, "UNPROVEN")
        ev = Evidence(current_text="xóa cái sớm nhất của Minh giúp tôi",
                      turn_observations=[("alarm.list_alarms", "time",
                                          "2026-11-14T06:15:00+07:00",
                                          None)],
                      rosters=[{"id": "c_05", "name": "Minh"}],
                      anchor=ANCHOR)
        v = prove_argument("time", "2026-11-14T06:15:00+07:00",
                           "alarm.delete", ev)
        self.assertEqual(v.status, "PROVEN")
        self.assertEqual(v.rule, "observation")
        v = prove_argument("contact_id", "c_05", "sms.send", ev)
        self.assertEqual(v.status, "PROVEN")
        self.assertEqual(v.rule, "roster")
        v = prove_argument("contact_id", "c_99", "sms.send", ev)
        self.assertEqual(v.status, "UNPROVEN")
        # Roster without an exclusive mention proves existence only.
        ev2 = Evidence(current_text="xóa cái sớm nhất giúp tôi",
                       rosters=[{"id": "c_05", "name": "Minh"}],
                       anchor=ANCHOR)
        v = prove_argument("contact_id", "c_05", "sms.send", ev2)
        self.assertEqual(v.status, "UNPROVEN")
        self.assertEqual(v.rule, "roster_no_intent")

    def test_history_reference_unique_vs_ambiguous(self):
        # Succeeded history calls only: legacy 2-tuples (unknown
        # outcome) do not prove.
        ev = Evidence(
            current_text="chuyển số tiền cũ cho Minh",
            history_call_args=[("banking.transfer", {"amount": 500000},
                                True)],
            anchor=ANCHOR)
        v = prove_argument("amount", 500000, "banking.transfer", ev)
        self.assertEqual(v.status, "PROVEN")
        self.assertEqual(v.rule, "history_reference")
        # Contract change (reviewer finding 6-HR, round 3):
        # AMBIGUOUS now requires >= 2 MATCHING candidates. A single
        # match among several candidates does NOT uniquely resolve
        # the reference ("số tiền cũ" could mean the other amount),
        # so it falls through to UNPROVEN -- the guard action is
        # unchanged (both verdicts block), only the label is now
        # strict: AMBIGUOUS means ">= 2 supporters, can't choose",
        # never "no supporter at all".
        ev2 = Evidence(
            current_text="chuyển số tiền cũ cho Minh",
            history_call_args=[("banking.transfer", {"amount": 500000},
                                True),
                               ("banking.transfer", {"amount": 700000},
                                True)],
            anchor=ANCHOR)
        v = prove_argument("amount", 500000, "banking.transfer", ev2)
        self.assertEqual(v.status, "UNPROVEN")
        # Two candidates both matching the value -> AMBIGUOUS.
        # (For time values the matcher compares HH:MM, so two full
        # datetimes with the same clock time but different dates
        # both match a time-only value.)
        ev2b = Evidence(
            current_text="dời sang giờ cũ nhé",
            history_call_args=[("calendar.update_event",
                                {"start": "2026-11-19T10:00:00+07:00"},
                                True),
                               ("calendar.update_event",
                                {"start": "2026-11-18T10:00:00+07:00"},
                                True)],
            anchor=ANCHOR)
        v = prove_argument("start", "10:00", "calendar.update_event",
                           ev2b)
        self.assertEqual(v.status, "AMBIGUOUS")
        # No candidate matches -> UNPROVEN, not AMBIGUOUS.
        ev2c = Evidence(
            current_text="chuyển số tiền cũ cho Minh",
            history_call_args=[("banking.transfer", {"amount": 700000},
                                True),
                               ("banking.transfer", {"amount": 900000},
                                True)],
            anchor=ANCHOR)
        v = prove_argument("amount", 500000, "banking.transfer", ev2c)
        self.assertEqual(v.status, "UNPROVEN")
        ev3 = Evidence(
            current_text="chuyển số tiền cũ cho Minh",
            history_call_args=[("banking.transfer", {"amount": 500000})],
            anchor=ANCHOR)
        v = prove_argument("amount", 500000, "banking.transfer", ev3)
        self.assertEqual(v.status, "UNPROVEN")

    def test_datetime_assembly(self):
        # Same current text, exactly one date span + one time span.
        ev = Evidence(current_text="hẹn bốn giờ chiều mai đi",
                      anchor=ANCHOR)
        v = prove_argument("time", "2026-11-19T16:00:00+07:00",
                           "reminders.create", ev)
        self.assertEqual(v.status, "PROVEN")
        self.assertEqual(v.rule, "datetime_assembly")
        # Fix round C: a bare "lại" no longer pairs a current date word
        # with an unrelated history time.
        ev = Evidence(
            current_text="nhắc tôi lại ngày mai nhé",
            history_user_texts=["đi công viên lúc 15 giờ hôm qua"],
            anchor=ANCHOR)
        v = prove_argument("time", "2026-11-19T15:00:00+07:00",
                           "reminders.create", ev)
        self.assertEqual(v.status, "UNPROVEN")

    def test_default_only_when_declared(self):
        ev = Evidence(current_text="nhắc tôi uống thuốc", anchor=ANCHOR,
                      defaults={})
        v = prove_argument("time", "2026-11-18T08:00:00+07:00",
                           "reminders.create", ev)
        self.assertEqual(v.status, "UNPROVEN")
        ev2 = Evidence(current_text="nhắc tôi uống thuốc", anchor=ANCHOR,
                       defaults={"time": "2026-11-18T08:00:00+07:00"})
        v = prove_argument("time", "2026-11-18T08:00:00+07:00",
                           "reminders.create", ev2)
        self.assertEqual(v.status, "PROVEN")
        self.assertEqual(v.rule, "default")

    def test_prove_call_monitors_only_monitored_slots(self):
        ev = Evidence(current_text="chuyển 500000 cho Minh", anchor=ANCHOR)
        out = prove_call({"name": "banking.transfer",
                          "arguments": {"amount": 500000,
                                        "contact_id": "c_05",
                                        "note": "tiền nhà"}},
                         ev)
        self.assertIn("amount", out)
        self.assertIn("contact_id", out)
        self.assertNotIn("note", out)

    def test_verbatim_baseline_subset(self):
        # The verbatim-only baseline must never prove what full DAG proves
        # via derivation rules.
        ev = Evidence(current_text="chuyển hai triệu cho Minh", anchor=ANCHOR)
        base = prove_argument("amount", 2000000, "banking.transfer", ev,
                              rules=["verbatim", "observation", "roster"])
        self.assertEqual(base.status, "UNPROVEN")
        full = prove_argument("amount", 2000000, "banking.transfer", ev)
        self.assertEqual(full.status, "PROVEN")


class TestFixRoundRegressions(unittest.TestCase):
    """Codex counterexamples A-H: each must stay UNPROVEN/SUPERSEDED."""

    def test_a_substring_number(self):
        ev = Evidence(current_text="chuyển 1500000 cho Minh",
                      anchor=ANCHOR)
        v = prove_argument("amount", 500000, "banking.transfer", ev)
        self.assertEqual(v.status, "UNPROVEN")

    def test_a2_phone_number(self):
        ev = Evidence(current_text="gọi cho Minh số 0914061230 nhé",
                      anchor=ANCHOR)
        v = prove_argument("amount", 914061230, "banking.transfer", ev)
        self.assertEqual(v.status, "UNPROVEN")

    def test_a3_identifier_digits(self):
        ev = Evidence(current_text="mã đơn c_9526 giao rồi",
                      anchor=ANCHOR)
        v = prove_argument("amount", 9526, "banking.transfer", ev)
        self.assertEqual(v.status, "UNPROVEN")

    def test_a4_substring_id(self):
        ev = Evidence(
            current_text="nhắn cho c_100 nhé",
            rosters=[{"id": "c_10", "name": "Minh"}],
            anchor=ANCHOR)
        v = prove_argument("contact_id", "c_10", "sms.send", ev)
        self.assertEqual(v.status, "UNPROVEN")

    def test_b_date_only_never_midnight(self):
        ev = Evidence(current_text="Nhắc tôi sáng mai uống thuốc",
                      anchor=ANCHOR)
        v = prove_argument("time", "2026-11-19T00:00:00+07:00",
                           "reminders.create", ev)
        self.assertEqual(v.status, "UNPROVEN")

    def test_d_balance_field(self):
        ev = Evidence(
            current_text="chuyển tiền cho Minh",
            turn_observations=[("banking.get_balance", "balance",
                                500000, None)],
            anchor=ANCHOR)
        v = prove_argument("amount", 500000, "banking.transfer", ev)
        self.assertEqual(v.status, "UNPROVEN")

    def test_e_unrelated_prior_call_offset(self):
        ev = Evidence(
            current_text="dời lịch họp mai muộn hơn nửa tiếng nhé",
            prior_call_args=[("alarm.create",
                              {"time": "2026-11-18T10:00:00+07:00"},
                              True)],
            anchor=ANCHOR)
        v = prove_argument("start", "2026-11-18T10:30:00+07:00",
                           "calendar.update_event", ev,
                           call_args={"event_id": "evt_99"})
        self.assertEqual(v.status, "UNPROVEN")

    def test_h4_cancel_blocks_history(self):
        ev = Evidence(
            current_text="thôi khỏi chuyển số tiền cũ",
            history_call_args=[("banking.transfer", {"amount": 500000},
                                True)],
            anchor=ANCHOR)
        v = prove_argument("amount", 500000, "banking.transfer", ev)
        self.assertEqual(v.status, "UNPROVEN")

    def test_h5_corrected_history_reference(self):
        ev = Evidence(
            current_text="chuyển số tiền cũ à không 700000",
            history_call_args=[("banking.transfer", {"amount": 500000},
                                True)],
            anchor=ANCHOR)
        v = prove_argument("amount", 500000, "banking.transfer", ev)
        self.assertEqual(v.status, "SUPERSEDED")

    def test_h9_duration_needs_proven_start(self):
        event = {"id": "evt_02", "start": "2026-11-10T15:00:00+07:00",
                 "end": "2026-11-10T16:00:00+07:00"}
        ev = Evidence(
            current_text="dời lịch đi",
            observation_events=[("calendar.list_events", event)],
            anchor=ANCHOR)
        v = prove_argument("end", "2026-11-10T16:30:00+07:00",
                           "calendar.update_event", ev,
                           call_args={"event_id": "evt_02",
                                      "start": "2026-11-10T15:30:00+07:00"})
        self.assertEqual(v.status, "UNPROVEN")

    def test_h10_other_entity_time(self):
        ev = Evidence(
            current_text="dời lịch đi",
            turn_observations=[("calendar.list_events", "start",
                                "2026-11-10T16:00:00+07:00", "evt_02")],
            anchor=ANCHOR)
        v = prove_argument("start", "2026-11-10T16:00:00+07:00",
                           "calendar.update_event", ev,
                           call_args={"event_id": "evt_01"})
        self.assertEqual(v.status, "UNPROVEN")

    def test_roster_duplicate_name_ambiguous(self):
        ev = Evidence(
            current_text="nhắn cho Minh nhé",
            rosters=[{"id": "c_05", "name": "Minh"},
                     {"id": "c_09", "name": "Minh"}],
            anchor=ANCHOR)
        v = prove_argument("contact_id", "c_05", "sms.send", ev)
        self.assertEqual(v.status, "AMBIGUOUS")

    def test_proposal_contact_name_is_not_intent(self):
        # Fix round 2: a model-invented contact_name must not prove
        # the user chose that person. Intent comes from user text only.
        ev = Evidence(
            current_text="nhắn cho anh ấy nhé",
            rosters=[{"id": "c_05", "name": "Minh"}],
            anchor=ANCHOR)
        v = prove_argument("contact_id", "c_05", "sms.send", ev,
                           call_args={"contact_name": "Minh"})
        self.assertEqual(v.status, "UNPROVEN")
class TestRound3ProverFixes(unittest.TestCase):
    """Main-thread round-3 prover fixes: spaced-phone spans (2-P),
    boundary amounts, offset direction proximity (2-O),
    None-entity observations (2-N)."""

    def test_spaced_phone_groups_are_not_amounts(self):
        self.assertEqual(
            find_number_spans("gọi cho Minh số 0914 061 230 nhé"), [])
        self.assertEqual(
            find_number_spans("gọi 0914-061-230 nhé"), [])
        ev = Evidence(
            current_text="gọi cho Minh số 0914 061 230 nhé",
            anchor=ANCHOR)
        for amount in (914, 61, 230):
            v = prove_argument("amount", amount, "banking.transfer", ev,
                               call_args={"contact_id": "c_01",
                                          "amount": amount})
            self.assertEqual(v.status, "UNPROVEN")
        # A real amount in the same text still proves.
        ev2 = Evidence(
            current_text="gọi 0914 061 230 chuyển 500000 nhé",
            anchor=ANCHOR)
        v = prove_argument("amount", 500000, "banking.transfer", ev2,
                           call_args={"contact_id": "c_01",
                                      "amount": 500000})
        self.assertEqual(v.status, "PROVEN")

    def test_amount_at_text_boundaries_proves(self):
        # Adjacent-fix found during 2-P: "" in "-:" is True, so the
        # old date/time filter dropped amounts at start/end of
        # text (verified against frozen 3838d99f).
        self.assertEqual(find_number_spans("chuyển 500000"),
                         [("500000", 500000)])
        self.assertEqual(find_number_spans("500000 là số tiền"),
                         [("500000", 500000)])

    def test_offset_direction_bound_by_proximity(self):
        # Reviewer 2-O repro: stray "muộn" far from the duration
        # must not prove the +1 direction; only the nearby "sớm"
        # proves -1.
        ev = Evidence(
            current_text="đừng để muộn nhé, dời lịch họp mai "
                         "sớm hơn một tiếng nhé",
            observation_events=[("calendar.list_events",
                                 {"id": "evt_01",
                                  "start": "2026-11-19T10:00:00+07:00",
                                  "end": "2026-11-19T11:00:00+07:00"})],
            anchor=ANCHOR)
        v = prove_argument("start", "2026-11-19T09:00:00+07:00",
                           "calendar.update_event", ev,
                           call_args={"event_id": "evt_01",
                                      "start": "2026-11-19T09:00:00+07:00"})
        self.assertEqual(v.status, "PROVEN")
        self.assertEqual(v.rule, "offset")
        v = prove_argument("start", "2026-11-19T11:00:00+07:00",
                           "calendar.update_event", ev,
                           call_args={"event_id": "evt_01",
                                      "start": "2026-11-19T11:00:00+07:00"})
        self.assertEqual(v.status, "UNPROVEN")

    def test_none_entity_observation_does_not_prove_id_linked(self):
        # Reviewer 2-N: a history observation with no entity must
        # not prove an id-linked write, even when unique.
        ev = Evidence(
            current_text="chuyển tiền cho Minh",
            history_observations=[("banking.get_balance", "amount",
                                   500000, None)],
            anchor=ANCHOR)
        v = prove_argument("amount", 500000, "banking.transfer", ev,
                           call_args={"contact_id": "c_01",
                                      "amount": 500000})
        self.assertEqual(v.status, "UNPROVEN")
        # Control: the same value WITH the entity link proves.
        ev2 = Evidence(
            current_text="chuyển tiền cho Minh",
            history_observations=[("banking.get_balance", "amount",
                                   500000, "c_01")],
            anchor=ANCHOR)
        v = prove_argument("amount", 500000, "banking.transfer", ev2,
                           call_args={"contact_id": "c_01",
                                      "amount": 500000})
        self.assertEqual(v.status, "PROVEN")


if __name__ == "__main__":
    unittest.main()
