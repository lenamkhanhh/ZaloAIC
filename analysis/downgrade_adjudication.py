#!/usr/bin/env python3
"""Adjudicate the Round 10 -> fix-round DAG coverage change (355 -> 284).

Joins the round-10 audit JSON (OLD) with the fix-round audit JSON (NEW)
by (sample, tool, slot) in order, and classifies every PROVEN ->
UNPROVEN / PROVEN -> AMBIGUOUS downgrade as either:

  invalid-old-proof: the old proof violated a principle the fix round
    made explicit (whole-span numbers, typed DATE/TIME/DATETIME,
    field/entity-typed observations, roster intent, history linkage,
    recursively proven offset/duration parents). The classification
    follows from the RULE DIFF between the two code versions, not from
    the new verdict alone: each mapping below names the exact semantic
    change that can only remove proofs of that class.
  window-artifact: the proof was valid but the evidence window changed
    (must be 0: the new per-write prefix windows are supersets of the
    old before-first-write window, and history windows are unchanged).
  unclassified: anything not matching a mapping -- printed for manual
    review; the report must NOT claim "all downgrades were false
    proofs" unless this bucket is empty.

PROVEN -> PROVEN rule changes (re-attributions) are counted separately:
they are not downgrades -- the value stays proven, via a different,
valid mechanism (e.g. an invalid same-app observation replaced by a
genuine offset derivation).

Usage:
  python3 analysis/downgrade_adjudication.py \
    --old ~/workspace/round10-base/e7_dag_audit_OLD.json \
    --new /tmp/e7_dag_audit_NEW.json
Exit code 0 iff the unclassified bucket is empty.
"""

import argparse
import collections
import json
import sys


def classify(old_rule, new_rule, new_detail):
    """Return (bucket, principle) for one downgrade."""
    if old_rule == "observation":
        if new_rule == "observation_cross_app":
            return ("invalid-old-proof",
                    "cross-app scalar equality (same value, other app)")
        if new_rule in ("roster_no_intent", "roster_ambiguous"):
            return ("invalid-old-proof",
                    "contact proven by same-app observation scalar; "
                    "contacts need roster + exclusive intent")
        if new_rule == "history_reference":
            return ("invalid-old-proof",
                    "same-app scalar proof masking an ambiguous "
                    "history reference (multiple candidates, no "
                    "unique link)")
        if new_rule == "none":
            return ("invalid-old-proof",
                    "same-app scalar equality ignoring field, entity "
                    "and source typing (balance/other-entity/unknown "
                    "source)")
        return ("unclassified",
                "observation -> %s" % new_rule)
    if old_rule == "relative_date" and new_rule == "observation_cross_app":
        return ("invalid-old-proof",
                "old relative-date proof with no time span in the "
                "current text; the value exists only in another app's "
                "result (unlinked history value)")
    if old_rule == "datetime_assembly" and new_rule == "none":
        return ("invalid-old-proof",
                "cross-text / unlinked assembly (bare linker, parts of "
                "complete spans, history texts)")
    if old_rule == "relative_date" and new_rule == "none":
        return ("invalid-old-proof",
                "date-only span promoted to midnight datetime (typed "
                "DATE/TIME/DATETIME dispatch; the only relative_date "
                "semantic change that removes proofs)")
    if old_rule == "roster" and new_rule in ("roster_no_intent",
                                             "roster_ambiguous"):
        return ("invalid-old-proof",
                "roster existence without exclusive intent mention "
                "(no-intent / duplicate-name)")
    if old_rule in ("number_words", "number_digits") and new_rule == "none":
        return ("invalid-old-proof",
                "substring / phone / identifier-digit span (whole-span "
                "boundary + phone/id skip)")
    if old_rule == "duration" and new_rule == "none":
        return ("invalid-old-proof",
                "duration from an unproven start (recursive parent "
                "requirement)")
    if old_rule == "offset" and new_rule == "none":
        return ("invalid-old-proof",
                "offset from an unlinked, failed or unproven base "
                "(entity-link + succeeded + recursive proof)")
    if old_rule == "supersede" and new_rule == "none":
        return ("invalid-old-proof",
                "supersede without succeeded/cancel-correct history "
                "handling")
    return ("unclassified", "%s -> %s (%s)"
            % (old_rule, new_rule, new_detail))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", required=True)
    ap.add_argument("--new", required=True)
    args = ap.parse_args()
    old = json.load(open(args.old))["rows"]
    new = json.load(open(args.new))["rows"]
    assert len(old) == len(new), (len(old), len(new))
    for o, n in zip(old, new):
        assert (o["sample"], o["tool"], o["slot"]) == \
            (n["sample"], n["tool"], n["slot"]), (o, n)
    buckets = collections.Counter()
    principles = collections.Counter()
    downgrades = []
    reattr = collections.Counter()
    for o, n in zip(old, new):
        if o["dag_status"] == "PROVEN" and n["dag_status"] == "PROVEN":
            if o["dag_rule"] != n["dag_rule"]:
                reattr["%s -> %s" % (o["dag_rule"], n["dag_rule"])] += 1
            continue
        if o["dag_status"] != "PROVEN" or n["dag_status"] == "PROVEN":
            continue
        bucket, principle = classify(o["dag_rule"], n["dag_rule"],
                                     n.get("dag_detail", ""))
        buckets[bucket] += 1
        principles["%s | %s" % (o["dag_rule"], principle)] += 1
        downgrades.append((o, n, bucket, principle))
    print("downgrades PROVEN -> UNPROVEN/AMBIGUOUS:",
          sum(buckets.values()))
    print("buckets:", dict(buckets))
    print("by old rule + principle:")
    for k, v in sorted(principles.items()):
        print("  %d  %s" % (v, k))
    print("re-attributions PROVEN -> PROVEN (rule changed, verdict kept):")
    for k, v in sorted(reattr.items()):
        print("  %d  %s" % (v, k))
    bad = [d for d in downgrades if d[2] == "unclassified"]
    if bad:
        print("UNCLASSIFIED (manual review required):")
        for o, n, _, principle in bad:
            print("  %s %s %s %s: %s -> %s (%s)" % (
                o["sample"], o["tool"], o["slot"], o["value"],
                o["dag_rule"], n["dag_rule"], principle))
        return 1
    print("unclassified: 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
