"""Three real samples, one LLM load, full run/score and OFF/ON gates."""
import argparse
import gc
import os
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--source-tree", required=True)
    p.add_argument("--data", required=True)
    p.add_argument("--benchmark", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--asr-model-dir")
    args = p.parse_args()
    os.environ["TIER1A_PILOT_SIZE"] = "3"
    os.environ["TIER1A_SMOKE_ONLY"] = "1"
    import tier1a_runner as r
    import sys
    sys.path.insert(0, args.source_tree)
    from lifemate.config import PipelineConfig
    common = vars(args) | {"asr_backend": "transformers"}
    base = argparse.Namespace(**common)
    if r.cmd_asr_cache(base):
        return 2
    gc.collect()
    import torch
    torch.cuda.empty_cache()
    cfg = PipelineConfig(**r.verify_source(Path(args.source_tree))["config"])
    generator = r.build_pilot_llm(cfg)
    run = argparse.Namespace(**(common | {"mode": "B0,B-gold", "pilot": True,
                                          "observer": "on", "resume": False}))
    if r.cmd_run(run, shared_llm=generator):
        return 2
    off = argparse.Namespace(**(common | {"out": str(Path(args.out) / "off_on")}))
    if r.cmd_check_off_on(off, shared_llm=generator):
        return 2
    score = argparse.Namespace(**(common | {"traces": args.out, "pilot": True,
                                            "off_on": None}))
    return r.cmd_score(score)


if __name__ == "__main__":
    raise SystemExit(main())
