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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lifemate.lifemate_callback_negation import (  # noqa: E402
    _has_other_number,
    analyze_action_selection,
    analyze_instruction_selection,
    analyze_topic_selection,
    binding_action_class,
    instruction_action,
    phone_mentions_all_content,
    phone_numbers_for_action,
)
from lifemate.lifemate_gates_adapter import decide as _decide  # noqa: E402

KINDS = {"phone.call": "write", "sms.send": "write"}
Y = "0911111111"
X = "0902345678"


def dec(text, number=Y, tool="phone.call"):
    return _decide({"name": tool,
                    "arguments": {"phone_number": number}},
                   [], [], text, KINDS)


def dec_reasons(d):
    return [a.get("selection_reason") for a in d.adjustments]


def sel(text, names=(), phones=(), action="call"):
    return analyze_action_selection(text, target_names=names,
                                    target_phones=phones,
                                    action=action)


def instr(text, phones=("0902345678",), names=()):
    return analyze_instruction_selection(text, target_names=names,
                                         target_phones=phones)


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


class TestInstructionSelectionLayerC(unittest.TestCase):
    """Layer C unit tests (thread A, R4): continuation of an
    anaphoric instruction reference. These test the analyzer
    ONLY -- whether the adapter vetoes on it is covered by the
    adapter suite. Scope: the analyzer judges the reference
    clause; it never proves a binding (a "continue" here is
    not an un-fire by itself)."""

    def test_r4_valid_control_continues(self):
        r = instr("Làm như em dặn lúc nãy")
        self.assertEqual(r["instruction_selection"], "continue")
        self.assertTrue(r["reference_present"])

    def test_r4_cancellation_wrappers_cancel(self):
        for text in ["Thôi, không cần làm như em dặn lúc nãy nữa",
                     "Khỏi làm như lúc nãy nữa",
                     "Đừng làm như em dặn lúc nãy"]:
            r = instr(text)
            self.assertEqual(r["instruction_selection"], "cancelled",
                             text)
            self.assertTrue(r["reference_present"])

    def test_question_and_recount_block(self):
        r = instr("Có nên làm như em dặn lúc nãy không?")
        self.assertEqual(r["instruction_selection"], "blocked")
        self.assertEqual(r["reason"], "instruction_question_blocked")
        r = instr("Hôm qua em đã làm như em dặn lúc nãy rồi")
        self.assertEqual(r["instruction_selection"], "blocked")
        self.assertEqual(r["reason"], "instruction_recount_blocked")

    def test_quoted_reference_only_blocks(self):
        r = instr('Anh ấy bảo "làm như em dặn lúc nãy"')
        self.assertEqual(r["instruction_selection"], "blocked")
        self.assertEqual(r["reason"], "instruction_quoted_only")
        self.assertTrue(r["reference_present"])

    def test_bare_reference_is_unknown_not_continue(self):
        # 0764-class: a bare reference with no verb and no
        # marker must NOT be upgraded to a continuation. The
        # adapter abstains here; the analyzer records unknown.
        r = instr("Như em dặn lúc nãy")
        self.assertEqual(r["instruction_selection"], "unknown")
        self.assertTrue(r["reference_present"])

    def test_no_reference_is_unknown_not_present(self):
        r = instr("Gọi số 0902345678 giúp tôi")
        self.assertEqual(r["instruction_selection"], "unknown")
        self.assertFalse(r["reference_present"])

    def test_replacement_with_new_number(self):
        r = instr("Đừng làm như lúc nãy nữa, gọi số 0912345678 đi")
        self.assertEqual(r["instruction_selection"], "replaced")
        # Same-number re-request is NOT a replacement at this
        # layer: the adapter's direct-selection skip handles it
        # (a fresh direct request stands on its own).
        r = instr("Đừng làm như lúc nãy nữa, gọi số 0902345678 đi")
        self.assertEqual(r["instruction_selection"], "cancelled")

    def test_last_reference_clause_governs(self):
        # Recount clause, then continuation clause: the LAST
        # reference governs, so this continues.
        r = instr("Em đã kể là hôm qua em dặn rồi. "
                  "Bây giờ làm như em dặn lúc nãy giúp tôi.")
        self.assertEqual(r["instruction_selection"], "continue")
        # Continuation clause, then an unrelated distractor
        # clause: the distractor must not cancel it.
        r = instr("Làm như em dặn lúc nãy giúp tôi. "
                  "Thôi, chuyện kia để sau đi.")
        self.assertEqual(r["instruction_selection"], "continue")

    def test_bare_thoi_is_not_a_cancellation_marker(self):
        # "Thôi" alone must not cancel: a "thôi" clause plus a
        # bare reference carries no continuation verb and no
        # cancellation marker, so it stays unknown rather than
        # being guessed as cancelled. (With "làm" present, the
        # "làm" continuation governs instead -- see
        # test_r4_valid_control_continues.)
        r = instr("Thôi, như lúc nãy")
        self.assertEqual(r["instruction_selection"], "unknown")

    def test_anaphoric_reference_continuation(self):
        r = instr("Gọi lại người vừa gọi giúp tôi")
        self.assertEqual(r["instruction_selection"], "continue")


class TestInstructionAction(unittest.TestCase):
    """instruction_action: action class of a text's verbs."""

    def test_call_message_both_unknown(self):
        self.assertEqual(instruction_action(
            "Gọi số 0902345678 giúp tôi"), "call")
        self.assertEqual(instruction_action(
            "Nhắn số 0902345678 giúp tôi"), "message")
        self.assertEqual(instruction_action(
            "Gọi số X giúp tôi, nhắn tin báo sau"), "both")
        self.assertEqual(instruction_action(
            "Số của Vy là 0902345678"), "unknown")
        self.assertEqual(instruction_action(""), "unknown")


class TestInstructionSelectionRound2(unittest.TestCase):
    """Layer C round 2: last-decisive-wins clause scan.

    Each case pins one finding (S1-S9, S15, M-c, M-d) at the
    analyzer level; adapter-level consequences live in
    TestLayerCRound2 (test_gates_adapter.py). A "continue"
    here never proves a binding by itself -- it only allows
    the adapter's bound-reference un-fire to stand.
    """

    def test_s1_khong_phai_lam_cancelled(self):
        # Folded particle set: "phải" folds to "phai" and must
        # match (v1 compared folds against diacritic forms and
        # never matched).
        r = instr("Không phải làm như lúc nãy")
        self.assertEqual(r["instruction_selection"], "cancelled")

    def test_s2_stop_verbs_cancel(self):
        for text in ["Dừng làm như lúc nãy",
                     "Ngừng làm như em dặn lúc nãy",
                     "Ngừng làm như lúc nãy đi"]:
            r = instr(text)
            self.assertEqual(r["instruction_selection"], "cancelled",
                             text)

    def test_s3_manner_negation_without_lam_cancelled(self):
        r = instr("Không phải như lúc nãy đâu")
        self.assertEqual(r["instruction_selection"], "cancelled")

    def test_s4_wider_question_frames_block(self):
        for text in ["Nên làm như lúc nãy không?",
                     "Làm như lúc nãy có được không?",
                     "Có làm như lúc nãy được không?"]:
            r = instr(text)
            self.assertEqual(r["instruction_selection"], "blocked",
                             text)
            self.assertEqual(r["reason"],
                             "instruction_question_blocked", text)
        # An affirmative request must NOT be blocked by the
        # wider frame.
        r = instr("Làm như lúc nãy đi")
        self.assertEqual(r["instruction_selection"], "continue")

    def test_s5_past_after_verb_blocks(self):
        for text in ["Làm như lúc nãy rồi",
                     "Làm như lúc nãy xong rồi"]:
            r = instr(text)
            self.assertEqual(r["instruction_selection"], "blocked",
                             text)
            self.assertEqual(r["reason"],
                             "instruction_recount_blocked", text)
        # Sequential "rồi" before another verb is NOT a
        # recount: do it, THEN call Vy.
        r = instr("Làm như lúc nãy rồi gọi cho Vy đi",
                  names=("Vy",))
        self.assertEqual(r["instruction_selection"], "continue")

    def test_s6_chua_status_blocks(self):
        for text in ["Chưa làm như lúc nãy",
                     "Em chưa làm như lúc nãy đâu"]:
            r = instr(text)
            self.assertEqual(r["instruction_selection"], "blocked",
                             text)
            self.assertEqual(r["reason"],
                             "instruction_not_yet_blocked", text)

    def test_s7_replacement_without_cancel_marker(self):
        for text in ["Làm như lúc nãy nhưng gọi số 0911111111 đi",
                     "Làm như lúc nãy, nhưng đổi thành số 0911111111"]:
            r = instr(text, phones=("0902345678",))
            self.assertEqual(r["instruction_selection"], "replaced",
                             text)
        # Same-number re-request is not a replacement.
        r = instr("Làm như lúc nãy nhưng gọi số 0902345678 đi",
                  phones=("0902345678",))
        self.assertEqual(r["instruction_selection"], "continue")

    def test_s8_tail_change_replaces(self):
        r = instr("Làm như lúc nãy nhưng đuôi đổi thành 1111",
                  phones=("0902345678",))
        self.assertEqual(r["instruction_selection"], "replaced")
        # Same tail is not a replacement.
        r = instr("Làm như lúc nãy nhưng đuôi đổi thành 5678",
                  phones=("0902345678",))
        self.assertEqual(r["instruction_selection"], "continue")

    def test_s9_last_decisive_wins_across_clauses(self):
        for text in ["Làm như lúc nãy đi, đừng làm nữa",
                     "Làm như lúc nãy đi, thôi đừng làm nữa",
                     "Làm như lúc nãy, à không, thôi",
                     "Làm như lúc nãy đi, nhưng thôi"]:
            r = instr(text)
            self.assertEqual(r["instruction_selection"], "cancelled",
                             text)
        # Cancel-then-reinvoke still continues.
        r = instr("Đừng làm nữa, làm như lúc nãy đi")
        self.assertEqual(r["instruction_selection"], "continue")
        # A cancellation naming a KNOWN-DIFFERENT target does
        # not override the continuation for this instruction.
        r = instr("Làm như lúc nãy đi, đừng gọi cho An nữa",
                  names=("Vy",))
        self.assertEqual(r["instruction_selection"], "continue")
        # Same-target later cancellation does govern.
        r = instr("Làm như lúc nãy đi, đừng gọi cho Vy nữa",
                  names=("Vy",))
        self.assertEqual(r["instruction_selection"], "cancelled")

    def test_s9_bare_thoi_mid_text_is_discourse(self):
        # Regression guard for the v1 test: a mid-text "thôi"
        # introducing a new topic does not withdraw the request.
        r = instr("Làm như em dặn lúc nãy giúp tôi. "
                  "Thôi, chuyện kia để sau đi.")
        self.assertEqual(r["instruction_selection"], "continue")

    def test_s15_conditional_blocks(self):
        for text in ["Nếu rảnh thì làm như lúc nãy",
                     "Nếu Vy đồng ý thì làm như lúc nãy"]:
            r = instr(text)
            self.assertEqual(r["instruction_selection"], "blocked",
                             text)
            self.assertEqual(r["reason"],
                             "instruction_conditional_blocked", text)

    def test_mc_reported_speech_blocks(self):
        r = instr("Vy bảo làm như lúc nãy")
        self.assertEqual(r["instruction_selection"], "blocked")
        self.assertEqual(r["reason"], "instruction_reported_speech")
        # The user reporting their own words is not reported
        # speech: "em bảo" keeps the continuation.
        r = instr("Em bảo làm như lúc nãy")
        self.assertEqual(r["instruction_selection"], "continue")

    def test_md_khoan_deferral_blocks(self):
        r = instr("Làm như lúc nãy đi, khoan đã")
        self.assertEqual(r["instruction_selection"], "blocked")
        self.assertEqual(r["reason"], "instruction_deferred_blocked")


class TestTopicSelection(unittest.TestCase):
    """S14 topic branch at the analyzer level (adapter
    consequences in TestLayerCRound2)."""

    def test_topic_cancel_question_block(self):
        cases = [
            ("Đừng làm như lúc nãy nữa, vụ hai trăm nghìn ấy",
             "cancelled"),
            ("Đừng hoàn lại hai trăm nghìn như tin nhắn lúc nãy nữa",
             "cancelled"),
            ("Có nên hoàn lại hai trăm nghìn không?", "blocked"),
            ("Hoàn lại hai trăm nghìn cho Vy đi", "unknown"),
        ]
        for text, exp in cases:
            r = analyze_topic_selection(text)
            self.assertEqual(r["topic_selection"], exp, text)


class TestInstructionActionOther(unittest.TestCase):
    """S11: recognised non-communication verbs are "other",
    never silently "unknown"-as-match."""

    def test_other_verbs(self):
        for text in ["Lưu số 0902345678 giúp tôi",
                     "Tra cứu số 0902345678 giúp tôi",
                     "Xóa số 0902345678 giúp tôi",
                     "Kiểm tra số 0902345678 giúp tôi",
                     "Xem số 0902345678 giúp tôi"]:
            self.assertEqual(instruction_action(text), "other", text)

    def test_mixed_callback_and_other_is_both(self):
        self.assertEqual(instruction_action(
            "Gọi số 0902345678 rồi lưu số đó giúp tôi"), "both")


class TestInstructionSelectionRound3(unittest.TestCase):
    """Layer C round 3 (F3/F4/F7/F8): new-number cues, tail
    adjacency, wait/only-then, khoan scope."""

    def _sel(self, text, phones=("0902345678",)):
        return analyze_instruction_selection(
            text, target_phones=phones)

    def test_new_number_statement_is_replacement(self):
        # F3: "số mới là X" states the number changed.
        sel = self._sel("Làm như lúc nãy đi, số mới là 0911111111")
        self.assertEqual(sel["instruction_selection"], "replaced")
        sel = self._sel("Làm như lúc nãy đi, số mới nhất là "
                        "0902345678")
        self.assertEqual(sel["instruction_selection"], "continue")

    def test_bare_ma_fragment_is_replacement(self):
        # F3 weak variant S7a: bare "mà + số X", no predicate.
        sel = self._sel("Làm như lúc nãy đi, mà số 0911111111")
        self.assertEqual(sel["instruction_selection"], "replaced")
        # ... but not with an informational/question predicate.
        for text in ["Làm như lúc nãy đi, mà số 0911111111 là "
                     "số tổng đài",
                     "Làm như lúc nãy đi, mà số 0911111111 thì sao"]:
            sel = self._sel(text)
            self.assertEqual(sel["instruction_selection"],
                             "continue", text)
        # A verb-carrying "mà" clause still replaces, but via
        # the normal positive-verb cue, not the fragment rule.
        sel = self._sel("Làm như lúc nãy đi, mà nhớ gọi số "
                        "0911111111")
        self.assertEqual(sel["instruction_selection"], "replaced")

    def test_tail_change_any_length_adjacent(self):
        # F4: 2- and 5-digit tails count in explicit context.
        for text in ["Làm như lúc nãy đi, đuôi đổi thành 56789",
                     "Làm như lúc nãy đi, đuôi đổi thành 68"]:
            sel = self._sel(text)
            self.assertEqual(sel["instruction_selection"],
                             "replaced", text)
        # Tail-same still does not veto.
        sel = self._sel("Làm như lúc nãy đi, đuôi đổi thành 5678")
        self.assertEqual(sel["instruction_selection"], "continue")
        # An unrelated digit far from the change verb does not
        # read as a tail change (same clause, no comma).
        sel = self._sel("Làm như lúc nãy đi, đuôi tóc đổi thành "
                        "màu khác 2 người")
        self.assertEqual(sel["instruction_selection"], "continue")

    def test_he_conditional_and_wait_then(self):
        # F7: "hễ...thì" is a whenever-conditional.
        sel = self._sel("Hễ rảnh thì làm như lúc nãy")
        self.assertEqual(sel["instruction_selection"], "blocked")
        self.assertEqual(sel["reason"],
                         "instruction_conditional_blocked")
        # Đợi/chờ + condition + rồi (+mới) làm defers.
        for text in ["Đợi Vy trả lời rồi mới làm như lúc nãy",
                     "Chờ rảnh rồi mới làm như lúc nãy",
                     "Đợi rảnh rồi làm như lúc nãy"]:
            sel = self._sel(text)
            self.assertEqual(sel["instruction_selection"],
                             "blocked", text)
            self.assertEqual(sel["reason"],
                             "instruction_wait_then_blocked", text)
        # ... but a particle-only gap is a short pause (S15d7).
        sel = self._sel("Đợi đã rồi làm như lúc nãy")
        self.assertEqual(sel["instruction_selection"], "continue")

    def test_only_then_trail_not_recount(self):
        # F7 trail: bare "rồi mới làm" is only-then, not past.
        sel = self._sel("Rồi mới làm như lúc nãy")
        self.assertEqual(sel["instruction_selection"], "blocked")
        self.assertEqual(sel["reason"],
                         "instruction_only_then_blocked")
        # Without a preceding "rồi", "mới làm" stays a recount.
        sel = self._sel("Mới làm như lúc nãy xong")
        self.assertEqual(sel["instruction_selection"], "blocked")
        self.assertEqual(sel["reason"],
                         "instruction_recount_blocked")

    def test_khoan_governing_lam_blocks(self):
        # F8: khoan scoping "làm" in the same clause defers.
        for text in ["Khoan làm như lúc nãy đã",
                     "Khoan làm như lúc nãy",
                     "Khoan làm như lúc nãy đi"]:
            sel = self._sel(text)
            self.assertEqual(sel["instruction_selection"],
                             "blocked", text)
            self.assertEqual(sel["reason"],
                             "instruction_deferred_blocked", text)
        # ... but wait-then-do does not (Md7).
        sel = self._sel("Khoan đã rồi làm như lúc nãy")
        self.assertEqual(sel["instruction_selection"], "continue")


class TestInstructionActionRound3(unittest.TestCase):
    """F5 inventory + F6 wrappers for instruction_action."""

    def test_unknown_actions(self):
        # F5: verbs outside every inventory stay unknown.
        self.assertEqual(instruction_action(
            "Báo số 0902345678 cho Vy giúp tôi"), "unknown")
        # CONTRACT CHANGE (selection round, ATK-019): bare
        # "chuyển" is no longer outside every inventory -- it
        # is a recognised forward/transfer verb (see the
        # round-4 S3 precedent for "gửi tiền" below), so it
        # is "other", not "unknown". Both labels veto
        # call/message proposals in layer C; the new label
        # records that the action IS recognised, just not a
        # callback.
        self.assertEqual(instruction_action(
            "Chuyển số 0902345678 cho Vy giúp tôi"), "other")
        # Bare "gửi" (no "tin nhắn"/"sms") is not a message verb.
        # CONTRACT CHANGE (round-4 fix S3): "gửi tiền" is no
        # longer "unknown" -- it is a recognised foreign action
        # ("other"), like "chuyển tiếp / forward / share". Both
        # labels veto call/message proposals in layer C; the
        # new label records that the action IS recognised, just
        # not a callback.
        self.assertEqual(instruction_action(
            "Gửi tiền tới số 0902345678 giúp tôi"), "other")

    def test_wrapper_verbs_are_other(self):
        # F6: scheduling / reminding a call is not a call now.
        for text in ["Đặt lịch gọi số 0902345678 giúp tôi",
                     "Đặt hẹn gọi số 0902345678 giúp tôi",
                     "Nhắc tôi gọi số 0902345678 giúp tôi"]:
            self.assertEqual(instruction_action(text), "other",
                             text)
        # ... but a direct call before/after a sequence is not
        # wrapped.
        self.assertEqual(instruction_action(
            "Gọi số 0902345678 rồi đặt lịch họp giúp tôi"), "call")
        self.assertEqual(instruction_action(
            "Đặt lịch họp rồi gọi số 0902345678 giúp tôi"), "call")

    def test_contact_class(self):
        # F5 inventory: generic "liên hệ" is "contact".
        self.assertEqual(instruction_action(
            "Liên hệ số 0902345678 giúp tôi"), "contact")
        # Bare "liên lạc" is NOT in the inventory.
        self.assertEqual(instruction_action(
            "Liên lạc số 0902345678 giúp tôi"), "unknown")


class TestRound4Batch3Selection(unittest.TestCase):
    """Round-4 batch-3 selection rules at the B level (S3/S4/S6).

    B is veto-only: "positive" means "no veto found", never
    proof of selection. These tests pin the veto reasons, not
    just the direction, so a later refactor cannot silently
    swap one mechanism for another.
    """

    X = ("0902345678",)

    def test_s6_wrapper_blocks_immediate_selection(self):
        # S6: a callback verb under a scheduling / reminder
        # wrapper is not an immediate request.
        for text in ["Đặt lịch gọi số 0902345678",
                     "Nhắc tôi đặt lịch gọi số 0902345678",
                     "Nhắc gọi số 0902345678 rồi đặt lịch họp",
                     "Đặt hẹn gọi số 0902345678"]:
            r = sel(text, phones=self.X, action="call")
            self.assertEqual(r["selection"], "unknown", text)
            self.assertEqual(r["reason"], "blocked_verb_only", text)

    def test_s6_sequenced_call_stays_positive(self):
        # Control: the call precedes the wrapper, or "rồi"
        # sequences a later call -- the verb is immediate, and
        # the positive comes from the verb itself, not from
        # wrapper blindness.
        for text in ["Gọi số 0902345678 rồi đặt lịch họp",
                     "Đặt lịch họp rồi gọi số 0902345678"]:
            r = sel(text, phones=self.X, action="call")
            self.assertEqual(r["selection"], "positive", text)
            self.assertEqual(r["reason"], "positive_selection",
                             text)

    def test_s3_foreign_action_vetoes(self):
        # S3: forwarding / sharing the number selects a
        # different action for it, never a call to it.
        for text in ["Chuyển tiếp số 0902345678 đi",
                     "Forward số 0902345678",
                     "Share số 0902345678",
                     "Lưu số 0902345678 lại"]:
            r = sel(text, phones=self.X, action="call")
            self.assertEqual(r["selection"], "unknown", text)
            self.assertEqual(r["reason"], "other_action_verb_only",
                             text)

    def test_s3_foreign_with_recipient_is_content(self):
        # Same veto, reached via the content rule when a
        # recipient is named: the outcome (veto) is what
        # matters, the reason records which rule fired.
        for text in ["Chuyển tiếp số 0902345678 cho Vy",
                     "Forward số 0902345678 cho Vy",
                     "Share số 0902345678 cho Vy"]:
            r = sel(text, phones=self.X, action="call")
            self.assertEqual(r["selection"], "unknown", text)

    def test_s3_later_genuine_call_wins(self):
        # A genuine later call re-selects: the foreign rule
        # only fires when no queried-verb event exists.
        r = sel("Chuyển tiếp số 0902345678 cho Vy, "
                "gọi số 0902345678 đi",
                phones=self.X, action="call")
        self.assertEqual(r["selection"], "positive")

    def test_s4_number_as_content_vetoes(self):
        # S4: the number is message content for another
        # recipient, not the message's recipient.
        for text in ["Gửi số 0902345678 cho Vy",
                     "Nhắn cho Vy số 0902345678"]:
            r = sel(text, phones=self.X, action="message")
            self.assertEqual(r["selection"], "unknown", text)
            self.assertEqual(
                r["reason"],
                "number_as_content_for_other_recipient", text)

    def test_s4_call_form_channel_and_plain_stay_positive(self):
        # Controls: the canonical call form, the "qua"
        # channel, and a recipient-less message all still
        # select the number.
        r = sel("Gọi cho Vy số 0902345678", phones=self.X,
                action="call")
        self.assertEqual(r["selection"], "positive")
        r = sel("Nhắn cho Vy qua số 0902345678", phones=self.X,
                action="message")
        self.assertEqual(r["selection"], "positive")
        r = sel("Nhắn số 0902345678", phones=self.X,
                action="message")
        self.assertEqual(r["selection"], "positive")

    def test_s4_owner_recipient_not_content(self):
        # Owner exception: when the named recipient IS the
        # bound counterpart (in target names), the recipient
        # reading stands and the mention is genuine.
        r = sel("Nhắn cho Vy số 0902345678", names=("Vy",),
                phones=self.X, action="message")
        self.assertEqual(r["selection"], "positive")
        self.assertTrue(phone_mentions_all_content(
            "Nhắn cho Vy số 0902345678", ("Vy",), self.X)
            is False)

    def test_s4_all_content_helper(self):
        self.assertTrue(phone_mentions_all_content(
            "Gửi số 0902345678 cho Vy", (), self.X))
        self.assertFalse(phone_mentions_all_content(
            "Gọi cho Vy số 0902345678", (), self.X))
        self.assertFalse(phone_mentions_all_content(
            "Nhắn cho Vy qua số 0902345678", (), self.X))
        self.assertFalse(phone_mentions_all_content(
            "Gọi số 0902345678 đi", (), self.X))
        # Mixed: one genuine + one content mention is NOT
        # all-content (the genuine selection stands).
        self.assertFalse(phone_mentions_all_content(
            "Gọi số 0902345678 đi, nhắn cho Vy số 0902345678",
            (), self.X))


class TestRound5Batch4Selection(unittest.TestCase):
    """Round-5 batch-4 MINOR fixes at the B (selection) level.

    Synthetic only. Each test states what it proves; the
    decide-level consequences are pinned in test_gates_adapter.
    """

    X = "0902345678"
    Y = "0911111111"

    def test_lookup_governed_mention_is_not_content(self):
        # F-B4-3: a number governed by a lookup verb is the
        # object of a lookup, never message content, even when
        # a later clause names another recipient.
        self.assertFalse(phone_mentions_all_content(
            "Tìm số %s rồi gọi cho Vy" % self.X, (), (self.X,)))
        self.assertFalse(phone_mentions_all_content(
            "Tìm số %s rồi nhắn cho Vy" % self.X, (), (self.X,)))
        self.assertFalse(phone_mentions_all_content(
            "Lấy số %s rồi gọi cho Vy" % self.X, (), (self.X,)))
        self.assertFalse(phone_mentions_all_content(
            "Tra cứu số %s rồi gọi cho Vy" % self.X, (), (self.X,)))
        # S4 originals still content: no lookup verb governs.
        self.assertTrue(phone_mentions_all_content(
            "Nhắn cho Vy số %s" % self.X, (), (self.X,)))
        self.assertTrue(phone_mentions_all_content(
            "Gửi số %s cho Vy" % self.X, (), (self.X,)))

    def test_lookup_then_callback_is_positive(self):
        # F-B4-3, narrowed by round-6 fix S3 (which SUPERSEDES
        # the blanket F-B4-3 premise): a lookup is preparatory
        # only when the later positive verb targets the
        # proposal (target name) or is bare. A later verb
        # targeting a specific OTHER person never makes the
        # lookup preparatory to this proposal -- the text
        # selects a call/message to that person, not to X.
        # (This also supersedes batch-4 probe case
        # G3/find-then-call, whose un-fire expectation encoded
        # the same pre-S3 premise; no per-name carve-out is
        # possible, since 3c "nhan cho Binh" is identical in
        # shape and must fire.)
        self.assertEqual(
            sel("Tìm số %s rồi gọi cho Vy" % self.X,
                names=("Vy",), phones=(self.X,),
                action="call")["selection"],
            "positive")
        self.assertEqual(
            sel("Tìm số %s rồi nhắn cho Vy" % self.X,
                names=("Vy",), phones=(self.X,),
                action="message")["selection"],
            "positive")
        self.assertEqual(
            sel("Tìm số %s rồi gọi" % self.X,
                phones=(self.X,), action="call")["selection"],
            "positive")
        self.assertEqual(
            sel("Tìm số %s rồi gọi cho Vy" % self.X,
                phones=(self.X,), action="call")["selection"],
            "unknown")
        self.assertEqual(
            sel("Tìm số %s rồi nhắn cho Bình" % self.X,
                phones=(self.X,), action="message")["selection"],
            "unknown")
        # A negated later verb does not rescue the lookup.
        self.assertNotEqual(
            sel("Tìm số %s rồi đừng gọi cho Vy" % self.X,
                phones=(self.X,), action="call")["selection"],
            "positive")

    def test_delegation_blocks_the_call_verb(self):
        # F-B4-6: nho / bao + person + verb scopes the verb to
        # the delegatee; it is blocked, never the user's own
        # positive selection.
        for txt in ("Nhờ Vy gọi số %s giúp" % self.X,
                    "Bảo Vy gọi số %s giúp tôi" % self.X,
                    "Nhờ Vy giúp gọi số %s" % self.X,
                    "Nhờ anh Nam gọi số %s" % self.X,
                    "Bảo Nguyễn Vy gọi số %s" % self.X):
            res = sel(txt, phones=(self.X,), action="call")
            self.assertEqual(res["selection"], "unknown")
            self.assertEqual(res["reason"], "blocked_verb_only")
        # "Nhờ Vy" with no following verb is unrelated.
        self.assertEqual(
            sel("Nhờ Vy nhé", phones=(self.X,),
                action="call")["selection"], "unknown")

    def test_delegation_does_not_overreach(self):
        # Generic pronouns are not third-party delegatees:
        # "nhờ em gọi" asks the assistant itself (direct).
        self.assertEqual(
            sel("Nhờ em gọi số %s giúp" % self.X,
                phones=(self.X,), action="call")["selection"],
            "positive")
        # "bảo là / bảo sao" are not delegation patterns.
        self.assertEqual(
            sel("Bảo là gọi số %s đi" % self.X,
                phones=(self.X,), action="call")["selection"],
            "positive")
        self.assertEqual(
            sel("Bảo sao không gọi số %s" % self.X,
                phones=(self.X,), action="call")["selection"],
            "negated")

    def test_channel_prepositions(self):
        # F-B4-7: qua / bang / o / theo / vao make X the
        # channel, not content; "tu" stays sender-side.
        for prep in ("qua", "bằng", "ở", "theo", "vào"):
            self.assertEqual(
                sel("Nhắn cho Vy %s số %s" % (prep, self.X),
                    phones=(self.X,),
                    action="message")["selection"], "positive")
        res = sel("Nhắn cho Vy từ số %s" % self.X,
                  phones=(self.X,), action="message")
        self.assertEqual(res["selection"], "unknown")
        self.assertEqual(
            res["reason"], "number_as_content_for_other_recipient")

    def test_forward_then_bare_call_is_not_positive(self):
        # F-B4-4 (discourse scope): a bare call verb after the
        # same clause forwarded the TARGET number to a named
        # other recipient has an elided, undetermined target.
        res = sel("Chuyển tiếp số %s cho Vy rồi gọi" % self.X,
                  phones=(self.X,), action="call")
        self.assertEqual(res["selection"], "unknown")
        # Explicit object after the verb: unaffected.
        self.assertEqual(
            sel("Chuyển tiếp số %s cho Vy, rồi gọi Số %s"
                % (self.X, self.X),
                phones=(self.X,), action="call")["selection"],
            "positive")
        # Forward of a DIFFERENT number: no suppression.
        self.assertEqual(
            sel("Chuyển tiếp số %s cho Vy rồi gọi" % self.Y,
                phones=(self.X,), action="call")["selection"],
            "positive")
        # Generic recipient: no suppression.
        self.assertEqual(
            sel("Chuyển tiếp số %s cho em rồi gọi" % self.X,
                phones=(self.X,), action="call")["selection"],
            "positive")

    def test_forward_adjacent_clause_suppression(self):
        # Round-6 fix S4: punctuation must not flip one
        # discourse unit -- a forward in the immediately
        # preceding clause of the same text suppresses a bare
        # callback verb exactly like a same-clause forward.
        self.assertEqual(
            sel("Chuyển tiếp số %s cho Vy rồi, gọi" % self.X,
                phones=(self.X,), action="call")["selection"],
            "unknown")
        self.assertEqual(
            sel("Chuyển tiếp số %s cho Vy rồi. Gọi" % self.X,
                phones=(self.X,), action="call")["selection"],
            "unknown")
        # Delegated forward + bare call, same root: the
        # forward is not a callback verb, so delegation does
        # not govern it, but the adjacent-clause suppression
        # still applies to the bare verb.
        self.assertEqual(
            sel("Nhờ Vy chuyển tiếp số %s cho Vy, gọi" % self.X,
                phones=(self.X,), action="call")["selection"],
            "unknown")

    def test_delegation_nho_va_filler(self):
        # Round-6 fix M1: "nho va" is the fixed phrase "ask a
        # favour" -- "va" is filler, never a person. Skipping
        # it (not stopping on it) keeps "nho va Vy goi"
        # delegated while "nho va goi" stays a direct request.
        self.assertEqual(
            sel("Nhờ vả Vy gọi số %s" % self.X,
                phones=(self.X,), action="call")["selection"],
            "unknown")
        self.assertEqual(
            sel("Nhờ vả gọi số %s" % self.X,
                phones=(self.X,), action="call")["selection"],
            "positive")

    def test_channel_sender_possessive_is_content(self):
        # Round-6 fix N5: a sender possessive immediately after
        # the number ("bang so X cua toi / em / minh") makes
        # the number the sender's instrument, not the
        # recipient's channel address -- the channel exception
        # must not apply.
        self.assertTrue(phone_mentions_all_content(
            "Nhắn cho Vy bằng số %s của tôi" % self.X,
            (), (self.X,)))
        self.assertTrue(phone_mentions_all_content(
            "Nhắn cho Vy bằng số %s của em" % self.X,
            (), (self.X,)))
        self.assertTrue(phone_mentions_all_content(
            "Nhắn cho Vy qua số %s của mình" % self.X,
            (), (self.X,)))
        # Pin (i): without a sender possessive, the bare-number
        # channel still reads as the recipient's address.
        self.assertFalse(phone_mentions_all_content(
            "Nhắn cho Vy bằng số %s" % self.X, (), (self.X,)))
        self.assertFalse(phone_mentions_all_content(
            "Nhắn cho Vy qua số %s" % self.X, (), (self.X,)))

    def test_sender_possessive_breaks_name_event(self):
        # Round-6 delta: the text asserts the target number
        # belongs to the sender ("bang so X cua toi"), breaking
        # the name == number equivalence the owner exception
        # relies on. With the target name in scope (roster
        # Vy -> X), the name mention "Vy" must NOT generate a
        # positive event toward X: the action targets Vy, not
        # the sender's number.
        for pronoun in ("tôi", "em", "mình"):
            res = sel("Nhắn cho Vy bằng số %s của %s"
                      % (self.X, pronoun),
                      names=("Vy",), phones=(self.X,),
                      action="message")
            self.assertEqual(res["selection"], "unknown", pronoun)
            self.assertEqual(res["reason"],
                             "number_as_content_for_other_recipient",
                             pronoun)

    def test_name_event_stands_without_possessive(self):
        # Control: without a sender possessive, the owner
        # exception stands -- recipient Vy IS the target, so
        # "nhan cho Vy bang so X" selects messaging X.
        res = sel("Nhắn cho Vy bằng số %s" % self.X,
                  names=("Vy",), phones=(self.X,),
                  action="message")
        self.assertEqual(res["selection"], "positive")
        # "anh" can be a third person, so it keeps the channel
        # reading (not a sender possessive).
        res = sel("Nhắn cho Vy bằng số %s của anh" % self.X,
                  names=("Vy",), phones=(self.X,),
                  action="message")
        self.assertEqual(res["selection"], "positive")


class TestRound7Batch6Selection(unittest.TestCase):
    """Round-7 batch-6 SERIOUS + MINOR fixes at the B level.

    Synthetic only. Each test states what it proves; the
    decide-level consequences are pinned in test_gates_adapter.
    """

    X = "0902345678"
    Y = "0911111111"

    def test_forward_empty_connector_clause_skipped(self):
        # Round-7 fix S1: a clause with no verb, no digit run
        # and no other content ("tuy nhien", "the nhung",
        # "nhung ma", "thuc ra") does not break the discourse
        # unit -- the backward scan skips it to the forward
        # clause. Several consecutive empty clauses skip too.
        for conn in ("Tuy nhiên", "Thế nhưng", "Nhưng mà",
                     "Thực ra"):
            self.assertEqual(
                sel("Chuyển tiếp số %s cho Bình. %s, gọi đi"
                    % (self.X, conn),
                    phones=(self.X,), action="call")["selection"],
                "unknown", conn)
        self.assertEqual(
            sel("Chuyển tiếp số %s cho Bình. Tuy nhiên, thực ra, "
                "gọi đi" % self.X,
                phones=(self.X,), action="call")["selection"],
            "unknown")
        # A CONTENT clause in between still breaks the unit:
        # the backward scan stops at the message clause and
        # never reaches the forward -- pinned at the function
        # level. (Batch-6 case 3e, ".... roi nhan cho Lan,
        # goi di", is NOT such a case: "roi" does not split
        # clauses, so its forward still sits in the
        # immediately preceding clause under the round-6 S4
        # rule; it stays covered by r4b6_probes at decide
        # level, where it fires via the foreign-action
        # fallback.)
        from lifemate.lifemate_callback_negation import (
            _clause_bounds, _forwarded_target_to_other, _nfc,
            _strip_quoted, _tokenize)
        text = ("Chuyển tiếp số %s cho Bình. Nhắn cho Lan đi. "
                "Gọi đi" % self.X)
        raws, folds, cids = _tokenize(_strip_quoted(_nfc(text)))
        bounds = _clause_bounds(cids)
        self.assertFalse(_forwarded_target_to_other(
            raws, folds, cids, bounds, folds.index("goi"),
            (), (self.X,)))

    def test_forward_elided_object_resolved(self):
        # Round-7 fix S2: a forward verb with an elided object
        # forwards the most recent target number mentioned
        # earlier in the same text ("tim / lay / kiem tra so X
        # roi chuyen tiep cho Binh"), whether the lookup sits
        # in the same clause, its own clause, or before the
        # verb in a topicalised clause.
        for lead in ("Tìm", "Lấy", "Kiểm tra"):
            self.assertEqual(
                sel("%s số %s rồi chuyển tiếp cho Bình, gọi đi"
                    % (lead, self.X),
                    phones=(self.X,), action="call")["selection"],
                "unknown", lead)
        self.assertEqual(
            sel("Tìm số %s, chuyển tiếp cho Bình, gọi đi"
                % self.X,
                phones=(self.X,), action="call")["selection"],
            "unknown")
        self.assertEqual(
            sel("Tìm số %s rồi chuyển tiếp cho Bình gọi đi"
                % self.X,
                phones=(self.X,), action="call")["selection"],
            "unknown")
        self.assertEqual(
            sel("Số %s chuyển tiếp cho Bình, gọi đi" % self.X,
                phones=(self.X,), action="call")["selection"],
            "unknown")
        # Constraint: forwarding ANOTHER number never
        # suppresses a bare call for this proposal -- the
        # resolution is from TEXT, never from the proposal.
        self.assertEqual(
            sel("Tìm số %s rồi chuyển tiếp cho Bình, gọi đi"
                % self.Y,
                phones=(self.X,), action="call")["selection"],
            "positive")
        # Explicit call after a forward+lookup still wins.
        self.assertEqual(
            sel("Tìm số %s rồi chuyển tiếp cho Bình, gọi số %s đi"
                % (self.X, self.X),
                phones=(self.X,), action="call")["selection"],
            "positive")

    def test_suppressed_bare_verb_is_not_positive_anywhere(self):
        # Round-7 fix S1+S2, downstream coherence: a
        # forward-suppressed bare verb is marked blocked, so it
        # cannot rescue its own lookup via the lookup
        # exception ("tim so X roi chuyen tiep cho Binh goi
        # di": the bare verb is in the SAME clause as the
        # lookup, so without the marking it would count as
        # the "later positive verb" and rescue the lookup).
        self.assertEqual(
            sel("Tìm số %s rồi chuyển tiếp cho Bình gọi đi"
                % self.X,
                phones=(self.X,), action="call")["selection"],
            "unknown")
        # And it cannot feed the positive-verb fallback either
        # ("lay so X roi chuyen tiep cho Binh, goi di": "lay"
        # is not an inventoried other verb, so no foreign
        # fallback vetoes -- only the blocked marking stops
        # the positive fallback).
        self.assertEqual(
            sel("Lấy số %s rồi chuyển tiếp cho Bình, gọi đi"
                % self.X,
                phones=(self.X,), action="call")["selection"],
            "unknown")

    def test_possessive_break_whole_text(self):
        # Round-7 fix M1: the sender-possessive break applies
        # across clauses, in both orders. The possessive must
        # still be OF THE TARGET phone: a possessive of another
        # number leaves the name event standing.
        res = sel("Nhắn cho Vy đi, số %s của tôi là số mới"
                  % self.X,
                  names=("Vy",), phones=(self.X,),
                  action="message")
        self.assertEqual(res["selection"], "unknown")
        res = sel("Số %s của tôi là số mới, nhắn cho Vy đi"
                  % self.X,
                  names=("Vy",), phones=(self.X,),
                  action="message")
        self.assertEqual(res["selection"], "unknown")
        res = sel("Nhắn cho Vy số %s đi, số %s của tôi là số mới"
                  % (self.Y, self.X),
                  names=("Vy",), phones=(self.Y,),
                  action="message")
        self.assertEqual(res["selection"], "positive")

    def test_turn_fully_delegated(self):
        # Round-7 fix S3 helper: same scope as the
        # current-text delegation rule. Generic "nho em" is
        # NOT delegation; a text with no queried-action verb
        # is NOT fully delegated (vacuous exclusion would
        # wrongly drop turns that merely mention a number).
        from lifemate.lifemate_callback_negation import (
            turn_fully_delegated)
        self.assertTrue(turn_fully_delegated(
            "Nhờ Vy gọi số %s giúp" % self.X, "call"))
        self.assertTrue(turn_fully_delegated(
            "Bảo Vy gọi số %s giúp tôi" % self.X, "call"))
        self.assertFalse(turn_fully_delegated(
            "Nhờ em gọi số %s giúp" % self.X, "call"))
        self.assertFalse(turn_fully_delegated(
            "Nhờ Vy gọi số %s giúp" % self.X, "message"))
        self.assertFalse(turn_fully_delegated(
            "Số %s là số mới" % self.X, "call"))
        # Per-action precision: a mixed turn's CALL verb is
        # delegated (so it is fully delegated for call
        # proposals) while its MESSAGE verb is the user's own
        # (so it still binds for message proposals).
        self.assertTrue(turn_fully_delegated(
            "Nhờ Vy gọi số %s giúp, nhắn số %s cho Vy"
            % (self.X, self.X), "call"))
        self.assertFalse(turn_fully_delegated(
            "Nhờ Vy gọi số %s giúp, nhắn số %s cho Vy"
            % (self.X, self.X), "message"))


class TestRound8Batch7Selection(unittest.TestCase):
    """Round-8 batch-7 SERIOUS + MINOR fixes at the
    selection / binding-action level. Synthetic only."""

    X = "0902345678"
    Y = "0911111111"

    def test_binding_action_class_suppressed_bare_verb(self):
        # S1: a forward+bare turn is "other", not "call":
        # the suppressed bare verb must not make the turn a
        # call instruction when it later becomes history.
        turn = "Chuyển tiếp số %s cho Bình, gọi đi" % self.X
        self.assertEqual(binding_action_class(turn, (), [self.X]),
                         "other")
        # Layer-C shape: the bound number is a genuine
        # message target in one clause AND a forward object
        # + bare verb in another -> "message", so a call
        # proposal mismatch-vetoes while sms passes.
        turn = ("Nhắn cho Bình số %s đi, chuyển tiếp số %s "
                "cho Lan, gọi đi" % (self.Y, self.Y))
        self.assertEqual(binding_action_class(turn, (), [self.Y]),
                         "message")
        # Explicit-object bare verb is never suppressed.
        turn = ("Chuyển tiếp số %s cho Bình, gọi số %s đi"
                % (self.X, self.X))
        self.assertEqual(binding_action_class(turn, (), [self.X]),
                         "call")
        # Pure forward stays "other"; pure message stays
        # "message" (the F1 mismatch controls).
        self.assertEqual(binding_action_class(
            "Chuyển tiếp số %s cho Bình" % self.X, (),
            [self.X]), "other")
        self.assertEqual(binding_action_class(
            "Nhắn số %s giúp tôi" % self.X, (), [self.X]),
            "message")

    def test_binding_action_class_delegation_excluded(self):
        # M1, same unified concept: a delegated verb is
        # another actor's action, so a mixed turn keeps only
        # its own (message) action.
        turn = ("Nhờ Vy gọi số %s giúp, nhắn cho Bình số %s "
                "đi" % (self.X, self.Y))
        self.assertEqual(binding_action_class(turn, (), [self.Y]),
                         "message")
        # A purely delegated turn has no own action at all.
        self.assertEqual(binding_action_class(
            "Nhờ Vy gọi số %s giúp" % self.X, (), [self.X]),
            "unknown")

    def test_binding_action_class_narrowed_both(self):
        # "both" means ONLY call AND message. A single
        # callback action plus other verbs returns that
        # action -- otherwise the adapter's "both passes"
        # rule would let a message+forward turn pass for a
        # call proposal, which the adapter's own comment
        # ("both includes the proposal action") does not
        # justify.
        self.assertEqual(binding_action_class(
            "Nhắn số %s đi, lưu số %s" % (self.X, self.X),
            (), [self.X]), "message")
        self.assertEqual(binding_action_class(
            "Gọi số %s đi, lưu số %s" % (self.X, self.X),
            (), [self.X]), "call")
        self.assertEqual(binding_action_class(
            "Gọi và nhắn số %s đi" % self.X, (), [self.X]),
            "both")

    def test_phone_numbers_for_action_partition(self):
        # M1: a mention takes its nearest PRECEDING callback
        # verb; a delegated preceding verb excludes the
        # mention instead of falling through to a later verb.
        self.assertEqual(phone_numbers_for_action(
            "Nhờ Vy gọi số %s giúp, nhắn cho Bình số %s đi"
            % (self.X, self.Y)), {"message": {self.Y}})
        # "và"-chain shares one object across both verbs, so
        # a shared-object multi-number turn degrades to
        # multiple (safe) instead of binding the wrong
        # number for the shared verb's other action.
        self.assertEqual(phone_numbers_for_action(
            "Gọi và nhắn số %s đi, gọi số %s đi"
            % (self.X, self.Y)),
            {"call": {self.X, self.Y}, "message": {self.X}})
        # Same verb, two numbers: genuinely ambiguous.
        self.assertEqual(phone_numbers_for_action(
            "Nhắn số %s và số %s" % (self.X, self.Y)),
            {"message": {self.X, self.Y}})
        # Leading number: no preceding verb, the following
        # governing verb applies.
        self.assertEqual(phone_numbers_for_action(
            "Số %s, gọi đi" % self.X), {"call": {self.X}})

    def test_forward_fragment_scan(self):
        # M2: a bare number fragment is content-less for the
        # backward scan, so suppression applies and the bare
        # verb is NOT positive; a fragment WITH an assertion
        # stays content, so the bare verb stays positive.
        # (The decide-level outcome for the assertion variant
        # is fired via demotion + no selection -- see the
        # adapter tests -- but the scan property itself is
        # pinned here: positive vs veto.)
        r = sel("Chuyển tiếp số %s cho Bình. Số 12, gọi đi"
                % self.X, phones=[self.X])
        self.assertNotEqual(r["selection"], "positive")
        r = sel("Chuyển tiếp số %s cho Bình. 0912, gọi đi"
                % self.X, phones=[self.X])
        self.assertNotEqual(r["selection"], "positive")
        r = sel("Chuyển tiếp số %s cho Bình. "
                "Số 12 là số mới, gọi đi" % self.X,
                phones=[self.X])
        self.assertEqual(r["selection"], "positive")
        self.assertEqual(r["reason"], "generic_callback_positive")

    def test_content_possessive_whole_text(self):
        # M3: a sender possessive anywhere in the text breaks
        # the content-layer owner exception for every mention
        # of the SAME number -- but not for another number.
        t = ("Nhắn cho Vy số %s đi, số %s của tôi là số mới"
             % (self.X, self.X))
        self.assertTrue(phone_mentions_all_content(
            t, ("Vy",), [self.X]))
        # Without a possessive the owner exception stands.
        self.assertFalse(phone_mentions_all_content(
            "Nhắn cho Vy số %s đi" % self.X, ("Vy",), [self.X]))
        # A possessive of another number leaves the exception
        # standing for this number.
        t = ("Nhắn cho Vy số %s đi, số %s của tôi là số mới"
             % (self.Y, self.X))
        self.assertFalse(phone_mentions_all_content(
            t, ("Vy",), [self.Y]))


class TestRound10Batch10Selection(unittest.TestCase):
    """Round-10 batch-10 fix S1 (verb leak) + M1 (gửi inventory).

    S1 concept: positive selection for a number requires
    per-number verb government -- a verb governs exactly the
    number it governs, never "a verb somewhere + a mention
    somewhere". Three layers, one concept: (1) an object
    span containing another number is specific, never
    general; (2) a verb does not govern past an intervening
    different number unless "và"-chained; (3) the fallback
    no-veto positive survives only when no number
    competition and no bare target exist (see the
    no-veto-contract test below).
    """

    X = "0902345678"
    Y = "0911111111"

    def test_b10_s1_verb_plus_bare_number_not_positive(self):
        # 1c + F1a/F1c/F1d/F5a/F5b: verb governs X, Y bare
        # (after / before / own sentence / assertion frame).
        # All one mechanism (generic_callback_positive leak),
        # all must stop being positive for Y.
        cases = [
            ("Gọi số %s đi, số %s" % (self.X, self.Y), "call"),
            ("Nhắn số %s đi, số %s" % (self.X, self.Y),
             "message"),
            ("Số %s, gọi số %s đi" % (self.Y, self.X), "call"),
            ("Gọi số %s đi, số %s là số mới"
             % (self.X, self.Y), "call"),
            ("Số %s. Gọi số %s đi" % (self.Y, self.X), "call"),
            ("Gọi số %s đi. Số %s" % (self.X, self.Y), "call"),
        ]
        for text, action in cases:
            r = sel(text, phones=[self.Y], action=action)
            self.assertEqual(r["selection"], "unknown", text)
        # Controls: the verb-selected number stays positive.
        r = sel("Gọi số %s đi, số %s" % (self.X, self.Y),
                phones=[self.X], action="call")
        self.assertEqual(r["selection"], "positive")
        r = sel("Số %s. Gọi số %s đi" % (self.Y, self.X),
                phones=[self.X], action="call")
        self.assertEqual(r["selection"], "positive")

    def test_b10_s1_same_clause_government(self):
        # Juxtaposition / "rồi" do not chain: the verb
        # governs X, not Y. "và" shares one object: both
        # governed.
        r = sel("Gọi số %s số %s đi" % (self.X, self.Y),
                phones=[self.Y], action="call")
        self.assertEqual(r["selection"], "unknown")
        r = sel("Gọi số %s rồi số %s" % (self.X, self.Y),
                phones=[self.Y], action="call")
        self.assertEqual(r["selection"], "unknown")
        r = sel("Gọi số %s đi số %s" % (self.X, self.Y),
                phones=[self.Y], action="call")
        self.assertEqual(r["selection"], "unknown")
        r = sel("Gọi số %s và số %s đi" % (self.X, self.Y),
                phones=[self.Y], action="call")
        self.assertEqual(r["selection"], "positive")

    def test_b10_s1_bare_verb_multi_number(self):
        # A bare verb in a multi-number turn selects neither
        # number; in a single-number turn it selects the
        # turn's only number (S3 general rule, narrowed).
        r = sel("Gọi đi, số %s, số %s" % (self.X, self.Y),
                phones=[self.Y], action="call")
        self.assertEqual(r["selection"], "unknown")
        r = sel("Số %s, gọi đi" % self.Y,
                phones=[self.Y], action="call")
        self.assertEqual(r["selection"], "positive")
        r = sel("Gọi đi, số %s" % self.Y,
                phones=[self.Y], action="call")
        self.assertEqual(r["selection"], "positive")

    def test_b10_s1_cross_action_no_leak(self):
        # F1b: a message verb never leaks to a call proposal.
        r = sel("Nhắn số %s đi, số %s" % (self.X, self.Y),
                phones=[self.Y], action="call")
        self.assertEqual(r["selection"], "unknown")
        self.assertEqual(r["reason"], "other_action_verb_only")

    def test_b10_s1_no_veto_contract_preserved(self):
        # PINNED veto-gate contract, narrowed -- not
        # overturned -- by S1: a positive verb for ANOTHER
        # NAME is "no veto", not selection for this target,
        # and the adapter (never this module alone) decides
        # binding. Only NUMBER government and bare-target
        # cases become unknown (see the tests above).
        r = sel("gọi Nguyễn Bình", names=("Nguyễn An",))
        self.assertEqual(r["selection"], "positive")
        self.assertFalse(r["mention_present"])
        r = sel("gọi lại cho An, đừng nhắn cho Vy",
                names=("Vy",), action="call")
        self.assertEqual(r["selection"], "positive")

    def test_b10_m1_gui_inventory_and_money_guard(self):
        # "gửi" is a message verb for person / number /
        # message objects, but never for money / amount
        # objects: a money transfer must not bind as a
        # message instruction.
        self.assertEqual(
            instruction_action("Gửi Vy số %s" % self.X),
            "message")
        self.assertEqual(
            binding_action_class("Gửi Vy số %s" % self.X,
                                 target_phones=[self.X]),
            "message")
        self.assertEqual(
            instruction_action("Gửi tin nhắn cho Vy"), "message")
        for text in ("Gửi tiền tới số %s" % self.X,
                     "Gửi 100000 tới số %s" % self.X,
                     "Gửi một trăm nghìn tới số %s" % self.X):
            self.assertNotEqual(instruction_action(text),
                                "message", text)
            self.assertNotEqual(
                binding_action_class(text,
                                     target_phones=[self.X]),
                "message", text)

    def test_b10_fragment_groups_not_competitors(self):
        # Gold-shape regression (train_0676, synthetic
        # numbers): a spoken number arriving in
        # comma-separated groups IS the target, so its
        # prefix group is not a competing number for (F-a).
        # "không chín không hai, ba bốn, năm sáu bảy tám"
        # = 0902 + 34 + 5678 = 0902345678.
        r = sel("xong gọi luôn số không chín không hai, "
                "ba bốn, năm sáu bảy tám giúp anh",
                phones=[self.X], action="call")
        self.assertEqual(r["selection"], "positive")

    def test_b10_rejected_tail_not_competitor(self):
        # Gold-shape regression (train_1677, synthetic
        # numbers): the OLD tail after "chứ không phải"
        # is the rejected value of a correction frame,
        # not a competing number, so the bare verb "gọi
        # lại" still selects the NEW tail's number.
        # R5 marker note: the NEW tail "68" is itself a
        # proper substring (suffix) of the target, so this
        # bare positive ALSO depends on the 0676 substring
        # exclusion -- the reason is therefore the
        # substring marker, not the plain generic reason.
        # Selection (positive) and decide() outcome
        # (un-fire) are unchanged; only the reason is now
        # more precise.
        r = sel("đọc nhầm số, đuôi là sáu tám chứ không "
                "phải tám sáu, gọi lại giúp tôi",
                phones=["0900000068"], action="call")
        self.assertEqual(r["selection"], "positive")
        self.assertEqual(
            r["reason"],
            "generic_callback_positive_substring_excluded")

    def test_b10_m1_gui_bare_number_ambiguous(self):
        # F2a: bare "gửi" + bare number, no named recipient
        # in the clause, is ambiguous (thing sent vs
        # recipient) and does not select the number. With
        # a named target owner in the clause (2a), it does.
        r = sel("Gửi số %s đi" % self.X, phones=[self.X],
                action="message")
        self.assertEqual(r["selection"], "unknown")
        r = sel("Gửi Vy số %s" % self.X, names=("Vy",),
                phones=[self.X], action="message")
        self.assertEqual(r["selection"], "positive")


class TestR5DigitRunObject(unittest.TestCase):
    """R5 fix for R4 batch-11 S1: a verb whose object span
    contains ANY digit run is specific, never general/bare.

    Scope: object classification only (the governed span,
    never a whole-sentence digit scan). Fragment 2345 is
    never completed into a full number (group joining stays
    a MINOR backlog item). Every case asserts the layer-C
    selection + reason AND the decide() outcome.
    """

    def test_s1_typed_short_run_object_fires(self):
        # THE R4 batch-11 S1 repro: verb governs short run
        # 2345, proposal is the other phone mention Y.
        # Before the fix this un-fired (general + bare verb
        # selected Y); now the verb is specific and the
        # target mention is bare in its own clause (F-b).
        r = sel("Gọi số 2345 đi, số 0911111111",
                phones=(Y,), action="call")
        self.assertEqual(r["selection"], "unknown")
        self.assertEqual(r["reason"],
                         "positive_verb_not_governing_target")
        d = dec("Gọi số 2345 đi, số 0911111111")
        self.assertTrue(d.fired)
        self.assertIn("positive_verb_not_governing_target",
                      dec_reasons(d))

    def test_s1_spoken_short_run_object_fires(self):
        # Spoken variant: "số không chín" (09) is a digit
        # run in the object span, so the verb is specific
        # even though 09 is not a phone mention.
        r = sel("Gọi số không chín đi, số 0911111111",
                phones=(Y,), action="call")
        self.assertEqual(r["selection"], "unknown")
        self.assertEqual(r["reason"],
                         "positive_verb_not_governing_target")
        d = dec("Gọi số không chín đi, số 0911111111")
        self.assertTrue(d.fired)

    def test_full_phone_object_fires(self):
        # Full-phone object (pre-existing behaviour): the
        # verb governs X specifically, never Y.
        r = sel("Gọi số 0902345678 đi, số 0911111111",
                phones=(Y,), action="call")
        self.assertEqual(r["selection"], "unknown")
        d = dec("Gọi số 0902345678 đi, số 0911111111")
        self.assertTrue(d.fired)

    def test_digit_object_without_generic_head_unchanged(self):
        # Control: "Gọi 2345 đi" (no "số" head) was already
        # specific before the fix (2345 is not a generic
        # head); the fix targets the generic-head path only.
        r = sel("Gọi 2345 đi, số 0911111111",
                phones=(Y,), action="call")
        self.assertEqual(r["selection"], "unknown")
        d = dec("Gọi 2345 đi, số 0911111111")
        self.assertTrue(d.fired)

    def test_truly_bare_verb_still_unfires(self):
        # F4a control, MUST NOT change: the verb "gọi" is
        # clause-final with an empty object span (truly
        # bare), so bare + exactly 1 phone mention selects Y.
        # The reason stays the PLAIN generic reason: no
        # substring fragment is involved, so the 0676
        # marker must not leak here.
        r = sel("Số 0911111111, số 2345, gọi đi",
                phones=(Y,), action="call")
        self.assertEqual(r["selection"], "positive")
        self.assertEqual(r["reason"], "generic_callback_positive")
        d = dec("Số 0911111111, số 2345, gọi đi")
        self.assertFalse(d.fired)

    def test_bare_verb_exactly_one_phone_mention(self):
        # Bare verb + exactly 1 phone mention selects it.
        r = sel("Gọi đi, số 0911111111",
                phones=(Y,), action="call")
        self.assertEqual(r["selection"], "positive")
        d = dec("Gọi đi, số 0911111111")
        self.assertFalse(d.fired)

    def test_bare_verb_two_phone_mentions_fires(self):
        # Bare verb + 2 phone mentions selects neither
        # (bare_verb_ambiguous via a true competitor).
        r = sel("Gọi đi, số 0902345678, số 0911111111",
                phones=(Y,), action="call")
        self.assertEqual(r["selection"], "unknown")
        d = dec("Gọi đi, số 0902345678, số 0911111111")
        self.assertTrue(d.fired)

    def test_target_before_verb_other_clause_fires(self):
        # Target mentioned in an earlier clause, verb in a
        # later clause governs a short run: no event, no
        # general event (specific object) -> fired.
        r = sel("Số 0911111111, gọi số 2345 đi",
                phones=(Y,), action="call")
        self.assertEqual(r["selection"], "unknown")
        d = dec("Số 0911111111, gọi số 2345 đi")
        self.assertTrue(d.fired)

    def test_quantity_distractor_fires(self):
        # "3 lần" after the short-run object does not rescue
        # the verb into a bare positive for Y.
        r = sel("Gọi số 2345 đi 3 lần, số 0911111111",
                phones=(Y,), action="call")
        self.assertEqual(r["selection"], "unknown")
        d = dec("Gọi số 2345 đi 3 lần, số 0911111111")
        self.assertTrue(d.fired)

    def test_time_distractor_does_not_rescue(self):
        # A time phrase in another clause does not change
        # the governed short-run object.
        r = sel("Gọi số 2345 đi lúc 3 giờ, số 0911111111",
                phones=(Y,), action="call")
        self.assertEqual(r["selection"], "unknown")
        d = dec("Gọi số 2345 đi lúc 3 giờ, số 0911111111")
        self.assertTrue(d.fired)

    def test_money_distractor_control_unfires(self):
        # Money text elsewhere does not break a genuine
        # bare-verb + 1 phone mention selection ("100k" is
        # not a digit run: the token is not all digits).
        r = sel("Gọi đi, số 0911111111, hết 100k",
                phones=(Y,), action="call")
        self.assertEqual(r["selection"], "positive")
        d = dec("Gọi đi, số 0911111111, hết 100k")
        self.assertFalse(d.fired)

    def test_va_chain_still_governs_both(self):
        # "và"-chain control (v10 government rule): the verb
        # governs both numbers, so Y is positively selected.
        r = sel("Gọi số 0902345678 và số 0911111111",
                phones=(Y,), action="call")
        self.assertEqual(r["selection"], "positive")
        d = dec("Gọi số 0902345678 và số 0911111111")
        self.assertFalse(d.fired)

    def test_roi_never_chains(self):
        # "rồi" control (v10 government rule): the verb
        # governs X only; Y past X is not governed, and the
        # number-governed fallback (F-a) fires.
        r = sel("Gọi số 0902345678 rồi số 0911111111",
                phones=(Y,), action="call")
        self.assertEqual(r["selection"], "unknown")
        self.assertEqual(r["reason"],
                         "positive_verb_not_governing_target")
        d = dec("Gọi số 0902345678 rồi số 0911111111")
        self.assertTrue(d.fired)

    def test_cross_action_message_verb_call_proposal(self):
        # Cross-action separation: a message verb never
        # selects a call proposal, short run or not.
        r = sel("Nhắn số 2345 đi, số 0911111111",
                phones=(Y,), action="call")
        self.assertEqual(r["selection"], "unknown")
        self.assertEqual(r["reason"], "other_action_verb_only")
        d = dec("Nhắn số 2345 đi, số 0911111111")
        self.assertTrue(d.fired)

    def test_lone_fragment_never_binds(self):
        # A phone fragment standing alone authorises
        # nothing: layer C may report "positive" (no veto
        # for another target) but the adapter has no
        # binding (no mention, no roster, no log), so
        # decide() must fire. This test pins the split:
        # negation-positive is NOT an un-fire by itself.
        r = sel("Gọi số 2345 đi", phones=(X,), action="call")
        self.assertEqual(r["selection"], "positive")
        self.assertEqual(r["reason"],
                         "positive_action_no_target_veto")
        d = dec("Gọi số 2345 đi", number=X)
        self.assertTrue(d.fired)
        r2 = sel("Số 2345 đi", phones=(X,), action="call")
        self.assertEqual(r2["selection"], "unknown")
        self.assertEqual(r2["reason"], "no_callback_verb")
        d2 = dec("Số 2345 đi", number=X)
        self.assertTrue(d2.fired)


class TestR5Fallback0676PathProof(unittest.TestCase):
    """Path proof for the 0676 substring fallback.

    Outcome-correct and mechanism-tested are separate
    claims. (1) Direct unit tests of _has_other_number
    prove the substring branch executes. (2) An end-to-end
    decide() case proves the bare-verb positive depends on
    it: the trail reason is the distinct marker
    "generic_callback_positive_substring_excluded", which
    is produced ONLY when a proper-substring fragment
    exclusion is decisive (fragments present, no true
    competitor, target mentioned). A general-rule-preempted
    case (F4a) is NEVER cited as fallback evidence.
    """

    def test_helper_fragment_groups_excluded(self):
        # Prefix + suffix fragment groups of the target are
        # excluded (proper substrings), so no competitor.
        has_other, excluded = _has_other_number(
            [(0, 1, "0911"), (2, 3, "1111")], [Y], set())
        self.assertFalse(has_other)
        self.assertEqual(excluded, [(0, 1, "0911"),
                                    (2, 3, "1111")])

    def test_helper_true_competitor(self):
        # A phone-like run that is no substring of the
        # target is a competitor; nothing is excluded.
        has_other, excluded = _has_other_number(
            [(0, 1, "1112")], [Y], set())
        self.assertTrue(has_other)
        self.assertEqual(excluded, [])

    def test_helper_exact_match_not_listed(self):
        # An exact target match is excluded from has_other
        # but is NOT fallback evidence (it is the target).
        has_other, excluded = _has_other_number(
            [(0, 1, Y)], [Y], set())
        self.assertFalse(has_other)
        self.assertEqual(excluded, [])

    def test_helper_rejected_run_ignored(self):
        # A rejected correction value never counts, even
        # when it is not a substring of the target.
        has_other, excluded = _has_other_number(
            [(0, 1, "1112")], [Y], {(0, 1)})
        self.assertFalse(has_other)
        self.assertEqual(excluded, [])

    def test_helper_no_targets(self):
        # With no target phones there is nothing to
        # compete with (pinned no-target generic case).
        has_other, excluded = _has_other_number(
            [(0, 1, "1112")], [], set())
        self.assertFalse(has_other)
        self.assertEqual(excluded, [])

    def test_helper_mixed_runs(self):
        # Exact + fragment + competitor: only the fragment
        # is listed, and the competitor still counts.
        has_other, excluded = _has_other_number(
            [(0, 1, Y), (2, 3, "1111"), (4, 5, "1112")],
            [Y], set())
        self.assertTrue(has_other)
        self.assertEqual(excluded, [(2, 3, "1111")])

    def test_end_to_end_marker_only_on_decisive_shape(self):
        # Bare verb + typed target mention + a spoken
        # suffix group (1111, a proper substring of Y) in
        # a "số" clause: the bare positive stands ONLY
        # because the fragment is excluded. The decide()
        # trail carries the distinct marker reason.
        text = "Gọi đi, số 0911111111, số một một một một"
        r = sel(text, phones=(Y,), action="call")
        self.assertEqual(r["selection"], "positive")
        self.assertEqual(
            r["reason"],
            "generic_callback_positive_substring_excluded")
        d = dec(text)
        self.assertFalse(d.fired)
        self.assertIn(
            "generic_callback_positive_substring_excluded",
            dec_reasons(d))

    def test_end_to_end_true_competitor_no_marker(self):
        # Same shape but the spoken group (1112) is NOT a
        # substring of Y: a true competitor, so the bare
        # verb is ambiguous and the decision fires with no
        # marker anywhere in the trail.
        text = "Gọi đi, số 0911111111, số một một một hai"
        r = sel(text, phones=(Y,), action="call")
        self.assertEqual(r["selection"], "unknown")
        self.assertEqual(r["reason"],
                         "positive_verb_not_governing_target")
        d = dec(text)
        self.assertTrue(d.fired)
        self.assertNotIn(
            "generic_callback_positive_substring_excluded",
            dec_reasons(d))


class TestSelectionRoundB(unittest.TestCase):
    """Selection round, thread-B level: emphatic negation,
    echo-questions, toneless 'nhi', and bare-'chuyen' forward.

    Scope: these prove analyze_action_selection's verdict for
    the current text alone. They do NOT prove the adapter's
    passed-path wiring (see TestSelectionRoundAdapter in
    test_gates_adapter.py).
    """

    def test_emphatic_negation_co_ma(self):
        sel = analyze_action_selection(
            "Đừng có mà gọi số 0903111444 đấy",
            target_phones=["0903111444"], action="call")
        self.assertEqual(sel["selection"], "negated")

    def test_emphatic_negation_bare_ma(self):
        sel = analyze_action_selection(
            "Đừng mà gọi số 0903111444",
            target_phones=["0903111444"], action="call")
        self.assertEqual(sel["selection"], "negated")

    def test_ma_without_dung_stays_positive(self):
        # "mà" alone is not a negation marker: the particle
        # bridge only extends a real "đừng" backward search.
        sel = analyze_action_selection(
            "Nhưng mà gọi số 0903111444",
            target_phones=["0903111444"], action="call")
        self.assertEqual(sel["selection"], "positive")

    def test_ma_nho_stays_positive(self):
        sel = analyze_action_selection(
            "Mà nhớ gọi số 0903111444",
            target_phones=["0903111444"], action="call")
        self.assertEqual(sel["selection"], "positive")

    def test_echo_question_nhi_blocked(self):
        # A wh-echo with the "nhỉ" particle is a question
        # clause, not a request: the verb is blocked.
        sel = analyze_action_selection(
            "Lúc nãy em bảo gọi số 0903111444 nhỉ?",
            target_phones=["0903111444"], action="call")
        self.assertEqual(sel["selection"], "unknown")
        self.assertEqual(sel["reason"], "blocked_verb_only")

    def test_verb_question_phai_khong_blocked(self):
        sel = analyze_action_selection(
            "Gọi cho Bình phải không?",
            target_names=["Bình"], action="call")
        self.assertEqual(sel["selection"], "unknown")
        self.assertEqual(sel["reason"], "blocked_verb_only")

    def test_toneless_nhi_name_stays_request(self):
        # Toneless "Nhi" with no digit in the clause is a
        # person's name (the call target), not the particle.
        sel = analyze_action_selection(
            "Gọi cho Nhi", target_names=["Nhi"], action="call")
        self.assertEqual(sel["selection"], "positive")

    def test_toneless_nhi_with_digit_is_question(self):
        sel = analyze_action_selection(
            "Gọi số 0903111444 nhi",
            target_phones=["0903111444"], action="call")
        self.assertEqual(sel["selection"], "unknown")
        self.assertEqual(sel["reason"], "blocked_verb_only")

    def test_bare_chuyen_forward_vetoes(self):
        # Bare "chuyển" + recipient + following bare "gọi"
        # is a forward: the number is content for Lan, not a
        # call selection (veto reason is the content rule,
        # which fires before the blocked-verb fallback).
        sel = analyze_action_selection(
            "Chuyển số 0903111222 cho Lan, gọi đi",
            target_phones=["0903111222"], action="call")
        self.assertEqual(sel["selection"], "unknown")
        self.assertEqual(
            sel["reason"], "number_as_content_for_other_recipient")


if __name__ == "__main__":
    unittest.main(verbosity=2)
