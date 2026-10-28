#!/usr/bin/env python3
"""Round 10: rerun the E7 shadow audit with the Provenance DAG prover.

Replaces E7's narrow verbatim guard with the Round 10 DAG (verbatim +
number words + relative dates + observations + rosters + history
references + supersession + datetime assembly + declared defaults) on the
same conceptual scope: dev gold writes carrying time/date/start/end/
amount/contact_id arguments.

SCOPE NOTE (read before quoting numbers): E7's original scope (459
monitored writes / 511 arguments, 31 ALLOW + 428 UNKNOWN) came from
Codex's guard code, which is not in this repo, so its exact scope
definition cannot be reproduced here. This script therefore defines its
scope explicitly and reproducibly -- dev gold calls that are mutating
writes (not read-verbs, not sys.ask_missing_info) with >= 1 monitored
argument -- which yields 479 writes / 556 arguments on the same dev
split. To keep the conversion claim honest, the script runs TWO provers
on the IDENTICAL scope and evidence:
  * baseline: verbatim + observation + roster rules only (the narrow
    guard class E7 used), and
  * DAG: the full Round 10 rule set.
Conversion = DAG_PROVEN - baseline_PROVEN on this scope. E7's 31/428 is
reported alongside as the reference point, not as this run's denominator.

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
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lifemate"))
from lifemate_provenance import Evidence, prove_argument  # noqa: E402

MONITORED = ("time", "date", "start", "end", "amount", "contact_id")
READ_VERBS = ("search", "list", "get", "status", "forecast", "balance",
              "history", "detail")
BASELINE_RULES = ["verbatim", "observation", "roster"]


def nfc_lower(s):
    return unicodedata.normalize("NFC", s or "").lower().strip()


def is_read(name):
    verb = (name or "").split(".", 1)[1] if "." in (name or "") else ""
    return any(verb == v or verb.startswith(v + "_") for v in READ_VERBS)


def flatten_observations(result, tool, out):
    """Flatten a tool result into (tool, scalar) observation entries.

    Phones are dropped (never provenance evidence for monitored args).
    """
    if isinstance(result, dict):
        for key, value in result.items():
            if key == "phone":
                continue
            flatten_observations(value, tool, out)
    elif isinstance(result, list):
        for value in result:
            flatten_observations(value, tool, out)
    elif isinstance(result, (str, int, float)) \
            and not isinstance(result, bool):
        out.append((tool, result))


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
                                "name": entry.get("name", "")})
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
            for call in calls:
                hist_call_args.append((call.get("name"),
                                       call.get("arguments") or {}))
            for call, res in zip(calls, results):
                flatten_observations(res, call.get("name"), hist_obs)
                collect_events(res, call.get("name"), hist_events)
                collect_rosters_from_results(res, hist_rosters)
            for res in results[len(calls):]:
                flatten_observations(res, None, hist_obs)
                collect_events(res, None, hist_events)
                collect_rosters_from_results(res, hist_rosters)
        # Same-sample replay through ToolEnv: reads only (writes skipped,
        # so no state is mutated by this audit). Reads before the first
        # gold write are PROVEN-eligible prefix observations; later reads
        # are kept for residual analysis only. contacts.search rosters are
        # safe at any position (contact names/ids are static).
        env = ToolEnv("train", s["id"], root=args.data_root)
        first_write_idx = None
        for idx, call in enumerate(gold):
            if not is_read(call.get("name", "")) \
                    and call.get("name") != "sys.ask_missing_info":
                first_write_idx = idx
                break
        if first_write_idx is None:
            first_write_idx = len(gold)
        prefix_obs = []
        prefix_events = []
        postwrite_values = []
        sample_rosters = []  # (position, entry)
        for idx, call in enumerate(gold):
            if not is_read(call.get("name", "")):
                continue
            try:
                res = env.call(call.get("name"),
                               call.get("arguments") or {})
            except Exception:
                continue
            if call.get("name") == "contacts.search" \
                    and isinstance(res, dict) and res.get("ok"):
                for entry in res.get("contacts") or []:
                    if isinstance(entry, dict) and entry.get("id"):
                        sample_rosters.append(
                            (idx, {"id": entry["id"],
                                   "name": entry.get("name", "")}))
            obs_entries = []
            flatten_observations(res, call.get("name"), obs_entries)
            ev_entries = []
            collect_events(res, call.get("name"), ev_entries)
            if idx < first_write_idx:
                prefix_obs.extend(obs_entries)
                prefix_events.extend(ev_entries)
            else:
                postwrite_values.extend([v for _, v in obs_entries])
        # Monitored writes, in gold order.
        for pos, call in enumerate(gold):
            name = call.get("name", "")
            if is_read(name) or name == "sys.ask_missing_info":
                continue
            call_args = call.get("arguments") or {}
            slots = [k for k in MONITORED if k in call_args]
            if not slots:
                continue
            n_writes += 1
            rosters = list(hist_rosters)
            rosters += [e for p, e in sample_rosters if p < pos]
            evidence = Evidence(
                current_text=current_text,
                history_user_texts=hist_user,
                history_observations=list(hist_obs) + list(prefix_obs),
                history_call_args=hist_call_args,
                rosters=rosters,
                observation_events=list(hist_events) + list(prefix_events),
                prior_call_args=[(c.get("name"), c.get("arguments") or {})
                                 for c in gold[:pos]],
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
                    "base_status": base.status, "base_rule": base.rule,
                    "postwrite_values": postwrite_values,
                    "context": s.get("context") or {},
                    "current_text": current_text,
                    "history_user_texts": hist_user,
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
        if r["dag_rule"] == "observation_cross_app":
            residual["cross-app observation candidate"] += 1
            continue
        if any(v == value for v in r["postwrite_values"]):
            residual["post-write same-sample read"] += 1
            continue
        ctx = r["context"]
        ctx_values = []
        flatten_scalars(ctx.get("user_profile") or {}, ctx_values)
        if value in ctx_values:
            residual["context user_profile"] += 1
            continue
        if isinstance(value, str) and value[:10] in r["current_text"]:
            residual["date substring in request (unparsed form)"] += 1
            continue
        if isinstance(value, (int, float)) \
                and str(int(value)) in r["current_text"]:
            residual["digit substring in request (unparsed form)"] += 1
            continue
        residual["no source found"] += 1

    summary = {
        "scope_note": "Reproducible scope: dev gold writes (not read-verbs, "
                      "not sys.ask_missing_info) with >= 1 monitored arg. "
                      "E7 original scope (459 writes / 511 args, 31 ALLOW + "
                      "428 UNKNOWN) came from Codex guard code not in this "
                      "repo and cannot be reproduced exactly; conversion is "
                      "therefore measured as DAG - baseline on THIS scope.",
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
         if k not in ("postwrite_values", "context", "current_text",
                      "history_user_texts")}
        for r in rows]}, open(args.out_json, "w"), ensure_ascii=False)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
