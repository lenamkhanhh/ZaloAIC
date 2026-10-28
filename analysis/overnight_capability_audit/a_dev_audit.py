#!/usr/bin/env python3
"""Thread A (overnight capability audit): dev-only data audit for SFT readiness.

Loads the split map FIRST and drops every held-out row before any
analysis. Uses ONLY the 1237 dev samples. CPU-only: gold replay goes
through zaic_tools.ToolEnv (the only legal state access); no model,
no GPU, no training, no held-out content anywhere in the output.

Outputs a_dev_audit.json next to this script.
"""
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path.home() / "workspace" / "zalo-aic-round3"
DATA = Path.home() / "workspace" / "zaic-data" / "lifemate" / "extracted" / "train+public_test"
TRAIN_DIR = DATA / "train"
sys.path.insert(0, str(TRAIN_DIR))
from zaic_tools import ToolEnv  # noqa: E402

OUT = Path(__file__).resolve().parent / "a_dev_audit.json"


def fold(s):
    s = unicodedata.normalize("NFD", str(s).lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.replace("đ", "d").strip()


def main():
    split = json.loads((REPO / "lifemate" / "splits" / "train_dev_heldout.json").read_text())
    dev_ids = {k for k, v in split.items() if v == "dev"}
    held_ids = {k for k, v in split.items() if v == "heldout"}
    assert len(dev_ids) == 1237 and len(held_ids) == 308, (len(dev_ids), len(held_ids))

    catalog = json.loads((TRAIN_DIR / "train_tools_catalog.json").read_text())
    kind = {}
    fuzzy = {}
    required_counts = {}
    for app in catalog["apps"]:
        for t in app["tools"]:
            kind[t["name"]] = t.get("kind", "")
            props = t["parameters"].get("properties", {})
            fuzzy[t["name"]] = sorted(n for n, s in props.items() if s.get("x-match") == "fuzzy")
            required_counts[t["name"]] = len(t["parameters"].get("required", []))

    dev = []
    n_rows = 0
    for line in (TRAIN_DIR / "train.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        n_rows += 1
        s = json.loads(line)
        if s["id"] in dev_ids:
            dev.append(s)
    assert len(dev) == 1237, len(dev)
    assert not any(s["id"] in held_ids for s in dev)
    print(f"train.jsonl rows={n_rows} dev_kept={len(dev)} heldout_dropped={len(held_ids)}")

    out = {"n_train_rows": n_rows, "n_dev": len(dev), "n_heldout_dropped": len(held_ids)}

    # ---- label classes ----
    def label_class(calls):
        if not calls:
            return "empty"
        names = [c["name"] for c in calls]
        if names == ["sys.ask_missing_info"]:
            return "ask_only"
        if "sys.ask_missing_info" in names:
            return "ask_after"
        return "normal"
    out["label_class"] = Counter(label_class(s["label"]["tool_calls"]) for s in dev)

    # ---- gold call shape ----
    lens = Counter(len(s["label"]["tool_calls"]) for s in dev)
    out["gold_call_count_dist"] = dict(sorted(lens.items()))
    kinds_per_sample = Counter()
    last_kind = Counter()
    for s in dev:
        ks = set(kind.get(c["name"], "?") for c in s["label"]["tool_calls"])
        kinds_per_sample["+".join(sorted(ks)) if ks else "none"] += 1
        if s["label"]["tool_calls"]:
            last_kind[kind.get(s["label"]["tool_calls"][-1]["name"], "?")] += 1
        else:
            last_kind["empty"] += 1
    out["gold_kind_mix_per_sample"] = dict(kinds_per_sample)
    out["gold_last_call_kind"] = dict(last_kind)

    # ---- tool / app distributions ----
    tool_ct = Counter()
    app_ct = Counter()
    toolname_to_app = {}
    for app in catalog["apps"]:
        for t in app["tools"]:
            toolname_to_app[t["name"]] = app["id"]
    seq_ct = Counter()
    first_ct = Counter()
    for s in dev:
        names = [c["name"] for c in s["label"]["tool_calls"]]
        tool_ct.update(names)
        app_ct.update(toolname_to_app.get(n, "?") for n in names)
        seq_ct[tuple(names)] += 1
        if names:
            first_ct[names[0]] += 1
    out["gold_tool_counts"] = dict(tool_ct)
    out["gold_app_counts"] = dict(app_ct)
    out["gold_top_sequences"] = [{"seq": list(k), "n": v} for k, v in seq_ct.most_common(25)]
    out["n_distinct_gold_sequences"] = len(seq_ct)
    out["gold_first_call_counts"] = dict(first_ct)
    out["tools_never_in_dev_gold"] = sorted(set(kind) - set(tool_ct))
    out["tools_rare_in_dev_gold_lt10"] = sorted(n for n, c in tool_ct.items() if c < 10)
    out["tools_rare_in_dev_gold_lt5"] = sorted(n for n, c in tool_ct.items() if c < 5)

    # ---- ask position ----
    ask_pos = Counter()
    for s in dev:
        names = [c["name"] for c in s["label"]["tool_calls"]]
        if "sys.ask_missing_info" in names:
            i = names.index("sys.ask_missing_info")
            ask_pos["only" if len(names) == 1 else ("first" if i == 0 else ("last" if i == len(names) - 1 else "middle"))] += 1
    out["ask_position"] = dict(ask_pos)

    # ---- read-before-write in gold order ----
    rbw = Counter()
    for s in dev:
        names = [c["name"] for c in s["label"]["tool_calls"]]
        kinds = [kind.get(n, "?") for n in names]
        has_write = "write" in kinds
        if not has_write:
            rbw["no_write"] += 1
            continue
        first_write = kinds.index("write")
        rbw["write_after_read" if "read" in kinds[:first_write] else "write_without_prior_read"] += 1
    out["gold_read_before_write"] = dict(rbw)

    # ---- pattern heuristics (labelled as heuristics in the report) ----
    cond_words = tuple(fold(w) for w in ("nếu", "khi ", "trừ khi", "trong trường hợp", "miễn là"))
    corr_words = tuple(fold(w) for w in ("sửa", "đổi lại", "nhầm", "không phải", "thôi khỏi", "hủy", "huỷ"))
    pat = Counter()
    for s in dev:
        req = fold(s.get("audio_text") or "")
        hist_user = " ".join(fold(t.get("audio_text") or "") for t in s.get("history", []) if t.get("role") == "user")
        if any(w in req for w in cond_words):
            pat["conditional_request"] += 1
        if any(w in req for w in corr_words) or any(w in hist_user for w in corr_words):
            pat["correction_or_cancel_word"] += 1
        names = [c["name"] for c in s["label"]["tool_calls"]]
        if any("cancel" in n or "delete" in n for n in names):
            pat["gold_has_cancel_or_delete"] += 1
        if any("update" in n for n in names):
            pat["gold_has_update"] += 1
        if len(s.get("history", [])) > 0:
            pat["has_history"] += 1
        if len(s.get("history", [])) >= 4:
            pat["history_ge_4_turns"] += 1
    out["pattern_heuristics"] = dict(pat)

    # ---- history tool_results form ----
    hist_form = Counter()
    hist_turns = Counter()
    for s in dev:
        hist_turns[len(s.get("history", []))] += 1
        for t in s.get("history", []):
            if t.get("role") == "assistant":
                tr = t.get("tool_results")
                hist_form["list" if isinstance(tr, list) else ("repr_string" if isinstance(tr, str) else ("none" if tr is None else "other"))] += 1
    out["history_turn_count_dist"] = dict(sorted(hist_turns.items()))
    out["history_assistant_tool_results_form"] = dict(hist_form)

    # ---- installed tools / apps per sample ----
    inst_ct = Counter()
    inst_apps = Counter()
    for s in dev:
        tools = set()
        for app in s["context"].get("installed_apps", {}).values():
            tools.update(app.get("tools", []))
            inst_apps[app.get("id", "?")] += 0  # placeholder
        inst_ct[len(tools)] += 1
        for appid in s["context"].get("installed_apps", {}):
            inst_apps[appid] += 1
    out["installed_tool_count_dist"] = dict(sorted(inst_ct.items()))
    out["installed_app_sample_counts"] = dict(inst_apps)

    # ---- gold replay through ToolEnv + duplicate-search audit ----
    replay = Counter()
    anomaly = []
    dup_searches = 0
    dup_total = 0
    dup_next = Counter()
    samples_all_succeeded = 0
    for s in dev:
        env = ToolEnv("train", s["id"], root=str(DATA))
        calls = s["label"]["tool_calls"]
        all_ok = True
        for pos, call in enumerate(calls):
            name, args = call.get("name"), call.get("arguments") or {}
            try:
                res = env.call(name, args)
            except Exception as e:  # noqa: BLE001
                replay["exception"] += 1
                all_ok = False
                anomaly.append({"sample": s["id"], "pos": pos, "tool": name, "issue": f"exception:{type(e).__name__}"})
                continue
            if not isinstance(res, dict):
                replay["non_dict_result"] += 1
                all_ok = False
                continue
            if res.get("ok") is True and res.get("done") is not False:
                replay["succeeded"] += 1
            elif res.get("ok") is True:
                replay["ok_but_not_done"] += 1
                all_ok = False
                anomaly.append({"sample": s["id"], "pos": pos, "tool": name, "issue": "ok_true_done_false"})
            else:
                replay["rejected_ok_false"] += 1
                all_ok = False
                anomaly.append({"sample": s["id"], "pos": pos, "tool": name, "issue": f"ok_false:{res.get('error')}"})
            if name == "contacts.search" and isinstance(res, dict) and res.get("ok"):
                contacts = res.get("contacts") or []
                dup_total += 1
                by_name = defaultdict(set)
                for c in contacts:
                    if isinstance(c, dict) and c.get("id") and c.get("name"):
                        by_name[fold(c["name"])].add(c["id"])
                if any(len(v) > 1 for v in by_name.values()):
                    dup_searches += 1
                    nxt = calls[pos + 1]["name"] if pos + 1 < len(calls) else "<end>"
                    dup_next[nxt] += 1
        if all_ok:
            samples_all_succeeded += 1
    out["gold_replay"] = dict(replay)
    out["gold_replay_samples_all_calls_succeeded"] = samples_all_succeeded
    out["gold_replay_anomalies"] = anomaly
    out["contacts_search"] = {"total": dup_total, "duplicate_name_searches": dup_searches,
                              "gold_next_call_after_duplicate": dict(dup_next)}

    # ---- time/amount/contact source heuristic ----
    # Second replay pass: collect each gold call's PRIOR gold results,
    # so observation-derived values (ids, bill amounts) are not
    # misclassified as "none_of_those".
    prefix_results = {}
    for s in dev:
        env = ToolEnv("train", s["id"], root=str(DATA))
        priors = []
        for call in s["label"]["tool_calls"]:
            prefix_results.setdefault(s["id"], []).append("\n".join(priors))
            try:
                res = env.call(call.get("name"), call.get("arguments") or {})
            except Exception:  # noqa: BLE001
                res = None
            priors.append(json.dumps(res, ensure_ascii=False) if res is not None else "")
    # Contacts-app availability: a no-query contacts.search returns
    # ok False ("không thuộc app đã cài") exactly when the sample
    # does not install the contacts app -- NOT an empty roster.
    # (An earlier draft predicate required ok True and misreported 0.)
    not_installed = []
    for s in dev:
        env = ToolEnv("train", s["id"], root=str(DATA))
        try:
            res = env.call("contacts.search", {})
        except Exception:  # noqa: BLE001
            continue
        if isinstance(res, dict) and not (res.get("contacts") or []):
            not_installed.append(s["id"])
    out["samples_without_contacts_app"] = len(not_installed)
    out["samples_without_contacts_app_ids"] = not_installed

    def src_of(value, s, prior_json=""):
        v = str(value)
        cur = s.get("audio_text") or ""
        if v and v in cur:
            return "verbatim_current"
        if v:
            # datetime: date part or HH:MM part
            m = re.match(r"(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})", v)
            if m and (m.group(1) in cur or m.group(2) in cur):
                return "verbatim_current_part"
        hist_user = " ".join(t.get("audio_text") or "" for t in s.get("history", []) if t.get("role") == "user")
        if v and v in hist_user:
            return "history_user_text"
        hist_res = json.dumps([t.get("tool_results") for t in s.get("history", []) if t.get("role") == "assistant"], ensure_ascii=False)
        if v and v in hist_res:
            return "history_tool_result"
        if v and v in prior_json:
            return "gold_prefix_result"
        ctx = json.dumps(s.get("context", {}), ensure_ascii=False)
        if v and v in ctx:
            return "context"
        return "none_of_those"
    def slot_class(arg):
        a = arg.lower()
        if a in ("time", "start", "end", "datetime") or a.endswith("_time") or a in ("start_time", "end_time"):
            return "time"
        if a in ("date",) or a.endswith("_date"):
            return "date"
        if a in ("amount", "price") or a.endswith("_amount"):
            return "amount"
        if a == "contact_id" or a == "to":
            return "contact_ref"
        if a.endswith("_id"):
            return "entity_id"
        return "other"
    src_ct = defaultdict(Counter)
    val_format = defaultdict(Counter)
    for s in dev:
        priors = prefix_results.get(s["id"], [])
        for ci, call in enumerate(s["label"]["tool_calls"]):
            if kind.get(call["name"]) != "write":
                continue
            prior_json = priors[ci] if ci < len(priors) else ""
            for arg, val in (call.get("arguments") or {}).items():
                sc = slot_class(arg)
                src_ct[sc][src_of(val, s, prior_json)] += 1
                if sc in ("time", "date"):
                    v = str(val)
                    if re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?(\+\d{2}:\d{2})?", v):
                        val_format[sc]["iso_datetime"] += 1
                    elif re.fullmatch(r"\d{2}:\d{2}(:\d{2})?", v):
                        val_format[sc]["time_only"] += 1
                    elif re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
                        val_format[sc]["date_only"] += 1
                    else:
                        val_format[sc]["other"] += 1
                elif sc == "amount":
                    val_format[sc]["int" if isinstance(val, int) else ("float" if isinstance(val, float) else "string")] += 1
    out["gold_write_arg_source_heuristic"] = {k: dict(v) for k, v in src_ct.items()}
    out["gold_write_arg_value_format"] = {k: dict(v) for k, v in val_format.items()}

    # ---- template / overlap: normalized request text + tool sequence ----
    def norm_req(t):
        t = fold(t or "")
        t = re.sub(r"\d+", "#", t)
        return re.sub(r"\s+", " ", t).strip()
    req_groups = defaultdict(list)
    for s in dev:
        req_groups[norm_req(s.get("audio_text") or "")].append(s["id"])
    dup_req = {k: v for k, v in req_groups.items() if len(v) > 1}
    out["request_template_overlap"] = {
        "n_distinct_normalized_requests": len(req_groups),
        "n_groups_with_gt1_sample": len(dup_req),
        "n_samples_in_dup_groups": sum(len(v) for v in dup_req.values()),
        "largest_groups": sorted((len(v) for v in dup_req.values()), reverse=True)[:10],
    }
    out["request_template_dup_examples"] = [
        {"request": k, "n": len(v), "samples": v[:5]} for k, v in sorted(dup_req.items(), key=lambda kv: -len(kv[1]))[:10]
    ]

    # ---- catalog schema stats ----
    out["catalog"] = {
        "n_tools": len(kind),
        "kind_counts": dict(Counter(kind.values())),
        "tools_with_required_params": sum(1 for v in required_counts.values() if v > 0),
        "tools_with_zero_required": sum(1 for v in required_counts.values() if v == 0),
        "fuzzy_params": {k: v for k, v in fuzzy.items() if v},
        "n_tools_with_fuzzy_params": sum(1 for v in fuzzy.values() if v),
    }

    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(f"wrote {OUT}")
    print("label_class:", dict(out["label_class"]))
    print("gold_replay:", dict(replay), "all_succeeded_samples:", samples_all_succeeded)
    print("contacts_search:", out["contacts_search"])
    print("gold_call_count_dist:", out["gold_call_count_dist"])


if __name__ == "__main__":
    main()
