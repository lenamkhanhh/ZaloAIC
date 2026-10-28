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
        ev = Evidence(
            current_text="dời lịch",
            history_observations=[("calendar.list_events",
                                   "2026-11-10T15:00:00+07:00")],
            anchor=ANCHOR)
        v = prove_argument("start", "2026-11-10T15:00:00+07:00",
                           "calendar.update_event", ev)
        self.assertEqual(v.status, "PROVEN")
        self.assertEqual(v.rule, "observation")
        v = prove_argument("time", "2026-11-10T15:00:00+07:00",
                           "alarm.create", ev)
        self.assertEqual(v.status, "UNPROVEN")
        self.assertEqual(v.rule, "observation_cross_app")

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
        ev = Evidence(current_text="xóa cái sớm nhất giúp tôi",
                      history_observations=["2026-11-14T06:15:00+07:00"],
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

    def test_history_reference_unique_vs_ambiguous(self):
        ev = Evidence(
            current_text="chuyển số tiền cũ cho Minh",
            history_call_args=[("banking.transfer", {"amount": 500000})],
            anchor=ANCHOR)
        v = prove_argument("amount", 500000, "banking.transfer", ev)
        self.assertEqual(v.status, "PROVEN")
        self.assertEqual(v.rule, "history_reference")
        ev2 = Evidence(
            current_text="chuyển số tiền cũ cho Minh",
            history_call_args=[("banking.transfer", {"amount": 500000}),
                               ("banking.transfer", {"amount": 700000})],
            anchor=ANCHOR)
        v = prove_argument("amount", 500000, "banking.transfer", ev2)
        self.assertEqual(v.status, "AMBIGUOUS")

    def test_datetime_assembly(self):
        # Date comes from a history turn, time from the current turn:
        # neither span alone equals the gold datetime, but together they do.
        ev = Evidence(current_text="hẹn lại lúc 9 giờ",
                      history_user_texts=["hôm qua tôi họp với Lan"],
                      anchor=ANCHOR)
        v = prove_argument("time", "2026-11-17T09:00:00+07:00",
                           "calendar.create_event", ev)
        self.assertEqual(v.status, "PROVEN")
        self.assertEqual(v.rule, "datetime_assembly")

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


if __name__ == "__main__":
    unittest.main()
