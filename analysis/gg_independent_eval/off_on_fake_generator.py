#!/usr/bin/env python3
"""OFF/ON fake-generator run (independent, candidate d1090d1d).

Runs the REAL AgentLoop from the candidate snapshot with a fake
generator and a fake env, twice: shadow observer OFF vs ON.
Compares everything the agent does, and inspects what the observer
recorded.

Realistic entry: a tmp repo root containing lifemate/ as a package;
ONLY the root is on sys.path (no lifemate/ hack). Fresh interpreter.

Fake generator script (per sample):
  1. valid phone.call (in-scope proposal)
  2. non-dict output (invalid generation)
  3. unknown tool (validation failure -> retry)
  4. valid sms.send (in-scope proposal)
  5. {"stop": true}

Compared OFF vs ON: prompts seen by the generator, submitted calls,
env state, return value, generator call count (retries/termination).

Assertions / checks:
  - behavior_identical: agent does exactly the same with ON and OFF.
  - observer_recorded: with ON, records exist for the run.
  - in_scope_have_decisions: every in-scope validated proposal has
    baseline/candidate decisions AND no import error. EXPECTED TO
    FAIL on this candidate (documents the integration gap); the
    script reports it as data, it does not raise.
  - reset_across_samples: running a second sample on the same loop
    does not leak the first sample's records.
  - observer_exception_path: unparseable history -> error record,
    never raises, agent flow untouched.

Usage:
  python3 off_on_fake_generator.py --lifemate-dir <candidate lifemate/>
      --out <json>
"""

import argparse
import copy
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PROBE = r'''
import copy, hashlib, json, sys
root = sys.argv[1]
sys.path.insert(0, root)  # realistic: repo root only, no lifemate/ hack
from lifemate.agent import AgentLoop
from lifemate.config import PipelineConfig
from lifemate.loader import Sample, Turn

TOOLS = {
    "phone.call": {"kind": "write", "parameters": {"required": []},
                   "description": "call"},
    "sms.send": {"kind": "write", "parameters": {"required": []},
                 "description": "sms"},
    "sys.ask_missing_info": {"kind": "meta",
                             "parameters": {"required": []},
                             "description": "ask"},
}

class FakeEnv:
    def __init__(self, sid):
        self.sid = sid
        self.calls = []
        self.state = {"n_calls": 0}
    def validate(self, name, args):
        if name in TOOLS:
            return {"ok": True}
        return {"ok": False, "error": "unknown tool %s" % name}
    def call(self, name, args):
        self.calls.append({"name": name, "arguments": args})
        self.state["n_calls"] += 1
        return {"ok": True, "done": True}
    def state_hash(self):
        return hashlib.sha256(json.dumps(
            self.state, sort_keys=True).encode()).hexdigest()[:16]
    def submission_line(self):
        return {"id": self.sid, "tool_calls": list(self.calls),
                "state_hash": self.state_hash()}

SCRIPT = [
    {"name": "phone.call", "arguments": {"phone_number": "0903111222"}},
    "not-a-dict",
    {"name": "nope.unknown", "arguments": {}},
    {"name": "sms.send", "arguments": {"phone_number": "0903333444",
                                       "content": "hi"}},
    {"stop": True},
]

def make_sample(sid, utext):
    return Sample(
        id=sid, split="train", audio="a.wav",
        context={"current_time": "2026-10-30T07:00:00+07:00",
                 "timezone": "Asia/Saigon",
                 "user_profile": {"name": "Test", "city": "HCM"},
                 "installed_apps": {}},
        history=[Turn(role="user", audio_text=utext)],
        audio_text=utext)

def run_once(observer_on, sid, utext):
    seen_prompts = []
    script = [copy.deepcopy(x) for x in SCRIPT]
    def gen(prompt, tools):
        seen_prompts.append(prompt)
        if not script:
            return None
        return script.pop(0)
    env = FakeEnv(sid)
    cfg = PipelineConfig(grounding=False, shadow_observer=observer_on)
    loop = AgentLoop(cfg, TOOLS)
    out = loop.run(make_sample(sid, utext), utext, env, gen)
    return {
        "prompts": seen_prompts,
        "submitted": out["tool_calls"],
        "state": env.state,
        "state_hash": out["state_hash"],
        "n_gen_calls": len(seen_prompts),
        "records": copy.deepcopy(loop.observer.records),
        "observer_enabled": loop.observer.enabled,
    }, loop

off, _ = run_once(False, "s1", "gọi số 0903111222")
on, loop_on = run_once(True, "s1", "gọi số 0903111222")

behavior_identical = (
    off["prompts"] == on["prompts"]
    and off["submitted"] == on["submitted"]
    and off["state"] == on["state"]
    and off["state_hash"] == on["state_hash"]
    and off["n_gen_calls"] == on["n_gen_calls"])

in_scope = [r for r in on["records"]
            if r.get("validation_outcome") == "ok"
            and r.get("proposal_grounded", {}).get("name")
            not in (None, "sys.ask_missing_info")]
decisions_ok = (
    len(in_scope) > 0
    and all(r["baseline_decision"] is not None
            and r["candidate_decision"] is not None for r in in_scope)
    and all(not r.get("error") or "ModuleNotFoundError" not in str(r["error"])
            for r in in_scope))
import_errors = sorted({str(r["error"]) for r in on["records"] if r.get("error")})

# reset across samples on the SAME loop instance (distinct number so a
# leak is detectable: any 0903111222 record after run 2 is stale)
_, loop2 = run_once(True, "s1", "gọi số 0903111222")
env2 = FakeEnv("s2")
script2 = [copy.deepcopy(x) for x in SCRIPT]
script2[0] = {"name": "phone.call",
              "arguments": {"phone_number": "0903777888"}}
def gen2(prompt, tools):
    return script2.pop(0) if script2 else None
out2 = loop2.run(make_sample("s2", "nhắn số 0903333444"),
                 "nhắn số 0903333444", env2, gen2)
leaked = any("0903111222" in json.dumps(r.get("proposal_raw"), ensure_ascii=False)
             for r in loop2.observer.records)

# observer exception path: unparseable history must not raise
from lifemate.lifemate_observer import ShadowObserver
obs = ShadowObserver(True)
bad_hist = [{"role": "assistant", "tool_calls": [{"name": "phone.call"}],
             "tool_results": "garbage-not-a-list"}]
try:
    obs.observe_proposal({"name": "phone.call",
                          "arguments": {"phone_number": "0903111222"}},
                         {"name": "phone.call",
                          "arguments": {"phone_number": "0903111222"}},
                         history=bad_hist, executed=[], results=[],
                         current_text="x", kinds={})
    exc_ok = (len(obs.records) == 1
              and obs.records[0]["baseline_decision"] is None
              and obs.records[0]["error"] is not None)
except Exception:
    exc_ok = False

report = {
    "behavior_identical_off_on": behavior_identical,
    "off_submitted": off["submitted"],
    "on_submitted": on["submitted"],
    "n_gen_calls_off": off["n_gen_calls"],
    "n_gen_calls_on": on["n_gen_calls"],
    "observer_enabled_on": on["observer_enabled"],
    "n_records_on": len(on["records"]),
    "n_records_off": len(off["records"]),
    "in_scope_proposals_observed": len(in_scope),
    "in_scope_have_decisions_no_import_error": decisions_ok,
    "record_errors": import_errors,
    "reset_no_leak_across_samples": not leaked,
    "observer_exception_path_no_raise": exc_ok,
}
print(json.dumps(report, ensure_ascii=False, indent=1))
'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lifemate-dir", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    tmp = Path(tempfile.mkdtemp(prefix="offon_"))
    shutil.copytree(args.lifemate_dir, tmp / "lifemate",
                    ignore=shutil.ignore_patterns("__pycache__"))
    cmd = [sys.executable, "-c", PROBE, str(tmp)]
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          timeout=300)
    out = {"returncode": proc.returncode,
           "stderr_tail": proc.stderr[-2000:]}
    if proc.returncode != 0:
        out["error"] = "probe failed"
        print(json.dumps(out, ensure_ascii=False, indent=1))
    else:
        report = json.loads(proc.stdout)
        report["probe_returncode"] = 0
        out.update(report)
        print(json.dumps(report, ensure_ascii=False, indent=1))
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False,
                                        indent=1), encoding="utf-8")
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
