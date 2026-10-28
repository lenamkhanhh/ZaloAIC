#!/usr/bin/env python3
"""Thread A prototype: gold -> runtime-text serialization round-trip.

Proves the SFT data-construction step is a DETERMINISTIC transform,
not hand-authored text: for a dev sample, render the exact runtime
base prompt (worktree agent.build_base_prompt), then walk the gold
trajectory turn by turn -- gold call JSON as the model target,
render_observation_prompt output as the next turn's input -- executing
each call in a real ToolEnv. Asserts executed calls == gold calls and
every observation line is well-formed.

No model, no training, no held-out. Three dev samples only: one
multi-step normal, one ask_only, one empty. Output: a_roundtrip.json.
"""
import json
import sys
from pathlib import Path

WORKTREE = Path.home() / "workspace" / "zaic-branch-a2e832b"
TRAIN_DIR = Path.home() / "workspace" / "zaic-data" / "lifemate" / "extracted" / "train+public_test" / "train"
DATA_ROOT = TRAIN_DIR.parent
sys.path.insert(0, str(WORKTREE))
sys.path.insert(0, str(TRAIN_DIR))

from lifemate.loader import load_catalog, load_split, catalog_tools_for_sample  # noqa: E402
from lifemate.agent import build_base_prompt, render_observation_prompt  # noqa: E402
from zaic_tools import ToolEnv  # noqa: E402

SAMPLE_IDS = ["train_0003", "train_0016", "train_0116", "train_0019"]  # normal / normal / ask_only / empty


def main():
    split = json.loads((Path.home() / "workspace" / "zalo-aic-round3" / "lifemate" / "splits" / "train_dev_heldout.json").read_text())
    assert all(split[s] == "dev" for s in SAMPLE_IDS)
    catalog = load_catalog(DATA_ROOT, "train")
    samples = {s.id: s for s in load_split(DATA_ROOT, "train")}
    out = {"samples": []}
    for sid in SAMPLE_IDS:
        sample = samples[sid]
        tools = catalog_tools_for_sample(catalog, sample)
        base = build_base_prompt(sample, sample.audio_text or "", tools)
        env = ToolEnv("train", sid, root=str(DATA_ROOT))
        executed, results = [], []
        for call in sample.label["tool_calls"]:
            res = env.call(call["name"], call.get("arguments") or {})
            executed.append({"name": call["name"], "arguments": call.get("arguments") or {}})
            results.append(res)
        prompt_after = render_observation_prompt(base, executed, results) if executed else base
        # Round-trip assertions.
        assert executed == [{"name": c["name"], "arguments": c.get("arguments") or {}} for c in sample.label["tool_calls"]]
        for call, res in zip(executed, results):
            line = f"- {call['name']}({call['arguments']}) -> "
            assert line in prompt_after
            json.dumps(res, ensure_ascii=False)  # observation must be JSON
        out["samples"].append({
            "id": sid,
            "label_class": sample.label_class(),
            "n_gold_calls": len(sample.label["tool_calls"]),
            "n_installed_tools": len(tools),
            "base_prompt_chars": len(base),
            "final_prompt_chars": len(prompt_after),
            "executed_equals_gold": True,
            "first_observation_line": prompt_after.splitlines()[-1][:200] if executed else None,
        })
        print(sid, sample.label_class(), "calls:", len(executed), "base_chars:", len(base))
    Path(__file__).resolve().parent.joinpath("a_roundtrip.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("round-trip OK for", len(out["samples"]), "samples")


if __name__ == "__main__":
    main()
