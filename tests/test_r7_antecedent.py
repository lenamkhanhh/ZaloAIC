#!/usr/bin/env python3
"""Run 7 antecedent tests (LifeMate only, synthetic, no gold).

Adapter-level mirrors of the R7 repro script: a reduced descriptor
is recognised by its distinguishing content tokens, and a
lookup/open/view history turn that uniquely resolves a duplicate
group is the antecedent for a pronoun in the next action turn.
Fixture names/relations are examples only; production matching is
by roster structured attributes, with no name, number, id or
relation hardcoded in production code.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lifemate.lifemate_gates_adapter import decide  # noqa: E402

KINDS = {
    "contacts.search": "read", "contacts.get": "read",
    "contacts.update": "write", "contacts.delete": "write",
    "phone.recent_calls": "read", "phone.call": "write",
    "sms.read_recent": "read", "sms.send": "write",
}


def user_turn(text, pos):
    return {"kind": "user_turn", "text": text, "position": pos}


def dup(name, id1, ph1, rel1, id2, ph2, rel2):
    return [{"id": id1, "name": name, "phone": ph1, "relation": rel1},
            {"id": id2, "name": name, "phone": ph2, "relation": rel2}]


HOA = dup("Hòa", "h1", "0903112101", "phòng kế toán",
          "h2", "0903112102", "bạn cấp ba")
MINH = dup("Minh", "m1", "0903112501", "bạn thân",
           "m2", "0903112502", "bạn học")


class TestR7Antecedent(unittest.TestCase):
    def _dec(self, proposal, prefix, roster, current):
        return decide(proposal, prefix, roster, current, KINDS,
                      proposal_position=len(prefix))

    def _call(self, phone):
        return {"name": "phone.call",
                "arguments": {"phone_number": phone}}

    def _sms(self, cid):
        return {"name": "sms.send",
                "arguments": {"contact_id": cid, "content": "hi"}}

    def _assert_pass(self, dec):
        self.assertFalse(dec.baseline_fired)
        self.assertFalse(dec.fired, dec.adjustments)

    def _assert_block_via_selection(self, dec):
        self.assertFalse(dec.baseline_fired)
        self.assertTrue(dec.fired)
        self.assertTrue(any(a["mechanism"] == "selection_mismatch"
                            for a in dec.adjustments),
                        dec.adjustments)

    def test_reduced_descriptor_same_turn_pronoun(self):
        current = ("Mở giúp mình liên hệ anh Hòa bên kế toán với, "
                   "rồi gọi điện thoại luôn cho anh ấy nha.")
        self._assert_pass(self._dec(self._call("0903112101"), [],
                                    HOA, current))
        self._assert_block_via_selection(self._dec(
            self._call("0903112102"), [], HOA, current))

    def test_view_history_reduced_descriptor_pronoun(self):
        prefix = [user_turn("Xem liên hệ Hòa bên kế toán giúp mình",
                            0)]
        current = "Gọi điện thoại cho anh ấy nha."
        self._assert_pass(self._dec(self._call("0903112101"),
                                    prefix, HOA, current))
        self._assert_block_via_selection(self._dec(
            self._call("0903112102"), prefix, HOA, current))

    def test_shared_token_matches_nobody(self):
        current = "Nhắn cho Minh bạn: Chào bạn"
        self._assert_block_via_selection(self._dec(
            self._sms("m1"), [], MINH, current))
        self._assert_block_via_selection(self._dec(
            self._sms("m2"), [], MINH, current))

    def test_antecedent_replaced_and_cancelled(self):
        replaced = [user_turn("Xem liên hệ Hòa bên kế toán giúp mình",
                              0),
                    user_turn("À không, xem Hòa bạn cấp ba giúp mình",
                              1)]
        current = "Gọi điện thoại cho anh ấy nha."
        self._assert_block_via_selection(self._dec(
            self._call("0903112101"), replaced, HOA, current))
        self._assert_pass(self._dec(self._call("0903112102"),
                                    replaced, HOA, current))
        cancelled = [user_turn("Xem liên hệ Hòa bên kế toán giúp mình",
                               0),
                     user_turn("Hủy xem Hòa bên kế toán đi", 1)]
        self._assert_block_via_selection(self._dec(
            self._call("0903112101"), cancelled, HOA, current))
        self._assert_block_via_selection(self._dec(
            self._call("0903112102"), cancelled, HOA, current))

    def test_lookup_does_not_license_other_action(self):
        prefix = [user_turn("Xem liên hệ Hòa bên kế toán giúp mình",
                            0)]
        self._assert_block_via_selection(self._dec(
            self._sms("h1"), prefix, HOA, "Gọi cho anh ấy nha."))
        self._assert_block_via_selection(self._dec(
            self._call("0903112101"), prefix, HOA,
            "Nhắn cho anh ấy: Chào bạn"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
