#!/usr/bin/env python3
"""R4-CONFLICT: unified roster conflict rule, same expectations
in all three roster paths.

Paths:
  * observer: lifemate/lifemate_observer.py
    collect_rosters_from_prefix_with_conflicts (prefix events
    in order, barriers from contacts.update events).
  * harness: analysis/gg_paired_audit.py -- the list API
    collect_rosters for read-only cases, and the state API
    (_new_roster_state / _merge_group_into_state /
    _apply_barrier_to_state) for barrier cases, which is
    what main() uses.
  * agent: lifemate/agent.py -- the state API directly, plus
    real AgentLoop runs for the loop-level roster.

Rule under test (see the rule text in each production file):
last-wins for a differing valid field from a later successful
read, in event order; a missing/invalid value never
overwrites; a failed read creates/updates/deletes nothing;
absence in a read is not a deletion; a lifecycle-confirmed
contacts.update (succeeded, returned item id == its
contact_id argument) is a per-field barrier, and a later
read contradicting it makes that field UNKNOWN (dropped,
conflict recorded), not a choice; a single read
contradicting itself on a field makes that field UNKNOWN
for the same reason. Roster entries are always whitelist
only (id/name/phone/relation): no conflict/reason field
is ever stored inside an entry, because D1 reads every
other field as a structured attribute.

Synthetic only: no LifeMate data, no simulator, no model.
Paired gold 976 remains NOT_RUN on this VM (Codex step).

The keep-first tests this rule supersedes (observer
collector/runtime, harness, agent backfill) were updated
in their own files to last-wins; they are not duplicated
here, and no expected value here was weakened to pass.
"""

import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lifemate.agent import (  # noqa: E402
    AgentLoop, _agent_roster_entry, _apply_barrier_to_state,
    _barrier_entry_from_update, _group_read_entries,
    _merge_group_into_state, _new_roster_state)
from lifemate.config import PipelineConfig  # noqa: E402
from lifemate.lifemate_gates_adapter import decide  # noqa: E402
from lifemate.lifemate_observer import (  # noqa: E402
    collect_rosters_from_prefix_with_conflicts)

_SPEC = importlib.util.spec_from_file_location(
    "gg_paired_audit",
    Path(__file__).resolve().parent.parent
    / "analysis" / "gg_paired_audit.py")
_HARNESS = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_HARNESS)
collect_rosters = _HARNESS.collect_rosters

KINDS = {"contacts.search": "read", "sms.send": "write"}

LAN_FIRST = [
    {"id": "c1", "name": "Lan", "phone": "0903111222",
     "relation": "đồng nghiệp"},
    {"id": "c2", "name": "Lan", "phone": "0903777888",
     "relation": "hàng xóm"}]
LAN_SECOND = [
    {"id": "c1", "name": "Lan", "phone": "0903111222",
     "relation": "bạn bè"},
    {"id": "c2", "name": "Lan", "phone": "0903777888",
     "relation": "hàng xóm"}]
LAN_MISSING = [
    {"id": "c1", "name": "Lan", "phone": "0903111222"},
    {"id": "c2", "name": "Lan", "phone": "0903777888",
     "relation": "hàng xóm"}]


def obs_prefix(*events):
    """events: ("search", contacts, ok) or ("update", args, item, ok)."""
    prefix = []
    for pos, ev in enumerate(events):
        if ev[0] == "search":
            _kind, contacts, ok = ev
            prefix.append({"tool": "contacts.search", "args": {},
                           "result": {"ok": ok, "contacts": contacts},
                           "outcome": "succeeded" if ok
                           else "schema_rejected",
                           "position": pos, "origin": "session"})
        else:
            _kind, args, item, ok = ev
            prefix.append({"tool": "contacts.update", "args": args,
                           "result": {"ok": ok, "item": item},
                           "outcome": "succeeded" if ok
                           else "schema_rejected",
                           "position": pos, "origin": "session"})
    return prefix


def obs_roster(*events):
    return collect_rosters_from_prefix_with_conflicts(
        obs_prefix(*events))


def harness_roster(*reads):
    """reads: list of raw result dicts, in order, via the list API."""
    out = []
    for raw in reads:
        collect_rosters(raw, out)
    return out


def harness_state_roster(*ops):
    """ops: ("read", contacts) or ("barrier", args, item).
    Returns (roster, conflicts) via the state API main() uses."""
    state = _HARNESS._new_roster_state()
    seq = 0
    for op in ops:
        if op[0] == "read":
            entries = [_HARNESS._harness_roster_entry(e)
                       for e in op[1]]
            entries = [e for e in entries if e is not None]
            grouped, unknown_map = _HARNESS._group_read_entries(
                entries)
            _HARNESS._merge_group_into_state(
                state, grouped, unknown_map, seq)
        else:
            barrier = _HARNESS._barrier_entry_from_update(
                op[1], {"item": op[2]})
            assert barrier is not None, "test barrier must be valid"
            _HARNESS._apply_barrier_to_state(state, barrier, seq)
        seq += 1
    return state["entries"], state["conflicts"]


def agent_state_roster(*ops):
    """Same ops as harness_state_roster, via the agent state API."""
    state = _new_roster_state()
    for op in ops:
        if op[0] == "read":
            entries = [_agent_roster_entry(e) for e in op[1]]
            entries = [e for e in entries if e is not None]
            grouped, unknown_map = _group_read_entries(entries)
            _merge_group_into_state(state, grouped, unknown_map)
        else:
            barrier = _barrier_entry_from_update(
                op[1], {"item": op[2]})
            assert barrier is not None, "test barrier must be valid"
            _apply_barrier_to_state(state, barrier)
    return state["entries"], state["conflicts"]


def decide_for(contact_id, roster, descriptor):
    prefix = [{"kind": "user_turn",
               "text": "Tìm số của Lan %s dùm tôi" % descriptor,
               "position": 0}]
    return decide({"name": "sms.send",
                   "arguments": {"contact_id": contact_id}},
                  prefix, roster, "Nhắn tin cho Lan", KINDS,
                  proposal_position=1)


def assert_blocked(test, decision):
    test.assertTrue(decision.fired, decision.adjustments)
    test.assertTrue(any(a["mechanism"] == "selection_mismatch"
                        for a in decision.adjustments),
                    decision.adjustments)


class TestU1U2(unittest.TestCase):
    """U1: the newest relation selects the correct person.
    U2: the replaced relation no longer proves a choice."""

    def test_u1_new_relation_passes_correct_blocks_wrong(self):
        for roster in (
                obs_roster(("search", LAN_FIRST, True),
                           ("search", LAN_SECOND, True))[0],
                harness_roster(
                    {"ok": True, "contacts": LAN_FIRST},
                    {"ok": True, "contacts": LAN_SECOND})):
            self.assertEqual(roster[0]["relation"], "bạn bè")
            self.assertFalse(decide_for("c1", roster, "bạn bè").fired)
            assert_blocked(self, decide_for("c2", roster, "bạn bè"))

    def test_u2_old_relation_blocks_both(self):
        for roster in (
                obs_roster(("search", LAN_FIRST, True),
                           ("search", LAN_SECOND, True))[0],
                harness_roster(
                    {"ok": True, "contacts": LAN_FIRST},
                    {"ok": True, "contacts": LAN_SECOND})):
            # The old value is gone from the roster: a pass on
            # it would be a pass on superseded data.
            self.assertEqual(roster[0]["relation"], "bạn bè")
            assert_blocked(self, decide_for("c1", roster, "đồng nghiệp"))
            assert_blocked(self, decide_for("c2", roster, "đồng nghiệp"))

    def test_u_conflict_is_recorded_not_silent(self):
        _roster, conflicts = obs_roster(
            ("search", LAN_FIRST, True), ("search", LAN_SECOND, True))
        self.assertTrue(any(
            c["reason"] == "last_wins" and c["field"] == "relation"
            and c["old"] == "đồng nghiệp" and c["new"] == "bạn bè"
            for c in conflicts), conflicts)


class TestBackfillAndConverse(unittest.TestCase):
    def test_missing_then_full_fills(self):
        expected = LAN_FIRST
        self.assertEqual(
            obs_roster(("search", LAN_MISSING, True),
                       ("search", LAN_FIRST, True))[0], expected)
        self.assertEqual(
            harness_roster({"ok": True, "contacts": LAN_MISSING},
                           {"ok": True, "contacts": LAN_FIRST}),
            expected)
        self.assertEqual(
            agent_state_roster(("read", LAN_MISSING),
                               ("read", LAN_FIRST))[0], expected)

    def test_full_then_missing_keeps(self):
        for roster in (
                obs_roster(("search", LAN_FIRST, True),
                           ("search", LAN_MISSING, True))[0],
                harness_roster({"ok": True, "contacts": LAN_FIRST},
                               {"ok": True, "contacts": LAN_MISSING}),
                agent_state_roster(("read", LAN_FIRST),
                                   ("read", LAN_MISSING))[0]):
            self.assertEqual(roster, LAN_FIRST)


class TestFailedReadsAndAbsence(unittest.TestCase):
    def test_failed_read_after_good_does_not_break(self):
        for roster in (
                obs_roster(("search", LAN_FIRST, True),
                           ("search", LAN_SECOND, False))[0],
                harness_roster({"ok": True, "contacts": LAN_FIRST},
                               {"ok": False, "contacts": LAN_SECOND})):
            self.assertEqual(roster, LAN_FIRST)

    def test_failed_first_does_not_poison(self):
        for roster in (
                obs_roster(("search", LAN_FIRST, False),
                           ("search", LAN_FIRST, True))[0],
                harness_roster({"ok": False, "contacts": LAN_FIRST},
                               {"ok": True, "contacts": LAN_FIRST})):
            self.assertEqual(roster, LAN_FIRST)

    def test_no_future_event_rewrites_an_earlier_prefix(self):
        full = obs_prefix(("search", LAN_FIRST, True),
                          ("search", LAN_SECOND, True))
        self.assertEqual(
            collect_rosters_from_prefix_with_conflicts(full[:1])[0],
            LAN_FIRST)
        self.assertEqual(
            collect_rosters_from_prefix_with_conflicts(full)[0][0]
            ["relation"], "bạn bè")

    def test_absence_in_a_later_search_is_not_a_deletion(self):
        only_c2 = [{"id": "c2", "name": "Lan",
                    "phone": "0903777888", "relation": "hàng xóm"}]
        for roster in (
                obs_roster(("search", LAN_FIRST, True),
                           ("search", only_c2, True))[0],
                harness_roster({"ok": True, "contacts": LAN_FIRST},
                               {"ok": True, "contacts": only_c2}),
                agent_state_roster(("read", LAN_FIRST),
                                   ("read", only_c2))[0]):
            # c1 was not mentioned by the later read, so no
            # field of c1 was updated and none was deleted.
            self.assertEqual(roster, LAN_FIRST)


class TestEmptyWrongTypeStray(unittest.TestCase):
    def test_empty_values_never_overwrite(self):
        empty = [{"id": "c1", "name": "", "phone": "",
                  "relation": ""},
                 {"id": "c2", "name": "Lan",
                  "phone": "0903777888", "relation": "   "}]
        for roster in (
                obs_roster(("search", LAN_FIRST, True),
                           ("search", empty, True))[0],
                harness_roster({"ok": True, "contacts": LAN_FIRST},
                               {"ok": True, "contacts": empty}),
                agent_state_roster(("read", LAN_FIRST),
                                   ("read", empty))[0]):
            self.assertEqual(roster, LAN_FIRST)

    def test_wrong_type_and_invalid_phone_are_ignored(self):
        wrong = [{"id": "c1", "name": 123, "phone": 123,
                  "relation": 123, "note": "đồng nghiệp"},
                 {"id": "c2", "name": "Lan",
                  "phone": "090311122", "relation": "hàng xóm"}]
        # 9-digit phone for c2 is invalid under the contract,
        # so c2 keeps its old phone; c1 keeps everything.
        for roster in (
                obs_roster(("search", LAN_FIRST, True),
                           ("search", wrong, True))[0],
                harness_roster({"ok": True, "contacts": LAN_FIRST},
                               {"ok": True, "contacts": wrong}),
                agent_state_roster(("read", LAN_FIRST),
                                   ("read", wrong))[0]):
            self.assertEqual(roster, LAN_FIRST)
        # Wrong types on a FIRST read create no evidence for
        # those fields (name/phone become missing, relation
        # absent, note dropped).
        first_wrong = [{"id": "c1", "name": 123,
                        "phone": "18001234", "relation": 123,
                        "note": "đồng nghiệp"}]
        for roster in (
                obs_roster(("search", first_wrong, True))[0],
                harness_roster({"ok": True, "contacts": first_wrong}),
                agent_state_roster(("read", first_wrong))[0]):
            self.assertEqual(
                roster, [{"id": "c1", "name": "", "phone": ""}])

    def test_stray_fields_never_qualify(self):
        stray = [{"id": "c1", "name": "Lan",
                  "phone": "0903111222", "relation": "đối tác",
                  "note": "bạn bè", "company": "bạn bè"},
                 {"id": "c2", "name": "Lan",
                  "phone": "0903777888", "relation": "hàng xóm"}]
        for roster in (
                obs_roster(("search", stray, True))[0],
                harness_roster({"ok": True, "contacts": stray}),
                agent_state_roster(("read", stray))[0]):
            self.assertNotIn("note", roster[0])
            self.assertNotIn("company", roster[0])
            # The note "bạn bè" must not qualify c1: the
            # descriptor matches no structured attribute.
            assert_blocked(self, decide_for("c1", roster, "bạn bè"))
            assert_blocked(self, decide_for("c2", roster, "bạn bè"))

    def test_roster_entries_are_whitelist_only(self):
        for roster in (
                obs_roster(("search", LAN_FIRST, True),
                           ("search", LAN_SECOND, True))[0],
                harness_roster({"ok": True, "contacts": LAN_FIRST},
                               {"ok": True, "contacts": LAN_SECOND}),
                agent_state_roster(("read", LAN_FIRST),
                                   ("read", LAN_SECOND))[0]):
            for entry in roster:
                self.assertEqual(
                    set(entry.keys()) - {"id", "name", "phone",
                                         "relation"}, set())


class TestIntraReadConflictUnknown(unittest.TestCase):
    def test_one_read_contradicting_itself_is_unknown(self):
        intra = [{"id": "c1", "name": "Lan",
                  "phone": "0903111222", "relation": "đồng nghiệp"},
                 {"id": "c1", "name": "Lan",
                  "phone": "0903111222", "relation": "bạn bè"},
                 {"id": "c2", "name": "Lan",
                  "phone": "0903777888", "relation": "hàng xóm"}]
        roster, conflicts = obs_roster(("search", intra, True))
        self.assertNotIn("relation", roster[0])
        self.assertTrue(any(
            c["reason"] == "intra_read_conflict_unknown"
            and c["field"] == "relation" for c in conflicts), conflicts)
        for roster2 in (
                harness_roster({"ok": True, "contacts": intra}),
                agent_state_roster(("read", intra))[0]):
            self.assertNotIn("relation", roster2[0])
        # Neither value can be used to choose c1 now.
        for roster3 in (roster,
                        harness_roster(
                            {"ok": True, "contacts": intra})):
            assert_blocked(self, decide_for("c1", roster3, "đồng nghiệp"))
            assert_blocked(self, decide_for("c1", roster3, "bạn bè"))

    def test_later_unambiguous_read_reestablishes_unknown(self):
        intra = [{"id": "c1", "name": "Lan",
                  "phone": "0903111222", "relation": "đồng nghiệp"},
                 {"id": "c1", "name": "Lan",
                  "phone": "0903111222", "relation": "bạn bè"}]
        roster, _conflicts = agent_state_roster(
            ("read", intra), ("read", LAN_SECOND))
        self.assertEqual(roster[0]["relation"], "bạn bè")


class TestBarrier(unittest.TestCase):
    UPDATE_ARGS = {"contact_id": "c1"}

    def test_barrier_overwrites_pre_barrier_value(self):
        # Update confirms c1's relation as bạn bè; the
        # pre-barrier đồng nghiệp is discarded, not kept.
        item = {"id": "c1", "relation": "bạn bè"}
        for roster in (
                obs_roster(
                    ("search", LAN_FIRST, True),
                    ("update", self.UPDATE_ARGS, item, True))[0],
                harness_state_roster(
                    ("read", LAN_FIRST),
                    ("barrier", self.UPDATE_ARGS, item))[0],
                agent_state_roster(
                    ("read", LAN_FIRST),
                    ("barrier", self.UPDATE_ARGS, item))[0]):
            self.assertEqual(roster[0]["relation"], "bạn bè")
            self.assertFalse(decide_for("c1", roster, "bạn bè").fired)
            assert_blocked(
                self, decide_for("c1", roster, "đồng nghiệp"))

    def test_barrier_contradiction_is_unknown_not_a_choice(self):
        item = {"id": "c1", "relation": "bạn bè"}
        stale = [{"id": "c1", "name": "Lan",
                  "phone": "0903111222", "relation": "đồng nghiệp"}]
        roster, conflicts = obs_roster(
            ("search", LAN_FIRST, True),
            ("update", self.UPDATE_ARGS, item, True),
            ("search", stale, True))
        self.assertNotIn("relation", roster[0])
        self.assertTrue(any(
            c["reason"] == "barrier_contradiction_unknown"
            and c["field"] == "relation"
            and c["old"] == "bạn bè" and c["new"] == "đồng nghiệp"
            for c in conflicts), conflicts)
        for roster2 in (
                harness_state_roster(
                    ("read", LAN_FIRST),
                    ("barrier", self.UPDATE_ARGS, item),
                    ("read", stale))[0],
                agent_state_roster(
                    ("read", LAN_FIRST),
                    ("barrier", self.UPDATE_ARGS, item),
                    ("read", stale))[0]):
            self.assertNotIn("relation", roster2[0])
        # Neither the barrier value nor the stale value can
        # be used to choose c1 while the field is UNKNOWN.
        assert_blocked(self, decide_for("c1", roster, "bạn bè"))
        assert_blocked(self, decide_for("c1", roster, "đồng nghiệp"))

    def test_barrier_agreement_reestablishes(self):
        item = {"id": "c1", "relation": "bạn bè"}
        stale = [{"id": "c1", "name": "Lan",
                  "phone": "0903111222", "relation": "đồng nghiệp"}]
        agreeing = [{"id": "c1", "name": "Lan",
                     "phone": "0903111222", "relation": "bạn bè"}]
        roster, _c = obs_roster(
            ("search", LAN_FIRST, True),
            ("update", self.UPDATE_ARGS, item, True),
            ("search", stale, True),
            ("search", agreeing, True))
        self.assertEqual(roster[0]["relation"], "bạn bè")

    def test_barrier_is_per_field_only(self):
        # A phone-only update bars the phone, never the
        # relation it never touched.
        item = {"id": "c1", "phone": "0902222222"}
        stale_phone = [{"id": "c1", "name": "Lan",
                        "phone": "0903111222",
                        "relation": "đồng nghiệp"}]
        roster, conflicts = obs_roster(
            ("search", LAN_FIRST, True),
            ("update", self.UPDATE_ARGS, item, True),
            ("search", stale_phone, True))
        self.assertEqual(roster[0]["phone"], "")
        self.assertEqual(roster[0]["relation"], "đồng nghiệp")
        self.assertTrue(all(
            c["field"] == "phone" for c in conflicts), conflicts)
        # Relation evidence still works for the descriptor.
        self.assertFalse(
            decide_for("c1", roster, "đồng nghiệp").fired)

    def test_unconfirmed_update_is_no_barrier(self):
        # Failed update, id mismatch, and an invalid phone
        # tail each fail patch-verification, so none bars
        # a later read: the later read last-wins normally.
        cases = [
            # (update event, later read) -- observer path
            (("update", self.UPDATE_ARGS,
              {"id": "c1", "phone": "0902222222"}, False),
             LAN_SECOND),
            (("update", self.UPDATE_ARGS,
              {"id": "c2", "phone": "0902222222"}, True),
             LAN_SECOND),
            (("update", self.UPDATE_ARGS,
              {"id": "c1", "phone": "đuôi 222"}, True),
             LAN_SECOND),
        ]
        for update_ev, later in cases:
            roster, conflicts = obs_roster(
                ("search", LAN_FIRST, True), update_ev,
                ("search", later, True))
            self.assertEqual(roster[0]["relation"], "bạn bè")
            self.assertFalse(any(
                c["reason"] == "barrier_contradiction_unknown"
                for c in conflicts), conflicts)


class TestAgentLoopRoster(unittest.TestCase):
    """Loop-level agent roster: real AgentLoop, scripted
    generator, canned FakeEnv. Grounding ON, pending OFF
    (the flag is untouched by this change; its own file
    covers ON/OFF)."""

    TOOLS = {
        "contacts.search": {"kind": "read",
                            "parameters": {"required": ["query"]},
                            "description": "search"},
        "contacts.update": {"kind": "write",
                            "parameters": {"required": ["contact_id"]},
                            "description": "update"},
    }
    CTX = {"current_time": "2026-10-30T09:00:00+07:00",
           "timezone": "Asia/Saigon",
           "user_profile": {"name": "Test", "city": "HCM"},
           "installed_apps": {}}

    class Gen:
        def __init__(self, proposals):
            self.queue = list(proposals)

        def __call__(self, prompt, tools):
            if not self.queue:
                return None
            return self.queue.pop(0)

    class FakeEnv:
        def __init__(self, search):
            self.search = search
            self.calls = []

        def validate(self, name, arguments):
            return {"ok": True}

        def call(self, name, arguments):
            self.calls.append({"name": name, "arguments": arguments})
            if name == "contacts.search":
                return {"ok": True, "contacts": self.search.get(
                    arguments.get("query"), [])}
            if name == "contacts.update":
                return {"ok": True, "item": {
                    "id": arguments.get("contact_id"),
                    "phone": arguments.get("phone")}}
            return {"ok": True, "done": True}

        def submission_line(self):
            return {"id": "fake", "tool_calls": list(self.calls),
                    "state_hash": "fake"}

    def _run(self, proposals, search):
        gen = self.Gen(proposals)
        env = self.FakeEnv(search)
        sample = SimpleNamespace(context=dict(self.CTX), history=[])
        loop = AgentLoop(
            PipelineConfig(grounding=True, shadow_observer=False,
                           pending_ask_stop=False), self.TOOLS)
        loop.run(sample, "gọi cho Lan", env, gen)
        return loop

    def test_loop_last_wins_and_stray_dropped(self):
        loop = self._run(
            [{"name": "contacts.search", "arguments": {"query": "Lan"}},
             {"name": "contacts.search",
              "arguments": {"query": "Lan2"}}],
            {"Lan": LAN_FIRST,
             "Lan2": [{"id": "c1", "name": "Lan",
                       "phone": "0903111222", "relation": "bạn bè",
                       "note": "bạn bè"},
                      {"id": "c2", "name": "Lan",
                       "phone": "0903777888",
                       "relation": "hàng xóm"}]})
        self.assertEqual(len(loop._roster), 2)
        self.assertEqual(loop._roster[0]["relation"], "bạn bè")
        self.assertNotIn("note", loop._roster[0])
        self.assertTrue(any(
            c["reason"] == "last_wins" for c in loop.roster_conflicts))

    def test_loop_barrier_contradiction_is_unknown(self):
        loop = self._run(
            [{"name": "contacts.search", "arguments": {"query": "Lan"}},
             {"name": "contacts.update",
              "arguments": {"contact_id": "c1",
                            "phone": "0902222222"}},
             {"name": "contacts.search",
              "arguments": {"query": "Lan2"}}],
            {"Lan": LAN_FIRST,
             "Lan2": [{"id": "c1", "name": "Lan",
                       "phone": "0903111222",
                       "relation": "đồng nghiệp"}]})
        self.assertEqual(loop._roster[0]["phone"], "")
        self.assertEqual(loop._roster[0]["relation"], "đồng nghiệp")
        self.assertTrue(any(
            c["reason"] == "barrier_contradiction_unknown"
            and c["field"] == "phone"
            for c in loop.roster_conflicts), loop.roster_conflicts)


if __name__ == "__main__":
    unittest.main()
