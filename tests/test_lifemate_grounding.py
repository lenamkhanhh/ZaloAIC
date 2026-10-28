#!/usr/bin/env python3
"""Tests for lifemate/lifemate_grounding.py (rounds 5-6).

Runs on CPU, stdlib only (+ RapidFuzz when installed; difflib otherwise).
Run with either interpreter -- both backends must pass:
  /tmp/rfvenv/bin/python tests/test_lifemate_grounding.py   # RapidFuzz path
  python3 tests/test_lifemate_grounding.py                   # difflib path

All test data is synthetic and fictitious. No probe IDs, amounts, or answers
from any dataset appear here. Two integration tests use REAL code (not mocks):
  - zaic_tools Simulator.validate() from the extracted LifeMate train package
    (proves validate() is free: log stays empty after schema checks).
  - branch lifemate.scoring.tool_f1 (proves the F1 consequence of
    read-after-write: 1.0 -> 0.6667 -> 0.5).
Those two tests skip with a clear message when their source trees are absent;
on the dev VM both paths exist, so a full run shows no skips.

Environment overrides (defaults are the dev-VM paths):
  ZAIC_TRAIN_DIR : directory containing zaic_tools/ and train_tools_catalog.json
  ZAIC_BRANCH_DIR: worktree root containing lifemate/scoring.py
"""

import importlib.util
import json
import os
import sys
import unittest
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = REPO_ROOT / "lifemate" / "lifemate_grounding.py"

spec = importlib.util.spec_from_file_location("lifemate_grounding", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
sys.modules["lifemate_grounding"] = mod  # dataclasses need this before exec
spec.loader.exec_module(mod)

NumberMoneyParser = mod.NumberMoneyParser
RelativeDateResolver = mod.RelativeDateResolver
ContactFilter = mod.ContactFilter
ContactCandidate = mod.ContactCandidate
validate_submission = mod.validate_submission

TRAIN_DIR = Path(os.environ.get(
    "ZAIC_TRAIN_DIR",
    os.path.expanduser("~/workspace/zaic-data/lifemate/extracted/"
                        "train+public_test/train")))
BRANCH_DIR = Path(os.environ.get(
    "ZAIC_BRANCH_DIR",
    os.path.expanduser("~/workspace/zaic-branch-a2e832b")))

print(f"[backend] text similarity backend: {mod.BACKEND}")


# ---------------------------------------------------------------- numbers
class TestNumberWords(unittest.TestCase):
    def setUp(self):
        self.p = NumberMoneyParser()

    def test_round4_group_cases(self):
        cases = [
            ("một trăm năm mươi nghìn", Decimal(150000)),
            ("hai mươi ba nghìn năm trăm", Decimal(23500)),
            ("một tỷ hai trăm triệu", Decimal(1200000000)),
            ("hai triệu rưỡi", Decimal(2500000)),
            ("năm mươi lăm triệu", Decimal(55000000)),
            ("một trăm", Decimal(100)),
            ("hai mươi", Decimal(20)),
            ("mười lăm", Decimal(15)),
            ("một trăm linh năm", Decimal(105)),
            ("một nghìn", Decimal(1000)),
            ("nghìn", Decimal(1000)),
            ("một nửa", Decimal("0.5")),
            ("năm rưỡi", Decimal("5.5")),
            ("một trăm rưỡi", Decimal(150)),
            ("nửa triệu", Decimal(500000)),
            ("một trăm năm mươi", Decimal(150)),
            ("mười", Decimal(10)),
        ]
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(self.p.parse_number_words(text), expected)

    def test_guards_return_none_not_zero(self):
        # Weekday / month-name / year readings and bare articles are NOT
        # numbers. Returning None (not 0) is what keeps the pipeline from
        # silently grounding a wrong value.
        for text in ("thứ hai", "tháng một", "năm nay", "nhắn một tin",
                     "hello", ""):
            with self.subTest(text=text):
                self.assertIsNone(self.p.parse_number_words(text))


class TestMoney(unittest.TestCase):
    def setUp(self):
        self.p = NumberMoneyParser()

    def test_digit_amounts(self):
        cases = [
            ("50 nghìn", Decimal(50000), ""),
            ("50k", Decimal(50000), ""),
            ("50kđ", Decimal(50000), "VND"),
            ("1,5 triệu", Decimal(1500000), ""),
            ("1.234.567", Decimal(1234567), ""),
            ("1.234.567,89", Decimal("1234567.89"), ""),
            ("1,234,567.89", Decimal("1234567.89"), ""),
            ("1.234", Decimal(1234), ""),   # single sep + 3 digits = thousands
            ("1,5", Decimal("1.5"), ""),    # single sep + 1 digit = decimal
            ("(1.234)", Decimal(-1234), ""),
            ("1.234-", Decimal(-1234), ""),
            ("150 nghìn đồng", Decimal(150000), "VND"),
            ("một trăm năm mươi nghìn", Decimal(150000), ""),  # word fallback
        ]
        for text, expected, unit in cases:
            with self.subTest(text=text):
                r = self.p.parse_money(text)
                self.assertEqual(r.value, expected)
                self.assertEqual(r.unit, unit)
                self.assertFalse(r.ambiguous)

    def test_unparseable_is_ambiguous_not_zero(self):
        r = self.p.parse_money("abc")
        self.assertIsNone(r.value)
        self.assertTrue(r.ambiguous)

    def test_multi_unit_money_regression(self):
        # Dry-run round 7 caught this: stripping a trailing big-unit
        # suffix and then multiplying DOUBLE-SCALES strings that already
        # contain a bigger unit ("hai trieu tam tram nghin" must be
        # 2,800,000, not 2,000,800 x 1000).
        cases = [
            ("hai triệu tám trăm nghìn", Decimal(2800000)),
            ("một triệu hai trăm nghìn", Decimal(1200000)),
            ("sáu triệu năm trăm nghìn", Decimal(6500000)),
            ("ba triệu sáu trăm nghìn", Decimal(3600000)),
            ("bảy triệu tám trăm nghìn", Decimal(7800000)),
            ("mười tám triệu năm trăm nghìn", Decimal(18500000)),
            ("hai mươi ba triệu hai trăm hai mươi nghìn", Decimal(23220000)),
            ("một tỷ hai trăm triệu", Decimal(1200000000)),
            ("năm mươi nghìn", Decimal(50000)),
        ]
        for text, expected in cases:
            with self.subTest(text=text):
                r = self.p.parse_money(text)
                self.assertEqual(r.value, expected)
                self.assertFalse(r.ambiguous)


# ---------------------------------------------------------------- dates
ANCHOR_WED = datetime(2026, 10, 14, 20, 0)   # Wednesday
ANCHOR_SAT = datetime(2026, 10, 17, 20, 0)   # Saturday


class TestRelativeDates(unittest.TestCase):
    def test_day_offsets(self):
        r = RelativeDateResolver(ANCHOR_WED)
        self.assertEqual(r.resolve("ngày mai").date, date(2026, 10, 15))
        self.assertEqual(r.resolve("hôm qua").date, date(2026, 10, 13))
        self.assertEqual(r.resolve("mai tôi họp").date, date(2026, 10, 15))
        self.assertEqual(r.resolve("2 ngày nữa").date, date(2026, 10, 16))
        self.assertEqual(r.resolve("3 ngày trước").date, date(2026, 10, 11))

    def test_weekdays(self):
        r = RelativeDateResolver(ANCHOR_WED)
        # Next Monday after Wednesday = Monday of next week.
        self.assertEqual(r.resolve("thứ hai tới").date, date(2026, 10, 19))
        self.assertEqual(r.resolve("thứ hai tuần sau").date, date(2026, 10, 19))
        # Friday of next week (not this Friday, not next-next Friday).
        self.assertEqual(r.resolve("thứ sáu tuần sau").date, date(2026, 10, 23))
        # Bare weekday = next occurrence strictly after the anchor.
        self.assertEqual(r.resolve("thứ sáu").date, date(2026, 10, 16))

    def test_daypart_gives_date_only(self):
        r = RelativeDateResolver(ANCHOR_WED)
        d = r.resolve("sáng mai")
        self.assertEqual(d.date, date(2026, 10, 15))
        self.assertTrue(d.hour_missing)
        self.assertEqual(d.daypart, "sang")
        d = r.resolve("chiều nay")
        self.assertEqual(d.date, date(2026, 10, 14))
        self.assertTrue(d.hour_missing)

    def test_week_month_refs_never_invent_a_day(self):
        r = RelativeDateResolver(ANCHOR_WED)
        for text in ("cuối tuần này", "tháng sau", "tuần này"):
            with self.subTest(text=text):
                d = r.resolve(text)
                self.assertIsNone(d.date)

    def test_absolute_forms(self):
        r = RelativeDateResolver(ANCHOR_WED)
        self.assertEqual(r.resolve("15/11").date, date(2026, 11, 15))
        self.assertEqual(r.resolve("ngày 15 tháng 11").date, date(2026, 11, 15))
        self.assertEqual(r.resolve("2026-12-25").date, date(2026, 12, 25))
        # dd/mm, never mm/dd.
        self.assertEqual(r.resolve("02/06/2026").date, date(2026, 6, 2))

    def test_anchor_is_required_and_decisive(self):
        with self.assertRaises(ValueError):
            RelativeDateResolver(None)
        a = RelativeDateResolver(ANCHOR_WED).resolve("ngày mai").date
        b = RelativeDateResolver(ANCHOR_SAT).resolve("ngày mai").date
        self.assertEqual(a, date(2026, 10, 15))
        self.assertEqual(b, date(2026, 10, 18))
        self.assertNotEqual(a, b)

    def test_no_wall_clock_reads_in_module_source(self):
        # AST check (not a substring grep): docstrings may NAME the banned
        # calls, but no executable call to now()/today()/utcnow() may exist.
        import ast
        tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        banned = {"now", "today", "utcnow"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                self.assertNotIn(node.func.attr, banned)


# ---------------------------------------------------------------- contacts
class TestContactFilter(unittest.TestCase):
    def setUp(self):
        self.f = ContactFilter()

    def test_exact_beats_close_tone_variant(self):
        roster = [ContactCandidate("c1", "Bình"),
                  ContactCandidate("c2", "Bính")]
        d = self.f.filter_contacts("Bình", roster)
        self.assertEqual(d.status, "EXACT")
        self.assertEqual(d.candidate.id, "c1")
        d = self.f.filter_contacts("Bính", roster)
        self.assertEqual(d.status, "EXACT")
        self.assertEqual(d.candidate.id, "c2")

    def test_tone_conflict_blocks_silent_grounding(self):
        # One character differs, tones differ on the last word: text score
        # clears 88 on both backends, but the tone channel must block it.
        roster = [ContactCandidate("c1", "Trần Thị Hường")]
        d = self.f.filter_contacts("Trần Thị Hương", roster)
        self.assertEqual(d.status, "AMBIGUOUS")
        self.assertEqual(d.reason, "tone_conflict")

    def test_fuzzy_grounded_with_matching_tones(self):
        roster = [ContactCandidate("c1", "Trần Thị Hương"),
                  ContactCandidate("c2", "Trần Thị Lan")]
        d = self.f.filter_contacts("Trần Thị Hươn", roster)
        self.assertEqual(d.status, "FUZZY_GROUNDED")
        self.assertEqual(d.candidate.id, "c1")

    def test_duplicate_name_is_always_ambiguous(self):
        roster = [ContactCandidate("c1", "Lan"),
                  ContactCandidate("c2", "Lan")]
        d = self.f.filter_contacts("Lan", roster)
        self.assertEqual(d.status, "AMBIGUOUS")
        self.assertEqual(d.reason, "duplicate_name")

    def test_abbreviation_single_hit_grounds(self):
        roster = [ContactCandidate("c1", "Lan Minh"),
                  ContactCandidate("c2", "Lan Anh")]
        d = self.f.filter_contacts("LM", roster)
        self.assertEqual(d.status, "FUZZY_GROUNDED")
        self.assertEqual(d.method, "abbreviation")
        self.assertEqual(d.candidate.id, "c1")

    def test_abbreviation_multi_hit_is_ambiguous(self):
        roster = [ContactCandidate("c1", "Lan Anh"),
                  ContactCandidate("c2", "Long An")]
        d = self.f.filter_contacts("LA", roster)
        self.assertEqual(d.status, "AMBIGUOUS")
        self.assertEqual(d.reason, "ambiguous_abbreviation")

    def test_word_of_name_single_hit_grounds(self):
        roster = [ContactCandidate("c1", "Sếp Dũng"),
                  ContactCandidate("c2", "Anh Tuấn")]
        d = self.f.filter_contacts("Dũng", roster)
        self.assertEqual(d.status, "FUZZY_GROUNDED")
        self.assertEqual(d.method, "abbreviation")

    def test_unknown_and_empty(self):
        roster = [ContactCandidate("c1", "Lan")]
        self.assertEqual(self.f.filter_contacts("Xyzabc", roster).status,
                         "UNKNOWN")
        self.assertEqual(self.f.filter_contacts("", roster).status, "UNKNOWN")
        self.assertEqual(self.f.filter_contacts("Lan", []).status, "UNKNOWN")

    def test_margin_rule_layer(self):
        # Decision-rule unit test with a stubbed scorer (the scorer itself
        # is covered by the behavioral tests above, which use the real one).
        # Query is deliberately NOT exact, so the margin branch is reached.
        orig = mod._text_score
        try:
            mod._text_score = lambda a, b: 95.0 if b == "lan minh" else 90.0
            roster = [ContactCandidate("c1", "Lan Minh"),
                      ContactCandidate("c2", "Lan Min")]
            d = self.f.filter_contacts("Lan Minx", roster)
            self.assertEqual(d.status, "AMBIGUOUS")
            self.assertEqual(d.reason, "small_margin")
            mod._text_score = lambda a, b: 95.0 if b == "lan minh" else 80.0
            d = self.f.filter_contacts("Lan Minx", roster)
            self.assertEqual(d.status, "FUZZY_GROUNDED")
        finally:
            mod._text_score = orig


# ---------------------------------------------------------------- pipeline
class TestPipelineGuard(unittest.TestCase):
    READS = {"reminders.list", "contacts.search", "weather.get_forecast"}

    def test_clean_write_only(self):
        calls = [{"name": "reminders.create",
                  "arguments": {"time": "2026-10-15T08:00:00+07:00",
                                "content": "x"}}]
        self.assertEqual(validate_submission(calls, self.READS), [])

    def test_read_after_write_flagged(self):
        calls = [{"name": "reminders.create", "arguments": {}},
                 {"name": "reminders.list", "arguments": {}}]
        v = validate_submission(calls, self.READS)
        self.assertEqual(len(v), 1)
        self.assertIn("read_after_write", v[0])

    def test_read_before_write_is_fine(self):
        calls = [{"name": "reminders.list", "arguments": {}},
                 {"name": "reminders.create", "arguments": {}}]
        self.assertEqual(validate_submission(calls, self.READS), [])

    def test_ask_after_write_is_not_a_read(self):
        calls = [{"name": "reminders.create", "arguments": {}},
                 {"name": "sys.ask_missing_info", "arguments": {}}]
        self.assertEqual(validate_submission(calls, self.READS), [])

    def test_empty_submission_flagged(self):
        self.assertEqual(validate_submission([], self.READS),
                         ["empty_submission"])


# ---------------------------------------------------------------- integration
class TestIntegrationRealCode(unittest.TestCase):
    @unittest.skipUnless((TRAIN_DIR / "zaic_tools").exists(),
                         "zaic_tools tree absent")
    def test_validate_is_free(self):
        sys.path.insert(0, str(TRAIN_DIR))
        from zaic_tools.executor import Simulator
        catalog = json.loads(
            (TRAIN_DIR / "train_tools_catalog.json").read_text(
                encoding="utf-8"))
        sample = {"context": {
            "installed_apps": {
                "reminders": {"tools": ["reminders.create", "reminders.list"],
                              "state": {}},
                "sys": {"tools": ["sys.ask_missing_info"], "state": {}}},
            "current_time": "2026-10-14T20:00:00+07:00"}}
        sim = Simulator(sample, catalog)
        good = sim.validate("reminders.create",
                            {"time": "2026-10-15T08:00:00+07:00",
                             "content": "x"})
        bad = sim.validate("reminders.create", {"content": "x"})
        self.assertEqual(good, {"ok": True, "error": None})
        self.assertFalse(bad["ok"])
        self.assertIn("time", bad["error"])
        self.assertEqual(sim.log, [])  # validate() never grows the trace
        sim.call("reminders.create",
                 {"time": "2026-10-15T08:00:00+07:00", "content": "x"})
        self.assertEqual(len(sim.log), 1)  # but a real call does

    @unittest.skipUnless((BRANCH_DIR / "lifemate" / "scoring.py").exists(),
                         "branch scorer absent")
    def test_f1_consequence_of_read_after_write(self):
        sys.path.insert(0, str(BRANCH_DIR))
        from lifemate.scoring import tool_f1
        gold = [{"name": "reminders.create",
                 "arguments": {"time": "2026-10-15T08:00:00+07:00",
                               "content": "x"}}]
        write = dict(gold[0])
        read = {"name": "reminders.list", "arguments": {}}
        read2 = {"name": "contacts.search", "arguments": {"query": "Lan"}}
        ask = {"name": "sys.ask_missing_info",
               "arguments": {"tool_name": "reminders.create",
                             "params": ["time"]}}
        self.assertEqual(tool_f1([write], gold, {}), 1.0)
        self.assertAlmostEqual(tool_f1([write, read], gold, {}), 2 / 3)
        self.assertAlmostEqual(tool_f1([write, read, read2], gold, {}), 0.5)
        self.assertEqual(tool_f1([ask], gold, {}), 0.0)


# ---------------------------------------------------------------- roster
# Realistic shapes measured in the round-6 ToolEnv replay (see
# research/lifemate/contacts-roster-audit.md). Names here are fictitious
# shapes, not copied roster rows.
class TestRosterShapes(unittest.TestCase):
    def setUp(self):
        self.f = ContactFilter()

    def test_exact_beats_longer_containing_name(self):
        # Query "Lan" with roster ["Lan", "Lan Anh"]: substring search
        # returns both, but exact equality must win, not the longer name.
        roster = [ContactCandidate("c1", "Lan"),
                  ContactCandidate("c2", "Lan Anh")]
        d = self.f.filter_contacts("Lan", roster)
        self.assertEqual(d.status, "EXACT")
        self.assertEqual(d.candidate.id, "c1")

    def test_duplicate_group_plus_third_name_still_ambiguous(self):
        roster = [ContactCandidate("c1", "Lan"),
                  ContactCandidate("c2", "Lan"),
                  ContactCandidate("c3", "Minh")]
        d = self.f.filter_contacts("Lan", roster)
        self.assertEqual(d.status, "AMBIGUOUS")
        self.assertEqual(d.reason, "duplicate_name")

    def test_empty_query_with_duplicates_is_unknown(self):
        roster = [ContactCandidate("c1", "Lan"),
                  ContactCandidate("c2", "Lan")]
        d = self.f.filter_contacts("", roster)
        self.assertEqual(d.status, "UNKNOWN")

    def test_threshold_sensitivity_on_fuzzy_input(self):
        # Proves the round-6 sweep machinery is alive: the sweep was flat
        # on gold because gold queries are all exact, NOT because the
        # thresholds do nothing. A typo query grounds at 88, not at 99.
        roster = [ContactCandidate("c1", "Trần Thị Hương"),
                  ContactCandidate("c2", "Trần Thị Lan")]
        orig = mod.FUZZY_THRESHOLD
        try:
            mod.FUZZY_THRESHOLD = 88.0
            self.assertEqual(
                self.f.filter_contacts("Trần Thị Hươn", roster).status,
                "FUZZY_GROUNDED")
            mod.FUZZY_THRESHOLD = 99.0
            self.assertEqual(
                self.f.filter_contacts("Trần Thị Hươn", roster).status,
                "UNKNOWN")
        finally:
            mod.FUZZY_THRESHOLD = orig


# ---------------------------------------------------------------- adapter
class TestAdapter(unittest.TestCase):
    CTX = {"current_time": "2026-10-14T20:00:00+07:00"}  # Wednesday

    def test_money_string_grounds_to_int(self):
        r = mod.ground_tool_call(
            {"name": "ewallet.transfer",
             "arguments": {"amount": "50 nghìn", "contact_id": "c1"}},
            self.CTX)
        self.assertEqual(r.status, "GROUNDED")
        self.assertEqual(r.call["arguments"]["amount"], 50000)
        self.assertIsInstance(r.call["arguments"]["amount"], int)

    def test_money_number_passes_through(self):
        r = mod.ground_tool_call(
            {"name": "ewallet.transfer", "arguments": {"amount": 50000}},
            self.CTX)
        self.assertEqual(r.status, "UNCHANGED")

    def test_money_unparseable_needs_ask(self):
        r = mod.ground_tool_call(
            {"name": "ewallet.transfer", "arguments": {"amount": "abc"}},
            self.CTX)
        self.assertEqual(r.status, "NEEDS_ASK")
        self.assertIn("amount", r.needs)

    def test_date_relative_grounds(self):
        r = mod.ground_tool_call(
            {"name": "reminders.create",
             "arguments": {"date": "ngày mai", "content": "x"}},
            self.CTX)
        self.assertEqual(r.status, "GROUNDED")
        self.assertEqual(r.call["arguments"]["date"], "2026-10-15")

    def test_date_week_only_needs_ask(self):
        r = mod.ground_tool_call(
            {"name": "reminders.create", "arguments": {"date": "tháng sau"}},
            self.CTX)
        self.assertEqual(r.status, "NEEDS_ASK")
        self.assertIn("date:unresolved", r.needs)

    def test_time_daypart_needs_hour(self):
        r = mod.ground_tool_call(
            {"name": "reminders.create", "arguments": {"time": "sáng mai"}},
            self.CTX)
        self.assertEqual(r.status, "NEEDS_ASK")
        self.assertIn("time:hour", r.needs)

    def test_time_relative_with_hour_composes_datetime(self):
        r = mod.ground_tool_call(
            {"name": "reminders.create",
             "arguments": {"time": "ngày mai lúc 8 giờ"}},
            self.CTX)
        self.assertEqual(r.status, "GROUNDED")
        self.assertEqual(r.call["arguments"]["time"],
                         "2026-10-15T08:00:00+07:00")

    def test_time_iso_and_time_only_pass_through(self):
        for v in ("2026-10-15T08:00:00+07:00", "19:00"):
            with self.subTest(v=v):
                r = mod.ground_tool_call(
                    {"name": "reminders.create", "arguments": {"time": v}},
                    self.CTX)
                self.assertEqual(r.status, "UNCHANGED")
                self.assertEqual(r.call["arguments"]["time"], v)

    def test_time_relative_without_context_needs_ask_not_wall_clock(self):
        r = mod.ground_tool_call(
            {"name": "reminders.create", "arguments": {"time": "ngày mai"}},
            None)
        self.assertEqual(r.status, "NEEDS_ASK")
        self.assertIn("time:context_time", r.needs)

    def test_contact_name_exact_grounds_to_id(self):
        roster = [{"id": "c1", "name": "Lan"}]
        r = mod.ground_tool_call(
            {"name": "sms.send",
             "arguments": {"contact_name": "Lan", "content": "hi"}},
            self.CTX, roster)
        self.assertEqual(r.status, "GROUNDED")
        self.assertEqual(r.call["arguments"]["contact_id"], "c1")
        self.assertNotIn("contact_name", r.call["arguments"])

    def test_contact_duplicate_needs_ask_and_sets_no_id(self):
        roster = [ContactCandidate("c1", "Lan"),
                  ContactCandidate("c2", "Lan")]
        r = mod.ground_tool_call(
            {"name": "sms.send",
             "arguments": {"contact_name": "Lan", "content": "hi"}},
            self.CTX, roster)
        self.assertEqual(r.status, "NEEDS_ASK")
        self.assertIn("contact:ambiguous", r.needs)
        self.assertNotIn("contact_id", r.call["arguments"])

    def test_search_call_is_never_rewritten(self):
        roster = [ContactCandidate("c1", "Lan")]
        r = mod.ground_tool_call(
            {"name": "contacts.search", "arguments": {"query": "Lan"}},
            self.CTX, roster)
        self.assertEqual(r.status, "UNCHANGED")
        self.assertEqual(r.call["arguments"]["query"], "Lan")

    def test_contact_id_outside_roster_is_noted_not_blocked(self):
        # Gold itself uses history ids outside search results (9/120 pairs).
        roster = [ContactCandidate("c1", "Lan")]
        r = mod.ground_tool_call(
            {"name": "sms.send",
             "arguments": {"contact_id": "c9", "content": "hi"}},
            self.CTX, roster)
        self.assertEqual(r.status, "UNCHANGED")
        self.assertTrue(any("not in provided roster" in n for n in r.notes))

    def test_input_is_never_mutated(self):
        call = {"name": "ewallet.transfer",
                "arguments": {"amount": "50 nghìn"}}
        before = json.loads(json.dumps(call))
        mod.ground_tool_call(call, self.CTX)
        self.assertEqual(call, before)

    def test_malformed_call_raises(self):
        with self.assertRaises(ValueError):
            mod.ground_tool_call({"name": "x"})
        with self.assertRaises(ValueError):
            mod.ground_tool_call({"name": "x", "arguments": "nope"})

    @unittest.skipUnless((TRAIN_DIR / "zaic_tools").exists(),
                         "zaic_tools tree absent")
    def test_ground_then_validate_order(self):
        # Pipeline order: ground FIRST, then the real Simulator.validate()
        # on the grounded call -- validation must pass and stay free.
        sys.path.insert(0, str(TRAIN_DIR))
        from zaic_tools.executor import Simulator
        catalog = json.loads(
            (TRAIN_DIR / "train_tools_catalog.json").read_text(
                encoding="utf-8"))
        sample = {"context": {
            "installed_apps": {
                "reminders": {"tools": ["reminders.create", "reminders.list"],
                              "state": {}},
                "sys": {"tools": ["sys.ask_missing_info"], "state": {}}},
            "current_time": "2026-10-14T20:00:00+07:00"}}
        sim = Simulator(sample, catalog)
        r = mod.ground_tool_call(
            {"name": "reminders.create",
             "arguments": {"time": "ngày mai lúc 8 giờ", "content": "x"}},
            self.CTX)
        self.assertEqual(r.status, "GROUNDED")
        v = sim.validate(r.call["name"], r.call["arguments"])
        self.assertEqual(v, {"ok": True, "error": None})
        self.assertEqual(sim.log, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
