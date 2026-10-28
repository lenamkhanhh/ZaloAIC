"""Integration tests for the grounding hook in lifemate/agent.py (round 8).

Test 1 (dormant): grounding=False (and the default config) runs the loop
byte-identical — scripted gold calls come out unchanged, grounding_log
stays empty, no ask is ever emitted by the hook.

Test 2 (grounding): grounding=True normalises word money to int, relative
dates to ISO, and turns duplicate / missing-hour / unknown-name proposals
into sys.ask_missing_info with the gold-shaped params. The roster is
accumulated from contacts.search RESULTS observed in the trace.

Test 3 (leftover-name): with no roster yet, a contact_name proposal must
NOT be executed (validate() ignores unknown args, so executing it would
run the tool without the contact) — it becomes an ask instead.

Validation in Test 2/3 goes through a REAL ZaicEnv (schema check only,
no state change); execution is a fake env with canned search results so
the roster is fully deterministic and data-independent. No test reads
anything under <split>_environment/ directly.
"""
import os
import unittest
from pathlib import Path
from types import SimpleNamespace

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lifemate.adapter import ZaicEnv
from lifemate.agent import AgentLoop
from lifemate.config import PipelineConfig
from lifemate.loader import catalog_tools_for_sample, load_catalog, load_split

DATA = Path(os.environ.get(
    "LIFEMATE_DATA",
    str(Path.home() / "workspace/zaic-data/lifemate/extracted/train+public_test"),
))
HAS_DATA = (DATA / "train" / "train.jsonl").is_file()
NEEDED_TOOLS = {"ewallet.transfer", "reminders.create", "contacts.search",
                "sms.send", "phone.call", "sys.ask_missing_info"}


def scripted(calls):
    """Generator yielding the given calls in order, then None."""
    queue = list(calls)

    def gen(prompt, tools):
        if not queue:
            return None
        return queue.pop(0)

    return gen


class FakeEnv:
    """Execution double: real validation, canned search results.

    validate() delegates to a real ZaicEnv (schema check only), so every
    executed call in the tests is proven to pass REAL validation.
    call() records calls and returns canned contacts.search results;
    other calls return ok/done without touching real state.
    """

    def __init__(self, real_env, search_results, sample_id):
        self._real = real_env
        self._search_results = search_results
        self.sample_id = sample_id
        self.calls = []

    def validate(self, name, arguments):
        return self._real.validate(name, arguments)

    def call(self, name, arguments):
        self.calls.append({"name": name, "arguments": arguments})
        if name == "contacts.search":
            return {"ok": True,
                    "contacts": self._search_results.get(arguments.get("query"), [])}
        return {"ok": True, "done": True}

    def tool_calls(self):
        return list(self.calls)

    def submission_line(self):
        return {"id": self.sample_id, "tool_calls": self.tool_calls(),
                "state_hash": "fake"}


@unittest.skipUnless(HAS_DATA, "LifeMate data not extracted (set LIFEMATE_DATA)")
class TestGroundingHookDormant(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.train = load_split(DATA, "train")
        cls.catalog = load_catalog(DATA, "train")

    def _pick_gold_sample(self):
        """First train sample with 2..12 distinct gold calls (guard- and
        step-safe, so a dormant loop must reproduce them exactly)."""
        for s in self.train:
            gold = s.label["tool_calls"]
            if 2 <= len(gold) <= 12 \
                    and len({str(c) for c in gold}) == len(gold):
                return s
        self.fail("no suitable gold sample found")

    def _run_dormant(self, config):
        sample = self._pick_gold_sample()
        tools = catalog_tools_for_sample(self.catalog, sample)
        env = ZaicEnv(DATA, "train", sample.id)
        loop = AgentLoop(config, tools)
        out = loop.run(sample, sample.audio_text, env,
                       scripted(sample.label["tool_calls"]))
        return sample, loop, out

    def test_grounding_false_is_byte_identical(self):
        sample, loop, out = self._run_dormant(
            PipelineConfig(grounding=False))
        self.assertEqual(out["tool_calls"], sample.label["tool_calls"])
        self.assertEqual(loop.grounding_log, [])
        self.assertIsNone(loop._roster)

    def test_default_config_is_off(self):
        self.assertFalse(PipelineConfig().grounding)
        sample, loop, out = self._run_dormant(PipelineConfig())
        self.assertEqual(out["tool_calls"], sample.label["tool_calls"])
        self.assertEqual(loop.grounding_log, [])


@unittest.skipUnless(HAS_DATA, "LifeMate data not extracted (set LIFEMATE_DATA)")
class TestGroundingHookActive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.train = load_split(DATA, "train")
        cls.catalog = load_catalog(DATA, "train")
        # A real sample whose installed tools cover the scripted trace;
        # used ONLY for real schema validation, never for its state.
        for s in cls.train:
            if NEEDED_TOOLS <= set(s.installed_tools):
                cls.val_sample = s
                break
        else:
            raise AssertionError("no sample with all needed tools")

    def _run_trace(self, proposals, search_results):
        real = ZaicEnv(DATA, "train", self.val_sample.id)
        env = FakeEnv(real, search_results, self.val_sample.id)
        sample = SimpleNamespace(
            context={"current_time": "2026-11-28T07:00:00+07:00",
                     "timezone": "Asia/Saigon",
                     "user_profile": {"name": "Test", "city": "HCM"},
                     "installed_apps": {}},
            history=[],
        )
        loop = AgentLoop(PipelineConfig(grounding=True), {})
        out = loop.run(sample, "test", env, scripted(proposals))
        # Every executed call must pass REAL validation (checked after
        # the run; validate() is side-effect-free).
        for c in out["tool_calls"]:
            check = real.validate(c["name"], c["arguments"])
            self.assertTrue(check.get("ok"), (c, check))
        return loop, out

    def test_money_date_contacts_and_asks(self):
        proposals = [
            {"name": "ewallet.transfer",
             "arguments": {"amount": "năm mươi nghìn", "contact_id": "c_01"}},
            {"name": "reminders.create",
             "arguments": {"time": "ngày mai lúc 8 giờ", "content": "họp"}},
            {"name": "contacts.search", "arguments": {"query": "Lan"}},
            {"name": "sms.send",
             "arguments": {"contact_name": "Lan", "content": "hi"}},
            {"name": "contacts.search", "arguments": {"query": "Minh"}},
            {"name": "phone.call", "arguments": {"contact_name": "Minh"}},
            {"name": "reminders.create",
             "arguments": {"time": "sáng mai", "content": "họp"}},
            {"name": "sms.send",
             "arguments": {"contact_name": "Người Lạ", "content": "hi"}},
        ]
        search_results = {
            "Lan": [{"id": "c_11", "name": "Lan"}],
            "Minh": [{"id": "c_05", "name": "Minh"},
                     {"id": "c_08", "name": "Minh"}],
        }
        loop, out = self._run_trace(proposals, search_results)
        calls = out["tool_calls"]
        self.assertEqual(len(calls), 8)
        # 1. Word money -> int.
        self.assertEqual(calls[0]["arguments"]["amount"], 50000)
        self.assertIsInstance(calls[0]["arguments"]["amount"], int)
        # 2. Relative date + explicit hour -> ISO datetime.
        self.assertEqual(calls[1]["arguments"]["time"],
                         "2026-11-29T08:00:00+07:00")
        # 3. Search passes through unchanged.
        self.assertEqual(calls[2], proposals[2])
        # 4. Name grounded from the observed search result.
        self.assertEqual(calls[3]["arguments"]["contact_id"], "c_11")
        self.assertNotIn("contact_name", calls[3]["arguments"])
        # 5. Second search passes through unchanged.
        self.assertEqual(calls[4], proposals[4])
        # 6. Duplicate name -> ask for contact_id.
        self.assertEqual(calls[5], {"name": "sys.ask_missing_info",
                                    "arguments": {"tool_name": "phone.call",
                                                  "params": ["contact_id"]}})
        # 7. Daypart without hour -> ask for time.
        self.assertEqual(calls[6], {"name": "sys.ask_missing_info",
                                    "arguments": {"tool_name": "reminders.create",
                                                  "params": ["time"]}})
        # 8. Unknown name (roster exists, no match) -> ask for contact_id.
        self.assertEqual(calls[7], {"name": "sys.ask_missing_info",
                                    "arguments": {"tool_name": "sms.send",
                                                  "params": ["contact_id"]}})
        # Audit log: one entry per proposal, raw preserved.
        self.assertEqual(len(loop.grounding_log), 8)
        self.assertEqual(loop.grounding_log[0]["raw"], proposals[0])
        self.assertEqual(loop.grounding_log[0]["grounded"].status, "GROUNDED")
        self.assertEqual(loop.grounding_log[5]["grounded"].status, "NEEDS_ASK")
        self.assertIn("contact:ambiguous",
                      loop.grounding_log[5]["grounded"].needs)

    def test_leftover_name_without_roster_becomes_ask(self):
        proposals = [
            {"name": "phone.call", "arguments": {"contact_name": "Ai Đó"}},
        ]
        loop, out = self._run_trace(proposals, {})
        self.assertEqual(out["tool_calls"],
                         [{"name": "sys.ask_missing_info",
                           "arguments": {"tool_name": "phone.call",
                                         "params": ["contact_id"]}}])
        self.assertEqual(len(loop.grounding_log), 1)
        self.assertEqual(loop.grounding_log[0]["grounded"].status, "UNCHANGED")


if __name__ == "__main__":
    unittest.main()
