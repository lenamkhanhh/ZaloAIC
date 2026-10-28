#!/usr/bin/env python3
"""Mixed-trace shadow: prover + Gate 2 over saved model proposals (v2).

Generalization of the round-2 E5 V13 script (which asserted every
sample's gold is a single sys.ask_missing_info). This version handles
gold write, gold read, gold ask, and gold empty, and proposal kinds
wrong action / wrong reference / wrong argument / missing slot /
invalid format, while keeping V13 as a regression control: run on the
V13 trace, the guard decisions must reproduce round 2 exactly
(29 write proposals, 16 monitored calls, 19 monitored args,
blocked 16 / passed 6 / out-of-scope-guard 7).

NEVER merge versions/arms into one opaque metric: one run = one trace
file (--version labels it, e.g. v10/v11/v13); summaries are per file.
A paired old-vs-new comparison re-runs the identical inputs (same
row keys: version/sample/arm/generation_index/call) after a guard
change and diffs rows by key.

CAUSAL PREFIX (identical to round 2 -- the evidence a guard would
actually have at the proposal's turn, nothing else):
  * current text: the trace's model_current_transcript (what the
    model received, NOT the gold audio_text);
  * history user texts: the trace's history_asr values, in u-number
    order (what the model received, NOT gold history transcripts);
  * history tool records: the sample's ORIGINAL history assistant
    tool_calls/tool_results (the input the trajectory started from);
  * turn observations / turn priors / rosters: trace tool events
    strictly BEFORE the proposal's generation event in the same trace
    (reads become turn observations; every event becomes a PriorCall
    with its recorded result and succeeded flag);
  * NEVER: the current proposal, rejected proposals, future tool
    results, or gold/label values (gold is used ONLY for external
    adjudication, never fed into evidence).

HISTORY PARSING GUARD (new in v2): history tool_results are expected
as a list aligned with tool_calls. A repr-string form (or any other
non-list, non-None form) is NOT silently zipped -- it is parsed with
json.loads, then ast.literal_eval, and if neither yields a list it is
recorded as missing evidence for that sample (parse note in the
output) and the affected calls contribute no observation and no
succeeded flag. Any sample with missing history evidence has ALL its
proposals adjudicated "insufficient_evidence" (the guard decision is
still computed and reported, so the row stays usable for the paired
re-run). Checked on this data: train.jsonl history tool_results are
list (2981 turns) or None (510 turns, all paired with no calls) --
zero repr-string cases in the full file, so the guard never fires
here; it exists so a future string form cannot silently lose
evidence through a parse failure.

GUARD DECISION (unchanged from round 2 -- this is what the paired
comparison diffs):
  * blocked: Gate 2 fired, or any monitored arg UNPROVEN/AMBIGUOUS;
  * passed: not blocked, and (monitored args present OR Gate 2
    applicable);
  * out-of-scope-guard: not blocked, no monitored args, Gate 2 not
    applicable (a missing slot / free-text / unmonitored-arg flaw
    belongs to a grammar, not to this guard).

ADJUDICATION (exactly one category per write proposal):
  * correct_block: guard blocked, proposal is not a correct call;
  * false_block: guard blocked, proposal IS a correct call with
    sufficient evidence (gold match or equivalent, prerequisites
    satisfied at the model prefix);
  * correct_pass: guard passed, proposal is a correct call;
  * miss: guard passed, proposal is not a correct call (guard scope
    limit, not necessarily a guard bug -- miss_reason says which);
  * out_of_scope: guard decision is out-of-scope-guard (correctness
    is still recorded separately in is_correct, so scope silence is
    never mistaken for correctness);
  * insufficient_evidence: sample history evidence is missing /
    unparseable, or gold equivalence is undecidable for a stated
    reason.
Rules enforced here: a gold-call match is NOT automatically a valid
positive -- the matched gold call's prerequisites (earlier gold
reads/searches, and earlier gold writes) must be satisfied at the
model prefix, else the proposal is "gold_match_but_prerequisite_
skipped" and NOT correct. A gold-divergent call is NOT automatically
wrong if an equivalent way exists -- equivalents are reported
separately (equivalent_to) and only a narrow no-op-extra-arg
equivalence is accepted (extra arg value equals the currently
observed value of that field for that entity in the prefix, e.g.
power:"on" for a device already observed on). UNPROVEN does NOT mean
hallucination (it means "no valid derivation found"). Gold ASK does
NOT mean every proposed argument is wrong (arg-level verdicts are
reported alongside the proposal-level action verdict).

Counts FIRST: precision/recall are computed ONLY over the adjudicated
subset (correct_block + false_block + correct_pass + miss), with
denominators stated explicitly. With very few positives the summary
says "insufficient evidence" instead of claiming safety.

DEFINITIONS (counted, not assumed):
  * generation: a generation event;
  * no-call generation: parsed is null;
  * parsed-call generation: parsed name present;
  * write proposal: a parsed generation whose catalog kind is write
    (sys.ask_missing_info is ask, __invalid__ is invalid -- neither
    is a write proposal);
  * monitored call: a write proposal carrying >= 1 monitored arg
    (time/date/start/end/amount/contact_id);
  * monitored argument: one monitored slot on one write proposal;
  * tool event: an executed call recorded in the trace;
  * independent positive: a DISTINCT sample with at least one
    correct (gold-match or equivalent, prerequisites satisfied)
    write proposal -- arms/versions of the same sample never count
    as independent evidence.

Usage:
  python3 analysis/model_trace_shadow.py \
    --trace analysis/runtime/e1_v10_diagnostic_trace.json \
    --version v10 \
    --train-jsonl <train/train.jsonl> \
    --split lifemate/splits/train_dev_heldout.json \
    --out-json /tmp/t2_v10_shadow.json
The trace file must already exist (branch history); this script never
writes trajectories and never touches the repo.
"""

import argparse
import ast
import collections
import importlib.util
import json
import re
import sys
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve()
FALLBACK_REPO = Path.home() / "workspace" / "zalo-aic-round3"

MONITORED = ("time", "date", "start", "end", "amount", "contact_id")


def resolve_lifemate_dir(explicit):
    if explicit:
        return Path(explicit)
    cand = HERE.parent.parent / "lifemate"
    if (cand / "lifemate_provenance.py").exists():
        return cand
    return FALLBACK_REPO / "lifemate"


def resolve_e7_path(explicit, lifemate_dir):
    if explicit:
        return Path(explicit)
    cand = HERE.parent / "e7_dag_shadow_audit.py"
    if cand.exists():
        return cand
    return FALLBACK_REPO / "analysis" / "e7_dag_shadow_audit.py"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def succeeded(result):
    return isinstance(result, dict) and result.get("ok") is True \
        and result.get("done") is not False


def u_number(key):
    m = re.search(r"_u(\d+)\.wav$", key or "")
    return int(m.group(1)) if m else 10 ** 9


def norm_text(text):
    nfkd = unicodedata.normalize("NFC", text or "").lower()
    kept = "".join(ch for ch in nfkd if ch.isalnum() or ch.isspace())
    return " ".join(kept.split())


def parse_tool_results(raw, sample_id, turn_idx):
    """Return (results_list_or_None, parse_note_or_None).

    Expected forms: list (aligned with tool_calls) or None (no
    calls). A string form is parsed, never zipped char-wise; an
    unparseable form yields (None, note) and the caller treats the
    sample's history evidence as missing.
    """
    if raw is None:
        return None, None
    if isinstance(raw, list):
        return raw, None
    if isinstance(raw, str):
        for parser in (json.loads, ast.literal_eval):
            try:
                parsed = parser(raw)
            except Exception:
                continue
            if isinstance(parsed, list):
                return parsed, (
                    "tool_results string form parsed (%s) sample %s "
                    "turn %d" % (parser.__name__, sample_id, turn_idx))
            return None, (
                "tool_results string form parsed to non-list "
                "sample %s turn %d" % (sample_id, turn_idx))
        return None, (
            "tool_results UNPARSEABLE string sample %s turn %d "
            "(evidence dropped, not silently zipped)" % (
                sample_id, turn_idx))
    return None, (
        "tool_results unexpected type %s sample %s turn %d" % (
            type(raw).__name__, sample_id, turn_idx))


def parsed_arguments(parsed):
    """Arguments dict for a generation's parsed call.

    Standard shape: {"name": ..., "arguments": {...}}. The V10 text
    arm also emits ask calls as {"name": ..., "tool_name": ...,
    "params": [...]} with no "arguments" key; those are ask-kind and
    never write proposals, but normalizing them keeps adjudication
    display honest instead of showing {}.
    """
    args = parsed.get("arguments")
    if isinstance(args, dict):
        return args
    if parsed.get("name") == "sys.ask_missing_info":
        synth = {}
        if parsed.get("tool_name") is not None:
            synth["tool_name"] = parsed["tool_name"]
        if parsed.get("params") is not None:
            synth["params"] = parsed["params"]
        return synth
    return {}


def is_reference_slot(key):
    return key == "contact_id" or key.endswith("_id")


def gold_classify(gold_calls, kind_of):
    """Gold shape for one sample (never used as guard evidence)."""
    writes = [c for c in gold_calls if kind_of(c.get("name")) == "write"]
    reads = [c for c in gold_calls if kind_of(c.get("name")) == "read"]
    asks = [c for c in gold_calls
            if c.get("name") == "sys.ask_missing_info"]
    if not gold_calls:
        kind = "empty"
    elif len(gold_calls) == 1 and asks:
        kind = "ask_only"
    elif writes:
        kind = "write"
    elif reads and not asks:
        kind = "read_only"
    else:
        kind = "mixed_no_write"
    return {"kind": kind, "writes": writes, "reads": reads,
            "asks": asks, "calls": gold_calls}


def check_prerequisites(matched_idx, gold_calls, kind_of,
                        prefix_names, prefix_search_queries,
                        prefix_executed_writes):
    """Prerequisites of gold_calls[matched_idx] at the model prefix.

    Read prerequisites: same tool name already in the prefix (for
    contacts.search, same normalized query). Write prerequisites:
    an identical (name, arguments) write already executed earlier in
    this trace. Returns (satisfied, missing_list). This is a
    deliberately lenient read check (name-only, not arg-equality:
    gold reads often carry {} while the model read carries a filter)
    -- the leniency is stated, not hidden.
    """
    missing = []
    for prior in gold_calls[:matched_idx]:
        pname = prior.get("name")
        pk = kind_of(pname)
        if pk == "read":
            if pname == "contacts.search":
                q = norm_text((prior.get("arguments") or {}).get("query", ""))
                if q not in prefix_search_queries:
                    missing.append("read:%s?%s" % (pname, q))
            elif pname not in prefix_names:
                missing.append("read:%s" % pname)
        elif pk == "write":
            key = (pname, json.dumps(prior.get("arguments") or {},
                                     sort_keys=True, ensure_ascii=False))
            if key not in prefix_executed_writes:
                missing.append("write:%s" % pname)
    return (not missing), missing


def no_op_equivalent(proposal_args, gold_args, prefix_entity_fields,
                       proposal_ref_entities):
    """Narrow equivalence: proposal differs from gold ONLY by extra
    args whose values equal the currently observed value of that
    field FOR THE REFERENCED ENTITY in the prefix (e.g. power:"on"
    for a device observed on). Entity context propagates into nested
    dicts (a device's state dict inherits the device id), so a
    state field is not lost. Any missing or differing gold arg, or
    any extra arg not so observed for a referenced entity, rejects
    equivalence. Returns (bool, reason). If the proposal references
    no entity, the check falls back to any-entity observed values
    and says so (looser -- never used for the light_set case)."""
    extra = set(proposal_args) - set(gold_args)
    missing = set(gold_args) - set(proposal_args)
    differing = [k for k in set(proposal_args) & set(gold_args)
                 if proposal_args[k] != gold_args[k]]
    if missing or differing:
        return False, "missing=%s differing=%s" % (sorted(missing), differing)
    if not extra:
        return False, "no difference (exact match handled separately)"
    for key in extra:
        observed = set()
        if proposal_ref_entities:
            for ent in proposal_ref_entities:
                observed |= prefix_entity_fields.get(ent, {}).get(key, set())
        else:
            for fields in prefix_entity_fields.values():
                observed |= fields.get(key, set())
        if proposal_args[key] not in observed:
            return False, "extra arg %s=%r not observed as current value " \
                "for referenced entities %s" % (
                    key, proposal_args[key], sorted(proposal_ref_entities))
    return True, "extra no-op args %s equal observed current values " \
        "for referenced entities" % (sorted(extra),)


def adjudicate_correctness(name, pargs, gold, kind_of, prefix_names,
                           prefix_search_queries, prefix_executed_writes,
                           prefix_entity_fields):
    """Return dict(is_correct, error_kind, reason, matched_gold,
    equivalent_to, prereq_missing). error_kind is None when correct.

    Order: exact gold match (+prereq) -> narrow equivalent (+prereq)
    -> error classification. A proposal matching a gold write's tool
    but differing in a reference slot is wrong_reference; differing
    in a value slot is wrong_argument; missing a slot the gold call
    has is missing_slot; a tool absent from gold writes is
    wrong_action (with gold kind noted: gold ask/empty/read_only
    means ANY write is a wrong action by construction).
    """
    gold_writes = gold["writes"]
    if gold["kind"] in ("ask_only", "empty", "read_only"):
        return {"is_correct": False, "error_kind": "wrong_action",
                "reason": "gold is %s: any write is a wrong action "
                "(gold says ask/nothing/read-only)" % gold["kind"],
                "matched_gold": None, "equivalent_to": None,
                "prereq_missing": []}
    # Exact match against any gold write.
    for idx, gc in enumerate(gold["calls"]):
        if kind_of(gc.get("name")) != "write":
            continue
        if gc.get("name") == name and \
                (gc.get("arguments") or {}) == pargs:
            ok, missing = check_prerequisites(
                idx, gold["calls"], kind_of, prefix_names,
                prefix_search_queries, prefix_executed_writes)
            if ok:
                return {"is_correct": True, "error_kind": None,
                        "reason": "exact gold match, prerequisites "
                        "satisfied at model prefix",
                        "matched_gold": gc, "equivalent_to": None,
                        "prereq_missing": []}
            return {"is_correct": False,
                    "error_kind": "prerequisite_skipped",
                    "reason": "exact gold match BUT prerequisite "
                    "skipped at model prefix: %s" % missing,
                    "matched_gold": gc, "equivalent_to": None,
                    "prereq_missing": missing}
    # Narrow equivalence against any gold write of the same tool.
    for idx, gc in enumerate(gold["calls"]):
        if kind_of(gc.get("name")) != "write" or gc.get("name") != name:
            continue
        ref_entities = {v for k, v in pargs.items()
                        if is_reference_slot(k) and isinstance(v, str)}
        ok_eq, eq_reason = no_op_equivalent(
            pargs, gc.get("arguments") or {}, prefix_entity_fields,
            ref_entities)
        if ok_eq:
            ok, missing = check_prerequisites(
                idx, gold["calls"], kind_of, prefix_names,
                prefix_search_queries, prefix_executed_writes)
            if ok:
                return {"is_correct": True, "error_kind": None,
                        "reason": "equivalent to gold (%s), "
                        "prerequisites satisfied" % eq_reason,
                        "matched_gold": gc, "equivalent_to": gc,
                        "prereq_missing": []}
            return {"is_correct": False,
                    "error_kind": "prerequisite_skipped",
                    "reason": "equivalent to gold BUT prerequisite "
                    "skipped at model prefix: %s" % missing,
                    "matched_gold": gc, "equivalent_to": gc,
                    "prereq_missing": missing}
    # Error classification against the same-tool gold write, if any.
    same_tool = [gc for gc in gold_writes if gc.get("name") == name]
    if same_tool:
        gc = same_tool[0]
        gargs = gc.get("arguments") or {}
        missing_slots = [k for k in gargs if k not in pargs]
        if missing_slots:
            return {"is_correct": False, "error_kind": "missing_slot",
                    "reason": "same tool as gold but missing slots %s"
                    % missing_slots, "matched_gold": gc,
                    "equivalent_to": None, "prereq_missing": []}
        ref_diff = [k for k in set(pargs) & set(gargs)
                    if pargs[k] != gargs[k] and is_reference_slot(k)]
        if ref_diff:
            return {"is_correct": False, "error_kind": "wrong_reference",
                    "reason": "same tool as gold but reference slots "
                    "differ: %s" % ref_diff, "matched_gold": gc,
                    "equivalent_to": None, "prereq_missing": []}
        val_diff = [k for k in set(pargs) & set(gargs)
                    if pargs[k] != gargs[k]]
        if val_diff:
            return {"is_correct": False, "error_kind": "wrong_argument",
                    "reason": "same tool as gold but argument values "
                    "differ: %s" % val_diff, "matched_gold": gc,
                    "equivalent_to": None, "prereq_missing": []}
        extra = sorted(set(pargs) - set(gargs))
        return {"is_correct": False, "error_kind": "wrong_argument",
                "reason": "same tool as gold, same gold args, but "
                "non-equivalent extra args %s" % extra,
                "matched_gold": gc, "equivalent_to": None,
                "prereq_missing": []}
    return {"is_correct": False, "error_kind": "wrong_action",
            "reason": "tool %s is not among gold writes %s"
            % (name, [c.get("name") for c in gold_writes]),
            "matched_gold": None, "equivalent_to": None,
            "prereq_missing": []}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trace", required=True)
    ap.add_argument("--version", required=True,
                    help="Trace version label, e.g. v10/v11/v13. "
                    "Outputs are per version, never merged here.")
    ap.add_argument("--train-jsonl", required=True)
    ap.add_argument("--split", required=True)
    ap.add_argument("--lifemate-dir", default=None)
    ap.add_argument("--e7-audit", default=None)
    ap.add_argument("--out-json", default="/tmp/t2_shadow.json")
    args = ap.parse_args()

    lifemate_dir = resolve_lifemate_dir(args.lifemate_dir)
    sys.path.insert(0, str(lifemate_dir))
    from lifemate_provenance import Evidence, prove_argument  # noqa: E402
    from lifemate_gates import (  # noqa: E402
        gate_read_before_write, PriorCall, flatten_result_entries)

    e7 = load_module("e7_audit", resolve_e7_path(args.e7_audit, lifemate_dir))
    flatten_obs = e7.flatten_observations_with_field
    collect_events = e7.collect_events
    collect_rosters = e7.collect_rosters_from_results

    train_dir = Path(args.train_jsonl).resolve().parent
    cat = json.load(open(str(train_dir / "train_tools_catalog.json")))
    kinds = {}
    required = {}

    def walk(o):
        if isinstance(o, dict):
            if isinstance(o.get("name"), str) and "kind" in o:
                kinds[o["name"]] = o.get("kind")
                req = (o.get("parameters") or {}).get("required")
                if isinstance(req, list):
                    required[o["name"]] = req
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(cat)

    def kind_of(name):
        if name == "sys.ask_missing_info":
            return "ask"
        if name == "__invalid__":
            return "invalid"
        return kinds.get(name, "unknown")

    split = json.load(open(args.split))
    samples = {}
    for line in open(args.train_jsonl):
        s = json.loads(line)
        samples[s["id"]] = s

    trace = json.load(open(args.trace))
    traces = trace["traces"]

    gen_counts = collections.Counter()
    invalid_generations = []
    rows = []
    history_parse_notes = []
    sample_gold_kind = {}
    for t in traces:
        sid, arm, group = t["id"], t["arm"], t["group"]
        s = samples[sid]
        in_dev = split.get(sid) == "dev"
        gold_calls = s["label"]["tool_calls"]
        gold = gold_classify(gold_calls, kind_of)
        sample_gold_kind[sid] = gold["kind"]
        anchor = (s.get("context") or {}).get("current_time")
        hist_user_gold = [h.get("audio_text", "")
                          for h in s.get("history", [])
                          if h.get("role") == "user"]
        hist_asr = [v for _, v in sorted(
            (t.get("history_asr") or {}).items(),
            key=lambda kv: u_number(kv[0]))]
        asr_divergent = (
            norm_text(t.get("model_current_transcript")) !=
            norm_text(s.get("audio_text"))) or (
            [norm_text(x) for x in hist_asr] !=
            [norm_text(x) for x in hist_user_gold])
        # --- history evidence (original input), with parse guard ---
        hist_obs, hist_events, hist_rosters = [], [], []
        hist_call_args, hist_priors = [], []
        missing_history = False
        for turn_idx, h in enumerate(s.get("history", [])):
            if h.get("role") != "assistant":
                continue
            calls = h.get("tool_calls")
            if calls is None:
                calls = []
            if not isinstance(calls, list):
                missing_history = True
                history_parse_notes.append(
                    "tool_calls non-list sample %s turn %d" % (sid, turn_idx))
                continue
            results, note = parse_tool_results(
                h.get("tool_results"), sid, turn_idx)
            if note:
                history_parse_notes.append(note)
            if h.get("tool_results") is not None and results is None:
                missing_history = True
            if results is None:
                results = []
            for idx, call in enumerate(calls):
                res = results[idx] if idx < len(results) else None
                if idx >= len(results):
                    missing_history = True
                    history_parse_notes.append(
                        "tool_results shorter than tool_calls sample %s "
                        "turn %d" % (sid, turn_idx))
                hist_call_args.append((call.get("name"),
                                       call.get("arguments") or {},
                                       succeeded(res)))
                entries = []
                if res is not None:
                    entries = flatten_result_entries(res)
                hist_priors.append(PriorCall(
                    call.get("name"), call.get("arguments") or {},
                    result_entries=entries, succeeded=succeeded(res)))
            for call, res in zip(calls, results):
                flatten_obs(res, call.get("name"), hist_obs)
                collect_events(res, call.get("name"), hist_events)
                collect_rosters(res, hist_rosters)
        hist_names = [c[0] for c in hist_call_args]
        hist_search_queries = {
            norm_text((c[1] or {}).get("query", ""))
            for c in hist_call_args if c[0] == "contacts.search"}
        # --- walk the trace; prefix = tool events strictly before ---
        prefix_tool_events = []
        for ev_idx, ev in enumerate(t["trace"]):
            if ev.get("event") == "tool":
                prefix_tool_events.append(ev)
                continue
            if ev.get("event") != "generation":
                continue
            parsed = ev.get("parsed")
            if not parsed or not parsed.get("name"):
                gen_counts["no_call"] += 1
                continue
            name = parsed["name"]
            k = kind_of(name)
            gen_counts[k] += 1
            if k == "invalid":
                invalid_generations.append({
                    "version": args.version, "sample": sid, "arm": arm,
                    "group": group, "generation_index": ev_idx,
                    "parsed": parsed})
            if k != "write":
                continue
            pargs = parsed_arguments(parsed)
            executed = any(
                e.get("event") == "tool" and e.get("name") == name
                and (e.get("arguments") or {}) == pargs
                for e in t["trace"][ev_idx + 1:])
            turn_obs, turn_events, turn_priors = [], [], []
            turn_rosters = []
            # Entity-propagated observed fields: {entity_id: {field: {values}}}
            # A dict carrying an id-like key sets the entity for itself
            # and for nested dicts (e.g. a device's state dict), so
            # state fields are attributed to the device, not lost.
            prefix_entity_fields = collections.defaultdict(
                lambda: collections.defaultdict(set))
            for pev in prefix_tool_events:
                pname = pev.get("name")
                pres = pev.get("result")
                entries = []
                if pres is not None:
                    entries = flatten_result_entries(pres)
                turn_priors.append(PriorCall(
                    pname, pev.get("arguments") or {},
                    result_entries=entries, succeeded=succeeded(pres)))
                if kind_of(pname) == "read":
                    flatten_obs(pres, pname, turn_obs)
                    collect_events(pres, pname, turn_events)
                    if pname == "contacts.search" \
                            and isinstance(pres, dict) and pres.get("ok"):
                        for entry in pres.get("contacts") or []:
                            if isinstance(entry, dict) and entry.get("id"):
                                turn_rosters.append(
                                    {"id": entry["id"],
                                     "name": entry.get("name", ""),
                                     "phone": entry.get("phone", "")})
                # Observed current field values per entity (for the
                # narrow no-op equivalence check).
                if isinstance(pres, dict):
                    def _scan(obj, entity=None):
                        if isinstance(obj, dict):
                            for ik in ("id", "device_id", "event_id",
                                       "alarm_id", "contact_id"):
                                if isinstance(obj.get(ik), str):
                                    entity = obj[ik]
                                    break
                            if entity is not None:
                                for fk, fv in obj.items():
                                    if isinstance(fv, (str, int, float)) \
                                            and not isinstance(fv, bool):
                                        prefix_entity_fields[entity][fk].add(fv)
                            for v in obj.values():
                                _scan(v, entity)
                        elif isinstance(obj, list):
                            for v in obj:
                                _scan(v, entity)
                    _scan(pres)
            rosters = list(hist_rosters) + turn_rosters
            evidence = Evidence(
                current_text=t.get("model_current_transcript") or "",
                history_user_texts=hist_asr,
                turn_observations=turn_obs,
                history_observations=hist_obs,
                history_call_args=hist_call_args,
                rosters=rosters,
                observation_events=list(hist_events) + turn_events,
                prior_call_args=[(pc.tool, pc.args, pc.succeeded)
                                 for pc in turn_priors],
                anchor=anchor,
                defaults={})
            arg_rows = []
            for slot in MONITORED:
                if slot not in pargs:
                    continue
                value = pargs[slot]
                v = prove_argument(slot, value, name, evidence,
                                   call_args=pargs)
                arg_rows.append({
                    "slot": slot, "value": value,
                    "verdict": v.status, "rule": v.rule,
                    "detail": v.detail})
            call = {"name": name, "arguments": pargs}
            g2 = gate_read_before_write(
                call, list(hist_priors) + turn_priors, rosters, kinds)
            blocked_by = []
            if g2.fired:
                blocked_by.append("g2")
            if any(a["verdict"] in ("UNPROVEN", "AMBIGUOUS")
                   for a in arg_rows):
                blocked_by.append("prover")
            if blocked_by:
                decision = "blocked"
            elif arg_rows or g2.applicable:
                decision = "passed"
            else:
                decision = "out-of-scope-guard"
            # --- external adjudication (gold only, never evidence) ---
            prefix_names = hist_names + [
                e.get("name") for e in prefix_tool_events]
            prefix_search = set(hist_search_queries)
            for e in prefix_tool_events:
                if e.get("name") == "contacts.search":
                    prefix_search.add(norm_text(
                        (e.get("arguments") or {}).get("query", "")))
            prefix_executed_writes = {
                (e.get("name"), json.dumps(e.get("arguments") or {},
                                           sort_keys=True,
                                           ensure_ascii=False))
                for e in prefix_tool_events
                if kind_of(e.get("name")) == "write"}
            corr = adjudicate_correctness(
                name, pargs, gold, kind_of, prefix_names, prefix_search,
                prefix_executed_writes, prefix_entity_fields)
            # Missing-slot note from the catalog (in addition to the
            # gold-comparison classification above).
            missing_required = [r for r in required.get(name, [])
                                if r not in pargs]
            if decision == "out-of-scope-guard":
                adjudication = "out_of_scope"
                adj_reason = ("guard silent by design (no monitored "
                              "arg, Gate 2 not applicable); correctness "
                              "recorded separately")
            elif missing_history:
                adjudication = "insufficient_evidence"
                adj_reason = ("sample history evidence missing / "
                              "unparseable; correctness not adjudicated")
            elif decision == "blocked":
                if corr["is_correct"]:
                    adjudication = "false_block"
                    adj_reason = "guard blocked a correct, "
                    "sufficiently-evidenced call"
                else:
                    adjudication = "correct_block"
                    adj_reason = corr["reason"]
            else:  # passed
                if corr["is_correct"]:
                    adjudication = "correct_pass"
                    adj_reason = corr["reason"]
                else:
                    adjudication = "miss"
                    adj_reason = corr["reason"]
            if corr["error_kind"] == "prerequisite_skipped":
                miss_note = "prerequisite skipped at model prefix"
            elif decision == "passed" and not corr["is_correct"] \
                    and not arg_rows and g2.applicable:
                miss_note = ("existence established but intent/entity "
                             "choice wrong -- Gate 2 checks existence, "
                             "not disambiguation")
            else:
                miss_note = None
            rows.append({
                "version": args.version,
                "sample": sid, "arm": arm, "group": group,
                "generation_index": ev_idx,
                "call": call, "executed": executed,
                "gold_kind": gold["kind"],
                "gold_calls": gold_calls,
                "in_dev": in_dev,
                "monitored_args": arg_rows,
                "missing_required_catalog": missing_required,
                "g2": {"fired": g2.fired, "applicable": g2.applicable,
                       "reason": g2.reason},
                "decision": decision, "blocked_by": blocked_by,
                "adjudication": adjudication,
                "adjudication_reason": adj_reason,
                "miss_note": miss_note,
                "is_correct": corr["is_correct"],
                "error_kind": corr["error_kind"],
                "correctness_reason": corr["reason"],
                "matched_gold": corr["matched_gold"],
                "equivalent_to": corr["equivalent_to"],
                "prereq_missing": corr["prereq_missing"],
                "missing_history_evidence": missing_history,
                "asr_divergent": asr_divergent})

    write_rows = rows
    monitored_args = [a for r in write_rows for a in r["monitored_args"]]
    proven_args = [a for a in monitored_args if a["verdict"] == "PROVEN"]
    decisions = collections.Counter(r["decision"] for r in write_rows)
    adjudications = collections.Counter(
        r["adjudication"] for r in write_rows)
    by_arm = {}
    for arm in sorted({r["arm"] for r in write_rows}):
        sub = [r for r in write_rows if r["arm"] == arm]
        by_arm[arm] = {
            "decisions": dict(collections.Counter(r["decision"] for r in sub)),
            "adjudications": dict(collections.Counter(
                r["adjudication"] for r in sub))}
    by_group = {}
    for group in sorted({r["group"] for r in write_rows}):
        sub = [r for r in write_rows if r["group"] == group]
        by_group[group] = {
            "decisions": dict(collections.Counter(r["decision"] for r in sub)),
            "adjudications": dict(collections.Counter(
                r["adjudication"] for r in sub))}
    correct_samples = sorted({r["sample"] for r in write_rows
                              if r["is_correct"]})
    # Adjudicated subset for precision/recall: guard-acted rows with
    # a correctness verdict (out_of_scope and insufficient_evidence
    # excluded -- their denominators are reported separately).
    adj_rows = [r for r in write_rows
                if r["adjudication"] in ("correct_block", "false_block",
                                         "correct_pass", "miss")]
    tp_block = sum(1 for r in adj_rows if r["adjudication"] == "correct_block")
    fp_block = sum(1 for r in adj_rows if r["adjudication"] == "false_block")
    fn_pass = sum(1 for r in adj_rows if r["adjudication"] == "miss")
    tn_pass = sum(1 for r in adj_rows if r["adjudication"] == "correct_pass")
    n_blocked_adj = tp_block + fp_block
    n_incorrect_adj = tp_block + fn_pass
    precision = (tp_block / n_blocked_adj) if n_blocked_adj else None
    recall = (tp_block / n_incorrect_adj) if n_incorrect_adj else None
    summary = {
        "version": args.version,
        "trace_file": args.trace,
        "code_base": f"lifemate_dir={lifemate_dir} "
        f"(this script generalizes adjudication only; the label "
        f"names the code actually loaded, not a frozen base)",
        "trajectories": len(traces),
        "samples": sorted({t["id"] for t in traces}),
        "samples_gold_kind": {sid: sample_gold_kind[sid]
                              for sid in sorted(sample_gold_kind)},
        "samples_not_in_dev": sorted(
            {t["id"] for t in traces if split.get(t["id"]) != "dev"}),
        "history_parse_notes": history_parse_notes,
        "generation_counts": dict(gen_counts),
        "generation_total": sum(gen_counts.values()),
        "invalid_generations": invalid_generations,
        "write_proposals": len(write_rows),
        "monitored_calls": sum(1 for r in write_rows
                               if r["monitored_args"]),
        "monitored_args": len(monitored_args),
        "monitored_args_proven": len(proven_args),
        "monitored_args_unproven_or_ambiguous":
            len(monitored_args) - len(proven_args),
        "guard_decisions": dict(decisions),
        "guard_decisions_by_arm": by_arm,
        "guard_decisions_by_group": by_group,
        "adjudications": dict(adjudications),
        "g2_fired": sum(1 for r in write_rows if r["g2"]["fired"]),
        "g2_applicable": sum(1 for r in write_rows
                             if r["g2"]["applicable"]),
        "asr_divergent_proposals": sum(
            1 for r in write_rows if r["asr_divergent"]),
        "executed_proposals": sum(
            1 for r in write_rows if r["executed"]),
        "correct_proposals": sum(1 for r in write_rows
                                 if r["is_correct"]),
        "independent_positive_samples": correct_samples,
        "independent_positive_count": len(correct_samples),
        "error_kinds": dict(collections.Counter(
            r["error_kind"] for r in write_rows if r["error_kind"])),
        "adjudicated_subset": {
            "n": len(adj_rows),
            "correct_block": tp_block, "false_block": fp_block,
            "miss": fn_pass, "correct_pass": tn_pass,
            "block_precision_denominator": n_blocked_adj,
            "block_precision": precision,
            "block_recall_denominator": n_incorrect_adj,
            "block_recall": recall,
            "note": "precision = correct_block / (correct_block + "
            "false_block); recall = correct_block / (correct_block + "
            "miss); both over adjudicated rows only. Out-of-scope "
            "and insufficient-evidence rows are excluded and counted "
            "separately above.",
        },
        "safety_conclusion": (
            "insufficient evidence" if len(correct_samples) < 2
            else "see adjudicated subset (still diagnostic, not a "
            "benchmark)"),
    }
    out = {"summary": summary, "rows": rows}
    json.dump(out, open(args.out_json, "w"), ensure_ascii=False, indent=1)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
