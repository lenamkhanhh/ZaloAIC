"""Synthetic E7 shadow tests; no contest sample IDs, labels or answers."""
import copy
import unittest

from analysis.e7_shadow.guard import assess

NOW = {'current_time': '2024-02-03T16:20:00+07:00'}
TOOLS = {
    'memo.create': {'kind': 'write', 'parameters': {'properties': {'time': {'type': 'string', 'format': 'date-time'}}}},
    'agenda.move': {'kind': 'write', 'parameters': {'properties': {
        'event_id': {'type': 'string', 'x-ref': 'agenda.events'},
        'start': {'type': 'string', 'format': 'date-time'}, 'end': {'type': 'string', 'format': 'date-time'}}}},
    'parcel.book': {'kind': 'write', 'parameters': {'properties': {'date': {'type': 'string', 'format': 'date'}}}},
    'wallet.pay': {'kind': 'write', 'parameters': {'properties': {'amount': {'type': 'integer'}}}},
    'meter.alert': {'kind': 'write', 'parameters': {'properties': {'threshold_kwh': {'type': 'integer'}}}},
    'inventory.add': {'kind': 'write', 'parameters': {'properties': {'quantity': {'type': 'integer'}}}},
    'finder.search': {'kind': 'read', 'parameters': {'properties': {'date': {'type': 'string'}}}},
    'sys.ask_missing_info': {'kind': 'meta', 'parameters': {'properties': {}}},
}


def check(name, args, request, **kwargs):
    return assess({'name': name, 'arguments': args}, TOOLS, request, NOW, **kwargs)


class ShadowGuardTests(unittest.TestCase):
    def test_explicit_clock_normalization_and_date(self):
        for request, value in [('nhắc đọc sách lúc 9 giờ tối', '2024-02-03T21:00:00+07:00'),
                               ('nhắc đọc sách tám giờ tối mai', '2024-02-04T20:00:00+07:00')]:
            with self.subTest(request=request):
                self.assertEqual(check('memo.create', {'time': value}, request)['status'], 'ALLOW')

    def test_now_and_relative_minutes_are_valid_clock_derivations(self):
        for request, value in [('nhắc ngay bây giờ', '2024-02-03T16:20:00+07:00'),
                               ('nhắc sau năm phút nữa', '2024-02-03T16:25:00+07:00')]:
            with self.subTest(request=request):
                self.assertEqual(check('memo.create', {'time': value}, request)['status'], 'ALLOW')

    def test_calendar_date_arithmetic_without_inventing_hour(self):
        self.assertEqual(check('parcel.book', {'date': '2024-02-04'}, 'đặt bưu tá ngày mai')['status'], 'ALLOW')
        self.assertEqual(check('parcel.book', {'date': '2024-02-05'}, 'đặt bưu tá thứ hai tới')['status'], 'ALLOW')
        self.assertEqual(check('memo.create', {'time': '2024-02-04T08:00:00+07:00'}, 'nhắc đọc sách sáng mai')['status'], 'BLOCK')

    def test_clock_copy_rounding_and_pure_invention_are_not_request_evidence(self):
        for value in ('2024-02-03T16:20:00+07:00', '2024-02-03T17:00:00+07:00', '2024-02-04T03:15:00+07:00'):
            with self.subTest(value=value):
                self.assertEqual(check('memo.create', {'time': value}, 'nhắc đọc sách')['status'], 'BLOCK')

    def test_unsupported_clock_syntax_correction_and_range_are_unknown(self):
        for text in ('nhắc tám giờ kém mười', 'nhắc 8 giờ à không 9 giờ', 'đặt từ 8 giờ đến 9 giờ'):
            with self.subTest(text=text):
                self.assertEqual(check('memo.create', {'time': '2024-02-03T07:50:00+07:00'}, text)['status'], 'UNKNOWN')

    def test_unrelated_history_clock_does_not_support_current_request(self):
        history=[{'role': 'assistant', 'tool_results': [{'ok': True, 'event': {
            'id': 'synthetic_event', 'title': 'dã ngoại', 'start': '2024-02-04T10:00:00+07:00'}}]}]
        self.assertEqual(check('memo.create', {'time': '2024-02-04T10:00:00+07:00'}, 'nhắc đọc sách', history=history)['status'], 'BLOCK')

    def test_explicit_refer_back_with_matched_entity(self):
        history=[{'role': 'assistant', 'tool_results': [{'ok': True, 'event': {
            'id': 'synthetic_event', 'title': 'dã ngoại', 'start': '2024-02-04T10:00:00+07:00'}}]}]
        self.assertEqual(check('memo.create', {'time': '2024-02-04T10:00:00+07:00'},
                               'nhắc dã ngoại theo giờ như lần trước', history=history)['status'], 'ALLOW')

    def test_supersession_is_unknown_not_blanket_discard_or_allow(self):
        self.assertEqual(check('memo.create', {'time': '2024-02-04T08:00:00+07:00'},
                               'nhắc uống thuốc sáng mai theo lời dặn mới nhất')['status'], 'UNKNOWN')

    def test_selected_observed_event_plus_relative_shift(self):
        obs=[({'name': 'agenda.list', 'arguments': {}}, {'ok': True, 'events': [
            {'id': 'synthetic_event', 'title': 'dã ngoại', 'start': '2024-02-04T10:00:00+07:00', 'end': '2024-02-04T11:00:00+07:00'}]})]
        result=check('agenda.move', {'event_id': 'synthetic_event', 'start': '2024-02-04T12:00:00+07:00'},
                     'dời dã ngoại muộn hai giờ', observations=obs)
        self.assertEqual(result['status'], 'ALLOW')

    def test_real_observation_id_without_matching_entity_is_unknown(self):
        obs=[({}, {'ok': True, 'events': [{'id': 'synthetic_event', 'title': 'dã ngoại', 'start': '2024-02-04T10:00:00+07:00'}]})]
        self.assertEqual(check('agenda.move', {'event_id': 'synthetic_event', 'start': '2024-02-04T12:00:00+07:00'},
                               'dời lịch bơi lội muộn hai giờ', observations=obs)['status'], 'UNKNOWN')

    def test_same_number_in_unrelated_observation_is_not_proof(self):
        obs=[({}, {'ok': True, 'bills': [{'id': 'synthetic_bill', 'type': 'internet', 'amount': 73000}]})]
        self.assertEqual(check('wallet.pay', {'amount': 73000}, 'trả số tiền hóa đơn nước', observations=obs)['status'], 'UNKNOWN')

    def test_amount_units_word_numbers_threshold_and_quantity(self):
        for name, args, request in [('wallet.pay', {'amount': 73000}, 'chuyển bảy mươi ba nghìn đồng'),
                                     ('meter.alert', {'threshold_kwh': 180}, 'đặt ngưỡng một trăm tám mươi số điện'),
                                     ('inventory.add', {'quantity': 2}, 'thêm hai cuộn vải')]:
            with self.subTest(name=name):
                self.assertEqual(check(name, args, request)['status'], 'ALLOW')

    def test_pointed_bill_amount(self):
        obs=[({}, {'ok': True, 'bills': [{'id': 'synthetic_bill', 'type': 'water', 'amount': 73000},
                                         {'id': 'other_bill', 'type': 'internet', 'amount': 81000}]})]
        self.assertEqual(check('wallet.pay', {'amount': 73000}, 'trả số tiền hóa đơn nước', observations=obs)['status'], 'ALLOW')
        self.assertEqual(check('wallet.pay', {'amount': 81000}, 'trả số tiền hóa đơn nước', observations=obs)['status'], 'BLOCK')

    def test_half_requires_observed_base_and_is_not_fixed_fifty(self):
        obs=[({}, {'ok': True, 'item': {'id': 'synthetic_item', 'name': 'cuộn vải', 'quantity': 80}})]
        self.assertEqual(check('inventory.add', {'quantity': 40}, 'thêm một nửa số lượng cuộn vải', observations=obs)['status'], 'ALLOW')
        self.assertEqual(check('inventory.add', {'quantity': 50}, 'thêm một nửa số lượng cuộn vải', observations=obs)['status'], 'BLOCK')
        self.assertEqual(check('inventory.add', {'quantity': 50}, 'thêm một nửa số lượng cuộn vải')['status'], 'UNKNOWN')

    def test_schema_defaults_are_not_user_request_evidence(self):
        tools=copy.deepcopy(TOOLS);tools['inventory.add']['parameters']['properties']['quantity']['default']=1
        self.assertEqual(assess({'name': 'inventory.add', 'arguments': {'quantity': 1}}, tools, 'thêm vải', NOW)['status'], 'UNKNOWN')

    def test_unparsed_amount_is_unknown_not_missing(self):
        self.assertEqual(check('wallet.pay', {'amount': 1500}, 'chuyển 1.500 đồng')['status'], 'UNKNOWN')

    def test_compound_amount_intents_do_not_share_literal_evidence(self):
        self.assertEqual(check('wallet.pay', {'amount': 73000}, 'nạp bảy mươi ba nghìn rồi trả hóa đơn nước')['status'], 'UNKNOWN')

    def test_failed_results_never_enter_evidence(self):
        obs=[({}, {'ok': False, 'bills': [{'type': 'water', 'amount': 73000}]})]
        self.assertEqual(check('wallet.pay', {'amount': 73000}, 'trả số tiền hóa đơn nước', observations=obs)['status'], 'UNKNOWN')

    def test_observation_does_not_override_current_time_correction(self):
        self.assertEqual(check('memo.create', {'time': '2024-02-03T09:00:00+07:00'}, 'nhắc 8 giờ à không 9 giờ')['status'], 'UNKNOWN')

    def test_reads_meta_missing_fields_and_unknown_tools_stay_outside_scope(self):
        for name, args in [('finder.search', {'date': '2024-02-04'}), ('sys.ask_missing_info', {}),
                           ('memo.create', {'content': 'text'}), ('unregistered.write', {'time': '2024-02-04T08:00:00+07:00'})]:
            with self.subTest(name=name):
                result=check(name, args, 'synthetic request')
                self.assertFalse(result['scoped'])

    def test_malformed_or_multivalue_time_is_unknown(self):
        for value in ('not a date', ['08:00', '12:00']):
            with self.subTest(value=value):
                self.assertEqual(check('memo.create', {'time': value}, 'nhắc đọc sách')['status'], 'UNKNOWN')

    def test_atomic_call_and_input_immutability(self):
        call={'name': 'agenda.move', 'arguments': {'start': '2024-02-03T21:00:00+07:00', 'end': '2024-02-03T22:00:00+07:00'}}
        before=copy.deepcopy(call)
        result=assess(call, TOOLS, 'đặt dã ngoại lúc 9 giờ tối', NOW)
        self.assertEqual(call, before)
        self.assertEqual(result['arguments']['start']['status'], 'ALLOW')
        self.assertEqual(result['status'], 'BLOCK')

    def test_clock_absence_and_no_pointed_amount_are_different(self):
        self.assertEqual(check('wallet.pay', {'amount': 73000}, 'chuyển tiền')['status'], 'UNKNOWN')
        self.assertEqual(check('memo.create', {'time': '2024-02-03T09:00:00+07:00'}, 'nhắc đọc sách')['status'], 'BLOCK')


if __name__ == '__main__': unittest.main()
