"""Build the self-contained Kaggle notebook; no remote execution here."""
import json
import argparse
from pathlib import Path


def build(output_dir=None, paired_inputs=None):
    root = Path(__file__).resolve().parent
    destination = Path(output_dir) if output_dir else root
    destination.mkdir(parents=True, exist_ok=True)
    source = (root / "smoke_runner.py").read_text(encoding="utf-8")
    definitions = source.rsplit('\nif __name__ == "__main__":', 1)[0]
    def code(text, cell_id):
        return {"id": cell_id, "cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": text.splitlines(True)}
    notebook = {
        "nbformat": 4, "nbformat_minor": 5,
        "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}},
        "cells": [
            {"id": "intro", "cell_type": "markdown", "metadata": {}, "source": [
                "# LifeMate dev5 GPU smoke\n",
                "Private diagnostic, not a benchmark or competition submission.\n",
                "PhoWhisper-small + Qwen3-4B, fixed dev IDs, seed 42, pinned source.\n",
                "Internet is used for setup; model calls use cached local weights.\n",
                "ASR uses cuda:0; FP16 LLM is balanced across two T4s. Timing is not A30 timing.\n",
                "Outputs: summary, raw model text, ASR, tool traces and proxy scores in smoke_artifacts.zip.\n",
            ]},
            code(definitions, "runner"), code("main()\n" if paired_inputs is None else
                "main(paired_inputs=" + repr(paired_inputs) + ")\n", "launch"),
        ],
    }
    if paired_inputs is not None:
        notebook["cells"][0]["source"] = [
            "# LifeMate paired current-transcript diagnostic\n",
            "Five fixed dev IDs, two arms: cached v3 ASR vs gold current transcript.\n",
            "Exact cached v3 ASR history in both arms. No prompt/model/seed changes.\n",
            "Gold is diagnostic only; not a deployable pipeline or benchmark.\n",
            "ASR model remains resident for matching placement; no ASR timing comparison.\n",
        ]
    # Kaggle CLI on Windows may read notebook JSON with the locale codec.
    # JSON escapes preserve Vietnamese text while keeping the upload ASCII.
    (destination / "lifemate_smoke.ipynb").write_text(json.dumps(notebook, ensure_ascii=paired_inputs is not None, indent=1) + "\n", encoding="utf-8")
    metadata = {
        "id": "khanhss/lifemate-smoke-dev5-20261027", "title": "LifeMate Smoke Dev5 20261027",
        "code_file": "lifemate_smoke.ipynb", "language": "python", "kernel_type": "notebook",
        "is_private": True, "enable_gpu": True, "enable_internet": True,
        "machine_shape": "NvidiaTeslaT4", "dataset_sources": [], "competition_sources": [],
        "kernel_sources": [], "model_sources": [],
    }
    (destination / "kernel-metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir")
    parser.add_argument("--paired-inputs", help="Local v3 ASR inputs JSON, embedded only in private diagnostic output")
    args = parser.parse_args()
    inputs = json.loads(Path(args.paired_inputs).read_text(encoding="utf-8")) if args.paired_inputs else None
    build(args.output_dir, inputs)
