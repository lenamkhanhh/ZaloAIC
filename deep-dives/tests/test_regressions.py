"""Regression tests for the deep-dives code fixes (round 3).

Run:  python3 -m unittest discover -s deep-dives/tests -v
from the repo root. Pure/fake-environment tests always run; DuckDB
tests skip gracefully if duckdb/pandas are not installed; the
jsonschema test skips if jsonschema is not installed. No GPU, no
model, no network, no ZAIC data: every case below is synthetic and
distinguishes correct from incorrect behaviour, including valid cases
so a fix cannot silently over-block.

Each test name cites the bug it guards, so a future failure reads as
a regression description, not just a red line.
"""

import importlib.util
import sys
import unittest
from pathlib import Path

DEEP_DIVES = Path(__file__).resolve().parent.parent


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, DEEP_DIVES / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


M1 = load("dd01", "01-constrained-decoding-lifemate.py")
M2 = load("dd02", "02-asr-grounding-lifemate.py")
M4 = load("dd04", "04-confidence-abstain-datamate.py")

try:
    import jsonschema  # type: ignore
except ImportError:
    jsonschema = None

try:
    M3 = load("dd03", "03-duckdb-excel-datamate.py")
except ImportError:
    M3 = None


def tools():
    return M1.normalize_catalog(M1.DEMO_CATALOG)


# ---------------------------------------------------------------------------
# 01: schema, x-ref, agent observation, normal termination, cache staleness
# ---------------------------------------------------------------------------

class Test01Schema(unittest.TestCase):
    def test_valid_call_passes_standard_validator(self):
        """Regression: outer additionalProperties used to reject every call."""
        if jsonschema is None:
            self.skipTest("jsonschema not installed")
        schema = M1.build_tool_call_schema(tools())
        jsonschema.validate(
            {"name": "contacts.search", "arguments": {"name": "An"}}, schema)

    def test_wrong_tool_rejected_by_standard_validator(self):
        if jsonschema is None:
            self.skipTest("jsonschema not installed")
        schema = M1.build_tool_call_schema(tools())
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(
                {"name": "nope.tool", "arguments": {}}, schema)

    def test_wrong_arguments_rejected_by_code_validator(self):
        call, errors = M1.validate_tool_call(
            {"name": "banking.transfer",
             "arguments": {"contact_id": "c-1", "amount": "not-a-number"}},
            tools(), {"contact_id": {"c-1"}})
        self.assertIsNone(call)
        self.assertTrue(errors)

    def test_extra_argument_rejected(self):
        call, errors = M1.validate_tool_call(
            {"name": "contacts.search",
             "arguments": {"name": "An", "surprise": 1}},
            tools(), {})
        self.assertIsNone(call)
        self.assertTrue(errors)

    def test_xref_missing_key_fails_closed(self):
        """Regression: a missing reference set used to pass any id."""
        call, errors = M1.validate_tool_call(
            {"name": "banking.transfer",
             "arguments": {"contact_id": "c-ANY", "amount": 1}},
            tools(), {})
        self.assertIsNone(call)
        self.assertTrue(any("not loaded" in e for e in errors))

    def test_xref_loaded_empty_rejects_everything(self):
        call, errors = M1.validate_tool_call(
            {"name": "banking.transfer",
             "arguments": {"contact_id": "c-1", "amount": 1}},
            tools(), {"contact_id": set()})
        self.assertIsNone(call)
        self.assertTrue(any("not a known" in e for e in errors))

    def test_xref_loaded_set_accepts_member(self):
        call, errors = M1.validate_tool_call(
            {"name": "banking.transfer",
             "arguments": {"contact_id": "c-1", "amount": 1}},
            tools(), {"contact_id": {"c-1", "c-2"}})
        self.assertIsNotNone(call)
        self.assertEqual(errors, [])

    def test_xref_refset_unloaded_fails_closed(self):
        call, errors = M1.validate_tool_call(
            {"name": "banking.transfer",
             "arguments": {"contact_id": "c-1", "amount": 1}},
            tools(), {"contact_id": M1.RefSet(ids=frozenset(), loaded=False)})
        self.assertIsNone(call)
        self.assertTrue(any("not loaded" in e for e in errors))


def make_text_generator(texts):
    """Feed pre-written tool-call JSONs in order (offline stand-in for
    the vLLM engine, via ToolAgent.text_generator)."""
    state = {"i": 0}

    def gen(prompt):
        idx = min(state["i"], len(texts) - 1)
        state["i"] += 1
        return texts[idx]

    return gen


class Test01Agent(unittest.TestCase):
    def test_read_result_feeds_next_call(self):
        """Regression: execute() used to return only booleans, so the
        agent could never use an id it had just read."""
        t = tools()
        gen = make_text_generator([
            '{"name": "contacts.search", "arguments": {"name": "An"}}',
            '{"name": "banking.transfer", "arguments": {"contact_id": "c-99", "amount": 50000}}',
        ])

        def execute(call):
            if call.name == "contacts.search":
                return M1.ExecutionResult(
                    ok=True, state_progress=True,
                    output={"contacts": [{"id": "c-99", "name": "An"}]},
                    refs={"contact_id": {"c-99"}})
            return M1.ExecutionResult(ok=True, state_progress=True,
                                      output={"status": "done"})

        agent = M1.ToolAgent(engine=None, tools=t, execute=execute, text_generator=gen)
        trace = agent.run(
            "Transfer to An",
            completion=lambda result, executed: executed[-1].name == "banking.transfer")
        self.assertTrue(agent.finished_normally)
        self.assertEqual([c.name for c in trace],
                         ["contacts.search", "banking.transfer"])
        self.assertEqual(trace[-1].arguments["contact_id"], "c-99")
        self.assertEqual(len(agent.last_results), 2)

    def test_tool_error_is_visible_to_replan(self):
        t = tools()
        gen = make_text_generator([
            '{"name": "contacts.search", "arguments": {"name": "An"}}',
            '{"name": "contacts.search", "arguments": {"name": "An"}}',
        ])
        seen = []

        def execute(call):
            seen.append(call)
            return M1.ExecutionResult(ok=False, state_progress=False,
                                      error="simulated tool failure")

        agent = M1.ToolAgent(engine=None, tools=t, execute=execute, text_generator=gen)
        trace = agent.run("Search An")
        # Guard semantics: the THIRD identical call is blocked before
        # execution (second is executed, then replan_once); the errors
        # of the executed calls are recorded, not hidden.
        self.assertEqual(len(seen), 2)
        self.assertEqual(len(trace), 2)
        self.assertTrue(all(r.error == "simulated tool failure"
                            for r in agent.last_results))

    def test_write_invalidates_value_cache_but_not_id_refs(self):
        t = tools()
        gen = make_text_generator([
            '{"name": "contacts.search", "arguments": {"name": "An"}}',
            '{"name": "banking.transfer", "arguments": {"contact_id": "c-99", "amount": 1}}',
        ])

        def execute(call):
            if call.name == "contacts.search":
                return M1.ExecutionResult(
                    ok=True, state_progress=True, output={"balance": 100},
                    refs={"contact_id": {"c-99"}})
            return M1.ExecutionResult(ok=True, state_progress=True)

        agent = M1.ToolAgent(engine=None, tools=t, execute=execute, text_generator=gen)
        agent.run("x", completion=lambda r, e: len(e) == 2)
        self.assertEqual(agent.value_cache, {})
        self.assertIn("c-99", agent.allowed_refs["contact_id"])

    def test_ask_after_write_is_flagged_as_assumption(self):
        # The gate itself is conservative; this test pins the documented
        # status so nobody later quotes it as an official rule.
        self.assertFalse(M1.request_missing_info(
            writes_executed=1, slot_groundable_by_any_read=False))
        self.assertIn("ASSUMPTION", M1.request_missing_info.__doc__)


# ---------------------------------------------------------------------------
# 02: typed grounding, clause-scoped negation
# ---------------------------------------------------------------------------

class Test02Grounding(unittest.TestCase):
    def C(self, value):
        return [M2.Candidate(value, "accounts")]

    def test_money_decimal_separator_kept(self):
        """Regression: '1,5' used to EXACT-match candidate '15'."""
        r = M2.ground_slot("1,5", self.C("15"), M2.SlotKind.MONEY)
        self.assertEqual(r.tier, M2.ConfidenceTier.UNKNOWN)
        self.assertIsNone(r.value)

    def test_money_sign_kept(self):
        """Regression: '-100' and '(100)' used to EXACT-match '100'."""
        for raw in ("-100", "(100)"):
            r = M2.ground_slot(raw, self.C("100"), M2.SlotKind.MONEY)
            self.assertEqual(r.tier, M2.ConfidenceTier.UNKNOWN, raw)
            self.assertIsNone(r.value)

    def test_money_negative_matches_negative(self):
        r = M2.ground_slot("-100", self.C("-100"), M2.SlotKind.MONEY)
        self.assertEqual(r.tier, M2.ConfidenceTier.EXACT)

    def test_money_unit_scaling(self):
        r = M2.ground_slot("1,5 triệu", self.C("1500000"), M2.SlotKind.MONEY)
        self.assertEqual(r.tier, M2.ConfidenceTier.EXACT)
        self.assertEqual(r.value, "1500000")

    def test_money_ambiguous_single_separator(self):
        # "1.500" as an ASR money span with no unit: 1500 or 1.5?
        # Typed parsing must not guess; UNKNOWN is the correct answer.
        r = M2.ground_slot("1.500", self.C("1500"), M2.SlotKind.MONEY)
        self.assertEqual(r.tier, M2.ConfidenceTier.UNKNOWN)

    def test_date_calendar_meaning(self):
        r = M2.ground_slot("15/7", [M2.Candidate("2025-07-15", "accounts")],
                           M2.SlotKind.DATE)
        self.assertEqual(r.tier, M2.ConfidenceTier.EXACT)
        r2 = M2.ground_slot("31/02/2025", [M2.Candidate("2025-02-28", "accounts")],
                            M2.SlotKind.DATE)
        self.assertEqual(r2.tier, M2.ConfidenceTier.UNKNOWN)
        r3 = M2.ground_slot("15/7", [M2.Candidate("2025-07-16", "accounts")],
                            M2.SlotKind.DATE)
        self.assertEqual(r3.tier, M2.ConfidenceTier.UNKNOWN)

    def test_id_leading_zeros_and_separators(self):
        r = M2.ground_slot("090 123 4567", self.C("0901234567"),
                           M2.SlotKind.ACCOUNT_ID)
        self.assertEqual(r.tier, M2.ConfidenceTier.EXACT)
        r2 = M2.ground_slot("0901234568", self.C("0901234567"),
                            M2.SlotKind.ACCOUNT_ID)
        self.assertEqual(r2.tier, M2.ConfidenceTier.UNKNOWN)

    def test_name_exact_still_works(self):
        r = M2.ground_slot("Nguyễn Văn An",
                           [M2.Candidate("Nguyễn Văn An", "contacts")],
                           M2.SlotKind.NAME)
        self.assertEqual(r.tier, M2.ConfidenceTier.EXACT)


class Test02Negation(unittest.TestCase):
    def test_pay_negation_blocked(self):
        """Regression: 'Không thanh toán hóa đơn' used to allow pay."""
        d = M2.guard_tool_call("pay", "hóa đơn", "Không thanh toán hóa đơn")
        self.assertFalse(d.allowed)

    def test_prohibition_blocked(self):
        d = M2.guard_tool_call("turn_on", "Đèn phòng khách",
                               "Đừng bật đèn phòng khách")
        self.assertFalse(d.allowed)

    def test_contrast_blocks_negated_side_only(self):
        text = "Không phải đèn phòng khách mà là đèn phòng ngủ, bật lên"
        self.assertFalse(M2.guard_tool_call("turn_on", "Đèn phòng khách", text).allowed)
        self.assertTrue(M2.guard_tool_call("turn_on", "Đèn phòng ngủ", text).allowed)

    def test_cross_clause_target_not_overblocked(self):
        """'Không bật A, bật B' must block A and allow B."""
        text = "Không bật đèn phòng khách, bật đèn phòng ngủ"
        self.assertFalse(M2.guard_tool_call("turn_on", "Đèn phòng khách", text).allowed)
        self.assertTrue(M2.guard_tool_call("turn_on", "Đèn phòng ngủ", text).allowed)

    def test_not_yet_does_not_block(self):
        d = M2.guard_tool_call("transfer", "Trần Thị Bình",
                               "Chưa chuyển tiền cho Trần Thị Bình")
        self.assertTrue(d.allowed)

    def test_generic_negation_blocks_unnamed_target(self):
        # "Không chuyển tiền" names no target: fail closed, do not allow
        # a transfer to someone on the grounds the name was absent.
        d = M2.guard_tool_call("transfer", "Trần Thị Bình", "Không chuyển tiền")
        self.assertFalse(d.allowed)

    def test_unrelated_action_not_blocked(self):
        d = M2.guard_tool_call("turn_off", "Đèn phòng khách",
                               "Không bật đèn phòng khách")
        self.assertTrue(d.allowed)


# ---------------------------------------------------------------------------
# 03: VN numbers, Decimal money, read-only SQL, order-level revenue rule
# ---------------------------------------------------------------------------

@unittest.skipIf(M3 is None, "duckdb/pandas not installed")
class Test03Numbers(unittest.TestCase):
    def test_negative_sign_kept(self):
        """Regression: '-100' and '(100)' used to become +100.0."""
        self.assertEqual(M3.parse_vn_number("-100"), (-100.0, None))
        self.assertEqual(M3.parse_vn_number("(100)"), (-100.0, None))
        self.assertEqual(M3.parse_vn_number("(1.000,50)"), (-1000.5, None))

    def test_plain_integer_in_vn_and_en(self):
        """Regression: locale='vn' used to reject '1000'."""
        self.assertEqual(M3.parse_vn_number("1000", locale="vn"), (1000.0, None))
        self.assertEqual(M3.parse_vn_number("1000", locale="en"), (1000.0, None))

    def test_thousands_and_decimals(self):
        self.assertEqual(M3.parse_vn_number("1.000.000,50"), (1000000.5, None))
        self.assertEqual(M3.parse_vn_number("1,000,000.50"), (1000000.5, None))
        self.assertEqual(M3.parse_vn_number("1.500", locale="vn"), (1500.0, None))
        self.assertEqual(M3.parse_vn_number("1,500", locale="en"), (1500.0, None))

    def test_ambiguous_and_null_and_percent(self):
        value, issue = M3.parse_vn_number("1.500")
        self.assertIsNone(value)
        self.assertIn("ambiguous", issue)
        self.assertEqual(M3.parse_vn_number(None), (None, None))
        self.assertEqual(M3.parse_vn_number(""), (None, None))
        value, issue = M3.parse_vn_number("50%")
        self.assertIsNone(value)
        self.assertIsNotNone(issue)

    def test_money_decimal_exact(self):
        from decimal import Decimal
        value, issue = M3.parse_vn_money("1.000.000,50")
        self.assertEqual(value, Decimal("1000000.50"))
        self.assertIsNone(issue)
        value, issue = M3.parse_vn_money("(100)")
        self.assertEqual(value, Decimal("-100"))
        # Decimal path must not inherit the float path's rounding.
        value, _ = M3.parse_vn_money("0,1")
        self.assertEqual(value, Decimal("0.1"))


@unittest.skipIf(M3 is None, "duckdb/pandas not installed")
class Test03Store(unittest.TestCase):
    def test_write_sql_rejected_by_store(self):
        """Regression: query() used to execute any SQL it was handed."""
        store = M3.DuckDBStore()
        try:
            with self.assertRaises(ValueError):
                store.query("DROP TABLE orders")
            with self.assertRaises(ValueError):
                store.query("SELECT * FROM orders; DROP TABLE orders")
            with self.assertRaises(ValueError):
                store.query("SELECT read_csv('x.csv')")
            df = store.query("SELECT 1 AS one")
            self.assertEqual(df.iloc[0]["one"], 1)
        finally:
            store.close()

    def test_order_level_return_exclusion(self):
        """A returned line excludes its whole order (rulebook reading),
        not just the returned line."""
        import pandas as pd
        store = M3.DuckDBStore()
        try:
            calendar = pd.DataFrame({
                "solar_date": pd.to_datetime(["2025-01-22"]).date,
                "lunar_year": [2024], "lunar_month": [12], "lunar_day": [23],
            })
            orders = pd.DataFrame({
                "order_id": [1, 2],
                "order_date": pd.to_datetime(["2025-01-22", "2025-01-22"]).date,
            })
            lines = pd.DataFrame({
                "order_id": [1, 1, 2],
                "line_amount_after_discount": [100.0, 50.0, 200.0],
                "line_status": ["ok", "returned", "ok"],
            })
            store.register_frame("calendar", calendar)
            store.register_frame("orders", orders)
            store.register_frame("order_lines", lines)
            sql, params = M3.tet_window_sql(2024)
            result = store.query(sql, params).iloc[0]["tet_revenue"]
            # Order 1 (100 ok + 50 returned) contributes 0, order 2 gives 200.
            self.assertEqual(result, 200.0)
        finally:
            store.close()

    def test_calendar_dayfirst(self):
        import pandas as pd
        import tempfile
        import os
        store = M3.DuckDBStore()
        try:
            with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
                f.write("solar_date,lunar_year,lunar_month,lunar_day\n")
                f.write("05/02/2025,2024,12,23\n")
                path = f.name
            store.load_calendar(path)
            df = store.query("SELECT solar_date FROM calendar")
            self.assertEqual(str(df.iloc[0]["solar_date"])[:10], "2025-02-05")
        finally:
            store.close()
            os.unlink(path)


# ---------------------------------------------------------------------------
# 04: typed canonicalisation, reject-all, strict majority, schema helper
# ---------------------------------------------------------------------------

class Test04Canonicalisation(unittest.TestCase):
    def test_bool_not_equal_to_number(self):
        """Regression: outputs_equal(True, 1) used to be True."""
        self.assertFalse(M4.outputs_equal(True, 1))
        self.assertFalse(M4.outputs_equal(False, 0))

    def test_int_float_equivalent(self):
        self.assertTrue(M4.outputs_equal(1, 1.0))
        self.assertTrue(M4.outputs_equal(1250000, 1250000.0))

    def test_number_string_not_equal(self):
        self.assertFalse(M4.outputs_equal(1, "1"))

    def test_date_object_not_equal_to_date_string(self):
        import datetime
        self.assertFalse(M4.outputs_equal(datetime.date(2025, 1, 1), "2025-01-01"))
        self.assertTrue(M4.outputs_equal(datetime.date(2025, 1, 1),
                                         datetime.date(2025, 1, 1)))


class Test04Consensus(unittest.TestCase):
    def R(self, output):
        return M4.CandidateResult(code="c", output=output)

    def test_minority_two_of_five_is_not_majority(self):
        """Regression: 2/5 used to be returned as an answer."""
        d = M4.decide_consensus([self.R(10), self.R(10), self.R(20),
                                 self.R(30), self.R(40)])
        self.assertEqual(d.kind, "abstain")

    def test_tie_two_of_four_is_not_majority(self):
        d = M4.decide_consensus([self.R(10), self.R(10), self.R(20), self.R(20)])
        self.assertEqual(d.kind, "abstain")

    def test_two_of_three_is_majority(self):
        d = M4.decide_consensus([self.R(10), self.R(10), self.R(20)])
        self.assertEqual(d.kind, "answer")
        self.assertEqual(d.value, 10)

    def test_failed_candidates_excluded_from_denominator(self):
        d = M4.decide_consensus([
            self.R(10), self.R(10),
            M4.CandidateResult(code="bad", error="timeout"),
            M4.CandidateResult(code="bad2", error="timeout"),
        ])
        self.assertEqual(d.kind, "answer")
        self.assertIn("4 attempted, 2 failed", d.reasons[0])

    def test_count_zero_is_an_answer_not_empty(self):
        d = M4.decide_consensus([self.R(0), self.R(0), self.R(0)])
        self.assertEqual(d.kind, "answer")
        self.assertEqual(d.value, 0)

    def test_empty_list_abstains_by_default_but_not_with_evidence(self):
        d = M4.decide_consensus([self.R([]), self.R([]), self.R([])])
        self.assertEqual(d.kind, "abstain")
        d2 = M4.decide_consensus([self.R([]), self.R([]), self.R([])],
                                 allow_empty_answer=True)
        self.assertEqual(d2.kind, "answer")


class Test04Calibration(unittest.TestCase):
    def test_reject_all_when_all_wrong(self):
        """Regression: one record (1.0, wrong) used to force answering."""
        thresholds = M4.learn_thresholds(
            [M4.CalibrationRecord(score=1.0, question_type="number", correct=False)],
            min_support=1)
        self.assertGreater(thresholds["number"], 1.0)
        holdout = M4.evaluate_holdout(
            [M4.CalibrationRecord(score=1.0, question_type="number", correct=False)],
            thresholds)
        self.assertEqual(holdout["pa"], 0.0)
        self.assertEqual(holdout["answered"], 0)

    def test_all_correct_keeps_answering(self):
        thresholds = M4.learn_thresholds(
            [M4.CalibrationRecord(score=1.0, question_type="number", correct=True)],
            min_support=1)
        self.assertLessEqual(thresholds["number"], 1.0)

    def test_tied_scores_all_correct_vs_all_wrong(self):
        wrong = M4.learn_thresholds(
            [M4.CalibrationRecord(score=0.5, question_type="number", correct=False)] * 3,
            min_support=1)
        # Any threshold above 0.5 abstains on all 0.5 scores (PA 0);
        # >1.0 is only required when the wrong score itself is 1.0.
        self.assertGreater(wrong["number"], 0.5)
        holdout = M4.evaluate_holdout(
            [M4.CalibrationRecord(score=0.5, question_type="number", correct=False)] * 3,
            wrong)
        self.assertEqual(holdout["pa"], 0.0)
        self.assertEqual(holdout["answered"], 0)
        right = M4.learn_thresholds(
            [M4.CalibrationRecord(score=0.5, question_type="number", correct=True)] * 3,
            min_support=1)
        self.assertLessEqual(right["number"], 0.5)

    def test_empty_calibration_fails_closed(self):
        thresholds = M4.learn_thresholds([], min_support=1)
        self.assertGreater(thresholds["__global__"], 1.0)

    def test_low_support_falls_back_to_global(self):
        records = (
            [M4.CalibrationRecord(score=0.9, question_type="number", correct=True)] * 40
            + [M4.CalibrationRecord(score=0.1, question_type="string", correct=False)]
        )
        thresholds = M4.learn_thresholds(records, min_support=30)
        self.assertEqual(thresholds["string"], thresholds["__global__"])

    def test_decide_question_uses_same_threshold_semantics(self):
        # score >= threshold answers; below abstains; reject-all abstains.
        full = M4.SchemaCoverage(fallback_tried=True)
        answered = M4.decide_question(
            coverage=full, candidates=["a", "b", "c"],
            executor=M4._fake_executor([42, 42, 42]),
            thresholds={"__global__": 0.5},
            gates=M4.GateReport(rule_assertions_pass=True, evidence_coverage=1.0,
                                second_path_agrees=True))
        self.assertEqual(answered.kind, "answer")
        abstained = M4.decide_question(
            coverage=full, candidates=["a", "b", "c"],
            executor=M4._fake_executor([42, 42, 42]),
            thresholds={"__global__": M4.REJECT_ALL_THRESHOLD},
            gates=M4.GateReport(rule_assertions_pass=True, evidence_coverage=1.0,
                                second_path_agrees=True))
        self.assertEqual(abstained.kind, "abstain")


class Test04SchemaCoverage(unittest.TestCase):
    def test_alias_finds_column_planner_missed(self):
        """A planner shortlist miss is not missing data."""
        cov = M4.check_schema_coverage(
            required_tables=["orders"], required_columns=["discount_amount"],
            available_tables=["orders"],
            available_columns=["DiscountAmount"],
            aliases={"discount_amount": ["discount", "ck"]})
        self.assertTrue(cov.is_complete)
        self.assertTrue(cov.fallback_tried)

    def test_truly_missing_column_still_unanswerable(self):
        cov = M4.check_schema_coverage(
            required_tables=["orders"], required_columns=["discount_amount"],
            available_tables=["orders"], available_columns=["price"])
        decision = M4.decide_unanswerable(cov)
        self.assertIsNotNone(decision)
        self.assertEqual(decision.kind, "unanswerable")

    def test_planner_shortlist_alone_never_concludes(self):
        cov = M4.SchemaCoverage(missing_columns=("discount_amount",),
                                fallback_tried=False)
        self.assertIsNone(M4.decide_unanswerable(cov))


if __name__ == "__main__":
    unittest.main()
