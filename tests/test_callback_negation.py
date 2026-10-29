#!/usr/bin/env python3
"""Tests for lifemate_callback_negation (thread B, negation /
correction of callback action selection).

Synthetic only: no gold, no sample ids, no held-out. Every case
carries a scope comment stating what it proves and what it does
NOT prove. Run with both backends:
    python3 tests/test_callback_negation.py
    ~/workspace/zaic-test-venv/bin/python tests/test_callback_negation.py
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lifemate"))
from lifemate_callback_negation import analyze_action_selection  # noqa: E402


def sel(text, names=(), phones=(), action="call"):
    return analyze_action_selection(text, target_names=names,
                                    target_phones=phones,
                                    action=action)


class TestMandatoryNegation(unittest.TestCase):
    def test_r3_dung_goi_lai(self):
        # R3 (the reported false binding): a negated callback
        # must NEVER un-fire. "dung" + verb governs the target.
        r = sel("đừng gọi lại cho Vy", names=("Vy",))
        self.assertEqual(r["selection"], "negated")
        self.assertTrue(r["mention_present"])

    def test_khoi_goi_lai_nua(self):
        # "khoi" is a negation marker like "dung"; the trailing
        # "nua" is emphasis, not a second decision.
        r = sel("khỏi gọi lại cho Vy nữa", names=("Vy",))
        self.assertEqual(r["selection"], "negated")

    def test_khong_goi(self):
        # Bare "khong" + verb is an action negation.
        r = sel("không gọi cho Vy", names=("Vy",))
        self.assertEqual(r["selection"], "negated")

    def test_khong_phai_goi(self):
        # "khong phai" + verb is verb negation, not correction
        # (there is no second target after "ma").
        r = sel("không phải gọi cho Vy", names=("Vy",))
        self.assertEqual(r["selection"], "negated")


class TestMandatoryCorrection(unittest.TestCase):
    def test_a_khong_replaced(self):
        # Correction marker + a different named target after it:
        # the OLD target is replaced, not merely negated.
        r = sel("gọi lại cho Vy, à không, gọi cho An",
                names=("Vy",))
        self.assertEqual(r["selection"], "replaced")

    def test_dung_goi_an_goi_lai_vy_positive(self):
        # LAST decision wins: the negated An clause does not
        # veto the later positive Vy clause.
        r = sel("đừng gọi An, gọi lại cho Vy", names=("Vy",))
        self.assertEqual(r["selection"], "positive")

    def test_a_khong_thoi_cancelled(self):
        # Correction marker with NO new target: the selection is
        # abandoned. "thoi" alone is not a new target.
        r = sel("gọi lại cho Vy, à không, thôi", names=("Vy",))
        self.assertEqual(r["selection"], "cancelled")

    def test_khong_phai_vy_ma_la_an_replaced(self):
        # "khong phai <old> ma (la) <new>" replaces the old
        # target even without an "a khong" marker.
        r = sel("gọi cho Vy, không phải Vy mà là An",
                names=("Vy",))
        self.assertEqual(r["selection"], "replaced")

    def test_khong_phai_vy_exclusion_negated(self):
        # "khong phai Vy" with no "ma" and no verb after it is
        # an explicit exclusion of Vy, not a value correction.
        r = sel("gọi cho An, không phải Vy", names=("Vy",))
        self.assertEqual(r["selection"], "negated")

    def test_reselection_after_correction_positive(self):
        # A positive re-mention after the marker wins over the
        # marker: the user corrected back to the same target.
        r = sel("gọi cho Vy, à không, gọi lại cho Vy",
                names=("Vy",))
        self.assertEqual(r["selection"], "positive")


class TestMandatoryActionScoping(unittest.TestCase):
    def test_khong_can_nhan_chi_goi_call_positive(self):
        # Clause-scoped negation: the message clause is negated,
        # the call clause is positive. For action=call this is
        # positive (the negated action is a different action).
        r = sel("không cần nhắn, chỉ gọi lại cho Vy",
                names=("Vy",), action="call")
        self.assertEqual(r["selection"], "positive")

    def test_khong_can_nhan_chi_goi_message_negated(self):
        # Same text, other action: the general message negation
        # ("khong can nhan", no object) vetoes messaging.
        r = sel("không cần nhắn, chỉ gọi lại cho Vy",
                names=("Vy",), action="message")
        self.assertEqual(r["selection"], "negated")

    def test_dung_nhan_blocks_message_not_call(self):
        # A message negation must not leak into the call verdict
        # (no negated verdict for call), and must not fake a
        # call positive either: no call verb exists -> unknown.
        r_call = sel("đừng nhắn cho Vy", names=("Vy",),
                     action="call")
        self.assertEqual(r_call["selection"], "unknown")
        r_msg = sel("đừng nhắn cho Vy", names=("Vy",),
                    action="message")
        self.assertEqual(r_msg["selection"], "negated")

    def test_other_clause_negated_action(self):
        # (a) Negated action is message, queried action is call:
        # positive (no call veto for Vy; a positive call verb
        # exists elsewhere in the text).
        r = sel("gọi lại cho An, đừng nhắn cho Vy",
                names=("Vy",), action="call")
        self.assertEqual(r["selection"], "positive")

    def test_other_clause_same_action_negated(self):
        # (b) Same action negated in another clause: negated,
        # even though a positive call verb exists for An.
        r = sel("gọi lại cho An, đừng gọi cho Vy",
                names=("Vy",), action="call")
        self.assertEqual(r["selection"], "negated")


class TestMandatoryGenericAndQuotes(unittest.TestCase):
    def test_generic_callback_positive(self):
        # Generic callback with no name: positive for the
        # queried action (binding is thread A's job, not this
        # module's; the veto gate only checks the action).
        r = sel("gọi lại người vừa gọi")
        self.assertEqual(r["selection"], "positive")
        self.assertFalse(r["mention_present"])

    def test_generic_callback_negated(self):
        # Generic callback negated: negated even with no name.
        r = sel("đừng gọi lại người vừa gọi")
        self.assertEqual(r["selection"], "negated")

    def test_quoted_mention_only_unknown(self):
        # Rule 1: a name only inside quotes is message content,
        # not a selection -- but mention_present stays True so
        # the caller can tell the difference from "not mentioned".
        r = sel("nhắn là 'gọi lại cho Vy'", names=("Vy",),
                action="call")
        self.assertEqual(r["selection"], "unknown")
        self.assertTrue(r["mention_present"])

    def test_quoted_negation_not_counted(self):
        # A negation inside quotes must not veto: the quoted
        # span is stripped before selection scanning.
        r = sel("nhắn là 'đừng gọi cho Vy'", names=("Vy",),
                action="call")
        self.assertEqual(r["selection"], "unknown")
        self.assertTrue(r["mention_present"])

    def test_khong_in_message_content_not_negation(self):
        # "khong" inside the message content ("toi khong di
        # duoc") does not govern a callback verb, so it is not
        # an action negation. The "nhan" verb reads positive.
        r = sel("nhắn là 'tôi không đi được'", names=("Vy",),
                action="message")
        self.assertEqual(r["selection"], "positive")

    def test_khong_in_unquoted_content_not_negation(self):
        # Same, unquoted: "khong" + "di" is not "khong" +
        # callback verb, so the message verb stays positive.
        r = sel("nhắn cho Vy là tôi không đi được",
                names=("Vy",), action="message")
        self.assertEqual(r["selection"], "positive")


class TestMandatoryPurposeAndTail(unittest.TestCase):
    def test_purpose_clause_trailing_khong_positive(self):
        # Trailing "khong" of a purpose clause ("co ranh khong")
        # is a question tail, not an action negation: polarity
        # is decided only by what PRECEDES the verb.
        r = sel("gọi lại cho Vy để hỏi xem có rảnh không",
                names=("Vy",))
        self.assertEqual(r["selection"], "positive")

    def test_question_mood_unknown(self):
        # "co (nen) <verb> ... khong" is a question about the
        # action, not a request: unknown, never guessed positive.
        r = sel("có nên gọi lại cho Vy không", names=("Vy",))
        self.assertEqual(r["selection"], "unknown")

    def test_chua_goi_unknown(self):
        # "chua" + verb is a status ("not yet called"), not a
        # request and not a veto: unknown, never positive.
        r = sel("chưa gọi cho Vy", names=("Vy",))
        self.assertEqual(r["selection"], "unknown")


class TestMandatoryPhoneTailCorrection(unittest.TestCase):
    def test_tail_correction_new_number_positive(self):
        # Rule 6: the new tail is affirmed, the old tail value
        # is negated, the ACTION is not negated. For the
        # CORRECTED number the selection stays positive.
        r = sel("gọi cho số đuôi là sáu tám chứ không phải tám sáu",
                phones=("09832415068",))
        self.assertEqual(r["selection"], "positive")
        self.assertTrue(r["mention_present"])

    def test_tail_correction_old_number_replaced(self):
        # Symmetric case (module's own extension, same rule):
        # for the OLD number, the tail was corrected away, so
        # the old number is replaced, not selectable.
        r = sel("gọi cho số đuôi là sáu tám chứ không phải tám sáu",
                phones=("09832415086",))
        self.assertEqual(r["selection"], "replaced")

    def test_typed_phone_positive_and_negated(self):
        # Typed digit runs match on full equality after
        # normalisation; negation works the same as for names.
        r = sel("gọi cho 0902345678", phones=("0902345678",))
        self.assertEqual(r["selection"], "positive")
        r2 = sel("đừng gọi 0902345678", phones=("0902345678",))
        self.assertEqual(r2["selection"], "negated")

    def test_spoken_year_not_a_phone(self):
        # "nam sau" (next year) must not parse as phone digits
        # 56: spoken runs need phone context or length >= 7.
        # No phone mention, no call veto -> the verb still reads
        # positive via the veto contract, but mention_present
        # must be False (no phone was mentioned).
        r = sel("năm sau gọi cho Vy", phones=("0902345656",))
        self.assertFalse(r["mention_present"])


class TestNameMatchingContract(unittest.TestCase):
    def test_single_token_diacritic_sensitive(self):
        # Single-token names match case-insensitively but
        # diacritic-SENSITIVELY: "An" must not match "an" with a
        # different diacritic. Here "an" (eat) leaves no target
        # mention and the negated verb is specific to another
        # object, so the verdict is unknown, never negated.
        r = sel("đừng gọi ăn", names=("An",))
        self.assertEqual(r["selection"], "unknown")
        self.assertFalse(r["mention_present"])
        r2 = sel("đừng gọi An", names=("An",))
        self.assertEqual(r2["selection"], "negated")

    def test_multi_token_full_phrase_only(self):
        # R1-adjacent contract (thread A owns the full fix, but
        # this module must not reintroduce token intersection):
        # "Nguyen Binh" must not match target "Nguyen An" via
        # the shared "Nguyen"; the negated verb is specific to
        # another object, so the verdict is unknown.
        r = sel("đừng gọi Nguyễn Bình", names=("Nguyễn An",))
        self.assertEqual(r["selection"], "unknown")
        self.assertFalse(r["mention_present"])
        r2 = sel("gọi Nguyễn An", names=("Nguyễn An",))
        self.assertEqual(r2["selection"], "positive")
        self.assertTrue(r2["mention_present"])

    def test_other_full_name_fallback_positive_is_veto_only(self):
        # VETO-GATE CONTRACT, asserted explicitly: a positive
        # verb for ANOTHER full name yields "positive" for this
        # target, because this module answers "is the action
        # toward this target vetoed?" -- NOT "is this target the
        # chosen one?". The adapter must NEVER un-fire on this
        # module alone; thread A's binding is required. This
        # test pins the contract so a future reader does not
        # mistake "positive" for binding proof.
        r = sel("gọi Nguyễn Bình", names=("Nguyễn An",))
        self.assertEqual(r["selection"], "positive")
        self.assertFalse(r["mention_present"])


class TestGeneralVetoAsymmetry(unittest.TestCase):
    def test_general_veto_after_selection_negated(self):
        # A later object-less veto ("dung goi nua") cancels a
        # prior selection: the last decision is to stop calling.
        r = sel("gọi lại cho Vy, đừng gọi nữa", names=("Vy",))
        self.assertEqual(r["selection"], "negated")

    def test_general_positive_does_not_rescue_veto(self):
        # Asymmetry, safe direction: a later generic positive
        # ("goi lai di") does NOT re-select a vetoed target;
        # only an explicit positive re-mention of the target does.
        r = sel("đừng gọi cho Vy, gọi lại đi", names=("Vy",))
        self.assertEqual(r["selection"], "negated")

    def test_action_mismatch_unknown(self):
        # No verb for the queried action at all: unknown, even
        # though the target is mentioned with another action.
        r = sel("gọi cho Vy", names=("Vy",), action="message")
        self.assertEqual(r["selection"], "unknown")

    def test_empty_and_invalid_action(self):
        # Empty text: unknown, nothing mentioned. An invalid
        # action value fails safe to unknown, never positive.
        r = sel("", names=("Vy",))
        self.assertEqual(r["selection"], "unknown")
        self.assertFalse(r["mention_present"])
        r2 = sel("gọi cho Vy", names=("Vy",), action="teleport")
        self.assertEqual(r2["selection"], "unknown")

    def test_any_action_covers_both(self):
        # action="any" accepts a call verb and a message veto.
        r = sel("gọi cho Vy", names=("Vy",), action="any")
        self.assertEqual(r["selection"], "positive")
        r2 = sel("đừng nhắn cho Vy", names=("Vy",), action="any")
        self.assertEqual(r2["selection"], "negated")


class TestPastMarkerBlocking(unittest.TestCase):
    def test_nguoi_vua_goi_inner_verb_blocked(self):
        # Regression pin: the inner "goi" of "nguoi vua goi"
        # is a relative clause ("who just called"), not a
        # second imperative. Without past-marker blocking, the
        # negated outer verb lost to this inner positive verb
        # and "dung goi lai nguoi vua goi" read positive.
        r = sel("đừng gọi lại người vừa gọi")
        self.assertEqual(r["selection"], "negated")
        r2 = sel("gọi lại người vừa gọi")
        self.assertEqual(r2["selection"], "positive")

    def test_vua_da_past_statement_unknown(self):
        # "Vy vua goi" / "da goi cho Vy" report a past action,
        # they do not request one: unknown, never positive.
        r = sel("Vy vừa gọi", names=("Vy",))
        self.assertEqual(r["selection"], "unknown")
        r2 = sel("đã gọi cho Vy", names=("Vy",))
        self.assertEqual(r2["selection"], "unknown")

    def test_correlative_vua_vua_not_past(self):
        # "vua ... vua ..." (both ... and ...) is correlative,
        # not past tense: both verbs stay positive.
        r = sel("vừa gọi vừa nhắn cho Vy", names=("Vy",),
                action="call")
        self.assertEqual(r["selection"], "positive")


if __name__ == "__main__":
    unittest.main(verbosity=2)
