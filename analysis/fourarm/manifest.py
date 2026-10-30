"""Frozen-benchmark manifest gate (stdlib only).

A real four-arm run accepts ONLY a stratified-frozen manifest: the
same freeze rule as Tier 1a's refreeze.py (dev only, stratum minimum
20, ids + sha only -- no transcript, no gold call, no wav in the
manifest itself). The manifest is produced outside this harness
(Tier 1a refreeze, coordinator-approved); this module only gates it,
never invents it.

Mock smoke uses a separate status, "mock-smoke-only", with synthetic
ids. The real-run gate refuses that status, and the mock gate refuses
a real manifest, so a mock id list can never silently become a
benchmark and a real manifest can never be run as a mock.

Manifest shape:
    {"status": "stratified-frozen" | "mock-smoke-only",
     "ids": [...], "ids_sha256": sha256(json.dumps(ids)),
     "stratum_selected_counts": {...} (real only, optional here),
     "coverage_shortfall": [...] (real only, reported not hidden)}
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def ids_sha256(ids):
    return hashlib.sha256(
        json.dumps(ids, ensure_ascii=False).encode("utf-8")).hexdigest()


def load_manifest(path):
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    ids = doc["ids"]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate ids in manifest")
    return doc


def validate_manifest(path, source_tree, allow_mock=False):
    """Gate a manifest against the pinned split file. Raises
    SystemExit with a precise reason on any failure; returns a report
    dict on success. Held-out ids are always refused, in both modes.
    When allow_mock is False, only status == 'stratified-frozen' and
    a recomputed ids_sha256 pass."""
    doc = load_manifest(path)
    split_path = Path(source_tree) / "lifemate/splits/train_dev_heldout.json"
    if not split_path.exists():
        raise SystemExit(f"split file not found at {split_path}; "
                         "real-run gate cannot verify dev/held-out")
    split = json.loads(split_path.read_text(encoding="utf-8"))
    dev = {k for k, v in split.items() if v == "dev"}
    held = {k for k, v in split.items() if v == "heldout"}
    leak = sorted(set(doc["ids"]) & held)
    if leak:
        raise SystemExit(f"held-out ids leaked into manifest: {leak}")
    status = doc.get("status")
    if allow_mock:
        if status != "mock-smoke-only":
            raise SystemExit(
                f"mock gate refuses manifest status {status!r}; "
                "mock smoke takes only mock-smoke-only manifests")
        if not set(doc["ids"]) <= set(doc.get("mock_ids_allowed", doc["ids"])):
            raise SystemExit("mock manifest ids outside its own mock set")
        # Mock ids are synthetic and are not in the real split; that
        # is expected here and is exactly why this gate never runs
        # a real benchmark.
        return {"manifest": str(path), "status": status,
                "n": len(doc["ids"]), "ids_sha256": doc.get("ids_sha256"),
                "mode": "mock"}
    if status != "stratified-frozen":
        raise SystemExit(
            f"real-run gate refuses manifest status {status!r}; "
            "run Tier 1a refreeze.py first and pass a stratified-frozen "
            "manifest (the provisional hash-only set is never accepted)")
    if doc.get("ids_sha256") != ids_sha256(doc["ids"]):
        raise SystemExit("manifest ids_sha256 mismatch: manifest was "
                         "edited after freezing; refuse to run")
    if not set(doc["ids"]) <= dev:
        raise SystemExit("manifest ids must all be dev ids")
    return {"manifest": str(path), "status": status, "n": len(doc["ids"]),
            "ids_sha256": doc["ids_sha256"],
            "split_dev": len(dev), "split_heldout": len(held),
            "stratum_selected_counts": doc.get("stratum_selected_counts"),
            "coverage_shortfall": doc.get("coverage_shortfall", []),
            "mode": "real"}
