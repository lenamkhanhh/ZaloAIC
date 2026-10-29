"""Name matching + family/relation binding (callback fix, thread A).

Every case states its scope in a comment. Rules under test:
  - name matching is FULL PHRASE only: a shared surname or a
    shared common token never matches (R1);
  - only the callback clause's addressee span selects: names in
    quotes, message content, or other clauses do not;
  - a family addressee binds ONLY on structured relation
    evidence (roster "relation" field or a log record's
    "relation" field) for the same counterpart (R2);
  - generic callbacks ("gọi lại người vừa gọi", "gọi lại giúp
    tôi") keep the old single-pool behaviour.
Run: python3 tests/test_name_binding.py (both backends).
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent
                       / "lifemate"))
import lifemate_phone_callback_evidence as ev


def missed(cid, name, phone, pos=0, relation=None):
    rec = {"tool": "phone.recent_calls", "contact_id": cid,
           "name": name, "phone_number": phone,
           "direction": "incoming", "status": "missed",
           "position": pos}
    if relation is not None:
        rec["relation"] = relation
    return rec


def msg(cid, phone, content, pos=0):
    return {"tool": "sms.read_recent", "contact_id": cid,
            "name": None, "phone_number": phone,
            "direction": "incoming", "status": None,
            "content": content, "position": pos}


class TestFullPhraseNameMatching(unittest.TestCase):
    def test_nguyen_an_vs_nguyen_binh_no_bind(self):
        # R1: shared surname "Nguyễn" must not rescue the
        # conflicting given name. Old code bound via token
        # intersection; new code vetoes (callback_name_mismatch).
        rec, reason = ev.bind_history_reference(
            "gọi lại cho Nguyễn Bình giúp tôi",
            [missed("c_x", "Nguyễn An", "0902345678")])
        self.assertIsNone(rec)
        self.assertEqual(reason, "callback_name_mismatch")

    def test_tran_minh_vs_tran_mai_no_bind(self):
        # Same shape, different family: shared "Trần" is not a
        # match for "Trần Mai" against "Trần Minh".
        rec, reason = ev.bind_history_reference(
            "gọi lại cho Trần Mai nhé",
            [missed("c_x", "Trần Minh", "0902345678")])
        self.assertIsNone(rec)
        self.assertEqual(reason, "callback_name_mismatch")

    def test_full_name_exact_binds(self):
        # Control: the exact full name still binds.
        rec, reason = ev.bind_history_reference(
            "gọi lại cho Nguyễn Bình giúp tôi",
            [missed("c_x", "Nguyễn Bình", "0902345678")])
        self.assertIsNotNone(rec)
        self.assertEqual(rec["contact_id"], "c_x")
        self.assertEqual(reason, "callback_unique_match")

    def test_short_name_unique_binds(self):
        # A short (given-name-only) addressee binds when it is
        # the unique given name in the pool: "An" -> "Nguyễn An"
        # with no competitor.
        rec, _ = ev.bind_history_reference(
            "gọi lại cho An nhé",
            [missed("c_x", "Nguyễn An", "0902345678"),
             missed("c_y", "Trần Bình", "0902444444", pos=1)])
        self.assertIsNotNone(rec)
        self.assertEqual(rec["contact_id"], "c_x")

    def test_short_name_single_token_candidate_binds(self):
        # Single-token candidate, single-token addressee: exact.
        rec, _ = ev.bind_history_reference(
            "gọi lại cho Vy dùm anh luôn nha",
            [missed("c_x", "Vy", "0902345678")])
        self.assertIsNotNone(rec)
        self.assertEqual(rec["contact_id"], "c_x")

    def test_short_name_ambiguous_no_bind(self):
        # Two candidates share the short name -> ambiguous, no
        # bind (neither record is selected).
        rec, reason = ev.bind_history_reference(
            "gọi lại cho An nhé",
            [missed("c_x", "Nguyễn An", "0902345678"),
             missed("c_y", "Trần An", "0902444444", pos=1)])
        self.assertIsNone(rec)
        self.assertEqual(reason, "callback_name_ambiguous")

    def test_surname_only_no_bind(self):
        # A bare surname is a non-final token: it never matches,
        # even with a single pool record ("Nguyễn" is not "An").
        rec, reason = ev.bind_history_reference(
            "gọi lại cho Nguyễn giúp tôi",
            [missed("c_x", "Nguyễn An", "0902345678")])
        self.assertIsNone(rec)
        self.assertEqual(reason, "callback_name_mismatch")

    def test_folded_full_name_binds(self):
        # Multi-token names may match folded, but only as a FULL
        # phrase: "Nguyen Van An" (no diacritics) still matches
        # "Nguyễn Văn An"; a folded surname alone does not.
        rec, _ = ev.bind_history_reference(
            "gọi lại cho Nguyen Van An nhé",
            [missed("c_x", "Nguyễn Văn An", "0902345678")])
        self.assertIsNotNone(rec)
        self.assertEqual(rec["contact_id"], "c_x")

    def test_name_matches_unit_partial_never(self):
        # Unit-level guard for _name_matches itself: partial
        # overlap (surname only) is False in both directions.
        self.assertFalse(ev._name_matches(
            "Nguyễn An", "gọi lại cho Nguyễn Bình"))
        self.assertFalse(ev._name_matches(
            "Nguyễn Bình", "Nguyễn An vừa gọi nhỡ"))
        self.assertTrue(ev._name_matches(
            "Nguyễn An", "gọi lại cho Nguyễn An"))
        # Single-token diacritic sensitivity is preserved.
        self.assertFalse(ev._name_matches("An", "ăn xong rồi gọi"))
        self.assertTrue(ev._name_matches("An", "gọi lại cho An"))


class TestAddresseeSpan(unittest.TestCase):
    def test_quoted_name_not_addressee(self):
        # A name inside quotes is content, not the addressee:
        # with two pool records and no real addressee, the
        # quoted "An" must not select An (multiple -> None).
        rec, reason = ev.bind_history_reference(
            'gọi lại giúp tôi, nội dung "nhắn An nhé"',
            [missed("c_a", "An", "0933333333"),
             missed("c_b", "Bình", "0944444444", pos=1)])
        self.assertIsNone(rec)
        self.assertEqual(reason,
                         "callback_multiple_incoming_candidates")

    def test_quoted_name_ignored_when_real_addressee_present(self):
        # Real addressee Bình wins; quoted "An" is ignored.
        rec, _ = ev.bind_history_reference(
            'gọi lại cho Bình với nội dung "An ơi"',
            [missed("c_a", "An", "0933333333"),
             missed("c_b", "Bình", "0944444444", pos=1)])
        self.assertIsNotNone(rec)
        self.assertEqual(rec["contact_id"], "c_b")

    def test_multi_clause_only_addressee_counts(self):
        # Two people across clauses: only the callback clause's
        # addressee (Vy) selects; the other clause's "An" does not.
        rec, _ = ev.bind_history_reference(
            "hỏi An xong rồi gọi lại cho Vy",
            [missed("c_a", "An", "0933333333"),
             missed("c_v", "Vy", "0944444444", pos=1)])
        self.assertIsNotNone(rec)
        self.assertEqual(rec["contact_id"], "c_v")

    def test_comma_stops_addressee_span(self):
        # "gọi lại cho Vy, An cũng nhắn rồi": the comma ends the
        # span, so the addressee is Vy alone (not "Vy An").
        rec, _ = ev.bind_history_reference(
            "gọi lại cho Vy, An cũng nhắn rồi",
            [missed("c_a", "An", "0933333333"),
             missed("c_v", "Vy", "0944444444", pos=1)])
        self.assertIsNotNone(rec)
        self.assertEqual(rec["contact_id"], "c_v")

    def test_title_prefix_stripped(self):
        # "anh Bình" addresses Bình (title + name), not a
        # two-token name "anh Bình".
        rec, _ = ev.bind_history_reference(
            "gọi lại cho anh Bình giúp tôi",
            [missed("c_b", "Bình", "0944444444")])
        self.assertIsNotNone(rec)
        self.assertEqual(rec["contact_id"], "c_b")

    def test_minh_name_vs_minh_pronoun(self):
        # Bare "Minh" (no diacritic) is the name Minh; "mình"
        # (diacritic) is the pronoun. Both directions checked:
        # name binds its pool record, pronoun keeps the generic
        # single-pool flow, bare name against another pool record
        # vetoes instead of falling back.
        rec, _ = ev.bind_history_reference(
            "gọi lại cho Minh giúp tôi",
            [missed("c_m", "Minh", "0955555555")])
        self.assertIsNotNone(rec)
        self.assertEqual(rec["contact_id"], "c_m")
        rec, _ = ev.bind_history_reference(
            "gọi lại cho mình giúp tôi",
            [missed("c_b", "Bình", "0944444444")])
        self.assertIsNotNone(rec)
        self.assertEqual(rec["contact_id"], "c_b")
        rec, reason = ev.bind_history_reference(
            "gọi lại cho Minh giúp tôi",
            [missed("c_b", "Bình", "0944444444")])
        self.assertIsNone(rec)
        self.assertEqual(reason, "callback_name_mismatch")

    def test_reply_message_object_not_addressee(self):
        # "Trả lời tin nhắn ..." has a generic object ("tin"),
        # not a person addressee: topic selection still applies
        # (adapter regression guard for the old topic test).
        rec, reason = ev.bind_history_reference(
            "Trả lời tin nhắn xin lại hai trăm nghìn",
            [msg("c_7", "0912345678",
                 "Cho mình xin lại hai trăm nghìn nhé")])
        self.assertIsNotNone(rec)
        self.assertEqual(rec["contact_id"], "c_7")
        self.assertEqual(reason, "callback_topic_unique")


class TestFamilyRelation(unittest.TestCase):
    def test_family_single_caller_no_relation_no_bind(self):
        # R2: one missed caller, no relation evidence anywhere:
        # "mẹ" must not fall back to the single caller. Question
        # (a) may hold (Vy exists) but (b) is unproven.
        rec, reason = ev.bind_history_reference(
            "gọi lại cho mẹ giúp tôi",
            [missed("c_x", "Vy", "0902345678")])
        self.assertIsNone(rec)
        self.assertEqual(reason, "callback_relation_unproven")

    def test_family_multiple_callers_no_bind(self):
        # Several callers, still no relation evidence: unproven,
        # not ambiguous-by-count -- the reason names the gap.
        rec, reason = ev.bind_history_reference(
            "gọi lại cho mẹ giúp tôi",
            [missed("c_x", "Vy", "0902345678"),
             missed("c_y", "An", "0902444444", pos=1)])
        self.assertIsNone(rec)
        self.assertEqual(reason, "callback_relation_unproven")

    def test_family_relation_evidence_via_roster_binds(self):
        # Roster entry carries relation "mẹ" for the pool
        # record's contact: the family request binds.
        roster = [{"id": "c_x", "name": "Vy",
                   "phone": "0902345678", "relation": "mẹ"}]
        rec, reason = ev.bind_history_reference(
            "gọi lại cho mẹ giúp tôi",
            [missed("c_x", "Vy", "0902345678")], roster=roster)
        self.assertIsNotNone(rec)
        self.assertEqual(rec["contact_id"], "c_x")
        self.assertEqual(reason, "callback_relation_match")

    def test_family_relation_evidence_via_log_record_binds(self):
        # The log record itself carries relation "mẹ": binds
        # without any roster.
        rec, reason = ev.bind_history_reference(
            "gọi lại cho mẹ giúp tôi",
            [missed("c_x", "Vy", "0902345678", relation="mẹ")])
        self.assertIsNotNone(rec)
        self.assertEqual(rec["contact_id"], "c_x")
        self.assertEqual(reason, "callback_relation_match")

    def test_family_relation_conflict_no_bind(self):
        # The counterpart explicitly claims a DIFFERENT relation
        # ("bạn"): the family request cannot bind them.
        roster = [{"id": "c_x", "name": "Vy",
                   "phone": "0902345678", "relation": "bạn"}]
        rec, reason = ev.bind_history_reference(
            "gọi lại cho mẹ giúp tôi",
            [missed("c_x", "Vy", "0902345678")], roster=roster)
        self.assertIsNone(rec)
        self.assertEqual(reason, "callback_relation_conflict")

    def test_family_relation_selects_other_no_bind(self):
        # Roster says ANOTHER contact is "mẹ": the request
        # selects them, not the pool record.
        roster = [{"id": "c_a", "name": "An",
                   "phone": "0902444444", "relation": "mẹ"}]
        rec, reason = ev.bind_history_reference(
            "gọi lại cho mẹ giúp tôi",
            [missed("c_x", "Vy", "0902345678")], roster=roster)
        self.assertIsNone(rec)
        self.assertEqual(reason, "callback_relation_selects_other")

    def test_contact_named_me_binds_by_name(self):
        # Name-first: a contact literally named "Mẹ" binds by
        # the exact-name rule, before the family path is reached.
        rec, reason = ev.bind_history_reference(
            "gọi lại cho mẹ giúp tôi",
            [missed("c_x", "Mẹ", "0902345678")])
        self.assertIsNotNone(rec)
        self.assertEqual(rec["contact_id"], "c_x")
        self.assertEqual(reason, "callback_unique_match")

    def test_me_lan_name_plus_me_request_no_bind(self):
        # "Mẹ Lan" + request "mẹ": partial overlap is not a name
        # match, and without relation evidence the family path
        # does not bind either.
        rec, reason = ev.bind_history_reference(
            "gọi lại cho mẹ giúp tôi",
            [missed("c_x", "Mẹ Lan", "0902345678")])
        self.assertIsNone(rec)
        self.assertEqual(reason, "callback_relation_unproven")

    def test_family_request_via_callback_reference(self):
        # Verdict level: R2 through callback_reference_for is
        # AMBIGUOUS (sources exist, question_b None with a
        # relation reason), never PROVEN; with relation evidence
        # it is PROVEN.
        prefix = [{"tool": "phone.recent_calls", "args": {},
                   "result": {"ok": True, "calls": [{
                       "id": "call_x",
                       "contact": {"id": "c_x", "name": "Vy",
                                   "phone": "0902345678"},
                       "direction": "incoming",
                       "status": "missed"}]},
                   "outcome": "succeeded", "position": 0,
                   "origin": "history"}]
        v = ev.callback_reference_for(
            {"contact_id": "c_x"}, prefix, [],
            current_text="gọi lại cho mẹ giúp tôi",
            consumer_tool="phone.call")
        self.assertFalse(v["established"])
        self.assertEqual(v["decision"], "AMBIGUOUS")
        self.assertIsNone(v["question_b_target_selected"])
        self.assertIn("callback_relation_unproven",
                      v["question_b_reason"])
        roster = [{"id": "c_x", "name": "Vy",
                   "phone": "0902345678", "relation": "mẹ"}]
        v2 = ev.callback_reference_for(
            {"contact_id": "c_x"}, prefix, roster,
            current_text="gọi lại cho mẹ giúp tôi",
            consumer_tool="phone.call")
        self.assertEqual(v2["decision"], "PROVEN")


class TestGenericCallbackPreserved(unittest.TestCase):
    def test_generic_callback_single_pool_binds(self):
        # No name/family constraint: the old single-pool flow
        # is unchanged ("gọi lại người vừa gọi").
        rec, _ = ev.bind_history_reference(
            "gọi lại người vừa gọi giúp tôi",
            [missed("c_x", "Vy", "0902345678")])
        self.assertIsNotNone(rec)
        self.assertEqual(rec["contact_id"], "c_x")

    def test_generic_callback_no_addressee_binds(self):
        # "gọi lại giúp tôi": no addressee at all, single pool
        # still binds (adapter regression guard).
        rec, _ = ev.bind_history_reference(
            "gọi lại giúp tôi",
            [missed("c_x", "Bình", "0944444444")])
        self.assertIsNotNone(rec)
        self.assertEqual(rec["contact_id"], "c_x")

    def test_generic_callback_two_pool_still_ambiguous(self):
        # Generic + two pool records: still ambiguous, no bind.
        rec, reason = ev.bind_history_reference(
            "gọi lại người vừa gọi giúp tôi",
            [missed("c_x", "Vy", "0902345678"),
             missed("c_y", "An", "0902444444", pos=1)])
        self.assertIsNone(rec)
        self.assertEqual(reason,
                         "callback_multiple_incoming_candidates")

    def test_r1_via_callback_reference(self):
        # Verdict level: R1 through callback_reference_for is a
        # refusal (fired stays), with the mismatch reason -- not
        # a PROVEN un-fire.
        prefix = [{"tool": "phone.recent_calls", "args": {},
                   "result": {"ok": True, "calls": [{
                       "id": "call_x",
                       "contact": {"id": "c_x", "name": "Nguyễn An",
                                   "phone": "0902345678"},
                       "direction": "incoming",
                       "status": "missed"}]},
                   "outcome": "succeeded", "position": 0,
                   "origin": "history"}]
        v = ev.callback_reference_for(
            {"contact_id": "c_x"}, prefix, [],
            current_text="gọi lại cho Nguyễn Bình giúp tôi",
            consumer_tool="phone.call")
        self.assertFalse(v["established"])
        self.assertIsNone(v["question_b_target_selected"])
        self.assertIn("callback_name_mismatch",
                      v["question_b_reason"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
