"""Synthetic / adversarial tests for lifemate_phone_callback_evidence.

ALL fixtures are invented. No sample ID, no gold value, and no
dev-set text appears in this file: every number, name, and message
below was made up for the test. Each test names the contract it
checks in its docstring; expected values are derived from the
zaic_tools implementation or the round brief, never adjusted to
make the suite green.

Run: python3 tests/test_phone_callback_evidence.py
(also runnable from the lifemate/ directory; the import below
resolves the module from either location.)
"""

import os
import sys
import unittest

# Package-mode import: the repo root (parent of tests/) is the only
# path entry added -- never the lifemate/ directory itself, so this
# test exercises the same import contract as the real entrypoint.
sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))

import lifemate.lifemate_phone_callback_evidence as ev


def _succeeded(tool, result, position=0, args=None):
    return {"tool": tool, "args": args or {}, "result": result,
            "outcome": "succeeded", "position": position}


def _mentions(text):
    return {m["normalized"]: m for m in ev.parse_phone_mentions(text)}


class TestNormPhone(unittest.TestCase):
    def test_digits_only_and_84_fold(self):
        # Contract: gates._norm_phone / base.contact_ref rule.
        self.assertEqual(ev.norm_phone("0912345678"), "0912345678")
        self.assertEqual(ev.norm_phone("+84912345678"), "0912345678")
        self.assertEqual(ev.norm_phone("84 912 345 678"), "0912345678")
        self.assertEqual(ev.norm_phone("090-123-4567"), "0901234567")

    def test_no_digit_editing(self):
        # Normalisation never adds, drops, or changes a digit to
        # force a match: a near-miss stays a near-miss.
        self.assertNotEqual(ev.norm_phone("0912345679"),
                            ev.norm_phone("0912345678"))


class TestSpokenDigits(unittest.TestCase):
    def test_spoken_grouped_by_commas(self):
        ms = _mentions(
            "Gọi giúp tôi tổng đài hỗ trợ, số một chín không hai, "
            "ba bốn năm sáu ấy.")
        self.assertEqual(ms["19023456"]["role"], "requested_target")
        self.assertEqual(ms["19023456"]["kind"], "spoken")

    def test_spoken_space_separated(self):
        ms = _mentions(
            "Gọi cho Bình giúp chị, số không chín tám sáu, hai ba "
            "bốn, năm sáu bảy tám nhé.")
        self.assertIn("09862345678", ms)

    def test_spoken_with_leading_zeros_after_cue(self):
        # "không" right after the "số" cue is digit 0, not negation.
        ms = _mentions("Gọi số không chín một hai, ba bốn năm nhé.")
        self.assertIn("0912345", ms)  # 7 digits: a short hotline form
        self.assertEqual(ms["0912345"]["role"], "requested_target")

    def test_bare_khong_is_not_a_digit(self):
        # "Không, để tôi xem lại đã" -- no digit run, no guess.
        self.assertEqual(ev.parse_phone_mentions(
            "Không, để tôi xem lại số đã."), [])

    def test_khong_phai_is_negation_not_zero(self):
        # "không phải" must not start a digit run (regression: the
        # old run loop could spin on "không phải").
        ms = _mentions("Đuôi là sáu tám chứ không phải tám sáu.")
        self.assertEqual(ms, {})

    def test_digits_and_spoken_mix(self):
        ms = _mentions("Gọi số 0912345678 giúp tôi.")
        self.assertEqual(ms["0912345678"]["kind"], "digits")


class TestRolesAndCorrections(unittest.TestCase):
    def test_negated_number(self):
        ms = _mentions(
            "Không phải số 0912345678, mà là số 0903123456 giúp tôi.")
        self.assertEqual(ms["0912345678"]["role"], "negated")
        self.assertEqual(ms["0903123456"]["role"], "requested_target")

    def test_corrected_away_old_number(self):
        # The old number retired by "số cũ ... không dùng nữa".
        ms = _mentions(
            "Số cũ của anh là 0912345678, số cũ anh không dùng nữa "
            "đâu, gọi số mới 0903123456 giúp tôi.")
        self.assertEqual(ms["0912345678"]["role"], "corrected_away")
        self.assertEqual(ms["0903123456"]["role"], "requested_target")

    def test_new_number_not_retired_by_old_number_clause(self):
        # "số mới của anh là X, số cũ anh không dùng nữa" states X
        # as the NEW number; the retirement clause is about the
        # (unstated) old number, not X.
        ms = _mentions(
            "Số mới của anh là 0912345678, số cũ anh không dùng "
            "nữa đâu.")
        self.assertNotEqual(ms["0912345678"]["role"], "corrected_away")

    def test_tail_correction_parse_and_apply(self):
        corr = ev.parse_tail_correction(
            "Đuôi là sáu tám chứ không phải tám sáu, gọi lại đi.")
        self.assertEqual(corr["old_tail"], "86")
        self.assertEqual(corr["new_tail"], "68")
        self.assertEqual(
            ev.apply_tail_correction("0912345686", corr), "0912345668")
        # Wrong tail: no correction, no invented digits.
        self.assertIsNone(
            ev.apply_tail_correction("0912345612", corr))
        self.assertIsNone(ev.parse_tail_correction("Gọi số này đi."))

    def test_correction_marker_khong_is_not_negation(self):
        # S13: the "không" in "à không" must not negate the verb
        # after it: the correction turn's number is a fresh
        # requested target, not a negated one.
        ms = _mentions("À không, gọi số 0912345678 đi")
        self.assertEqual(ms["0912345678"]["role"], "requested_target")
        ms = _mentions("Ý là, gọi số 0912345678 đi")
        self.assertEqual(ms["0912345678"]["role"], "requested_target")
        # A real negation still negates.
        ms = _mentions("Không phải số 0912345678")
        self.assertEqual(ms["0912345678"]["role"], "negated")

    def test_copula_information_is_background(self):
        # M-b: "Số X là ..." with no action verb anywhere in the
        # window states a fact; it must not become a phone turn
        # that hijacks a prior-instruction binding.
        ms = _mentions("Số 0912345678 là số tổng đài")
        self.assertEqual(ms["0912345678"]["role"], "background")
        ms = _mentions("Số 0912345678 là số của em")
        self.assertEqual(ms["0912345678"]["role"], "background")
        # An action verb in the window keeps the request reading.
        ms = _mentions("Gọi số 0912345678 là số chính giúp tôi")
        self.assertEqual(ms["0912345678"]["role"], "requested_target")


class TestContextClassification(unittest.TestCase):
    def _cls(self, text):
        return [(r["digits"],
                 ev.classify_phone_context(text, r)["classification"])
                for r in ev.find_digit_runs(text)]

    def test_money_not_phone(self):
        out = dict(self._cls("Chuyển 200000 đồng cho tôi."))
        self.assertEqual(out["200000"], "money")

    def test_money_and_phone_in_one_sentence(self):
        # Adjacent units win: the amount stays money, the phone
        # stays phone, even in one sentence.
        out = dict(self._cls(
            "Gọi số 0912345678, chuyển 200000 đồng sau đó."))
        self.assertEqual(out["0912345678"], "phone")
        self.assertEqual(out["200000"], "money")

    def test_time_and_date_not_phone(self):
        out = dict(self._cls("Lúc 14:05 ngày 08/11 gọi lại nhé."))
        self.assertEqual(out["14"], "time")
        self.assertEqual(out["08"], "date")

    def test_spoken_time_not_phone(self):
        out = dict(self._cls("Lúc ba giờ hai mươi gọi lại nhé."))
        self.assertEqual(out["3"], "time")

    def test_order_code_not_phone(self):
        out = dict(self._cls("Mã đơn 12345678 đang giao."))
        self.assertEqual(out["12345678"], "order_code")

    def test_short_tail_not_phone(self):
        out = dict(self._cls("Vé đuôi 95 có trúng không?"))
        self.assertEqual(out["95"], "other_number")

    def test_bare_long_digits_ambiguous(self):
        # Shaped like a phone number but nothing selects it as one.
        out = dict(self._cls("0912345678"))
        self.assertEqual(out["0912345678"], "ambiguous")


class TestHistoryResultParsing(unittest.TestCase):
    def test_dict_and_list_passthrough(self):
        self.assertEqual(
            ev.parse_history_result({"ok": True})["status"], "ok")
        self.assertEqual(
            ev.parse_history_result([1, 2])["status"], "ok")

    def test_json_string(self):
        self.assertEqual(
            ev.parse_history_result('{"ok": true, "calls": []}'),
            {"status": "ok", "value": {"ok": True, "calls": []},
             "reason": "json"})

    def test_python_repr_string(self):
        # History results arrive as repr strings; literal_eval (not
        # eval) must handle single quotes and True/None.
        parsed = ev.parse_history_result(
            "{'ok': True, 'messages': [{'id': 'm1', "
            "'contact_id': None}]}")
        self.assertEqual(parsed["status"], "ok")
        self.assertIsNone(parsed["value"]["messages"][0]["contact_id"])

    def test_malformed_never_crashes(self):
        for raw in ("not a result at all {{{", "", 12345, None):
            got = ev.parse_history_result(raw)
            self.assertEqual(got["status"], "malformed")
            self.assertIsNone(got["value"])

    def test_no_eval(self):
        # A hostile string must not execute: literal_eval rejects
        # call expressions, so this stays malformed.
        got = ev.parse_history_result("__import__('os').system('x')")
        self.assertEqual(got["status"], "malformed")


class TestLogRecordExtraction(unittest.TestCase):
    def test_nested_contact_unpacked(self):
        # phone.recent_calls history shape: calls carry a nested
        # contact dict, not flat contact_id/phone_number fields.
        recs = ev.extract_log_records(
            {"ok": True, "calls": [
                {"id": "call_1",
                 "contact": {"id": "c_9", "name": "Vy",
                             "phone": "0922222222"},
                 "direction": "incoming", "status": "missed"}]},
            "phone.recent_calls", 3)
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["contact_id"], "c_9")
        self.assertEqual(recs[0]["phone_number"], "0922222222")
        self.assertEqual(recs[0]["direction"], "incoming")

    def test_malformed_result_yields_no_records(self):
        self.assertEqual(
            ev.extract_log_records("garbage {{{", "sms.read_recent", 0),
            [])


class TestBinding(unittest.TestCase):
    def _logs(self):
        return [
            {"tool": "phone.recent_calls", "position": 0,
             "record_id": "call_1", "contact_id": "c_100",
             "phone_number": "0911111111", "name": "Sep",
             "direction": "outgoing", "status": "completed",
             "content": None, "time": "2026-10-01T10:00:00"},
            {"tool": "phone.recent_calls", "position": 0,
             "record_id": "call_2", "contact_id": "c_200",
             "phone_number": "0922222222", "name": "Vy",
             "direction": "incoming", "status": "missed",
             "content": None, "time": "2026-10-01T15:00:00"},
        ]

    def test_callback_named_selects_missed_not_outgoing(self):
        rec, _ = ev.bind_history_reference(
            "Xong gọi lại cho Vy dùm anh luôn nha.", self._logs())
        self.assertEqual(rec["contact_id"], "c_200")

    def test_callback_unnamed_single_missed(self):
        logs = [r for r in self._logs()
                if r["direction"] == "incoming"]
        rec, _ = ev.bind_history_reference(
            "Gọi lại người vừa gọi giúp tôi.", logs)
        self.assertEqual(rec["contact_id"], "c_200")

    def test_callback_two_missed_no_name_is_ambiguous(self):
        logs = self._logs() + [
            {"tool": "phone.recent_calls", "position": 1,
             "record_id": "call_3", "contact_id": "c_300",
             "phone_number": "0933333333", "name": "Lan",
             "direction": "incoming", "status": "missed",
             "content": None, "time": "2026-10-01T16:00:00"}]
        rec, reason = ev.bind_history_reference(
            "Gọi lại người vừa gọi giúp tôi.", logs)
        self.assertIsNone(rec)

    def test_callback_topic_disambiguates(self):
        logs = [
            {"tool": "sms.read_recent", "position": 0,
             "record_id": "m1", "contact_id": "c_1",
             "phone_number": "0911111111", "name": None,
             "direction": "incoming", "status": None,
             "content": "Vé đài Đà Nẵng đuôi 95, dò giùm coi trúng không.",
             "time": "2026-10-01T09:00:00"},
            {"tool": "sms.read_recent", "position": 0,
             "record_id": "m2", "contact_id": None,
             "phone_number": "0944444444", "name": None,
             "direction": "incoming", "status": None,
             "content": "Sách mượn của bạn sẽ hết hạn.",
             "time": "2026-10-01T10:00:00"},
        ]
        rec, _ = ev.bind_history_reference(
            "Coi giùm kết quả Đà Nẵng, có trúng thì nhắn lại giúp tôi.",
            logs)
        self.assertEqual(rec["record_id"], "m1")

    def test_anaphoric_latest_time_selects_newest(self):
        chats = [
            {"tool": "chat_ott.read_chat", "position": 0,
             "record_id": None, "contact_id": None,
             "phone_number": "", "name": "Nhóm",
             "direction": None, "status": None,
             "content": "Đường dây cũ là 0901111111 nhé.",
             "time": "2026-09-01T08:00:00"},
            {"tool": "chat_ott.read_chat", "position": 0,
             "record_id": None, "contact_id": None,
             "phone_number": "", "name": "Nhóm",
             "direction": None, "status": None,
             "content": "Đường dây sự cố đổi sang 0902222222, số cũ "
                        "không dùng nữa.",
             "time": "2026-10-01T08:00:00"},
        ]
        rec, _ = ev.bind_history_reference(
            "Lấy số mới nhất ấy gọi thử số đó giúp tôi.", chats)
        self.assertEqual(rec["phone_number"], "0902222222")

    def test_anaphoric_multiple_numbers_no_cue_is_ambiguous(self):
        chats = [
            {"tool": "chat_ott.read_chat", "position": 0,
             "record_id": None, "contact_id": None,
             "phone_number": "", "name": "Nhóm",
             "direction": None, "status": None,
             "content": "Số A là 0901111111, số B là 0902222222.",
             "time": "2026-10-01T08:00:00"},
        ]
        rec, _ = ev.bind_history_reference(
            "Gọi số đó giúp tôi.", chats)
        self.assertIsNone(rec)

    def test_prior_instruction_binding(self):
        turns = [{"kind": "user_turn",
                  "text": "Nếu cổng phụ báo có người cạy cửa thì gọi "
                          "ngay cho số trực ca 0902000111 giúp em nha.",
                  "position": 0}]
        rec, _ = ev.bind_history_reference(
            "Vừa có báo động, cứ làm như em dặn lúc nãy nhé.", turns)
        self.assertEqual(rec["phone_number"], "0902000111")

    def test_mere_cooccurrence_is_not_binding(self):
        turns = [{"kind": "user_turn",
                  "text": "Gọi số 0902000111 giúp em.",
                  "position": 0}]
        rec, _ = ev.bind_history_reference(
            "Xem giúp tôi thời tiết hôm nay.", turns)
        self.assertIsNone(rec)


class TestPhoneEvidence(unittest.TestCase):
    def test_user_digits_proven(self):
        v = ev.phone_evidence_for(
            "0912345678", [], [],
            current_text="Gọi giúp tôi số 0912345678 nhé.")
        self.assertEqual(v["decision"], "PROVEN")
        self.assertEqual(v["basis"], "source")
        self.assertTrue(v["question_b_target_selected"])

    def test_user_spoken_proven(self):
        v = ev.phone_evidence_for(
            "0912345678", [], [],
            current_text="Gọi số không chín một hai, ba bốn năm, "
                         "sáu bảy tám nhé.")
        self.assertEqual(v["decision"], "PROVEN")

    def test_write_echo_excluded(self):
        # A succeeded sms.send result echoing the number proves
        # nothing: counting it would launder a hallucinated number
        # through its own first use.
        prefix = [_succeeded(
            "sms.send",
            {"ok": True, "message": {"phone_number": "0912345678"}},
            args={"phone_number": "0912345678"})]
        v = ev.phone_evidence_for(
            "0912345678", prefix, [],
            current_text="Xem giúp tôi thời tiết hôm nay.")
        self.assertEqual(v["decision"], "UNKNOWN")
        self.assertEqual(v["question_a_sources"], [])

    def test_proposal_args_never_evidence(self):
        # Prior-call ARGUMENTS are not evidence; only succeeded
        # results and turn texts are.
        prefix = [{"tool": "phone.recent_calls",
                   "args": {"phone_number": "0912345678"},
                   "result": {"ok": True, "calls": []},
                   "outcome": "succeeded", "position": 0}]
        v = ev.phone_evidence_for(
            "0912345678", prefix, [],
            current_text="Xem giúp tôi thời tiết hôm nay.")
        self.assertEqual(v["decision"], "UNKNOWN")

    def test_failed_log_is_not_evidence(self):
        prefix = [{"tool": "phone.recent_calls", "args": {},
                   "result": {"ok": False},
                   "outcome": "schema_rejected", "position": 0}]
        v = ev.phone_evidence_for(
            "0912345678", prefix, [],
            current_text="Gọi số 0912345678 nhé.")
        # user_text still proves it (direct request); the failed
        # log contributes nothing -- check the sources list.
        self.assertEqual(
            [s["source"] for s in v["question_a_sources"]],
            ["user_text"])

    def test_roster_unique_vs_duplicate(self):
        roster = [{"id": "c_1", "name": "An", "phone": "0912345678"}]
        v = ev.phone_evidence_for(
            "0912345678", [], roster,
            current_text="Gọi cho An giúp tôi.")
        self.assertEqual(v["decision"], "PROVEN")
        dup = [{"id": "c_1", "name": "An", "phone": "0912345678"},
               {"id": "c_2", "name": "Bình", "phone": "0912345678"}]
        v2 = ev.phone_evidence_for(
            "0912345678", [], dup,
            current_text="Gọi cho An giúp tôi.")
        # Contract change (reviewer fix R2-A2): roster sources are
        # now SPLIT -- contact identity stays ambiguous (duplicate),
        # but number existence is active (>=1 entry carries it).
        # With the name selecting An, the NUMBER verdict is PROVEN
        # for a number-target consumer; identity is still not
        # claimed (counterpart None on the active evidence).
        self.assertTrue(any(
            s["source"] == "roster" and s["status"] == "ambiguous"
            for s in v2["question_a_sources"]))
        self.assertTrue(any(
            s["source"] == "roster" and s["status"] == "active"
            and s["reason"] == "roster_number_present_multiple_contacts"
            for s in v2["question_a_sources"]))
        self.assertEqual(v2["decision"], "PROVEN")

    def test_roster_without_selection_is_ambiguous_not_proven(self):
        # Question (a) alone is not question (b): a roster number
        # with no selection signal in the request is AMBIGUOUS,
        # never written up as PROVEN.
        roster = [{"id": "c_1", "name": "An", "phone": "0912345678"}]
        v = ev.phone_evidence_for(
            "0912345678", [], roster,
            current_text="Xem giúp tôi thời tiết hôm nay.")
        self.assertEqual(v["decision"], "AMBIGUOUS")
        self.assertFalse(v["established"])
        self.assertIsNone(v["question_b_target_selected"])

    def test_different_number_requested_is_not_selected(self):
        v = ev.phone_evidence_for(
            "0912345678", [], [],
            current_text="Gọi số 0903123456 giúp tôi, đừng gọi số "
                         "0912345678.")
        self.assertFalse(v["question_b_target_selected"])
        self.assertFalse(v["established"])

    def test_tail_correction_binding(self):
        prefix = [{"kind": "user_turn",
                   "text": "Gọi giúp tôi số không chín một hai, ba bốn "
                           "năm, sáu bảy tám sáu.",
                   "position": 0}]
        v = ev.phone_evidence_for(
            "09123456768", prefix, [],
            current_text="Đuôi là sáu tám chứ không phải tám sáu, "
                         "gọi lại giúp tôi.")
        self.assertEqual(v["decision"], "PROVEN")
        self.assertEqual(v["basis"], "binding")

    def test_tail_correction_multiple_history_matches_ambiguous(self):
        prefix = [
            {"kind": "user_turn",
             "text": "Gọi số 0911111186 giúp tôi.", "position": 0},
            {"kind": "user_turn",
             "text": "Gọi số 0922222286 giúp tôi.", "position": 1},
        ]
        v = ev.phone_evidence_for(
            "0911111168", prefix, [],
            current_text="Đuôi là sáu tám chứ không phải tám sáu.")
        self.assertFalse(any(
            s["status"] == "active" and s["reason"] ==
            "tail_correction_of_history_number"
            for s in v["question_a_sources"]))


class TestCallbackReference(unittest.TestCase):
    def _prefix(self):
        return [_succeeded(
            "sms.read_recent",
            {"ok": True, "messages": [
                {"id": "m1", "contact_id": "c_300",
                 "phone_number": "0933333333", "direction": "incoming",
                 "content": "hi"}]})]

    def test_observed_counterpart_phone_call_proven(self):
        # sms/phone never validate contacts, so an observed log
        # counterpart suffices for execution -- and the verdict
        # still does not claim roster membership.
        v = ev.callback_reference_for(
            {"contact_id": "c_300"}, self._prefix(), [],
            current_text="Nhắn lại cho người đó giúp tôi.",
            consumer_tool="phone.call")
        self.assertEqual(v["decision"], "PROVEN")
        self.assertEqual(v["basis"], "binding")
        self.assertFalse(any(
            s["source"] == "roster" and s["status"] == "active"
            for s in v["question_a_sources"]))

    def test_observed_counterpart_not_roster_for_contacts_update(self):
        # contacts.update is patch-verified: a log counterpart
        # does not prove contacts-collection membership.
        v = ev.callback_reference_for(
            {"contact_id": "c_300"}, self._prefix(), [],
            current_text="Cập nhật số cho người đó.",
            consumer_tool="contacts.update")
        self.assertEqual(v["decision"], "AMBIGUOUS")
        self.assertIn("observed_counterpart_not_roster_membership",
                      v["question_b_reason"])

    def test_roster_member_contacts_update_proven(self):
        roster = [{"id": "c_300", "name": "An",
                   "phone": "0933333333"}]
        v = ev.callback_reference_for(
            {"contact_id": "c_300"}, self._prefix(), roster,
            current_text="Cập nhật số cho An.",
            consumer_tool="contacts.update")
        self.assertEqual(v["decision"], "PROVEN")
        self.assertEqual(v["basis"], "source")

    def test_free_text_id_is_not_a_source(self):
        # A contact_id appearing only inside message CONTENT (free
        # text) proves nothing about any registry.
        prefix = [_succeeded(
            "sms.read_recent",
            {"ok": True, "messages": [
                {"id": "m1", "contact_id": None,
                 "phone_number": "0944444444", "direction": "incoming",
                 "content": "Bạn c_999 nhắn là sẽ qua sau."}]})]
        v = ev.callback_reference_for(
            {"contact_id": "c_999"}, prefix, [],
            current_text="Nhắn lại cho người đó giúp tôi.",
            consumer_tool="phone.call")
        self.assertEqual(v["decision"], "UNKNOWN")

    def test_same_id_string_other_registry_is_not_contact(self):
        # Registry separation: an id string from another registry
        # (here a chat id) is not a contact reference.
        prefix = [_succeeded(
            "chat_ott.list_chats",
            {"ok": True, "chats": [{"id": "chat_77"}]})]
        v = ev.callback_reference_for(
            {"contact_id": "chat_77"}, prefix, [],
            current_text="Nhắn lại giúp tôi.",
            consumer_tool="phone.call")
        self.assertEqual(v["decision"], "UNKNOWN")

    def test_unknown_consumer_capped_at_ambiguous(self):
        v = ev.callback_reference_for(
            {"contact_id": "c_300"}, self._prefix(), [],
            current_text="Nhắn lại cho người đó giúp tôi.",
            consumer_tool="some_tool.call_x")
        self.assertEqual(v["decision"], "AMBIGUOUS")



class TestReviewerRound2Fixes(unittest.TestCase):
    """Regression tests for independent-reviewer round-2 findings
    (R2-A1/A2/A3/A4/A5). Synthetic only, no gold, no sample ids."""

    def _missed(self, cid, name, phone, pos=0):
        # Extracted log-record shape (what bind_history_reference
        # consumes), not a raw prefix entry.
        return {"tool": "phone.recent_calls", "contact_id": cid,
                "name": name, "phone_number": phone,
                "direction": "incoming", "status": "missed",
                "position": pos}

    def test_so_cua_not_retired_speaker_number_called(self):
        # R2-A5: "Số của em là X, gọi giúp em" must NOT be
        # corrected_away ("so cua" contains "so cu" as a prefix).
        mentions = ev.parse_phone_mentions(
            "Số của em là 0900333444, gọi giúp em nhé")
        self.assertEqual(
            [(m["normalized"], m["role"]) for m in mentions],
            [("0900333444", "requested_target")])
        v = ev.phone_evidence_for(
            "0900333444", [], [],
            "Số của em là 0900333444, gọi giúp em nhé")
        self.assertEqual(v["decision"], "PROVEN")

    def test_so_cu_retired_still_works(self):
        mentions = ev.parse_phone_mentions(
            "Số cũ của anh là 0900111222, số cũ không dùng nữa đâu")
        self.assertEqual(
            [(m["normalized"], m["role"]) for m in mentions],
            [("0900111222", "corrected_away")])

    def test_long_spoken_run_not_dropped_for_leading_khong(self):
        # R2-A1: a 10-digit spoken run starting with "không"
        # must be returned as a phone mention, not dropped.
        mentions = ev.parse_phone_mentions(
            "không chín tám bảy sáu năm bốn ba hai một")
        self.assertEqual([m["normalized"] for m in mentions],
                         ["0987654321"])

    def test_shared_number_name_selection_proven(self):
        # R2-A2: roster-multi + name selection proves the NUMBER
        # for a number-target consumer, even though contact
        # identity stays ambiguous.
        roster = [{"id": "c_1", "name": "An", "phone": "0987654321"},
                  {"id": "c_2", "name": "Bình", "phone": "0987654321"}]
        v = ev.phone_evidence_for("0987654321", [], roster,
                                  "Gọi cho An giúp tôi")
        self.assertEqual(v["decision"], "PROVEN")
        self.assertEqual(v["question_b_reason"], "roster_contact_named")

    def test_callback_name_mismatch_veto(self):
        # R2-A3: one missed call from Bình + "gọi lại cho An"
        # must NOT bind Bình.
        rec, reason = ev.bind_history_reference(
            "gọi lại cho An",
            [self._missed("c_111", "Bình", "0911111111")])
        self.assertIsNone(rec)
        self.assertEqual(reason, "callback_name_mismatch")

    def test_callback_family_reference_no_veto(self):
        # CONTRACT CHANGE (callback fix round, thread A, R2):
        # "gọi lại cho mẹ" is a family reference, not a name,
        # and it must NOT fall back to the single pool record
        # without relation evidence. The old expectation (bind
        # via single-pool fallback) contradicted the new
        # contract and is replaced: no bind, relation_unproven.
        # The record here is NAMED "Mạ" but carries no relation
        # field, and "mẹ" != "Mạ" as a name, so neither the name
        # path nor the relation path binds.
        rec, reason = ev.bind_history_reference(
            "gọi lại cho mẹ",
            [self._missed("c_9", "Mạ", "0922222222")])
        self.assertIsNone(rec)
        self.assertEqual(reason, "callback_relation_unproven")

    def test_callback_no_name_single_pool_preserved(self):
        rec, _ = ev.bind_history_reference(
            "gọi lại giúp tôi",
            [self._missed("c_111", "Bình", "0911111111")])
        self.assertIsNotNone(rec)
        self.assertEqual(rec["contact_id"], "c_111")

    def test_folded_name_collision_an_vs_an(self):
        # R2-A4: "An" (name) must not match "ăn" (to eat).
        rec, _ = ev.bind_history_reference(
            "Gọi lại khi ăn xong nhé",
            [self._missed("c_a", "An", "0933333333", pos=0),
             self._missed("c_c", "Chi", "0944444444", pos=1)])
        self.assertIsNone(rec)
        rec, _ = ev.bind_history_reference(
            "Gọi lại cho An nhé",
            [self._missed("c_a", "An", "0933333333", pos=0),
             self._missed("c_c", "Chi", "0944444444", pos=1)])
        self.assertIsNotNone(rec)
        self.assertEqual(rec["contact_id"], "c_a")

    def test_shared_phone_not_roster_membership(self):
        # R2-A2 (callback side): a phone shared by two roster
        # contacts never proves membership for a requiring consumer.
        roster = [{"id": "c_1", "name": "An", "phone": "0987654321"},
                  {"id": "c_2", "name": "Bình", "phone": "0987654321"}]
        v = ev.callback_reference_for(
            {"phone_number": "0987654321"}, [], roster,
            current_text="Gọi cho An giúp tôi",
            consumer_tool="contacts.update")
        self.assertNotEqual(v["decision"], "PROVEN")


class TestRound4Batch3Phone(unittest.TestCase):
    """Round-4 batch-3 phone-module rules (S2 tail-change,
    M2 copula exemption, M3 name map)."""

    def test_parse_tail_change_forms(self):
        # S2: typed + spoken + all surface forms parse to the
        # same new tail; the explicit-correction form is NOT a
        # bare change (it goes through parse_tail_correction).
        for text, tail in [
                ("Đuôi đổi thành 1234", "1234"),
                ("Đuôi đổi thành một hai ba bốn", "1234"),
                ("Đuôi là năm sáu", "56"),
                ("Đuôi thành 1234", "1234"),
                ("Đuôi là 1234", "1234"),
                ("Đổi đuôi thành 1234", "1234"),
                ("Đuôi đổi thành 1234 đi", "1234")]:
            got = ev.parse_tail_change(text)
            self.assertIsNotNone(got, text)
            self.assertEqual(got["new_tail"], tail, text)
        self.assertIsNone(ev.parse_tail_change(
            "Đuôi là 1234 chứ không phải 5678"))
        corr = ev.parse_tail_correction(
            "Đuôi là 1234 chứ không phải 5678")
        self.assertEqual(corr["new_tail"], "1234")
        self.assertEqual(corr["old_tail"], "5678")
        self.assertIn("span", corr)

    def test_m2_new_number_copula_not_background(self):
        # M2: "số X là số mới / khác" selects X; the M-b
        # copula rule still demotes role statements.
        ms = _mentions("Mà số 0911111111 là số mới")
        self.assertEqual(ms["0911111111"]["role"], "requested_target")
        ms = _mentions("Số 0911111111 là số khác")
        self.assertEqual(ms["0911111111"]["role"], "requested_target")
        ms = _mentions("Số 0911111111 là số tổng đài")
        self.assertEqual(ms["0911111111"]["role"], "background")
        ms = _mentions("Số 0911111111 là số của em")
        self.assertEqual(ms["0911111111"]["role"], "background")

    def test_m3_name_map_guards(self):
        # Unique mapping, multi-number exclusion, family
        # exclusion, action classification.
        turns = [
            {"kind": "user_turn",
             "text": "Gọi cho Vy số 0902345678 giúp tôi",
             "position": 0},
            {"kind": "user_turn",
             "text": "Nhắn cho Bình số 0911111111 giúp tôi",
             "position": 1},
            {"kind": "user_turn",
             "text": "Gọi cho mẹ số 0922222222 giúp tôi",
             "position": 2},
        ]
        m = ev._instruction_name_map(turns)
        self.assertEqual(m["vy"], [("0902345678", 0, "call")])
        # Map keys are FOLDED phrases: "Bình" -> "binh".
        self.assertEqual(m["binh"], [("0911111111", 1, "message")])
        self.assertNotIn("me", m)
        # Same name, second number: the map keeps both, so the
        # resolution (single-number guard) refuses.
        turns.append({"kind": "user_turn",
                      "text": "Gọi cho Vy số 0933333333 giúp tôi",
                      "position": 3})
        m = ev._instruction_name_map(turns)
        self.assertEqual(len(m["vy"]), 2)
        self.assertEqual(ev._instruction_addressee(
            "Gọi cho Vy nhé"), "vy")
        self.assertIsNone(ev._instruction_addressee(
            "Gọi cho mẹ nhé"))
        self.assertEqual(ev._instruction_turn_action(
            "Gọi cho Vy nhé"), "call")
        self.assertEqual(ev._instruction_turn_action(
            "Nhắn cho Vy nhé"), "message")
        self.assertIsNone(ev._instruction_turn_action(
            "Gửi cho Vy nhé"))

    def test_m3_resolution_verdict(self):
        # End to end at the module level: name-only current
        # text resolves to the instruction's number.
        prefix = [{"kind": "user_turn",
                   "text": "Gọi cho Vy số 0902345678 giúp tôi",
                   "position": 0}]
        v = ev.phone_evidence_for("0902345678", prefix, [],
                                  "Gọi cho Vy nhé")
        self.assertTrue(v["established"])
        self.assertEqual(v["question_b_reason"],
                         "instruction_name_resolution_selects_value")
        # Action mismatch: no resolution, no establishment.
        v = ev.phone_evidence_for("0902345678", prefix, [],
                                  "Nhắn cho Vy nhé")
        self.assertFalse(v["established"])

class TestRound5OwnerNewNumberStatement(unittest.TestCase):
    """Round-5 fix F-B4-9: "số mới của <Name> là Y" is a
    statement about someone else's new number, not a direct
    request for Y -- unless a request verb is present."""

    def test_owner_new_number_is_background(self):
        ms = _mentions("Số mới của Vy là 0911111111")
        self.assertEqual(ms["0911111111"]["role"], "background")
        self.assertEqual(ms["0911111111"]["reason"],
                         "owner_new_number_statement")
        ms = _mentions("Số mới của Bình là 0911111111")
        self.assertEqual(ms["0911111111"]["role"], "background")
        ms = _mentions("Số điện thoại mới của Vy là 0911111111")
        # Long form: currently no mention at all; the contract
        # is only that it must never be a direct request.
        if "0911111111" in ms:
            self.assertNotEqual(ms["0911111111"]["role"],
                                "requested_target")

    def test_owner_new_number_with_action_still_requests(self):
        # An action verb in the window keeps the request
        # reading: the statement plus an instruction is an
        # instruction.
        ms = _mentions("Số mới của Vy là 0911111111, gọi cho Vy đi")
        self.assertEqual(ms["0911111111"]["role"], "requested_target")

    def test_m2_correction_still_binds(self):
        # M2 untouched: "mà số Y là số mới" corrects to Y, so Y
        # keeps the requested_target reading (the number
        # precedes "là số mới", a different shape).
        ms = _mentions("Mà số 0911111111 là số mới")
        self.assertEqual(ms["0911111111"]["role"], "requested_target")


class TestRound7DelegatedBinding(unittest.TestCase):
    """Round-7 fix S3 at the binding level: prior-instruction
    candidates exclude fully-delegated turns when the caller
    passes the proposal action. Synthetic only."""

    X = "0902345678"

    def _ut(self, text, pos):
        return {"kind": "user_turn", "text": text, "position": pos}

    def test_delegated_turn_excluded(self):
        # The most recent phone turn is delegated, so binding
        # falls back to the earlier own instruction.
        turns = [self._ut("Gọi cho Vy số %s giúp tôi" % self.X, 0),
                 self._ut("Nhờ Vy gọi số %s giúp" % self.X, 1)]
        rec, reason = ev.bind_history_reference(
            "Làm như lúc nãy đi", turns, action="call")
        self.assertIsNotNone(rec)
        self.assertEqual(rec["position"], 0)
        self.assertEqual(reason, "prior_instruction_unique")
        # Delegated-only history binds nothing, with a
        # distinct reason (not the generic no-phone-turn).
        rec, reason = ev.bind_history_reference(
            "Làm như lúc nãy đi",
            [self._ut("Nhờ Vy gọi số %s giúp" % self.X, 0)],
            action="call")
        self.assertIsNone(rec)
        self.assertEqual(reason, "prior_instruction_all_delegated")

    def test_generic_and_other_action_not_excluded(self):
        # Generic "nho em" is not delegation: the turn binds.
        rec, _ = ev.bind_history_reference(
            "Làm như lúc nãy đi",
            [self._ut("Nhờ em gọi số %s giúp" % self.X, 0)],
            action="call")
        self.assertIsNotNone(rec)
        # Per-action precision: a delegated CALL turn still
        # binds for a MESSAGE proposal only if its message
        # verb is the user's own -- here the turn has no
        # message verb at all, so for message proposals the
        # turn is simply not a message instruction; binding
        # still returns it as the prior phone turn (the
        # adapter's action-match check, not binding, refuses
        # the cross-action un-fire). What binding must NOT
        # do is drop the turn for the action it actually
        # delegates: for call it is excluded (above).
        rec, _ = ev.bind_history_reference(
            "Làm như lúc nãy đi",
            [self._ut("Nhờ Vy gọi số %s giúp" % self.X, 0)],
            action="message")
        self.assertIsNotNone(rec)

    def test_no_action_keeps_old_behaviour(self):
        # Without an action the caller cannot judge
        # delegation, so the old behaviour stands (the
        # delegated turn binds) -- this preserves the contact
        # path and direct callers.
        rec, _ = ev.bind_history_reference(
            "Làm như lúc nãy đi",
            [self._ut("Nhờ Vy gọi số %s giúp" % self.X, 0)])
        self.assertIsNotNone(rec)
        self.assertEqual(rec["position"], 0)


class TestRound8Batch7Phone(unittest.TestCase):
    """Round-8 fix S2 (forward-object demotion, redirect
    supersede) and M1 (per-action partition) at the evidence
    level. Synthetic only."""

    X = "0902345678"
    Y = "0911111111"

    def _ut(self, text, pos):
        return {"kind": "user_turn", "text": text, "position": pos}

    def test_forward_object_is_background(self):
        # S2: a number being forwarded to someone else is
        # CONTENT, not a call/message target -- parallel to
        # the S4 content rule.
        ms = ev.parse_phone_mentions(
            "Chuyển tiếp số %s cho Bình. Tôi đổi sang số 12, "
            "gọi đi" % self.X)
        self.assertEqual(len(ms), 1)
        self.assertEqual(ms[0]["role"], "background")
        self.assertEqual(ms[0]["reason"], "forwarded_object")
        # Topicalised object: the forward verb follows the
        # mention ("Số X, chuyển tiếp cho Bình").
        ms = ev.parse_phone_mentions(
            "Số %s, chuyển tiếp cho Bình" % self.X)
        self.assertEqual(ms[0]["role"], "background")
        self.assertEqual(ms[0]["reason"], "forwarded_object")
        # A mention already governed by an earlier verb keeps
        # its own reading; only the forward object demotes.
        ms = ev.parse_phone_mentions(
            "Gọi số %s, chuyển tiếp số %s cho Bình"
            % (self.X, self.Y))
        self.assertEqual(ms[0]["role"], "requested_target")
        self.assertEqual(ms[1]["role"], "background")
        self.assertEqual(ms[1]["reason"], "forwarded_object")
        # Bare "chuyển" is NOT a forward pattern: transfer /
        # unknown shapes keep their own rules.
        ms = ev.parse_phone_mentions(
            "Chuyển số %s cho Vy" % self.X)
        self.assertEqual(ms[0]["role"], "requested_target")
        # Generic recipient exemption (2f/4b regression pin):
        # forwarding to "em" / "mình" / ... does NOT count
        # as forwarding away (F-B4-4 rule), so the mention
        # stays a target -- wherever the generic phrase
        # sits (after the mention, between verb and mention,
        # or after a topicalised forward).
        for text in (
                "Chuyển tiếp số %s cho em, gọi đi" % self.X,
                "Chuyển tiếp số %s cho em rồi gọi đi" % self.X,
                "Chuyển tiếp cho em Số %s" % self.X,
                "Số %s, chuyển tiếp cho em" % self.X):
            ms = ev.parse_phone_mentions(text)
            self.assertEqual(ms[0]["role"], "requested_target")
        # A later "cho em" belonging to another verb never
        # exempts a forward to a named recipient.
        ms = ev.parse_phone_mentions(
            "Chuyển tiếp số %s cho Bình, nhắn cho em đi"
            % self.X)
        self.assertEqual(ms[0]["role"], "background")
        self.assertEqual(ms[0]["reason"], "forwarded_object")

    def test_explicit_redirect_supersedes(self):
        # S2 backstop: "đổi sang" + a different number after
        # the last target mention re-selects away from this
        # value (last-decisive-wins for selections).
        val, reason = ev._question_b_for_phone(
            self.X,
            "Gọi số %s đi, tôi đổi sang số %s, gọi đi"
            % (self.X, self.Y), [], None)
        self.assertFalse(val)
        self.assertEqual(reason, "explicit_redirect_supersedes")
        # A target mention after the redirect re-selects it.
        val, _ = ev._question_b_for_phone(
            self.X,
            "Tôi đổi sang số %s, rồi gọi số %s đi"
            % (self.Y, self.X), [], None)
        self.assertTrue(val)
        # A redirect TO the same value confirms it.
        val, _ = ev._question_b_for_phone(
            self.X,
            "Tôi đổi sang số %s, gọi số %s đi"
            % (self.X, self.X), [], None)
        self.assertTrue(val)

    def test_prior_instruction_per_action_partition(self):
        # M1: a multi-number history turn binds per action.
        turns = [self._ut(
            "Nhờ Vy gọi số %s giúp, nhắn cho Bình số %s đi"
            % (self.X, self.Y), 0)]
        rec, reason = ev.bind_history_reference(
            "Làm như lúc nãy đi", turns, action="message")
        self.assertIsNotNone(rec)
        self.assertEqual(rec["phone_number"], self.Y)
        self.assertEqual(reason, "prior_instruction_unique")
        # The delegated call number never binds for call
        # (excluded before number selection).
        rec, reason = ev.bind_history_reference(
            "Làm như lúc nãy đi", turns, action="call")
        self.assertIsNone(rec)
        self.assertEqual(reason, "prior_instruction_all_delegated")
        # Same verb, two numbers: genuinely ambiguous, stays
        # unbound -- for message and for the action-less
        # caller (old behaviour preserved).
        turns = [self._ut(
            "Nhắn số %s và số %s" % (self.X, self.Y), 0)]
        rec, reason = ev.bind_history_reference(
            "Làm như lúc nãy đi", turns, action="message")
        self.assertIsNone(rec)
        self.assertEqual(reason, "prior_instruction_multiple_numbers")
        rec, reason = ev.bind_history_reference(
            "Làm như lúc nãy đi", turns)
        self.assertIsNone(rec)
        self.assertEqual(reason, "prior_instruction_multiple_numbers")



class TestRound9Batch9Phone(unittest.TestCase):
    """Round-9 batch-9 fix M1: switch-family backstop verbs
    at the evidence level. Synthetic only."""

    X = "0902345678"
    Y = "0911111111"

    def test_switch_family_redirect_supersedes(self):
        # M1: "đổi thành" / "đổi lại" / "chuyển sang" join
        # "đổi sang" in the backstop verb set, with the same
        # constraints (different number after the last
        # target mention, bare call after it).
        for verb in ("đổi thành", "đổi lại thành",
                     "chuyển sang"):
            val, reason = ev._question_b_for_phone(
                self.X,
                "Gọi số %s đi, tôi %s số 12, gọi đi"
                % (self.X, verb), [], None)
            self.assertFalse(val, verb)
            self.assertEqual(reason, "explicit_redirect_supersedes")
        # Explicit redirect still works via direct mention
        # regardless of verb (no backstop needed).
        val, _ = ev._question_b_for_phone(
            self.Y,
            "Tôi đổi thành số %s rồi gọi Số %s đi"
            % (self.Y, self.Y), [], None)
        self.assertTrue(val)
        # A redirect TO the same value confirms it.
        val, _ = ev._question_b_for_phone(
            self.X,
            "Tôi đổi lại thành số %s, gọi đi" % self.X,
            [], None)
        self.assertTrue(val)




if __name__ == "__main__":
    unittest.main(verbosity=2)
