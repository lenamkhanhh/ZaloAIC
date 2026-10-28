#!/usr/bin/env python3
"""E-asr-1 audit: count error-relevant expression frequencies in LifeMate train.

Reads ONLY train.jsonl fields: id, audio_text (current request), history (user
turns' audio_text only), label.tool_calls (gold calls). It NEVER reads
train_environment/ or state.json: per-sample contact rosters are out of scope
for this audit (see the report for why duplicate-name and abbreviation rates
are reported as NOT MEASURABLE from these fields alone).

Method (deterministic, no model, stdlib only):
  - Text is NFC-normalized and lowercased. Tones are KEPT (no diacritic
    folding): Vietnamese number/time words differ by tone, and folding would
    merge distinct words.
  - Text is tokenized into unicode letter/digit tokens. Multi-word expressions
    are matched on token sequences, longest first, non-overlapping, so
    "ngay mai" counts once (not "ngay mai" + "mai") and "thu tu" (Wednesday)
    does not count as the number word "tu" (four).
  - Relative-time phrases are scanned FIRST and their spans are consumed, so
    number-word counting never double-counts words inside time phrases
    ("thu hai" contains "hai", "thu nam" contains "nam").
  - A number-word token immediately preceded by "thang" is skipped (month
    names: "thang mot" = January, not the number one).

Usage:
  python3 analysis/e_asr_1_audit.py --train-jsonl <path> [--out-json <path>]

Output: JSON summary on stdout (and to --out-json when given).
"""

import argparse
import collections
import json
import re
import sys
import unicodedata

# ---------------------------------------------------------------- lexicons
# Single-token Vietnamese number words (surface forms, tones kept).
NUMBER_TOKENS = {
    "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín", "mười",
    "mươi", "chục", "trăm", "nghìn", "ngàn", "triệu", "tỷ", "tỉ",
    "rưỡi", "nửa", "linh", "lẻ", "mốt", "tư", "lăm",
}
BIG_UNITS = {"nghìn", "ngàn", "triệu", "tỷ", "tỉ", "k"}

# Relative-time phrases as token tuples, longest first at match time.
TIME_PHRASES = [
    ("ngày", "mai"), ("ngày", "kia"), ("ngày", "mốt"),
    ("hôm", "nay"), ("hôm", "qua"), ("hôm", "kia"),
    ("tuần", "này"), ("tuần", "sau"), ("tuần", "trước"),
    ("tháng", "này"), ("tháng", "sau"), ("tháng", "trước"),
    ("năm", "nay"), ("năm", "sau"), ("năm", "trước"),
    ("sáng", "mai"), ("chiều", "mai"), ("tối", "mai"),
    ("sáng", "nay"), ("chiều", "nay"), ("tối", "nay"),
    ("cuối", "tuần"), ("đầu", "tuần"), ("cuối", "tháng"), ("đầu", "tháng"),
    ("thứ", "hai"), ("thứ", "ba"), ("thứ", "tư"), ("thứ", "năm"),
    ("thứ", "sáu"), ("thứ", "bảy"), ("chủ", "nhật"),
    ("vài", "ngày"),
    ("mai",), ("mốt",),
]
# Vague dayparts: give a DATE only, the hour is still missing -> ask for hour.
VAGUE_DAYPARTS = {
    ("sáng", "mai"), ("chiều", "mai"), ("tối", "mai"),
    ("sáng", "nay"), ("chiều", "nay"), ("tối", "nay"),
}
WEEKDAY_PHRASES = {
    ("thứ", "hai"), ("thứ", "ba"), ("thứ", "tư"), ("thứ", "năm"),
    ("thứ", "sáu"), ("thứ", "bảy"), ("chủ", "nhật"),
}
DAY_OFFSET_PHRASES = {
    ("ngày", "mai"), ("ngày", "kia"), ("ngày", "mốt"),
    ("hôm", "nay"), ("hôm", "qua"), ("hôm", "kia"), ("mai",), ("mốt",),
}
WEEK_MONTH_PHRASES = {
    ("tuần", "này"), ("tuần", "sau"), ("tuần", "trước"),
    ("tháng", "này"), ("tháng", "sau"), ("tháng", "trước"),
    ("năm", "nay"), ("năm", "sau"), ("năm", "trước"),
    ("cuối", "tuần"), ("đầu", "tuần"), ("cuối", "tháng"), ("đầu", "tháng"),
}

TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)  # unicode letters + digits
DIGIT_RE = re.compile(r"^\d+$")


def normalize(text):
    return unicodedata.normalize("NFC", text or "").lower()


def tokenize(text):
    return TOKEN_RE.findall(normalize(text))


def scan_time_phrases(tokens):
    """Longest-first non-overlapping scan. Returns (matches, consumed_idx)."""
    matches = []
    consumed = set()
    phrases = sorted(TIME_PHRASES, key=len, reverse=True)
    i = 0
    while i < len(tokens):
        hit = None
        for ph in phrases:
            if tokens[i:i + len(ph)] == list(ph):
                hit = ph
                break
        if hit:
            matches.append(hit)
            for j in range(i, i + len(hit)):
                consumed.add(j)
            i += len(hit)
        else:
            i += 1
    return matches, consumed


def scan_digit_offsets(tokens):
    """Patterns: <digits> ngay nua/truoc, <digits> tuan/thang nua."""
    hits = []
    for i, tok in enumerate(tokens):
        if DIGIT_RE.match(tok) and i + 2 < len(tokens) + 1:
            nxt = tokens[i + 1] if i + 1 < len(tokens) else None
            nxt2 = tokens[i + 2] if i + 2 < len(tokens) else None
            if nxt == "ngày" and nxt2 in ("nữa", "trước"):
                hits.append((tok, "ngày", nxt2))
            elif nxt in ("tuần", "tháng") and nxt2 == "nữa":
                hits.append((tok, nxt, nxt2))
    return hits


def scan_numbers(tokens, consumed):
    """Number-word tokens on unconsumed positions (see module docstring)."""
    hits = []
    for i, tok in enumerate(tokens):
        if i in consumed:
            continue
        if tok in NUMBER_TOKENS:
            # Month names: "thang mot" = January, not the number one.
            if tok in ("một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám",
                       "chín", "mười") \
                    and i > 0 and tokens[i - 1] == "tháng":
                continue
            hits.append(tok)
    # Digit + word-unit: "50 nghin", "2 trieu", "50k" (k attaches to digits).
    digit_units = 0
    for i, tok in enumerate(tokens):
        if DIGIT_RE.match(tok) and i + 1 < len(tokens) \
                and tokens[i + 1] in BIG_UNITS:
            digit_units += 1
    digit_k = sum(1 for t in tokens if re.match(r"^\d+k$", t))
    return hits, digit_units, digit_k


def user_texts(sample):
    cur = sample.get("audio_text", "") or ""
    hist = []
    for turn in sample.get("history", []) or []:
        if isinstance(turn, dict) and turn.get("role") == "user":
            hist.append(turn.get("audio_text", "") or "")
    return cur, hist


def audit(path):
    samples = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                samples.append(json.loads(line))
    n = len(samples)
    c = collections.Counter()
    per_token = collections.Counter()
    per_phrase = collections.Counter()
    per_token_cur = collections.Counter()
    search_queries = collections.Counter()
    search_query_tokens = collections.Counter()

    for s in samples:
        cur_text, hist_texts = user_texts(s)
        cur_tok = tokenize(cur_text)
        hist_tok = []
        for t in hist_texts:
            hist_tok.extend(tokenize(t))
        gold = (s.get("label") or {}).get("tool_calls", []) or []
        names = [g.get("name", "") for g in gold]
        argkeys = set()
        for g in gold:
            argkeys.update((g.get("arguments") or {}).keys())
        has_search = "contacts.search" in names
        has_contact_id = "contact_id" in argkeys
        has_amount = "amount" in argkeys
        has_time = bool(argkeys & {"time", "date", "start", "end"})
        has_ask = "sys.ask_missing_info" in names
        exactly_one_ask = len(gold) == 1 and has_ask

        c["samples"] += 1
        if hist_texts:
            c["samples_with_history"] += 1
        if has_search:
            c["samples_with_contacts_search"] += 1
        if has_contact_id:
            c["samples_with_contact_id_arg"] += 1
        if has_contact_id and not has_search:
            c["samples_contact_id_without_search"] += 1
        if has_amount:
            c["samples_with_amount_arg"] += 1
        if has_time:
            c["samples_with_time_arg"] += 1
        if has_ask:
            c["samples_with_ask_in_gold"] += 1
        if exactly_one_ask:
            c["samples_gold_exactly_one_ask"] += 1

        for g in gold:
            if g.get("name") == "contacts.search":
                q = (g.get("arguments") or {}).get("query", "")
                search_queries[q] += 1
                search_query_tokens[len(tokenize(q))] += 1

        for scope, toks in (("cur", cur_tok), ("hist", hist_tok)):
            t_matches, consumed = scan_time_phrases(toks)
            d_off = scan_digit_offsets(toks)
            n_hits, d_units, d_k = scan_numbers(toks, consumed)
            has_num = bool(n_hits)
            has_time_expr = bool(t_matches or d_off)
            if scope == "cur":
                if has_num:
                    c["cur_number_word_samples"] += 1
                if has_time_expr:
                    c["cur_rel_time_samples"] += 1
                if n_hits and any(t in BIG_UNITS for t in n_hits):
                    c["cur_number_word_with_big_unit_samples"] += 1
                if d_units or d_k:
                    c["cur_digit_unit_samples"] += 1
                if has_num and has_amount:
                    c["cur_number_word_and_gold_amount"] += 1
                if has_amount and not has_num:
                    c["cur_gold_amount_without_number_word"] += 1
                if has_time_expr and has_time:
                    c["cur_rel_time_and_gold_time_arg"] += 1
                if any(p in VAGUE_DAYPARTS for p in t_matches):
                    c["cur_vague_daypart_samples"] += 1
                if any(p in WEEKDAY_PHRASES for p in t_matches):
                    c["cur_weekday_samples"] += 1
                if any(p in DAY_OFFSET_PHRASES for p in t_matches) or d_off:
                    c["cur_day_offset_samples"] += 1
                if any(p in WEEK_MONTH_PHRASES for p in t_matches):
                    c["cur_week_month_samples"] += 1
                for t in n_hits:
                    per_token[t] += 1
                    per_token_cur[t] += 1
                for p in t_matches:
                    per_phrase[" ".join(p)] += 1
                for d in d_off:
                    per_phrase[" ".join(d)] += 1
                c["cur_number_word_matches"] += len(n_hits)
                c["cur_time_matches"] += len(t_matches) + len(d_off)
            else:
                if has_num:
                    c["hist_number_word_samples"] += 1
                if has_time_expr:
                    c["hist_rel_time_samples"] += 1
            # Either-scope flags (computed from both scopes at the end).
            if scope == "cur":
                cur_flags = (has_num, has_time_expr)
            else:
                hist_flags = (has_num, has_time_expr)
        if cur_flags[0] or hist_flags[0]:
            c["either_number_word_samples"] += 1
        if cur_flags[1] or hist_flags[1]:
            c["either_rel_time_samples"] += 1

    out = {
        "train_jsonl": path,
        "n_samples": n,
        "counts": dict(c),
        "number_word_token_matches_current": dict(per_token),
        "time_phrase_matches_current": dict(per_phrase),
        "contacts_search_query_token_counts": {
            str(k): v for k, v in sorted(search_query_tokens.items())
        },
        "top_contacts_search_queries": search_queries.most_common(15),
        "method_notes": [
            "Tones are kept (no diacritic folding).",
            "Time phrases are scanned longest-first and consume their spans, "
            "so number-word counting never double-counts words inside time "
            "phrases ('thu tu' is Wednesday, not four).",
            "A number-word token right after 'thang' is skipped (month names).",
            "History scope counts user turns only; assistant text and tool "
            "results are excluded (they are system output, not user speech).",
            "Duplicate-name and abbreviation rates are NOT measurable from "
            "audio_text + label.tool_calls alone: they need the per-sample "
            "contact roster, which this audit deliberately does not read "
            "(competition rule: all state access via ToolEnv). See report.",
        ],
    }
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train-jsonl", required=True)
    ap.add_argument("--out-json", default=None)
    args = ap.parse_args()
    result = audit(args.train_jsonl)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out_json:
        with open(args.out_json, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
