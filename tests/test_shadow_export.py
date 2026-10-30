#!/usr/bin/env python3
"""Fresh-process + OFF/ON tests for lifemate.shadow_export (RUN2, R2-G4).

Synthetic only, CPU only, no dataset, no model, no GPU.
Run from the repo root:
    python3 tests/test_shadow_export.py

The subprocess tests are the point: the CLI must work in a fresh
interpreter, cwd = repo root, NO PYTHONPATH, NO lifemate/ entry
in sys.path, with the lifemate.* package identity (the same
contract pinned by tests/test_observer.py for the observer).
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lifemate.shadow_export import (  # noqa: E402
    BASE_SOURCE_COMMIT, RECORD_KEYS, validate_envelope,
)

FIXTURE = ROOT / "analysis/chat3/r2-g4/fixture.jsonl"
CONFIG_ON = ROOT / "analysis/chat3/r2-g4/config_on.json"
CONFIG_OFF = ROOT / "analysis/chat3/r2-g4/config_off.json"

_CHILD_PACKAGE = r'''
import sys
assert not any(
    p and (p.rstrip("/") == "lifemate"
           or p.rstrip("/").endswith("/lifemate"))
    for p in sys.path), sys.path
from lifemate.shadow_export import BASE_SOURCE_COMMIT
assert BASE_SOURCE_COMMIT == "ff7a288e668f37e96c03bf9318d974e3a8e6d2a4"
assert "lifemate.shadow_export" in sys.modules
assert "shadow_export" not in sys.modules, "dual module identity"
print("package-ok")
'''


def run_cli(config, out, manifest, tmp):
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    proc = subprocess.run(
        [sys.executable, "-m", "lifemate.shadow_export",
         "--mode", "scripted-test",
         "--fixture", str(FIXTURE), "--config", str(config),
         "--out", str(out), "--manifest", str(manifest),
         "--run-id", "r2-g4-test"],
        cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=180)
    return proc


def read_jsonl(path):
    return [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]


class TestShadowExportFreshProcess(unittest.TestCase):
    def test_package_import_in_fresh_process(self):
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        proc = subprocess.run(
            [sys.executable, "-c", _CHILD_PACKAGE],
            cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=180)
        self.assertEqual(proc.returncode, 0,
                         f"package import failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")
        self.assertIn("package-ok", proc.stdout)

    def test_off_on_export_matches_records_and_behaviour(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            off_out, off_man = tmp / "off.jsonl", tmp / "off.manifest.json"
            on_out, on_man = tmp / "on.jsonl", tmp / "on.manifest.json"
            off = run_cli(CONFIG_OFF, off_out, off_man, tmp)
            self.assertEqual(off.returncode, 0, f"OFF CLI failed:\n{off.stdout}\n{off.stderr}")
            on = run_cli(CONFIG_ON, on_out, on_man, tmp)
            self.assertEqual(on.returncode, 0, f"ON CLI failed:\n{on.stdout}\n{on.stderr}")
            off_env = read_jsonl(off_out)
            on_env = read_jsonl(on_out)
            self.assertEqual(len(off_env), 3)
            self.assertEqual(len(on_env), 3)
            off_man_data = json.loads(off_man.read_text(encoding="utf-8"))
            on_man_data = json.loads(on_man.read_text(encoding="utf-8"))
            self.assertTrue(off_man_data["integration_success"])
            self.assertTrue(on_man_data["integration_success"])
            self.assertEqual(on_man_data["source_commit"], BASE_SOURCE_COMMIT)
            for off_e, on_e in zip(off_env, on_env):
                self.assertEqual(off_e["submission_tool_calls"], on_e["submission_tool_calls"])
                self.assertEqual(off_e["state_hash"], on_e["state_hash"])
                self.assertEqual(off_e["records"], [])
                self.assertFalse(off_e["observer_enabled"])
                self.assertTrue(on_e["observer_enabled"])
                self.assertEqual(on_e["record_count"], len(on_e["records"]))
                self.assertEqual(on_e["observer_error_count"], 0)
                for rec in on_e["records"]:
                    self.assertEqual(set(rec.keys()), RECORD_KEYS)
                    self.assertIsNone(rec["error"])
            # test-1: search + call, both validated non-ask -> decisions present
            recs1 = on_env[0]["records"]
            self.assertEqual(len(recs1), 2)
            for rec in recs1:
                self.assertIsInstance(rec["baseline_decision"], dict)
                self.assertIsInstance(rec["candidate_decision"], dict)
            # test-2: ask -> decision null (gate scope exclusion, not a failure)
            recs2 = on_env[1]["records"]
            self.assertEqual(len(recs2), 1)
            self.assertIsNone(recs2[0]["baseline_decision"])
            self.assertIsNone(recs2[0]["candidate_decision"])
            # test-3: invalid generation -> validation_outcome invalid, decision null
            recs3 = on_env[2]["records"]
            self.assertEqual(len(recs3), 1)
            self.assertEqual(recs3[0]["validation_outcome"], "invalid")
            self.assertIsNone(recs3[0]["baseline_decision"])

    def test_observer_error_is_not_integration_success(self):
        # validate_envelope is the gate used by the CLI. An error
        # record must fail it even if the agent ran to completion.
        bad = {
            "observer_enabled": True, "record_count": 1,
            "observer_error_count": 1,
            "records": [{
                "proposal_raw": {"name": "phone.call", "arguments": {}},
                "proposal_grounded": {"name": "phone.call", "arguments": {}},
                "validation_outcome": "ok",
                "baseline_decision": None, "candidate_decision": None,
                "adjustments": [], "eligibility": None,
                "error": "RuntimeError: decide failed", "position": 0,
            }],
        }
        failures = validate_envelope(bad)
        self.assertTrue(failures, "observer error must fail integration")
        good = {
            "observer_enabled": True, "record_count": 1,
            "observer_error_count": 0,
            "records": [{
                "proposal_raw": {"name": "phone.call", "arguments": {}},
                "proposal_grounded": {"name": "phone.call", "arguments": {}},
                "validation_outcome": "ok",
                "baseline_decision": {"fired": False, "applicable": True, "reason": "x"},
                "candidate_decision": {"fired": False, "applicable": True},
                "adjustments": [], "eligibility": None,
                "error": None, "position": 0,
            }],
        }
        self.assertEqual(validate_envelope(good), [])

    def test_cli_exits_3_on_observer_error(self):
        # End-to-end gate, in-process: force the adapter decide() to
        # raise, so every validated proposal becomes an error record.
        # The agent still runs to completion, but the CLI must NOT
        # report integration success (exit 3, manifest false).
        import lifemate.lifemate_observer as observer_module
        from lifemate.shadow_export import main as cli_main
        old = observer_module._decide_cache.get("fn")

        def raiser(*args, **kwargs):
            raise RuntimeError("forced decide failure for R2-G4 test")

        observer_module._decide_cache["fn"] = raiser
        try:
            with tempfile.TemporaryDirectory() as tmp:
                tmp = Path(tmp)
                out, man = tmp / "err.jsonl", tmp / "err.manifest.json"
                code = cli_main([
                    "--mode", "scripted-test",
                    "--fixture", str(FIXTURE), "--config", str(CONFIG_ON),
                    "--out", str(out), "--manifest", str(man),
                    "--run-id", "r2-g4-test-error"])
                self.assertEqual(code, 3, "observer error must exit 3, not 0")
                manifest = json.loads(man.read_text(encoding="utf-8"))
                self.assertFalse(manifest["integration_success"])
                self.assertGreater(manifest["total_observer_errors"], 0)
                envelopes = read_jsonl(out)
                self.assertTrue(any(e["observer_error_count"] > 0 for e in envelopes))
        finally:
            observer_module._decide_cache["fn"] = old


def _base_record():
    return {
        "proposal_raw": {"name": "phone.call", "arguments": {}},
        "proposal_grounded": {"name": "phone.call", "arguments": {}},
        "validation_outcome": "ok",
        "baseline_decision": {"fired": True, "applicable": True, "reason": "x"},
        "candidate_decision": {"fired": True, "applicable": True},
        "adjustments": [], "eligibility": None,
        "error": None, "position": 0,
    }


def _envelope_for(records):
    return {
        "observer_enabled": True, "record_count": len(records),
        "observer_error_count": sum(
            1 for r in records if r.get("error")),
        "records": records,
    }


_UNKNOWN_PENDING_SD = {
    "decision": "unknown_pending",
    "unknown_kind": "question_after_positive",
    "active_status": "pending_unproven",
    "blocked_subtype": "question",
    "mismatch": "unknown_pending",
    "last_event": {"kind": "positive_request", "turn_position": 0,
                   "evidence": "history_text"},
}

_MISMATCH_SD = {
    "decision": "mismatch",
    "active_status": "discharged",
    "blocked_subtype": "completion",
    "mismatch": "blocked_request",
    "last_event": {"kind": "positive_request", "turn_position": 0,
                   "evidence": "history_text"},
}


class TestSelectionDecisionValidator(unittest.TestCase):
    """R4 export-validator: 9-key old records and valid 10-key
    selection_decision records pass; anything else fails.

    The two valid shapes are the exact dicts the gates adapter
    writes into notes["selection_decision"] (see the backfill-log
    report §3): unknown_pending carries unknown_kind, mismatch
    never does. The JSON round-trip test proves an UNKNOWN
    record written to an export file still carries unknown_kind
    and last_event when read back -- the fields the strict
    9-key validator used to discard by rejection.
    """

    def test_old_9_key_record_still_passes(self):
        self.assertEqual(validate_envelope(_envelope_for([_base_record()])), [])

    def test_unknown_pending_10_key_passes(self):
        rec = _base_record()
        rec["selection_decision"] = dict(_UNKNOWN_PENDING_SD)
        self.assertEqual(validate_envelope(_envelope_for([rec])), [])

    def test_mismatch_10_key_passes(self):
        rec = _base_record()
        rec["selection_decision"] = dict(_MISMATCH_SD)
        self.assertEqual(validate_envelope(_envelope_for([rec])), [])

    def test_mismatch_with_last_event_none_passes(self):
        # Adapter writes last_event=None when no decisive
        # history event exists (e.g. question over an absent
        # positive); that is a real adapter shape, not an error.
        rec = _base_record()
        sd = dict(_MISMATCH_SD)
        sd["last_event"] = None
        rec["selection_decision"] = sd
        self.assertEqual(validate_envelope(_envelope_for([rec])), [])

    def test_strange_10th_key_rejected(self):
        rec = _base_record()
        rec["note"] = "stray string, not structured evidence"
        self.assertTrue(validate_envelope(_envelope_for([rec])))

    def test_strange_key_alongside_valid_selection_decision_rejected(self):
        rec = _base_record()
        rec["selection_decision"] = dict(_UNKNOWN_PENDING_SD)
        rec["note"] = "extra key is still a schema violation"
        self.assertTrue(validate_envelope(_envelope_for([rec])))

    def test_selection_decision_wrong_type_rejected(self):
        for bad in ("unknown_pending", ["unknown_pending"], None, 42, True):
            with self.subTest(bad=bad):
                rec = _base_record()
                rec["selection_decision"] = bad
                self.assertTrue(validate_envelope(_envelope_for([rec])))

    def test_selection_decision_missing_decision_rejected(self):
        rec = _base_record()
        sd = dict(_UNKNOWN_PENDING_SD)
        del sd["decision"]
        rec["selection_decision"] = sd
        self.assertTrue(validate_envelope(_envelope_for([rec])))

    def test_selection_decision_unknown_decision_value_rejected(self):
        rec = _base_record()
        sd = dict(_UNKNOWN_PENDING_SD)
        sd["decision"] = "passed"
        rec["selection_decision"] = sd
        self.assertTrue(validate_envelope(_envelope_for([rec])))

    def test_unknown_pending_without_unknown_kind_rejected(self):
        rec = _base_record()
        sd = dict(_UNKNOWN_PENDING_SD)
        del sd["unknown_kind"]
        rec["selection_decision"] = sd
        self.assertTrue(validate_envelope(_envelope_for([rec])))

    def test_mismatch_with_unknown_kind_rejected(self):
        rec = _base_record()
        sd = dict(_MISMATCH_SD)
        sd["unknown_kind"] = "question_after_positive"
        rec["selection_decision"] = sd
        self.assertTrue(validate_envelope(_envelope_for([rec])))

    def test_selection_decision_unknown_field_rejected(self):
        rec = _base_record()
        sd = dict(_UNKNOWN_PENDING_SD)
        sd["company"] = "stray field inside selection_decision"
        rec["selection_decision"] = sd
        self.assertTrue(validate_envelope(_envelope_for([rec])))

    def test_malformed_last_event_rejected(self):
        for bad_event in (
                {"kind": "positive_request", "turn_position": "0",
                 "evidence": "history_text"},
                {"kind": "positive_request", "turn_position": 0},
                "positive_request",
        ):
            with self.subTest(bad_event=bad_event):
                rec = _base_record()
                sd = dict(_UNKNOWN_PENDING_SD)
                sd["last_event"] = bad_event
                rec["selection_decision"] = sd
                self.assertTrue(validate_envelope(_envelope_for([rec])))

    def test_error_and_decision_checks_still_apply_to_10_key(self):
        # Validator is not loosened elsewhere: a 10-key record
        # with an observer error, or missing decisions for a
        # validated non-ask proposal, still fails.
        rec = _base_record()
        rec["selection_decision"] = dict(_UNKNOWN_PENDING_SD)
        rec["error"] = "RuntimeError: decide failed"
        self.assertTrue(validate_envelope(_envelope_for([rec])))
        rec = _base_record()
        rec["selection_decision"] = dict(_MISMATCH_SD)
        rec["baseline_decision"] = None
        self.assertTrue(validate_envelope(_envelope_for([rec])))

    def test_unknown_record_json_round_trip_keeps_structured_fields(self):
        rec = _base_record()
        rec["selection_decision"] = dict(_UNKNOWN_PENDING_SD)
        envelope = _envelope_for([rec])
        restored = json.loads(json.dumps(envelope, ensure_ascii=False))
        self.assertEqual(validate_envelope(restored), [])
        sd = restored["records"][0]["selection_decision"]
        self.assertEqual(sd["unknown_kind"], "question_after_positive")
        self.assertEqual(sd["last_event"],
                         {"kind": "positive_request", "turn_position": 0,
                          "evidence": "history_text"})
        self.assertEqual(sd["decision"], "unknown_pending")


if __name__ == "__main__":
    unittest.main(verbosity=2)
