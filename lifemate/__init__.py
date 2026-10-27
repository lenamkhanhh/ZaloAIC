"""LifeMate pipeline (Zalo AI Challenge 2026) — runnable, stdlib core.

Model backends (faster-whisper, transformers, vLLM) are lazy imports in
``asr.py`` / ``llm.py``: importing this package never requires a GPU or
a model. The parts that run anywhere are: the real-data loader, the
zaic_tools adapter, the agent loop (observation after every call,
validator before every call, loop guard), typed grounding, the
official-style scorer, and the CLI in ``run.py``.

What this package is NOT: it is not a claim that a model baseline has
been run. On a machine without a GPU (like the dev VM this was built
on), ``infer`` fails fast with install instructions; the checks that
do run here are loader/adapter/scorer checks and fake/gold-replay
mechanics checks, labelled as such in RUN_LIFEMATE.md.
"""
