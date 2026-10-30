"""R4 pending_ask_stop (variant, default OFF) + agent roster backfill.

Self-contained: real AgentLoop, scripted generator, permissive FakeEnv
with canned contacts.search results. No LifeMate data, no simulator,
no model — what is proven is loop order and the loop's own roster.

pending_ask_stop semantics (agent.py, flag ON only):
  * a successful sys.ask_missing_info opens pending key
    (tool_name, params-tuple);
  * a later proposal that would become the SAME ask ends the turn
    with no second ask and no env.call for that proposal;
  * a later write filling a pending slot ends the turn with no
    env.call unless its exact value appeared as a leaf of a read
    result executed AFTER that ask (post-ask reads only);
  * a different (tool, params) ask is still allowed, and a write for
    an unrelated slot is unchanged.

Roster backfill (agent.py, unconditional task-1 change, NOT gated by
the flag): a later successful contacts.search for an id already in
the roster supplements missing fields only — never overwrites a
non-empty field, never overwrites with an empty value, never appends
a duplicate entry. Backfill mutates the roster copy, not the search
result's own dict.

Well-formed fabrication on a FIRST proposal (no prior ask) is NOT
closed by this variant and is not tested as closed here.
"""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lifemate.agent import AgentLoop
from lifemate.config import PipelineConfig

TOOLS = {
    "contacts.search": {"kind": "read", "parameters": {"required": ["query"]},
     "description": "search"},
    "contacts.update": {"kind": "write", "parameters": {"required": ["contact_id"]},
     "description": "update"},
    "reminders.create": {"kind": "write", "parameters": {"required": []},
     "description": "create reminder"},
    "phone.call": {"kind": "write", "parameters": {"required": []},
     "description": "call"},
    "sms.send": {"kind": "write", "parameters": {"required": []},
     "description": "send sms"},
    "sys.ask_missing_info": {"kind": "write", "parameters": {"required": []},
     "description": "ask"},
}
CTX = {"current_time": "2026-10-30T09:00:00+07:00", "timezone": "Asia/Saigon",
       "user_profile": {"name": "Test", "city": "HCM"}, "installed_apps": {}}
TAIL = {"name": "contacts.update",
        "arguments": {"contact_id": "c1", "phone": "đuôi 222"}}
ASK_PHONE = {"name": "sys.ask_missing_info",
             "arguments": {"tool_name": "contacts.update", "params": ["phone"]}}
TIME_TAIL = {"name": "reminders.create",
             "arguments": {"time": "sáng mai", "content": "họp"}}
ASK_TIME = {"name": "sys.ask_missing_info",
            "arguments": {"tool_name": "reminders.create", "params": ["time"]}}


class CountingGen:
    def __init__(self, proposals):
        self.queue = list(proposals)
        self.proposals = 0

    def __call__(self, prompt, tools):
        if not self.queue:
            return None
        self.proposals += 1
        return self.queue.pop(0)


class FakeEnv:
    def __init__(self, search=None):
        self.search = search or {}
        self.calls = []

    def validate(self, name, arguments):
        return {"ok": True}

    def call(self, name, arguments):
        self.calls.append({"name": name, "arguments": arguments})
        if name == "contacts.search":
            return {"ok": True,
                    "contacts": self.search.get(arguments.get("query"), [])}
        if name == "contacts.update":
            return {"ok": True, "item": {"id": arguments.get("contact_id"),
                                         "phone": arguments.get("phone")}}
        if name == "sys.ask_missing_info":
            return {"ok": True, "waiting_for_user": True}
        return {"ok": True, "done": True}

    def tool_calls(self):
        return list(self.calls)

    def submission_line(self):
        return {"id": "fake", "tool_calls": self.tool_calls(),
                "state_hash": "fake"}


def run(proposals, search=None, pending=False):
    gen = CountingGen(proposals)
    env = FakeEnv(search=search)
    sample = SimpleNamespace(context=dict(CTX), history=[])
    loop = AgentLoop(
        PipelineConfig(grounding=True, shadow_observer=False,
                       pending_ask_stop=pending), TOOLS)
    out = loop.run(sample, "gọi cho Lan", env, gen)
    return loop, out, gen


class TestPendingOff(unittest.TestCase):
    def test_default_config_is_off(self):
        self.assertFalse(PipelineConfig().pending_ask_stop)

    def test_off_repeat_tail_is_baseline_two_asks(self):
        loop, out, gen = run([dict(TAIL)] * 6, pending=False)
        self.assertEqual(out["tool_calls"], [ASK_PHONE, ASK_PHONE])
        self.assertEqual(gen.proposals, 3)

    def test_off_ask_then_invented_write_executes(self):
        loop, out, gen = run(
            [{"name": "contacts.search", "arguments": {"query": "Lan"}},
             dict(TAIL),
             {"name": "contacts.update",
              "arguments": {"contact_id": "c1", "phone": "0903111222"}}],
            search={"Lan": [{"id": "c1", "name": "Lan",
                             "phone": "0901111111"}]},
            pending=False)
        self.assertEqual(
            out["tool_calls"][2],
            {"name": "contacts.update",
             "arguments": {"contact_id": "c1", "phone": "0903111222"}})


class TestPendingOn(unittest.TestCase):
    def test_on_repeat_tail_stops_after_one_ask(self):
        loop, out, gen = run([dict(TAIL)] * 6, pending=True)
        self.assertEqual(out["tool_calls"], [ASK_PHONE])
        # 1st proposal -> ask, 2nd proposal -> pending stop; the
        # remaining proposals are never consumed.
        self.assertEqual(gen.proposals, 2)

    def test_on_distinct_ask_allowed_then_repeat_stops(self):
        loop, out, gen = run([dict(TAIL), dict(TIME_TAIL), dict(TAIL)],
                             pending=True)
        self.assertEqual(out["tool_calls"], [ASK_PHONE, ASK_TIME])
        self.assertEqual(gen.proposals, 3)

    def test_on_three_distinct_asks_preserved(self):
        loop, out, gen = run(
            [{"name": "contacts.search", "arguments": {"query": "Lan"}},
             dict(TAIL), dict(TIME_TAIL),
             {"name": "phone.call",
              "arguments": {"contact_name": "Người Lạ"}}],
            search={"Lan": [{"id": "c1", "name": "Lan"}]},
            pending=True)
        self.assertEqual(len(out["tool_calls"]), 4)
        asks = [c for c in out["tool_calls"]
                if c["name"] == "sys.ask_missing_info"]
        self.assertEqual(len(asks), 3)
        self.assertEqual(
            {(a["arguments"]["tool_name"], tuple(a["arguments"]["params"]))
             for a in asks},
            {("contacts.update", ("phone",)),
             ("reminders.create", ("time",)),
             ("phone.call", ("contact_id",))})

    def test_on_invented_write_after_ask_has_no_env_call(self):
        loop, out, gen = run(
            [{"name": "contacts.search", "arguments": {"query": "Lan"}},
             dict(TAIL),
             {"name": "contacts.update",
              "arguments": {"contact_id": "c1", "phone": "0903111222"}}],
            search={"Lan": [{"id": "c1", "name": "Lan",
                             "phone": "0901111111"}]},
            pending=True)
        self.assertEqual(
            out["tool_calls"],
            [{"name": "contacts.search", "arguments": {"query": "Lan"}},
             ASK_PHONE])

    def test_on_post_ask_read_without_value_does_not_unlock(self):
        loop, out, gen = run(
            [dict(TAIL),
             {"name": "contacts.search", "arguments": {"query": "Lan"}},
             {"name": "contacts.update",
              "arguments": {"contact_id": "c1", "phone": "0903111222"}}],
            search={"Lan": [{"id": "c1", "name": "Lan",
                             "phone": "0901111111"}]},
            pending=True)
        self.assertEqual(
            out["tool_calls"],
            [ASK_PHONE,
             {"name": "contacts.search", "arguments": {"query": "Lan"}}])

    def test_on_write_after_post_ask_read_with_value_allowed(self):
        loop, out, gen = run(
            [dict(TAIL),
             {"name": "contacts.search", "arguments": {"query": "Lan"}},
             {"name": "contacts.update",
              "arguments": {"contact_id": "c1", "phone": "0903111222"}}],
            search={"Lan": [{"id": "c1", "name": "Lan",
                             "phone": "0903111222"}]},
            pending=True)
        self.assertEqual(
            out["tool_calls"][2],
            {"name": "contacts.update",
             "arguments": {"contact_id": "c1", "phone": "0903111222"}})

    def test_on_unrelated_write_after_ask_unchanged(self):
        loop, out, gen = run(
            [dict(TAIL),
             {"name": "reminders.create",
              "arguments": {"time": "2026-10-31T08:00:00+07:00",
                            "content": "họp"}}],
            pending=True)
        self.assertEqual(out["tool_calls"][1]["name"], "reminders.create")


class TestRosterBackfill(unittest.TestCase):
    def _roster_after(self, search, pending=False):
        loop, out, gen = run(
            [{"name": "contacts.search", "arguments": {"query": "Lan"}},
             {"name": "contacts.search", "arguments": {"query": "Lan2"}}],
            search=search, pending=pending)
        return loop, out

    def test_backfill_missing_phone_and_relation(self):
        first = [{"id": "c1", "name": "Lan"}]
        loop, out = self._roster_after(
            {"Lan": first,
             "Lan2": [{"id": "c1", "name": "Lan", "phone": "0901111111",
                       "relation": "hàng xóm"}]})
        self.assertEqual(len(loop._roster), 1)
        self.assertEqual(loop._roster[0]["phone"], "0901111111")
        self.assertEqual(loop._roster[0]["relation"], "hàng xóm")
        # Backfill did not mutate the first search result's own dict.
        self.assertNotIn("phone", first[0])

    def test_backfill_keeps_first_on_conflict(self):
        loop, out = self._roster_after(
            {"Lan": [{"id": "c1", "name": "Lan", "phone": "0901111111"}],
             "Lan2": [{"id": "c1", "name": "Lan", "phone": "0902222222",
                       "relation": "đồng nghiệp"}]})
        self.assertEqual(len(loop._roster), 1)
        self.assertEqual(loop._roster[0]["phone"], "0901111111")
        self.assertEqual(loop._roster[0]["relation"], "đồng nghiệp")

    def test_backfill_never_overwrites_with_empty(self):
        loop, out = self._roster_after(
            {"Lan": [{"id": "c1", "name": "Lan", "phone": "0901111111"}],
             "Lan2": [{"id": "c1", "name": "Lan", "phone": ""}]})
        self.assertEqual(loop._roster[0]["phone"], "0901111111")

    def test_backfill_same_result_with_flag_on(self):
        loop, out = self._roster_after(
            {"Lan": [{"id": "c1", "name": "Lan"}],
             "Lan2": [{"id": "c1", "name": "Lan", "phone": "0901111111"}]},
            pending=True)
        self.assertEqual(len(loop._roster), 1)
        self.assertEqual(loop._roster[0]["phone"], "0901111111")


if __name__ == "__main__":
    unittest.main()
