"""Shadow-observer export CLI (RUN2, Group 4 Observer / log storage).

RUN2 task R2-G4, parent L6. LifeMate only. Base source pin:
ff7a288e668f37e96c03bf9318d974e3a8e6d2a4.

This is a NEW file only. It does not edit lifemate/agent.py,
lifemate/config.py, any config JSON, the simulator, the scorer, or
any split. AgentLoop already exposes ``loop.observer``; this CLI
reads ``loop.observer.records`` immediately after ``loop.run()``
returns, before the next sample's ``reset()`` can erase it, and
writes one JSONL envelope per sample/attempt. That is the whole
connection point, and it is why no agent/config edit was needed
for this first version. A future ``lifemate/run.py`` subcommand
that reuses this module still needs an L4 file lock for run.py.

Usage (run from the repo root, or any cwd — paths are explicit):

  # CPU, synthetic, no dataset needed (real AgentLoop + real
  # observer/adapter, synthetic env/sample/generator, labelled as such):
  python -m lifemate.shadow_export --mode scripted-test \
    --fixture <fixture.jsonl> --config <config.json> \
    --out <out.jsonl> --manifest <manifest.json>

  # Real env/sample, scripted generator (needs extracted data;
  # fails fast, NOT_RUN, when --data is absent or unreadable):
  python -m lifemate.shadow_export --mode data \
    --data <extracted train+public_test> --split public_test \
    --fixture <fixture.jsonl> --config <config.json> \
    --out <out.jsonl> --manifest <manifest.json>

Fixture format (JSONL, one line per sample/attempt):
  {"sample_id": "<id>", "transcript": "<current request>",
   "outputs": [{"name": "<tool>", "arguments": {...}}, {"stop": true}, ...]}
In scripted-test mode ``sample_id`` is only a label (the synthetic
sample id is "test-sample" in the underlying double, so the envelope
keeps the fixture sample_id as the reported id and the synthetic
flag in ``split``). In data mode ``sample_id`` must match a real
sample id in the requested split, otherwise the CLI fails fast.

Config format (JSON): any PipelineConfig fields, notably
``shadow_observer`` (bool). If ``shadow_observer`` is false the
CLI still writes envelopes with records=[] and
observer_enabled=false, but it refuses ON-mode claims: it is a
control run, not an observer run.

Envelope (schema_version "chat3-e3-1", additive derived fields
only — every field accepted by L6 for chat3-e3-1 is present with
the same meaning):
  schema_version, run_id, source_commit (base pin ff7a288e),
  code_commit (git HEAD of the checkout running the CLI, or null),
  sample_id, attempt, split, observer_enabled,
  records (exact observer records, in list order, unmutated),
  record_count, observer_error_count, observer_errors
    ([{record_index, error}]), steps_executed
    (len(submission_tool_calls)), positions ([record positions]),
  submission_tool_calls, state_hash

Record identity: (sample_id, attempt, record_index). ``position``
is NOT a unique id: it is len(prefix) at observation time, and
two failed attempts at the same evidence position share it.

Integration success (this is the gate, and it is strict):
  * OFF: records must be [], submission/state_hash are the control.
  * ON: every record must have exactly the 9 observer keys, error
    must be null, and every validated non-ask proposal must have a
    non-null baseline_decision and candidate_decision (dicts).
  * Export must equal records: json.loads(loop.observer.to_json())
    must equal the records list written to the file.
  * If any of those fails, the CLI still writes the export file
    for diagnosis, writes integration_success=false in the
    manifest, and exits with code 3. "Observer errored but the
    agent still ran" is NOT integration success.
Exit codes: 0 success, 2 usage/data/config error, 3 observer
integration failure.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lifemate.agent import AgentLoop  # noqa: E402
from lifemate.config import PipelineConfig  # noqa: E402

BASE_SOURCE_COMMIT = "ff7a288e668f37e96c03bf9318d974e3a8e6d2a4"
SCHEMA_VERSION = "chat3-e3-1"
ASK_TOOL = "sys.ask_missing_info"
RECORD_KEYS = {
    "proposal_raw", "proposal_grounded", "validation_outcome",
    "baseline_decision", "candidate_decision", "adjustments",
    "eligibility", "error", "position",
}


def _code_commit() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(Path(__file__).resolve().parent.parent),
            capture_output=True, text=True, timeout=30)
        head = out.stdout.strip()
        return head or None
    except Exception:
        return None


def _json_copy(value):
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def validate_envelope(envelope: dict) -> list[str]:
    """Return a list of integration failures (empty = success).

    This is deliberately strict: an observer error, a missing
    decision for a validated non-ask proposal, a wrong record
    schema, or a record/export mismatch all fail integration,
    even though the agent itself may have run to completion.
    """
    failures = []
    records = envelope.get("records")
    if not isinstance(records, list):
        return ["records is not a list"]
    if envelope.get("record_count") != len(records):
        failures.append("record_count does not match records")
    errors = [r for r in records if isinstance(r, dict) and r.get("error")]
    if envelope.get("observer_error_count") != len(errors):
        failures.append("observer_error_count does not match records")
    if not envelope.get("observer_enabled"):
        if records:
            failures.append("observer disabled but records are non-empty")
        return failures
    for i, rec in enumerate(records):
        if not isinstance(rec, dict):
            failures.append(f"record {i} is not an object")
            continue
        if set(rec.keys()) != RECORD_KEYS:
            failures.append(
                f"record {i} keys differ from the 9-key observer schema")
        if rec.get("error") is not None:
            failures.append(f"record {i} has observer error: {rec.get('error')}")
        grounded = rec.get("proposal_grounded")
        grounded_name = grounded.get("name") if isinstance(grounded, dict) else None
        if rec.get("validation_outcome") == "ok" and grounded_name != ASK_TOOL:
            if not isinstance(rec.get("baseline_decision"), dict):
                failures.append(f"record {i} missing baseline_decision")
            if not isinstance(rec.get("candidate_decision"), dict):
                failures.append(f"record {i} missing candidate_decision")
    return failures


class ScriptedGenerator:
    def __init__(self, outputs):
        self.outputs = [json.loads(json.dumps(o, ensure_ascii=False)) for o in outputs]
        self.index = 0
        self.prompts = []

    def __call__(self, prompt, tools):
        self.prompts.append(prompt)
        if self.index < len(self.outputs):
            out = self.outputs[self.index]
            self.index += 1
            return out
        return None


# --- Synthetic harness (scripted-test mode only, labelled as such) ---
class _FakeTurn:
    def __init__(self, role, audio_text=None, text=None, tool_calls=None, tool_results=None):
        self.role = role
        self.audio_text = audio_text
        self.text = text
        self.tool_calls = tool_calls or []
        self.tool_results = tool_results


class _FakeSample:
    def __init__(self):
        self.id = "test-sample"
        self.split = "synthetic"
        self.audio = ""
        self.context = {
            "current_time": "2026-10-30T09:00:00+07:00",
            "timezone": "Asia/Ho_Chi_Minh",
            "user_profile": {"name": "Test", "city": "HCMC"},
        }
        self.history = []
        self.audio_text = None
        self.label = None


class _FakeEnv:
    def __init__(self):
        self.calls = []

    def validate(self, name, args):
        return {"ok": True}

    def call(self, name, args):
        self.calls.append({"name": name, "arguments": dict(args)})
        if name == "contacts.search":
            return {"ok": True, "contacts": [{"id": "c_1", "name": "Bình", "phone": "0902345678"}]}
        return {"ok": True}

    def submission_line(self):
        blob = json.dumps(self.calls, sort_keys=True, ensure_ascii=False)
        return {"tool_calls": [dict(c) for c in self.calls],
                "state_hash": hashlib.sha256(blob.encode()).hexdigest()}


_FAKE_TOOLS = {
    "contacts.search": {"kind": "read", "description": "search contacts", "parameters": {"required": []}},
    "contacts.get": {"kind": "read", "description": "get contact", "parameters": {"required": ["contact_id"]}},
    "phone.call": {"kind": "write", "description": "call", "parameters": {"required": ["phone_number"]}},
    "sms.send": {"kind": "write", "description": "send sms", "parameters": {"required": ["contact_id", "content"]}},
    "tasks.add": {"kind": "write", "description": "add task", "parameters": {"required": ["title"]}},
    "sys.ask_missing_info": {"kind": "meta", "description": "ask", "parameters": {"required": ["tool_name", "params"]}},
}


def _run_one(config, tools, sample, transcript, env, outputs, *, run_id, attempt):
    loop = AgentLoop(config, tools)
    gen = ScriptedGenerator(outputs)
    submitted = loop.run(sample, transcript, env, gen)
    # Capture BEFORE anything else can reset the observer.
    records = _json_copy(loop.observer.records)
    to_json_records = json.loads(loop.observer.to_json())
    envelope = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "source_commit": BASE_SOURCE_COMMIT,
        "code_commit": _code_commit(),
        "sample_id": sample.id,
        "attempt": attempt,
        "split": getattr(sample, "split", "unknown"),
        "observer_enabled": bool(loop.observer.enabled),
        "records": records,
        "record_count": len(records),
        "observer_error_count": sum(1 for r in records if isinstance(r, dict) and r.get("error")),
        "observer_errors": [
            {"record_index": i, "error": r.get("error")}
            for i, r in enumerate(records)
            if isinstance(r, dict) and r.get("error")],
        "steps_executed": len(submitted.get("tool_calls", [])),
        "positions": [r.get("position") for r in records if isinstance(r, dict)],
        "submission_tool_calls": submitted.get("tool_calls", []),
        "state_hash": submitted.get("state_hash"),
    }
    failures = validate_envelope(envelope)
    if to_json_records != records:
        failures.append("export records differ from observer.to_json() records")
    return envelope, failures


def _load_fixture(path):
    lines = []
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        if raw.strip():
            lines.append(json.loads(raw))
    if not lines:
        raise ValueError("fixture is empty")
    for i, line in enumerate(lines):
        if "outputs" not in line or not isinstance(line["outputs"], list):
            raise ValueError(f"fixture line {i} has no outputs list")
    return lines


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="lifemate.shadow_export")
    parser.add_argument("--mode", choices=["scripted-test", "data"], required=True)
    parser.add_argument("--data", default=None)
    parser.add_argument("--split", default="public_test")
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--run-id", default="r2-g4")
    args = parser.parse_args(argv)

    try:
        config = PipelineConfig.from_json(args.config)
        fixture = _load_fixture(args.fixture)
    except (ValueError, FileNotFoundError, KeyError, AssertionError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    envelopes = []
    all_failures = []
    try:
        if args.mode == "scripted-test":
            for attempt, line in enumerate(fixture):
                sample = _FakeSample()
                # The envelope reports the fixture id, not the double's
                # internal id, so a fixture with several samples stays
                # distinguishable. The underlying sample is synthetic.
                env = _FakeEnv()
                envelope, failures = _run_one(
                    config, _FAKE_TOOLS, sample,
                    line.get("transcript", "Gọi số 0902345678 giúp tôi"),
                    env, line["outputs"], run_id=args.run_id, attempt=attempt)
                envelope["sample_id"] = line.get("sample_id", sample.id)
                envelope["split"] = "synthetic"
                envelopes.append(envelope)
                all_failures.extend(f"attempt {attempt}: {f}" for f in failures)
        else:
            if not args.data:
                print("error: --mode data requires --data", file=sys.stderr)
                return 2
            from lifemate.adapter import ZaicEnv  # noqa: E402
            from lifemate.loader import catalog_tools_for_sample, load_catalog, load_split  # noqa: E402
            root = Path(args.data)
            if not (root / args.split).is_dir():
                print(f"error: data split directory not found: {root / args.split}", file=sys.stderr)
                return 2
            catalog = load_catalog(root, args.split)
            samples = {s.id: s for s in load_split(root, args.split)}
            for attempt, line in enumerate(fixture):
                sid = line.get("sample_id")
                if sid not in samples:
                    print(f"error: sample id not found in split {args.split}: {sid}", file=sys.stderr)
                    return 2
                sample = samples[sid]
                tools = catalog_tools_for_sample(catalog, sample)
                env = ZaicEnv(root, args.split, sample.id)
                envelope, failures = _run_one(
                    config, tools, sample,
                    line.get("transcript", ""), env, line["outputs"],
                    run_id=args.run_id, attempt=attempt)
                envelopes.append(envelope)
                all_failures.extend(f"attempt {attempt}: {f}" for f in failures)
    except Exception as exc:  # data/model/generator errors are not integration success
        print(f"error: {exc}", file=sys.stderr)
        return 2

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fout:
        for envelope in envelopes:
            fout.write(json.dumps(envelope, ensure_ascii=False) + "\n")
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "run_id": args.run_id,
        "source_commit": BASE_SOURCE_COMMIT,
        "code_commit": _code_commit(),
        "mode": args.mode,
        "split": args.split if args.mode == "data" else "synthetic",
        "config_path": args.config,
        "fixture_path": args.fixture,
        "out_path": str(out_path),
        "envelope_count": len(envelopes),
        "total_records": sum(e["record_count"] for e in envelopes),
        "total_observer_errors": sum(e["observer_error_count"] for e in envelopes),
        "integration_success": not all_failures,
        "failures": all_failures,
    }
    Path(args.manifest).parent.mkdir(parents=True, exist_ok=True)
    Path(args.manifest).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"shadow-export: {len(envelopes)} envelopes -> {out_path} "
          f"(records={manifest['total_records']}, "
          f"observer_errors={manifest['total_observer_errors']}, "
          f"integration_success={manifest['integration_success']})")
    if all_failures:
        for failure in all_failures:
            print(f"  integration failure: {failure}")
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
