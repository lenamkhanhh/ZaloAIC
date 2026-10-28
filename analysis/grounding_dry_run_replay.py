#!/usr/bin/env python3
"""Round 7: grounding dry-run replay on all 1545 LifeMate train samples.

Two arms, labelled everywhere so their numbers are never conflated:

Arm A (the specified dry-run, gold calls as-is): every gold tool call of
every train sample runs through lifemate_grounding.ground_tool_call() with
the sample's real current_time and roster=None, and the grounded call is
checked with the official ToolEnv.validate(). No state is changed and
nothing is submitted: validate() is free and env.call() is never invoked.
Arm A measures SAFETY: gold calls are already normalized (ISO dates, int
amounts, contact_ids), so the adapter is expected to change ~nothing --
its job here is to prove 0 breakage and 100% validate pass.

Arm B (activity probes from REAL gold situations, synthetic proposals):
gold values are re-rendered into the noisy shapes an LLM proposal would
carry, then run through the adapter. These inputs are NOT gold calls and
are never reported as such:
  B-money: gold int amounts re-rendered as Vietnamese words
      ("150 nghin" style) -> adapter must recover the exact int.
  B-date: gold ISO dates re-rendered as anchor-relative expressions
      ("ngay mai", "hom qua", "15/11") -> adapter must recover the ISO date.
  B-time: gold ISO datetimes re-rendered as relative date + "luc H gio"
      -> adapter must recover (date, hour, minute).
  B-dup: for each gold search whose returned roster duplicates the QUERY
      name, a proposal {contact_name: query} with that roster -> adapter
      must return NEEDS_ASK (duplicate), matching gold's own ask policy.
  B-daypart: for each sample whose CURRENT request contains a vague
      daypart phrase (sang/chieu/toi + mai/nay), a proposal {time: phrase}
      -> adapter must return NEEDS_ASK(hour). A bonus arm appends an
      explicit hour ("... luc 8 gio") -> adapter must GROUND (hour comes
      from the string, not from context).

Roster observations in Arm B come ONLY from ToolEnv(...).call(
'contacts.search', gold_args) -- the official runtime path. This script
never opens train_environment/ or state.json directly.

Usage:
  python3 analysis/grounding_dry_run_replay.py \
      --train-jsonl <train.jsonl> --data-root <dir containing train/> \
      [--out-json <path>]
"""

import argparse
import collections
import json
import re
import sys
import unicodedata
from datetime import date, datetime
from pathlib import Path

# ------------------------------------------------------------------ helpers
_UNITS = ["không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám",
          "chín"]


def _three_digits(n):
    tram, rem = divmod(n, 100)
    chuc, donvi = divmod(rem, 10)
    parts = []
    if tram:
        parts.append(f"{_UNITS[tram]} trăm")
    if chuc == 0:
        if donvi and tram:
            parts.append(f"linh {_UNITS[donvi]}")
        elif donvi:
            parts.append(_UNITS[donvi])
    elif chuc == 1:
        if donvi == 0:
            parts.append("mười")
        elif donvi == 5:
            parts.append("mười lăm")
        else:
            parts.append(f"mười {_UNITS[donvi]}")
    else:
        if donvi == 0:
            parts.append(f"{_UNITS[chuc]} mươi")
        elif donvi == 1:
            parts.append(f"{_UNITS[chuc]} mươi mốt")
        elif donvi == 4:
            parts.append(f"{_UNITS[chuc]} mươi tư")
        elif donvi == 5:
            parts.append(f"{_UNITS[chuc]} mươi lăm")
        else:
            parts.append(f"{_UNITS[chuc]} mươi {_UNITS[donvi]}")
    return " ".join(parts)


def int_to_words(n):
    """int -> Vietnamese words (0 < n < 10**12), or None if unrenderable."""
    if not isinstance(n, int) or n <= 0 or n >= 10 ** 12:
        return None
    parts = []
    rest = n
    for scale, word in ((10 ** 9, "tỷ"), (10 ** 6, "triệu"),
                        (10 ** 3, "nghìn")):
        g, rest = divmod(rest, scale)
        if g:
            parts.append(f"{_three_digits(g)} {word}")
    if rest:
        parts.append(_three_digits(rest))
    return " ".join(parts)


def nfc_lower(s):
    return unicodedata.normalize("NFC", s or "").lower().strip()


def rel_date_expr(d, anchor):
    """ISO date -> anchor-relative expression (or dd/mm[/yyyy] if far)."""
    delta = (d - anchor).days
    m = {0: "hôm nay", -1: "hôm qua", -2: "hôm kia",
         1: "ngày mai", 2: "ngày kia", 3: "ngày mốt"}
    if delta in m:
        return m[delta]
    if d.year != anchor.year:
        return f"{d.day:02d}/{d.month:02d}/{d.year}"
    return f"{d.day:02d}/{d.month:02d}"


_DAYPARTS = ["sáng mai", "chiều mai", "tối mai",
             "sáng nay", "chiều nay", "tối nay"]


def first_daypart(text):
    s = nfc_lower(text)
    for ph in _DAYPARTS:
        if ph in s:
            return ph
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train-jsonl", required=True)
    ap.add_argument("--data-root", required=True)
    ap.add_argument("--out-json", default=None)
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(repo_root))
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "lifemate_grounding", repo_root / "lifemate" / "lifemate_grounding.py")
    gmod = importlib.util.module_from_spec(spec)
    sys.modules["lifemate_grounding"] = gmod
    spec.loader.exec_module(gmod)

    train_dir = str(Path(args.train_jsonl).resolve().parent)
    sys.path.insert(0, train_dir)
    from zaic_tools import ToolEnv

    samples = [json.loads(l) for l in open(args.train_jsonl, encoding="utf-8")
               if l.strip()]
    A = collections.Counter()
    A_changed_keys = collections.Counter()
    A_needs = collections.Counter()
    A_failures = []      # grounded calls failing validate (gate breakers)
    A_orig_failures = []  # gold calls failing validate (data findings)
    B = collections.Counter()
    B_failures = []

    for s in samples:
        ctx = {"current_time": (s.get("context") or {}).get("current_time")}
        anchor = None
        if ctx["current_time"]:
            try:
                anchor = datetime.fromisoformat(ctx["current_time"]).date()
            except ValueError:
                anchor = None
        gold = (s.get("label") or {}).get("tool_calls", []) or []
        # ---- Arm A: gold calls through the adapter + ToolEnv validate
        try:
            env = ToolEnv("train", s["id"], root=args.data_root)
        except Exception as e:  # noqa: BLE001 - counted, not fatal
            A["samples_env_error"] += 1
            A_failures.append({"sample": s["id"], "error": f"ToolEnv: {e}"})
            continue
        for call in gold:
            A["gold_calls"] += 1
            grounded = gmod.ground_tool_call(call, ctx, None)
            A[f"status_{grounded.status}"] += 1
            for k in grounded.needs:
                A_needs[k] += 1
            orig_args = call.get("arguments") or {}
            new_args = grounded.call.get("arguments") or {}
            for k in set(orig_args) | set(new_args):
                if orig_args.get(k) != new_args.get(k):
                    A_changed_keys[k] += 1
            v_orig = env.validate(call["name"], orig_args)
            if not v_orig.get("ok"):
                A_orig_failures.append(
                    {"sample": s["id"], "call": call, "error": v_orig})
            v = env.validate(grounded.call["name"], new_args)
            if not v.get("ok"):
                A_failures.append({"sample": s["id"], "call": grounded.call,
                                   "error": v})
            else:
                A["grounded_validate_ok"] += 1
        # ---- Arm B: activity probes from real gold situations
        for call in gold:
            cargs = call.get("arguments") or {}
            # B-money: int amount -> words -> adapter must recover int.
            if isinstance(cargs.get("amount"), int):
                words = int_to_words(cargs["amount"])
                if words is None:
                    B["money_skipped_unrenderable"] += 1
                else:
                    B["money_probes"] += 1
                    prop = {"name": call["name"],
                            "arguments": dict(cargs, amount=words)}
                    r = gmod.ground_tool_call(prop, ctx, None)
                    if (r.status == "GROUNDED"
                            and r.call["arguments"].get("amount")
                            == cargs["amount"]):
                        B["money_recovered"] += 1
                    else:
                        B_failures.append({"arm": "money", "sample": s["id"],
                                           "words": words,
                                           "status": r.status,
                                           "got": r.call["arguments"].get(
                                               "amount")})
            # B-date / B-time: ISO values -> relative expressions.
            for key in ("date", "time", "start", "end"):
                v = cargs.get(key)
                if not isinstance(v, str) or anchor is None:
                    continue
                if key == "date":
                    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", v)
                    if not m:
                        B["date_skipped_non_full_date"] += 1
                        continue
                    d = date(int(m.group(1)), int(m.group(2)),
                             int(m.group(3)))
                    expr = rel_date_expr(d, anchor)
                    B["date_probes"] += 1
                    prop = {"name": call["name"],
                            "arguments": dict(cargs, **{key: expr})}
                    r = gmod.ground_tool_call(prop, ctx, None)
                    if (r.status == "GROUNDED"
                            and r.call["arguments"].get(key) == v):
                        B["date_recovered"] += 1
                    else:
                        B_failures.append({"arm": "date", "sample": s["id"],
                                           "expr": expr, "status": r.status,
                                           "got": r.call["arguments"].get(
                                               key)})
                else:
                    m = re.match(
                        r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})", v)
                    if not m:
                        B["time_skipped_non_datetime"] += 1
                        continue
                    d = date(int(m.group(1)), int(m.group(2)),
                             int(m.group(3)))
                    hh, mm = int(m.group(4)), int(m.group(5))
                    expr = rel_date_expr(d, anchor) + f" lúc {hh} giờ"
                    if mm:
                        expr += f" {mm}"
                    B["time_probes"] += 1
                    prop = {"name": call["name"],
                            "arguments": dict(cargs, **{key: expr})}
                    r = gmod.ground_tool_call(prop, ctx, None)
                    got = r.call["arguments"].get(key)
                    ok = False
                    if r.status == "GROUNDED" and isinstance(got, str):
                        try:
                            gd = datetime.fromisoformat(got)
                            ok = (gd.date() == d and gd.hour == hh
                                  and gd.minute == mm)
                        except ValueError:
                            ok = False
                    if ok:
                        B["time_recovered"] += 1
                    else:
                        B_failures.append({"arm": "time", "sample": s["id"],
                                           "expr": expr, "status": r.status,
                                           "got": got})
        # B-daypart (+hour bonus) from the CURRENT request text.
        ph = first_daypart(s.get("audio_text", ""))
        if ph:
            B["daypart_probes"] += 1
            prop = {"name": "reminders.create",
                    "arguments": {"time": ph, "content": "x"}}
            r = gmod.ground_tool_call(prop, ctx, None)
            if r.status == "NEEDS_ASK" and "time:hour" in r.needs:
                B["daypart_needs_ask_hour"] += 1
            else:
                B_failures.append({"arm": "daypart", "sample": s["id"],
                                   "phrase": ph, "status": r.status,
                                   "needs": r.needs})
            B["daypart_hour_probes"] += 1
            prop2 = {"name": "reminders.create",
                     "arguments": {"time": ph + " lúc 8 giờ",
                                   "content": "x"}}
            r2 = gmod.ground_tool_call(prop2, ctx, None)
            if r2.status == "GROUNDED":
                B["daypart_hour_grounded"] += 1
            else:
                B_failures.append({"arm": "daypart_hour", "sample": s["id"],
                                   "phrase": ph + " lúc 8 giờ",
                                   "status": r2.status, "needs": r2.needs})
        # B-dup: replay this sample's gold searches; duplicate-query
        # proposals must NEEDS_ASK, other-duplicate proposals must ground.
        search_idx = [i for i, gg in enumerate(gold)
                      if gg.get("name") == "contacts.search"]
        if search_idx:
            env2 = ToolEnv("train", s["id"], root=args.data_root)
            for si in search_idx:
                gg = gold[si]
                query = (gg.get("arguments") or {}).get("query")
                res = env2.call("contacts.search", gg.get("arguments") or {})
                returned = []
                if isinstance(res, dict) and res.get("ok"):
                    for ct in res.get("contacts", []) or []:
                        returned.append({"id": ct.get("id"),
                                         "name": ct.get("name")})
                by_name = collections.defaultdict(set)
                for ct in returned:
                    by_name[gmod._nfc_lower(ct["name"])].add(ct["id"])
                dups = {k for k, v in by_name.items() if len(v) > 1}
                if not query or not query.strip():
                    continue
                # Ask target after this search (gold's own next call).
                ask_tool = None
                if si + 1 < len(gold) and gold[si + 1]["name"] == \
                        "sys.ask_missing_info":
                    ask_tool = (gold[si + 1].get("arguments") or {}).get(
                        "tool_name")
                tool = ask_tool or "phone.call"
                key = "to" if tool == "email.create_draft" else "contact_name"
                prop = {"name": tool, "arguments": {key: query}}
                r = gmod.ground_tool_call(prop, ctx, returned)
                if gmod._nfc_lower(query) in dups:
                    B["dup_probes"] += 1
                    if (r.status == "NEEDS_ASK"
                            and "contact:ambiguous" in r.needs):
                        B["dup_needs_ask"] += 1
                    else:
                        B_failures.append({"arm": "dup", "sample": s["id"],
                                           "query": query,
                                           "status": r.status})
                elif dups:
                    # Duplicates exist, but NOT of the query name: the
                    # query itself is unambiguous and must still ground.
                    B["otherdup_probes"] += 1
                    if r.status == "GROUNDED":
                        B["otherdup_grounded"] += 1
                    else:
                        B_failures.append({"arm": "otherdup",
                                           "sample": s["id"], "query": query,
                                           "status": r.status,
                                           "needs": r.needs})
                else:
                    B["clean_probes"] += 1
                    if r.status == "GROUNDED":
                        B["clean_grounded"] += 1
                    else:
                        B_failures.append({"arm": "clean",
                                           "sample": s["id"], "query": query,
                                           "status": r.status,
                                           "needs": r.needs})
    out = {
        "n_samples": len(samples),
        "arm_a": dict(A),
        "arm_a_changed_keys": dict(A_changed_keys),
        "arm_a_needs": dict(A_needs),
        "arm_a_grounded_validate_failures": A_failures,
        "arm_a_original_validate_failures": A_orig_failures,
        "arm_b": dict(B),
        "arm_b_failures": B_failures,
    }
    text = json.dumps(out, ensure_ascii=False, indent=2)
    if args.out_json:
        with open(args.out_json, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    short = dict(out)
    short["arm_a_grounded_validate_failures_n"] = len(A_failures)
    short["arm_a_original_validate_failures_n"] = len(A_orig_failures)
    short["arm_b_failures_n"] = len(B_failures)
    del short["arm_a_grounded_validate_failures"]
    del short["arm_a_original_validate_failures"]
    del short["arm_b_failures"]
    print(json.dumps(short, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
