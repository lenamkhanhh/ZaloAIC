#!/usr/bin/env python3
"""Fix round: rerun the E7 shadow audit with the fixed prover.

Scope is IDENTICAL to round 10 (dev gold calls that are mutating
writes -- not read-verbs, not sys.ask_missing_info -- with >= 1
monitored argument; 479 writes / 556 arguments expected), but the
evidence construction changed in three documented ways:

1. Structured observations. Tool results are flattened to
   (tool, field, value, entity) quadruples (field = leaf dict key,
   entity = the enclosing dict's id/event_id/alarm_id/reminder_id,
   inherited through nesting). Phones are dropped. Legacy
   (tool, scalar) pairs and plain scalars are gone: an observation
   without a field/app/entity can no longer prove anything.
2. Split evidence windows. Same-sample replay observations are
   turn_observations (reads before the audited write, in trajectory
   order); history results are history_observations. Round 10
   concatenated them; the fixed prover treats them differently
   (see the prover docstring for the exact per-source rules).
3. Trajectory-faithful replay. Gold calls are replayed IN ORDER
   through ToolEnv (reads AND writes), so later reads see post-write
   state and every prior call carries a real succeeded flag
   (result ok True and done is not False). Round 10 replayed reads
   only, from initial state, and gave every prior call an unknown
   outcome. History calls pair with their recorded results
   (ok True, no done key -> succeeded); unpaired calls -> False.

BASELINE CAVEAT: the baseline is the narrow rule set (verbatim +
observation + roster) under the NEW strict semantics -- verbatim is
strings-only, observations are field/entity-typed, roster needs an
intent mention. Round 10's baseline numbers were inflated by the same
bugs this round fixes, so baseline_old vs baseline_new is itself a
finding, not a regression to explain away. Conversion is still
DAG - baseline on THIS scope, with identical evidence.

SANCTIONED ACCESS ONLY: every environment observation comes from
``zaic_tools.ToolEnv(...).call(...)`` -- the official runtime path.
This script NEVER opens train_environment/ or state.json directly.
Phones are dropped from stored records (only id/name are kept).
Audit JSON is written locally only (default /tmp) and is never pushed.

Usage:
  python3 analysis/e7_dag_shadow_audit.py \
      --train-jsonl <train.jsonl> --data-root <dir containing train/> \
      --split lifemate/splits/train_dev_heldout.json \
      [--out-json /tmp/e7_dag_audit.json]
"""

import argparse
import collections
import json
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lifemate"))
from lifemate_provenance import (  # noqa: E402
    Evidence, prove_argument, find_number_spans)

MONITORED = ("time", "date", "start", "end", "amount", "contact_id")
READ_VERBS = ("search", "list", "get", "status", "forecast", "balance",
              "history", "detail")
BASELINE_RULES = ["verbatim", "observation", "roster"]
ID_KEYS = ("id", "event_id", "alarm_id", "reminder_id")


def nfc_lower(s):
    return unicodedata.normalize("NFC", s or "").lower().strip()


def is_read(name, kind_by_tool=None):
    """Read classification: catalog kind wins when a kind map is
    supplied (a verb-name list misclassifies 14 catalog reads,
    e.g. email.read, sms.read_recent, chat_ott.read_chat -- reviewer
    finding 8-V); otherwise the verb list is the fallback."""
    if kind_by_tool is not None and name in kind_by_tool:
        return kind_by_tool[name] == "read"
    verb = (name or "").split(".", 1)[1] if "." in (name or "") else ""
    return any(verb == v or verb.startswith(v + "_") for v in READ_VERBS)


def load_kind_map(train_dir):
    """{tool name: kind} from train_tools_catalog.json, or {} when
    the catalog is unavailable (caller falls back to verb list)."""
    try:
        cat = json.load(open(str(Path(train_dir)
                               / "train_tools_catalog.json")))
        kinds = {}
        for app in cat.get("apps", []):
            for tool in app.get("tools", []):
                if isinstance(tool.get("name"), str):
                    kinds[tool["name"]] = tool.get("kind", "")
        return kinds
    except Exception:
        return {}


def succeeded(result):
    """Contract: ok True AND done is not False (missing done counts
    as not-False, matching recorded history results which carry ok
    only). Non-dict results are not successes."""
    return isinstance(result, dict) and result.get("ok") is True \
        and result.get("done") is not False


def flatten_observations_with_field(result, tool, out, entity=None):
    """Same as flatten_observations but keeps the leaf key as field.

    (The plain flattener above loses the key when recursing into a
    scalar; this variant threads it through.)
    """
    if isinstance(result, dict):
        ent = entity
        for key in ID_KEYS:
            if isinstance(result.get(key), str):
                ent = result[key]
                break
        for key, value in result.items():
            if key == "phone":
                continue
            if isinstance(value, dict):
                flatten_observations_with_field(value, tool, out, ent)
            elif isinstance(value, list):
                for item in value:
                    flatten_observations_with_field(item, tool, out, ent)
            elif isinstance(value, (str, int, float)) \
                    and not isinstance(value, bool):
                out.append((tool, key, value, ent))
    elif isinstance(result, list):
        for value in result:
            flatten_observations_with_field(value, tool, out, entity)
    elif isinstance(result, (str, int, float)) \
            and not isinstance(result, bool):
        out.append((tool, None, result, entity))


def collect_events(result, tool, out):
    """Collect event-like dicts (id + start/time/end) from a result."""
    if isinstance(result, dict):
        keys = set(result.keys())
        if keys & {"id", "event_id", "alarm_id", "reminder_id"} \
                and keys & {"start", "time", "end"}:
            out.append((tool, result))
        for key, value in result.items():
            if key == "phone":
                continue
            collect_events(value, tool, out)
    elif isinstance(result, list):
        for value in result:
            collect_events(value, tool, out)


def flatten_scalars(obj, out):
    # Phones are dropped (never provenance evidence for monitored args).
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == "phone":
                continue
            flatten_scalars(value, out)
    elif isinstance(obj, list):
        for value in obj:
            flatten_scalars(value, out)
    elif isinstance(obj, (str, int, float)) and not isinstance(obj, bool):
        out.append(obj)


def collect_rosters_from_results(results, out):
    if isinstance(results, dict):
        contacts = results.get("contacts")
        if isinstance(contacts, list):
            for entry in contacts:
                if isinstance(entry, dict) and entry.get("id"):
                    out.append({"id": entry["id"],
                                "name": entry.get("name", ""),
                                "phone": entry.get("phone", "")})
        for value in results.values():
            collect_rosters_from_results(value, out)
    elif isinstance(results, list):
        for value in results:
            collect_rosters_from_results(value, out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train-jsonl", required=True)
    ap.add_argument("--data-root", required=True)
    ap.add_argument("--split", required=True)
    ap.add_argument("--out-json", default="/tmp/e7_dag_audit.json")
    args = ap.parse_args()

    split = json.load(open(args.split))
    dev_ids = {k for k, v in split.items() if v == "dev"}
    train_dir = str(Path(args.train_jsonl).resolve().parent)
    kinds = load_kind_map(train_dir)
    kind_source = "catalog" if kinds else "verb_fallback"
    sys.path.insert(0, train_dir)
    from zaic_tools import ToolEnv  # noqa: E402

    rows = []
    n_samples = 0
    n_writes = 0
    for line in open(args.train_jsonl):
        s = json.loads(line)
        if s["id"] not in dev_ids:
            continue
        n_samples += 1
        gold = s["label"]["tool_calls"]
        anchor = (s.get("context") or {}).get("current_time")
        current_text = s.get("audio_text", "")
        hist_user = [h.get("audio_text", "") for h in s.get("history", [])
                     if h.get("role") == "user"]
        hist_obs = []
        hist_events = []
        hist_rosters = []
        hist_call_args = []
        for h in s.get("history", []):
            if h.get("role") != "assistant":
                continue
            calls = h.get("tool_calls") or []
            results = h.get("tool_results") or []
            for idx, call in enumerate(calls):
                res = results[idx] if idx < len(results) else None
                hist_call_args.append((call.get("name"),
                                       call.get("arguments") or {},
                                       succeeded(res)))
            for call, res in zip(calls, results):
                flatten_observations_with_field(
                    res, call.get("name"), hist_obs)
                collect_events(res, call.get("name"), hist_events)
                collect_rosters_from_results(res, hist_rosters)
            for res in results[len(calls):]:
                flatten_observations_with_field(res, None, hist_obs)
                collect_events(res, None, hist_events)
                collect_rosters_from_results(res, hist_rosters)
        # Trajectory-faithful replay through ToolEnv: gold calls in
        # order (reads AND writes), so later reads see post-write
        # state and every prior call carries a real succeeded flag.
        # Per audited write, prefix evidence = reads before its
        # position; rosters from contacts.search at any earlier
        # position (names/ids are static within a sample).
        env = ToolEnv("train", s["id"], root=args.data_root)
        replay = []  # (call, succeeded, result) per gold position
        for call in gold:
            try:
                res = env.call(call.get("name"),
                               call.get("arguments") or {})
            except Exception:
                res = None
            replay.append((call, succeeded(res), res))
        # Monitored writes, in gold order.
        for pos, call in enumerate(gold):
            name = call.get("name", "")
            if is_read(name, kinds) or name == "sys.ask_missing_info":
                continue
            call_args = call.get("arguments") or {}
            slots = [k for k in MONITORED if k in call_args]
            if not slots:
                continue
            n_writes += 1
            prefix_obs = []
            prefix_events = []
            sample_rosters = []
            prior_call_args = []
            for idx, (pcall, psucc, pres) in enumerate(replay[:pos]):
                prior_call_args.append((pcall.get("name"),
                                        pcall.get("arguments") or {},
                                        psucc))
                if not is_read(pcall.get("name", ""), kinds):
                    continue
                if pcall.get("name") == "contacts.search" \
                        and isinstance(pres, dict) and pres.get("ok"):
                    for entry in pres.get("contacts") or []:
                        if isinstance(entry, dict) and entry.get("id"):
                            sample_rosters.append(
                                {"id": entry["id"],
                                 "name": entry.get("name", ""),
                                 "phone": entry.get("phone", "")})
                flatten_observations_with_field(
                    pres, pcall.get("name"), prefix_obs)
                collect_events(pres, pcall.get("name"), prefix_events)
            rosters = list(hist_rosters) + sample_rosters
            evidence = Evidence(
                current_text=current_text,
                history_user_texts=hist_user,
                turn_observations=prefix_obs,
                history_observations=hist_obs,
                history_call_args=hist_call_args,
                rosters=rosters,
                observation_events=list(hist_events) + list(prefix_events),
                prior_call_args=prior_call_args,
                anchor=anchor,
                defaults={})
            for slot in slots:
                value = call_args[slot]
                dag = prove_argument(slot, value, name, evidence,
                                     call_args=call_args)
                base = prove_argument(slot, value, name, evidence,
                                      rules=BASELINE_RULES,
                                      call_args=call_args)
                rows.append({
                    "sample": s["id"], "tool": name, "slot": slot,
                    "value": value,
                    "dag_status": dag.status, "dag_rule": dag.rule,
                    "dag_detail": dag.detail,
                    "base_status": base.status, "base_rule": base.rule,
                    "base_detail": base.detail,
                    "context": s.get("context") or {},
                    "current_text": current_text,
                })

    # ---- aggregate -------------------------------------------------------
    dag_proven = collections.Counter()
    base_proven = 0
    dag_status = collections.Counter()
    value_args = [r for r in rows if r["slot"] != "contact_id"]
    contact_args = [r for r in rows if r["slot"] == "contact_id"]
    for r in rows:
        dag_status[r["dag_status"]] += 1
        if r["dag_status"] == "PROVEN":
            dag_proven[r["dag_rule"]] += 1
        if r["base_status"] == "PROVEN":
            base_proven += 1
    dag_value_proven = sum(1 for r in value_args
                           if r["dag_status"] == "PROVEN")
    base_value_proven = sum(1 for r in value_args
                            if r["base_status"] == "PROVEN")
    dag_contact_proven = sum(1 for r in contact_args
                             if r["dag_status"] == "PROVEN")
    base_contact_proven = sum(1 for r in contact_args
                              if r["base_status"] == "PROVEN")

    # ---- residuals for still-UNPROVEN args ------------------------------
    residual = collections.Counter()
    for r in rows:
        if r["dag_status"] != "UNPROVEN":
            continue
        value = r["value"]
        if r["dag_rule"] in ("observation_cross_app",
                             "observation_unknown_source",
                             "observation_field_mismatch"):
            residual["observation blocked: " + r["dag_rule"]] += 1
            continue
        if r["dag_rule"] == "roster_no_intent":
            residual["contact in roster, no intent mention"] += 1
            continue
        if r["dag_rule"] == "roster_ambiguous":
            residual["contact ambiguous in roster"] += 1
            continue
        ctx = r["context"]
        ctx_values = []
        flatten_scalars(ctx.get("user_profile") or {}, ctx_values)
        if value in ctx_values:
            residual["context user_profile"] += 1
            continue
        if isinstance(value, (int, float)) \
                and not isinstance(value, bool):
            span_values = [v for _, v in find_number_spans(
                r["current_text"])]
            if value in span_values:
                residual["digit span in request (unparsed form)"] += 1
                continue
        if isinstance(value, str) and value[:10] in r["current_text"]:
            residual["ISO date substring in request"] += 1
            continue
        residual["no source found"] += 1

    summary = {
        "scope_note": "Reproducible scope: dev gold calls whose catalog "
                      "kind is write (round 3: kind classification; "
                      "earlier rounds used a verb-name list that "
                      "misclassified 14 catalog reads as writes) with "
                      ">= 1 monitored arg, excluding "
                      "sys.ask_missing_info. E7 original scope "
                      "(459 writes / 511 args, 31 ALLOW + 428 UNKNOWN) "
                      "came from Codex guard code not in this repo and "
                      "cannot be reproduced exactly; conversion is "
                      "therefore measured as DAG - baseline on THIS "
                      "scope. Fix-round changes vs round 10: structured "
                      "(tool, field, value, entity) observations, split "
                      "turn/history evidence windows, trajectory-faithful "
                      "replay with real succeeded flags, per-write prefix "
                      "windows. Baseline is the narrow rule set under the "
                      "NEW strict semantics, so baseline_old vs baseline_new "
                      "is itself a finding.",
        "kind_classification": kind_source,
        "dev_samples": n_samples,
        "monitored_writes": n_writes,
        "monitored_args": len(rows),
        "value_args": len(value_args),
        "contact_args": len(contact_args),
        "dag_status": dict(dag_status),
        "dag_proven_by_rule": dict(dag_proven),
        "baseline_proven_total": base_proven,
        "dag_proven_total": sum(dag_proven.values()),
        "conversion_total": sum(dag_proven.values()) - base_proven,
        "value_args_dag_proven": dag_value_proven,
        "value_args_baseline_proven": base_value_proven,
        "value_args_conversion": dag_value_proven - base_value_proven,
        "contact_args_dag_proven": dag_contact_proven,
        "contact_args_baseline_proven": base_contact_proven,
        "contact_args_conversion": dag_contact_proven - base_contact_proven,
        "residual_unproven_breakdown": dict(residual),
    }
    json.dump({"summary": summary, "rows": [
        {k: v for k, v in r.items()
         if k not in ("context", "current_text")}
        for r in rows]}, open(args.out_json, "w"), ensure_ascii=False)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
