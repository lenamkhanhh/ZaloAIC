"""R4 pending_ask_stop (variant, default OFF) + agent roster backfill.

REVISED contract (supersedes the c0f7a9a pending-key contract in
full): when the flag is ON, a sys.ask_missing_info that env.call
executes SUCCESSFULLY (result ok is True) ends the turn IMMEDIATELY,
with that ask kept in the submission. The generator is not called
again after that ask, and no read / write / further ask runs after
it. There is NO post-ask-read leaf exception in this contract: the
same value in a later read does not prove the right slot/intent,
and any continuation after an ask is a separate research direction,
not part of this candidate. Distinct-key asks after a successful
ask are therefore NOT allowed in this contract either — the turn
is already over.

The two non-success cases do NOT trigger this rule, and follow the
old flow:
  * an ask validation rejects -> it never reaches env.call; the
    loop retries with the next generation (old validation flow);
  * an ask whose env.call returns ok False -> it is not a
    successful ask; the loop continues via guard / re-prompt.

Self-contained: real AgentLoop, scripted generator, permissive
FakeEnv with canned contacts.search results. No LifeMate data, no
simulator, no model — what is proven is loop order and the loop's
own roster.

Roster backfill (agent.py, unconditional task-1 change, NOT gated
by the flag), as superseded for conflicts by R4-CONFLICT: a later
successful contacts.search for an id already in the roster
supplements missing fields and replaces a differing valid field
(last-wins) — never overwrites with an empty value, never appends
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
from lifemate.lifemate_gates_adapter import decide

KINDS = {"phone.call": "write", "sms.send": "write"}

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
REMINDER_ISO = {"name": "reminders.create",
                "arguments": {"time": "2026-10-31T08:00:00+07:00",
                              "content": "họp"}}
SEARCH_LAN = {"name": "contacts.search", "arguments": {"query": "Lan"}}


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


class AskValidateFailOnceEnv(FakeEnv):
    """Rejects the FIRST ask at validation only; later validations
    pass. The rejected ask never reaches env.call."""

    def __init__(self, search=None):
        super().__init__(search=search)
        self._ask_validate_failed = False

    def validate(self, name, arguments):
        if name == "sys.ask_missing_info" and not self._ask_validate_failed:
            self._ask_validate_failed = True
            return {"ok": False, "error": "schema"}
        return {"ok": True}


class AskCallFailEnv(FakeEnv):
    """Ask executes but returns ok False (execution failure)."""

    def call(self, name, arguments):
        if name == "sys.ask_missing_info":
            self.calls.append({"name": name, "arguments": arguments})
            return {"ok": False, "error": "ask failed"}
        return super().call(name, arguments)


def run(proposals, search=None, pending=False, env_cls=FakeEnv):
    gen = CountingGen(proposals)
    env = env_cls(search=search)
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

    def test_off_ask_does_not_end_turn(self):
        # OFF: after a successful ask the loop keeps going, so a
        # second (distinct) ask still executes.
        loop, out, gen = run([dict(TAIL), dict(TIME_TAIL)], pending=False)
        self.assertEqual(len(out["tool_calls"]), 2)
        self.assertEqual(out["tool_calls"][0], ASK_PHONE)
        self.assertEqual(gen.proposals, 2)

    def test_off_ask_then_invented_write_executes(self):
        loop, out, gen = run(
            [dict(SEARCH_LAN),
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


class TestPendingOnSuccessEndsTurn(unittest.TestCase):
    def test_on_successful_ask_then_next_ask_does_not_run(self):
        loop, out, gen = run([dict(TAIL), dict(TIME_TAIL)], pending=True)
        self.assertEqual(out["tool_calls"], [ASK_PHONE])
        self.assertEqual(gen.proposals, 1)

    def test_on_successful_ask_then_read_does_not_run(self):
        loop, out, gen = run(
            [dict(TAIL), dict(SEARCH_LAN)],
            search={"Lan": [{"id": "c1", "name": "Lan"}]},
            pending=True)
        self.assertEqual(out["tool_calls"], [ASK_PHONE])
        self.assertEqual(gen.proposals, 1)

    def test_on_successful_ask_then_write_does_not_run(self):
        loop, out, gen = run([dict(TAIL), dict(REMINDER_ISO)], pending=True)
        self.assertEqual(out["tool_calls"], [ASK_PHONE])
        self.assertEqual(gen.proposals, 1)

    def test_on_successful_ask_then_all_kinds_do_not_run(self):
        loop, out, gen = run(
            [dict(TAIL), dict(TIME_TAIL), dict(SEARCH_LAN),
             dict(REMINDER_ISO)],
            search={"Lan": [{"id": "c1", "name": "Lan"}]},
            pending=True)
        self.assertEqual(out["tool_calls"], [ASK_PHONE])
        self.assertEqual(gen.proposals, 1)

    def test_on_successful_ask_mid_trace_kept_and_turn_ends(self):
        loop, out, gen = run(
            [dict(SEARCH_LAN), dict(TAIL), dict(REMINDER_ISO)],
            search={"Lan": [{"id": "c1", "name": "Lan"}]},
            pending=True)
        self.assertEqual(out["tool_calls"], [dict(SEARCH_LAN), ASK_PHONE])
        self.assertEqual(gen.proposals, 2)


class TestPendingOnNonSuccessDoesNotEndTurn(unittest.TestCase):
    def test_on_validation_rejected_ask_does_not_end_turn(self):
        # Ask validation fails once, so the ask never reaches
        # env.call; the loop retries with the next generation and
        # that generation (a reminder write) executes. No ask is in
        # the submission, because the ask was never executed.
        loop, out, gen = run([dict(TAIL), dict(REMINDER_ISO)],
                             pending=True,
                             env_cls=AskValidateFailOnceEnv)
        self.assertEqual(out["tool_calls"], [dict(REMINDER_ISO)])
        self.assertEqual(gen.proposals, 2)

    def test_on_execution_failed_ask_does_not_end_turn(self):
        # Ask executes with ok False, so it is not a successful ask;
        # the old flow continues and the next proposal executes.
        loop, out, gen = run([dict(TAIL), dict(REMINDER_ISO)],
                             pending=True, env_cls=AskCallFailEnv)
        self.assertEqual(out["tool_calls"],
                         [ASK_PHONE, dict(REMINDER_ISO)])
        self.assertEqual(gen.proposals, 2)


class TestRosterBackfill(unittest.TestCase):
    def _roster_after(self, search, pending=False):
        loop, out, gen = run(
            [dict(SEARCH_LAN),
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

    def test_backfill_last_wins_on_conflict(self):
        loop, out = self._roster_after(
            {"Lan": [{"id": "c1", "name": "Lan", "phone": "0901111111"}],
             "Lan2": [{"id": "c1", "name": "Lan", "phone": "0902222222",
                       "relation": "đồng nghiệp"}]})
        self.assertEqual(len(loop._roster), 1)
        # Last-wins (R4-CONFLICT rule change, not a dodged
        # case): the later valid phone replaces the first.
        self.assertEqual(loop._roster[0]["phone"], "0902222222")
        self.assertEqual(loop._roster[0]["relation"], "đồng nghiệp")
        self.assertTrue(any(
            c["reason"] == "last_wins" and c["field"] == "phone"
            for c in loop.roster_conflicts))
        # F-1 counterproof (decision, not just roster value):
        # the loop's OWN c1 entry, plus a second Lan, decided
        # through the adapter. The NEW phone selects c1; the
        # OLD phone no longer does. If the loop still kept
        # the first phone, these two calls invert (the new
        # phone fires, the old phone passes), so flipping
        # the roster assertion above alone cannot make
        # this test pass while decision behaviour is unchanged.
        roster = list(loop._roster) + [
            {"id": "c2", "name": "Lan", "phone": "0903777888",
             "relation": "hàng xóm"}]
        for phone, want_fired in (("0902222222", False),
                                  ("0901111111", True)):
            dec = decide(
                {"name": "phone.call",
                 "arguments": {"phone_number": phone}},
                [{"kind": "user_turn",
                  "text": "Tìm số của Lan %s dùm tôi" % phone,
                  "position": 0}],
                roster, "Gọi cho Lan", KINDS, proposal_position=1)
            if want_fired:
                self.assertTrue(dec.fired, dec)
            else:
                self.assertFalse(dec.fired, dec)

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
