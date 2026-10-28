"""E7 phase-0 ONLY: partial, three-valued provenance, never an executor.

No labels, sample IDs, model proposals from other steps, hidden environment
state or schema example values are evidence. UNKNOWN is NOT an allow and
NOT a measured false-block. This module is not imported by lifemate runtime.
"""
from __future__ import annotations

import ast
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
import json
import re
import unicodedata

_WORDS = {'không': 0, 'một': 1, 'mốt': 1, 'hai': 2, 'ba': 3, 'bốn': 4,
          'tư': 4, 'năm': 5, 'lăm': 5, 'sáu': 6, 'bảy': 7, 'tám': 8, 'chín': 9}
_NUM = r'(?:\d+(?:[.,]\d+)*|(?:' + '|'.join([*_WORDS, 'mười', 'mươi', 'trăm', 'linh', 'lẻ']) + r')(?:\s+(?:' + '|'.join([*_WORDS, 'mười', 'mươi', 'trăm', 'linh', 'lẻ']) + r'))*)'
_TEMPORAL = {'time', 'start', 'end', 'date', 'schedule_time', 'due_date', 'times'}
_AMOUNT = {'amount', 'quantity', 'threshold', 'threshold_kwh'}
_INDIRECT = r'như lần trước|như hôm qua|như cũ|hôm đó|hôm ấy|buổi đó|lúc đó|giờ đó|lời dặn|theo|mới nhất|đã đổi|giờ họp|giờ hẹn|trước lúc|giờ xe|lịch'
_SUPERSESSION = r'mới nhất|đã đổi|không theo cái cũ|thay thế|cập nhật'
_COMPLEX = r'à không|kém|từ.+(?:đến|tới)|\b(?:rồi|sau đó|đồng thời)\b'
_BILL_TYPES = {'water': r'nước', 'internet': r'mạng|internet',
               'electricity': r'điện(?!\s*thoại)', 'phone': r'điện thoại',
               'tv': r'truyền hình', 'tuition': r'học phí'}


def _text(value):
    return unicodedata.normalize('NFC', str(value)).lower().strip()


def _number(text):
    text = _text(text)
    if re.fullmatch(r'\d+(?:[.,]\d+)*', text):
        # A single 3-digit separator is deliberately ambiguous, as in grounding.
        if re.fullmatch(r'\d{1,3}[.,]\d{3}', text):
            return None
        try:
            return Decimal(text.replace(',', '.'))
        except InvalidOperation:
            return None
    tokens = [t for t in text.split() if t not in ('linh', 'lẻ')]
    if not tokens:
        return None
    total = 0
    if 'trăm' in tokens:
        i = tokens.index('trăm')
        if i != 1 or tokens[0] not in _WORDS:
            return None
        total = _WORDS[tokens[0]] * 100
        tokens = tokens[2:]
    if not tokens:
        return Decimal(total)
    if tokens[0] == 'mười':
        return Decimal(total + 10 + (_WORDS.get(tokens[1], 0) if len(tokens) == 2 else 0)) if len(tokens) <= 2 else None
    if len(tokens) >= 2 and tokens[1] == 'mươi' and tokens[0] in _WORDS:
        return Decimal(total + 10 * _WORDS[tokens[0]] + (_WORDS.get(tokens[2], 0) if len(tokens) == 3 else 0)) if len(tokens) <= 3 else None
    if len(tokens) == 1 and tokens[0] in _WORDS:
        return Decimal(total + _WORDS[tokens[0]])
    return None


def _decision(status, reason, source=None):
    return {'status': status, 'reason': reason, 'source': source}


def _dt(value):
    try:
        result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return result if result.tzinfo is not None else None
    except (ValueError, TypeError):
        return None


def _result_objects(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            try:
                value = ast.literal_eval(value)
            except (ValueError, SyntaxError):
                return []
    if isinstance(value, list):
        return [child for child in value if isinstance(child, dict)]
    return [value] if isinstance(value, dict) else []


def _records(value):
    if isinstance(value, dict):
        if any(k in value for k in _TEMPORAL | _AMOUNT | {'balance'}):
            yield value
        for child in value.values():
            yield from _records(child)
    elif isinstance(value, list):
        for child in value:
            yield from _records(child)


def _sources(observations, history, include_history):
    for index, (_, result) in enumerate(observations):
        if isinstance(result, dict) and result.get('ok') is True and result.get('done') is not False:
            for record in _records(result):
                yield record, f'observation:{index}'
    if include_history:
        for index, turn in enumerate(history):
            for result in _result_objects(turn.get('tool_results')):
                if result.get('ok') is True and result.get('done') is not False:
                    for record in _records(result):
                        yield record, f'history:{index}'


def _points_to(record, request):
    if isinstance(record.get('id'), str) and record['id'].lower() in request:
        return True
    for key in ('name', 'title', 'label', 'provider'):
        value = _text(record.get(key, ''))
        words = set(re.findall(r'\w+', value))
        if len(words) >= 2 and words <= set(re.findall(r'\w+', request)):
            return True
    bill_type = _text(record.get('type', ''))
    return bool(bill_type in _BILL_TYPES and re.search(_BILL_TYPES[bill_type], request))


def _pointed(call, spec, request, observations, history):
    # Typed argument IDs restrict candidates, but never by themselves prove intent.
    properties = spec.get('parameters', {}).get('properties', {})
    ids = {value for key, value in call.get('arguments', {}).items()
           if properties.get(key, {}).get('x-ref') and isinstance(value, str)}
    include_history = bool(re.search(_INDIRECT, request))
    result = []
    for record, source in _sources(observations, history, include_history):
        # A bill amount can source a transfer amount without being the selected
        # bank-account/beneficiary ID. Those IDs bind different entity types.
        is_bill = record.get('type') in _BILL_TYPES and 'amount' in record
        if ids and record.get('id') not in ids and not is_bill:
            continue
        if _points_to(record, request):
            result.append((record, source))
    return result


def _date_request(request, now):
    explicit = re.search(r'\b(\d{4}-\d{2}-\d{2})\b', request)
    if explicit:
        try:
            return datetime.fromisoformat(explicit[1]).date(), 'explicit_date'
        except ValueError:
            return None, 'unparsed_date'
    match = re.search(r'\b(\d{1,2})/(\d{1,2})(?:/(\d{4}))?\b', request)
    if match:
        try:
            return datetime(int(match[3] or now.year), int(match[2]), int(match[1])).date(), 'explicit_date'
        except ValueError:
            return None, 'unparsed_date'
    if re.search(r'ngày kia|ngày mốt', request):
        return now.date() + timedelta(days=2), 'relative_date'
    if re.search(r'\b(?:ngày|sáng|trưa|chiều|tối|đêm|giờ)\s+mai\b|^mai\b', request):
        return now.date() + timedelta(days=1), 'relative_date'
    if re.search(r'\bmai\b', request):
        return None, 'ambiguous_date_or_person_name'
    if 'hôm nay' in request:
        return now.date(), 'relative_date'
    weekdays = {'hai': 0, 'ba': 1, 'tư': 2, 'năm': 3, 'sáu': 4, 'bảy': 5}
    match = re.search(r'thứ\s+(hai|ba|tư|năm|sáu|bảy)|chủ nhật', request)
    if match:
        weekday = weekdays[match[1]] if match[1] else 6
        days = (weekday - now.weekday()) % 7
        if 'tuần sau' in request:
            days = 7 - now.weekday() + weekday
        elif days == 0 and ('tới' in request or 'sau' in request):
            days = 7
        return now.date() + timedelta(days=days), 'weekday'
    if re.search(r'tuần|tháng|ngày\s+\d|hôm qua|ngày trước', request):
        return None, 'unparsed_date'
    return now.date(), 'implicit_today_anchor'


def _clocks(request):
    values = []
    for match in re.finditer(r'(?<!\w)(' + _NUM + r')\s*(?:giờ|h\b|:)\s*(?:(\d{1,2})(?:\s*phút)?)?\s*(rưỡi)?\s*(sáng|chiều|tối|trưa|đêm)?', request):
        number = _number(match[1])
        if number is None:
            continue
        hour = int(number)
        minute = 30 if match[3] else int(match[2] or 0)
        if match[4] in ('chiều', 'tối') and hour < 12:
            hour += 12
        if match[4] == 'đêm' and hour == 12:
            hour = 0
        if 0 <= hour < 24 and 0 <= minute < 60:
            values.append((hour, minute))
    return list(dict.fromkeys(values))


def _delta(request):
    # One operation only. Multiple temporal operations need a task/slot binding.
    matches = list(re.finditer(r'(sau|trước|muộn(?: hơn)?|sớm(?: hơn)?)\s+(' + _NUM + r')\s*(phút|tiếng|giờ)', request))
    if len(matches) != 1:
        return None
    match = matches[0]
    number = _number(match[2])
    if number is None:
        return None
    minutes = float(number) * (1 if match[3] == 'phút' else 60)
    return timedelta(minutes=-minutes if match[1].startswith(('trước', 'sớm')) else minutes)


def _temporal(key, value, request, context, pointed):
    if not isinstance(value, str):
        return _decision('UNKNOWN', 'unsupported_multivalue_or_type')
    now = _dt(context.get('current_time'))
    if now is None:
        return _decision('UNKNOWN', 'missing_clock_anchor')
    date_only = key.endswith('date') or bool(re.fullmatch(r'\d{4}-\d{2}-\d{2}', value))
    candidate = _dt(value) if not date_only else None
    if date_only:
        try:
            candidate_date = datetime.fromisoformat(value).date()
        except ValueError:
            return _decision('UNKNOWN', 'unparsed_proposed_date')
    elif candidate is None:
        return _decision('UNKNOWN', 'unparsed_proposed_datetime')
    if re.search(_SUPERSESSION, request):
        return _decision('UNKNOWN', 'unresolved_field_level_supersession')
    if re.search(_COMPLEX, request):
        return _decision('UNKNOWN', 'unparsed_correction_range_or_multiple_actions')
    desired_date, date_source = _date_request(request, now)
    if date_only:
        if desired_date is None or date_source == 'implicit_today_anchor':
            return _decision('UNKNOWN', 'date_reference_not_resolved')
        return _decision('ALLOW' if candidate_date == desired_date else 'BLOCK', 'derived_date_check', date_source)
    candidate = candidate.astimezone(now.tzinfo)
    if 'ngay bây giờ' in request or 'ngay lúc này' in request:
        return _decision('ALLOW' if candidate == now else 'BLOCK', 'explicit_now_check', 'request+clock')
    delta = _delta(request)
    if delta is not None and 'nữa' in request:
        return _decision('ALLOW' if candidate == now + delta else 'BLOCK', 'relative_clock_check', 'request+clock')
    if delta is not None:
        candidates = [(record.get(key), source) for record, source in pointed if record.get(key)]
        valid = [(_dt(raw), source) for raw, source in candidates if _dt(raw)]
        if len(valid) == 1:
            base, source = valid[0]
            return _decision('ALLOW' if candidate == base + delta else 'BLOCK', 'pointed_time_arithmetic', source)
        return _decision('UNKNOWN', 'relative_event_or_slot_not_uniquely_bound')
    clocks = _clocks(request)
    if len(clocks) > 1 or desired_date is None:
        return _decision('UNKNOWN', 'multiple_clocks_or_unparsed_date')
    if clocks:
        expected_hour, expected_minute = clocks[0]
        valid = candidate.date() == desired_date and (candidate.hour, candidate.minute) == (expected_hour, expected_minute) and candidate.second == 0
        # Event updates without a request date need the selected event's date.
        if key in ('start', 'end') and pointed and date_source == 'implicit_today_anchor':
            return _decision('UNKNOWN', 'update_date_inheritance_not_implemented')
        return _decision('ALLOW' if valid else 'BLOCK', 'explicit_request_clock_check', 'request+' + date_source)
    if re.search(_INDIRECT, request):
        values = [(record.get(key) or record.get('start') or record.get('time'), source) for record, source in pointed]
        values = [(raw, source) for raw, source in values if _dt(raw)]
        if len(values) == 1:
            raw, source = values[0]
            return _decision('ALLOW' if candidate == _dt(raw) else 'BLOCK', 'explicit_pointed_reference_check', source)
        return _decision('UNKNOWN', 'unresolved_reference_or_entity')
    if re.search(r'giờ|\d\s*h|rưỡi|tiếng|phút', request):
        return _decision('UNKNOWN', 'unparsed_time_expression')
    return _decision('BLOCK', 'no_request_hour_or_supported_reference', 'request_hour_absent')


def _numeric(key, value, request, pointed, schema):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return _decision('UNKNOWN', 'unsupported_numeric_type')
    proposed = Decimal(str(value))
    if re.search(_SUPERSESSION, request):
        return _decision('UNKNOWN', 'unresolved_field_level_supersession')
    if re.search(_COMPLEX, request):
        return _decision('UNKNOWN', 'multiple_action_slot_binding_not_implemented')
    if 'một nửa' in request:
        base_keys = ('balance', 'amount') if key == 'amount' else (key,)
        bases = [(record[k], source) for record, source in pointed for k in base_keys
                 if isinstance(record.get(k), (int, float)) and not isinstance(record[k], bool)]
        if len(bases) == 1:
            base, source = bases[0]
            return _decision('ALLOW' if proposed == Decimal(str(base)) / 2 else 'BLOCK', 'half_of_pointed_base', source)
        return _decision('UNKNOWN', 'half_requires_one_pointed_base')
    if re.search(r'hóa đơn|số tiền|số dư|số lượng|ngưỡng cũ|như lần trước', request):
        values = [(record[key], source) for record, source in pointed
                  if isinstance(record.get(key), (int, float)) and not isinstance(record[key], bool)]
        if len(values) == 1:
            base, source = values[0]
            return _decision('ALLOW' if proposed == Decimal(str(base)) else 'BLOCK', 'pointed_numeric_value', source)
        return _decision('UNKNOWN', 'numeric_reference_not_uniquely_bound')
    numbers = []
    if key == 'amount':
        for match in re.finditer(r'(?<!\w)(' + _NUM + r')\s*(nghìn|ngàn|triệu|k\b|đồng|vnd)', request):
            number = _number(match[1])
            if number is not None:
                numbers.append(number * {'nghìn': 1000, 'ngàn': 1000, 'triệu': 1000000, 'k': 1000}.get(match[2], 1))
    else:
        numbers = [value for match in re.finditer(r'(?<!\w)(' + _NUM + r')(?!\w)', request) if (value := _number(match[1])) is not None]
    numbers = list(dict.fromkeys(numbers))
    if len(numbers) == 1:
        return _decision('ALLOW' if proposed == numbers[0] else 'BLOCK', 'single_explicit_numeric_expression', 'request')
    if 'default' in schema:
        return _decision('UNKNOWN', 'schema_default_is_not_request_binding')
    return _decision('UNKNOWN', 'numeric_expression_or_source_not_resolved')


def assess(call, tools, request, context, *, observations=(), history=()):
    """Return an immutable-by-convention diagnostic dict; never call a tool.

    Only present, catalog-declared scalar slots are checked. Required-field
    absence and unknown tools belong to the existing validator, not this guard.
    """
    spec = tools.get(call.get('name'), {})
    output = {'status': 'ALLOW', 'scoped': False, 'arguments': {}}
    if spec.get('kind') != 'write':
        return output
    properties = spec.get('parameters', {}).get('properties', {})
    request = _text(request)
    pointed = _pointed(call, spec, request, observations, history)
    for key, value in call.get('arguments', {}).items():
        if key not in properties:
            continue
        schema = properties[key]
        if key in _TEMPORAL or schema.get('format') in ('date-time', 'date') or key.endswith(('_time', '_date')):
            result = _temporal(key, value, request, context, pointed)
        elif key in _AMOUNT or key.startswith('threshold_'):
            result = _numeric(key, value, request, pointed, schema)
        else:
            continue
        output['arguments'][key] = result
    if not output['arguments']:
        return output
    output['scoped'] = True
    statuses = {result['status'] for result in output['arguments'].values()}
    output['status'] = 'BLOCK' if 'BLOCK' in statuses else 'UNKNOWN' if 'UNKNOWN' in statuses else 'ALLOW'
    return output
