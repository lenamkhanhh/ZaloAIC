"""Build the self-contained Kaggle notebook; no remote execution here."""
import json
from pathlib import Path


def build():
    root = Path(__file__).resolve().parent
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
                "Only cuda:0 is used. Timing is not A30 timing.\n",
                "Outputs: summary, raw model text, ASR, tool traces and proxy scores in smoke_artifacts.zip.\n",
            ]},
            code(definitions, "runner"), code("main()\n", "launch"),
        ],
    }
    (root / "lifemate_smoke.ipynb").write_text(json.dumps(notebook, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    metadata = {
        "id": "khanhss/lifemate-smoke-dev5-20261027", "title": "LifeMate Smoke Dev5 20261027",
        "code_file": "lifemate_smoke.ipynb", "language": "python", "kernel_type": "notebook",
        "is_private": True, "enable_gpu": True, "enable_internet": True,
        "machine_shape": "NvidiaTeslaT4", "dataset_sources": [], "competition_sources": [],
        "kernel_sources": [], "model_sources": [],
    }
    (root / "kernel-metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    build()
