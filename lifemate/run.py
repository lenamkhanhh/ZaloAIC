"""CLI for the LifeMate pipeline. Stdlib only; model backends lazy.

Usage (run from the repo root, or any cwd — paths are explicit):

  # 1. Sanity: replay gold label calls on N train samples through the
  #    real zaic_tools and compare changed apps vs label.final_state.
  python -m lifemate.run replay-gold --data <extracted train+public_test> --n 50

  # 2. Mechanics: run the agent with the empty policy on public_test
  #    (valid submission format, zero model) and self-check it by replay.
  python -m lifemate.run fake-run --data <...> --split public_test --limit 20 --out /tmp/sub.jsonl
  python -m lifemate.run check-submission --data <...> --split public_test --submission /tmp/sub.jsonl

  # 3. Score a submission file against train labels (official-style
  #    metric as documented in scoring.py; NOT the organiser evaluator).
  python -m lifemate.run score --data <...> --submission <file> --split train

  # 4. Full inference with real models (needs GPU + installed backends;
  #    fails fast with instructions on the CPU-only dev VM).
  python -m lifemate.run infer --data <...> --split public_test --config lifemate/configs/recommended.json --out submission.jsonl

  # 5. Build the fixed dev/held-out split file (ids only).
  python -m lifemate.run make-split --data <...> --out lifemate/splits/train_dev_heldout.json

Data layout: <data> is the extracted ``train+public_test/`` directory
containing ``train/`` and ``public_test/``. Raw data/audio/weights are
NEVER written to the repo by any command here.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lifemate.adapter import ZaicEnv  # noqa: E402
from lifemate.agent import AgentLoop  # noqa: E402
from lifemate.config import PipelineConfig  # noqa: E402
from lifemate.loader import catalog_tools_for_sample, fuzzy_params, load_catalog, load_split  # noqa: E402
from lifemate.scoring import score_sample, summarise  # noqa: E402
from lifemate.split import load_split_assignment, make_split, split_report, write_split  # noqa: E402


def parse_ids_file(path: str | Path) -> list[str]:
    """Read ids from a JSON file. Accepted shapes (in priority order):
    a bare list of ids (or of {"id": ...} objects), a dict with
    "smoke_ids", a dict with "probes" ([{"id": ...}, ...]), or a dict
    with "ids". This is how the ZAIC2 probe file
    (dev_probe_ids.json, "smoke_ids") is consumed without hard-coding
    its ids into the pipeline."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [item["id"] if isinstance(item, dict) else str(item) for item in data]
    if isinstance(data, dict):
        for key in ("smoke_ids", "ids"):
            if key in data:
                return [str(x) for x in data[key]]
        if "probes" in data:
            return [str(p["id"]) for p in data["probes"]]
    raise ValueError(f"unrecognised ids file shape in {path}")


def select_samples(samples, ids=None, ids_file=None):
    """Filter samples to an explicit id list, preserving the LISTED
    order (not file order) and failing fast on unknown ids — so
    `--ids train_0025,...` can never silently run the wrong samples.
    With neither argument, returns samples unchanged."""
    if ids is None and ids_file is None:
        return samples
    if isinstance(ids, str):
        ids = [x for x in (part.strip() for part in ids.split(",")) if x]
    wanted = list(ids) if ids is not None else parse_ids_file(ids_file)
    by_id = {s.id: s for s in samples}
    missing = [i for i in wanted if i not in by_id]
    if missing:
        raise ValueError(f"ids not found in this split: {missing}")
    return [by_id[i] for i in wanted]


def _gold_hash(data_root: Path, split: str, sample) -> str:
    """Diagnostic-only gold replay: fresh env, label calls, hash out.
    Never used as agent input and never merged into a submission."""
    env = ZaicEnv(data_root, split, sample.id)
    for call in sample.label["tool_calls"]:
        env.call(call["name"], call["arguments"])
    return env.state_hash()


def cmd_replay_gold(args) -> int:
    """Diagnostic ONLY (never agent input): replay each label's calls
    in a fresh env and compare the changed apps against
    label.final_state. Uses the library's documented debug accessor
    get_state() on diagnostic sessions only — the agent path in
    agent.py never calls it."""
    root = Path(args.data)
    samples = load_split(root, "train")[: args.n]
    ok_log, ok_final, mismatches = 0, 0, []
    for sample in samples:
        init = ZaicEnv(root, "train", sample.id)._env.get_state()
        env = ZaicEnv(root, "train", sample.id)
        for call in sample.label["tool_calls"]:
            env.call(call["name"], call["arguments"])
        final = env._env.get_state()
        changed = {app: st for app, st in final.items() if st != init.get(app)}
        if env.tool_calls() == sample.label["tool_calls"]:
            ok_log += 1
        if changed == sample.label["final_state"]:
            ok_final += 1
        else:
            mismatches.append(sample.id)
    print(f"replay-gold: {len(samples)} samples, log identical: {ok_log}, "
          f"changed-apps == label.final_state: {ok_final}")
    if mismatches:
        print(f"  final_state mismatches (first 10): {mismatches[:10]}")
    return 0


def cmd_fake_run(args) -> int:
    root = Path(args.data)
    samples = select_samples(load_split(root, args.split), args.ids, args.ids_file)
    if args.limit:
        samples = samples[: args.limit]
    out = Path(args.out)
    with open(out, "w", encoding="utf-8") as fout:
        for sample in samples:
            env = ZaicEnv(root, args.split, sample.id)
            # Empty policy: submit [] + initial-state hash. Format-valid,
            # zero model — a mechanics check ONLY, never a baseline.
            fout.write(json.dumps(env.submission_line(), ensure_ascii=False) + "\n")
    print(f"fake-run: {len(samples)} lines -> {out} (empty policy, mechanics only)")
    return 0


def cmd_check_submission(args) -> int:
    root = Path(args.data)
    lines = [json.loads(l) for l in open(args.submission, encoding="utf-8") if l.strip()]
    bad = 0
    for line in lines:
        env = ZaicEnv(root, args.split, line["id"])
        for call in line["tool_calls"]:
            env.call(call["name"], call["arguments"])
        replayed = env.submission_line()
        if replayed["state_hash"] != line["state_hash"] or replayed["tool_calls"] != line["tool_calls"]:
            bad += 1
            print(f"  MISMATCH {line['id']}")
    print(f"check-submission: {len(lines)} lines, {bad} mismatches (0 = submission is replay-consistent)")
    return 1 if bad else 0


def cmd_score(args) -> int:
    root = Path(args.data)
    catalog = load_catalog(root, args.split)
    fuzzy = fuzzy_params(catalog)
    samples = {s.id: s for s in load_split(root, args.split)}
    wanted = None
    if args.ids or args.ids_file:
        wanted = {s.id for s in select_samples(list(samples.values()), args.ids, args.ids_file)}
    results, classes = [], []
    for line in open(args.submission, encoding="utf-8"):
        if not line.strip():
            continue
        line = json.loads(line)
        if wanted is not None and line["id"] not in wanted:
            continue
        sample = samples[line["id"]]
        gh = _gold_hash(root, args.split, sample)
        results.append(score_sample(line, sample, gh, fuzzy))
        classes.append(sample.label_class())
    print(json.dumps(summarise(results, classes), indent=2, ensure_ascii=False))
    return 0


def cmd_make_split(args) -> int:
    root = Path(args.data)
    samples = load_split(root, "train")
    assignment = make_split(samples, seed=42, heldout_frac=0.2)
    write_split(args.out, assignment)
    print(json.dumps(split_report(samples, assignment), indent=2, ensure_ascii=False))
    print(f"split file (ids only) -> {args.out}")
    return 0


def cmd_infer(args) -> int:
    from lifemate.asr import FasterWhisperASR
    from lifemate.llm import VLLMGenerator

    config = PipelineConfig.from_json(args.config)
    root = Path(args.data)
    catalog = load_catalog(root, args.split)
    samples = select_samples(load_split(root, args.split), args.ids, args.ids_file)
    if args.limit:
        samples = samples[: args.limit]
    asr = FasterWhisperASR(config.asr_checkpoint, device="cuda",
                           compute_type="float16")
    llm = VLLMGenerator(config.llm_checkpoint, config.llm_revision, seed=config.llm_seed)
    out = Path(args.out)
    with open(out, "w", encoding="utf-8") as fout:
        for sample in samples:
            wav = root / args.split / sample.audio
            transcript = asr.transcribe(wav)
            # History user turns have no transcript on public_test
            # (train has audio_text); transcribe them too so the prompt
            # never has to guess history content.
            for turn in sample.history:
                if turn.role == "user" and turn.audio_text is None and turn.audio:
                    turn.audio_text = asr.transcribe(root / args.split / turn.audio)
            tools = catalog_tools_for_sample(catalog, sample)
            env = ZaicEnv(root, args.split, sample.id)
            loop = AgentLoop(config, tools)
            line = loop.run(sample, transcript, env, llm)
            fout.write(json.dumps(line, ensure_ascii=False) + "\n")
    print(f"infer: {len(samples)} lines -> {out}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="lifemate.run")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name, func in [
        ("replay-gold", cmd_replay_gold),
        ("fake-run", cmd_fake_run),
        ("check-submission", cmd_check_submission),
        ("score", cmd_score),
        ("make-split", cmd_make_split),
        ("infer", cmd_infer),
    ]:
        p = sub.add_parser(name)
        p.add_argument("--data", required=True, help="extracted train+public_test/ dir")
        if name in ("fake-run", "infer"):
            p.add_argument("--split", default="public_test")
            p.add_argument("--limit", type=int, default=None)
            p.add_argument("--out", required=True)
            p.add_argument("--ids", default=None,
                           help="comma-separated sample ids, in run order "
                                "(overrides positional selection; --limit "
                                "then truncates)")
            p.add_argument("--ids-file", default=None,
                           help="JSON file of ids: bare list, or dict with "
                                "smoke_ids / ids / probes")
        if name == "check-submission":
            p.add_argument("--split", required=True)
            p.add_argument("--submission", required=True)
        if name == "score":
            p.add_argument("--split", default="train")
            p.add_argument("--submission", required=True)
            p.add_argument("--ids", default=None,
                           help="comma-separated sample ids to score")
            p.add_argument("--ids-file", default=None,
                           help="JSON file of ids (see fake-run --ids-file)")
        if name == "replay-gold":
            p.add_argument("--n", type=int, default=50)
        if name == "make-split":
            p.add_argument("--out", required=True)
        if name == "infer":
            p.add_argument("--config", default="lifemate/configs/recommended.json")
        p.set_defaults(func=func)
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
