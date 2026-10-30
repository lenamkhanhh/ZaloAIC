#!/usr/bin/env python3
"""Paired-harness roster tests (synthetic only, no gold data).

Regression: analysis/gg_paired_audit.py used to forward only
id/name/phone from a contacts.search result, so D1 (the
structured-attribute qualifier in
lifemate_callback_negation.py) never saw ``relation`` and the
paired harness blocked the D1 gold shape even though D1 is
correct on a full roster. Every case here starts from a RAW
contacts.search result, goes through collect_rosters, and
then through the real adapter decide() -- the same chain
the harness uses for history rosters.

The duplicate-name shape below is a synthetic reconstruction
of the train_0063/0225 shape (history descriptor "Minh
khách hàng" + two Minh roster entries, exactly one with
relation "khách hàng"). It is NOT the real paired-gold
samples: the real paired-dev run (976, with real data)
remains NOT_RUN on this VM and is the Codex step.

Scope of this file: the harness only. It does not test
the runtime observer, and a PASS here does not mean the
runtime is fixed -- the harness is only correct when its
input roster is complete (see the report).
"""

import importlib.util
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lifemate.lifemate_gates_adapter import decide  # noqa: E402

_SPEC = importlib.util.spec_from_file_location(
    "gg_paired_audit",
    Path(__file__).resolve().parent.parent
    / "analysis" / "gg_paired_audit.py")
_HARNESS = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_HARNESS)
collect_rosters = _HARNESS.collect_rosters
# getattr (not a direct attribute) so this file still loads
# against the pre-fix harness and fails on assertions there
# instead of failing at import: the helper did not exist
# before the fix.
_harness_roster_entry = getattr(
    _HARNESS, "_harness_roster_entry", None)

KINDS = {"contacts.search": "read", "sms.send": "write"}
# History turn carrying the descriptor, as a user turn.
PREFIX = [{"kind": "user_turn",
           "text": "Tìm số của Minh khách hàng dùm tôi",
           "position": 0}]


def roster_from(raw):
    out = []
    collect_rosters(raw, out)
    return out


def decide_for(contact_id, roster):
    return decide({"name": "sms.send",
                   "arguments": {"contact_id": contact_id}},
                  PREFIX, roster, "Nhắn tin cho Minh", KINDS,
                  proposal_position=1)


class TestHarnessRoster(unittest.TestCase):
    def test_collect_keeps_relation_string_only(self):
        raw = {"ok": True, "contacts": [
            {"id": "c_m1", "name": "Minh", "phone": "0903111222",
             "relation": "khách hàng", "note": "khách hàng",
             "company": "khách hàng"},
            {"id": "c_m2", "name": "Minh", "phone": "0903777888",
             "relation": "đồng nghiệp"},
            # Non-string relation and missing id: neither
            # may become roster evidence.
            {"id": "c_m3", "name": "Minh", "phone": "0903999888",
             "relation": 123},
            {"name": "Minh", "phone": "0903000000",
             "relation": "khách hàng"}]}
        self.assertEqual(roster_from(raw), [
            {"id": "c_m1", "name": "Minh", "phone": "0903111222",
             "relation": "khách hàng"},
            {"id": "c_m2", "name": "Minh", "phone": "0903777888",
             "relation": "đồng nghiệp"},
            {"id": "c_m3", "name": "Minh", "phone": "0903999888"}])

    def test_replay_helper_uses_same_whitelist(self):
        # The replay (session) path in main() builds its
        # rosters through this helper, so the whitelist
        # proven here is the whitelist both paths share.
        self.assertIsNotNone(_harness_roster_entry)
        self.assertEqual(
            _harness_roster_entry(
                {"id": "c_m1", "name": "Minh", "phone": "0903111222",
                 "relation": "khách hàng", "note": "x"}),
            {"id": "c_m1", "name": "Minh", "phone": "0903111222",
             "relation": "khách hàng"})
        self.assertIsNone(_harness_roster_entry(
            {"name": "Minh", "relation": "khách hàng"}))

    def test_gold_passes_and_wrong_person_blocks(self):
        roster = roster_from({"ok": True, "contacts": [
            {"id": "c_m1", "name": "Minh", "phone": "0903111222",
             "relation": "khách hàng"},
            {"id": "c_m2", "name": "Minh", "phone": "0903777888",
             "relation": "đồng nghiệp"}]})
        gold = decide_for("c_m1", roster)
        self.assertFalse(gold.fired)
        wrong = decide_for("c_m2", roster)
        self.assertTrue(wrong.fired)
        self.assertTrue(any(a["mechanism"] == "selection_mismatch"
                            for a in wrong.adjustments),
                        wrong.adjustments)

    def test_missing_relation_blocks_both(self):
        roster = roster_from({"ok": True, "contacts": [
            {"id": "c_m1", "name": "Minh", "phone": "0903111222"},
            {"id": "c_m2", "name": "Minh", "phone": "0903777888"}]})
        for contact_id in ("c_m1", "c_m2"):
            self.assertTrue(decide_for(contact_id, roster).fired)

    def test_duplicate_relation_blocks_both(self):
        roster = roster_from({"ok": True, "contacts": [
            {"id": "c_m1", "name": "Minh", "phone": "0903111222",
             "relation": "khách hàng"},
            {"id": "c_m2", "name": "Minh", "phone": "0903777888",
             "relation": "khách hàng"}]})
        for contact_id in ("c_m1", "c_m2"):
            self.assertTrue(decide_for(contact_id, roster).fired)

    def test_mismatched_relation_blocks_both(self):
        roster = roster_from({"ok": True, "contacts": [
            {"id": "c_m1", "name": "Minh", "phone": "0903111222",
             "relation": "bạn học"},
            {"id": "c_m2", "name": "Minh", "phone": "0903777888",
             "relation": "đồng nghiệp"}]})
        for contact_id in ("c_m1", "c_m2"):
            self.assertTrue(decide_for(contact_id, roster).fired)

    def test_stray_string_fields_do_not_qualify(self):
        # "khách hàng" appearing only in a note/company
        # field, with no relation field, must NOT qualify
        # either duplicate -- otherwise any string in the
        # dictionary would count as structured evidence.
        roster = roster_from({"ok": True, "contacts": [
            {"id": "c_m1", "name": "Minh", "phone": "0903111222",
             "note": "khách hàng", "company": "khách hàng"},
            {"id": "c_m2", "name": "Minh", "phone": "0903777888",
             "relation": 123}]})
        for contact_id in ("c_m1", "c_m2"):
            self.assertTrue(decide_for(contact_id, roster).fired)

    def test_failed_read_contributes_no_roster(self):
        roster = roster_from({"ok": False, "contacts": [
            {"id": "c_m1", "name": "Minh", "phone": "0903111222",
             "relation": "khách hàng"},
            {"id": "c_m2", "name": "Minh", "phone": "0903777888",
             "relation": "đồng nghiệp"}]})
        self.assertEqual(roster, [])
        # With no roster evidence at all, neither arm may
        # pass on the failed read.
        for contact_id in ("c_m1", "c_m2"):
            self.assertTrue(decide_for(contact_id, roster).fired)


if __name__ == "__main__":
    unittest.main()
