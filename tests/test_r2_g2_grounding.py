"""R2-G2 grounding tests (Run 2, LifeMate only, CPU only).

Synthetic cases only; no dataset ids, names, or amounts are hardcoded
as fixtures. Covers the three evidenced gaps fixed in this round:
phone values read in groups / spoken digits, word-number relative
dates, and word hours -- plus the guard that an incomplete phone is
never completed from a roster and that recognizing a number does not
authorize an action (ground_tool_call only normalizes the value).
"""
import unittest
from datetime import datetime

from lifemate.lifemate_grounding import (
    NumberMoneyParser,
    RelativeDateResolver,
    ground_tool_call,
    normalize_phone,
)

ANCHOR = datetime(2026, 10, 30, 9, 0)


class TestPhoneNormalization(unittest.TestCase):
    def test_spoken_digits(self):
        r = normalize_phone("không chín không ba một một một hai hai hai")
        self.assertEqual(r.kind, "full")
        self.assertEqual(r.value, "0903111222")

    def test_grouped_digits(self):
        for raw in ("0903 111 222", "0903-111-222", "0903.111.222"):
            self.assertEqual(normalize_phone(raw).value, "0903111222")

    def test_country_prefix_folded(self):
        self.assertEqual(normalize_phone("+84 903 111 222").value, "0903111222")

    def test_tail_is_incomplete_not_guessed(self):
        r = normalize_phone("đuôi 222")
        self.assertEqual(r.kind, "incomplete")
        self.assertIsNone(r.value)

    def test_short_and_no_zero_are_incomplete(self):
        self.assertEqual(normalize_phone("0903 111").kind, "incomplete")
        self.assertEqual(normalize_phone("903 111 222").kind, "incomplete")

    def test_no_digits_is_none(self):
        self.assertEqual(normalize_phone("không có số").kind, "none")

    def test_ground_tool_call_phone(self):
        r = ground_tool_call(
            {"name": "phone.call", "arguments": {"phone_number": "0903 111 222"}})
        self.assertEqual(r.status, "GROUNDED")
        self.assertEqual(r.call["arguments"]["phone_number"], "0903111222")
        r = ground_tool_call(
            {"name": "phone.call", "arguments": {"phone_number": "đuôi 222"}})
        self.assertEqual(r.status, "NEEDS_ASK")
        # Value left untouched: normalization never invents a number.
        self.assertEqual(r.call["arguments"]["phone_number"], "đuôi 222")


class TestWordDatesAndHours(unittest.TestCase):
    def test_word_day_offsets(self):
        res = RelativeDateResolver(ANCHOR)
        self.assertEqual(str(res.resolve("hai ngày nữa").date), "2026-11-01")
        self.assertEqual(str(res.resolve("ba ngày trước").date), "2026-10-27")
        self.assertEqual(
            str(res.resolve("hai mươi lăm ngày nữa").date), "2026-11-24")

    def test_word_hours(self):
        r = ground_tool_call(
            {"name": "tasks.create", "arguments": {"time": "ngày mai lúc tám giờ"}},
            {"current_time": ANCHOR})
        self.assertEqual(r.call["arguments"]["time"], "2026-10-31T08:00:00")
        r = ground_tool_call(
            {"name": "tasks.create",
             "arguments": {"time": "ngày mai lúc tám giờ rưỡi"}},
            {"current_time": ANCHOR})
        self.assertEqual(r.call["arguments"]["time"], "2026-10-31T08:30:00")
        r = ground_tool_call(
            {"name": "tasks.create",
             "arguments": {"time": "ngày mai lúc chín giờ kém mười"}},
            {"current_time": ANCHOR})
        self.assertEqual(r.call["arguments"]["time"], "2026-10-31T08:50:00")

    def test_no_hour_still_needs_ask(self):
        r = ground_tool_call(
            {"name": "tasks.create", "arguments": {"time": "ngày mai"}},
            {"current_time": ANCHOR})
        self.assertEqual(r.status, "NEEDS_ASK")
        self.assertIn("time:hour", r.needs)


class TestMoneyUnchanged(unittest.TestCase):
    def test_multi_unit_and_ruoi_still_parse(self):
        p = NumberMoneyParser()
        self.assertEqual(
            p.parse_money("hai triệu ba trăm nghìn").value.__int__(), 2300000)
        self.assertEqual(
            p.parse_money("một triệu rưỡi").value.__int__(), 1500000)
        self.assertEqual(
            p.parse_money("ba trăm rưỡi nghìn").value.__int__(), 350000)


class TestDigitWordMultiUnitMoney(unittest.TestCase):
    """P2: digit coefficients in a multi-unit money amount (Check-A G-M1/G-M5).

    Before this fix the digit tokens broke the number span, so the span
    collapsed to a bare big unit and both cases parsed as 1,000,000 --
    a wrong value, not a fail-closed block. A digit coefficient is now
    part of the span and of its group; all-word cases above are unchanged.
    """

    def test_check_a_digit_word_cases(self):
        p = NumberMoneyParser()
        self.assertEqual(
            p.parse_money("3 triệu 500 nghìn").value.__int__(), 3500000)
        self.assertEqual(
            p.parse_money("1 triệu 250 nghìn").value.__int__(), 1250000)

    def test_digit_word_generalises(self):
        p = NumberMoneyParser()
        self.assertEqual(
            p.parse_money("2 tỷ 3 triệu 500 nghìn").value.__int__(), 2003500000)
        r = p.parse_money("3 triệu 500 nghìn đồng")
        self.assertEqual(r.value.__int__(), 3500000)
        self.assertEqual(r.unit, "VND")
        self.assertEqual(
            p.parse_money("50 nghìn rưỡi").value.__int__(), 50500)
        self.assertEqual(
            p.parse_money("3 trăm nghìn").value.__int__(), 300000)
        # Single-unit digit cases still go through their old paths.
        self.assertEqual(
            p.parse_money("3 triệu").value.__int__(), 3000000)
        self.assertEqual(
            p.parse_money("500 nghìn").value.__int__(), 500000)

    def test_digit_guards_stay_fail_closed(self):
        p = NumberMoneyParser()
        # Month/weekday guard applies to digit tokens as to word tokens.
        r = p.parse_money("tháng 1")
        self.assertIsNone(r.value)
        self.assertTrue(r.ambiguous)
        # A decimal coefficient spread over two digit tokens is not
        # fused into a guessed multi-unit value.
        r = p.parse_money("1,5 triệu 500 nghìn")
        self.assertIsNone(r.value)
        self.assertTrue(r.ambiguous)


if __name__ == "__main__":
    unittest.main()
