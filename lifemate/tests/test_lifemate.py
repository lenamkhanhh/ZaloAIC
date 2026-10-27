"""Tests for lifemate/ — run against the real extracted package.

Data path: env LIFEMATE_DATA, defaulting to the dev VM extraction.
Tests SKIP (not fail) when the data dir is absent, so the suite stays
green on machines that have not downloaded the dataset yet. No test
reads anything under <split>_environment/ directly; state access goes
through zaic_tools, and get_state() appears only in the diagnostic
gold-replay test, labelled as such.
"""
import json
import os
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from lifemate.adapter import ZaicEnv
from lifemate.agent import AgentLoop
from lifemate.config import PipelineConfig
from lifemate.grounding import ground_name, parse_date, parse_money, normalise_id
from lifemate.loader import catalog_tools_for_sample, load_catalog, load_split
from lifemate.scoring import score_sample, token_f1, tool_f1
from lifemate.split import make_split

DATA = Path(os.environ.get(
    "LIFEMATE_DATA",
    str(Path.home() / "workspace/zaic-data/lifemate/extracted/train+public_test"),
))
HAS_DATA = (DATA / "train" / "train.jsonl").is_file()


@unittest.skipUnless(HAS_DATA, "LifeMate data not extracted (set LIFEMATE_DATA)")
class TestLoaderRealData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.train = load_split(DATA, "train")
        cls.pub = load_split(DATA, "public_test")
        cls.train_cat = load_catalog(DATA, "train")
        cls.pub_cat = load_catalog(DATA, "public_test")

    def test_counts_and_keys(self):
        self.assertEqual(len(self.train), 1545)
        self.assertEqual(len(self.pub), 634)
        for s in self.train:
            self.assertIsNotNone(s.audio_text)
            self.assertIsNotNone(s.label)
        for s in self.pub:
            self.assertIsNone(s.audio_text)
            self.assertIsNone(s.label)

    def test_catalog_sizes(self):
        n_train = sum(len(a["tools"]) for a in self.train_cat["apps"])
        n_pub = sum(len(a["tools"]) for a in self.pub_cat["apps"])
        self.assertEqual(n_train, 147)
        self.assertEqual(n_pub, 122)

    def test_installed_tools_subset_of_catalog(self):
        tools = catalog_tools_for_sample(self.train_cat, self.train[0])
        self.assertTrue(set(tools) <= {t["name"] for a in self.train_cat["apps"] for t in a["tools"]})
        self.assertIn("sys.ask_missing_info", tools)


@unittest.skipUnless(HAS_DATA, "LifeMate data not extracted (set LIFEMATE_DATA)")
class TestSplit(unittest.TestCase):
    def test_deterministic_and_stratified(self):
        train = load_split(DATA, "train")
        a = make_split(train, seed=42, heldout_frac=0.2)
        b = make_split(train, seed=42, heldout_frac=0.2)
        self.assertEqual(a, b)
        self.assertEqual(len(a), 1545)
        held = [s for s in train if a[s.id] == "heldout"]
        self.assertTrue(280 <= len(held) <= 340, len(held))
        for cls in ("empty", "ask_only", "ask_after", "normal"):
            members = [s for s in train if s.label_class() == cls]
            h = [s for s in members if a[s.id] == "heldout"]
            self.assertTrue(0.15 <= len(h) / len(members) <= 0.25, (cls, len(h), len(members)))


@unittest.skipUnless(HAS_DATA, "LifeMate data not extracted (set LIFEMATE_DATA)")
class TestAdapterRealEnv(unittest.TestCase):
    def test_validate_is_not_logged_and_read_does_not_change_hash(self):
        train = load_split(DATA, "train")
        cat = load_catalog(DATA, "train")
        sample = train[0]
        tools = catalog_tools_for_sample(cat, sample)
        env = ZaicEnv(DATA, "train", sample.id)
        h0 = env.state_hash()
        # A schema-invalid validation must NOT appear in the trace:
        # sms.send requires contact_id, so content-only fails validation.
        check = env.validate("sms.send", {"content": "hi"})
        self.assertFalse(check.get("ok"))
        self.assertEqual(env.tool_calls(), [])
        # Find a no-required-arg read tool for this sample and call it.
        read_tool = next(
            (name for name, spec in tools.items()
             if spec["kind"] == "read" and not spec["parameters"].get("required")),
            None,
        )
        self.assertIsNotNone(read_tool)
        result = env.call(read_tool, {})
        self.assertTrue(result.get("ok"))
        self.assertEqual(env.state_hash(), h0)  # reads do not change state
        self.assertEqual(len(env.tool_calls()), 1)

    def test_gold_replay_changed_apps_match_final_state(self):
        # DIAGNOSTIC ONLY: get_state() on replay sessions, never agent input.
        train = load_split(DATA, "train")
        for sample in train[:5]:
            init = ZaicEnv(DATA, "train", sample.id)._env.get_state()
            env = ZaicEnv(DATA, "train", sample.id)
            for call in sample.label["tool_calls"]:
                env.call(call["name"], call["arguments"])
            final = env._env.get_state()
            changed = {a: s for a, s in final.items() if s != init.get(a)}
            self.assertEqual(changed, sample.label["final_state"], sample.id)
            self.assertEqual(env.tool_calls(), sample.label["tool_calls"])


class TestGrounding(unittest.TestCase):
    def test_money_keeps_sign_and_units(self):
        from decimal import Decimal
        self.assertEqual(parse_money("1,5 triệu"), Decimal("1500000"))
        self.assertEqual(parse_money("-100"), Decimal("-100"))
        self.assertEqual(parse_money("(100)"), Decimal("-100"))
        self.assertIsNone(parse_money("1.500"))  # ambiguous, never guessed

    def test_date_rejects_invalid_calendar(self):
        self.assertEqual(parse_date("15/7", year_hint=2025), "2025-07-15")
        self.assertIsNone(parse_date("31/02/2025"))

    def test_id_keeps_leading_zeros(self):
        self.assertEqual(normalise_id("090 123 4567"), "0901234567")
        self.assertEqual(normalise_id("c-08"), "C08")  # separators stripped, letters kept

    def test_same_display_different_entities_is_ambiguous(self):
        # Correction: existence does not prove intent.
        res = ground_name("An", [("c_01", "An"), ("c_02", "An")])
        self.assertEqual(res.status, "AMBIGUOUS")
        res = ground_name("An", [("c_01", "An")])
        self.assertEqual(res.status, "EXACT")


class TestScoring(unittest.TestCase):
    def test_token_f1_and_empty_rule(self):
        # P=3/3, R=3/4 -> F1 = 2*1*0.75/1.75 = 0.857
        self.assertAlmostEqual(token_f1("mai chạy bộ", "mai chạy bộ nhé"), 0.857, places=3)
        self.assertEqual(tool_f1([], [], {}), 1.0)
        self.assertEqual(tool_f1([{"name": "a", "arguments": {}}], [], {}), 0.0)

    def test_hash_gate(self):
        from lifemate.loader import Sample
        sample = Sample(id="x", split="train", audio="a.wav", context={"installed_apps": {}},
                        history=[], label={"tool_calls": [], "tool_results": [], "final_state": {}})
        line = {"id": "x", "tool_calls": [], "state_hash": "abc"}
        self.assertEqual(score_sample(line, sample, "abc", {})["score"], 1.0)
        self.assertEqual(score_sample(line, sample, "zzz", {})["score"], 0.0)


@unittest.skipUnless(HAS_DATA, "LifeMate data not extracted (set LIFEMATE_DATA)")
class TestAgentMechanics(unittest.TestCase):
    def test_empty_policy_submission_is_replay_consistent(self):
        train = load_split(DATA, "train")
        sample = train[0]
        env = ZaicEnv(DATA, "train", sample.id)
        line = env.submission_line()
        self.assertEqual(line["tool_calls"], [])
        env2 = ZaicEnv(DATA, "train", sample.id)
        self.assertEqual(env2.state_hash(), line["state_hash"])


if __name__ == "__main__":
    unittest.main()
