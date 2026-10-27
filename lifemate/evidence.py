"""Observed argument provenance, not intent inference or a state reader.

Only user input and actual successful tool results enter this ledger. Tool
schemas/examples, model proposals, labels and hidden state never enter it.
IDs are scoped by catalog x-ref collection. Existence/evidence alone does not
prove that an entity is the one intended by the current request.
"""
from __future__ import annotations

import ast
import json
import re


def parse_history_results(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            try:
                value = ast.literal_eval(value)
            except (ValueError, SyntaxError, TypeError, RecursionError):
                return []
    if isinstance(value, dict):
        return [value]
    return value if isinstance(value, list) else []


def _singular(word):
    return word[:-3] + "y" if word.endswith("ies") else word.rstrip("s")


class EvidenceLedger:
    def __init__(self, tools, executed=(), results=(), history=(), transcript="", context=None):
        self.entities = {}
        self.phones = set()
        self.refs_by_app = {}
        self.refs_by_param = {}
        self.context_ids = {}
        self.user_text = [transcript]
        for tool in tools.values():
            for name, prop in tool.get("parameters", {}).get("properties", {}).items():
                ref = prop.get("x-ref")
                if ref:
                    self.refs_by_app.setdefault(ref.split(".")[0], set()).add(ref)
                    self.refs_by_param.setdefault(name, set()).add(ref)
        for turn in history or ():
            if turn.role == "user":
                self.user_text.append(turn.audio_text or "")
            else:
                for call, result in zip(turn.tool_calls or (), parse_history_results(turn.tool_results)):
                    self.observe(call, result)
        for call, result in zip(executed, results):
            self.observe(call, result)
        self._collect_phones(context or {})
        def context_ids(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    if key in self.refs_by_param and isinstance(child, str):
                        self.context_ids.setdefault(key, set()).add(child)
                    context_ids(child)
            elif isinstance(value, list):
                for child in value:
                    context_ids(child)
        context_ids(context or {})
        for text in self.user_text:
            self.phones.update(_text_phones(text))

    def _collect_phones(self, value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in ("phone", "phone_number", "mobile") and isinstance(child, str):
                    number = _phone(child)
                    if number:
                        self.phones.add(number)
                if key in ("content", "body", "text", "message", "description", "note", "subject") and isinstance(child, str):
                    self.phones.update(_text_phones(child))
                self._collect_phones(child)
        elif isinstance(value, list):
            for child in value:
                self._collect_phones(child)

    def observe(self, call, result):
        if not isinstance(result, dict) or result.get("ok") is not True or result.get("done") is False:
            return
        self._collect_phones(result)
        app = call.get("name", "").split(".")[0]
        refs = self.refs_by_app.get(app, set())
        aliases = {_singular(ref.split(".", 1)[1]): ref for ref in refs}
        default = next(iter(refs)) if len(refs) == 1 else None

        def visit(value, ref):
            if isinstance(value, dict):
                if isinstance(value.get("id"), str) and ref:
                    display = next((value[k] for k in ("name", "display_name", "title", "label")
                                    if isinstance(value.get(k), str)), None)
                    self.entities.setdefault(ref, {})[value["id"]] = display
                for key, child in value.items():
                    for target in self.refs_by_param.get(key, ()):
                        if isinstance(child, str):
                            self.entities.setdefault(target, {})[child] = None
                    visit(child, aliases.get(_singular(key), ref))
            elif isinstance(value, list):
                for child in value:
                    visit(child, ref)
        visit(result, default)

    def user_supplied(self, value, parameter):
        if value in self.context_ids.get(parameter, ()):
            return True
        literal = r"(?<!\w)" + re.escape(value) + r"(?!\w)"
        # A person's name merely appearing in the request is not an opaque ID.
        shaped_id = not re.search(r"\s", value) and bool(re.search(r"[\d_:-]", value))
        labelled = r"\b(?:" + re.escape(parameter) + r"|id)\s*[:=]?\s*['\"]?" + re.escape(value) + r"(?!\w)"
        return any(re.search(labelled, text, re.I) or (shaped_id and re.search(literal, text))
                   for text in self.user_text)


def _phone(value):
    if not isinstance(value, str) or re.search(r"[^\d\s+().-]", value):
        return None
    number = re.sub(r"\D", "", value)
    return number if 7 <= len(number) <= 15 else None


def _text_phones(text):
    numbers = set()
    for match in re.finditer(r"(?<!\w)\+?\d[\d .()-]{5,}\d(?!\w)", text):
        number = _phone(match.group())
        if number:
            numbers.add(number)
    # Individual spoken digits only, not cardinal-number arithmetic. The
    # minimum length avoids interpreting ordinary amounts/times as phones.
    digits = {"không": "0", "một": "1", "hai": "2", "ba": "3", "bốn": "4",
              "tư": "4", "năm": "5", "sáu": "6", "bảy": "7", "bẩy": "7",
              "tám": "8", "chín": "9"}
    run = ""
    for word in re.findall(r"\w+|[^\w\s]", text.lower()) + [""]:
        if word in digits:
            run += digits[word]
        elif word in (",", "-", "/") and run:
            continue  # Spoken digit groups may be separated by short pauses.
        else:
            if 7 <= len(run) <= 15:
                numbers.add(run)
            run = ""
    return numbers
