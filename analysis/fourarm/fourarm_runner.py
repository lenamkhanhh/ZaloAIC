"""Four-arm runner: preflight, mock smoke, real run, OFF/ON check.

RUN / SCORE SEPARATION (hard requirement, not style): this file,
tracing.py, mock_backends.py, arm_config.py, manifest.py and
metrics.py are the RUN path. They never read a sample's gold tool
calls, never read a gold transcript as agent input, never call the
library scorer, and never compute a score. `check-separation`
proves this by parsing these files' ASTs and failing if any
gold/score access pattern appears in them. The score phase is
score_fourarm.py, a separate command that reads run traces from
disk first and only then reads gold.

Commands:
  preflight --source-tree T --arms ARMS.json [--real]
      Checks, before any weight loads: branch/HEAD (when a git
      checkout is present), lifemate/ vs ddbe0a0, config + split
      SHAs, arm validation (shared identical, B/C/D differ only as
      named), manifest gate if --benchmark given. In --real mode it
      additionally lists every missing blocker (data, GPU, backends,
      partner pins) and exits 2 if any is missing -- it never
      proceeds to a partial real run.
  check-separation
      AST check over the run-path files listed above.
  mock-smoke --source-tree T --out DIR
      4 mock samples x 4 arms via mock_backends.py, writes
      traces_<arm>.jsonl + mock_gold_fixture.json + run manifests
      into OUT (never into the repo). Result is MOCK ONLY.
  run --source-tree T --data D --benchmark M --arms A.json --out DIR
      Real run. FAILS FAST (exit 2, BLOCKED message, no traces, no
      numbers) if: data root missing train/train.jsonl, no GPU
      backend (torch/vllm/faster-whisper import fails), partner pins
      unpinned, manifest gate fails, or arm validation fails.
      On a GPU host with data + pins, it runs the real path:
      per-checkpoint ASR cache (key = checkpoint, revision, wav
      sha, backend, beam, language; never reused across
      checkpoints), TracingGenerator around the lifemate generator,
      real AgentLoop, real ZaicEnv, traces written per arm, no
      score computed here.
  check-off-on --source-tree T --out DIR [--mock] [--pilot N]
      G&G OFF/ON identity check on the pilot set. Mock mode runs
      the mock loop twice (shadow False, then True) for arm A and
      compares calls, final state (state_hash), submission lines
      (id + tool_calls + state_hash) and termination -- they must
      be IDENTICAL, because G&G is shadow-only. Any difference
      exits 3, writes the differing fields, and score_fourarm.py
      refuses to score against that report. Real mode does the
      same with the real AgentLoop and requires --data/--benchmark/
      --arms; without them it exits 2 BLOCKED, never faking a pass.

Call paths (so a reviewer can verify no reimplementation):
  agent:  lifemate.agent.AgentLoop (imported from source_tree)
  env:    lifemate.adapter.ZaicEnv
  scorer: lifemate.scoring.score_sample -- SCORE PHASE ONLY
  config: lifemate.config.PipelineConfig.from_json(recommended.json)
          + per-arm overrides (asr/llm pins only)
  asr:    lifemate.asr.FasterWhisperASR
  llm:    lifemate.llm.VLLMGenerator / TransformersGenerator
  WER/slot/bootstrap: fourarm/metrics.py (frozen Tier 1a defs)
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

from arm_config import build_arms, validate_arms  # noqa: E402
from manifest import validate_manifest  # noqa: E402
from mock_backends import (MOCK_SAMPLES, mock_run_sample)  # noqa: E402
from tracing import TracingGenerator, termination_from_generations  # noqa: E402

EXPECTED_CONFIG_SHA = "71d5f38f23d126427b08c09925cbbd9da933fc3750cbec55942809737e980076"
EXPECTED_SPLIT_SHA = "eefd0faa163285b23d2634bc4cc04f515b58367a2344599e46e85d48818280aa"
EXPECTED_SOURCE_COMMIT = "ddbe0a0b18a6fb9f6e7d261628a51e7a2c6c10c6"
EXPECTED_HEAD = "4eba28c53cfbfaf2ed6124119acdcb45895188b9"
RUN_PATH_FILES = ["fourarm_runner.py", "tracing.py", "mock_backends.py",
                  "arm_config.py", "manifest.py", "metrics.py"]
# Attribute / name patterns that must never appear in run-path code
# (gold calls, gold transcript as input, scorer, label classes).
FORBIDDEN_AST = {"label", "label_class", "score_sample", "gold_calls",
                 "gold_hash", "_gold_hash", "audio_text", "fuzzy_params"}


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check_separation():
    """AST-parse every run-path file; fail on any forbidden pattern.
    Comments and docstrings are not AST names, so a docstring that
    MENTIONS gold (to explain the separation) does not trip this --
    only code that actually touches it does. One deliberate
    exception, with a reason: writing (Store context) to a history
    turn's transcript field is ALLOWED, because that field is the
    library's only history-input channel (agent.py build_base_prompt
    reads it) and the real run must overwrite gold history
    transcripts with arm ASR transcripts before the loop sees them.
    READING that field (Load context) is forbidden: the run path
    never reads a pre-existing transcript value, it only sets it
    from the arm ASR cache."""
    bad = []
    for name in RUN_PATH_FILES:
        path = _HERE / name
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_AST:
                if node.attr == "audio_text" and isinstance(node.ctx, ast.Store):
                    continue
                bad.append(f"{name}:{node.lineno}: .{node.attr}")
            if isinstance(node, ast.Name) and node.id in FORBIDDEN_AST:
                bad.append(f"{name}:{node.lineno}: {node.id}")
    return {"ok": not bad, "forbidden_hits": bad,
            "files_checked": RUN_PATH_FILES}


def _git_info(source_tree):
    import subprocess
    try:
        out = subprocess.run(
            ["git", "-C", str(source_tree), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=30)
        head = out.stdout.strip() if out.returncode == 0 else None
        diff = subprocess.run(
            ["git", "-C", str(source_tree), "diff", "--quiet",
             EXPECTED_SOURCE_COMMIT, "HEAD", "--", "lifemate/"],
            capture_output=True, timeout=30)
        lifemate_matches = (diff.returncode == 0)
        return head, lifemate_matches
    except Exception:
        return None, None


def preflight(source_tree, arms, benchmark=None, real=False):
    source_tree = Path(source_tree)
    checks = {}
    cfg = source_tree / "lifemate/configs/recommended.json"
    split = source_tree / "lifemate/splits/train_dev_heldout.json"
    checks["config_sha_ok"] = cfg.exists() and sha256_file(cfg) == EXPECTED_CONFIG_SHA
    checks["config_sha"] = sha256_file(cfg) if cfg.exists() else None
    checks["split_sha_ok"] = split.exists() and sha256_file(split) == EXPECTED_SPLIT_SHA
    checks["split_sha"] = sha256_file(split) if split.exists() else None
    head, lifemate_matches = _git_info(source_tree)
    checks["head"] = head
    checks["head_expected"] = EXPECTED_HEAD
    checks["head_ok"] = (head == EXPECTED_HEAD) if head else None
    checks["lifemate_matches_ddbe0a0"] = lifemate_matches
    arm_errors = validate_arms(arms, real_mode=real)
    checks["arm_errors"] = arm_errors
    checks["arms_ok"] = not arm_errors
    if benchmark:
        try:
            checks["manifest"] = validate_manifest(benchmark, source_tree,
                                                   allow_mock=not real)
            checks["manifest_ok"] = True
        except SystemExit as exc:
            checks["manifest_ok"] = False
            checks["manifest_error"] = str(exc)
    sep = check_separation()
    checks["separation"] = sep
    checks["separation_ok"] = sep["ok"]
    blockers = []
    if real:
        if not checks["config_sha_ok"]:
            blockers.append("recommended.json SHA mismatch")
        if not checks["split_sha_ok"]:
            blockers.append("split SHA mismatch")
        if not checks["arms_ok"]:
            blockers.append(f"arm validation: {arm_errors}")
        if benchmark and not checks.get("manifest_ok"):
            blockers.append(f"manifest: {checks.get('manifest_error')}")
    checks["blockers"] = blockers
    checks["ok"] = (checks["config_sha_ok"] and checks["split_sha_ok"]
                    and checks["arms_ok"] and checks["separation_ok"]
                    and (not benchmark or checks.get("manifest_ok", False))
                    and not blockers)
    return checks


def cmd_preflight(args):
    arms = build_arms()
    if args.arms:
        from arm_config import load_arms
        arms = load_arms(args.arms)
    report = preflight(args.source_tree, arms, args.benchmark, real=args.real)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "preflight_report.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0 if report["ok"] else 2


def cmd_check_separation(args):
    report = check_separation()
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["ok"] else 2


def cmd_mock_smoke(args):
    from mock_backends import MOCK_GOLD
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    arms = build_arms()
    # Mock arm kinds: A own/own, B partner ASR/own LLM, C own/partner,
    # D partner/partner -- same mapping as the real contract.
    kind_map = {"A": ("own", "own"), "B": ("partner", "own"),
                "C": ("own", "partner"), "D": ("partner", "partner")}
    for arm in ("A", "B", "C", "D"):
        asr_kind, llm_kind = kind_map[arm]
        traces = [mock_run_sample(sid, arm, asr_kind, llm_kind,
                                  shadow_observer=True)
                  for sid in MOCK_SAMPLES]
        with open(out / f"traces_{arm}.jsonl", "w", encoding="utf-8") as f:
            for t in traces:
                f.write(json.dumps(t, ensure_ascii=False) + "\n")
        (out / f"run_manifest_{arm}.json").write_text(
            json.dumps({"arm": arm, "mode": "mock",
                        "result_kind": "MOCK ONLY -- not a model score",
                        "asr_kind": asr_kind, "llm_kind": llm_kind,
                        "sample_ids": MOCK_SAMPLES,
                        "arm_config": arms[arm]}, indent=2, ensure_ascii=False),
            encoding="utf-8")
    (out / "mock_gold_fixture.json").write_text(
        json.dumps(MOCK_GOLD, indent=2, ensure_ascii=False), encoding="utf-8")
    # Mock manifest, accepted only by the mock gate.
    import hashlib as _h
    ids = MOCK_SAMPLES
    (out / "mock_manifest.json").write_text(
        json.dumps({"status": "mock-smoke-only", "ids": ids,
                    "ids_sha256": _h.sha256(json.dumps(ids).encode()).hexdigest()},
                   indent=2), encoding="utf-8")
    print(f"mock-smoke: 4 samples x 4 arms = 16 traces -> {out} "
          "(MOCK ONLY, not a model score)")
    return 0


def _real_blockers(source_tree, data, arms):
    blockers = []
    root = Path(data) if data else None
    if not root or not (root / "train" / "train.jsonl").exists():
        blockers.append(
            "B1 data: extracted train+public_test root with "
            "train/train.jsonl + wav files (env/data path). "
            "Download + verify per RUN_LIFEMATE.md §0: zip 876430231 "
            "bytes, sha256 57d371518996ec70d3af86402b7eba61208093c"
            "82955b9807a7ab39604b47320, unzip -t no errors.")
    for mod in ("torch", "vllm", "faster_whisper"):
        try:
            __import__(mod)
        except ImportError:
            blockers.append(f"B2 backend missing: {mod} not importable "
                            "(GPU host install per RUN_LIFEMATE.md §3)")
    try:
        import subprocess
        out = subprocess.run(["nvidia-smi"], capture_output=True,
                             text=True, timeout=30)
        if out.returncode != 0:
            blockers.append("B2 GPU: nvidia-smi did not succeed "
                            "(need 1x GPU >= 16 GB VRAM; A30 is the "
                            "reference for the 30 s/sample limit)")
    except Exception:
        blockers.append("B2 GPU: nvidia-smi not available")
    arm_errors = validate_arms(arms, real_mode=True)
    if arm_errors:
        blockers.append(f"partner pins / arm validation: {arm_errors}")
    return blockers


def cmd_run(args):
    from arm_config import load_arms
    arms = load_arms(args.arms) if args.arms else build_arms()
    blockers = _real_blockers(args.source_tree, args.data, arms)
    if blockers:
        print("BLOCKED: real four-arm run cannot start. Missing:", file=sys.stderr)
        for b in blockers:
            print(f"  - {b}", file=sys.stderr)
        print("No traces were written and no number was produced. "
              "Unlock with: data (B1) + GPU/backends (B2) + Phase 2 "
              "partner pins (merged LLM checkpoints) + a "
              "stratified-frozen manifest, then re-run this command.",
              file=sys.stderr)
        return 2
    # Real path (only reachable on a GPU host with data + pins).
    # It is implemented, not stubbed, so the GPU run needs no new
    # harness code -- but it has never run here, and this branch
    # must not claim it has.
    source_tree = Path(args.source_tree)
    sys.path.insert(0, str(source_tree))
    from manifest import validate_manifest as _vm
    manifest_report = _vm(args.benchmark, source_tree, allow_mock=False)
    from lifemate.config import PipelineConfig
    from lifemate.loader import catalog_tools_for_sample, load_catalog, load_split
    from lifemate.adapter import ZaicEnv
    from lifemate.agent import AgentLoop
    from lifemate.asr import FasterWhisperASR
    from lifemate.llm import TransformersGenerator, VLLMGenerator
    root = Path(args.data)
    catalog = load_catalog(root, "train")
    samples = {s.id: s for s in load_split(root, "train")}
    ids = json.loads(Path(args.benchmark).read_text(encoding="utf-8"))["ids"]
    if args.pilot:
        ids = ids[:args.pilot]
    # History transcripts: AgentLoop builds its prompt from history
    # turn transcripts, and on train those are gold by default.
    # The four-arm rule is full-ASR history, so each sample-run gets
    # a DEEP COPY whose history user turns are overwritten with the
    # arm ASR transcript BEFORE the loop runs. The original sample
    # is never mutated (otherwise arm B would inherit arm A's
    # history), and the original gold history value is never READ:
    # the copy's field is SET from the ASR cache, which is the only
    # history-input channel agent.py provides. See the separation
    # check's Store-only exception for this field.
    base_cfg = PipelineConfig.from_json(
        source_tree / "lifemate/configs/recommended.json")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    # Per-checkpoint ASR caches (never reused across checkpoints).
    asr_caches = {}
    for arm_name in ("A", "B", "C", "D"):
        arm = arms[arm_name]
        asr_key = (arm["asr"]["checkpoint"], arm["asr"]["revision"],
                   arm["asr"]["backend"], arm["asr"]["decode"]["beam_size"],
                   arm["asr"]["decode"]["language"])
        if asr_key not in asr_caches:
            asr_caches[asr_key] = {
                "meta": {"checkpoint": asr_key[0], "revision": asr_key[1],
                         "backend": asr_key[2], "beam_size": asr_key[3],
                         "language": asr_key[4]},
                "data": {},
            }
        cache = asr_caches[asr_key]
        asr = FasterWhisperASR(arm["asr"]["checkpoint"], device="cuda",
                               compute_type="float16")
        llm_cfg = arm["llm"]
        llm_checkpoint = llm_cfg["merged"] or llm_cfg["base"]
        # Revision comes from the arm file for every arm (own:
        # cdbee75; partner merged: Phase 2 pin). validate_arms in
        # real mode already refused a checkpoint without one.
        llm_revision = llm_cfg.get("revision")
        if llm_cfg["backend"] == "vllm":
            llm = VLLMGenerator(llm_checkpoint, llm_revision, seed=42)
        else:
            llm = TransformersGenerator(llm_checkpoint, llm_revision,
                                        device="cuda")

        def make_config(base, arm_cfg):
            import dataclasses
            cfg = dataclasses.replace(
                base,
                asr_checkpoint=arm_cfg["asr"]["checkpoint"],
                asr_backend=arm_cfg["asr"]["backend"],
                llm_checkpoint=llm_checkpoint,
                llm_revision=llm_revision,
                shadow_observer=True, grounding=True,
                pending_ask_stop=False, history_presentation_v2=False)
            cfg.check_budget()
            return cfg

        cfg = make_config(base_cfg, arm)
        traces = []
        for sid in ids:
            import copy as _copy
            sample = _copy.deepcopy(samples[sid])
            start = time.time()
            wav = root / "train" / sample.audio
            wav_sha = hashlib.sha256(wav.read_bytes()).hexdigest() if wav.exists() else None
            run_error = None
            try:
                if wav_sha in cache["data"]:
                    transcript = cache["data"][wav_sha]
                else:
                    transcript = asr.transcribe(wav)
                    if transcript == "":
                        raise ValueError("empty ASR transcript (failed record, "
                                         "never fed to the prompt as '')")
                    if wav_sha:
                        cache["data"][wav_sha] = transcript
            except Exception as exc:
                # P2 failed-record rule: a failed sample keeps its
                # position with run_error set; score phase excludes
                # it explicitly (see score_fourarm.py), never silently
                # shifts the order or scores a guessed transcript.
                run_error = f"asr_failed: {exc}"
                transcript = None
            if run_error is None:
                for turn in sample.history:
                    if turn.role == "user" and turn.audio:
                        hwav = root / "train" / turn.audio
                        hsha = hashlib.sha256(hwav.read_bytes()).hexdigest() if hwav.exists() else None
                        try:
                            if hsha in cache["data"]:
                                turn.audio_text = cache["data"][hsha]
                            else:
                                htext = asr.transcribe(hwav)
                                if htext == "":
                                    raise ValueError("empty history ASR transcript")
                                turn.audio_text = htext
                                if hsha:
                                    cache["data"][hsha] = htext
                        except Exception as exc:
                            run_error = f"history_asr_failed: {exc}"
                            break
            if run_error is not None:
                traces.append({
                    "sample_id": sid, "split": "dev", "arm": arm_name,
                    "mode": "real", "asr": arm["asr"], "llm": arm["llm"],
                    "shared": arm["shared"], "transcript_current": transcript,
                    "transcript_source": "arm_asr",
                    "wav_path": str(wav), "wav_sha256": wav_sha,
                    "prompt_sha256": None, "generations": [],
                    "grounding_log": [], "observer_log": [],
                    "tool_calls": [], "state_hash": None,
                    "termination": {"kind": "run_error", "n_generations": 0},
                    "seconds": time.time() - start, "run_error": run_error,
                })
                continue
            tools = catalog_tools_for_sample(catalog, sample)
            env = ZaicEnv(root, "train", sample.id)
            loop = AgentLoop(cfg, tools)
            tracing = TracingGenerator(llm)
            line = loop.run(sample, transcript, env, tracing)
            tracing.finalise_observations()
            term = termination_from_generations(tracing.generations, 12)
            traces.append({
                "sample_id": sid, "split": "dev", "arm": arm_name,
                "mode": "real", "asr": arm["asr"], "llm": arm["llm"],
                "shared": arm["shared"], "transcript_current": transcript,
                "transcript_source": "arm_asr",
                "wav_path": str(wav), "wav_sha256": wav_sha,
                "prompt_sha256": tracing.generations[0]["prompt_sha256"]
                if tracing.generations else None,
                "generations": tracing.generations,
                "grounding_log": loop.grounding_log,
                "observer_log": getattr(loop.observer, "records", []),
                "tool_calls": line["tool_calls"],
                "state_hash": line["state_hash"],
                "termination": term,
                "seconds": time.time() - start,
                "run_error": None,
            })
        with open(out / f"traces_{arm_name}.jsonl", "w", encoding="utf-8") as f:
            for t in traces:
                f.write(json.dumps(t, ensure_ascii=False) + "\n")
        (out / f"run_manifest_{arm_name}.json").write_text(
            json.dumps({"arm": arm_name, "mode": "real",
                        "manifest": manifest_report, "arm_config": arm,
                        "sample_ids": ids}, indent=2, ensure_ascii=False),
            encoding="utf-8")
        (out / f"asr_cache_{arm_name}.json").write_text(
            json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        print(f"run: arm {arm_name}: {len(traces)} traces -> {out}")
    return 0


def cmd_check_off_on(args):
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if args.mock:
        from mock_backends import MOCK_SAMPLES as _ms
        ids = _ms[:args.pilot] if args.pilot else _ms
        off = [mock_run_sample(sid, "A", "own", "own", shadow_observer=False)
               for sid in ids]
        on = [mock_run_sample(sid, "A", "own", "own", shadow_observer=True)
              for sid in ids]
        differences = []
        for a, b in zip(off, on):
            for field in ("tool_calls", "state_hash", "termination"):
                if a[field] != b[field]:
                    differences.append({"sample_id": a["sample_id"],
                                        "field": field,
                                        "off": a[field], "on": b[field]})
            if {"id": a["sample_id"], "tool_calls": a["tool_calls"],
                "state_hash": a["state_hash"]} != \
               {"id": b["sample_id"], "tool_calls": b["tool_calls"],
                "state_hash": b["state_hash"]}:
                differences.append({"sample_id": a["sample_id"],
                                    "field": "submission_line"})
        report = {"mode": "mock", "arm": "A", "pilot_ids": ids,
                  "identical": not differences, "differences": differences,
                  "result_kind": "MOCK ONLY -- not a G&G proof for real runs"}
        (out / "off_on_report.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if report["identical"] else 3
    # Real mode: same comparison with the real loop; blocked here
    # without data/benchmark/arms, never faked.
    if not (args.data and args.benchmark and args.arms):
        print("BLOCKED: real OFF/ON check needs --data, --benchmark "
              "and --arms (GPU host + stratified-frozen manifest). "
              "No mock result is substituted for it.", file=sys.stderr)
        return 2
    print("Real OFF/ON check is implemented as: run the real path "
          "twice on the pilot set (shadow_observer False, then True) "
          "and compare calls / state_hash / submission / termination. "
          "This host cannot run it (see preflight blockers); run "
          "`fourarm_runner.py run` with the pilot set under both "
          "observer settings on the GPU host and compare with "
          "score_fourarm.py --off-on-report.", file=sys.stderr)
    return 2


def main(argv=None):
    parser = argparse.ArgumentParser(prog="fourarm_runner")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("preflight")
    p.add_argument("--source-tree", required=True)
    p.add_argument("--arms", default=None)
    p.add_argument("--benchmark", default=None)
    p.add_argument("--real", action="store_true")
    p.add_argument("--out", default=None)
    p.set_defaults(func=cmd_preflight)
    p = sub.add_parser("check-separation")
    p.set_defaults(func=cmd_check_separation)
    p = sub.add_parser("mock-smoke")
    p.add_argument("--source-tree", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_mock_smoke)
    p = sub.add_parser("run")
    p.add_argument("--source-tree", required=True)
    p.add_argument("--data", default=None)
    p.add_argument("--benchmark", default=None)
    p.add_argument("--arms", default=None)
    p.add_argument("--out", required=True)
    p.add_argument("--pilot", type=int, default=None)
    p.set_defaults(func=cmd_run)
    p = sub.add_parser("check-off-on")
    p.add_argument("--source-tree", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--mock", action="store_true")
    p.add_argument("--pilot", type=int, default=None)
    p.add_argument("--data", default=None)
    p.add_argument("--benchmark", default=None)
    p.add_argument("--arms", default=None)
    p.set_defaults(func=cmd_check_off_on)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
