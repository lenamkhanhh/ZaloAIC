#!/usr/bin/env python3
"""Round 6: replay gold contacts.search through the official ToolEnv.

Measures, on LifeMate train, what the text-only E-asr-1 audit could NOT:
  (a) true duplicate-name rate within a sample's visible roster (same
      display name, different contact_id, among contacts returned by a gold
      search -- a lower bound on roster duplicates, since search returns
      matches, not the whole book; empty-query searches return the whole
      book and are reported separately);
  (b) true abbreviation/initials rate: gold queries that match exactly one
      returned contact by an abbreviation rule (initials, word-substring,
      cross-word substring), and how often that single hit is the contact
      gold subsequently uses.

SANCTIONED ACCESS ONLY: every roster observation comes from
``zaic_tools.ToolEnv(...).call('contacts.search', ...)`` -- the official
runtime path. This script NEVER opens train_environment/ or state.json
directly, and never reads a sample's full state. Phones are dropped from
stored records (only id, name, relation are kept, locally, for calibration).

Also collected (gold-only, no env): contacts.update frequency in gold
(roster mutation caveat), gold amount value types, gold time value formats
-- these feed the round-6 adapter design, not the roster rates.

Usage:
  python3 analysis/contacts_roster_replay.py \
      --train-jsonl <train.jsonl> --data-root <dir containing train/> \
      [--out-json <path>]
"""

import argparse
import collections
import json
import re
import sys
import unicodedata
from pathlib import Path


def nfc_lower(s):
    return unicodedata.normalize("NFC", s or "").lower().strip()


def fold(s):
    """Lowercase + strip diacritics (mirrors the simulator's search match)."""
    nfd = unicodedata.normalize("NFD", s or "").lower()
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")


def words(name):
    return re.findall(r"[^\W_]+", nfc_lower(name), flags=re.UNICODE)


def initials(name):
    return "".join(w[0] for w in words(name) if w)


def classify_query(query, returned):
    """Classify one gold search query against its returned contacts.

    Returns (category, n_rule_hits) where n_rule_hits counts returned entries
    matching by the fired rule (for single-hit analysis). Categories:
    empty, exact, first_word, initials, substring, cross_word_substring,
    relation, phone, nomatch, other.
    """
    q = query or ""
    if not q.strip():
        return "empty", len(returned)
    qn, qf = nfc_lower(q), fold(q)
    q_words = words(q)
    if not returned:
        return "nomatch", 0
    # exact full name
    hits = [c for c in returned if nfc_lower(c["name"]) == qn]
    if hits:
        return "exact", len(hits)
    # first word of a multi-word name (a first-name reference, NOT abbrev)
    if len(q_words) == 1:
        hits = [c for c in returned
                if len(words(c["name"])) > 1 and words(c["name"])[0] == qn]
        if hits:
            return "first_word", len(hits)
    # initials (spaces removed)
    q_nospace = re.sub(r"\s+", "", qn)
    if len(q_nospace) >= 2:
        hits = [c for c in returned if initials(c["name"]) == q_nospace]
        if hits:
            return "initials", len(hits)
    # proper substring of a name word (folded, like the simulator matches)
    if len(q_words) == 1 and len(qf) >= 2:
        hits = [c for c in returned
                if any(qf in fold(w) and qf != fold(w)
                       for w in words(c["name"]))]
        if hits:
            return "substring", len(hits)
    # cross-word substring of the full folded name
    hits = [c for c in returned if qf in fold(c["name"]) and qf != fold(c["name"])]
    if hits:
        return "cross_word_substring", len(hits)
    # relation / phone matches (the tool matches these fields too)
    hits = [c for c in returned
            if qf and qf in fold(c.get("relation", ""))]
    if hits:
        return "relation", len(hits)
    hits = [c for c in returned if q and q in (c.get("phone") or "")]
    if hits:
        return "phone", len(hits)
    return "other", len(returned)


def duplicates_in(returned):
    """Groups of same normalized name with >1 distinct id."""
    by_name = collections.defaultdict(set)
    for c in returned:
        by_name[nfc_lower(c["name"])].add(c["id"])
    return {name: sorted(ids) for name, ids in by_name.items()
            if len(ids) > 1}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train-jsonl", required=True)
    ap.add_argument("--data-root", required=True)
    ap.add_argument("--out-json", default=None)
    args = ap.parse_args()

    train_dir = str(Path(args.train_jsonl).resolve().parent)
    sys.path.insert(0, train_dir)
    from zaic_tools import ToolEnv

    samples = [json.loads(l) for l in open(args.train_jsonl, encoding="utf-8")
               if l.strip()]
    c = collections.Counter()
    size_dist = collections.Counter()
    query_cat = collections.Counter()
    abbrev_single_hit = collections.Counter()  # category -> single-hit count
    abbrev_used_correct = collections.Counter()
    abbrev_total = collections.Counter()
    dup_searches = []
    full_book_dup_samples = []
    used_in_returned = collections.Counter()
    search_then_use = 0
    gold_formats = collections.Counter()
    contacts_update_samples = 0
    calibration_triples = []  # (query, candidates, gold_used_id or None)

    for s in samples:
        gold = (s.get("label") or {}).get("tool_calls", []) or []
        for g in gold:
            if g.get("name") == "contacts.update":
                contacts_update_samples += 1
                break
        for g in gold:
            for k, v in (g.get("arguments") or {}).items():
                if k == "amount":
                    gold_formats[f"amount:{type(v).__name__}"] += 1
                if k in ("time", "start", "end"):
                    vstr = str(v)
                    if re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}.*", vstr):
                        gold_formats[f"{k}:datetime"] += 1
                    elif re.fullmatch(r"\d{4}-\d{2}-\d{2}", vstr):
                        gold_formats[f"{k}:date_only"] += 1
                    else:
                        gold_formats[f"{k}:other"] += 1
                if k == "date":
                    vstr = str(v)
                    if re.fullmatch(r"\d{4}-\d{2}(-\d{2})?", vstr):
                        gold_formats[f"date:iso"] += 1
                    else:
                        gold_formats[f"date:other"] += 1
        search_idx = [i for i, g in enumerate(gold)
                      if g.get("name") == "contacts.search"]
        if not search_idx:
            continue
        c["samples_with_gold_search"] += 1
        env = ToolEnv("train", s["id"], root=args.data_root)
        for si in search_idx:
            g = gold[si]
            query = (g.get("arguments") or {}).get("query")
            res = env.call("contacts.search", g.get("arguments") or {})
            returned = []
            if isinstance(res, dict) and res.get("ok"):
                for ct in res.get("contacts", []) or []:
                    returned.append({"id": ct.get("id"), "name": ct.get("name"),
                                     "relation": ct.get("relation")})
            c["gold_searches_replayed"] += 1
            size_dist[len(returned)] += 1
            cat, n_hits = classify_query(query, returned)
            query_cat[cat] += 1
            dups = duplicates_in(returned)
            if dups:
                c["searches_with_duplicate_in_returned"] += 1
                dup_searches.append({"sample": s["id"], "query": query,
                                     "dups": dups})
            if cat == "empty" and dups:
                full_book_dup_samples.append(s["id"])
            # First gold contact_id AFTER this search (search-then-use).
            used_id = None
            for later in gold[si + 1:]:
                if "contact_id" in (later.get("arguments") or {}):
                    used_id = later["arguments"]["contact_id"]
                    break
            if used_id is not None:
                search_then_use += 1
                ids = {ct["id"] for ct in returned}
                used_in_returned["used_in_returned" if used_id in ids
                                 else "used_NOT_in_returned"] += 1
            calibration_triples.append(
                {"sample": s["id"], "query": query,
                 "candidates": returned, "gold_used_id": used_id})
            if cat in ("initials", "substring", "cross_word_substring"):
                abbrev_total[cat] += 1
                if n_hits == 1:
                    abbrev_single_hit[cat] += 1
                    if used_id is not None:
                        hit_id = [ct["id"] for ct in returned
                                  if _rule_hit(cat, query, ct)][0]
                        if hit_id == used_id:
                            abbrev_used_correct[cat] += 1
        # end searches
    out = {
        "n_samples": len(samples),
        "counts": dict(c),
        "returned_size_distribution": {str(k): v
                                       for k, v in sorted(size_dist.items())},
        "query_categories": dict(query_cat),
        "searches_with_duplicate_in_returned": len(dup_searches),
        "full_book_empty_query_dup_samples": len(full_book_dup_samples),
        "search_then_use_pairs": search_then_use,
        "used_in_returned": dict(used_in_returned),
        "abbrev_total": dict(abbrev_total),
        "abbrev_single_hit": dict(abbrev_single_hit),
        "abbrev_single_hit_resolves_to_gold_used": dict(abbrev_used_correct),
        "contacts_update_samples": contacts_update_samples,
        "gold_formats": dict(gold_formats),
        "calibration_triples": calibration_triples,
        "method_notes": [
            "Every roster observation comes from ToolEnv('train', id).call("
            "'contacts.search', gold_args) -- the official runtime path. No "
            "train_environment/ or state.json file was opened directly.",
            "Returned lists are search MATCHES, not whole rosters, so "
            "duplicate counts are lower bounds -- except empty-query "
            "searches, which return the whole address book.",
            "Phones are dropped from stored records.",
            "Contacts roster is static within a sample (search is a read; "
            "contacts.update appears in gold only in the counted samples), "
            "so replaying searches on the initial state is faithful for "
            "roster measurement.",
        ],
    }
    text = json.dumps(out, ensure_ascii=False, indent=2)
    if args.out_json:
        with open(args.out_json, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    # Print everything except the (large) calibration triples.
    short = {k: v for k, v in out.items() if k != "calibration_triples"}
    short["calibration_triples_n"] = len(calibration_triples)
    print(json.dumps(short, ensure_ascii=False, indent=2))
    return 0


def _rule_hit(cat, query, contact):
    qn, qf = nfc_lower(query), fold(query)
    if cat == "initials":
        return initials(contact["name"]) == re.sub(r"\s+", "", qn)
    if cat == "substring":
        return any(qf in fold(w) and qf != fold(w)
                   for w in words(contact["name"]))
    if cat == "cross_word_substring":
        return qf in fold(contact["name"]) and qf != fold(contact["name"])
    return False


if __name__ == "__main__":
    sys.exit(main())
